# The AI pipeline, from raw data to the LLM's decision

This repository contains two AI parts with very different jobs:

1. A **machine-learning model** that forecasts PV production. It is trained offline on historical weather and PV data.
2. A **large language model** (DeepSeek) that decides every four hours how to charge or discharge the battery. It is not trained. It is prompted at runtime with a JSON snapshot of the plant and a forecast table.

Everything else is simulation, validation and accounting. This document follows one day of data through both parts.

```
OPCOM prices ─┐
ENTSO-E load ─┼─> aligned 15-min CSV ─> trained PV model ─┐
Open-Meteo  ──┘                                          │
                                                         v
                              context JSON ─> prompt ─> DeepSeek ─> schedule
                                                                       │
                                                                       v
                                          simulator ─> score (RON/day) ─> UI
```

| Stage | Input | Output | Main file |
|---|---|---|---|
| 1. Collect raw data | APIs and CSV exports | price, load, weather series | `RL/src/battery_rl/data/` |
| 2. Align | separate series | one 15-minute table | `RL/scripts/build_dataset.py` |
| 3. Train PV model | aligned table | forecast model artifact | `RL/scripts/train_pv.py` |
| 4. Simulate | actions + actuals | energy flows and cash | `RL/src/battery_rl/env/` |
| 5. Build context | simulator state | validated JSON snapshot | `RL/src/battery_rl/env/context.py` |
| 6. Prompt | context JSON | system + user messages | `RL/src/battery_rl/agents/prompts.py` |
| 7. Ask the LLM | messages + tools | schedule | `RL/src/battery_rl/agents/llm.py` |
| 8. Execute | schedule | daily metrics and UI trace | `backend/app/services/rl_simulation_runner.py` |

## Terms used in this document

| Term | Meaning |
|---|---|
| PV | Photovoltaic solar production |
| NWP | Numerical weather prediction: a weather model's forecast output |
| SoC | State of charge: stored energy as a fraction of capacity |
| P_max | The battery's maximum charge or discharge power |
| kWp | Kilowatt-peak: installed DC solar capacity under standard test conditions |
| MAE | Mean absolute error: the average size of a miss, in the target's units |
| RMSE | Root mean squared error: like MAE, but it penalizes large misses more |
| Gradient boosting | A model built from many small trees, each correcting earlier errors |
| Prompt | The text sent to an LLM before it answers |
| Tool call | A structured function request the LLM emits instead of prose |
| Training | Fitting model parameters from data |
| Inference | Running a trained model, or an LLM, on new input |
| Data leakage | Letting a model see information it would not have at prediction time |

## 1. What the system controls

The site is a merchant PV + battery + grid asset with **no local load**. PV production and battery discharge are sold to the grid. Grid energy is bought only to charge the battery.

The controller makes one decision per 15-minute interval. The action is an index into 17 signed levels, expressed as a fraction of the battery's maximum power:

| Index | Level | Meaning |
|---|---|---|
| 0 | -1.000 | charge at full power |
| 4 | -0.500 | charge at half power |
| 8 | 0.000 | hold |
| 12 | +0.500 | discharge at half power |
| 16 | +1.000 | discharge at full power |

Positive power discharges and sells. Negative power charges and buys. The full list lives in `agents/schemas.py` and must match `configs/env.yaml`.

The agent re-plans every 16 intervals, which is four hours. A normal day has 96 intervals, so there are six decisions per day: at 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00 local time. Each decision returns a block of 16 actions. DST days have 92 or 100 intervals, and the last block is shorter.

The default farm in `configs/farm.yaml` has a 10 MWh battery with 2 MW maximum power (`P_max`), 10–90% state of charge, and 95% efficiency each way. One level step is therefore 0.25 MW, and charging from empty to full at maximum power takes about five hours.

## 2. Raw data

Five sources feed the pipeline. Each one has a different cadence and a different role.

| Source | What it provides | Cadence | Role |
|---|---|---|---|
| OPCOM PZU | Day-ahead market price in RON/MWh | 15 minutes | Known input, not forecast |
| ENTSO-E | Romanian national load and day-ahead load forecast | 15 minutes | Market context only |
| Open-Meteo archive | Historical irradiance at the farm coordinates | Hourly, interpolated | Proxy for actual PV |
| Open-Meteo Single Runs | ECMWF IFS numerical weather prediction (NWP) runs | 6-hour runs | Features for the PV forecast |
| Open-Meteo air quality | Aerosol optical depth | Hourly | Features for the PV forecast |

