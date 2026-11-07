# PLAN — RL Battery Energy Optimization

Build plan for the component described in `IDEA.md`: a simulated PV park + battery + grid
environment driven by real data, a PPO agent that decides when to charge / discharge / hold,
the two baseline strategies, and an evaluation harness that compares them on unseen days.

Scope: a standalone Python package under `RL/` (no backend/frontend dependency for the core
work). Dashboard/API integration is an optional final phase.

---

## 0. What we are building

```
real data (OPCOM PZU prices, national load, PV, forecasts)
        ↓
Gymnasium environment (battery physics, power balance, reward)
        ↓
PPO agent (Stable-Baselines3)
        ↓
evaluation report (RL vs idle vs rule-based, IDEA metrics, unseen days)
```

Every phase below produces something runnable. Later phases must not be started before the
exit criteria of earlier ones are met, because bugs in the simulator silently poison the
learning and are very hard to diagnose later.

---

## 1. Decisions and assumptions

Values from `IDEA.md` are fixed. Data-source decisions taken on 2026-11-07 are recorded below;
remaining gaps are marked **open** and tracked until filled. Keep all of them in one config
file, never hard-coded.

| Parameter | Value | Source |
|---|---|---|
| Episode length | 24 h = 96 steps | IDEA |
| Step duration | 15 min (`dt = 0.25 h`) | IDEA |
| Battery capacity | 10 MWh | IDEA |
| Max charge / discharge power | 2 MW / 2 MW | IDEA |
| SoC limits | 10% – 90% | IDEA |
| Charge / discharge efficiency | 95% / 95% | IDEA |
| PV park peak power | TBD — real site capacity | **open** (coordinates, kWp) |
| Consumer peak load | TBD — national load scaled to site | **open** (scaling factor) |
| Grid export limit | none | decision 2026-11-07 |
| Grid import limit | unlimited | decision 2026-11-07 |
| Buy price | OPCOM PZU, 15-min, RON/MWh | decision 2026-11-07 |
| Sell price | OPCOM PZU, 15-min, RON/MWh | decision 2026-11-07 |
| Price forecast | actual PZU (published D-1) | decision 2026-11-07 |
| Load source | ENTSO-E RO actual load, scaled | **open** (scaling) |
| PV source | farm config from the form → PVGIS; metered CSV optional | **open** (seed config) |
| Date range | 2026-01-01 → 2026-11-07 scraped; extend daily | done (2026-11-07) |
| Currency | RON internally; EUR display only | decision 2026-11-07 |
| Forecast horizon | next 4 h = 16 steps (`K=16`) | state spec |
| Train / val / test | chronological blocked split, frozen test | evaluation spec |
| Training timesteps | 300k–1M PPO steps | SB3 practical range |

Decision 2026-11-07 — no export limit: all surplus is sold, so there is no curtailment and no
wasted energy. This makes two IDEA metrics constant (`wasted energy = 0`, `renewable
utilization = 100%`); they are still reported for compliance, but conclusions must rest on net
cost, export revenue, self-consumption and battery metrics. The environment keeps an optional
`export_limit` (default `None`) so a capped connection can be simulated later without a code
change.

Open items still to settle (they do not block the price/load pipeline):
1. The first farm configuration to train (location, PV capacity, inverter, tilt/azimuth,
   battery parameters). These are captured by the Phase 11 form; until the form exists, use a
   seed config with the defaults above. A metered PV CSV, if one exists, replaces the PVGIS
   model.
2. Consumer size/type for scaling the national load (annual MWh or peak MW).
3. Exact training/evaluation window within the available 15-min PZU history.
4. Data delivery: user-provided OPCOM CSVs, or a downloader we build; confirm OPCOM terms.
5. PV forecast source: archived NWP (Open-Meteo) or a vendor.
6. Should the demo show the live simulation in the dashboard (Phase 11) or is a report enough?
7. Is a continuous-action version required, or is the discrete version the deliverable?

---

## 2. Repository layout

