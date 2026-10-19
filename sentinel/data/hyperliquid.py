"""Hyperliquid perpetuals (keyless public info API).

All requests are read-only POSTs to https://api.hyperliquid.xyz/info.
Funding on Hyperliquid is paid hourly; APR = hourly rate × 24 × 365.
Open interest is reported in base units, converted to USD with the mark price.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import streamlit as st

from sentinel.core.formatting import _safe_float
from sentinel.core.http import _post_robust_json

logger = logging.getLogger("sentinel.data")

INFO_URL = "https://api.hyperliquid.xyz/info"
HOURS_PER_YEAR = 24 * 365
CANDLE_INTERVALS = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def _info(payload: dict, timeout: int = 10):
    return _post_robust_json(INFO_URL, payload, timeout=timeout)


@st.cache_data(ttl=3600, show_spinner=False)
def hl_perp_dexs() -> list[str]:
    """Builder-deployed (HIP-3) perp DEX names; '' is the main Hyperliquid DEX."""
    data = _info({"type": "perpDexs"})
    names = [""]
    for d in data or []:
        if isinstance(d, dict) and d.get("name"):
            names.append(str(d["name"]))
    return names


@st.cache_data(ttl=15, show_spinner=False)
def hl_markets(dex: str = "") -> pd.DataFrame:
    """One row per listed perp: mark, 24h change, volume, OI, funding, premium."""
    payload = {"type": "metaAndAssetCtxs"}
    if dex:
        payload["dex"] = dex
    data = _info(payload)
    if not isinstance(data, list) or len(data) < 2:
        return pd.DataFrame()
    universe = (data[0] or {}).get("universe", []) or []
    ctxs = data[1] or []
    rows = []
    for meta, ctx in zip(universe, ctxs):
        if not isinstance(meta, dict) or not isinstance(ctx, dict) or meta.get("isDelisted"):
            continue
        mark = _safe_float(ctx.get("markPx"), None)
        if not mark:
            continue
        prev = _safe_float(ctx.get("prevDayPx"), None)
        oracle = _safe_float(ctx.get("oraclePx"), None)
        funding = _safe_float(ctx.get("funding"), 0.0)
        oi_base = _safe_float(ctx.get("openInterest"), 0.0)
        name = str(meta.get("name", ""))
        rows.append({
            "coin": name,
            "symbol": name.split(":", 1)[-1],
            "mark": mark,
            "oracle": oracle,
            "prev_day": prev,
            "chg_24h_pct": (mark / prev - 1) * 100 if prev else None,
            "volume_24h_usd": _safe_float(ctx.get("dayNtlVlm"), 0.0),
            "oi_base": oi_base,
            "oi_usd": oi_base * mark,
            "funding_1h_pct": funding * 100,
            "funding_apr_pct": funding * HOURS_PER_YEAR * 100,
            "premium_pct": _safe_float(ctx.get("premium"), 0.0) * 100,
            "basis_pct": (mark / oracle - 1) * 100 if oracle else None,
            "max_leverage": int(_safe_float(meta.get("maxLeverage"), 0)),
            "sz_decimals": int(_safe_float(meta.get("szDecimals"), 0)),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("volume_24h_usd", ascending=False).reset_index(drop=True)
    return df


def hl_summary(df: pd.DataFrame) -> dict:
    """Aggregate stats for a markets frame (OI-weighted funding)."""
    if df is None or df.empty:
        return {}
    oi = df["oi_usd"].sum()
    w_funding = (df["funding_apr_pct"] * df["oi_usd"]).sum() / oi if oi > 0 else None
    return {
        "markets": int(len(df)),
        "oi_usd": float(oi),
        "volume_24h_usd": float(df["volume_24h_usd"].sum()),
        "oi_weighted_funding_apr": float(w_funding) if w_funding is not None else None,
        "positive_funding_share": float((df["funding_1h_pct"] > 0).mean() * 100),
        "advancers": int((df["chg_24h_pct"] > 0).sum()),
        "decliners": int((df["chg_24h_pct"] < 0).sum()),
    }


@st.cache_data(ttl=30, show_spinner=False)
def hl_candles(coin: str, interval: str = "1h", bars: int = 200) -> pd.DataFrame:
    """OHLCV candles (UTC index). Hyperliquid caps a snapshot at 5000 bars."""
    minutes = CANDLE_INTERVALS.get(interval, 60)
    bars = max(10, min(int(bars), 5000))
    end = int(time.time() * 1000)
    start = end - bars * minutes * 60_000
    data = _info({"type": "candleSnapshot",
                  "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": end}}, timeout=15)
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    out = pd.DataFrame({
        "Open": pd.to_numeric(df["o"], errors="coerce"),
        "High": pd.to_numeric(df["h"], errors="coerce"),
        "Low": pd.to_numeric(df["l"], errors="coerce"),
        "Close": pd.to_numeric(df["c"], errors="coerce"),
        "Volume": pd.to_numeric(df["v"], errors="coerce"),
    })
    out.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return out.dropna()


@st.cache_data(ttl=300, show_spinner=False)
def hl_funding_history(coin: str, days: int = 7) -> pd.DataFrame:
    """Hourly funding prints for the last *days* (rate in %/hour and APR %)."""
    start = int(time.time() * 1000) - int(days) * 86_400_000
    data = _info({"type": "fundingHistory", "coin": coin, "startTime": start}, timeout=15)
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    rate = pd.to_numeric(df["fundingRate"], errors="coerce")
    out = pd.DataFrame({
        "funding_1h_pct": rate * 100,
        "funding_apr_pct": rate * HOURS_PER_YEAR * 100,
        "premium_pct": pd.to_numeric(df.get("premium"), errors="coerce") * 100,
    })
    out.index = pd.to_datetime(df["time"], unit="ms", utc=True)
    return out.dropna(subset=["funding_1h_pct"]).sort_index()


@st.cache_data(ttl=5, show_spinner=False)
def hl_order_book(coin: str) -> dict:
    """Top-of-book L2 snapshot: bids/asks DataFrames (px, sz, cumulative), spread, imbalance."""
    data = _info({"type": "l2Book", "coin": coin})
    levels = (data or {}).get("levels") if isinstance(data, dict) else None
    if not levels or len(levels) < 2:
        return {}

    def _side(rows):
        df = pd.DataFrame(rows or [])
        if df.empty:
            return pd.DataFrame(columns=["px", "sz", "n", "cum_sz", "cum_usd"])
        df["px"] = pd.to_numeric(df["px"], errors="coerce")
        df["sz"] = pd.to_numeric(df["sz"], errors="coerce")
        df["n"] = pd.to_numeric(df.get("n"), errors="coerce")
        df = df.dropna(subset=["px", "sz"])
        df["cum_sz"] = df["sz"].cumsum()
        df["cum_usd"] = (df["px"] * df["sz"]).cumsum()
        return df

    bids, asks = _side(levels[0]), _side(levels[1])
    if bids.empty or asks.empty:
        return {}
    best_bid, best_ask = float(bids["px"].iloc[0]), float(asks["px"].iloc[0])
    mid = (best_bid + best_ask) / 2
    bid_usd, ask_usd = float(bids["cum_usd"].iloc[-1]), float(asks["cum_usd"].iloc[-1])
    return {
        "bids": bids, "asks": asks, "best_bid": best_bid, "best_ask": best_ask, "mid": mid,
        "spread_bps": (best_ask - best_bid) / mid * 1e4 if mid else None,
        "imbalance_pct": (bid_usd - ask_usd) / (bid_usd + ask_usd) * 100 if (bid_usd + ask_usd) else None,
        "bid_depth_usd": bid_usd, "ask_depth_usd": ask_usd,
    }


@st.cache_data(ttl=5, show_spinner=False)
def hl_recent_trades(coin: str) -> pd.DataFrame:
    """Latest public prints (wallet addresses intentionally dropped)."""
    data = _info({"type": "recentTrades", "coin": coin})
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    out = pd.DataFrame({
        "time": pd.to_datetime(df["time"], unit="ms", utc=True),
        "side": df["side"].map({"B": "BUY", "A": "SELL"}).fillna(df["side"]),
        "px": pd.to_numeric(df["px"], errors="coerce"),
        "sz": pd.to_numeric(df["sz"], errors="coerce"),
    })
    out["usd"] = out["px"] * out["sz"]
    return out.sort_values("time", ascending=False).reset_index(drop=True)
