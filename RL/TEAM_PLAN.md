# TEAM_PLAN — Parallel Development with Two Developers

Status: 2026-11-07. Companion to `PLAN.md`.
Map the two roles to your names before starting.

- **Dev A — Data / ML / Agent lane**
- **Dev B — Simulator / Baselines / Evaluation lane**

Phase 0 (skeleton/config) and Phase 1A (farm configuration UI) are **done** and are shared
infrastructure. Do not rebuild them. This plan covers Phase 1B onward.

---

## 1. Rules that make async work

1. **Interfaces are frozen before parallel work.** Section 3 is the contract. Changes require
   a PR to this file and a message to the other developer; no silent changes.
2. **No one waits more than 2 hours on the other.** If a dependency is missing, use the
   fixture/stub listed in section 7 and keep going.
3. **One owner per file.** Do not edit the other lane's files. Shared files change by PR and
   with a note in the status log.
4. **Small merges, early merges.** Merge at every checkpoint (section 5), not at the end.
5. **Async status log.** Update the table at the end of this file each work block. It is the
   handoff record.
6. **Tests are the contract.** Every interface change updates its test; CI must stay green.

---

## 2. Ownership map

| Area | Owner | Files |
|---|---|---|
| ENTSO-E parsing, PVGIS, PV model, aligned dataset | A | `data/entsoe.py`, `data/pv.py`, `data/forecasts.py`, `data/dataset.py`, `models/pv.py`, `scripts/build_dataset.py`, `scripts/train_pv.py`, `configs/pv_model.yaml` |
| LLM agent, prompts, tools, transcripts | A | `agents/llm.py`, `agents/prompts.py`, `agents/tools.py`, `configs/agent.yaml`, `tests/test_llm_agent.py` |
| Simulator, battery, balance, context builder | B | `env/battery.py`, `env/balance.py`, `env/env.py`, `env/context.py`, `tests/test_battery.py`, `tests/test_env.py`, `tests/test_context.py` |
| Objective, metrics, baselines, MPC, oracle | B | `eval/metrics.py`, `strategies/*`, `configs/env.yaml` |
| Evaluation runner, reports, plots | B | `eval/runner.py`, `eval/report.py`, `scripts/evaluate.py`, `scripts/make_report.py`, `configs/eval.yaml` |
| Schemas and planner protocol | B (A consumes) | `agents/schemas.py`, `agents/base.py`, `tests/test_schemas.py` |
| Config contract (`config.py`) | Both, PR required | `src/battery_rl/config.py` |
| Data fixtures | A | `tests/fixtures/*` |
| Farm config UI (done) | Shared | `backend/`, `frontend/` — changes require notice |
| Results dashboard (optional, Phase 11) | A | `backend/app/api/routes/simulate.py`, `frontend/src/pages/Simulation.tsx` |
| `PLAN.md`, `TEAM_PLAN.md`, `pyproject.toml`, `README.md` | Both, one at a time | announce before editing |

---

## 3. Interface freeze (Block 1 deliverable)

### 3.1 Aligned dataset

Path: `RL/artifacts/data/processed/aligned_2026.csv`
Metadata: `dataset_meta.json`, `splits.json`, `data_card.md`.

| Column | Type | Unit | Notes |
|---|---|---|---|
| `timestamp_utc` | ISO 8601 UTC | — | Start of the 15-min interval |
| `delivery_date` | `YYYY-MM-DD` | — | Europe/Bucharest local day |
| `interval` | int | — | 1..N; N = 96, 92 (29 Mar) or 100 (25 Oct) |
| `price_ron_mwh` | float | RON/MWh | OPCOM PZU; known D-1; may be negative |
| `load_mw` | float | MW | ENTSO-E national actual load, not scaled |
| `load_forecast_mw` | float | MW | ENTSO-E day-ahead forecast |
| `pv_mw` | float | MW | PV production, scaled by farm `s` |
| `pv_forecast_mw` | float | MW | ML forecast for this interval, scaled by `s` |
| `pv_forecast_issue_utc` | ISO 8601 UTC | — | Latest 4-hour boundary at or before the target |
| `is_complete` | bool | — | False if the interval touches a known data gap |

Rules:

- Build from the active `RL/configs/farm.yaml`; record its checksum in `dataset_meta.json`.
- `pv_forecast_mw` must be causal: the issue time is `<= timestamp_utc`; never use future
  actual weather. The oracle column is simply `pv_mw` and is only used for ablations.