```
RL/
  pyproject.toml
  README.md
  PLAN.md
  IDEA.md
  configs/
    env.yaml               # battery, park, reward weights, episode settings
    train_ppo.yaml         # PPO hyperparameters, seeds, run name
    eval.yaml              # scenarios, episode counts, output paths
  scripts/
    download_opcom.py      # CLI: OPCOM PZU 15-min scraper (implemented)
    build_dataset.py       # CLI: align, validate, split, write data card + stats plots
    train.py               # CLI: PPO training
    evaluate.py            # CLI: compare strategies, write metrics table
    make_report.py         # CLI: plots + report.md from evaluation results
  src/battery_rl/
    __init__.py
    config.py              # dataclasses/pydantic models for all YAML configs
    seeding.py             # seed everything (random, numpy, torch, gym)
    data/
      opcom.py             # OPCOM PZU 15-min prices (buy = sell)
      entsoe.py            # RO national actual load + day-ahead load forecast
      pv.py                # metered PV CSV or PVGIS/ERA5 production model
      forecasts.py         # price/load/PV forecast alignment
      synthetic.py         # deterministic tiny fixtures for unit tests only
      scenarios.py         # data-derived date ranges / scenario labels
      dataset.py           # loading, splits, EpisodeSampler
      validate.py          # gaps, DST, ranges, provenance checks
    env/
      battery.py           # pure battery physics functions
      observations.py      # state vector builder + normalization
      reward.py            # reward and terminal valuation
      env.py               # BatteryEnv(gym.Env)
    strategies/
      base.py              # Strategy protocol: act(obs, info) -> action
      idle.py
      rule_based.py
      price_threshold.py   # optional third baseline
      rl_policy.py         # adapter around a loaded SB3 model
    eval/
      metrics.py           # all metric formulas in one place
      runner.py            # unified episode loop for any Strategy
      report.py            # tables, plots
    train/
      train_ppo.py         # model construction + training loop
      callbacks.py         # periodic eval, best checkpoint, early stop
  tests/
    test_battery.py
    test_env.py
    test_reward.py
    test_data.py
    test_metrics.py
    test_opcom.py
  artifacts/               # gitignored
    data/
      raw/                 # untouched downloads + provenance
      processed/           # aligned dataset used by the env
    models/
    runs/                  # tensorboard
    reports/
```

Add `artifacts/` to `.gitignore`. Use `uv` like the backend (`pyproject.toml` + `uv sync`).
Dependencies: `gymnasium`, `stable-baselines3`, `numpy`, `pandas`, `matplotlib`, `pyyaml`,
`pytest`, `tensorboard`; optional `pulp` or `scipy` for the perfect-foresight oracle.

---

## 3. Simulator specification

### 3.1 Time and data

- Resolution 15 min, episode = 96 steps. All series are real, aligned to Europe/Bucharest and
  stored at 15-min resolution: buy and sell price from OPCOM PZU, load from the national
  dataset (scaled), PV from metered data or PVGIS. PZU became 15-min on 2025-10-01, so the
  15-min dataset starts there; older hourly prices are not used.
- An episode starts at a random index inside a split. For the main reported numbers, align
  starts to whole days (index multiple of 96) to match "duration of an episode: 24 hours";
  random starts are used during training for coverage.
- Initial SoC: random in [30%, 70%] during training; fixed 50% during evaluation so all
  strategies start identically.

### 3.2 Battery model

State: `SoC ∈ [0.1, 0.9]`, stored energy `E = SoC · C` (MWh), `C = 10 MWh`.
Power sign convention: `P > 0` = discharge to the bus, `P < 0` = charge from the bus (MW).

Per step (`dt = 0.25 h`):

```
charge:     E_next = E + |P| · dt · η_c
discharge:  E_next = E − P · dt / η_d
```

Feasible power (clip before applying, record the clipped amount):

```
P_charge_max    = (SoC_max − SoC) · C / (η_c · dt)       [MW]
P_discharge_max = (SoC − SoC_min) · C · η_d / dt         [MW]
```

Both are additionally capped at 2 MW. Clipping is the mechanism that enforces
`SoC_min ≤ SoC ≤ SoC_max`; the environment never produces an invalid SoC. The requested-vs-
executed difference is stored in `info` and fed into a small violation penalty, so the agent
learns to avoid pushing against the limits rather than relying on the clip.

### 3.3 Power balance and economics

Order of operations per step:

1. Read `pv[t]`, `demand[t]`, `price_buy[t]`, `price_sell[t]`.
2. Execute the (clipped) battery action.
3. Net bus power before grid limits (`P_charge ≥ 0` and `P_discharge ≥ 0` are the magnitudes of
   the executed battery power; both are zero unless the corresponding action was taken):

   ```
   P_net = demand − pv − P_discharge + P_charge        [MW]
   ```

4. Import / export. The export limit is disabled (decision 2026-11-07); import is unlimited:

   ```
   import = max(P_net, 0)
   export = max(−P_net, 0)
   ```

   Keep `export_limit` as an optional config parameter (default `None`) so a capped
   connection can be simulated later without changing the environment code.

