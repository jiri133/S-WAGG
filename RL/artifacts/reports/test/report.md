# Evaluation report — test

## Scope

- Split: **test**
- Farm: **seed-demo** (`s=1`, checksum `2fb404feebe8…`)
- Repeats per day: **3**
- Days: **36**
- Runs: **864**
- Per-day CSV: `results.csv`
- Skipped incomplete days: 2026-10-02

Score is the full merchant objective: −cash flow − degradation − violations +
terminal value. Net cost is cash flow only (negative = revenue).

MPC and OracleLP have identical actions here: with known D-1 prices, zero site
demand and no export limit, the dispatch LP is price-only. The oracle differs
only in using actual future PV for the reported objective; it is the upper bound.

## By strategy and mode

| Strategy | Mode | Runs | Days | Score mean | Score std | Net cost mean | Export rev mean | Throughput mean | Cycles mean | Self-cons mean |
|---|---|---|---|---|---|---|---|---|---|---|
| idle | block | 108 | 36 | 25,922.19 | 14,440.11 | -19,540.41 | 19,540.41 | 0.000 | 0.000 | 0.000 |
| idle | step | 108 | 36 | 25,922.19 | 14,440.11 | -19,540.41 | 19,540.41 | 0.000 | 0.000 | 0.000 |
| mpc | block | 108 | 36 | 31,253.01 | 15,784.33 | -30,034.96 | 36,171.93 | 22.607 | 1.130 | 0.292 |
| oracle_lp | block | 108 | 36 | 31,253.01 | 15,784.33 | -30,034.96 | 36,171.93 | 22.607 | 1.130 | 0.292 |
| price_threshold | block | 108 | 36 | 30,220.82 | 15,616.20 | -28,591.09 | 34,499.72 | 18.977 | 0.949 | 0.182 |
| price_threshold | step | 108 | 36 | 30,220.82 | 15,616.20 | -28,591.09 | 34,499.72 | 18.977 | 0.949 | 0.182 |
| rule_based | block | 108 | 36 | 26,007.27 | 14,677.20 | -16,214.49 | 16,538.28 | 4.620 | 0.231 | 0.433 |
| rule_based | step | 108 | 36 | 26,807.25 | 15,537.30 | -26,216.15 | 26,216.15 | 14.765 | 0.738 | 0.454 |

## By regime

Regimes are split terciles: high/low mean price, high price volatility, high/low
daily PV energy, plus weekends. A day can be in several regimes; `all` is the
full split.

