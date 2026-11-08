# Dev B Brief — Simulator / Baselines / Evaluation Lane

> Personal onboarding summary for **Dev B (roberto)**.
> Sources of truth: `RL/TEAM_PLAN.md` (contracts, ownership, milestones) and `RL/PLAN.md`
> (specification). This document is a digest — if it conflicts with those two, they win.

---

## 1. What the project is

A PV + battery + grid site in Romania. Every 15 minutes the system decides one of three
things: **charge (buy), discharge (sell), or hold**. Decisions are signed power levels, not
separate actions.

The "agent" is an **LLM** that re-plans every 4 hours over the rest of the delivery day, using:

- real **OPCOM PZU** 15-minute prices (known D-1, may be negative),
- **ENTSO-E** national actual load and day-ahead load forecast,
- an **ML PV forecast** (96-step delivery-day curve),
- the exact battery state.

It must beat simple baselines and be compared against an **MPC** (strong baseline) and a
**perfect-foresight LP** (upper bound).

> `IDEA.md` describes a PPO/RL agent; that is outdated. **`PLAN.md` supersedes it** — the agent
> is an LLM. PPO is optional Phase 10 only.

---

## 2. The team split

| Lane | Owner | Scope |
|---|---|---|
| A | other developer | Data pipeline (ENTSO-E, PVGIS, aligned dataset), ML PV model, LLM agent/prompts/tools |
| **B (you)** | **you** | **Simulator, agent context, schemas, baselines, metrics, evaluation harness** |

Critical path: `A data → B env/context → A agent → B eval`.

Lane A literally cannot interface with the environment until **your** contracts exist. Your
interfaces are frozen before parallel work starts (M0).

---

## 3. Your work in build order

### B1 — Simulator core (Phases 2–4) → milestone M0 / M1

**Files you own:**

```
src/battery_rl/env/battery.py
src/battery_rl/env/balance.py
src/battery_rl/env/env.py
src/battery_rl/env/context.py
src/battery_rl/agents/schemas.py     # B owns, A consumes
src/battery_rl/agents/base.py        # B owns, A consumes
src/battery_rl/eval/metrics.py
tests/test_battery.py
tests/test_env.py
tests/test_context.py
tests/test_schemas.py
```

**What it must do:**

- **Battery physics** — charge/discharge with η_c = η_d = 0.95, clip requested power to
  feasible bounds, SoC always in [0.1, 0.9], asset scale `s` multiplies capacity, P_max and PV.
  - `charge:    E_next = E + |P|·dt·η_c`
  - `discharge: E_next = E − P·dt/η_d`
  - `P_charge_max = (SoC_max − SoC)·C / (η_c·dt)`, capped at `P_max`
  - `P_discharge_max = (SoC − SoC_min)·C·η_d / dt`, capped at `P_max`
- **Balance/economics** — `P_net = demand − pv − P_discharge + P_charge`;
  `import = max(P_net, 0)`, `export = max(−P_net, 0)`;
  `cost_t = price·import·dt − price·export·dt` (positive = spent).
  **Energy conservation is the primary invariant test:**
  `pv + import + P_discharge = demand + P_charge + export + curtailment`.
- **Env** — `reset(day)` / `step(action)`; 17 signed levels
  `{-1, −0.875, …, 0, …, +0.875, +1} × P_max`; variable day length (92 / 96 / 100 intervals
  on DST days); the exact per-step `info` dict from TEAM_PLAN §3.4:
  ```
  timestamp_utc, step_index, pv_mw, load_mw, price_ron_mwh,
  soc, soc_next, p_charge_mw, p_discharge_mw,
  requested_level, executed_level, import_mw, export_mw,
  curtailed_mw, cost_ron, degradation_ron, violation_mwh, feasible
  ```
- **Context builder** — the versioned JSON from TEAM_PLAN §3.2: battery state, full-day prices,
  PV forecast for the rest of the day, realized PV so far, load forecast, grid limits, terminal
  value, previous plan.
- **Schemas** — pydantic models for context and schedule; `Planner` and `StepStrategy`
  protocols (TEAM_PLAN §3.5).