5. While the export limit is disabled there is no curtailment:
   `curtailed_energy_t = 0`. If a limit is configured later, curtailment is
   `max(−P_net − export_limit, 0) · dt`, derived from the balance so it can never be
   double-counted.
6. Cash flow (`EUR`, or any consistent unit):

   ```
   cost_t = price_buy[t] · import · dt − price_sell[t] · export · dt
   ```

   Positive `cost_t` = money spent, negative = money earned. Load is always served (import
   is unlimited by default), so no unserved-demand term is needed in v1.

Energy conservation identity that must hold every step (power form; multiply by `dt` for
MWh). This follows directly from the definitions above and is the single most valuable
invariant test:

```
pv + import + P_discharge = demand + P_charge + export + curtailment_power
```

where `curtailment_power = max(−P_net − export_limit, 0)`, which is 0 while the export limit
is disabled.

### 3.4 Observation vector

All components scaled to roughly `[-1, 1]` with fixed, documented constants (not running
statistics, so evaluation is consistent across runs):

| Block | Dim | Notes |
|---|---|---|
| SoC | 1 | `(SoC − 0.1) / 0.8` |
| PV now | 1 | `/ 6 MW` |
| Demand now | 1 | `/ 4 MW` |
| Buy price now | 1 | `/ 200` |
| Sell price now | 1 | `/ 200` |
| PV forecast | K | actual next K steps, normalized |
| Demand forecast | K | actual next K steps, normalized |
| Price forecast | K | optional extension, day-ahead prices are known in advance |
| Time of day | 2 | `sin(2πt/96)`, `cos(2πt/96)` |

Total ≈ 40 dims with `K=16`. `gym.spaces.Box(-1, 1, shape=(obs_dim,), float32)`.

Forecast construction: precomputed in the dataset as `forecast[t, h]` for `h = 1..K`.
Default mode is *noisy perfect foresight*: `actual[t+h] · (1 + ε_h)` with `ε_h` growing with
horizon, clipped at 0. This is not a causal forecast model; document that limitation. Provide
an `oracle` mode (no noise) and a `strong_noise` mode for robustness tests. Never include
actual future values anywhere else in the observation.

### 3.5 Actions

Discrete, `gym.spaces.Discrete(3)`:

| Action | Meaning | Power |
|---|---|---|
| 0 | CHARGE | `−P_max` (2 MW) |
| 1 | HOLD | 0 |
| 2 | DISCHARGE | `+P_max` (2 MW) |

Start with full-power actions. If the learned policy degenerates to bang-bang behavior, add
finer levels `{−1, −0.5, 0, 0.5, 1} · P_max` (still `Discrete(5)`) without changing the API.
Continuous actions are Phase 10, not the deliverable.

### 3.6 Episode definition

- `reset(seed, options)`: sample a start index within the env's split (optionally a fixed
  `options={"day_index": ...}` for evaluation), sample initial SoC, return normalized obs and
  an `info` dict with raw values.
- `step(action)`: returns `(obs, reward, terminated, truncated, info)`.
  `terminated=False` always in v1 (battery limits are clipped, not fatal);
  `truncated=True` at step 96. No time-limit wrapper needed.
- `info` contains raw PV, demand, prices, SoC, executed powers, cash flow, curtailed energy,
  violation amount, and episode step index. Evaluation reads metrics from `info`, not from
  the reward, which keeps measurement independent from reward shaping.

---

## 4. Reward function

Primary signal is real money, so the objective matches the IDEA requirement to reflect the
true economic goal without rewarding the same energy twice.

```
r_t = reward_scale · [ −cost_t
                       − c_deg · (charge_energy_t + discharge_energy_t)
                       − λ_viol · |P_requested − P_executed| · dt
                       − λ_switch · 1[action_t ≠ action_{t−1}]        (optional)
                     ]
```

Here `charge_energy_t = P_charge · dt` and `discharge_energy_t = P_discharge · dt`, both in
MWh.

At the last step, add the value of energy left in the battery, otherwise the agent learns to
dump the battery at the end of the episode:

```
terminal_value = price_ref · SoC_end · C · η_d
```

with `price_ref` = mean buy price over the episode (or a fixed configured reference price).

Rules to avoid double counting:

- Do **not** add separate bonuses for "solar used", "revenue" or "reduced import": all of
  those already appear in `cost_t` through the buy/sell prices.
- `wasted energy` is penalized only if it is not already priced. Since curtailment has an
  opportunity cost visible through export price, v1 leaves it out of the reward and only
  reports it as a metric.
- Keep every penalty an order of magnitude below the economic term; the policy should not
  learn to idle because penalties dominate.