| Regime | Strategy | Mode | Runs | Score mean | Net cost mean | Export rev mean | Throughput mean | Self-cons mean |
|---|---|---|---|---|---|---|---|---|
| all | idle | block | 108 | 25,922.19 | -19,540.41 | 19,540.41 | 0.000 | 0.000 |
| all | idle | step | 108 | 25,922.19 | -19,540.41 | 19,540.41 | 0.000 | 0.000 |
| all | mpc | block | 108 | 31,253.01 | -30,034.96 | 36,171.93 | 22.607 | 0.292 |
| all | oracle_lp | block | 108 | 31,253.01 | -30,034.96 | 36,171.93 | 22.607 | 0.292 |
| all | price_threshold | block | 108 | 30,220.82 | -28,591.09 | 34,499.72 | 18.977 | 0.182 |
| all | price_threshold | step | 108 | 30,220.82 | -28,591.09 | 34,499.72 | 18.977 | 0.182 |
| all | rule_based | block | 108 | 26,007.27 | -16,214.49 | 16,538.28 | 4.620 | 0.433 |
| all | rule_based | step | 108 | 26,807.25 | -26,216.15 | 26,216.15 | 14.765 | 0.454 |
| high_price | idle | block | 36 | 23,604.82 | -15,948.17 | 15,948.17 | 0.000 | 0.000 |
| high_price | idle | step | 36 | 23,604.82 | -15,948.17 | 15,948.17 | 0.000 | 0.000 |
| high_price | mpc | block | 36 | 28,190.64 | -24,930.80 | 34,452.88 | 21.547 | 0.259 |
| high_price | oracle_lp | block | 36 | 28,190.64 | -24,930.80 | 34,452.88 | 21.547 | 0.259 |
| high_price | price_threshold | block | 36 | 27,087.81 | -23,777.92 | 32,100.58 | 16.347 | 0.090 |
| high_price | price_threshold | step | 36 | 27,087.81 | -23,777.92 | 32,100.58 | 16.347 | 0.090 |
| high_price | rule_based | block | 36 | 23,317.06 | -11,708.85 | 12,109.70 | 3.679 | 0.587 |
| high_price | rule_based | step | 36 | 23,247.89 | -22,242.22 | 22,242.22 | 11.776 | 0.523 |
| low_price | idle | block | 36 | 33,769.13 | -28,633.75 | 28,633.75 | 0.000 | 0.000 |
| low_price | idle | step | 36 | 33,769.13 | -28,633.75 | 28,633.75 | 0.000 | 0.000 |
| low_price | mpc | block | 36 | 41,059.43 | -41,135.30 | 43,930.06 | 24.407 | 0.250 |
| low_price | oracle_lp | block | 36 | 41,059.43 | -41,135.30 | 43,930.06 | 24.407 | 0.250 |
| low_price | price_threshold | block | 36 | 40,032.59 | -39,840.02 | 41,710.41 | 20.632 | 0.216 |
| low_price | price_threshold | step | 36 | 40,032.59 | -39,840.02 | 41,710.41 | 20.632 | 0.216 |
| low_price | rule_based | block | 36 | 34,396.48 | -26,779.91 | 26,888.34 | 6.133 | 0.165 |
| low_price | rule_based | step | 36 | 36,419.40 | -36,303.96 | 36,303.96 | 18.996 | 0.266 |
| volatile | idle | block | 36 | 29,495.80 | -23,545.06 | 23,545.06 | 0.000 | 0.000 |
| volatile | idle | step | 36 | 29,495.80 | -23,545.06 | 23,545.06 | 0.000 | 0.000 |
| volatile | mpc | block | 36 | 37,687.03 | -36,526.24 | 41,553.70 | 23.844 | 0.256 |
| volatile | oracle_lp | block | 36 | 37,687.03 | -36,526.24 | 41,553.70 | 23.844 | 0.256 |
| volatile | price_threshold | block | 36 | 36,240.67 | -34,989.14 | 38,457.54 | 18.668 | 0.149 |
| volatile | price_threshold | step | 36 | 36,240.67 | -34,989.14 | 38,457.54 | 18.668 | 0.149 |
| volatile | rule_based | block | 36 | 30,042.54 | -21,608.00 | 21,786.40 | 5.640 | 0.285 |
| volatile | rule_based | step | 36 | 31,761.21 | -31,362.90 | 31,362.90 | 16.749 | 0.340 |
| sunny | idle | block | 36 | 39,280.56 | -33,765.88 | 33,765.88 | 0.000 | 0.000 |
| sunny | idle | step | 36 | 39,280.56 | -33,765.88 | 33,765.88 | 0.000 | 0.000 |
| sunny | mpc | block | 36 | 46,808.86 | -46,514.27 | 49,110.42 | 23.889 | 0.214 |
| sunny | oracle_lp | block | 36 | 46,808.86 | -46,514.27 | 49,110.42 | 23.889 | 0.214 |
| sunny | price_threshold | block | 36 | 45,541.56 | -44,981.62 | 46,940.10 | 19.082 | 0.160 |
| sunny | price_threshold | step | 36 | 45,541.56 | -44,981.62 | 46,940.10 | 19.082 | 0.160 |
| sunny | rule_based | block | 36 | 39,754.41 | -31,214.65 | 31,281.50 | 6.081 | 0.121 |
| sunny | rule_based | step | 36 | 42,059.92 | -41,894.65 | 41,894.65 | 19.657 | 0.217 |
| cloudy | idle | block | 36 | 11,357.56 | -4,277.22 | 4,277.22 | 0.000 | 0.000 |
| cloudy | idle | step | 36 | 11,357.56 | -4,277.22 | 4,277.22 | 0.000 | 0.000 |
| cloudy | mpc | block | 36 | 15,259.92 | -12,956.25 | 22,640.63 | 20.146 | 0.307 |
| cloudy | oracle_lp | block | 36 | 15,259.92 | -12,956.25 | 22,640.63 | 20.146 | 0.307 |
| cloudy | price_threshold | block | 36 | 14,293.74 | -11,728.76 | 20,814.75 | 17.897 | 0.184 |
| cloudy | price_threshold | step | 36 | 14,293.74 | -11,728.76 | 20,814.75 | 17.897 | 0.184 |
| cloudy | rule_based | block | 36 | 11,003.69 | -1,142.02 | 1,730.53 | 3.436 | 0.819 |
| cloudy | rule_based | step | 36 | 10,735.00 | -9,632.61 | 9,632.61 | 7.547 | 0.612 |
| weekend | idle | block | 30 | 23,347.93 | -17,661.48 | 17,661.48 | 0.000 | 0.000 |
| weekend | idle | step | 30 | 23,347.93 | -17,661.48 | 17,661.48 | 0.000 | 0.000 |
| weekend | mpc | block | 30 | 28,751.35 | -28,325.63 | 31,831.51 | 20.149 | 0.272 |
| weekend | oracle_lp | block | 30 | 28,751.35 | -28,325.63 | 31,831.51 | 20.149 | 0.272 |
| weekend | price_threshold | block | 30 | 27,465.53 | -26,477.63 | 30,153.42 | 17.062 | 0.165 |
| weekend | price_threshold | step | 30 | 27,465.53 | -26,477.63 | 30,153.42 | 17.062 | 0.165 |
| weekend | rule_based | block | 30 | 24,139.28 | -16,000.44 | 16,184.43 | 5.727 | 0.398 |
| weekend | rule_based | step | 30 | 25,614.63 | -25,198.52 | 25,198.52 | 15.327 | 0.417 |

## Plots

![score_by_strategy](score_by_strategy.png)

![soc_sample_day](soc_sample_day.png)

![price_and_power](price_and_power.png)