- **Metrics** — the fixed metric names from TEAM_PLAN §3.4:
  ```
  net_cost_ron, import_cost_ron, export_revenue_ron,
  renewable_utilization, self_consumption_ratio, wasted_mwh,
  throughput_mwh, equivalent_cycles, degradation_ron, violations_mwh,
  grid_import_mwh, grid_export_mwh, soc_min, soc_max, soc_end,
  llm_feasible_rate, llm_invalid_rate, llm_tool_calls, llm_tokens, llm_latency_s, llm_cost_ron
  ```

**Acceptance (Phase 2–4 exits):**
- random feasible schedule runs 96 steps with valid SoC and conserved energy;
- schema round-trip; context covers the rest of day; causality (no future actuals);
- with penalties zero, score equals negative cash flow;
- hand-computed mini-day metrics match.

### B2 — Baselines + MPC + oracle (Phase 5) → M2

**Files:**

```
src/battery_rl/strategies/idle.py
src/battery_rl/strategies/rule_based.py
src/battery_rl/strategies/price_threshold.py
src/battery_rl/strategies/mpc.py        # 4-hour receding LP, SciPy linprog
src/battery_rl/strategies/oracle_lp.py  # perfect-foresight day LP
configs/env.yaml                        # already exists
```

**Behavior:**

| Strategy | Behavior |
|---|---|
| `Idle` | hold always; zero throughput |
| `RuleBased` | charge on PV surplus, discharge on deficit, deadband to avoid chattering |
| `PriceThreshold` | charge below daily price quantile, discharge above |
| `MPC` | every 4 h solve an LP over rest of day (PV forecast + known prices), execute first 4 h |
| `OracleLP` | perfect-foresight whole-day LP; upper bound only |

MPC and OracleLP must use **the same battery model and objective** as the environment — that is
what makes the comparison exact.

**Acceptance:** idle has zero throughput; rule-based behaves as expected; **MPC beats
rule-based**; oracle is the highest.

### B3 — Evaluation harness (Phase 6) → M2 / M3

**Files:**

```
src/battery_rl/eval/runner.py
src/battery_rl/eval/report.py
scripts/evaluate.py
scripts/make_report.py
configs/eval.yaml                       # already exists
```

**What it must do:**
- run both per-step strategies (`StepStrategy.act`) and block planners
  (`Planner.plan(context, execution_steps)`);
- handle variable DST day length;
- collect per-step records + per-day metrics;
- aggregate by regime (high/low/volatile price, sunny/cloudy, weekend) and across 3 repeats;
- produce CSV + plots, optionally `report.md`.

**Acceptance:** repeatable comparison table for idle/rule/MPC/oracle on the validation split;
runner determinism.

---

## 4. Frozen contracts you produce (A consumes them)

TEAM_PLAN §3 is the contract. Changes require a PR to `TEAM_PLAN.md` + a message to A; no
silent changes.

1. **Context JSON** (§3.2) — versioned, `context_version: "1"`.
2. **Action space / schedule JSON** (§3.3) — 17 signed levels; `execution_steps =
   min(16, steps_remaining)`; schedule payload
   `{"schedule": [{"interval": 0, "level": -0.5}, ...], "rationale": "..."}`.
3. **Step `info` + metric names** (§3.4) — listed above; do not rename.
4. **Planner protocols** (§3.5):
   ```python
   class Planner(Protocol):
       def plan(self, context: dict, execution_steps: int) -> list[int]: ...

   class StepStrategy(Protocol):
       def act(self, info: dict) -> int: ...
   ```
5. **Schema validation** (§3.6) — length 16 (or `min(16, remaining)`), levels in the 17-value
   set, SoC feasibility bounds.

---

## 5. What you consume from A (none of it exists yet)

- `src/battery_rl/data/dataset.py` →
  ```python
  @dataclass(frozen=True)
  class DayData:
      day: date
      intervals: int
      price_ron_mwh: np.ndarray
      load_mw: np.ndarray
      load_forecast_mw: np.ndarray
      pv_mw: np.ndarray
      pv_forecast_mw: np.ndarray
      pv_forecast_issue_utc: list[str]

  def load_days(path: Path) -> dict[date, DayData]: ...
  def load_split(split: str) -> list[DayData]: ...
  ```
