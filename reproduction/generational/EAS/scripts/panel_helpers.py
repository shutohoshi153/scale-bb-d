"""疾病発生率パネル構築の共通ヘルパ.

estat_data_dictionary.md §9.1 で言及されている機能を提供する。
各 build_*_panel.py から import して共通の正規化を行う。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# -----------------------------------------------------------------------------
# パスユーティリティ
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROW_DATA = PROJECT_ROOT / "data" / "RowData"
PROCESSED = PROJECT_ROOT / "data" / "processed"
PATIENT_SURVEY = ROW_DATA / "estat_processed" / "patient_survey"
POPULATION = ROW_DATA / "estat_processed" / "population"
VITAL_STATS = ROW_DATA / "estat_processed" / "vital_statistics"


# -----------------------------------------------------------------------------
# 和暦・全角数字 → 西暦
# -----------------------------------------------------------------------------
_ERA_RE = re.compile(r"^(昭和|平成|令和)\s*(元|[０-９\d]+)\s*年?$")


def _to_ascii(s: str) -> str:
    """全角→半角を含めた NFKC 正規化."""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s))


def wareki_to_seireki(label: object) -> int | None:
    """「平成8年 / 令和元年 / ２０２３年 / 1995年」→ 1996 / 2019 / 2023 / 1995.

    None / 空文字 / パース不能の場合は ``None``.
    """
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None
    s = _to_ascii(label).strip().replace("年", "")
    if not s:
        return None
    m = _ERA_RE.match(_to_ascii(label).strip())
    if m:
        era, num = m.group(1), m.group(2)
        n = 1 if num == "元" else int(_to_ascii(num))
        if era == "昭和":
            return 1925 + n
        if era == "平成":
            return 1988 + n
        if era == "令和":
            return 2018 + n
    try:
        return int(s)
    except ValueError:
        return None


# -----------------------------------------------------------------------------
# 年齢ラベル正規化
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class AgeBand:
    code: str            # 'a05_09', 'a90p', 'r65p', 'total' など
    low: int | None      # 下限 (含む)
    high: int | None     # 上限 (含む, 開区間は None)
    is_recap: bool       # 「再掲」項目フラグ
    is_total: bool       # 総数フラグ


_TOTAL_KEYWORDS = {"総数", "全年齢", "全数"}


def _parse_range(s: str) -> tuple[int | None, int | None]:
    """「5～9歳 / 5-9歳 / 85歳以上 / 100歳以上」等を (low, high) に分解."""
    s = _to_ascii(s)
    # NFKC 後は 「～」→ 「~」、「－」→ 「-」になっているので両方を「-」に寄せる
    for sep in ("～", "〜", "―", "~", "ー", "–", "—"):
        s = s.replace(sep, "-")
    s = s.replace("歳以上", "p").replace("歳", "").strip()
    if s.endswith("p"):
        try:
            low = int(s[:-1])
            return low, None
        except ValueError:
            return None, None
    if "-" in s:
        lo, hi = s.split("-", 1)
        try:
            return int(lo), int(hi)
        except ValueError:
            return None, None
    try:
        n = int(s)
        return n, n
    except ValueError:
        return None, None


def parse_age_label(label: object) -> AgeBand:
    """年齢ラベルを AgeBand に変換する.

    Examples:
        '総数' → AgeBand('total', None, None, False, True)
        '0歳' → AgeBand('a00', 0, 0, False, False)
        '5～9歳' → AgeBand('a05_09', 5, 9, False, False)
        '85歳以上' → AgeBand('a85p', 85, None, False, False)
        '（再掲）65歳以上' → AgeBand('r65p', 65, None, True, False)
    """
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return AgeBand("unknown", None, None, False, False)
    raw = _to_ascii(label).strip()
    is_recap = ("再掲" in raw) or raw.startswith("　")
    s = raw.replace("（再掲）", "").replace("(再掲)", "").strip()
    if s in _TOTAL_KEYWORDS:
        return AgeBand("total", None, None, is_recap, True)

    low, high = _parse_range(s)
    if low is None and high is None:
        return AgeBand("unknown", None, None, is_recap, False)

    prefix = "r" if is_recap else "a"
    if high is None:
        code = f"{prefix}{low:02d}p"
    elif low == high:
        code = f"{prefix}{low:02d}"
    else:
        code = f"{prefix}{low:02d}_{high:02d}"
    return AgeBand(code, low, high, is_recap, False)


# -----------------------------------------------------------------------------
# 疾病ラベル正規化
# -----------------------------------------------------------------------------
_ROMAN_PREFIX_RE = re.compile(
    r"^[\u2160-\u2188IVXＩⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅬⅭⅮⅯ]+\s*[　 ]*"
)


def normalize_disease_label(label: object) -> str:
    """疾病ラベルの正規化.

    - ローマ数字 / 数字プレフィックス除去
    - 外側括弧除去
    - 再掲トレーラ '（再掲）' / '(再掲)' 除去
    - 前後空白・全角空白除去
    """
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return ""
    s = _to_ascii(str(label)).strip()
    s = re.sub(r"^\s*\d+\s+", "", s)
    s = _ROMAN_PREFIX_RE.sub("", s)
    s = re.sub(r"[（(]再掲[）)]$", "", s).strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    if s.startswith("（") and s.endswith("）"):
        s = s[1:-1]
    return s.strip()


# -----------------------------------------------------------------------------
# Focus disease マッピング
# -----------------------------------------------------------------------------
# 統一 disease_id (estat_data_dictionary.md §9.1)
FOCUS_DISEASES = [
    "cancer",
    "neoplasm_all",
    "cardiovascular_all",
    "heart_disease",
    "ischemic_heart",
    "cerebrovascular",
    "hypertensive",
    "total",
]

_DISEASE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("cancer", ("悪性新生物",)),
    ("neoplasm_all", ("新生物",)),
    ("ischemic_heart", ("虚血性心疾患",)),
    ("heart_disease", ("心疾患",)),
    ("cerebrovascular", ("脳血管",)),
    ("hypertensive", ("高血圧",)),
    ("cardiovascular_all", ("循環器",)),
    ("total", ("総数",)),
]


def focus_disease_id(label: str) -> str | None:
    """正規化済み疾病ラベル → 統一 disease_id.

    ``label`` は ``normalize_disease_label`` 済みを想定。
    マッチしなければ None。
    """
    if not label:
        return None
    for did, keys in _DISEASE_KEYWORDS:
        if any(k in label for k in keys):
            return did
    return None


# -----------------------------------------------------------------------------
# 性別正規化
# -----------------------------------------------------------------------------
def normalize_sex(label: object) -> str:
    """'総数 / 男 / 女' → 'total' / 'male' / 'female'."""
    if label is None:
        return "unknown"
    s = _to_ascii(str(label)).strip()
    if s in ("総数", "男女計", "計", "全体", "合計"):
        return "total"
    if s in ("男", "男性"):
        return "male"
    if s in ("女", "女性"):
        return "female"
    return s.lower() or "unknown"


def sex_code(sex_label: str) -> int:
    """正規化済み sex → 0/1/2 (population_incidence.sex 列)."""
    return {"total": 0, "male": 1, "female": 2}.get(sex_label, 0)


# -----------------------------------------------------------------------------
# 人口読込
# -----------------------------------------------------------------------------
def load_population(path: Path | None = None) -> pd.DataFrame:
    """pop_5yr_age_combined.csv を tidy に読み込む.

    Returns columns:
        year (int), sex (total/male/female), age_code, age_low, age_high,
        age_is_recap, age_is_total, population_thousand
    """
    path = path or (POPULATION / "pop_5yr_age_combined.csv")
    df = pd.read_csv(path)

    df = df[df["人口・割合"].isna() | (df["人口・割合"] == "人口")]
    df["year"] = df["時間軸（年）"].map(wareki_to_seireki)
    df["sex"] = df["男女別"].map(normalize_sex)

    ages = df["年齢5歳階級"].map(parse_age_label)
    df["age_code"] = [a.code for a in ages]
    df["age_low"] = [a.low for a in ages]
    df["age_high"] = [a.high for a in ages]
    df["age_is_recap"] = [a.is_recap for a in ages]
    df["age_is_total"] = [a.is_total for a in ages]

    df["population_thousand"] = df["value"].astype(float)

    return df[
        [
            "year",
            "sex",
            "age_code",
            "age_low",
            "age_high",
            "age_is_recap",
            "age_is_total",
            "population_thousand",
        ]
    ].dropna(subset=["year"])


# -----------------------------------------------------------------------------
# 出力用共通カラム
# -----------------------------------------------------------------------------
INCIDENCE_PANEL_COLUMNS = [
    "disease_id",
    "disease_norm",
    "icd10",
    "sex",
    "sex_code",
    "age_code",
    "age_low",
    "age_high",
    "year",
    "section",
    "rate_type",
    "incidence_rate_annual",
    "incidence_rate_per_100k",
    "numerator_count",
    "population_thousand",
    "source_table",
    "quality_flag",
    "method_note",
]


def empty_incidence_panel() -> pd.DataFrame:
    """空の incidence_panel DataFrame (カラムのみ定義)."""
    return pd.DataFrame(columns=INCIDENCE_PANEL_COLUMNS)


def conform_incidence_panel(df: pd.DataFrame) -> pd.DataFrame:
    """不足カラムを NaN で補って規定の列順に揃える."""
    out = df.copy()
    for col in INCIDENCE_PANEL_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[INCIDENCE_PANEL_COLUMNS]