- Normalize reward once, centrally: either `reward_scale = 1 / mean_abs_episode_cost` (data
  statistic) or `VecNormalize(norm_reward=True, clip_reward=10)`. Do not stack both.

Starting weights: `c_deg` equivalent to ~25–100 RON per MWh of throughput, `λ_viol` small and
in RON (e.g. 5 RON per MWh clipped), `λ_switch = 0` initially. Tune on validation days only.

Because buy and sell are the same PZU series, import and export prices are identical at each
instant; with 90.25% round-trip efficiency the agent cannot profit from a buy/sell spread and
must create value from price differences across time plus PV self-consumption. Charging from
PV is priced correctly by the cash flow: the forgone export appears as lost revenue.

---

## 5. Real data: sources, ingestion, validation

Training uses real data only. Synthetic series are kept solely as deterministic unit-test
fixtures (a handful of hand-checkable steps), never for training.

| Series | Source | Native resolution | Units | Status |
|---|---|---|---|---|
| Sell price | OPCOM PZU report (linked page) | 15 min | RON/MWh | done (2026-11-07) |
| Buy price | same OPCOM PZU series | 15 min | RON/MWh | done (2026-11-07) |
| Price forecast | actual PZU, published D-1 | 15 min | RON/MWh | done (causal) |
| Consumer load | ENTSO-E RO actual total load, scaled | 15 min where available | MW | **open** (scaling) |
| Load forecast | ENTSO-E RO day-ahead load forecast, scaled | hourly / 15 min | MW | **open** |
| PV production | farm config from the form → PVGIS; metered CSV optional | 15 min / hourly | MW | **open** (seed config) |
| PV forecast | Open-Meteo archived NWP + same PV model, or vendor | hourly | MW | **open** |

### 5.1 OPCOM prices
- The linked report is the Day-Ahead Market (PZU), not intraday. Buy and sell both use it.
- Implemented endpoint:
  `https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv/DD/MM/YYYY/ro?resolution=15`.
- Implemented in `src/battery_rl/data/opcom.py`, CLI `scripts/download_opcom.py`. Verified for
  2026-01-01 → 2026-11-07: 311 days, 29,856 interval rows, 0 failures. DST days yield 92
  (29 Mar) and 100 (25 Oct) intervals; all other days 96. Negative prices are preserved.
- Each trading day has 96 quarter-hour clearing prices; export formats include PT15 CSV/XML.
  The scraper fetches one trading day at a time, rate-limited. Raw files are stored unchanged
  under `artifacts/data/raw/opcom/YYYY/MM/DD/` with a manifest (URL, SHA-256, interval count).
- Prices are RON/MWh. Keep RON internally; convert only for display.
- The price forecast is the actual PZU curve for the delivery day, published the day before,
  so it is legitimately available at decision time.
- Do not put PZU traded volume in the agent state: it is market-wide and not actionable for a
  price taker.

### 5.2 Consumer load (open)
- Requirement: national dataset only, never synthetic. Use ENTSO-E RO actual total load.
- Scale the national curve to the site with a factor derived from annual MWh or peak MW.
  Until the site size is known, use an explicit placeholder peak (e.g. 1 MW) recorded in the
  data card.
- Demand forecast: ENTSO-E RO day-ahead load forecast, scaled by the same factor.
- Open item: the scaling factor, and whether the national shape is an acceptable stand-in for
  this consumer. Track until real site data arrives.

### 5.3 PV production (config-driven)
- The farm configuration captured by the Phase 11 form supplies location, kWp, inverter AC
  rating, tilt, azimuth and tracking. That configuration is the training config as well.
- If metered 15-min generation exists, load it instead.
- Otherwise use PVGIS (SARAH3/ERA5) irradiance at the configured coordinates with a PV model;
  hourly output interpolated to 15 min and documented. Snapshot the fetched series into the
  dataset so training and evaluation are reproducible without live PVGIS calls.
- PV forecast: archived numerical weather forecasts (Open-Meteo Historical Forecast API) run
  through the same PV model, or a commercial vendor. If neither is available, forecast quality
  is the only modelled component left and must be labelled as such in the report.

### 5.4 Alignment, gaps, splits
- Store UTC, expose Europe/Bucharest; DST days have 92/100 quarter-hours. Keep the real
  intervals rather than fabricating 96-step days, and document the day-length variation.
- Never forward-fill a gap silently: mark gaps, exclude affected days from training, and
  report coverage.
- Chronological blocked split with a frozen test set; each split must span multiple seasons
  and price regimes. All series share identical timestamps.
