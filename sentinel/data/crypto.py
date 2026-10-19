"""Spot crypto (CoinGecko), sentiment, BTC ETF flow proxy."""
from __future__ import annotations

import logging

import numpy as np
import streamlit as st

from sentinel.core.http import (
    _fetch_robust_json, _yf_semaphore, yf,
)

from sentinel.config import ETF_TICKERS as _ETF_TICKERS
from sentinel.core.cache import stale_cached_source
from sentinel.data.market import _extract_ohlcv_frames

logger = logging.getLogger("sentinel.data")


@stale_cached_source(ttl=600, retry_ttl=60)
def fear_greed_crypto():
    """Alternative.me crypto fear & greed (value, label)."""
    d = _fetch_robust_json("https://api.alternative.me/fng/?limit=1", timeout=8)
    try:
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except (TypeError, KeyError, IndexError, ValueError):
        return None, None


# CoinGecko's keyless tier rate-limits aggressively; keep the last good snapshot
# instead of caching an empty response for the full TTL.
@stale_cached_source(ttl=300, retry_ttl=45)
def crypto_markets():
    data = _fetch_robust_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 20, "page": 1,
                "price_change_percentage": "24h"}, timeout=15)
    return data if isinstance(data, list) else []


@stale_cached_source(ttl=300, retry_ttl=45)
def crypto_global():
    data = _fetch_robust_json("https://api.coingecko.com/api/v3/global", timeout=8)
    return (data or {}).get("data", {}) if isinstance(data, dict) else {}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_btc_etf_flows():
    """Daily directional dollar-volume proxy per spot BTC ETF, $B (not true creations/redemptions)."""
    import pandas as _pd
    if yf is None:
        return None
    try:
        with _yf_semaphore:
            hist_all = yf.download(
                _ETF_TICKERS, period="35d", progress=False, threads=True,
                auto_adjust=True, group_by="column",
            )
        frames = _extract_ohlcv_frames(hist_all, _ETF_TICKERS)
        if len(_ETF_TICKERS) == 1 and not frames and hist_all is not None and not getattr(hist_all, "empty", True):
            frames[_ETF_TICKERS[0]] = hist_all

        all_data = {}
        for ticker in _ETF_TICKERS:
            try:
                hist = frames.get(ticker)
                if hist is None or getattr(hist, "empty", True) or len(hist) < 2:
                    continue
                close = hist["Close"] if "Close" in hist.columns else None
                if close is None:
                    continue
                high = hist["High"] if "High" in hist.columns else close
                low = hist["Low"] if "Low" in hist.columns else close
                vol = hist["Volume"] if "Volume" in hist.columns else None
                if vol is None:
                    continue
                prev_close = close.shift(1)
                vwap = (high + low + close) / 3.0
                direction = np.where((close - prev_close) >= 0, 1.0, -1.0)
                all_data[ticker] = ((vol * vwap * direction) / 1e9).iloc[1:]
            except Exception as e:
                logger.error("BTC ETF Fallback flow error for %s: %s", ticker, str(e))
                continue

        if not all_data:
            return None
        df = _pd.DataFrame(all_data)
        df.index = _pd.to_datetime(df.index)
        try:
            df.index = df.index.tz_localize(None)
        except (TypeError, ValueError):
            try:
                df.index = df.index.tz_convert(None)
            except Exception:
                pass
        df = df.fillna(0)
        df["Total"] = df[[c for c in df.columns if c in _ETF_TICKERS]].sum(axis=1)
        return df.tail(30) if len(df) > 0 else None
    except Exception:
        return None
