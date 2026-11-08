# Phase 8 — receding-horizon evaluation and prompt tuning

Status: **complete for the validation split** (prompt v2, 61 days × 3 repeats).
The first full run was interrupted by host memory pressure at 120/183 episodes;
the resumed run reused those transcripts and completed the remaining 63. The
test split remains untouched (Phase 9).
Date: 2026-11-08.
Scope: `RL/` only. The test split is **not** touched in this phase.

Phase 8 answers four questions on the validation split:

1. Does the LLM beat idle and rule-based under the 4-hour receding horizon?
2. How large is the gap to price-threshold, MPC and the perfect-foresight oracle?
3. Which decisions or failure modes explain the gap, and can prompt tuning close it?
4. Are schedules feasible, and are tokens, latency and cost operationally credible?

## Pre-Phase-8 model-state backup

Created before any Phase 8 change:

- Archive: `artifacts/backups/pre_phase8_2026-11-08_004503.tar.gz`
- SHA-256: `8d2781ceda9853e9db56cb9cc94006a3e1d4bcbd29b129d7cec411fdd8007e71`
- Size: 1,921,010 bytes, 100 files
- Contents: trained PV model (`artifacts/models/pv`), agent config, v1
  prompt/tool/LLM source, all configs, the pre-Phase-8 baseline reports,
  dataset metadata, tests, and a `BACKUP_MANIFEST.md` with per-file hashes,
  the git commit and the farm checksum.
- Explicitly excluded: `RL/.env` (API key), virtual environments, caches, raw
  downloads and the large processed CSVs.

`scripts/backup_model_state.py` reproduces the snapshot. The manifest inside the
archive documents the restore command.

## Implementation changes

### Raw decision transcripts (Phase 7 carry-over)

`LLMAgent` now keeps one transcript per decision. `run_split(...,
transcript_dir=...)` writes one JSONL file per day/strategy/mode/repeat. Each
line contains the full system and user prompts, every conversation message,
every tool call with arguments, per-round cache-hit/miss and output tokens,
latency, cost, the retry history and the final valid/fallback result.
`scripts/evaluate.py` writes to `<output>/transcripts/` by default and exposes
`--transcript-dir` / `--no-transcripts`. The completed validation transcripts
are archived as `artifacts/reports/val/transcripts.tar.gz` (3.8 MB compressed
from 38 MB).

### Evaluation throughput and robustness

- `run_split(..., workers=N)` evaluates delivery days concurrently. Days are
  independent; result order is unchanged. `evaluate.py` exposes `--workers`.
- Per-episode progress is logged (`run <day>: <strategy>/<mode> repeat <n>`);
  HTTP client INFO logs are suppressed.
- `--resume` replays existing per-decision transcripts locally and calls the
  LLM only for missing day/mode/repeat combinations. The replay reproduces the
  original actions and telemetry, and rejects transcripts from a different
  prompt version. A host memory kill interrupted the first full validation run
  at 120 of 183 episodes; the resumed run reuses those 120 transcripts.
- SDK-level retries are disabled (`client_max_retries: 0`) so a provider
  `Retry-After` cannot hide a long sleep. The agent makes one explicit retry
  with a short bounded backoff, logs the failure, then falls back.
- `request_timeout_s` is configurable (60 s by default).

### Cost and telemetry

- The client records DeepSeek `prompt_cache_hit_tokens` /
  `prompt_cache_miss_tokens` and the served model from the response.
- `AgentConfig.pricing` holds the published USD-per-million-token rates, the
  off-peak multiplier and the USD/RON rate. Peak hours are 01:00–04:00 and
  06:00–10:00 UTC, Monday–Friday; Chinese public holidays are ignored
  (conservative).
- `llm_cost_ron` is now populated per decision and per day.
- The report gains an **LLM telemetry** section: feasibility, invalid rate,
  tool calls/day, tokens/day, latency/day and cost/day.
