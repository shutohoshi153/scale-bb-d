[日本語](README.md) | **English**

# bel_demo — Reproduction package for the §8 BEL sensitivity demonstration (scenario generator → projection → sensitivity table)

This package re-runs §8 of the paper (BEL sensitivity under economic-value-based valuation) and Appendix A (simplified life-insurance risk capital and MOCE) entirely inside `reproduction/`. Where the neighbouring `generational/` package runs Scale BB-D forward to produce rate tables, this package **takes those rate tables into a valuation model and turns them into a regulatory sensitivity table**. Table 8.3, Figure 8.1 and Table A.1 are generated here.

**For practitioners**: this package is the executable form of arguments 1 and 2 of §9.2 — the generator sits upstream of the valuation model, its output is the rate-table format valuation practice already consumes, and it replaces the "static table × uniform factor" stress-table step. The column layout of `data/processed/scn_claim_rates.csv` (`SCN_CD, BNFT_Q, GNDR_CD, ISSUE_AGE, DUR, ASSM_RT`) is designed as a valuation-model input; swap in your own rate tables, model points and discount curve to obtain your own sensitivities.

**Scope statement (same as §8.4)**: a **demonstration model** — benefit cash flows only, independence approximation for decrements, 8 model points. It is not a production valuation model. For the reconciliation on a production projection model (FMS Booster) see `../../fms_booster/`.

## Layout

```
bel_demo/
├── README.md / README.en.md
├── _paths.py                       self-contained path layer (shares core and panel with backtest/)
├── run_all.sh                      runs ⓪–⑤ and checks against reference_output_20260930/
├── check_reference.py              acceptance test (rtol 1e-9 against reference_output_20260930/; switch with --reference-dir)
├── build_esr_discount_curve.py     ⓪ ESR risk-free curve (JPY, 31 Mar 2026, Smith-Wilson)
├── build_scenario_claim_rates.py   ① scenario generator: one Phase 1 fit → 6 scenarios by replacing L
├── verify_pipeline_rates.py        ② V1a: independent re-derivation of every rate
├── calc_bel_standalone.py          ③ projection (equations 8.1–8.2) + V2/V3 checks
├── aggregate_bel_results.py        ④ Table 8.3 / Figure 8.1
├── calc_esr_life_risk.py           ⑤ Appendix A (notice Articles 56–64, 81, 29–30)
├── data/external/fsa_esr/          FSA published material (yield-curve tool) + source README
├── data/processed/                 regenerated (not tracked)
├── output/                         regenerated (not tracked)
├── reference_output/               reference results as of 2026-08 (before the smoothing-grid correction); identical to the co-author share; no longer reproduced by the current code
├── reference_output_20260902/      reference results after the 2026-09-02 correction (core annual_grid, lam_col=20; projection started from the smoothed rate); no longer reproduced by the current code
├── reference_output_20260903/      accepted reference results after the 2026-09-03 correction (projection starts from the observed rate: core `ScaleBBConfig.base_level="observed"`, as equation 3.6 of the paper states); source of the paper's current §8 / Appendix A numbers (total BASE BEL 333,233 yen); no longer reproduced by the current code
└── reference_output_20260930/      accepted reference results after the 2026-09-30 change (valuation as a cause-specific death benefit: a death from the three causes leaves the survivors once; ESR_M = mortality +12.5%)
```

## Run

```bash
cd reproduction/bel_demo
bash run_all.sh            # six scripts, then check_reference.py against reference_output_20260930/
```

Environment: as `../backtest/README.en.md` (Python 3.10+, numpy / pandas / matplotlib) plus `openpyxl`. Runtime is on the order of tens of seconds.

## Inputs and outputs by step

| Step | Script | Input | Output |
|---|---|---|---|
| ⓪ | `build_esr_discount_curve.py` | Yield-curve tool parameter sheet (JPY: LOT 30y, UFR 3.8%, convergence 60y, 13 observed maturities) | `data/processed/esr_jpy_spot_curve_20260331.csv` |
| ① | `build_scenario_claim_rates.py` | `../backtest/data/prebuilt_disease_panel_mortality.csv`, `_scalebb_core` (`../backtest/vendor/`) | `scn_claim_rates.csv` (6 scenarios × 3 diseases × 2 sexes), `scn_mortality_rates.csv` (all-cause, BASE fixed), `rate_surface_*.csv` for checking |
| ② | `verify_pipeline_rates.py` | output of ① | `output/verify_pipeline_rates.csv` (pass = 0 mismatches) |
| ③ | `calc_bel_standalone.py` | outputs of ⓪ and ① | `output/bel_by_mp_scenario.csv`, `verify_bel_checks.csv` |
| ④ | `aggregate_bel_results.py` | output of ③ | `output/bel_sensitivity_table.csv` (= Table 8.3), `bel_sensitivity_bar.png` (= Figure 8.1) |
| ⑤ | `calc_esr_life_risk.py` | outputs of ⓪ and ① | `output/esr_life_risk_by_mp.csv`, `esr_life_risk_summary.csv` (= Table A.1) |

## Specification (§8.4–8.5)