- `tests/fixtures/tiny_day.csv` — 96 rows, all contract columns
  (+ `tiny_day_spring.csv` = 92, `tiny_day_fall.csv` = 100).
- `src/battery_rl/models/stub.py::StubPVModel`.

**Blocked rule:** never wait more than 2 hours on A. Use the fixture/stub; if it doesn't exist
yet, use inline synthetic arrays in **your own** test files and keep going. Do not invent a
second schema.

Ownership note: `tests/fixtures/*` belongs to A per the ownership map — coordinate on who
creates `tiny_day.csv` rather than writing it yourself.

---

## 6. Current repo state (as of 2026-11-07)

**Done (shared infrastructure — do not rebuild):**
- Phase 0: `src/battery_rl/config.py`, `seeding.py`, `data/opcom.py`, existing tests;
- Phase 1A: backend + frontend farm-config UI, exported `configs/farm.yaml` (+ `.sha256`);
- configs: `env.yaml`, `eval.yaml`, `agent.yaml`, `pv_model.yaml`, `farm.yaml`.

**Empty (your lane):** `env/`, `eval/`, `strategies/`, `agents/` contain only `__init__.py`.

**Data present:** `artifacts/data/processed/opcom_pzu_2026.csv` (~29.8k rows) and
`ENTSO_15MIN.csv` (~35k rows). The aligned dataset, PV model, and fixtures do **not** exist yet.

**Branch:** started from `main` → current RL work (main is an ancestor of the branch point).

---

## 7. Milestones you are part of

| Checkpoint | Merge criteria (your part) |
|---|---|
| **M0 — Interface freeze** | §3 agreed; schemas + stub modules; contract tests skeleton; main green |
| **M1 — First vertical slice** | env + context build; idle/rule run one fixture day end-to-end |
| **M2 — Data + baselines** | env/context integrated; MPC/oracle + eval harness on validation |
| **M3 — Agent integrated** | LLM mocked tests pass; one-day smoke, six decisions, all feasible |
| **M4 — Receding evaluation** | LLM vs idle/rule/MPC/oracle on validation, 3 repeats |
| **M5 — Freeze + report** | test split frozen; final table/plots; reproducible from README |

Merge to `main` at M0–M5 only. Each merge runs: RL `pytest`, backend `pytest` (if touched),
frontend build/lint (if touched), and `ruff check`.

---

## 8. Rules of engagement (from TEAM_PLAN)

- One owner per file; never edit the other lane's files.
- Shared files (`config.py`, `PLAN.md`, `TEAM_PLAN.md`, `pyproject.toml`, `README.md`) change by
  PR with notice.
- Small PRs (< ~400 lines); rebase on `main` before each block.
- No direct pushes to `main`; no force-push to `main`.
- Update the **status log** at the bottom of `TEAM_PLAN.md` every work block — it is the
  handoff record.
- Tests are the contract; CI must stay green.
- Blocked on A? Use fixture/stub, post the blocker in the status log, continue another task.

**Branches:** `b/env-context` then `b/baselines-eval` per the plan. This working branch is
`robisimulator` (your personal name), created at Dev B's request.

---

## 9. Suggested first move (M0 — interface freeze)

1. Cut a working branch (done: `robisimulator`).
2. Write `agents/schemas.py` + `agents/base.py` + `tests/test_schemas.py` — pure contract, no
   data dependency. **Start here: A is blocked on these.**
3. Write `env/battery.py` + `env/balance.py` + `tests/test_battery.py` — pure physics, no data
   dependency.
4. Agree §3 with A and confirm who produces `tiny_day.csv`.
5. Then env/context + fixture day end-to-end → **M1**.

---

## 10. Quick reference

```bash
cd RL
python -m venv .venv && . .venv/bin/activate      # macOS
pip install -e ".[dev]"
pytest                                            # RL tests
ruff check .
```

Key paths:

```
RL/TEAM_PLAN.md            # contract + ownership + status log
RL/PLAN.md                 # full specification
RL/configs/env.yaml        # 17 levels, objective weights
RL/configs/eval.yaml       # splits, repeats, strategies, regimes
RL/configs/farm.yaml       # active seed farm (UI-exported)
RL/src/battery_rl/config.py
```
