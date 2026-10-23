"""Trend breadth for the largest US stocks: % above 50/200-day averages and 52-week highs/lows.

Universe = the 500 largest US listings by market cap from the Nasdaq screener (an
S&P 500 proxy that needs no constituent list). Two years of daily closes are
downloaded in one yfinance batch and cached for six hours.
"""
from __future__ import annotations

import logging

import pandas as pd

from sentinel.core.cache import stale_cached_source
from sentinel.core.http import _yf_semaphore, yf
from sentinel.data.screener import large_caps, market_screener

logger = logging.getLogger("sentinel.data")


@stale_cached_source(ttl=6 * 3600, retry_ttl=600)
def breadth_history(n: int = 500) -> dict:
    """{"daily": DataFrame[date → pct50, pct200, highs, lows, n], "highs": [...], "lows": [...]} or {}."""
    if yf is None:
        return {}
    uni = large_caps(market_screener(), n, min_cap=0)
    if uni.empty:
        return {}
    tickers = uni["symbol"].tolist()
    try:
        with _yf_semaphore:
            raw = yf.download(tickers, period="2y", interval="1d", auto_adjust=True, progress=False, threads=True)
    except Exception as e:
        logger.warning("breadth download failed: %s", e)
        return {}
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all").dropna(axis=1, thresh=260)  # need ~a year of history per stock
    if closes.empty or len(closes) < 260:
        return {}
    closes = closes.ffill(limit=3)
    ma50, ma200 = closes.rolling(50).mean(), closes.rolling(200).mean()
    hi, lo = closes.rolling(252, min_periods=240).max(), closes.rolling(252, min_periods=240).min()
    valid50, valid200 = ma50.notna() & closes.notna(), ma200.notna() & closes.notna()
    validhl = hi.notna() & closes.notna()

    def share(cond, valid):
        num = (cond & valid).astype(float).sum(axis=1)
        den = valid.astype(float).sum(axis=1).replace(0.0, float("nan"))
        return num / den * 100

    daily = pd.DataFrame({
        "pct50": share(closes > ma50, valid50),
        "pct200": share(closes > ma200, valid200),
        "highs": ((closes >= hi) & validhl).astype(float).sum(axis=1),
        "lows": ((closes <= lo) & validhl).astype(float).sum(axis=1),
        "n": closes.notna().astype(float).sum(axis=1),
    }).dropna().tail(260)
    last = closes.iloc[-1]
    meta = uni.set_index("symbol")
    def _names(mask):
        syms = [s for s in last.index[mask.reindex(last.index, fill_value=False)]]
        rows = meta.reindex(syms).dropna(subset=["mcap"]).sort_values("mcap", ascending=False)
        return [{"symbol": s, "name": r["name"], "sector": r["sector"], "pct": r["pct"]} for s, r in rows.iterrows()]
    return {
        "daily": daily,
        "highs": _names(last >= hi.iloc[-1]),
        "lows": _names(last <= lo.iloc[-1]),
        "universe": int(closes.shape[1]),
        "as_of": closes.index[-1].strftime("%Y-%m-%d"),
    }