- Produce a data card in `artifacts/data/` with source URLs, download dates, licenses,
  transformations, scaling factors, gap list, and split dates.

### 5.5 Validation checks
- Row counts and interval regularity per day; identical timestamps across series.
- Price range sanity (including any genuine negative prices); load and PV non-negative.
- No NaNs introduced by joins; validation failures fail the build instead of silently dropping
  rows.
- Provenance: every processed row traces back to a raw file.

---

## 6. Baselines

Implement all strategies against one interface:

```python
class Strategy(Protocol):
    def act(self, obs, info) -> int: ...
    def reset(self, seed=None) -> None: ...   # optional state for stateful rules
```

| Strategy | Behavior |
|---|---|
| `IdleStrategy` | always HOLD (IDEA "Strategy 1 – fără optimizare") |
| `RuleBasedStrategy` | charge if `pv > demand` and SoC < max; discharge if `demand > pv` and SoC > min; else hold ("Strategy 2") |
| `PriceThresholdStrategy` *(optional)* | charge when price below a daily quantile, discharge when above; useful third reference |
| `RLStrategy` | wraps a loaded PPO model, deterministic `predict` |
| `OracleLP` *(stretch)* | perfect-foresight linear program, gives the upper bound |

The rule-based strategy must use a deadband (e.g. only act if surplus/deficit exceeds 0.1 MW)
to avoid unrealistic chattering caused by the discrete 2 MW action. All strategies are run
through the same evaluation loop with identical episodes and seeds so comparisons are fair.

---

## 7. Agent and training

- Algorithm: PPO from `stable-baselines3` (IDEA choice), `MlpPolicy`.
- Architecture: `net_arch=[128, 128]` (raise to 256 only if learning stalls).
- Starting hyperparameters: `n_steps=2048`, `batch_size=256`, `n_epochs=10`, `lr=3e-4`,
  `gamma=0.995`, `gae_lambda=0.95`, `clip_range=0.2`, `ent_coef=0.005`, `vf_coef=0.5`,
  `max_grad_norm=0.5`. Gamma matters: at 96 steps/day, `0.995` discounts the day end to
  ~0.62, `0.999` to ~0.91. Start at 0.995, sweep 0.99–0.999 on validation.
- Wrappers: `Monitor`, `VecNormalize(norm_obs=False, norm_reward=True, clip_reward=10)`
  around a `DummyVecEnv`/`SubprocVecEnv` (CPU only, 4–8 envs). Observations are already
  normalized inside the env; do not double-normalize.
- Seeding: seed Python, NumPy, PyTorch, env, and VecEnv. Store the seed in the run metadata.
- Checkpointing: `EvalCallback` on 20 held-out val days every 20k steps, save best model,
  save VecNormalize statistics next to it. TensorBoard logging into `artifacts/runs/<name>/`.
- Total budget: 300k–1M timesteps, expected minutes on CPU. Stop when validation reward
  plateaus (patience ~3 eval cycles).
- Before the long run: an *overfit test* on a single fixed day must reach near-oracle cost.
  If PPO cannot overfit one day, fix the environment/reward before tuning anything else.
- Optional head-to-head: DQN with the same env, only if PPO is unconvincing and time permits.

Training is only considered finished when the model file and its normalization statistics are
saved together and reproducible from config + seed.

### Single-site vs fleet policy

- Default for this project: one policy per site/configuration. The environment is fully
  config-driven, so training for another farm is a config change, not a code change.
- Scale invariance: if PV, load, battery power and capacity scale together and every
  observation is normalized (PV/peak, load/peak, SoC fraction, power as a fraction of max), the
  normalized MDP is identical across sizes and one policy can serve both.
- What breaks a shared policy: different battery/PV and load/PV ratios, different weather
  regimes, tariffs, grid limits, or battery parameters. Either condition the observation on
  those parameters or retrain per site.
- Fleet option (only if PPC needs it): one policy trained with parameter domain randomization
  and ratio features in the observation, evaluated zero-shot on held-out farms and compared
  against per-farm fine-tuning. This is a Phase 10 extension, not required for the demo.
- Training cost is small (small MLP, 300k–1M steps on CPU); the real per-farm cost is data
  acquisition, validation and evaluation.
- If a site has deterministic day-ahead prices and simple constraints, an LP/MPC may match or
  beat RL without training; RL is justified by forecast uncertainty and richer constraints.

---

## 8. Evaluation harness and metrics

`eval/runner.py` runs any `Strategy` for N episodes on a given split/scenario, collecting per-
step records and per-episode metrics. `eval/report.py` aggregates into tables and plots.

Metric definitions (all from `info`, computed once, reused everywhere):