- Every `evaluate.py` run writes `run_metadata.json` with the split, farm
  checksum, repeats, strategies, requested/served model, prompt version,
  execution horizon and pricing source.

### Simulator-tool instructions

- A successful `simulate_schedule` response now reports
  `simulator_calls_remaining` and a `next_step` hint.
- A call beyond the limit returns an explicit "call `submit_schedule` now"
  instruction. This removed the rejected fourth simulator call observed in v1.

## Prompt tuning: v1 → v2

Version string: `PROMPT_VERSION = "v2"` in
`src/battery_rl/agents/prompts.py`, and `prompt_version: v2` in
`configs/agent.yaml`.

The v1 transcript audit (10 validation days, 60 decisions) found three
economics errors and two process inefficiencies:

| Observation (v1) | Consequence | v2 fix |
|---|---|---|
| PV charging treated as free ("PV covers charging") | over-charged into moderate prices | Charging has the current price as opportunity cost, whether from PV or grid |
| `terminal_value` used as an intraday charging hurdle (57/60 rationales) | refused profitable cheap-hour charging, e.g. 2026-08-07 | Terminal value applies only to end-of-day SoC; intraday decisions compare remaining-day prices |
| Charge and discharge required to fit in one 4-hour window | held instead of charging for a later window | Plan the rest of the day as one arbitrage problem; a charge may be discharged later |
| `get_state` and `get_forecast` called on every decision (1.0 each) | extra rounds/tokens | Prompt states the state block and table already contain that data; tools remain available |
| 5 rejected fourth simulator calls in 60 decisions | wasted rounds | Explicit budget plus `next_step`/`simulator_calls_remaining` tool responses |

v2 also adds the exact charge hurdle

```
p_later > p_now / (eta_c * eta_d)
          + degradation_cost_ron_per_mwh * (1 + 1 / eta_d)
```

and compact derived price summaries in the user prompt (execution-window and
remaining-day min/mean/max, four cheapest and four most expensive intervals).
These are derived from the same known prices; no new data or test information
is used.

Example failure (v1, 2026-08-07 05:00): the rationale rejected charging at
423–872 RON/MWh because those prices were "well below the terminal value of
831", even though the same forecast showed an evening peak of 1100–1360. The
LLM cycled 4.0 MWh that day and scored 37,592; MPC cycled 22.9 MWh and scored
42,127. The v2 prompt replaces that comparison with the remaining-day price
distribution and the explicit charge hurdle.

Measured prompt effect (same days, LLM transcripts):

| Metric | v1 (10 days × 1 repeat) | v2 (2-day smoke) |
|---|---|---|
| Rounds per decision | 4.50 | 4.08 |
| `get_state` calls/decision | 1.00 | 0.67 |
| `get_forecast` calls/decision | 1.00 | 0.33 |
| `simulate_schedule` calls/decision | 2.50 | 2.33 |
| Rejected simulator calls | 5 / 60 decisions | 0 / 12 decisions |
| Rationales mentioning terminal value | 57 / 60 | 4 / 12 |

## Evaluation protocol

- Split: **validation** (2026-08-01 … 2026-09-30), complete delivery days only.
- Receding horizon: re-plan every 16 intervals (4 hours); execution window 16
  intervals; planning horizon rest of the delivery day.
- Repeats: **3 per day** for the final run.
- Strategies: `idle`, `rule_based` (step and block), `price_threshold`, `mpc`,
  `oracle_lp`, `llm`.
- Model: requested `deepseek-chat`, served `deepseek-flash` (recorded per
  response). Temperature 0.
- Prompt tuning used only validation days. The test split remains frozen.

Reproduction:

```powershell
cd RL
# 10-day tuning sample
.venv\Scripts\python.exe scripts/evaluate.py --split val --limit-days 10 `
    --repeats 3 --workers 2 --output-dir artifacts/reports/val_prompt_v2_sample_r3

# full validation run
.venv\Scripts\python.exe scripts/evaluate.py --split val --repeats 3 --workers 2

