# PLAN — Battery Energy Optimization: ML PV Forecast + LLM Dispatch

Status: 2026-11-07. This supersedes the earlier PPO-first draft.
Project directory: `RL/`. Scope: real-data ingestion, PV production model, battery simulator,
LLM dispatch agent, baselines, evaluation and (optional) dashboard.

---

## 0. Architecture at a glance

```
Farm configuration UI (map + form)
        │  location, kWp, tilt, azimuth, battery, asset scale s
        ▼
configs/farm.yaml (active/seed config, checksummed)
        │
        ├──► Open-Meteo archive / metered PV ──► ML PV model ──► 96-step PV forecast
        │
OPCOM PZU prices (known D-1, 96 steps) ────────┤
ENTSO-E national load (market context) ───────┤
Battery state (SoC, limits, scaled assets) ────┘
                                               ▼
                         small LLM agent, receding horizon every 4 h
                                               │
                                               ▼
                    signed battery schedule for the next 16 intervals
                                               │
                                               ▼
                         simulator → cash flow, SoC, energy flows, metrics
```

Pipeline stages:

0. **Farm configuration (UI).** A map selects the seed farm location; the form sets PV,
   battery and the asset scale `s`. Saving/activating exports `configs/farm.yaml`, which is the
   single input to every later stage. This must exist before the PV model is trained.
1. **PV forecast (offline ML).** A gradient-boosted model predicts the 96-step PV production
   curve for the delivery day from weather forecasts and site parameters. It is re-run at each
   4-hour boundary with the latest available inputs.
2. **Dispatch (LLM).** Every 4 hours a small LLM receives the PV forecast, the day's price
   list, the battery state and realized production. It returns a signed power schedule for
   the next 4 hours. The simulator executes it and the loop repeats.
3. **Evaluation.** The LLM agent is compared with idle, rule-based, an MPC baseline and a
   perfect-foresight LP oracle. Price is never forecast: PZU is known D-1.

---

## 1. Decisions and assumptions

Values from `IDEA.md` are fixed unless marked otherwise. Decisions dated 2026-11-07 were
taken during design; open items are listed at the end of this section.