Two time conventions coexist, and mixing them is the most common source of bugs:

- **OPCOM delivery days are local** to Europe/Bucharest. Interval 1 starts at local midnight.
- **Every join is by UTC timestamp.** The dataset stores both `timestamp_utc` and `delivery_date` so a row is unambiguous.
- **DST days keep their real length.** 2026-03-29 has 92 intervals; 2026-10-25 has 100. The validator rejects any day whose interval count does not match `expected_intervals()`.

`pv_mw` is not a meter reading in this dataset. The builder fetches archived irradiance, converts it to plane-of-array irradiance, multiplies by installed kWp and a performance ratio, then clips the result to the inverter AC rating. The data card says this plainly: it is a proxy, not a measurement. If you have metered PV, pass `--pv-source metered` and use it instead.

National load is also easy to misread. It is not the site's demand. The site has zero demand. Load is supplied as a market signal because high national demand often coincides with high prices. The environment never consumes it in the power balance.

## 3. From sources to one aligned CSV

`RL/scripts/build_dataset.py` does the merge. `RL/src/battery_rl/data/dataset.py` defines the contract.

The steps:

1. Filter OPCOM prices to the requested date range.
2. Merge ENTSO-E load on exact UTC timestamp.
3. Attach a **forecast issue time** to every interval: the latest decision boundary at or before the target. Boundaries are 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00 local.
4. Compute `pv_mw` from archived irradiance.
5. Compute `pv_forecast_mw` with the trained model. The forecast that a row carries is the one available at that row's issue time, never a later one.
6. Mark `is_complete` when every contract field is non-null.
7. Validate the whole table: correct interval counts, timestamps that match local midnight plus 15-minute steps, no negative PV or load, and no forecast issued after its target.

The result has ten columns:

| Column | Unit | Meaning |
|---|---|---|
| `timestamp_utc` | ISO 8601 UTC | Physical instant |
| `delivery_date` | local date | OPCOM delivery day |
| `interval` | 1..N | Position in the local day |
| `price_ron_mwh` | RON/MWh | Market price |
| `load_mw` | MW | National load, context only |
| `load_forecast_mw` | MW | Day-ahead national load forecast |
| `pv_mw` | MW | Actual PV proxy |
| `pv_forecast_mw` | MW | Causal PV forecast |
| `pv_forecast_issue_utc` | ISO 8601 UTC | When that forecast was issued |
| `is_complete` | bool | All fields present |

The aligned `pv_forecast_mw` column is a per-row forecast. Each interval carries the forecast issued at the latest decision boundary at or before it, so its lead is 0–4 hours. The training script also writes rest-of-day snapshots (`artifacts/models/pv/pv_forecast_snapshots.csv`). Those issue one forecast from each decision boundary across all remaining intervals, and they are what the lead-time error table uses.

The committed dataset has 29,760 rows over 310 delivery days, from 2026-01-01 to 2026-11-06. Five intervals are incomplete because ENTSO-E has gaps at the start of the year. The evaluation runner skips any day with an incomplete interval rather than inventing data.

The split is chronological:

| Split | Dates | Purpose |
|---|---|---|
| train | 2026-01-01 .. 2026-07-31 | Fit the PV model |
| validation | 2026-08-01 .. 2026-09-30 | Tune and compare |
| test | 2026-10-01 .. 2026-11-06 | Final, untouched check |

Do not shuffle a time series. A random split would put future weather in the training set and past weather in the test set, and the reported error would be fiction.

## 4. The trained part: the PV forecast model

This is the only place in the repository where a model learns from data.

The target is `pv_mw` at each 15-minute interval. The model learns a mapping from 21 features to that value.

The features fall into four groups:

| Group | Features | Why |
|---|---|---|
| Calendar | `hour_sin`, `hour_cos`, `doy_sin`, `doy_cos`, `month` | The sun's position depends on time of day and season |
| Weather from NWP | `ghi`, `dni`, `dhi`, `cloud_cover`, `temperature`, `humidity`, `wind_speed`, `precipitation`, `snow` | These are the physical drivers of PV output |
| Geometry | `clear_sky_ghi`, `clear_sky_index` | What a clear sky would produce, and how far reality is from it |
| Horizon and history | `lead_steps`, `pv_lag_1`, `pv_lag_2`, `pv_roll_4`, `aerosol` | How far ahead the forecast looks, and what the plant produced recently |