| Metric | Formula |
|---|---|
| Import cost | `Σ price_buy · import · dt` |
| Export revenue | `Σ price_sell · export · dt` |
| Net energy cost | import cost − export revenue (primary KPI, lower is better) |
| Renewable utilization | `1 − curtailed / available_pv` |
| Self-consumption ratio | `(pv_to_load + pv_to_battery) / available_pv` |
| Wasted energy | total curtailed PV (MWh) |
| Battery throughput | `Σ (charge_energy + discharge_energy)` (MWh) |
| Equivalent full cycles | `throughput / (2 · C)` |
| Degradation estimate | `c_deg · throughput` (same linear model as reward) |
| Constraint violations | sum of clipped MW·h; count of steps with clipping |
| Grid import / export | MWh each |
| Mean SoC / SoC range | per episode |

PV allocation convention for reporting (PV and grid energy are physically indistinguishable at
the battery, so pick one convention and apply it everywhere): PV serves load first, then
battery charging, then export, then curtailment; any remaining charge demand is met from the
grid. This makes `pv_to_load` and `pv_to_battery` well-defined without affecting the economics.

With the export limit disabled, `curtailed = 0`, so renewable utilization is always 1 and
wasted energy always 0. Both remain in the report for IDEA compliance but do not discriminate
between strategies; the informative metrics are net energy cost, export revenue,
self-consumption ratio, throughput/cycles, and violations. If an `export_limit` is configured
later, both become meaningful again.

Net energy cost is energy-only: it excludes retail supply margin, network tariffs, taxes and
imbalance costs, because buy and sell are both the PZU price by decision. Do not present it as
the full retail bill.

Evaluation protocol:

1. Fixed evaluation seeds; deterministic policy (`model.predict(..., deterministic=True)`).
2. Run all four strategies (idle, rule-based, optional price-threshold, RL) on the **same**
   held-out episodes.
3. Report `mean ± std` over episodes, plus `% improvement vs idle` and `% improvement vs
   rule-based`.
4. Break results down by data-derived regime (high-price days, low-price days, volatile days,
   cloudy weeks, weekends/holidays), not just overall, to expose where RL wins or fails.
5. Robustness pass: evaluate RL with the archived-NWP PV forecast and with a degraded/naive
   forecast; a policy that only works with perfect foresight is not a valid result.
6. Track a *business* check: RL must reduce net cost after degradation cost is included; do
   not report only throughput gains.

Plots produced: net cost by strategy, SoC trajectory over a sample day, power flows
(PV/demand/charge/discharge/grid), price vs. action timeline, learning curve.

---

## 9. Workflow phases (build order)

### Phase 0 — Setup and locked decisions
- [ ] Fill the open data items in section 1 (site coordinates/capacity, load scaling, date
      range, data delivery).
- [ ] Confirm OPCOM terms for automated downloading and record the attribution requirement.
- [ ] Confirm demo scope (Phase 11 in or out).
- [ ] Create `RL/pyproject.toml`, package skeleton, `configs/*.yaml`, `config.py`, `seeding.py`.
- [x] Add `RL/artifacts/` to `.gitignore`.
- [ ] One command installs and an import smoke test passes (`uv run python -c "import battery_rl"`).
- **Exit:** skeleton runs, configs load and validate, no hard-coded constants.

### Phase 1 — Real data ingestion and validation
- [x] `data/opcom.py`: ingest PZU 15-min prices (buy = sell), raw files + provenance.
      2026-01-01 → 2026-11-07 scraped: 311 days, 29,856 interval rows, 0 failures.
- [x] `scripts/download_opcom.py`: CLI scraper (implemented, rate-limited, idempotent).
- [ ] `data/entsoe.py`: national RO load and day-ahead load forecast, scaled to the site
      (placeholder factor until the site size is known).
- [ ] `data/pv.py`: metered PV loader or PVGIS model driven by the farm configuration (the
      same config the Phase 11 form produces); snapshot fetched series into the dataset.
- [ ] `data/forecasts.py`: actual PZU as price forecast; archived NWP for PV; scaled ENTSO-E
      forecast for load.
- [ ] `scripts/build_dataset.py`: align, validate, split, write data card and overview plots.
- [x] `tests/test_opcom.py` (DST mapping, URL, parser, interval validation).
- [ ] `tests/test_data.py` (interval regularity, alignment, gap handling, split disjointness,
      no leakage).
- **Exit:** an aligned, validated real dataset spanning multiple seasons, with a data card and
  every processed row traceable to a raw source.

