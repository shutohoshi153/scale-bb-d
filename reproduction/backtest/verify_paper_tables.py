"""Check the result tables of the paper against the generated outputs (added 2026-09-30; referee comment A-0).

Reads the Markdown source of §5 and §6 of the paper, parses Tables 5.1-5.5 and
6.1-6.5, recomputes every number from the CSVs under output/ and reports each
cell that differs by more than half a unit of the last printed digit.

Usage:
    python verify_paper_tables.py                                # English final sections
    python verify_paper_tables.py --sections ../../final/sections  # Japanese final sections

Exit code 0 if every checked cell agrees, 1 otherwise.  Run after run_all.sh.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import _paths

BASE = _paths.OUTPUT_DIR
HERE = Path(__file__).resolve().parent
DISEASES = ["total", "heart_disease", "cancer", "cerebrovascular", "kidney", "liver", "diabetes", "hypertensive"]
SIX = ["total", "heart_disease", "cancer", "cerebrovascular", "kidney", "diabetes"]
CUTOFFS = [2014, 2021, 2022]
NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*")


# ---------------------------------------------------------------- paper side
def find_table(text: str, number: str) -> list[list[str]]:
    """Rows (lists of cell strings, header and separator dropped) of the table captioned 'Table n:' / '表 n:'."""
    lines = text.split("\n")
    start = [k for k, l in enumerate(lines) if re.match(rf"^(Table|表) {re.escape(number)}[:：]", l)]
    if len(start) != 1:
        raise LookupError(f"caption of table {number} found {len(start)} times")
    k = start[0] + 1
    while k < len(lines) and not lines[k].startswith("|"):
        k += 1
    rows = []
    while k < len(lines) and lines[k].startswith("|"):
        rows.append([c.strip() for c in lines[k].strip().strip("|").split("|")])
        k += 1
    return rows[2:]


def numbers(cell: str) -> list[tuple[float, int]]:
    """All numbers in a cell as (value, printed decimals); typographic minus signs and LaTeX are normalised."""
    s = cell.replace("−", "-").replace("–", " ").replace("〜", " ")
    s = re.sub(r"\$[^$]*\$", " ", s)  # drop inline maths such as $n = 118$ (checked separately where needed)
    out = []
    for m in NUM.finditer(s):
        tok = m.group().replace(",", "")
        out.append((float(tok), len(tok.split(".")[1]) if "." in tok else 0))
    return out


def series_of(cell: str) -> str | None:
    m = re.search(r"`(\w+)`", cell)
    return m.group(1) if m else None


class Report:
    def __init__(self) -> None:
        self.n = 0
        self.bad: list[str] = []

    def check(self, label: str, printed: tuple[float, int], value: float) -> None:
        self.n += 1
        p, dec = printed
        # half a unit of the last printed digit, plus a small allowance for values that sit on a rounding boundary
        if not np.isfinite(value) or abs(p - value) > 0.502 * 10 ** (-dec):
            self.bad.append(f"{label}: paper {p:.{dec}f}, output {value:.{dec + 2}f}")


# ---------------------------------------------------------------- output side
def tables_dir(cutoff: int, base_level: str = "observed") -> Path:
    if base_level != "observed":
        return BASE / f"base_{base_level}_cutoff_{cutoff}" / "tables"
    return BASE / "tables" if cutoff == 2014 else BASE / f"cutoff_{cutoff}" / "tables"


def cell_errors(cutoff: int, base_level: str = "observed") -> pd.DataFrame:
    sb = pd.read_csv(tables_dir(cutoff, base_level) / "validation_long.csv").assign(method="scalebb")
    bl = pd.read_csv(tables_dir(cutoff) / "validation_long_baseline.csv")
    df = pd.concat([sb, bl], ignore_index=True)
    return df[df["actual_rate_per_100k"] > 0]


def mape_table(cutoff: int, base_level: str = "observed") -> pd.DataFrame:
    """index (disease, sex), columns method: MAPE [%]; plus 'bias' = mean relative error of Scale BB-D [%]."""
    df = cell_errors(cutoff, base_level)
    m = df.groupby(["disease", "sex", "method"])["abs_rel_error"].mean().mul(100).unstack("method")
    m["bias"] = df[df["method"] == "scalebb"].groupby(["disease", "sex"])["rel_error"].mean().mul(100)
    m["best"] = m[["naive_last", "mean_3pts", "loglin_trend"]].min(axis=1)
    return m


def independent(t: pd.DataFrame) -> pd.DataFrame:
    """The 14 independent disease x sex cells: seven causes (all-cause excluded) for men and for women."""
    return t[(t.index.get_level_values("sex") != "total") & (t.index.get_level_values("disease") != "total")]


# ---------------------------------------------------------------- checks
def check_5_1(text, rep):
    m = mape_table(2014).xs("total", level="sex")
    for row in find_table(text, "5.1"):
        d = series_of(row[0])
        for col, key in ((1, "scalebb"), (2, "bias"), (3, "naive_last"), (4, "mean_3pts"), (5, "loglin_trend")):
            rep.check(f"Table 5.1 {d} {key}", numbers(row[col])[0], m.loc[d, key])
        rep.check(f"Table 5.1 {d} gap", numbers(row[7])[0], round(m.loc[d, "scalebb"], 2) - round(m.loc[d, "best"], 2))


def check_5_2(text, rep):
    m = {c: mape_table(c).xs("total", level="sex") for c in CUTOFFS}
    for row in find_table(text, "5.2"):
        d = series_of(row[0])
        for k, c in enumerate(CUTOFFS):
            rep.check(f"Table 5.2 {d} {c}", numbers(row[1 + k])[0], m[c].loc[d, "scalebb"])


def check_5_3(text, rep):
    cols = [(c, lvl) for c in CUTOFFS for lvl in ("observed", "mean_obs")]
    m = {k: mape_table(*k) for k in cols}
    for row in find_table(text, "5.3"):
        d = series_of(row[0])
        for j, k in enumerate(cols):
            t = m[k]
            if d:
                rep.check(f"Table 5.3 {d} {k}", numbers(row[1 + j])[0], t.xs("total", level="sex").loc[d, "scalebb"])
            elif "ahead" in row[0] or "上回る" in row[0]:
                sub_t = independent(t) if "14" in row[0] else t
                rep.check(f"Table 5.3 cells ahead ({len(sub_t)} cells) {k}", numbers(row[1 + j])[-1],
                          float((sub_t["scalebb"] < sub_t["best"] - 1e-9).sum()))
            else:
                tt = t.xs("total", level="sex")
                rep.check(f"Table 5.3 mean gap {k}", numbers(row[1 + j])[0], float((tt["scalebb"].round(2) - tt["best"].round(2)).mean()))


def check_5_4(text, rep):
    s = pd.read_csv(BASE / "cutoff_comparison" / "tables" / "fixed_horizon_summary.csv").set_index(["cutoff", "h"])
    for row in find_table(text, "5.4"):
        c = int(numbers(row[0])[0][0])
        for h in (1, 2, 3):
            for j, key in ((2 * h - 1, "scalebb"), (2 * h, "best_baseline")):
                if numbers(row[j]):
                    rep.check(f"Table 5.4 cutoff {c} h={h} {key}", numbers(row[j])[0], s.loc[(c, h), key])


def check_5_5(text, rep):
    c = pd.read_csv(BASE / "cutoff_comparison" / "tables" / "same_anchor_cells.csv")
    mean8 = c[c["sex"] == "total"].groupby(["anchor", "trend", "cutoff"])["MAPE"].mean()
    order = [("observed", "none"), ("observed", "loglin"), ("observed", "scalebb"), ("mean3", "none"), ("mean3", "loglin"),
             ("mean3", "scalebb"), ("fitted", "loglin"), ("fitted", "scalebb")]
    rows = find_table(text, "5.5")
    for (a, tr), row in zip(order, rows):
        for k, cut in enumerate(CUTOFFS):
            rep.check(f"Table 5.5 {a}/{tr} {cut}", numbers(row[2 + k])[0], mean8[(a, tr, cut)])
    w = c.pivot_table(index=["cutoff", "disease", "sex"], columns=["anchor", "trend"], values="MAPE")
    for k, cut in enumerate(CUTOFFS):
        for row, x in ((rows[8], independent(w.loc[cut])), (rows[9], w.loc[cut])):  # 14 independent cells, then all 24
            got = numbers(row[2 + k])
            for j, a in enumerate(("observed", "mean3")):
                rep.check(f"Table 5.5 cells ahead ({len(x)} cells) {a} {cut}", got[j],
                          float((x[(a, "scalebb")] < x[(a, "loglin")] - 1e-9).sum()))


def da_summary() -> pd.DataFrame:
    return pd.read_csv(BASE / "directional" / "tables" / "directional_summary_total.csv")


def check_6_1(text, rep):
    s = da_summary()
    s = s[(s["cutoff"] == 2014) & (s["method"] == "scalebb")].set_index("disease")
    inf = pd.read_csv(BASE / "directional" / "tables" / "da_inference.csv")
    inf = inf[inf["cutoff"] == 2014].set_index("series")
    for row in find_table(text, "6.1"):
        d = series_of(row[0]) or "pooled_six"
        r = inf.loc[d]
        rep.check(f"Table 6.1 {d} n", numbers(row[1])[0], r["n"])
        rep.check(f"Table 6.1 {d} DA", numbers(row[2])[0], r["DA"])
        if d != "pooled_six":
            rep.check(f"Table 6.1 {d} predicted down", numbers(row[3])[0], s.loc[d, "pred_down_pct"])
            rep.check(f"Table 6.1 {d} n (summary)", numbers(row[1])[0], s.loc[d, "n_cells_evaluable"])
        rep.check(f"Table 6.1 {d} majority", numbers(row[4])[0], r["majority"])
        lo, hi = numbers(row[5])
        rep.check(f"Table 6.1 {d} DA lo", lo, r["DA_lo"]); rep.check(f"Table 6.1 {d} DA hi", hi, r["DA_hi"])
        rep.check(f"Table 6.1 {d} DA - benchmark", numbers(row[6])[0], r["DA_minus_majority"])
        if numbers(row[7]):
            lo, hi = numbers(row[7])
            rep.check(f"Table 6.1 {d} excess lo", lo, r["excess_lo"]); rep.check(f"Table 6.1 {d} excess hi", hi, r["excess_hi"])


def check_6_2(text, rep):
    s = da_summary()
    s = s[s["method"] == "scalebb"].set_index(["disease", "cutoff"])
    for row in find_table(text, "6.2"):
        d = series_of(row[0])
        for k, c in enumerate(CUTOFFS):
            da, maj = numbers(row[1 + k])
            rep.check(f"Table 6.2 {d} {c} DA", da, s.loc[(d, c), "dir_acc_pct"])
            rep.check(f"Table 6.2 {d} {c} majority", maj, s.loc[(d, c), "majority_pct"])


def check_6_3(text, rep):
    r = pd.read_csv(BASE / "directional" / "tables" / "rolling_origin_da.csv")
    r = r[r["disease"].isin(SIX)]
    mean = r.groupby(["method", "cutoff"])["dir_acc_pct"].mean()
    maj = r[r["method"] == "scalebb"].groupby("cutoff")["majority_pct"].mean()
    rows = find_table(text, "6.3")
    cutoffs = list(range(2014, 2023))
    for row, key in zip(rows[1:], ("scalebb", "loglin_trend", "majority", "always_down")):
        for k, c in enumerate(cutoffs):
            rep.check(f"Table 6.3 {key} {c}", numbers(row[1 + k])[0], maj[c] if key == "majority" else mean[(key, c)])


def check_6_4(text, rep):
    w = pd.read_csv(BASE / "directional" / "tables" / "directional_winloss.csv").set_index("vs")
    s = pd.read_csv(BASE / "directional" / "tables" / "directional_summary.csv")
    p = independent(s.pivot_table(index=["cutoff", "disease", "sex"], columns="method", values="dir_acc_pct"))
    by_sex = pd.DataFrame({m: {"wins": ((p["scalebb"] - p[m]) > 1e-9).sum(), "ties": ((p["scalebb"] - p[m]).abs() <= 1e-9).sum(),
                               "losses": ((p["scalebb"] - p[m]) < -1e-9).sum()} for m in p.columns if m != "scalebb"}).T
    for row in find_table(text, "6.4"):
        m = series_of(row[0])
        for j, key in ((1, "wins"), (2, "ties"), (3, "losses")):
            rep.check(f"Table 6.4 {m} {key}", numbers(row[j])[0], float(w.loc[m, key]))
        if len(row) > 4:  # independent comparisons: seven causes x men and women x 3 cutoffs
            for got, key in zip(numbers(row[4]), ("wins", "ties", "losses")):
                rep.check(f"Table 6.4 {m} {key} (by sex)", got, float(by_sex.loc[m, key]))


def check_6_5(text, rep):
    c = pd.read_csv(BASE / "directional" / "tables" / "calibration_recovery.csv").set_index(["setting", "disease"])
    settings = ["2014_default", "2014_L0", "2014_L0_P2020"]
    rows = find_table(text, "6.5")
    s = da_summary()
    s = s[s["method"] == "scalebb"].set_index(["disease", "cutoff"])
    for row, st in zip(rows[:3], settings):
        for j, d in ((2, "liver"), (3, "hypertensive")):
            rep.check(f"Table 6.5 {st} {d}", numbers(row[j])[0], c.loc[(st, d), "dir_acc_pct"])
    for row, cut in zip(rows[3:5], (2021, 2022)):
        for j, d in ((2, "liver"), (3, "hypertensive")):
            rep.check(f"Table 6.5 {cut} default {d}", numbers(row[j])[0], s.loc[(d, cut), "dir_acc_pct"])


CHECKS = [("05_results_point_forecast.md", [check_5_1, check_5_2, check_5_3, check_5_4, check_5_5]),
          ("06_results_directional_accuracy.md", [check_6_1, check_6_2, check_6_3, check_6_4, check_6_5])]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--sections", default=str(HERE.parents[1] / "final" / "sections_en_b1"),
                    help="directory holding 05_results_point_forecast.md and 06_results_directional_accuracy.md")
    args = ap.parse_args()
    sections = Path(args.sections)
    rep = Report()
    for fname, checks in CHECKS:
        path = sections / fname
        if not path.exists():
            print(f"[verify_paper_tables] {path} not found; nothing checked for this file")
            continue
        text = path.read_text(encoding="utf-8")
        for fn in checks:
            before = rep.n
            try:
                fn(text, rep)
            except Exception as e:  # a parsing or lookup failure is itself a finding
                rep.bad.append(f"{fn.__name__}: {type(e).__name__}: {e}")
            print(f"  {fn.__name__.replace('check_', 'Table ').replace('_', '.')}: {rep.n - before} cells checked")
    print(f"\n[verify_paper_tables] {rep.n} cells checked against {BASE}, {len(rep.bad)} mismatches")
    for b in rep.bad:
        print("  MISMATCH", b)
    return 1 if rep.bad or rep.n == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
