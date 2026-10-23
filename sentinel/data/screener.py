"""Whole-market snapshot from Nasdaq's public screener (keyless, ~7,000 US listings).

One request returns every listed stock with sector, industry, market cap and the
day's change, which powers the heatmap, market breadth and top movers.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from sentinel.core.cache import stale_cached_source
from sentinel.core.http import _get_http_session
from sentinel.data.fundamentals import _NASDAQ_HEADERS

logger = logging.getLogger("sentinel.data")

_URL = "https://api.nasdaq.com/api/screener/stocks"
# Share classes / preferreds / units / warrants duplicate the common stock.
_SKIP_SYMBOL = re.compile(r"\^|[./](?:U|W|WS|R)$")
_SKIP_NAME = re.compile(r"Preferred|Depositary Shares representing|\bNotes?\b|Debentures|Warrants?\b|\bRights?\b|"
                        r"\bUnits?\b(?!.*Partners)|\d+(?:\.\d+)?%|Fund Inc|Trust Units|\bETN\b", re.I)


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(r"[$,%]", "", regex=True).str.strip(), errors="coerce")


@stale_cached_source(ttl=300, retry_ttl=60)
def market_screener() -> pd.DataFrame:
    """Columns: symbol, name, sector, industry, price, change, pct, volume, mcap."""
    try:
        r = _get_http_session().get(_URL, headers=_NASDAQ_HEADERS, timeout=20,
                                    params={"tableonly": "true", "limit": 25, "offset": 0, "download": "true"})
        r.raise_for_status()
        rows = ((r.json() or {}).get("data") or {}).get("rows") or []
    except Exception as e:
        logger.warning("Nasdaq screener failed: %s", e)
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "symbol": df["symbol"].astype(str).str.strip().str.replace("/", "-", regex=False),  # BRK/B → BRK-B (Yahoo style)
        "name": df["name"].astype(str).str.replace(r"\s+(Common Stock|Class [A-C].*|Ordinary Shares.*|American Depositary.*)$",
                                                     "", regex=True).str.strip(),
        "sector": df["sector"].replace("", "Other").fillna("Other"),
        "industry": df["industry"].fillna(""),
        "price": _num(df["lastsale"]), "change": _num(df["netchange"]), "pct": _num(df["pctchange"]),
        "volume": _num(df["volume"]), "mcap": _num(df["marketCap"]),
    })
    raw_names = df.loc[out.index, "name"].astype(str)
    out = out[~out["symbol"].str.contains(_SKIP_SYMBOL) & ~raw_names.str.contains(_SKIP_NAME)]
    out = out.dropna(subset=["price", "pct"])
    out = out[(out["price"] > 0) & (out["pct"].abs() < 500)]
    # Nasdaq leaves a few large listings without a sector.
    out.loc[out["symbol"].isin(["BRK-A", "BRK-B"]), "sector"] = "Finance"
    out.loc[out["symbol"] == "KSPI", "sector"] = "Finance"
    # Keep one share class per company (GOOG/GOOGL, BRK/A–B): the larger by volume.
    out = out.sort_values("volume", ascending=False).drop_duplicates("name").reset_index(drop=True)
    return out


def large_caps(df: pd.DataFrame, n: int = 200, min_cap: float = 2e9) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[(df["mcap"] >= min_cap) & (df["sector"] != "Other")]
    return d.nlargest(n, "mcap").reset_index(drop=True)


def breadth(df: pd.DataFrame, min_cap: float = 3e8) -> dict:
    """Advance/decline stats over listed stocks above *min_cap* (filters out micro-cap noise)."""
    if df is None or df.empty:
        return {}
    d = df[df["mcap"] >= min_cap]
    up, down = int((d["pct"] > 0).sum()), int((d["pct"] < 0).sum())
    cap = d["mcap"].sum()
    return {
        "n": len(d), "up": up, "down": down, "flat": len(d) - up - down,
        "ad_ratio": up / down if down else None,
        "pct_up": up / len(d) * 100 if len(d) else 0.0,
        "big_up": int((d["pct"] >= 4).sum()), "big_down": int((d["pct"] <= -4).sum()),
        "cap_weighted": float((d["pct"] * d["mcap"]).sum() / cap) if cap else 0.0,
        "equal_weighted": float(d["pct"].clip(-50, 50).mean()),
    }


def sector_table(df: pd.DataFrame, min_cap: float = 3e8) -> pd.DataFrame:
    """Cap-weighted day change and breadth per sector."""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[(df["mcap"] >= min_cap) & (df["sector"] != "Other")].copy()
    d["w"] = d["pct"] * d["mcap"]
    g = d.groupby("sector").agg(mcap=("mcap", "sum"), w=("w", "sum"), n=("symbol", "size"),
                                up=("pct", lambda s: int((s > 0).sum())))
    g["pct"] = g["w"] / g["mcap"]
    g["pct_up"] = g["up"] / g["n"] * 100
    return g.drop(columns="w").sort_values("pct", ascending=False).reset_index()


def movers(df: pd.DataFrame, n: int = 10, min_cap: float = 1e10):
    """Biggest gainers/losers among stocks above *min_cap*."""
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()
    d = df[df["mcap"] >= min_cap]
    return d.nlargest(n, "pct").reset_index(drop=True), d.nsmallest(n, "pct").reset_index(drop=True)