- DST days keep their real 92/100 intervals; do not fabricate 96-step days.
- `dataset.py` API (B consumes):
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
- `splits.json`:
  ```json
  {"train": ["2026-01-01", "2026-07-31"],
   "val":   ["2026-08-01", "2026-09-30"],
   "test":  ["2026-10-01", "2026-11-06"]}
  ```

### 3.2 Agent context (versioned)

`agents/schemas.py` defines this exactly; `env/context.py` builds it; the LLM consumes it.

```json
{
  "context_version": "1",
  "delivery_day": "2026-11-05",
  "farm": {"name": "seed", "lat": 44.4, "lon": 26.1, "kwp": 6000.0, "asset_scale": 1.0},
  "time_utc": "2026-11-05T12:00:00Z",
  "step_index": 48,
  "steps_remaining": 48,
  "execution_steps": 16,
  "battery": {
    "capacity_mwh": 10.0, "p_max_mw": 2.0, "soc": 0.42,
    "soc_min": 0.10, "soc_max": 0.90, "eta_c": 0.95, "eta_d": 0.95,
    "degradation_cost_ron_per_mwh": 50.0
  },
  "market": {"currency": "RON", "prices_ron_mwh": "[intervals]"},
  "pv": {"now_mw": 3.1, "forecast_mw": "[steps_remaining]", "realized_so_far_mw": "[step_index]"},
  "load": {"now_mw": 5788.0, "forecast_mw": "[steps_remaining]"},
  "limits": {"export_limit_mw": null, "import_limit_mw": null},
  "terminal_value": {"price_ron_mwh": 735.0, "mode": "episode_mean_price"},
  "previous_plan": ["[execution_steps]"]
}
```

### 3.3 Schedule and action space

- 17 signed levels: `{-1, -0.875, …, 0, …, +0.875, +1} × P_max`; positive = discharge/sell.
- Schedule length = `execution_steps = min(16, steps_remaining)`; on DST days the last block
  can be shorter.
- JSON:
  ```json
  {"schedule": [{"interval": 0, "level": -0.5}, ...], "rationale": "..."}
  ```
  `level` must be one of the 17 values; the same values are exposed as action indices 0..16.

### 3.4 Step info and metrics

`info` per step (B produces, B consumes in metrics):

```
timestamp_utc, step_index, pv_mw, load_mw, price_ron_mwh,
soc, soc_next, p_charge_mw, p_discharge_mw,
requested_level, executed_level, import_mw, export_mw,
curtailed_mw, cost_ron, degradation_ron, violation_mwh, feasible
```

Per-day metrics (fixed names):

```
net_cost_ron, import_cost_ron, export_revenue_ron,
renewable_utilization, self_consumption_ratio, wasted_mwh,
throughput_mwh, equivalent_cycles, degradation_ron, violations_mwh,
grid_import_mwh, grid_export_mwh, soc_min, soc_max, soc_end,
llm_feasible_rate, llm_invalid_rate, llm_tool_calls, llm_tokens, llm_latency_s, llm_cost_ron
```

### 3.5 Planner interface

```python
class Planner(Protocol):
    # Plans over the rest of the day; returns execution_steps signed action indices.
    def plan(self, context: dict, execution_steps: int) -> list[int]: ...

class StepStrategy(Protocol):
    def act(self, info: dict) -> int: ...
```

B implements the runner (both interfaces). A implements `LLMAgent.plan`; B's MPC/oracle use
the same `plan` interface.

### 3.6 Contract tests

- `tests/test_data_contract.py` (A): columns, dtypes, units, no leakage, DST counts.
- `tests/test_context_contract.py` (B): versioned keys, lengths, causality.
- `tests/test_schemas.py` (B): schedule validation and bounds.
- `tests/test_rl_export_contract.py` (already exists in backend): farm YAML checksum.

---

## 4. Parallel lanes

### Lane A — Data, PV model, LLM agent

**A1. Data pipeline (Phase 1B)**
- [ ] `data/entsoe.py`: parse the received CSV, CET/CEST → UTC, gaps, 15-min alignment.
- [ ] `data/pv.py`: PVGIS fetch at the farm coordinates, hourly → 15-min, scale by `s`;
      metered loader if available.
- [ ] `data/forecasts.py`: join prices, load forecast, and the ML PV forecast by 4-hour issue.
- [ ] `data/dataset.py`: `DayData` loader and split loader to the contract.
- [ ] `scripts/build_dataset.py`: write `aligned_2026.csv`, `dataset_meta.json`,
      `splits.json`, data card and validation report.