| Parameter | Value | Source |
|---|---|---|
| Episode length | 24 h = 96 steps | IDEA |
| Step duration | 15 min (`dt = 0.25 h`) | IDEA |
| Battery capacity | 10 MWh | IDEA |
| Max charge / discharge power | 2 MW / 2 MW | IDEA |
| SoC limits | 10% – 90% | IDEA |
| Charge / discharge efficiency | 95% / 95% | IDEA |
| Asset scale `s` | UI parameter; scales PV, battery power and capacity together; default 1; national load is not scaled | decision |
| Farm configuration | map-based UI; selects the seed farm and exports `configs/farm.yaml` | decision |
| Site demand | 0 MW: merchant PV + battery asset, no local consumer (deviation from IDEA's consumer component) | decision |
| Buy price | OPCOM PZU, 15-min, RON/MWh | decision |
| Sell price | OPCOM PZU, 15-min, RON/MWh | decision |
| Price input | current delivery day, 96 steps (known D-1) | decision |
| Price forecast | none required; no price model | decision |
| Load context | ENTSO-E RO national actual load + day-ahead forecast; market context only, not the site demand | decision |
| PV source | Open-Meteo archive irradiance × PR (default); optional metered CSV; PVGIS proxy for 2005–2023 | decision |
| PV forecast | ML model, 96-step day curve, re-run every 4 h | decision |
| Action space | signed battery power, 17 levels (−1 … +1 × P_max; 0.25 MW steps at P_max=2 MW) | decision |
| Decision agent | small LLM (default `deepseek-chat`) | decision |
| Receding horizon | every 4 h, 6 decisions/day | decision |
| Planning horizon | rest of the delivery day; execution window 4 h | decision |
| Grid export limit | none | decision |
| Grid import limit | unlimited | decision |
| Currency | RON internally; EUR display only | decision |
| Data window | 2026-01-01 → 2026-11-06 (complete actuals; prices through 11-07) | decision |

Consequences to keep explicit in the report:

- **No export limit** means all surplus is sold, so `wasted energy = 0` and renewable
  utilization is always 100%. Both metrics are still reported for IDEA compliance but are
  not discriminating; net cost, export revenue, self-consumption and battery metrics are.
- **Buy price = sell price = PZU** makes this an energy-only model: no retail margin, network
  tariffs, taxes or imbalance costs. With 90.25% round-trip efficiency, grid charging only
  pays if the later price exceeds the current price divided by 0.9025 plus degradation.
- **Merchant site, zero local demand.** The site only exchanges power with the grid; the
  national ENTSO-E load is market context, not site demand. This keeps the battery material
  at `s=1` and avoids the absurd economics of a 6 MW site importing ~5,000 MW. The asset
  scale `s` scales PV and battery together; national load is never scaled.

Open items (must be resolved before Phase 9):

1. Whether metered PV is available; otherwise Open-Meteo archive irradiance is used, with
   PVGIS available as a 2005–2023 proxy.
2. Demo scope and evaluation window.
3. Final evaluation cut-off (recommend 2026-11-06 for complete actual load).

Resolved: LLM provider/model is `deepseek-chat`; `DEEPSEEK_API_KEY` and optional
`DEEPSEEK_BASE_URL` live in `RL/.env`, loaded by `battery_rl.credentials`.

The seed farm location, PV/battery parameters and asset scale `s` are selected in the Phase 1A
UI. At least one saved/active configuration is required before Phase 1B starts; there is no
plan-level default.

---

## 2. Repository layout

```
RL/
  pyproject.toml
  README.md
  PLAN.md
  IDEA.md
  PV_MODEL.md              # PV model architecture, training and results
  configs/
    env.yaml               # episode, action levels, objective
    pv_model.yaml          # features, model, forecast horizon
    agent.yaml             # model id, prompt version, horizon, limits
    eval.yaml              # splits, regimes, repeats, output paths
    farm.yaml              # exported active farm config (from the UI; training input)
  scripts/
    download_opcom.py      # CLI: OPCOM PZU scraper (implemented)
    build_dataset.py       # CLI: align, validate, split, write data card + plots
    train_pv.py            # CLI: train and evaluate the PV forecast model
    evaluate.py            # CLI: run baselines + LLM agent, write metrics
    make_report.py         # CLI: plots + report.md
  src/battery_rl/
    __init__.py
    config.py              # dataclasses/pydantic for all YAML configs
    seeding.py             # seeds for numpy/torch/env where applicable
    credentials.py         # RL/.env loader and agent key/base-URL helpers
    data/
      opcom.py             # PZU 15-min prices (implemented)
      entsoe.py            # national load + day-ahead forecast, CET/CEST → UTC
      pv.py                # metered / Open-Meteo archive / PVGIS / clear-sky sources
      nwp.py               # Open-Meteo Single Runs client, run fallback, aerosol
      forecasts.py         # forecast issue times; price is passed through as known
      dataset.py           # DayData loading, validation, splits, data card
    models/
      pv.py                # ML PV forecast: features + HistGradientBoosting
      stub.py              # causal persistence stub for pre-A2 fixtures
    env/
      battery.py           # pure battery physics
      context.py           # structured agent context builder
      balance.py           # merchant power balance, import/export, cost
      env.py               # stateful 15-minute simulator, 17-level actions
    agents/
      base.py              # Planner protocol: plan(context, execution_steps) -> list[int]
      llm.py               # DeepSeek client, retries, tools, telemetry
      prompts.py           # system/user prompts, versioned
      schemas.py           # pydantic schemas for context and schedule
      tools.py             # get_state, get_forecast, simulate_schedule, submit_schedule
      simulator.py         # ContextSimulator adapter for the evaluation runner
      stub.py              # StubLLMClient / StubSimulator for CI
    strategies/
      common.py            # shared action/SoC helpers
      idle.py
      rule_based.py
      price_threshold.py
      mpc.py               # 4-hour receding LP using the PV forecast
      oracle_lp.py         # perfect-foresight LP upper bound
      rl_policy.py         # optional PPO benchmark (not implemented)
    eval/
      metrics.py
      runner.py            # executes per-step or block planners
      report.py            # tables, plots
  tests/
    test_opcom.py, test_config.py, test_data_contract.py, test_pv_model.py,
    test_credentials.py, test_battery.py, test_balance.py, test_env.py,
    test_context.py, test_schemas.py, test_metrics.py, test_strategies.py,
    test_mpc.py, test_runner.py, test_report.py, test_llm_agent.py,
    test_llm_integration.py
  artifacts/               # gitignored raw; processed data trackable
    data/raw/opcom/        # 311 days scraped, manifest
    data/raw/nwp/          # cached Single Runs + aerosol
    data/processed/        # aligned dataset, model metadata, reports
    models/pv/             # trained PV model, metrics, snapshots
    runs/                  # LLM transcripts (pending) and usage
    reports/
```

Add `RL/artifacts/data/raw/` to `.gitignore` (done). Processed data is trackable.

Dependencies: `numpy`, `pandas`, `scikit-learn`, `scipy`, `matplotlib`, `pydantic`, `pyyaml`,
`openai` (OpenAI-compatible client for DeepSeek), `python-dotenv`, and
`pytest`/`ruff` for development. LightGBM/XGBoost remain optional future model backends.

### Integration: early farm-config UI

The existing FastAPI + React template is extended first, before the PV model:

```
backend/app/models/farm.py          # SQLModel FarmConfig (location, PV, battery, s)
backend/app/schemas/farm.py         # request/response + validation
backend/app/api/routes/farms.py     # CRUD, activate, export
backend/app/services/farm_config.py # YAML export + schema mirror/checksum
frontend/src/components/FarmMap.tsx # Leaflet + OpenStreetMap, click to set lat/lon
frontend/src/components/FarmForm.tsx
frontend/src/pages/FarmConfig.tsx
frontend/src/types/farm.ts
RL/configs/farm.yaml                # exported active config consumed by the RL pipeline
```

- Map: Leaflet + `react-leaflet` with OpenStreetMap tiles and attribution; no API key. A
  manual lat/lon entry is the fallback if tiles are unavailable.
- Backend dependency: `pyyaml`; frontend dependencies: `leaflet`, `react-leaflet`.
- The canonical schema lives in `RL/src/battery_rl/config.py`; the backend schema mirrors it
  and a contract test keeps field names and units aligned.
- The UI is required before Phase 1B: `train_pv.py` and `build_dataset.py` refuse to run
  without an active exported config (a `--config` path is allowed for CI/reproducibility, but
  it must point to a UI-exported file).

---

## 3. Simulator specification

### 3.1 Time and data

- Resolution 15 min, episode = 96 steps. All series are real: PZU prices, ENTSO-E national
  load, PV from Open-Meteo archive, metered data, or a PVGIS proxy.
- Store UTC; expose Europe/Bucharest. DST days have 92/100 quarter-hours. The simulator steps
  the physical UTC timeline; day boundaries are local.
- Episodes start at the delivery-day boundary. Initial SoC is fixed at 50% for evaluation and
  at 30–70% for robustness tests.
- The LLM is invoked at steps 0, 16, 32, 48, 64, 80 (00:00, 04:00, 08:00, 12:00, 16:00,
  20:00).

### 3.2 Battery model

`C = 10 MWh`, `SoC ∈ [0.1, 0.9]`, `P_max = 2 MW`, `η_c = η_d = 0.95`, `dt = 0.25 h`.

Power sign convention: `P > 0` discharges to the bus, `P < 0` charges from the bus.

```
charge:     E_next = E + |P| · dt · η_c
discharge:  E_next = E − P · dt / η_d
```

Feasible power (clip before applying; record the clipped amount):

```
P_charge_max    = (SoC_max − SoC) · C / (η_c · dt)
P_discharge_max = (SoC − SoC_min) · C · η_d / dt
```

Both are capped at `P_max`. The environment never produces an invalid SoC. Requested vs
executed power is reported in `info` and used in the violation metric and penalty term.
Asset scale `s` comes from the active farm config exported by the Phase 1A UI and multiplies
`C` and `P_max` consistently; the PV series is scaled by the same factor.

### 3.3 Power balance and economics (merchant site)

The site is a merchant PV + battery asset with **zero local demand**. National load is market
context only and does not enter the power balance.

Order per step:

1. Read `pv[t]`, `price[t]` (buy = sell = PZU).
2. Execute the clipped battery action.
3. `P_net = P_charge − pv − P_discharge` (MW). Positive means the site imports (battery
   charging exceeds PV and discharge); negative means it exports.
4. Import/export, no export limit:

   ```
   import = max(P_net, 0)
   export = max(−P_net, 0)
   ```

   Keep `export_limit` as an optional config parameter (default `None`) for future scenarios.
5. No curtailment while the export limit is disabled: `curtailed = 0`. If a limit is added,
   `curtailed = max(−P_net − export_limit, 0) · dt`, derived from the balance.
6. Cash flow (RON):

   ```
   cost_t = price[t] · import · dt − price[t] · export · dt
   ```

   Positive = money spent; negative = money earned. Import is grid charging, not load
   supply. Export is PV surplus plus battery discharge.

Energy conservation per step (power form):

```
pv + import + P_discharge = P_charge + export + curtailment_power
```

Site demand is zero (merchant), so `demand` does not appear. This is the primary invariant
test.

### 3.4 Agent context (no normalized Gym vector)

The LLM consumes raw values, not a `Box` observation. The context is a versioned JSON object
produced by `env/context.py`:

```json
{
  "delivery_day": "2026-11-05",
  "farm": {
    "name": "seed",
    "lat": 44.4, "lon": 26.1,
    "kwp": 6000.0, "asset_scale": 1.0
  },
  "time_utc": "2026-11-05T12:00:00Z",
  "step_index": 48,
  "steps_remaining": 48,
  "battery": {
    "capacity_mwh": 10.0, "p_max_mw": 2.0,
    "soc": 0.42, "soc_min": 0.10, "soc_max": 0.90,
    "eta_c": 0.95, "eta_d": 0.95
  },
  "market": {
    "currency": "RON",
    "prices_ron_mwh": [ ... 96 values for the delivery day ... ]
  },
  "pv": {
    "now_mw": 3.1,
    "forecast_mw": [ ... values from step_index to end of day ... ],
    "realized_so_far_mw": [ ... ]
  },
  "load": {
    "now_mw": 5788.0,
    "forecast_mw": [ ... values for the rest of the day ... ]
  },
  "limits": {"export_limit_mw": null, "import_limit_mw": null},
  "objective": {
    "terminal_soc_price_ron_mwh": 735.0,
    "degradation_cost_ron_per_mwh": 50.0,
    "note": "maximize net cash flow minus degradation and violations"
  },
  "previous_plan": [ ... ]
}
```

`load` is national market context. The site is a merchant asset with zero local demand, so
the agent must not treat `load` as a site load to serve.

The exact schema lives in `agents/schemas.py` and is versioned in the prompt. The agent sees
the whole remaining day, so it can reserve energy for an evening price peak even though it
only schedules the next 4 hours.

### 3.5 Actions and schedule

Signed battery power, 17 levels as fractions of `P_max`:

```
{-1.0, -0.875, …, 0.0, …, +0.875, +1.0} × P_max
positive = discharge / sell; negative = charge / buy; 0 = hold
```

At the IDEA scale (`P_max = 2 MW`) the steps are 0.25 MW; under asset scale `s` the levels and
steps scale with `P_max`.

The LLM returns a schedule of 16 entries (next 4 hours), each one of those levels. SELL, BUY
and HOLD are interpretations of the sign, not separate actions. The site has no local load:
PV charges the battery or is exported, and the battery discharge is exported. The agent
controls the grid exchange through the charge/discharge magnitude.

Execution rules:

- Schedule entries apply one per 15-minute step.
- When the battery is at a SoC limit, the environment clips and records a violation.
- Repeating an action is how the agent continues charging or selling; there is no persistent
  mode.

### 3.6 Episode and receding-horizon loop

- `reset(day)`: set the delivery day, SoC 50%, clear the plan and metrics.
- Every 16 steps (4 h), the runner builds the context and calls the planner.
  - LLM/MPC: plan over the rest of the day, execute the first 16 actions.
  - Idle/rule-based/price-threshold: evaluated both per-step and in 4-hour block mode for
    fairness.
- `step(action)` applies one 15-minute action and returns raw state, cost, and `info`.
- `truncated=True` at step 96. `terminated=False` (limits clip, never fail).
- `info`: PV, national load context, price, SoC, executed powers, import/export, cost,
  degradation, curtailed, violations, token/tool metrics for the LLM.

---

## 4. Objective and scoring

The economic objective is net cash flow minus degradation and violations, plus terminal
energy value:

```
score = −Σ cost_t
        − c_deg · Σ (charge_energy_t + discharge_energy_t)
        − λ_viol · Σ |P_requested − P_executed| · dt
        + price_ref · SoC_end · C · η_d
```

`c_deg` ≈ 25–100 RON/MWh throughput; `λ_viol` small (e.g. 5 RON/MWh clipped);
`price_ref` = mean buy price over the episode or a configured reference. This same formula is
used to score every strategy and is included in the LLM prompt as the objective. The LLM is
not trained on it; it is prompted to maximize it and can call `simulate_schedule` to see the
cost of a candidate plan.

Because the site is a merchant asset, `cost_t` contains only export revenue and the cost of
grid charging. There is no retail load supply in the objective.

Rules:

- Do not add separate bonuses for "solar used", "revenue" or "reduced import"; all are already
  in `cost_t`.
- Do not double count curtailment: with no export limit it is zero.
- Keep penalties an order of magnitude below the economic term.
- A PPO benchmark, if built, uses this as its reward with a single normalization path.

---

## 5. Data

Training/evaluation uses real data only. Synthetic series remain only as deterministic unit
test fixtures.

### 5.1 OPCOM PZU prices (implemented)
- Endpoint: `https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv/DD/MM/YYYY/ro?resolution=15`.
- Code: `src/battery_rl/data/opcom.py`; CLI: `scripts/download_opcom.py`.
- Verified 2026-01-01 → 2026-11-07: 311 days, 29,856 interval rows, 0 failures. DST days have
  92 (29 Mar) and 100 (25 Oct) intervals; all others 96. Negative prices preserved.
- Raw files: `artifacts/data/raw/opcom/YYYY/MM/DD/`, manifest with URL, SHA-256 and interval
  count. Processed: `artifacts/data/processed/opcom_pzu_2026.csv`.
- Buy and sell both use this series. The price is known D-1; no price model is trained.
- Do not put traded volume in the agent context.

### 5.2 ENTSO-E national load (market context)
- File: `artifacts/data/processed/ENTSO_15MIN.csv`, area BZN|RO, 15-min, 2026-01-01 →
  2026-12-31, columns `Actual Total Load (MW)` and `Day-ahead Total Load Forecast (MW)`.
  National load: min 2,592, mean 5,809, max 9,296 MW; annual demand ~50.9 TWh.
- Decision: the site is a merchant PV + battery asset with **zero local demand**. National
  load is market context for the agent; it is **not** the site demand and does not enter the
  power balance. The asset scale `s` scales PV and battery, not national load.
- Deviation from `IDEA.md`: the local consumer component is removed. The national load
  remains as market context. Record this in the report.
- Timezone: MTU is CET/CEST, not Europe/Bucharest. Convert to UTC before joining with OPCOM;
  day boundaries differ by one hour, so join on UTC and trim to the overlap.
- Gaps: actual load missing 1 interval on 2026-10-02, 32 intervals on 2026-11-07, and all
  future days; forecast missing 53 future days. Use through 2026-11-06 for complete actuals.
- Load forecast (context): the day-ahead national forecast, same alignment, passed to the
  agent as market context, not as the site demand.

### 5.3 PV production (config-driven)
- The Phase 1A UI supplies location, kWp, inverter AC, tilt, azimuth, tracking and the asset
  scale `s`; it exports `configs/farm.yaml`. That file is the training and evaluation config.
- If metered 15-min generation exists, use it.
- Otherwise Open-Meteo archived irradiance at the configured coordinates with a PV model:
  fixed-plane GTI for fixed/single-axis and a direct+diffuse plane-of-array model for
  dual-axis tracking. Hourly output is interpolated to 15 min and documented. Snapshot the
  fetched series into the dataset so runs are reproducible offline.
- PVGIS (SARAH3/ERA5) only serves 2005–2023, so it is an optional proxy/fallback for years it
  covers, not the default for 2026. Record the source and any proxy year in the data card.
- Scale the series by `s` along with the battery parameters.

### 5.4 PV forecast model (ML)
- Target: PV power (MW) for each 15-min interval of the delivery day (96-step curve), not only
  total daily energy. The agent needs the timing of production. If only a daily total is
  available, derive the intraday shape from a clear-sky model and label it as an
  approximation; the curve remains the preferred target.
- NWP source: Open-Meteo Single Runs (ECMWF IFS HRES, 00/06/12/18 UTC). Each 4-hour issue
  uses the latest run published after a 6-hour lag; missing runs fall back to the previous
  available run. The stitched Historical Forecast API is not used because it does not preserve
  run initialisation times.
- Features: time encodings; NWP at the target (GHI, DNI, DHI, cloud cover, temperature,
  humidity, wind, precipitation/snow, aerosol); clear-sky irradiance/index; realized PV lags
  at the issue; lead steps. Site geometry is constant for a single farm and is omitted; add
  lat/lon, tilt, azimuth, tracking, kWp and inverter AC when pooling farms.
- Model: `HistGradientBoostingRegressor` is implemented (scikit-learn). LightGBM/XGBoost
  remain config options but are not implemented. The baseline is causal day-over-day
  persistence; a physical irradiance-to-power model supplies the actual-PV proxy.
- Training: chronological split; MAE/RMSE overall and by lead time, month and season. The
  economic impact of forecast error on dispatch is reported by the evaluation lane, not used
  as the PV training loss.
- Leakage: NWP features come from the run available at the issue; realized PV lags stop at the
  issue. One known approximation: aerosol is read from the historical archive at the target
  time, not from an issue-time forecast; switch to the last issue-time value for strict
  causality.
- Re-run the forecast at each 4-hour boundary using the latest available NWP run and realized
  PV. Store the per-row `pv_forecast_mw` (latest issue) and the rest-of-day
  `pv_forecast_snapshots.csv` used for planning and lead-time metrics.

### 5.5 Alignment, splits, validation
- Store UTC, expose Europe/Bucharest; keep 92/100-interval DST days.
- Never forward-fill a gap silently: mark gaps, exclude affected days, report coverage.
- Chronological blocked split with a frozen test set, spanning seasons and price regimes.
- Data card: source URLs, download dates, licenses, transformations, asset scale, gap list and
  split dates.
- Checks: interval regularity per day; identical timestamps across series; price range sanity;
  non-negative load/PV; no NaNs from joins; provenance for every processed row.

---

## 6. Baselines and reference strategies

Common interface:

```python
class Planner(Protocol):
    # Plans over the rest of the day, returns the execution window (16 actions).
    def plan(self, context: dict, execution_steps: int = 16) -> list[int]: ...

class StepStrategy(Protocol):
    def act(self, info: dict) -> int: ...
```

The runner supports per-step strategies and block planners; per-step strategies are also run
in 4-hour block mode for a fair comparison with the LLM.

| Strategy | Behavior |
|---|---|
| `Idle` | hold all the time (IDEA "fără optimizare") |
| `RuleBased` | charge on PV surplus, discharge on deficit, deadband to avoid chattering |
| `PriceThreshold` | charge below a daily price quantile, discharge above |
| `MPC` | every 4 h, solve an LP over the rest of the day using the PV forecast and known prices; execute the first 4 h. The primary strong baseline. |
| `OracleLP` | perfect-foresight LP over the whole day; upper bound only |
| `LLMAgent` | section 7 |
| `PPO` (optional) | discrete-action benchmark, Phase 10 only |

The MPC and OracleLP use the same battery model and objective, so the comparison is exact.

---

## 7. LLM dispatch agent

### 7.1 Invocation
- Every 4 hours, six times per day (00:00, 04:00, 08:00, 12:00, 16:00, 20:00).
- The API key comes from `RL/.env` via `battery_rl.credentials.agent_api_key(agent_config)`.
  The base URL comes from `DEEPSEEK_BASE_URL` (default `https://api.deepseek.com`). The key is
  never written to transcripts, artifacts, prompts or logs.
- Planning horizon: rest of the delivery day. Execution horizon: the next 16 intervals.
- Re-planning uses updated PV forecasts and realized PV; battery state is exact.

### 7.2 Context
- Built by `env/context.py`; schema in `agents/schemas.py`.
- Includes the full delivery-day price list (96 values), the PV forecast for the remaining day,
  the national load forecast as market context, battery state and limits, realized PV,
  previous plan, and the objective parameters. National load is not the site demand; the site
  is a merchant asset with zero local demand.
- Prices are passed as known data; the agent is told explicitly not to forecast prices.
- Use a compact CSV-like table in the user message (time, price, PV forecast, load forecast)
  plus a short state block. Keep the static instructions and tool definitions in the cached
  prefix.

### 7.3 Output
- A schedule of 16 entries, each a signed power level from the 17-level set.
- Structured JSON, validated against `agents/schemas.py`; or a strict `submit_schedule` tool.
- Include a one-paragraph rationale for the log (not used for scoring).

### 7.4 Tools
- `get_state()` — raw SoC, limits, current PV/load, time remaining.
- `get_forecast()` — PV forecast and price list for the rest of the day.
- `simulate_schedule(schedule)` — runs the candidate plan through the simulator; returns cash
  flow, SoC trajectory, feasibility and violations. The agent should call it before
  submitting. The evaluation runner wires this to `agents/simulator.py::ContextSimulator`.
- `submit_schedule(schedule)` — final action; validated and executed.
- Max 3 simulator calls per decision to control latency/cost.

### 7.5 Prompt
- Role: battery dispatch operator for a PV + storage + grid site.
- Objective: maximize net cash flow minus degradation and violations, with terminal SoC value.
- Constraints: configured `P_max`, capacity and SoC limits (IDEA defaults 2 MW, 10 MWh,
  10–90%, 95% efficiencies), no export limit.
- Priority rules: the site has no local load. PV charges the battery first; surplus is
  exported; the battery discharges to the grid; grid charging is profitable only above the
  efficiency threshold.
- Planning instruction: consider the rest of the delivery day, but return the schedule for the
  next 4 hours (16 intervals).
- Output schema and tool instructions.
- Prompt version string stored in every result.

### 7.6 Validation and fallback
- Validate schema, length 16, action levels, SoC feasibility, no simultaneous import/export
  beyond the physical balance.
- On invalid output: one retry with the validation error; then fall back to the rule-based
  plan (or HOLD) and log `invalid_output`.
- Executed schedules are always feasible; report the raw invalid rate separately.

### 7.7 Model, cost, latency
- Default model: `deepseek-chat` (DeepSeek, OpenAI-compatible endpoint). Provider, model ID
  and base URL are config, so another compatible model can be swapped without code changes.
- Six calls/day; measure actual input usage (the prompt is roughly 8–12k tokens per call
  with the full-day forecast table) and allow up to 4k output tokens per call so reasoning
  does not crowd out the schedule. Measure the provider's current pricing and log
  tokens/cost per decision; do not estimate from memory.
- Measure latency and rate limits per provider; evaluation can run days concurrently.
- Use the provider's deterministic setting (e.g. temperature 0) and repeat runs for variance.

### 7.8 Reproducibility
- Store model ID, prompt version, full context, raw output, tool calls, token usage and
  latency for every decision. Token/latency telemetry is implemented; raw context/output
  transcript storage is still pending in the evaluation runner.
- Run each held-out day three times; report mean and spread for the primary metrics.
- No claim is made from a cherry-picked run.

### 7.9 Open-loop vs receding
- Receding horizon at 4 h is the default and the headline result.
- Open-loop (one day-ahead plan) is kept as a comparison to quantify the value of re-planning.
- The agent is also evaluated with a naive PV forecast and with the oracle PV forecast to
  separate forecast quality from dispatch quality.

### 7.10 Farms and configuration
- The LLM is configuration-driven: farm parameters and asset scale are in the context, so the
  same agent can serve different configurations; every configuration must be evaluated.
- The battery/PV ratio and asset scale matter; include them in the context. National load is
  market context, not a site load ratio.
- Fleet evaluation: zero-shot on held-out farms vs the MPC baseline; no retraining required.

---

## 8. Evaluation

`eval/runner.py` runs any `Planner` or `StepStrategy` for N days on a split/regime, collecting
per-step records and per-day metrics. `eval/report.py` aggregates tables and plots.

Metric definitions:

| Metric | Formula |
|---|---|
| Import cost | `Σ price · import · dt` |
| Export revenue | `Σ price · export · dt` |
| Net energy cost | import cost − export revenue (primary KPI) |
| Renewable utilization | `1 − curtailed / available_pv` (constant 1 here) |
| Self-consumption ratio | `pv_to_battery / available_pv` (merchant site: no local load) |
| Wasted energy | curtailed PV (0 here) |
| Battery throughput | `Σ (charge_energy + discharge_energy)` |
| Equivalent full cycles | `throughput / (2C)` |
| Degradation estimate | `c_deg · throughput` |
| Constraint violations | clipped MW·h and count of clipped steps |
| Grid import / export | MWh each |
| Mean SoC / SoC range | per day |
| LLM feasibility rate | executed plans that passed validation / decisions |
| Raw invalid rate | invalid outputs before fallback / decisions |
| Tool calls per decision | from telemetry (raw transcripts pending) |
| Tokens per decision | input + output from API usage |
| Latency per decision | seconds |
| Cost per day | tokens × provider price; `llm_cost_ron` remains 0 until DeepSeek pricing is configured |

Protocol:

1. Fixed days and seeds; same episodes for every strategy.
2. Compare idle, rule-based, price-threshold, MPC, oracle LP and the LLM agent.
3. Run the LLM three times per day; report mean ± std and the run-level spread.
4. Break results down by data-derived regime: high/low/volatile price days, cloudy/sunny
   weeks, weekends/holidays.
5. Report open-loop vs 4-hour receding horizon, and oracle vs naive PV forecast.
6. Report tokens, latency and cost per decision/day; the agent must be operationally credible,
   not only economically good.
7. Business check: net cost after degradation; do not report only throughput gains.

Plots: net cost by strategy, SoC and power flows over a sample day, price vs schedule, LLM vs
MPC gap, token/latency distributions, decision and error analysis.

---

## 9. Workflow phases (build order)

### Phase 0 — Setup and locked decisions
- [ ] Resolve the remaining open items in section 1: metered PV, demo scope and evaluation
      cut-off. (LLM model and key are resolved.)
- [ ] The seed farm and asset scale are captured by the Phase 1A UI, not hard-coded here.
- [ ] Confirm OPCOM terms/attribution (scraper already implemented and verified).
- [x] Create `RL/pyproject.toml`, package skeleton, `configs/*.yaml`, `config.py`, `seeding.py`.
- [x] Add `RL/artifacts/data/raw/` to `.gitignore`; also ignore `*.egg-info/`.
- [x] `pip install -e ".[dev]"` works in `RL/.venv`; `import battery_rl` smoke test passes.
- [x] Verification: 22 tests pass, `ruff check` clean, all configs load and validate.
- **Exit:** met — skeleton runs, configs load and validate, no hard-coded experiment values.

### Phase 1A — Farm configuration UI (required before ML training)
Goal: the map + form is the single source of the active farm config, including asset scale `s`.

**Backend**
- [x] `models/farm.py`: SQLModel `FarmConfig` (name, lat, lon, PV params, battery params,
      asset scale `s`, grid limits, active flag).
- [x] `schemas/farm.py`: Pydantic validation (lat/lon ranges, kWp > 0, SoC min < max,
      efficiencies in (0, 1], `s` > 0, power limits).
- [x] `api/routes/farms.py`: create/list/get/update/activate/export.
- [x] Register the model in `backend/app/models/__init__.py` and the router in
      `backend/app/api/router.py` (follow the template checklist).
- [x] `services/farm_config.py`: export the active config to `RL/configs/farm.yaml` with a
      checksum; mirror the canonical RL schema.
- [x] Contract test: backend schema ↔ `battery_rl.config`; the exported YAML loads in the RL
      package with identical values.

**Frontend**
- [x] `components/FarmMap.tsx`: Leaflet + OpenStreetMap tiles; click sets lat/lon; manual
      lat/lon entry as fallback; attribution visible.
- [x] `components/FarmForm.tsx`: PV (kWp, inverter AC, tilt, azimuth, tracking), battery
      (MWh, MW, SoC limits, efficiencies), asset scale `s`, grid limits. Show the scaled
      PV/battery values and warn if battery power is < 1% of national peak load.
- [x] `pages/FarmConfig.tsx`: save, activate, export; summary of the active configuration.
- [x] `types/farm.ts` and API client wiring; register the page in `App.tsx`.

**Verification (2026-11-07):** backend 10 tests pass (health + farm CRUD/export/contract);
frontend `npm run build` and `npm run lint` pass; exported YAML loads through
`battery_rl.config.load_farm_config` with a matching SHA-256 checksum.

**Exit:** met — selecting a location on the map, filling the parameters and `s`, saving and
activating produces a `farm.yaml` that `battery_rl.config.load_farm_config` accepts; the UI
shows the scaled system and the battery/load warning.

### Phase 1B — Real data ingestion and PV model (consumes Phase 1A config)
- [x] OPCOM PZU scraper and processed series (311 days, 29,856 rows, 0 failures).
- [x] ENTSO-E CSV received.
- [x] `data/entsoe.py`: parse, convert CET/CEST → UTC, align; no load scaling.
- [x] `data/pv.py`: metered / Open-Meteo archive sources; PVGIS proxy for 2005–2023; snapshot.
- [x] `models/pv.py` + `scripts/train_pv.py`: train the 96-step PV forecast from NWP/time
      features; evaluate MAE/RMSE by horizon; no future-weather leakage. Both read
      `configs/farm.yaml` and fail with a clear error if it is missing or checksum-invalid.
- [x] `data/forecasts.py`: align price (pass-through, no model), the ENTSO-E load forecast and
      the ML PV forecast into per-step arrays for each delivery day.
- [x] `scripts/build_dataset.py`: align prices, load, PV, forecasts; apply `s`; validate; split;
      write data card and overview plots.
- [x] `tests/test_opcom.py`, `tests/test_data_contract.py`, `tests/test_pv_model.py`.
- **Exit:** aligned, validated dataset + PV model with per-horizon error, data card, and
  every processed row traceable to a raw source; the active config checksum is recorded.

### Phase 2 — Environment core
- [x] `battery.py`: feasible power, SoC update, efficiency, asset scale.
- [x] `balance.py`: bus balance, import/export, optional limit, curtailment, cost.
- [x] `env.py`: reset/step, 17-level action mapping, info, episode loop.
- [x] Tests: SoC bounds, round-trip efficiency, energy conservation identity.
- **Exit:** random feasible schedule runs 96 steps with valid SoC and conserved energy.

### Phase 3 — Agent context and simulator tool
- [x] `context.py`: build the versioned context from env state and data.
- [x] `agents/schemas.py`: pydantic models for context, schedule, tool results.
- [x] `simulate_schedule` tool: deterministic simulation of a 16-step candidate plan.
- [x] Tests: schema round-trip, context covers rest of day, tool equals env step cost.
- **Exit:** a schedule can be planned, simulated and validated without the LLM.

### Phase 4 — Objective and scoring
- [x] `eval/metrics.py`: cost, revenue, utilization, self-consumption, throughput, cycles,
      degradation, violations.
- [x] Terminal SoC value and degradation term used consistently by MPC, oracle and LLM prompt.
- [x] Test: with penalties zero, score equals negative cash flow.
- **Exit:** objective accounting verified on a hand-computed mini day.

### Phase 5 — Baselines and MPC/oracle
- [x] `idle.py`, `rule_based.py`, optional `price_threshold.py`.
- [x] `mpc.py`: 4-hour receding LP using the PV forecast and known prices. Requires SciPy or
      PuLP.
- [x] `oracle_lp.py`: perfect-foresight LP upper bound.
- [ ] Run each through the simulator for 10 days.
- **Exit:** idle has zero throughput; rule-based behaves as expected; MPC beats rule-based;
      oracle is the highest.

### Phase 6 — Evaluation harness
- [x] `eval/runner.py` supports per-step strategies and block planners.
- [x] `scripts/evaluate.py` produces a comparison table and plots.
- [x] `eval/report.py` aggregates per regime and repeats.
- **Exit:** repeatable table for idle/rule/MPC/oracle on the validation split.

### Phase 7 — LLM agent implementation
- [x] `agents/llm.py`: DeepSeek client, retries, structured output, token/latency logging.
- [x] `agents/prompts.py`: versioned system and user prompt; compact context table.
- [x] `agents/tools.py`: get_state, get_forecast, simulate_schedule, submit_schedule.
- [x] Validation and fallback (hold; rule-based is B's strategy and can be injected).
- [ ] Raw output/transcript storage (belongs to the evaluation runner).
- [x] `tests/test_llm_agent.py`: schema validation, fallback path, tool loop, six-decision
      stub smoke.
- [x] Real-env integration via `eval.runner`, `agents/simulator.py` and
      `LLMAgent.telemetry`.
- [ ] Raw transcript storage and a real-API smoke test.
- **Exit:** the LLM produces feasible 4-hour schedules and the logs capture tokens, latency
      and tool calls. Verified through the runner with the stub client and
      `ContextSimulator`; the real API smoke test is pending.

### Phase 8 — Receding-horizon evaluation and prompt tuning
- [ ] Run the LLM on the validation split with 4-hour receding horizon, 3 repeats/day.
- [ ] Compare with rule-based, MPC and oracle; inspect decisions and failure modes.
- [ ] Tune the prompt (not the data or the test set) and the simulator-tool instructions.
- [ ] Confirm the LLM beats idle and rule-based; report the gap to MPC/oracle.
- **Exit:** stable evaluation, feasible schedules, documented prompt version, cost/latency
      within budget.

### Phase 9 — Final evaluation and report
- [ ] Freeze model ID, prompt version and evaluation protocol.
- [ ] Run on held-out test days and all regimes; three repeats.
- [ ] Produce the IDEA metrics table plus LLM-specific metrics and open-loop vs receding.
- [ ] Robustness across PV forecast sources (oracle vs naive vs ML).
- [ ] `artifacts/reports/report.md` with plots and a conclusion.
- **Exit:** results reproducible from documented commands; claims match measured numbers.

### Phase 10 — Extensions (only if time remains)
- [ ] PPO/DQN benchmark on the same environment and test split.
- [ ] Continuous action space (quantized 17 levels vs continuous).
- [ ] Hybrid fallback: LLM selects store/sell windows, LP computes amounts.
- [ ] Additional farm configurations and fleet zero-shot evaluation.
- [ ] MPC with scenario-based uncertainty instead of a single forecast.

### Phase 11 — Results dashboard and demo (optional)
- [ ] Backend `POST /api/simulate`: active/selected farm config + date + strategy → trajectory +
      metrics. Reuse the Phase 1A configuration store; do not duplicate the form.
- [ ] Run the LLM agent for any configuration when `DEEPSEEK_API_KEY` is configured;
      otherwise baselines only, with a clear message.
- [ ] PV-source lookup (Open-Meteo/PVGIS) with timeout, cache and error state.
- [ ] Results page: SoC/power/price charts, metrics comparison, LLM transcript summary.
- [ ] Link from the farm-config page to the results page; the date range and strategy are
      selected there.
- [ ] No retraining or training jobs in the request path. Store prompt version and model ID
      with every run.
- **Exit:** the UI reproduces the Phase 9 numbers for a selected configuration; with an API key
  it runs the LLM agent for any configuration with data available, otherwise baselines only.

---

## 10. Definition of done

- Farm configuration: map-based UI selects the seed farm and asset scale `s`; the active
  config is exported to `configs/farm.yaml` and consumed by the PV model, simulator and
  evaluation, with a checksum recorded in results.

- Data pipeline: validated real dataset with provenance, data card and frozen test split.
- PV model: 96-step forecast evaluated by horizon and season, no leakage.
- Simulator: energy conservation, SoC bounds, 17-level actions, tests pass.
- Baselines: idle, rule-based, MPC and perfect-foresight oracle all run on the same days.
- LLM agent: 4-hour receding horizon, feasible schedules, structured outputs, fallback,
      token/latency telemetry; raw transcripts are still pending in the runner.
- Results on held-out days: the LLM beats idle and the rule-based baseline (target ≥ 5% net
  cost vs rule-based) and reports its gap to MPC and the oracle. If it loses, document why.
- All IDEA metrics plus LLM feasibility, invalid rate, tokens, latency and cost are reported.
- Reproducibility: model ID, prompt version, evaluation protocol and raw outputs are stored
  (transcripts pending); three repeats per day are reported.
- `RL/README.md` documents installation, data build, PV model, evaluation and results.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM emits invalid or infeasible schedules | Strict schema, simulator tool, validation, one retry, rule-based fallback; report raw invalid rate |
| LLM non-determinism | Three repeats per day, report mean and spread; freeze model and prompt version |
| LLM loses to MPC/rule-based | Report honestly; use the hybrid fallback (LLM selects windows, LP computes amounts) |
| Cost or latency too high | Six calls/day, small model, prompt caching, compact context, concurrency limits |
| Prompt brittleness / context overflow | Versioned prompts, compact tables, token counts, regression tests on sample days |
| API outage or rate limits | Retries, fallback to baselines, offline evaluation mode |
| UI config and RL config drift | Single canonical schema, contract test, checksum on export |
| PV source or map tiles unavailable | Cached Open-Meteo/PVGIS series, manual lat/lon fallback, OSM attribution; no API key |
| Asset scale misuse | Show scaled PV/battery values in the UI; warn when battery power is < 1% of national peak load (market materiality, not balance demand) |
| PV forecast leakage | Archived NWP run issue times; never use future actual weather; snapshot forecasts. Known exception: aerosol currently uses the target-time archive; switch to issue-time for strict causality |
| National load misused as site demand | Merchant decision: site demand = 0; national load is context only; balance and context tests enforce it |
| No export limit makes utilization/wasted metrics constant | Report for IDEA compliance; base conclusions on net cost, revenue, self-consumption and battery metrics |
| Data gaps, DST, timezone mismatch | Explicit gap marking, UTC joins, per-day interval checks, coverage report |
| Reward/objective double counting | Single cash-flow formula; no separate solar/revenue bonuses |
| Discrete actions cause chattering | 17 levels; degradation cost; optional action-change penalty |
| Running out of time | Phases 0–9 are the minimum; Phase 10–11 optional |

---

## 12. Sequencing and ownership

- **Config UI track (Phase 1A):** map, farm form, asset scale `s`, YAML export. Must land
  before the PV model; it defines the seed configuration.
- **Data + PV model track (Phase 1B):** ENTSO parse, Open-Meteo/PVGIS PV, dataset build, PV
  model. Consumes the exported config; blocked until Phase 1A produces a valid `farm.yaml`.
- **Simulator track (Phases 2–4):** battery, balance, context, objective. Can proceed in
  parallel with the data track using fixture data once the config schema is stable.
- **Evaluation track (Phases 5–6):** baselines, MPC/oracle, metrics and runner. Needed before
  the LLM can be judged.
- **Agent track (Phases 7–8):** phase 7 (LLM client, prompts, tools, validation) is
  implemented and integrated with the runner; phase 8 (receding-horizon evaluation and prompt
  tuning) is next.
- **Report/demo (Phases 9, 11):** final evaluation and optional results dashboard.

Current state: phases 0–7 are implemented. The six-decision stub smoke passes and a one-day
baselines evaluation runs end-to-end. Next: phase 8 (validation evaluation and prompt tuning)
→ phase 9 (test split and report). Phase 10–11 are optional. Phase 8 must not begin until MPC
and rule-based are numerically stable on the validation split.

Parallel execution with two developers is specified separately in `TEAM_PLAN.md`: frozen
interfaces, lane ownership, merge checkpoints and the async status/handoff protocol.

---

## 13. Open decisions

1. Metered PV available? If not, use Open-Meteo archive; PVGIS is an optional 2005–2023 proxy.
2. Demo scope and UI expectations.
3. Final evaluation window cut-off (recommend 2026-11-06 for complete actual load).

Resolved: LLM provider/model is `deepseek-chat`; `DEEPSEEK_API_KEY` and optional
`DEEPSEEK_BASE_URL` live in `RL/.env` (gitignored).

The seed farm location, PV/battery parameters and asset scale `s` are selected in the Phase 1A
UI; the demo needs at least one saved/active configuration.
