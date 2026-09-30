"""EAS 内蔵の Scale BB 拡張モデル・アルゴリズムコア.

`ScaleBB_Research/scripts/research/` の研究実装を EAS 配下に取り込み、
EAS を独立した経験率分析システムとして動作させるためのパッケージ。

公開モジュール::

    model       : Scale BB (AP) コア (fit_scale_bb / project_scale_bb / ScaleBBConfig)
    apc_model   : Scale BB APC コア (fit_scale_bb_apc / project_scale_bb_apc)
    panels      : data/processed/ パネル CSV/parquet → 観測行列ローダ
    disease     : 疾病/受療率パネル → fit/project の高位 API
    heatmap     : Scale BB ヒートマップ・投影プロット (PNG 出力)
"""
from __future__ import annotations