Three of these deserve a plain explanation.

**Why sine and cosine for the hour.** A clock is circular. Numerically, 23:45 and 00:00 look far apart, but they are 15 minutes apart in reality. Encoding the hour as `sin(2πh/24)` and `cos(2πh/24)` places midnight next to 23:45 on a circle. The model does not have to learn a discontinuity.

**What the clear-sky index means.** `clear_sky_ghi` is the irradiance a cloudless sky would deliver at that place and time. `clear_sky_index` is the NWP's actual irradiance divided by that value, clipped to a sensible range. A value near 1 means clear. A value near 0.3 means heavy cloud. It gives the model a scale-free way to reason about cloudiness.

**Why `lead_steps` matters.** The same weather forecast is less trustworthy 20 hours out than 2 hours out. `lead_steps` tells the model how far ahead it is predicting, so it can learn to be more conservative at long horizons. The published error curves show exactly that.

The estimator is `HistGradientBoostingRegressor` from scikit-learn. In plain terms:

- It is a collection of small decision trees.
- The trees are built in sequence. Each new tree focuses on the errors the previous trees made.
- "Histogram" means feature values are binned before splitting, which makes training fast on tabular data.
- It predicts a number, not a class, so this is regression.

Predictions are clipped to `[0, inverter AC rating]`. A PV plant cannot produce negative power, and it cannot exceed its inverter.

### Causality is the whole game

A forecast model is only useful if it only sees information that existed when the forecast was made. This code enforces that in three places:

- **NWP runs.** `latest_run()` subtracts a six-hour publication lag, then floors to the previous 00/06/12/18 UTC cycle. A decision at 08:00 local uses the model run that would have been published by then, not the final analysis.
- **PV lags.** `pv_lag_1`, `pv_lag_2` and `pv_roll_4` come from realized PV at or before the issue time. They never look forward.
- **Issue timestamps.** Every row records `pv_forecast_issue_utc`, and the validator rejects a forecast issued after its target.

If you skip this discipline, validation scores look excellent and the live system fails. That failure has a name: **data leakage**. It is the first thing to check when a time-series model looks too good.

### Training and results

`RL/scripts/train_pv.py` fits on the train split only, then reports mean absolute error (MAE), root mean squared error (RMSE) and bias overall and by lead time, month and season. It also trains a persistence baseline: copy the PV value from 24 hours earlier. Persistence is a low bar, but it is an honest one.

The committed model card reports:

| Split | MAE (MW) | RMSE (MW) | Bias (MW) | Persistence MAE (MW) |
|---|---|---|---|---|
| validation | 0.1615 | 0.3425 | +0.0188 | 0.4253 |
| test | 0.0971 | 0.2230 | +0.0358 | 0.3795 |

MAE is the average absolute miss in MW. RMSE squares the errors before averaging, so it punishes large misses more. Bias tells you whether the model systematically overshoots or undershoots.

Error grows with lead time. On validation, MAE is 0.1615 MW at 0–4 hours, 0.3425 MW at 8–12 hours, and 0.3785 MW at 12–16 hours. That is expected: the further out you look, the less the weather forecast knows. It is also why the agent re-plans every four hours instead of once a day.

The artifact is a `joblib` file containing the fitted estimator, the feature order, the model config and a checksum of the farm config. Loading refuses if the farm checksum or feature list has changed. A model trained for a 6 MWp array in one location is not valid after someone edits the farm in the UI.

## 5. The simulator: where a decision becomes money

`RL/src/battery_rl/env/battery.py`, `balance.py` and `env.py` implement the plant.

`reset()` starts the day at 50% state of charge and fixes the terminal energy price at the day's mean price. Then each step does seven things:

1. Convert the action index to a signed power: `level × P_max`.
2. Clip that request to what is physically possible given the current SoC, the SoC bounds, `P_max` and the efficiencies.
3. Update stored energy. Discharging removes `E / eta_d`; charging adds `E × eta_c`.
4. Solve the power balance: `PV + import + discharge = charge + export + curtail`. Site demand is zero.
5. Compute cash: import cost minus export revenue.
6. Charge degradation at 50 RON per MWh of throughput.
7. Charge a violation penalty at 5 RON per MWh for any requested power that could not be executed.

