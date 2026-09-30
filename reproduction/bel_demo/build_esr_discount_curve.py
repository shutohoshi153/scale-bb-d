#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESR 割引率カーブ(JPY 無リスク金利)の再現(BEL感応度デモ)。

【目的】
    金融庁「イールド・カーブ作成ツール」(2026年3月末版) のパラメータシートから
    JPY のゼロクーポン無リスク金利(信用リスク調整後、年限 1〜LOT=30 年)と
    UFR(終局金利)3.8%・収束年限 60 年を読み取り、Smith-Wilson 補外により
    経済価値ベースのソルベンシー規制(ESR)の無リスク金利カーブを再現する。
    出典: https://www.fsa.go.jp/policy/economic_value-based_solvency/index.html
          (イールド・カーブ作成ツール 2026年3月末版 20260331.xlsx)

【手法】
    観測年限(1..LOT)のゼロクーポン価格に Smith-Wilson 法を適合し、
    UFR(連続複利 ω = ln(1+UFR))へ補外する。収束速度 α は、収束年限に
    おける瞬間フォワードレートと UFR の乖離が 1bp 以内となる最小値
    (下限 0.05)を探索して定める(EIOPA / ICS 系の標準的な決め方)。
    ツール自体の SW シートと同一実装であることまでは検証していないため、
    「同一パラメータに基づくロジックの再現」であることに留意。

【簡略化】
    - 無リスク金利カーブのみ再現する。一般バケット等のスプレッド調整
      (ICS 3 バケットアプローチ)は適用しない(保守的側の簡略化)
    - UFR スプレッド(+0.2%)はスプレッド調整カーブ用のため不使用

【入力】data/external/fsa_esr/esr_yield_curve_tool_20260331.xlsx(パラメータシート)
【出力】data/processed/bel_demo/esr_jpy_spot_curve_20260331.csv
        列: MATURITY(年), SPOT_RATE(年複利スポット), DISCOUNT_FACTOR
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

# --- パス(再現パッケージ・自己完結。定義は _paths.py) ----------------------
from _paths import XLSX, PROCESSED_DIR as OUT_DIR  # noqa: E402

CURRENCY = "JPY"
MAX_MATURITY = 70          # 出力する最長年限(BEL 計算は最長 60 年)
FWD_TOLERANCE = 1e-4       # 収束判定: フォワードと UFR の乖離 1bp
ALPHA_MIN = 0.05


def read_jpy_params() -> tuple[np.ndarray, np.ndarray, float, int]:
    """パラメータシートから JPY のゼロ金利・UFR・収束年限を読む。"""
    wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
    ws = wb["パラメータ"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[1]
    # 年限列はヘッダの数値ラベルで特定する(1..20 は 1 年刻み、以降 25/30/40/50 と不連続)
    first_mat_col = next(i for i, c in enumerate(header) if str(c) == "1")
    mat_cols = []  # (列インデックス, 年限)
    for i in range(first_mat_col, len(header)):
        c = header[i]
        if isinstance(c, (int, float)):
            mat_cols.append((i, int(c)))
        else:
            break
    for r in rows[2:]:
        if r[3] == CURRENCY:
            lot = int(r[4])
            conv_year = int(r[5])
            ufr = float(r[6])
            # 未観測年限(None・'-')は除外し、観測年限のみで適合する
            mats, zeros = [], []
            for i, m in mat_cols:
                v = r[i]
                if m <= lot and isinstance(v, (int, float)):
                    mats.append(m)
                    zeros.append(float(v))
            return np.array(mats, dtype=float), np.array(zeros), ufr, conv_year
    raise ValueError(f"{CURRENCY} がパラメータシートに見つからない")


def sw_wilson(t: np.ndarray, u: np.ndarray, alpha: float, omega: float) -> np.ndarray:
    """Smith-Wilson カーネル W(t, u)(行: t、列: u)。"""
    t = t[:, None]
    u = u[None, :]
    mn = np.minimum(t, u)
    mx = np.maximum(t, u)
    return np.exp(-omega * (t + u)) * (
        alpha * mn - 0.5 * np.exp(-alpha * mx) * (np.exp(alpha * mn) - np.exp(-alpha * mn))
    )


def fit_curve(mats: np.ndarray, zeros: np.ndarray, ufr: float, conv_year: int
              ) -> tuple[np.ndarray, float]:
    """Smith-Wilson 適合と α 探索。年限 1..MAX_MATURITY の割引価格を返す。"""
    omega = np.log(1.0 + ufr)
    prices = (1.0 + zeros) ** (-mats)     # 観測ゼロクーポン価格(年複利)

    def curve_prices(alpha: float, grid: np.ndarray) -> np.ndarray:
        W_uu = sw_wilson(mats, mats, alpha, omega)
        zeta = np.linalg.solve(W_uu, prices - np.exp(-omega * mats))
        W_tu = sw_wilson(grid, mats, alpha, omega)
        return np.exp(-omega * grid) + W_tu @ zeta

    def fwd_gap(alpha: float) -> float:
        """収束年限における瞬間フォワードと UFR(連続複利)の乖離。"""
        h = 1e-4
        g = np.array([conv_year - h, conv_year + h])
        p = curve_prices(alpha, g)
        fwd = -(np.log(p[1]) - np.log(p[0])) / (2 * h)
        return abs(fwd - omega)

    # α 探索: 下限 0.05 から、収束年限でのフォワード乖離が 1bp 以内となる最小値
    alpha = ALPHA_MIN
    if fwd_gap(alpha) > FWD_TOLERANCE:
        lo, hi = ALPHA_MIN, 1.0
        while fwd_gap(hi) > FWD_TOLERANCE:
            hi *= 2.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if fwd_gap(mid) > FWD_TOLERANCE:
                lo = mid
            else:
                hi = mid
        alpha = hi

    grid = np.arange(1, MAX_MATURITY + 1, dtype=float)
    return curve_prices(alpha, grid), alpha


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mats, zeros, ufr, conv_year = read_jpy_params()
    prices, alpha = fit_curve(mats, zeros, ufr, conv_year)

    grid = np.arange(1, MAX_MATURITY + 1)
    spot = prices ** (-1.0 / grid) - 1.0
    df = pd.DataFrame({"MATURITY": grid, "SPOT_RATE": spot, "DISCOUNT_FACTOR": prices})
    df.to_csv(OUT_DIR / "esr_jpy_spot_curve_20260331.csv", index=False)

    # 検算: 観測年限の完全再現と、UFR への収束(grid[m-1] = 年限 m)
    obs_idx = mats.astype(int) - 1
    rep = prices[obs_idx] - (1.0 + zeros) ** (-mats)
    assert np.abs(rep).max() < 1e-10, "観測年限の価格再現に失敗"
    print(f"JPY: 観測年限 {len(mats)} 点(最長 {int(mats.max())} 年), "
          f"UFR={ufr:.3%}, 収束年限={conv_year}, α={alpha:.4f}")
    print(f"スポット: 1y={spot[0]:.4%}  10y={spot[9]:.4%}  30y={spot[29]:.4%}  "
          f"60y={spot[59]:.4%}(→UFR {ufr:.1%} へ収束)")
    print(f"出力: {OUT_DIR / 'esr_jpy_spot_curve_20260331.csv'}")


if __name__ == "__main__":
    main()
