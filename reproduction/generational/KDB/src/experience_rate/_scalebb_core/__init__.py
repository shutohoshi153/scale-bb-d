"""KDB-embedded Scale BB extension model / algorithm core.

Package that incorporates the research-side Scale BB implementation into
KDB so that KDB operates as a standalone experience-rate analysis system.

Public modules::

    model       : Scale BB (AP) core (fit_scale_bb / project_scale_bb / ScaleBBConfig)
    apc_model   : Scale BB APC core (fit_scale_bb_apc / project_scale_bb_apc)
    panels      : data/processed/ panel CSV/parquet -> observation matrix loader
    disease     : disease / utilization-rate panels -> high-level fit/project API
    heatmap     : Scale BB heatmap / projection plots (PNG output)
"""
from __future__ import annotations