- [ ] `tests/test_data_contract.py`.

**A2. PV forecast model (Phase 1B)**
- [ ] Fetch archived NWP forecasts (Open-Meteo) at the farm coordinates.
- [ ] `models/pv.py`: features from `pv_model.yaml`; `HistGradientBoostingRegressor` first.
- [ ] `scripts/train_pv.py`: chronological train/val/test, MAE/RMSE by lead time, save model.
- [ ] Generate `pv_forecast_mw` for every interval by issue time; snapshot into the dataset.
- [ ] Fixture/stub: `tests/fixtures/tiny_day.csv` (Block 1) and `StubPVModel` for B.

**A3. LLM agent (Phase 7)**
- [ ] `agents/llm.py`: Anthropic client, structured JSON output, retries, token/latency logs.
- [ ] `agents/prompts.py`: versioned system/user prompt with the contract table.
- [ ] `agents/tools.py`: `get_state`, `get_forecast`, `simulate_schedule`, `submit_schedule`;
      `simulate_schedule` calls B's env/runner.
- [ ] Validate length, levels, SoC feasibility; one retry; rule-based fallback.
- [ ] `tests/test_llm_agent.py` with a mocked client (no API key in CI).
- [ ] One-day smoke test: six decisions, feasible schedules, token log.

### Lane B — Simulator, baselines, evaluation

**B1. Environment and context (Phases 2–4)**
- [ ] `env/battery.py`: feasible power, SoC update, efficiencies, asset scale.
- [ ] `env/balance.py`: PV→load→battery→grid priority, import/export, cost.
- [ ] `env/env.py`: reset/step, 17-level mapping, variable day length, `info` contract.
- [ ] `env/context.py`: build the versioned context from the dataset and battery state.
- [ ] `agents/schemas.py` + `agents/base.py`: context, schedule, Planner/StepStrategy.
- [ ] `eval/metrics.py`: the fixed metric names; degradation and violations.
- [ ] Tests: energy conservation, SoC bounds, context lengths, fixture day.

**B2. Baselines and reference optimization (Phase 5)**
- [ ] `strategies/idle.py`, `rule_based.py`, `price_threshold.py`.
- [ ] `strategies/mpc.py`: every 4 h solve an LP on the PV forecast + known prices; execute
      `execution_steps`.
- [ ] `strategies/oracle_lp.py`: perfect-foresight day LP (upper bound).
- [ ] Tests on the fixture and one real day.

**B3. Evaluation harness (Phase 6)**
- [ ] `eval/runner.py`: per-step strategies and block planners; variable DST day length.
- [ ] `scripts/evaluate.py`: run all strategies on a split, write CSV + plots.
- [ ] `eval/report.py`, `scripts/make_report.py`: aggregate by regime and repeats.
- [ ] Tests: hand-computed mini-day metrics; runner determinism.

### Joint — Integration and final evaluation