The day score is:

```
score = -import_cost - degradation - violation_penalty + terminal_value
```

`terminal_value` values the energy left in the battery when the delivery day ends, at the day's mean price, multiplied by discharge efficiency. Without it, the cheapest strategy would always be to drain the battery and stop.

Two details matter for reading results:

- The **environment executes actual PV and actual prices**. The **agent plans with forecast PV and known prices**. That gap is where forecast quality turns into money.
- The environment never crashes on an infeasible request. It clips, records `violation_mwh`, and lets the score reflect the mistake. That keeps a bad action comparable to a good one instead of aborting the run.

## 6. The context: the snapshot the LLM sees

`RL/src/battery_rl/env/context.py` builds a validated JSON object at every decision boundary. `agents/schemas.py` defines and checks its shape.

The context contains:

| Field | What it holds |
|---|---|
| `delivery_day`, `time_utc`, `step_index`, `steps_remaining` | Where we are in the day |
| `execution_steps` | Block length, `min(16, steps_remaining)` |
| `farm` | Name, coordinates, kWp, asset scale |
| `battery` | Capacity, `P_max`, current SoC, bounds, efficiencies, degradation cost |
| `market` | Prices for the **whole** delivery day, because they are known one day ahead |
| `pv` | Current forecast, rest-of-day forecast, realized PV so far |
| `load` | National load forecast, context only |
| `limits` | Optional import and export limits |
| `terminal_value` | Price and mode used to value leftover energy |
| `previous_plan` | The previous block's action indices |

Pydantic enforces the length rules. For example:

- `execution_steps` must equal `min(16, steps_remaining)`.
- Prices must cover `step_index + steps_remaining` intervals.
- The PV forecast must have `steps_remaining` entries.
- Realized PV must have `step_index` entries.
- `time_utc` must be timezone-aware.

The schema is frozen on purpose. The LLM agent, the rule-based baseline, MPC, the oracle and the evaluator all consume the same context. A field rename would break them in different ways, so changes go through `TEAM_PLAN.md` first.

## 7. The prompt

`RL/src/battery_rl/agents/prompts.py` builds two messages. `PROMPT_VERSION` is `v1` and is recorded in the usage payload so a result can be traced to the prompt that produced it.

The **system prompt** states:

- The role: a battery dispatch operator for a merchant PV + battery + grid site.
- That there is no local load, and national load is context only.
- The objective: export revenue minus charging cost minus degradation minus violations, plus terminal SoC value.
- The 17 action levels and the sign convention.
- Planning rules: prices are known, do not forecast them; PV and load forecasts are given.
- The four tools and the JSON shape to use if the model answers directly.

The **user prompt** is compact:

- A state block with the day, time, step index, steps remaining, execution window, farm, battery values, terminal value, limits and previous plan.
- A CSV table with one row per remaining interval: index, time, price, PV forecast, national load forecast.
- A final instruction: the first `execution_steps` rows are the window, return exactly that many entries.

Three prompt choices are deliberate:

- **Temperature 0.0.** Dispatch is a control task. The same state should produce the same schedule, not a creative variation.
- **Prices are labeled as known.** The model is told not to forecast them, because OPCOM publishes them a day ahead.
- **Load is labeled as context.** Without that sentence, a model can easily treat national demand as the site's demand and plan around a load that does not exist.

## 8. The LLM decision loop

`RL/src/battery_rl/agents/llm.py` runs the loop. `tools.py` defines what the model can call.

The model is `deepseek-chat`, reached through the OpenAI-compatible API. The client sends the system and user messages and offers four tools:

| Tool | Purpose |
|---|---|
| `get_state` | Return battery and site state |
| `get_forecast` | Return remaining prices, PV forecast and load forecast |
| `simulate_schedule` | Run a candidate schedule through the simulator |
| `submit_schedule` | Submit the final schedule |

The loop allows up to six tool rounds. A typical successful run looks like this:

1. The model reads the table.
2. It calls `simulate_schedule` once or twice with candidate plans.
3. It compares the simulated cash flow and SoC trajectory.
4. It calls `submit_schedule` with 16 levels.

The model may also answer with plain JSON:

```json
{"schedule": [{"interval": 0, "level": -0.25}, ...], "rationale": "..."}
```

Both paths go through the same validator:

