# PLAN — RL Battery Energy Optimization

Build plan for the component described in `IDEA.md`: a simulated PV park + battery + grid
environment, a PPO agent that decides when to charge / discharge / hold, the two baseline
strategies, and an evaluation harness that compares them on unseen days.

Scope: a standalone Python package under `RL/` (no backend/frontend dependency for the core
work). Dashboard/API integration is an optional final phase.

---

## 0. What we are building

```
synthetic data (PV, demand, prices, forecasts)
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

Values from `IDEA.md` are fixed. Values marked *(proposed)* are not in the document and must
be confirmed or tuned in Phase 0. Keep all of them in one config file, never hard-coded.

| Parameter | Value | Source |
|---|---|---|
| Episode length | 24 h = 96 steps | IDEA |
| Step duration | 15 min (`dt = 0.25 h`) | IDEA |
| Battery capacity | 10 MWh | IDEA |
| Max charge / discharge power | 2 MW / 2 MW | IDEA |
| SoC limits | 10% – 90% | IDEA |
| Charge / discharge efficiency | 95% / 95% | IDEA |
| PV park peak power | 6 MWp *(proposed)* | missing from IDEA |
| Peak demand | ~3–4 MW *(proposed)* | missing from IDEA |
| Grid export limit | 4 MW *(proposed, configurable)* | missing from IDEA |
| Grid import limit | unlimited *(proposed)* | not specified |
| Buy price | synthetic time-of-use, 20–200 EUR/MWh | missing from IDEA |
| Sell price | 60% of buy price *(proposed)* | not specified |
| Forecast horizon | next 4 h = 16 steps (`K=16`) | state spec |
| Train / val / test | 70 / 10 / 10 synthetic days, disjoint | evaluation spec |
| Training timesteps | 300k–1M PPO steps | SB3 practical range |

Why export limit matters: without it, all surplus PV is sold and "wasted energy" is always
zero, so one of the IDEA metrics becomes meaningless. With a limit, the battery has a second
job (absorbing otherwise-curtailed PV), which matches the IDEA intent.

Open questions to settle in Phase 0 (defaults above are used if unanswered):
1. Is there real data available (PVGIS / ENTSO-E / utility data), or synthetic only?
2. Should the demo show the live simulation in the dashboard (Phase 11) or is a report enough?
3. Currency and tariff structure (flat vs day-ahead vs time-of-use)?
4. Is a continuous-action version required, or is the discrete version the deliverable?

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
    generate_data.py       # CLI: build synthetic dataset + splits + stats plots
    train.py               # CLI: PPO training
    evaluate.py            # CLI: compare strategies, write metrics table
    make_report.py         # CLI: plots + report.md from evaluation results
  src/battery_rl/
    __init__.py
    config.py              # dataclasses/pydantic models for all YAML configs
    seeding.py             # seed everything (random, numpy, torch, gym)
    data/
      generate.py          # synthetic PV / demand / price / forecasts
      scenarios.py         # weather + market scenario definitions
      dataset.py           # loading, splits, EpisodeSampler
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
  artifacts/               # gitignored
    data/
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

- Resolution 15 min, episode = 96 steps. Dataset stored at 15-min resolution and indexed by
  step.
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

4. Import / export, respecting limits:

   ```
   import = min(max(P_net, 0), import_limit)
   export = min(max(−P_net, 0), export_limit)
   ```

5. Any surplus that exceeds the export limit is curtailed:

   ```
   curtailed_energy_t = max(−P_net − export_limit, 0) · dt      [MWh]
   ```

   This is derived from the balance, not tracked separately, so curtailment can never be
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

where `curtailment_power = max(−P_net − export_limit, 0)`.

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

Starting weights: `c_deg` equivalent to ~5–20 EUR per MWh of throughput, `λ_viol` small
(e.g. 1 EUR per MW·h clipped), `λ_switch = 0` initially. Tune on validation days only.

---

## 5. Synthetic data and scenarios

Generator script produces one long time series plus named scenario masks, then splits it into
disjoint day ranges.

1. **Timestamps**: 1 year at 15-min resolution (or 120 days for speed). Save
   `data/{split}.csv` and a combined `data/meta.json`.
2. **PV**: seasonal daylight length + `sin^k` diurnal shape × AR(1) cloud attenuation
   (0.15–1.0). Capacity 6 MWp. Occasional fully overcast days and a storm scenario.
3. **Demand**: base load + morning (~08:00) and evening (~19:00) Gaussian peaks, weekday /
   weekend factor, AR(1) noise, clipped to [0, 4] MW.
4. **Prices**: buy price = base + morning peak + evening peak + noise, clipped to
   [20, 200] EUR/MWh; sell price = 0.6 × buy (always ≤ buy, so importing to re-export is
   never profitable without storage). Optional scenario: high volatility / price spikes.
5. **Forecasts**: precomputed arrays for each `t` as described in 3.4, in three noise modes.
6. **Scenarios**: named combinations, e.g. `sunny`, `cloudy`, `mixed`, `storm`,
   `high_price`, `low_price`, `heatwave` (high demand + high PV). Store the scenario id per
   day so evaluation can report per scenario.
7. **Splits**: train = first 70% of days, val = next 15%, test = last 15%, split by whole
   days, never by rows. Verify no timestamp overlap in a test.
8. **Sanity plots** (matplotlib): one week of PV/demand/price, distributions, daily energy
   totals; save into `artifacts/reports/data_overview.png`.

Design goal: the dataset must make the battery useful (midday PV surplus, evening demand
peak, price spread large enough to beat efficiency losses) but not trivial.

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

Evaluation protocol:

1. Fixed evaluation seeds; deterministic policy (`model.predict(..., deterministic=True)`).
2. Run all four strategies (idle, rule-based, optional price-threshold, RL) on the **same**
   held-out episodes.
3. Report `mean ± std` over episodes, plus `% improvement vs idle` and `% improvement vs
   rule-based`.
4. Break results down per scenario (`sunny`, `cloudy`, `storm`, `high_price`, ...), not just
   overall, to expose where RL wins or fails.
5. Robustness pass: evaluate RL under the three forecast-noise modes. A policy that only
   works with perfect forecasts is not a valid result.
6. Track a *business* check: RL must reduce net cost after degradation cost is included; do
   not report only throughput gains.

Plots produced: net cost by strategy, SoC trajectory over a sample day, power flows
(PV/demand/charge/discharge/grid), price vs. action timeline, learning curve.

---

## 9. Workflow phases (build order)

### Phase 0 — Setup and locked decisions
- [ ] Resolve the open questions in section 1 (real vs synthetic data, tariff model, demo scope).
- [ ] Create `RL/pyproject.toml`, package skeleton, `configs/*.yaml`, `config.py`, `seeding.py`.
- [ ] Add `artifacts/` to `.gitignore`.
- [ ] One command installs and an import smoke test passes (`uv run python -c "import battery_rl"`).
- **Exit:** skeleton runs, configs load and validate, no hard-coded constants.

### Phase 1 — Synthetic data generator
- [ ] Implement PV, demand, price, forecast generation; scenario definitions; day-based splits.
- [ ] CLI `scripts/generate_data.py` writes CSVs + meta with a fixed seed.
- [ ] Sanity plots and distribution checks; assert no NaNs and no split overlap.
- [ ] `tests/test_data.py` (determinism, split disjointness, forecast alignment).
- **Exit:** a deterministic dataset exists and looks physically plausible for a full week.

### Phase 2 — Environment core (battery + balance)
- [ ] `battery.py` pure functions: feasible power, SoC update, efficiencies.
- [ ] `env.py`: Gymnasium API, bus balance, import/export limits, curtailment, `info`.
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
- [ ] Robustness across forecast-noise modes.
- [ ] `artifacts/reports/report.md` with plots and a short conclusion.
- **Exit:** results are reproducible from a documented command; claims match measured numbers.

### Phase 10 — Extensions (only if time remains)
- [ ] Continuous action space (`Box(-1, 1)`), compare against discrete.
- [ ] DQN head-to-head (IDEA mention).
- [ ] Perfect-foresight LP oracle for an upper bound.
- [ ] Real data adapter (PVGIS solar, ENTSO-E prices, real demand profile).
- [ ] Finer discrete action levels for smoother operation.

### Phase 11 — Demo integration (optional, after core is done)
- [ ] `POST /api/simulate` endpoint runs a chosen strategy over a scenario and returns the
      full trajectory (timestamps, PV, demand, price, SoC, power flows, cash flow, metrics).
- [ ] `GET /api/scenarios` and a comparison endpoint for the metrics table.
- [ ] Load the trained PPO model once at startup from `artifacts/models/`.
- [ ] Frontend page: scenario picker, strategy selector, SoC/power/price charts, metrics table.
- **Exit:** the dashboard reproduces the Phase 9 numbers; the model is a single documented
  artifact path, not retrained at request time.

---

## 10. Definition of done

- Environment passes `check_env`, all unit tests pass, energy conservation holds.
- Training is reproducible from `config + seed`; model and normalization stats are saved.
- On held-out synthetic days, the RL agent beats both IDLE and the rule-based baseline on net
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
| Synthetic data too easy or battery useless | Verify there is a price spread and midday surplus; compare rule-based vs idle before training |
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