# resume an interrupted run, reusing its saved transcripts
.venv\Scripts\python.exe scripts/evaluate.py --split val --repeats 3 --workers 2 --resume

# rebuild the markdown report from a saved CSV
.venv\Scripts\python.exe scripts/make_report.py --csv artifacts/reports/val/results.csv
```

## Results

<!-- RESULTS_START -->
### Tuning sample — first 10 validation days

Prompt v1, 1 repeat per day (the 3-repeat run was stopped after the provider
stalled; v2 is compared on the same days):

| Strategy | Mode | Score mean | Net cost mean | Throughput mean | Cycles mean |
|---|---|---:|---:|---:|---:|
| idle | block | 35,973.88 | −32,242.35 | 0.000 | 0.000 |
| rule_based | block | 35,915.78 | −29,838.41 | 6.252 | 0.313 |
| rule_based | step | 37,816.94 | −35,109.99 | 16.019 | 0.801 |
| price_threshold | block | 41,922.70 | −41,923.44 | 15.962 | 0.798 |
| mpc / oracle_lp | block | 43,702.15 | −44,077.15 | 22.774 | 1.139 |
| **llm (v1)** | block | **40,957.69** | **−41,041.20** | 17.709 | 0.885 |

v1 gaps on this sample: **+13.9% vs idle**, **+8.3% vs rule-based step**
(+14.0% vs rule-based block), **−2.3% vs price-threshold**, **−6.3% vs
MPC/oracle**. All 60 decisions were feasible with no fallbacks; telemetry was
33 tool calls/day, 141,348 tokens/day and 79.0 s/day of API latency.

Per-day gaps to MPC ranged from −2% to −14%. The worst days (2026-08-01,
2026-08-06, 2026-08-07) were traced to the three economics errors listed
above, not to invalid schedules.

Prompt v2, same 10 days, **3 repeats per day** (30 episodes):

| Strategy | Mode | Score mean | Net cost mean | Throughput mean | Cycles mean |
|---|---|---:|---:|---:|---:|
| idle | block | 35,973.88 | −32,242.35 | 0.000 | 0.000 |
| rule_based | block | 35,915.78 | −29,838.41 | 6.252 | 0.313 |
| rule_based | step | 37,816.94 | −35,109.99 | 16.019 | 0.801 |
| price_threshold | block | 41,922.70 | −41,923.44 | 15.962 | 0.798 |
| mpc / oracle_lp | block | 43,702.15 | −44,077.15 | 22.774 | 1.139 |
| **llm (v2)** | block | **42,718.29** | **−42,784.37** | 19.212 | 0.961 |

v2 gaps on the same sample: **+18.8% vs idle**, **+18.9% vs rule-based
block** (+13.0% vs its step mode), **+1.9% vs price-threshold**, and
**−2.25% vs MPC/oracle**.

Prompt v2 improves the LLM mean score by **+4.30%** over v1 on the same days.
It closes 4.1 of the 6.3 percentage points of the v1 MPC gap and moves ahead
of price-threshold. Across the 10 days the per-day gap to MPC is consistently
between **−1% and −4%** (no −11%…−14% outliers).

LLM telemetry (30 episodes): **100% feasible**, 0% invalid, 24.8 tool
calls/day, 132,249 tokens/day, 98.3 s/day of API latency, **0.0611 RON/day**
of provider cost. The mean within-day standard deviation across the three
repeats is 440 RON (~1.0% of the mean score), so the evaluation is stable.

_This sample is a tuning result. The final headline numbers come from the
full validation split, 3 repeats/day (see below)._

### Full validation split

61 complete days (2026-08-01 … 2026-09-30) × 3 repeats = **183 LLM episodes**,
prompt v2, 4-hour receding horizon. The run was resumed from 120 saved
transcripts; only the 63 missing episodes called the provider.

| Strategy | Mode | Score mean | Score std | Net cost mean | Export rev mean | Throughput mean | Cycles mean |
|---|---|---:|---:|---:|---:|---:|---:|
| idle | block | 30,421.08 | 11,755.32 | −26,340.68 | 26,340.68 | 0.000 | 0.000 |
| rule_based | block | 30,803.22 | 11,021.28 | −24,186.81 | 24,334.93 | 6.513 | 0.326 |
| rule_based | step | 33,055.43 | 10,183.82 | −31,396.40 | 31,396.40 | 17.547 | 0.877 |
| price_threshold | block | 36,383.25 | 11,173.02 | −36,409.55 | 36,936.61 | 17.938 | 0.897 |
| **llm (v2)** | block | **36,524.77** | 10,913.41 | **−36,322.51** | 36,870.22 | 18.988 | 0.949 |
| mpc / oracle_lp | block | 37,759.69 | 11,134.09 | −38,075.80 | 39,094.22 | 23.106 | 1.155 |

**Headline gaps (block mode):**

| Reference | LLM score | Reference score | Gap |
|---|---:|---:|---:|
| idle | 36,524.77 | 30,421.08 | **+20.1%** |
| rule_based (block) | 36,524.77 | 30,803.22 | **+18.6%** |
| rule_based (step) | 36,524.77 | 33,055.43 | +10.5% |
| price_threshold | 36,524.77 | 36,383.25 | **+0.4%** |
| mpc / oracle_lp | 36,524.77 | 37,759.69 | **−3.3%** |

The LLM earns **50.2% more net revenue than rule-based block** (−36,322.51 vs
−24,186.81 RON) and 15.7% more than rule-based step. It is effectively tied
with price-threshold in the aggregate (+0.4%) and wins that comparison on 34 of
61 days. It does **not** beat MPC/oracle: it trails by 3.3%, with a per-day gap
between −1.16% and −8.12% (no day beats MPC, which is the optimization
baseline). This is the honest Phase 8 outcome.

**Per regime:**

| Regime | Days | LLM | MPC | Price-thr. | Rule | Gap vs MPC | Gap vs price-thr. | Gap vs rule |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 61 | 36,524.77 | 37,759.69 | 36,383.25 | 30,803.22 | −3.27% | +0.39% | +18.57% |
| high_price | 21 | 43,112.55 | 44,733.96 | 43,257.92 | 36,777.58 | −3.62% | −0.34% | +17.23% |
| low_price | 21 | 28,044.45 | 29,019.08 | 27,551.54 | 21,761.95 | −3.36% | +1.79% | +28.87% |
| volatile | 21 | 35,413.99 | 36,961.14 | 35,704.13 | 28,522.94 | −4.19% | −0.81% | +24.16% |
| sunny | 21 | 43,330.56 | 44,651.96 | 43,073.26 | 36,896.35 | −2.96% | +0.60% | +17.44% |
| cloudy | 21 | 30,993.28 | 32,345.22 | 31,027.03 | 25,660.09 | −4.18% | −0.11% | +20.78% |
| weekend | 18 | 25,727.14 | 26,624.99 | 25,071.81 | 19,625.28 | −3.37% | +2.61% | +31.09% |

The relative pattern is stable across regimes: the LLM beats the simple
baselines everywhere and trails MPC everywhere. The largest deficit is in
volatile/cloudy conditions (−4.2%); the smallest is sunny (−3.0%).

**Telemetry (183 episodes):**

- Feasibility **100%**; invalid/fallback rate **0%**.
- 25.7 tool calls/day, **137,894 tokens/day**, **99.6 s/day** of API latency.
- **0.0663 RON/day** (~$0.014) provider cost; **12.14 RON (~$2.54)** for the
  entire 183-episode validation run.
- Mean within-day standard deviation across the three repeats: **512 RON**
  (~1.4% of the mean score).

**Why the remaining MPC gap:** the LLM uses 18.99 MWh/day of throughput and
0.949 equivalent cycles versus MPC's 23.11 MWh and 1.155 cycles. It matches
MPC's general shape (charge cheap, discharge expensive, end near SoC minimum)
but leaves roughly 18% of the arbitrage volume unused. The gap is economic,
not operational: no invalid schedules, no fallbacks, no SoC violations.

**Phase 8 exit:** met. The LLM beats idle (+20.1%) and rule-based (+18.6%
block, +10.5% step, winning 61/61 days with a minimum +5.6%), is stable across
three repeats, produces 100% feasible schedules, and is operationally
credible at ~100 s/day of API latency and 0.07 RON/day. The gap to MPC/oracle
is reported at −3.3%.

<!-- RESULTS_END -->

## Cost and latency

The provider rates and FX rate are recorded in `configs/agent.yaml` and
`run_metadata.json`. The LLM cost is small relative to energy revenue; the
operational constraint is wall-clock latency and provider throughput, not cost.

## Limitations

- `deepseek-chat` is not listed on the provider pricing page; the API serves it
  as `deepseek-flash`, confirmed by `response.model`. Flash rates apply.
- Temperature 0 is not fully deterministic across runs; three repeats per day
  quantify the spread.
- The provider was congested during peak hours. The final run uses conservative
  day-level concurrency; raw transcripts and per-episode logs make stalls
  visible.
- The simulator scores only the execution window, so the model must reason
  about later windows from the forecast table.
- Chinese public holidays are not modelled in the peak/off-peak cost; treating
  them as peak is conservative.

## Complete change list

Code and configuration:

- `src/battery_rl/agents/llm.py` — per-decision transcripts (prompts,
  conversation, tool calls, outcomes), cache-hit/miss token accounting,
  served-model capture, cost calculation, bounded retries and a prompt-version
  check.
- `src/battery_rl/agents/prompts.py` — prompt v2: charging opportunity cost,
  end-of-day-only terminal value, cross-window planning, price summaries,
  no redundant state/forecast calls, simulator budget.
- `src/battery_rl/agents/tools.py` — simulator call budget, remaining-call
  hints and an explicit "submit now" instruction at the limit.
- `src/battery_rl/config.py` — `AgentPricingConfig`, request timeout, client
  retry setting and prompt v2 default.
- `src/battery_rl/eval/runner.py` — JSONL transcript writing, local transcript
  replay, `--resume` support, day-level concurrency and per-episode logging.
- `src/battery_rl/eval/report.py` — LLM telemetry table, LLM-vs-reference gap
  table, run-metadata line.
- `scripts/evaluate.py` — transcript directory, concurrency, resume and run
  metadata.
- `scripts/backup_model_state.py` — reproducible pre-change model-state
  snapshot with manifest and checksums.
- `configs/agent.yaml` — prompt v2, provider pricing, timeout/retry settings.
- Tests — transcripts, resume, prompt-version rejection, cost accounting,
  concurrency ordering and report tables (235 tests, ruff clean).
- Docs — `README.md`, `PLAN.md` and this document.

Artifacts:

- `artifacts/backups/pre_phase8_2026-11-08_004503.tar.gz` — pre-Phase-8 model
  state, manifest and SHA-256.
- `artifacts/reports/val/report.md`, `results.csv`, plots and
  `run_metadata.json` — final validation report.
- `artifacts/reports/val/transcripts.tar.gz` — compressed per-decision
  transcripts for all 183 validation episodes.
- Tuning samples (`val_prompt_v1_sample`, `val_prompt_v2_sample_r3`,
  `val_llm_smoke`, `val_prompt_v2_smoke`) remain on disk as supporting
  evidence; they are generated outputs and are not tracked.

Commits:

- `ed6e297` — implementation, prompt v2 and the pre-Phase-8 backup.
- `f8a8238` — full validation results, resume support and documentation.

## Next steps (Phase 9)

- Freeze model ID, prompt version and evaluation protocol.
- Run the held-out test split with three repeats.
- Report the IDEA metrics, LLM-specific metrics, regime breakdown and
  open-loop vs receding comparison.
- Publish `artifacts/reports/report.md` with plots and a conclusion.