- Exactly `execution_steps` entries.
- Every level is one of the 17 allowed values.
- Intervals are ordered from 0.
- The simulator says the schedule is feasible under the SoC bounds.

If validation fails, the error is appended to the conversation and the model gets one retry (`max_retries: 1`). The retry message says what was wrong and how many intervals are expected. If the retry also fails, or the API errors out, the agent uses the fallback planner. It charges from PV when PV is available, discharges when it is not, and holds inside a small SoC deadband. If even that is unavailable, it holds.

The fallback is not a detail. A live controller cannot stop because a network call failed or a model emitted a malformed array. The run records `valid`, `fallback`, `error` and the usage counters so a bad day is visible in the UI instead of silently scored.

Per-decision telemetry includes tool calls, input and output tokens, model latency, wall-clock time, retry count, and whether the result was feasible. `compute_day_metrics()` turns that into `llm_feasible_rate`, `llm_invalid_rate`, `llm_tool_calls`, `llm_tokens` and `llm_latency_s`.

## 9. Execution, scoring and the web UI

The backend cannot import the RL package because the two have separate virtual environments. Instead, `backend/app/services/rl_simulation.py` launches `backend/app/services/rl_simulation_runner.py` with the RL interpreter and exchanges JSON over stdout.

The runner:

1. Picks a complete day from the requested split, or a specific day if one was passed.
2. Loads the farm, environment and agent configs.
3. Builds the environment and the chosen planner.
4. Loops until the day is done: build context, get a plan, execute each action.
5. Computes the day metrics and returns a JSON trace.

The trace contains `summary`, `decisions` and `steps`. The API exposes it at `POST /api/simulate`, and the React page in `frontend/src/pages/Simulation.tsx` renders it.

What the UI shows maps directly to the trace:

| UI element | Trace field |
|---|---|
| Score and profit cards | `summary.score_ron`, `net_cost_ron`, `export_revenue_ron` |
| Battery and grid charts | `steps[].soc`, `import_mw`, `export_mw`, `pv_mw`, `price_ron_mwh` |
| Decision cards | `decisions[].actions`, `levels`, `rationale`, `usage` |
| LLM telemetry | `usage.tokens_in`, `tokens_out`, `tool_calls`, `latency_s`, `retries` |
| Fallback warning | `decisions[].fallback`, `valid`, `error` |

## 10. One day, walked through

Take 08:00 local on a normal 96-interval day.

- `step_index` is 32, so 64 intervals remain.
- `execution_steps` is 16, covering 08:00 to 12:00.
- The battery is at 50%, or 5 MWh of a 10 MWh pack.
- The PV forecast for the next block starts near 2.0 MW and rises toward midday.
- Prices for the whole day are already in the context, because they are known from the day-ahead market.

The context is built and validated. The prompt contains the state block and a 64-row forecast table. DeepSeek reads it, calls `simulate_schedule` with a charging plan, compares the result, then submits 16 levels.

Suppose it submits level `-0.25` for the first interval. An actual PV value of 2.0 MW arrives, and the price is 400 RON/MWh:

```
requested power  = -0.25 x 2 MW = -0.5 MW   (charge)
power balance    = PV 2.0 - charge 0.5 = export 1.5 MW
export revenue   = 400 x 1.5 MW x 0.25 h = 150 RON
charge energy    = 0.5 MW x 0.25 h x 0.95 = 0.11875 MWh
degradation      = 50 RON/MWh x 0.11875 MWh = 5.94 RON
SoC change       = 0.11875 MWh / 10 MWh = +1.19 percentage points
```

Those prices and PV values are illustrative. The arithmetic is the same one the simulator runs.

At 12:00 the next decision starts from the new SoC and the updated forecast. The cycle repeats four more times. When the delivery day ends, the score adds the terminal value of whatever energy is left.

## 11. Where the learning actually happens

This is worth stating plainly because the folder is called `RL/` and the package is called `battery_rl`.

| Component | Learns from data? | How it works |
|---|---|---|
| PV forecast model | Yes | Supervised regression, gradient-boosted trees, trained offline |
| LLM dispatch agent | No | Prompted at runtime, tools, temperature 0 |
| MPC | No | Linear program over known prices and forecast PV |
| Oracle LP | No | Same LP, but with actual future PV as an upper bound |
| Rule-based, price threshold, idle | No | Fixed rules or simple quantiles |
| Simulator | No | Deterministic physics and accounting |

