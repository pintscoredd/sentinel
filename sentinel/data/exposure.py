"""Dealer exposure analytics from CBOE delayed chains (keyless): GEX, DEX, VEX.

Conventions (the common "SpotGamma/SqueezeMetrics-style" assumption):
customers are net long calls and net long puts, so dealers are short both.
Dealer gamma is then reported as +call gamma − put gamma, so positive
exposure means dealer hedging dampens moves and negative amplifies them.

Units:
* GEX: $ change in dealer delta per 1% move in the underlying.
* DEX: $ notional delta of open interest.
* VEX: $ change in dealer delta per 1 vol-point rise in IV.

All three are estimates. Real dealer positioning is not public.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st

from sentinel.data.zero_dte import fetch_cboe_gex

_SQRT2PI = math.sqrt(2 * math.pi)


def _npdf(x):
    return np.exp(-0.5 * x * x) / _SQRT2PI


@st.cache_data(ttl=300, show_spinner=False)
def exposure_chain(ticker: str = "SPX", r: float = 0.04):
    """(spot, contracts DataFrame) with per-contract GEX/DEX/VEX columns, or (None, None)."""
    spot, df = fetch_cboe_gex(ticker)
    if spot is None or df is None or df.empty:
        return None, None
    now = pd.Timestamp.now(tz="US/Eastern").tz_localize(None)
    df = df[df["expiration"] >= now.normalize()].copy()
    df = df[(df["open_interest"] > 0) & (df["iv"] > 0)]
    if df.empty:
        return spot, None
    # Expiry at 16:00 ET; floor at ~1 hour so same-day contracts stay finite.
    T = ((df["expiration"] + pd.Timedelta(hours=16)) - now).dt.total_seconds() / (365.0 * 86400)
    df["T"] = T.clip(lower=1 / (365 * 24))
    sign = np.where(df["type"] == "C", 1.0, -1.0)
    oi100 = df["open_interest"] * 100
    sig, K = df["iv"].astype(float), df["strike"].astype(float)
    d1 = (np.log(spot / K) + (r + 0.5 * sig ** 2) * df["T"]) / (sig * np.sqrt(df["T"]))
    d2 = d1 - sig * np.sqrt(df["T"])
    # CBOE rounds gamma to 4 decimals (crude for SPX); re-derive it from the quoted IV.
    df["gamma"] = _npdf(d1) / (spot * sig * np.sqrt(df["T"]))
    df["gex"] = sign * df["gamma"] * oi100 * spot * spot * 0.01
    df["dex"] = df["delta"] * oi100 * spot
    vanna = -_npdf(d1) * d2 / sig                       # dDelta/dSigma (per 1.00 vol)
    df["vex"] = sign * vanna * oi100 * spot * 0.01      # per 1 vol point
    df["dte"] = (df["expiration"] - now.normalize()).dt.days
    return float(spot), df.reset_index(drop=True)


def by_strike(df, spot, metric="gex", strike_pct=0.05, max_dte=None):
    """Net exposure per strike within ±strike_pct of spot, split into call/put parts ($)."""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[(df["strike"] >= spot * (1 - strike_pct)) & (df["strike"] <= spot * (1 + strike_pct))]
    if max_dte is not None:
        d = d[d["dte"] <= max_dte]
    if d.empty:
        return pd.DataFrame()
    g = d.pivot_table(index="strike", columns="type", values=metric, aggfunc="sum", fill_value=0.0)
    for c in ("C", "P"):
        if c not in g:
            g[c] = 0.0
    g["net"] = g["C"] + g["P"]
    return g.reset_index().rename(columns={"C": "call", "P": "put"})


def heatmap(df, spot, metric="gex", strike_pct=0.04, n_expiries=10, max_strikes=40):
    """Strike × expiry matrix of net exposure ($M). Rows = strikes (ascending), columns = expiries."""
    if df is None or df.empty:
        return pd.DataFrame()
    exps = sorted(df["expiration"].unique())[:n_expiries]
    d = df[df["expiration"].isin(exps)
           & (df["strike"] >= spot * (1 - strike_pct)) & (df["strike"] <= spot * (1 + strike_pct))]
    if d.empty:
        return pd.DataFrame()
    m = d.pivot_table(index="strike", columns="expiration", values=metric, aggfunc="sum", fill_value=0.0) / 1e6
    if len(m) > max_strikes:  # keep the strikes with the most activity, then restore order
        keep = m.abs().sum(axis=1).nlargest(max_strikes).index
        m = m.loc[sorted(keep)]
    m.columns = [pd.Timestamp(c).strftime("%b %d") for c in m.columns]
    return m.sort_index()  # ascending: plotly draws the first category at the bottom, so high strikes end up on top


def gamma_profile(df, spot, r=0.04, span=0.08, points=61, max_dte=90):
    """Total dealer GEX if spot moved to each level (gamma re-priced with Black-Scholes).

    Returns (levels, total_gex_$bn, flip_level or None). The flip is where the curve
    crosses zero: below it dealers are short gamma (moves get amplified).
    """
    if df is None or df.empty:
        return np.array([]), np.array([]), None
    d = df[(df["dte"] <= max_dte) & (df["strike"] >= spot * 0.7) & (df["strike"] <= spot * 1.3)]
    if d.empty:
        return np.array([]), np.array([]), None
    levels = np.linspace(spot * (1 - span), spot * (1 + span), points)
    K = d["strike"].to_numpy()[None, :]
    sig = d["iv"].to_numpy()[None, :]
    T = d["T"].to_numpy()[None, :]
    w = (np.where(d["type"] == "C", 1.0, -1.0) * d["open_interest"].to_numpy() * 100)[None, :]
    S = levels[:, None]
    d1 = (np.log(S / K) + (r + 0.5 * sig ** 2) * T) / (sig * np.sqrt(T))
    gamma = _npdf(d1) / (S * sig * np.sqrt(T))
    total = (w * gamma * S * S * 0.01).sum(axis=1) / 1e9
    flip = None
    sgn = np.sign(total)
    idx = np.where(np.diff(sgn) != 0)[0]
    if len(idx):
        # Crossing nearest to spot, linearly interpolated.
        i = idx[np.argmin(np.abs(levels[idx] - spot))]
        x0, x1, y0, y1 = levels[i], levels[i + 1], total[i], total[i + 1]
        flip = float(x0 - y0 * (x1 - x0) / (y1 - y0)) if y1 != y0 else float(x0)
    return levels, total, flip


def key_levels(df, spot, strike_pct=0.10, max_dte=60):
    """Call wall, put wall, net totals and the largest-OI strikes."""
    if df is None or df.empty:
        return {}
    bs = by_strike(df, spot, "gex", strike_pct, max_dte)
    if bs.empty:
        return {}
    calls, puts = bs[bs["call"] > 0], bs[bs["put"] < 0]
    out = {
        "call_wall": float(calls.loc[calls["call"].idxmax(), "strike"]) if not calls.empty else None,
        "put_wall": float(puts.loc[puts["put"].idxmin(), "strike"]) if not puts.empty else None,
        "net_gex_bn": float(df["gex"].sum() / 1e9),
        "net_dex_bn": float(df["dex"].sum() / 1e9),
        "net_vex_m": float(df["vex"].sum() / 1e6),
    }
    near = df[df["dte"] <= max_dte]
    oi = near.groupby(["strike", "type"])["open_interest"].sum().reset_index()
    for t, k in (("C", "top_call_oi"), ("P", "top_put_oi")):
        sub = oi[oi["type"] == t]
        out[k] = float(sub.loc[sub["open_interest"].idxmax(), "strike"]) if not sub.empty else None
    return out