- [ ] Merge at checkpoints; run both test suites.
- [ ] Integrate the LLM agent with the real env/eval (A calls B's runner).
- [ ] Run the 4-hour receding-horizon evaluation on validation; three repeats per day.
- [ ] Tune prompts only on validation; freeze before test.
- [ ] Final test split, report, optional results dashboard.

---

## 5. Milestones and merge checkpoints

| Checkpoint | Owner | Merge criteria |
|---|---|---|
| **M0 — Interface freeze** | Both | Section 3 agreed; `tiny_day.csv`; schemas + stub modules; contract tests skeleton; main green |
| **M1 — First vertical slice** | A+B | Prices/load/PV dataset skeleton; env + context build; idle/rule run one fixture day end-to-end |
| **M2 — Data + baselines** | A+B | Aligned dataset + PV model with horizon MAE; env/context integrated; MPC/oracle + eval harness on validation |
| **M3 — Agent integrated** | A+B | LLM mocked tests pass; one-day smoke with six decisions, all feasible; token/latency logged |
| **M4 — Receding evaluation** | Both | LLM vs idle/rule/MPC/oracle on validation, 3 repeats; open-loop vs receding; no interface drift |
| **M5 — Freeze + report** | Both | Test split frozen; final table/plots; report; optional UI; reproducible from README commands |

Merge to `main` at M0–M5 only. Each merge runs: RL `pytest`, backend `pytest` (if touched),
frontend build/lint (if touched), and `ruff check`.

---

## 6. Async workflow

### Branches
- A: `a/data-pv`, then `a/llm-agent`.
- B: `b/env-context`, then `b/baselines-eval`.
- Small PRs (target < 400 lines); rebase on `main` before starting a block.
- No direct pushes to `main`; no force-push to `main`.

### Status log (update every work block)

| Date | Owner | Done | Next | Blockers | Interface change |
|---|---|---|---|---|---|
| 2026-11-07 | Both | Phase 0 + 1A done | M0 interface freeze | none | — |

### Interface changes
- PR touching `agents/schemas.py`, `config.py`, `data/dataset.py`, or this section.
- Both developers approve or comment within the same block; until then, use the old shape.
- Add a one-line entry to the status log and the version string if the context changes.

### Blocked rule
- Missing data? Use `tests/fixtures/tiny_day.csv` or `StubPVModel`.
- Missing context/tool? Use the frozen schema and a stub; do not invent a second schema.
- Missing LLM key? Mock the client; integration uses the key later.
- Post the blocker in the status log; continue on another task in your lane.

---

## 7. Fixtures and stubs (Block 1)

- `tests/fixtures/tiny_day.csv`: 96 rows for one day with all contract columns; a simple
  price shape (low night, evening peak), a midday PV bell, flat-ish load.
- `tests/fixtures/tiny_day_spring.csv`: 92 intervals around the spring transition.
- `tests/fixtures/tiny_day_fall.csv`: 100 intervals around the fall transition.
- `models/stub.py::StubPVModel`: returns a clear-sky/persistence forecast; B uses it until A's
  model is ready.
- `agents/stub.py::StubLLMClient`: returns a fixed valid schedule; A uses it in CI.
- `strategies/stub.py::HoldPlanner`: returns all-zero actions; B uses it for runner tests.
- A fixture dataset is enough for every B task; B is never blocked on real data.

---

## 8. Suggested schedule (work blocks, two people)

| Block | Lane A | Lane B | Joint output |
|---|---|---|---|
| 0 (30 min) | Select seed farm in UI, activate, confirm `farm.yaml` | Same | Frozen farm config/checksum |
| 1 (0.5 day) | Dataset contract, fixtures, data skeleton | Context/schedule/info contracts, env skeleton | **M0** interfaces + stubs |
| 2 (1 day) | ENTSO parse, PVGIS, dataset build | Battery/balance/env/context/objective | **M1** vertical slice |
| 3 (1 day) | PV model, forecasts, dataset validation | Baselines, MPC, oracle, eval harness | **M2** data + baselines |
| 4 (1 day) | LLM client/prompts/tools, mocked tests | Runner integration, metrics, report | **M3** agent integrated |
| 5 (0.5–1 day) | Prompt tuning on validation, transcripts | Receding-horizon runs, metrics, plots | **M4** evaluation |
| 6 (0.5 day) | Report sections + optional UI | Final test metrics + plots | **M5** freeze/report |

Total: roughly **4.5–5.5 working days**, or compress to three 4-hour blocks for a 48-hour
hackathon. The critical path is `A data → B env/context → A agent → B eval`.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Interface drift between A and B | Section 3 frozen; contract tests; status log |
| A blocked on NWP/PVGIS | Ship prices/load first; stub PV forecast; label the fallback |
| B blocked on real dataset | `tiny_day.csv` + `StubPVModel` from Block 1 |
| LLM key/quota unavailable | Mocked client in CI; key only for integration; rule-based fallback |
| Merge conflicts | File ownership, small PRs, checkpoint merges |
| MPC too slow/complex | SciPy `linprog` on the deterministic day; start with a simple LP |
| DST/variable day length bugs | Fixture variants; contract tests for 92/96/100 intervals |
| Scope creep into Phase 11 | Results dashboard only after M5, explicitly optional |

---

## 10. Definition of done

**Lane A**
- Aligned dataset + data card + splits; PV model with per-horizon error and no leakage.
- LLM agent with structured output, validation, fallback, transcripts, token/latency logs.
- Tests for data contract, PV model, mocked agent.

**Lane B**
- Simulator with energy conservation, SoC bounds, 17 levels, variable day length.
- Idle/rule/price-threshold/MPC/oracle baselines and the evaluation harness.
- Metrics with fixed names, per-regime aggregation, plots.

**Joint**
- On the held-out test split, the LLM beats idle and rule-based (target ≥ 5% vs rule-based)
  and reports the gap to MPC/oracle; all IDEA + LLM metrics reported.
- Three repeats per day; model ID, prompt version, config checksum and raw outputs stored.
- Reproducible from documented commands; optional results dashboard reproduces the same numbers.