"Reinforcement learning" describes the shape of the problem: an agent observes a state, takes an action, and receives a reward. It does not describe a training loop in this codebase. No reward signal updates the LLM's weights. Improving the agent means changing the prompt, the tools, the forecast quality or the evaluation set, not running gradient descent.

That distinction also explains the reference strategies. Idle, rule-based, price threshold and MPC are there so the LLM has something honest to beat. The oracle is there to show the ceiling. Without them, "the LLM made 3,000 RON" says nothing.

## 12. Where to look in the code

| What you want to understand | File |
|---|---|
| Dataset contract and alignment | `RL/src/battery_rl/data/dataset.py` |
| OPCOM price scraping and DST handling | `RL/src/battery_rl/data/opcom.py` |
| NWP runs and causal issue times | `RL/src/battery_rl/data/nwp.py`, `forecasts.py` |
| PV actual from irradiance | `RL/src/battery_rl/data/pv.py` |
| Feature engineering and the model | `RL/src/battery_rl/models/pv.py` |
| Training and metrics | `RL/scripts/train_pv.py` |
| Battery physics | `RL/src/battery_rl/env/battery.py` |
| Power balance and cash | `RL/src/battery_rl/env/balance.py` |
| Environment loop | `RL/src/battery_rl/env/env.py` |
| Context JSON | `RL/src/battery_rl/env/context.py`, `agents/schemas.py` |
| Prompts | `RL/src/battery_rl/agents/prompts.py` |
| LLM client and tool loop | `RL/src/battery_rl/agents/llm.py`, `tools.py` |
| Simulator used by the `simulate_schedule` tool | `RL/src/battery_rl/agents/simulator.py` |
| Daily metrics | `RL/src/battery_rl/eval/metrics.py` |
| Evaluation over a split | `RL/src/battery_rl/eval/runner.py`, `RL/scripts/evaluate.py` |
| Backend bridge | `backend/app/services/rl_simulation.py`, `rl_simulation_runner.py` |
| Web endpoint | `backend/app/api/routes/simulate.py` |
| Web page | `frontend/src/pages/Simulation.tsx` |

## 13. How to run it

Setup from the repository root:

```powershell
make setup      # or: powershell -ExecutionPolicy Bypass -File .\setup.ps1
make dev        # or: powershell -ExecutionPolicy Bypass -File .\dev.ps1
```

The web app runs at `http://localhost:5173` and the API docs at `http://localhost:8000/api/docs`.

A direct simulation call:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/simulate `
  -ContentType application/json `
  -Body '{"strategy":"llm","split":"val"}'
```

The RL package has its own virtual environment:

```powershell
cd RL
.venv\Scripts\python.exe scripts\build_dataset.py --pv-source auto --pv-forecast model
.venv\Scripts\python.exe scripts\train_pv.py
.venv\Scripts\python.exe scripts\evaluate.py --split val
```

The LLM strategies need `DEEPSEEK_API_KEY` in `RL/.env`. Without it, `evaluate.py` skips the LLM with a warning and runs the other strategies.

## 14. Things that confuse people first

**"The model forecasts prices."** It does not. OPCOM prices are known from the day-ahead market and are passed to the agent directly. Only PV and national load are forecasts.

**"National load is the site's demand."** The site has zero local demand. National load is a market signal. The power balance never uses it.

**"`pv_mw` and `pv_forecast_mw` are the same thing."** They are not. `pv_mw` is the realized proxy the environment executes. `pv_forecast_mw` is what the agent was allowed to know at the issue time. Comparing them is how forecast error becomes money.

**"The LLM learns from the simulation."** There is no training loop. The simulation scores the output. It does not update the model.

**"Lower MAE always means more money."** Not necessarily. An error at noon on a clear day matters differently from the same error at night, and an error during a high-price interval costs more. MAE is a useful summary, not the objective.

**"An API failure stops the run."** The agent retries once, then falls back to the rule-based planner. The trace marks the decision as a fallback.

**"Sixteen actions cover the day."** They cover four hours. The day is six blocks of sixteen, with a shorter final block on DST days.

**"The schedule can push the battery past its SoC limits."** The agent may submit an infeasible schedule, but the validator rejects it before execution. The environment also clips every executed step and records the shortfall as a violation.