- Six scenarios: BASE (L = 1.0%) / UP50 (1.5%) / DN50 (0.5%) / ICS_T (0%) / ICS_C (ICS_T × 1.125) / ESR_M (BASE × 1.125). One Phase 1 fit per disease × sex; only Phase 2 is re-run (implementation column of Table 8.2)
- Eight model points: entry ages 30/40/50/60 × male/female, issued 2026, lump sum of JPY 1 million on first diagnosis of the three major diseases (cancer, heart, cerebrovascular), cover to age 90
- Common assumptions: lapse 3% p.a., death decrement from projected all-cause rates (BASE fixed), discounting on the ESR risk-free curve (no spread adjustment)
- Regulatory stress factor: Pillar 1 notice Article 56 mortality +12.5% (ESR_M and the level part of ICS_C; applied to the three causes and to the other causes)

## Running on your own data

1. Point `PANEL_CSV` in `_paths.py` at your own cause-specific (or incidence) panel. Column layout as `disease_panel_mortality.csv` in `../backtest/README.en.md` (`disease_id, sex, age_low, year, rate`, per 100k).
2. Set `MODEL_POINTS` / `LAPSE_RATE` / `SUM_ASSURED` in `calc_bel_standalone.py` to your product and assumptions.
3. Replace `XLSX` in `_paths.py` with the FSA tool for your valuation date (published quarterly).
4. `bash run_all.sh --skip-check` (the reference comparison is specific to the paper's settings).

To feed your own valuation model directly, convert `scn_claim_rates.csv` from step ① into your model's rate-table format; steps ③ onward are then unnecessary (§9.2, argument 1). `../../fms_booster/` shows a worked reconciliation on a production model.

## Not included; licences

- The FSA material in `data/external/fsa_esr/` is the FSA's own publication and is not covered by this repository's licences (MIT / CC BY 4.0). The notice PDFs are not bundled; source URLs are in `data/external/fsa_esr/README.md`.
- The FMS-side input builders (`build_fms_input_tables.py` etc.) depend on the upstream research pipeline and are not bundled; the generated input databases and the reconciliation script are in `../../fms_booster/`.
- Originals live in the working repository `ICA/ScaleBB/Research/scripts/bel_demo/`; only the path anchors differ (synchronised by `Paper_ICA2026_publish/package_bel_demo.sh`).

## Verification status

- V1a (every rate re-derived independently): pass, 0 mismatches
- V2 (monotonicity UP50 < BASE < DN50 < ICS_T < ICS_C): holds at every model point
- V3 (composition): ICS_C/ICS_T = 1.09–1.11, ESR_M/BASE = 1.09–1.11 (deviation from the nominal factors is the decrement interaction)
- Discount curve: 13 observed maturities reproduced exactly; instantaneous forward at 60y within ±1 bp of the UFR
- Headline results (total BEL vs BASE): UP50 −6.7% / DN50 +7.4% / ICS_T +15.4% / ICS_C +26.5% / ESR_M +10.0%

## Variant for the sensitivity analysis (added 2026-09-30)

Running `build_esr_discount_curve.py` → `build_scenario_claim_rates.py` → `calc_bel_standalone.py` → `aggregate_bel_results.py` with `BEL_DEMO_VARIANT=deathweight` replaces the Phase 1 smoothing by the death-count-weighted fit (`fit_scale_bb(..., weight=deaths)`) and writes to `data/processed_deathweight/` and `output_deathweight/` (§10 item 6 of the paper). Reference values are in `reference_output_20260930_deathweight/`. Without the variable the main results of the paper (equal weights) are written to `output/` as before, and `check_reference.py` is unaffected.

## Change of 2026-09-30: valuation as a cause-specific death benefit

The BEL calculation (Eq. 8.1 of the paper) was changed when the scope of the paper was limited to cause-specific death benefits.

- Survivors: `S(t+1) = S(t)·(1 − q_dis − q_other − q_lapse)`, where `q_dis` is the death rate from the three causes (cancer, heart disease, cerebrovascular disease) and `q_other` that from all other causes (all-cause BASE less the three causes BASE). Up to the 2026-09-03 version the product was valued as a benefit paid on a health event, `1 − q_dis − q_death − q_lapse` with `q_death` the all-cause rate, which for a death benefit removes a death from the three causes twice.
- Level stress ESR_M: mortality risk +12.5% (Art. 56) instead of morbidity and disability risk +20% (Arts. 59–60). In ICS_C and ESR_M the same factor is applied to the other causes.
- Appendix A (`calc_esr_life_risk.py`): the mortality sub-risk equals the ΔBEL of ESR_M; the longevity and morbidity sub-risks are zero.
- Result: total BASE BEL 333,233 → 364,198 yen (+9.3%); the ICS_T sensitivities rise by 0.5–1.0pp. The results of the earlier calculation remain in `reference_output_20260903/`; `final/review/scripts/death_benefit_reading_a6.py` puts the two side by side.
- The reconciliation on the production model (FMS; §9.2 of the paper) was made with the earlier calculation and has not been repeated. The rate-table format (`scn_claim_rates.csv`) is unchanged; only the ESR_M factor differs.
