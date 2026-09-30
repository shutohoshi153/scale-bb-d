# Supplementary checks cited in the paper

Each script is run from `reproduction/backtest/` (it imports that package's path
layer and algorithm core) and writes its CSV and Markdown output to `final/review/`.

```bash
cd reproduction/backtest
python ../../final/review/scripts/<script>.py
```

| Script | Paper | Content | Needs first |
|---|---|---|---|
| `long_horizon_comparison.py` | §7.2, Table 7.1, Figure 7.1 | Scale BB-D vs log-linear extrapolation to 2086; BEL by method | `reproduction/bel_demo/run_all.sh` (discount curve) |
| `l_range_a7.py` | §7.2 | Distribution of historical ten-year improvement rates (basis for the range of *L*) | — |
| `death_benefit_reading_a6.py` | §8.3 | BEL as a death benefit vs the earlier health-event form of the calculation (run from `reproduction/bel_demo/`) | `reproduction/bel_demo/run_all.sh` |
| `weighted_smoothing_a8.py` | §8.3, §10 item 6 | Death-count-weighted smoothing: backtest and end-of-data stability | — |
| `b_items_20260930.py` | §5, §6.1, §6.3 | Counts over the 14 independent cells; ties and zero cells; MAPE by horizon | `reproduction/backtest/run_all.sh` |
| `shock_and_break_a8_a12.py` | §5.3, §6.4 | Effect of training on the shock years (fixed convergence period, shock years given zero weight); `hypertensive` bridged across the 2017 classification revision | `reproduction/backtest/run_all.sh` |

The file names and comments refer to the referee comments (A-*, B-*) to which the
checks were a response. Comments are partly in Japanese.