### Phase 2 — Environment core (battery + balance)
- [ ] `battery.py` pure functions: feasible power, SoC update, efficiencies.
- [ ] `env.py`: Gymnasium API, bus balance, optional `export_limit` (default `None`), `info`.
- [ ] Unit tests: SoC bounds, round-trip efficiency loss, energy conservation identity.
- [ ] `gymnasium.utils.env_checker.check_env` passes.
- **Exit:** random policy runs 96 steps with valid SoC and conserved energy every step.

### Phase 3 — Observations and forecasts
- [ ] `observations.py`: state vector, fixed normalization, time encoding.
- [ ] Wire forecast arrays from the dataset into the observation; verify horizon alignment.
- [ ] Test: obs shape/dtype/bounds, no future leakage outside the forecast block.
- **Exit:** `reset`/`step` return consistent `Box` observations in `[-1, 1]`.

### Phase 4 — Reward and terminal valuation
- [ ] `reward.py`: economic term, degradation term, violation term, terminal SoC value.
- [ ] Central reward scaling; single normalization path (env or VecNormalize, not both).
- [ ] Test: with penalties zeroed, episode reward equals negative net cash flow exactly.
- **Exit:** reward accounting verified on a hand-computed mini episode.

### Phase 5 — Baselines
- [ ] `strategies/base.py`, `idle.py`, `rule_based.py`, optional `price_threshold.py`.
- [ ] Deadband on the rule-based action to avoid chattering.
- [ ] Run each for 10 episodes end-to-end through the env.
- **Exit:** idle produces zero throughput; rule-based produces the expected qualitative
  behavior (charge at midday surplus, discharge at deficit).

### Phase 6 — Evaluation harness and metrics
- [ ] `metrics.py`, `runner.py`, `report.py`.
- [ ] Hand-computed tiny episode test for every metric.
- [ ] CLI `scripts/evaluate.py` compares idle vs rule-based and writes a table + plots.
- **Exit:** repeatable comparison table with per-scenario breakdown for the baselines.

### Phase 7 — PPO pipeline and overfit test
- [ ] `train_ppo.py` + callbacks (eval, best checkpoint, tensorboard, vecnormalize save).
- [ ] Smoke run 20k steps; check logs, checkpoint reload, deterministic evaluation.
- [ ] Overfit one fixed day; verify learned cost approaches the oracle/ideal for that day.
- **Exit:** learning loop works end-to-end and the policy actually optimizes the signal.

### Phase 8 — Train and tune
- [ ] Train 300k–1M steps on train split, evaluate on val.
- [ ] Tune reward weights, `gamma`, `c_deg`, and action granularity only on validation.
- [ ] Confirm RL beats rule-based on validation net cost after degradation; if not, diagnose
      with per-step action traces before changing hyperparameters.
- **Exit:** stable learning curve, RL ≥ rule-based on validation, best model + stats saved.

### Phase 9 — Final evaluation and report
- [ ] Freeze the model; run on the held-out test days and all scenarios, all strategies.
- [ ] Produce the IDEA metrics table with uncertainty and per-scenario breakdown.
- [ ] Robustness across forecast sources (archived NWP vs naive forecast).
- [ ] `artifacts/reports/report.md` with plots and a short conclusion.
- **Exit:** results are reproducible from a documented command; claims match measured numbers.

### Phase 10 — Extensions (only if time remains)
- [ ] Continuous action space (`Box(-1, 1)`), compare against discrete.
- [ ] DQN head-to-head (IDEA mention).
- [ ] Perfect-foresight LP oracle for an upper bound.
- [ ] Fleet policy: parameter domain randomization + ratio features, evaluated zero-shot versus
      per-farm fine-tuning.
- [ ] Additional sites: repeat the pipeline for another farm configuration.
- [ ] Finer discrete action levels for smoother operation.

### Phase 11 — Farm parameter form and demo integration (optional, after core is done)

Goal: let a user describe a farm in a browser and run the simulation with it, without editing
YAML. The form is also where the per-site nature of the policy must be made explicit:
changing farm parameters does not retrain the agent.

**Form fields** (validated server-side against one shared schema):
- Location: latitude/longitude or city preset; used to fetch PVGIS data (cached).
- PV: installed kWp, inverter AC rating, tilt, azimuth, tracking.
- Battery: capacity (MWh), max charge/discharge (MW), SoC min/max, efficiencies.
- Consumer: peak MW / annual MWh, or an uploaded 15-min load CSV; "no local consumer" option.
- Grid: export limit (default none), import limit.
- Simulation: date range within the available PZU history, strategy, initial SoC.

