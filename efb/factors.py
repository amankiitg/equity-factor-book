"""Kenneth French data library loaders (Sprint E1, Task 3).

Downloads the four daily files (FF5, Momentum, Short-term reversal, 12
industry portfolios) and parses them into decimal units on a business-day
DatetimeIndex. Missing values use the library's sentinel codes (-99.99,
-999), which are converted to NaN before unit conversion.
"""

from __future__ import annotations

import io
import re
import zipfile

import numpy as np
import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (research; Equity Factor Book E1)"}
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"

FF_URLS: dict[str, str] = {
    "ff5": BASE + "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": BASE + "F-F_Momentum_Factor_daily_CSV.zip",
    "strev": BASE + "F-F_ST_Reversal_Factor_daily_CSV.zip",
    "ind12": BASE + "12_Industry_Portfolios_daily_CSV.zip",
}

SENTINELS = (-99.99, -999.0, -99.0)

_DATA_LINE = re.compile(r"^\d{4,8},")


def _get_bytes(url: str, timeout: int = 90) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def download_french_zip(url: str) -> str:
    """Download a French library zip and return the first CSV as text."""
    data = _get_bytes(url)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = zf.namelist()[0]
        return zf.read(name).decode("utf-8", errors="replace")


def parse_french_csv(text: str) -> pd.DataFrame:
    """Parse a French library CSV text block into a DataFrame.

    The library files have comment lines first, then a header line whose
    first field is empty (the date column), then data lines that start with
    an 8-digit date. Parsing stops at the first non-data line, so only the
    first block of multi-block files (e.g. 12 industry value weight) is
    returned. Values stay in percent here; callers convert units.
    """
    lines = [line.strip() for line in text.splitlines()]
    header_idx = -1
    for i, line in enumerate(lines):
        if _DATA_LINE.match(line):
            break
        if line.startswith(",") and any(ch.isalpha() for ch in line[1:]):
            header_idx = i
    if header_idx < 0:
        raise ValueError("no French CSV header line found")
    columns = [c.strip() for c in lines[header_idx].split(",")[1:]]
    rows: list[list[float]] = []
    dates: list[pd.Timestamp] = []
    for line in lines[header_idx + 1 :]:
        if not _DATA_LINE.match(line):
            break
        parts = [p.strip() for p in line.split(",")]
        try:
            dates.append(pd.to_datetime(parts[0], format="%Y%m%d"))
            rows.append([float(x) for x in parts[1:]])
        except ValueError:
            break
    frame = pd.DataFrame(
        rows, index=pd.DatetimeIndex(dates, name="date"), columns=columns
    )
    return frame


def to_decimal(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert percent columns to decimal units and sentinels to NaN."""
    out = frame.replace(SENTINELS, np.nan).astype(float)
    return out / 100.0


def _industry_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename 12 industry portfolio columns positionally to ind1..ind12."""
    return frame.rename(columns={c: f"ind{i + 1}" for i, c in enumerate(frame.columns)})


def load_french_factors() -> dict[str, pd.DataFrame]:
    """Download and parse all four daily French files.

    Returns a dict keyed by ff5, mom, strev, ind12. All DataFrames carry a
    business-day DatetimeIndex named date, decimal units, and NaN for
    missing values.
    """
    ff5_raw = parse_french_csv(download_french_zip(FF_URLS["ff5"]))
    ff5 = to_decimal(ff5_raw).rename(
        columns={
            "Mkt-RF": "mkt_rf",
            "SMB": "smb",
            "HML": "hml",
            "RMW": "rmw",
            "CMA": "cma",
            "RF": "rf",
        }
    )
    mom = to_decimal(parse_french_csv(download_french_zip(FF_URLS["mom"])))
    mom = mom.rename(columns={c: "mom" for c in mom.columns}).iloc[:, [0]]
    strev = to_decimal(parse_french_csv(download_french_zip(FF_URLS["strev"])))
    strev = strev.rename(columns={c: "st_rev" for c in strev.columns}).iloc[:, [0]]
    ind12 = to_decimal(
        _industry_columns(parse_french_csv(download_french_zip(FF_URLS["ind12"])))
    )
    for frame in (ff5, mom, strev, ind12):
        frame.index = pd.DatetimeIndex(frame.index, name="date")
    return {"ff5": ff5, "mom": mom, "strev": strev, "ind12": ind12}


def merge_factors(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merge the four French files into one wide decimal DataFrame.

    Index is the union of business days across the files; files that start
    later leave NaN before their first row. Column order is fixed.
    """
    columns = [
        "mkt_rf",
        "smb",
        "hml",
        "rmw",
        "cma",
        "rf",
        "mom",
        "st_rev",
        "ind1",
        "ind2",
        "ind3",
        "ind4",
        "ind5",
        "ind6",
        "ind7",
        "ind8",
        "ind9",
        "ind10",
        "ind11",
        "ind12",
    ]
    out = pd.concat([frames[key] for key in ("ff5", "mom", "strev", "ind12")], axis=1)
    out = out.reindex(columns=columns)
    out = out.sort_index()
    out.index.name = "date"
    return out


FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"


def download_dtb3(timeout: int = 90) -> pd.Series | None:
    """Download the FRED DTB3 daily series; None when unreachable."""
    try:
        resp = requests.get(FRED_URL, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    frame = pd.read_csv(io.StringIO(resp.text), parse_dates=["observation_date"])
    out = frame.set_index("observation_date")["DTB3"]
    return pd.to_numeric(out, errors="coerce").dropna()


def cross_check_rf(rf: pd.Series, dtb3: pd.Series) -> dict[str, float] | None:
    """Cross-check the FF RF daily rate against FRED DTB3.

    rf and dtb3 are daily decimals. Returns correlation and mean absolute
    difference in basis points per day, or None when either series is
    empty (the documented null for an unavailable source).
    """
    both = pd.concat(
        [rf.rename("rf"), dtb3.rename("dtb3")], axis=1, join="inner"
    ).dropna()
    if len(both) < 10:
        return None
    diff_bp = ((both["rf"] - both["dtb3"]).abs() * 10_000.0).mean()
    return {
        "correlation": float(both["rf"].corr(both["dtb3"])),
        "mean_diff_bp": float(diff_bp),
        "n_obs": int(len(both)),
    }


def build_factors_artifact(
    frames: dict[str, pd.DataFrame], start: str = "2010-01-04"
) -> pd.DataFrame:
    """Clip the merged factors to the universe window."""
    merged = merge_factors(frames)
    return merged.loc[merged.index >= pd.Timestamp(start)]