**Two modes, clearly labelled:**
- **Trained farm** — the configuration matches (by canonical hash) an entry in
  `artifacts/models/registry.json`; the RL strategy is enabled and the model plus VecNormalize
  statistics are loaded from that entry.
- **Custom farm** — no matching model. Baselines (idle / rule-based) run normally; the RL
  option is disabled with an explanation that the policy is site-specific. Optional stretch:
  queue an asynchronous training job and notify when a model exists.

**Backend**
- [ ] `backend/app/schemas/farm.py` — farm-config schema; mirrors `RL/configs/env.yaml`.
- [ ] `backend/app/api/routes/simulate.py` — `POST /api/simulate` (config + dates + strategy),
      `GET /api/models` (registry entries), `GET /api/scenarios`.
- [ ] `backend/app/services/battery_sim.py` — run the RL env in-process, never retrain at
      request time; reuse the RL metrics code.
- [ ] `RL/artifacts/models/registry.json` — config hash → model zip, VecNormalize stats,
      trained-at timestamp, data window, validation metrics.
- [ ] PVGIS lookup with timeouts, cache keyed by rounded coordinates, and a clear error state.

**Frontend** (use the existing React app; a standalone static HTML is only a time-saving
fallback, since it duplicates the template)
- [ ] `frontend/src/pages/Simulator.tsx` — parameter form, preset selector, client validation.
- [ ] Results: SoC/power/price charts, trajectory table, metrics comparison.
- [ ] Types mirroring the backend schema in `frontend/src/types/`.
- [ ] Optional: "Download as env.yaml" so the form doubles as a training-config builder.

**Rules**
- Do not silently run a model trained on a different configuration; that is the central
  generalization trap from section 7.
- Do not train inside the request path. Training stays a CLI job; a UI-triggered job queue is
  a stretch goal only.
- Validate ranges (SoC min < max, power > 0, coordinates, date range) and return actionable
  errors.
- **Exit:** the form reproduces Phase 9 numbers for a registered farm; for a custom farm it
  runs the baselines and explains the RL limitation.

---

## 10. Definition of done

- Environment passes `check_env`, all unit tests pass, energy conservation holds.
- Training is reproducible from `config + seed`; model and normalization stats are saved.
- On held-out real days, the RL agent beats both IDLE and the rule-based baseline on net
  energy cost (target: ≥ 5% vs rule-based; otherwise document the gap and its cause).
- All IDEA metrics are reported for all strategies, per scenario, with means and spreads.
- `RL/README.md` documents installation, data generation, training, evaluation, and where
  artifacts live, so a teammate can reproduce everything with three commands.
- No claim is made from training data; only from the held-out test split.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Reward hacking (agent idles, or cycles to game a shaping term) | Primary reward is net cash; keep penalties < 10% of economic term; validate against cost metrics, not reward value |
| PPO fails to learn | Short overfit test on one day first; normalize obs/reward; large gamma; fall back to DQN if needed |
| Real data gaps, DST shifts, or misalignment | Explicit gap marking, per-day interval checks, fail-fast joins, coverage report in the data card |
| Load scaling distorts the economics | Record the scaling factor; sanity-check daily energy vs site size; replace with site data when available |
| No export limit makes utilization/wasted metrics constant | Report them for IDEA compliance but base conclusions on net cost, revenue, self-consumption and battery metrics; keep optional `export_limit` |
| OPCOM access or terms change | Cache raw downloads, store provenance, keep a manual CSV fallback path |
| Forecast leakage / unrealistic information | Only the forecast block sees future; horizon-dependent noise; robustness evaluation |
| Episode boundary effects | Random starts + terminal SoC valuation; whole-day alignment for reported results |
| Discrete full-power actions cause chattering | Rule-based deadband; optional finer action levels; optional switch penalty |
| Evaluation leakage | Strict day-based split; freeze the test set; fixed seeds across strategies |
| Running out of time | Phases 0–9 are the minimum deliverable; Phase 10–11 are explicitly optional and only start after a complete report exists |

---

## 12. Suggested sequencing and ownership

Two parallel workstreams, converging at Phase 6 and Phase 9:

- **Simulator track (Phases 1–4):** data generation, battery physics, environment, reward.
  This is the critical path; the quality of everything else depends on it.
- **Experiment track (Phases 5–8):** baselines, evaluation harness, PPO pipeline. Can start
  against a stub env and be wired to the real env as soon as Phase 2 exits.

Order for the next session: Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 →
Phase 6 → Phase 7 → Phase 8 → Phase 9, with the overfit test in Phase 7 treated as a hard
gate before any long training run.
