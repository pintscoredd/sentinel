"""SPX 0DTE: Alpaca chain, CBOE GEX, direction model, trade recommendation."""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz
import streamlit as st

from sentinel.core.http import (
    _fetch_robust_json, get_yf_ticker, yf,
)
from sentinel.core.formatting import _safe_float
from sentinel.core.secrets import unwrap_secret as _unwrap_secret
from sentinel.analytics.options_math import (
    bs_greeks_engine, compute_max_pain, compute_pcr, get_iv_newton, year_fraction_to_expiry,
    realized_volatility, rsi as wilder_rsi, macd as macd_line,
)

from sentinel.config import TRADING_DAYS_PER_YEAR
from sentinel.data.macro import get_risk_free_rate
from sentinel.data.market import get_spy_history, yahoo_quote

logger = logging.getLogger("sentinel.data")


def _alpaca_headers():
    import os
    try:
        key = _unwrap_secret(st.secrets.get("ALPACA_API_KEY", "")) or os.environ.get("ALPACA_API_KEY", "")
        secret = _unwrap_secret(st.secrets.get("ALPACA_SECRET_KEY", "")) or os.environ.get("ALPACA_SECRET_KEY", "")
    except Exception:
        key = os.environ.get("ALPACA_API_KEY", "")
        secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        return None
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }


@st.cache_data(ttl=30)
def get_stock_snapshot(symbol="SPY"):
    headers = _alpaca_headers()
    if not headers: return None
    try:
        data = _fetch_robust_json(f"https://data.alpaca.markets/v2/stocks/{symbol}/snapshot", headers=headers, timeout=10)
        latest_trade = data.get("latestTrade", {})
        daily_bar = data.get("dailyBar", {})
        minute_bar = data.get("minuteBar", {})
        return {
            "price": _safe_float(latest_trade.get("p")),
            "vwap": _safe_float(daily_bar.get("vw")),
            "open": _safe_float(daily_bar.get("o")),
            "high": _safe_float(daily_bar.get("h")),
            "low": _safe_float(daily_bar.get("l")),
            "close": _safe_float(daily_bar.get("c")),
            "volume": int(_safe_float(daily_bar.get("v"), 0)),
            "minute_vwap": _safe_float(minute_bar.get("vw")),
        }
    except Exception:
        return None


def get_spx_metrics():
    """SPX levels. Prefer live ^GSPC; scale SPY bars by live ratio (not fixed ×10).

    SPY ≈ SPX/10 only approximately. Using a live SPX/SPY ratio keeps
    VWAP/OHLC in index points without the ~0.5–2% fixed-multiple error.
    """
    spy_snap = get_stock_snapshot("SPY")
    try:
        spx_q = yahoo_quote("^GSPC")
        spx_price = round(spx_q["price"], 2) if spx_q and spx_q.get("price", 0) > 0 else None
    except Exception:
        spx_price = None

    if spy_snap and spy_snap.get("price", 0) > 0:
        spy_px = float(spy_snap["price"])
        # Live ratio when both available; else classic ~10x proxy
        if spx_price and spy_px > 0:
            ratio = spx_price / spy_px
        else:
            ratio = 10.0
        spot = spx_price if spx_price else round(spy_px * ratio, 2)
        return {
            "spot": spot,
            "vwap": round(float(spy_snap.get("vwap") or 0) * ratio, 2),
            "open": round(float(spy_snap.get("open") or 0) * ratio, 2),
            "high": round(float(spy_snap.get("high") or 0) * ratio, 2),
            "low": round(float(spy_snap.get("low") or 0) * ratio, 2),
            "volume": spy_snap.get("volume", 0),
            "spy_spot": spy_px,
            "spx_spy_ratio": round(ratio, 4),
        }
    if spx_price:
        return {
            "spot": spx_price, "vwap": spx_price, "open": 0, "high": 0, "low": 0,
            "volume": 0, "spy_spot": None, "spx_spy_ratio": 10.0,
        }
    return None


_OCC_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<ymd>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


def _parse_strike_from_symbol(sym: str) -> float:
    """OCC strike: last 8 digits = strike × 1000."""
    try:
        m = _OCC_RE.match(str(sym).replace(" ", "").upper())
        if m:
            return int(m.group("strike")) / 1000.0
        # Fallback: trailing 8 digits
        digits = re.sub(r"\D", "", str(sym)[-12:])
        if len(digits) >= 8:
            return int(digits[-8:]) / 1000.0
        return 0.0
    except Exception:
        return 0.0


def _parse_type_from_symbol(sym: str) -> str:
    """OCC right: C/P immediately before 8-digit strike (not first C/P in root)."""
    try:
        m = _OCC_RE.match(str(sym).replace(" ", "").upper())
        if m:
            return "call" if m.group("cp") == "C" else "put"
        # Fallback scan near the end only (avoids roots like PCAR, CAT)
        s = str(sym).upper()
        m2 = re.search(r"(\d{6})([CP])(\d{8})$", s)
        if m2:
            return "call" if m2.group(2) == "C" else "put"
        return "unknown"
    except Exception:
        return "unknown"


@st.cache_data(ttl=30)
def fetch_0dte_chain(underlying="SPY"):
    headers = _alpaca_headers()
    if not headers: return [], "No Alpaca API keys configured"

    snap = get_stock_snapshot(underlying)
    if not snap or snap["price"] <= 0: return [], "Could not fetch spot price"
    spot = snap["price"]
    today_str = datetime.today().strftime("%Y-%m-%d")

    try:
        c_data = _fetch_robust_json("https://paper-api.alpaca.markets/v2/options/contracts", 
                                    headers=headers, params={"underlying_symbols": underlying, "status": "active", "limit": 1000,
                                            "expiration_date_gte": today_str,
                                            "expiration_date_lte": (datetime.today() + timedelta(days=7)).strftime("%Y-%m-%d")}, timeout=10)
        if not c_data:
            logger.error("fetch_0dte_chain: Alpaca contracts endpoint returned None (timeout/circuit breaker)")
            return [], "Alpaca API unavailable — network timeout or circuit breaker tripped"
        dates = [c.get("expiration_date") for c in c_data.get("option_contracts", []) if c.get("expiration_date") and c.get("expiration_date") >= today_str]
        if not dates: return [], "No active option contracts found"
        target_expiry = sorted(list(set(dates)))[0]
    except Exception as e:
        return [], f"Error locating expiry: {str(e)}"

    try:
        url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{underlying}"
        params = {"feed": "indicative", "limit": 250, "expiration_date": target_expiry}
        data = _fetch_robust_json(url, headers=headers, params=params, timeout=15)
        if not data:
            logger.error("fetch_0dte_chain: Alpaca snapshots endpoint returned None")
            return [], "Alpaca snapshots API unavailable — network timeout or circuit breaker"
        snapshots = data.get("snapshots", {})
        seen_tokens = set()
        pages = 0

        while data is not None and data.get("next_page_token") and pages < 10:
            token = data["next_page_token"]
            if token in seen_tokens:
                break
            seen_tokens.add(token)
            params["page_token"] = token
            import time
            time.sleep(0.5)
            data = _fetch_robust_json(url, headers=headers, params=params, timeout=15)
            if data is not None:
                snapshots.update(data.get("snapshots", {}))
            else:
                logger.warning(f"fetch_0dte_chain: pagination page {pages+1} returned None, stopping")
                break
            pages += 1

        chain = []
        # Wider wing for GEX walls (±5%); 0DTE activity concentrates near spot
        lower_bound, upper_bound = spot * 0.95, spot * 1.05

        r_rate = get_risk_free_rate()
        # True residual time to equity close on expiry — not a fixed 0.5 day
        T_val = year_fraction_to_expiry(target_expiry)

        for sym, snap_data in snapshots.items():
            greeks = snap_data.get("greeks", {}) or {}
            quote = snap_data.get("latestQuote", {}) or {}
            trade = snap_data.get("latestTrade", {}) or {}
            strike = _parse_strike_from_symbol(sym)
            opt_type = _parse_type_from_symbol(sym)

            if opt_type == "unknown" or strike <= 0:
                continue
            if strike < lower_bound or strike > upper_bound:
                continue
            bid = _safe_float(quote.get("bp"))
            ask = _safe_float(quote.get("ap"))
            last = _safe_float(trade.get("p"))
            # Mid: prefer NBBO; never invent a mid from one-sided quotes alone
            # when spread is absurd (>50% of mid) — use last trade instead
            if bid > 0 and ask > 0 and ask >= bid:
                mid = round((bid + ask) / 2.0, 4)
                if mid > 0 and (ask - bid) / mid > 0.5 and last > 0:
                    mid = last
            elif last > 0:
                mid = last
            elif bid > 0:
                mid = bid
            elif ask > 0:
                mid = ask
            else:
                mid = 0.0

            calculated_iv = None
            if mid > 0:
                calculated_iv = get_iv_newton(spot, strike, T_val, r_rate, mid, opt_type)
            if calculated_iv is not None and calculated_iv > 0:
                bs_override = bs_greeks_engine(spot, strike, T_val, r_rate, calculated_iv, opt_type)
                final_iv = calculated_iv
                final_delta = bs_override["delta"]
                final_gamma = bs_override["gamma"]
                final_theta = bs_override["theta"]
                final_vega = bs_override["vega"]
            else:
                final_iv = _safe_float(snap_data.get("impliedVolatility") or greeks.get("iv"))
                final_delta = _safe_float(greeks.get("delta"))
                final_gamma = _safe_float(greeks.get("gamma"))
                final_theta = _safe_float(greeks.get("theta"))
                final_vega = _safe_float(greeks.get("vega"))

            chain.append({
                "symbol": sym, "strike": strike, "type": opt_type,
                "bid": bid, "ask": ask, "mid": mid, "last": last,
                "iv": final_iv,
                "delta": final_delta, "gamma": final_gamma,
                "theta": final_theta, "vega": final_vega,
                "oi": int(_safe_float(snap_data.get("openInterest", 0), 0)),
                "volume": int(_safe_float(trade.get("s", 0), 0)),
                "T": T_val,
            })
        chain.sort(key=lambda x: (x["strike"], 0 if x["type"] == "call" else 1))
        return chain, "OK"
    except Exception as e:
        return [], f"Error: {str(e)}"


def compute_gex_profile(chain, spot):
    """Gamma exposure by strike (SpotGamma-style dealer convention), pure numpy.

    GEX_$M = sign × OI × 100 × |γ| × S² × 0.01 / 1e6
      sign = +1 call / -1 put
    """
    if spot <= 0 or not chain:
        return {}
    try:
        strikes, ois, gammas, signs = [], [], [], []
        for opt in chain:
            try:
                k = float(opt["strike"])
                oi = float(opt.get("oi", 0) or 0)
                g = abs(float(opt.get("gamma", 0) or 0))
                t = opt.get("type", "")
            except (TypeError, ValueError, KeyError):
                continue
            if oi <= 0 or g <= 0:
                continue
            strikes.append(k)
            ois.append(oi)
            gammas.append(g)
            signs.append(1.0 if t == "call" else -1.0)
        if not strikes:
            return {}
        k = np.asarray(strikes, dtype=np.float64)
        gex = (
            np.asarray(signs, dtype=np.float64)
            * np.asarray(ois, dtype=np.float64)
            * 100.0
            * np.asarray(gammas, dtype=np.float64)
            * (float(spot) ** 2)
            * 0.01
            / 1_000_000.0
        )
        # Aggregate by strike
        order = np.argsort(k)
        k, gex = k[order], gex[order]
        uniq, inv = np.unique(k, return_inverse=True)
        sums = np.zeros(uniq.size, dtype=np.float64)
        np.add.at(sums, inv, gex)
        return {float(uniq[i]): float(sums[i]) for i in range(uniq.size)}
    except Exception as e:
        logger.error("compute_gex_profile error: %s", e)
        return {}


def find_gamma_flip(gex_profile):
    """Strike where cumulative dealer GEX (summed from the lowest strike up) crosses zero.

    The per-strike sign flips constantly (calls above spot, puts below); the
    level that matters is where *aggregate* gamma changes sign. Returns None
    when the cumulative profile never crosses zero inside the strike window.
    """
    if not gex_profile:
        return None
    strikes = sorted(gex_profile)
    cum = np.cumsum([gex_profile[k] for k in strikes])
    for i in range(1, len(strikes)):
        c0, c1 = cum[i - 1], cum[i]
        if c0 == 0:
            return float(strikes[i - 1])
        if c0 * c1 < 0:
            t = -c0 / (c1 - c0)
            return float(strikes[i - 1] + t * (strikes[i] - strikes[i - 1]))
    return None


def compute_spx_direction(chain, spx_metrics, vix_data, gex_profile=None):
    """Multi-factor quantitative SPX daily direction predictor.
    
    Combines 8 weighted signals rooted in options market microstructure:
    1. Gamma Regime       — positive gamma = mean-reverting (dealer hedging dampens moves)
    2. Net GEX Tilt       — call vs put gamma imbalance shows directional flow
    3. Typical Price Pos  — daily (H+L+C)/3 anchor; reversion signal
    4. Put/Call Ratio     — sentiment skew from OI distribution
    5. Max Pain Gravity   — expiry pin effect attracts price
    6. Vol Regime         — combined VIX term structure + level (2×2 grid)
    7. RSI(14)            — momentum oscillator: overbought/oversold
    8. MACD(12,26,9)      — trend following momentum signal
    
    Returns dict with direction, confidence, score, and per-signal breakdown.
    """
    if not chain or not spx_metrics:
        return None

    spot = spx_metrics["spot"]
    vwap = spx_metrics["vwap"]
    vix = (vix_data or {}).get("vix") or 20.0
    contango = (vix_data or {}).get("contango")

    # Chain is typically SPY 0DTE — GEX must use SPY spot, not SPX.
    # Scale strikes → SPX via live ratio (not hard-coded ×10).
    spy_spot = (spx_metrics or {}).get("spy_spot") or (spot / 10.0 if spot else 0)
    ratio = (spx_metrics or {}).get("spx_spy_ratio") or (spot / spy_spot if spy_spot else 10.0)
    if gex_profile is None and spy_spot > 0:
        gex_profile = compute_gex_profile(chain, spy_spot)

    gamma_flip_spy = find_gamma_flip(gex_profile) if gex_profile else None
    gamma_flip = (gamma_flip_spy * ratio) if gamma_flip_spy else None
    max_pain_spy = compute_max_pain(chain)
    max_pain = (max_pain_spy * ratio) if max_pain_spy else None
    pcr = compute_pcr(chain)

    daily_em = spot * (vix / 100) / (TRADING_DAYS_PER_YEAR ** 0.5)

    score = 0.0
    signals = []

    if gex_profile:
        net_gex = sum(gex_profile.values())
        if net_gex > 0:
            contrib = 2.5
            signals.append(("Gamma Regime", f"Net +{net_gex:.1f}M", contrib,
                           "POSITIVE — Dealers hedge → dampened, mean-reverting", "#3FCF8E"))
        elif net_gex < -0.5:
            contrib = -2.5
            signals.append(("Gamma Regime", f"Net {net_gex:.1f}M", contrib,
                           "NEGATIVE — Dealers amplify → trending, volatile", "#F2555A"))
        else:
            contrib = 0.0
            signals.append(("Gamma Regime", f"Net {net_gex:.1f}M", contrib,
                           "NEUTRAL — Near gamma-neutral zone", "#BDBDBD"))
        score += contrib

    if gex_profile and gamma_flip and spy_spot > 0:
        # Compare SPY-space strikes to SPY spot for tilt
        above_gex = sum(v for k, v in gex_profile.items() if k > spy_spot)
        below_gex = sum(v for k, v in gex_profile.items() if k < spy_spot)
        total_abs = abs(above_gex) + abs(below_gex)
        if total_abs > 0:
            if spot > gamma_flip:
                contrib = 1.5
                signals.append(("GEX Tilt", f"Above Gamma Flip (Δ{spot-gamma_flip:+.0f})", contrib,
                               "BULLISH — Spot above dealer flip point", "#3FCF8E"))
            else:
                contrib = -1.5
                signals.append(("GEX Tilt", f"Below Gamma Flip (Δ{spot-gamma_flip:+.0f})", contrib,
                               "BEARISH — Spot below dealer flip point", "#F2555A"))
            score += contrib

    vwap_dev = ((spot - vwap) / vwap * 100) if vwap else 0.0
    if abs(vwap_dev) > 0.05:
        if vwap_dev > 0:
            contrib = min(vwap_dev * 8, 2.5)
            signals.append(("VWAP Position", f"{vwap_dev:+.2f}% above", contrib,
                           f"BULLISH — Spot {spot:,.0f} above session VWAP {vwap:,.0f}", "#3FCF8E"))
        else:
            contrib = max(vwap_dev * 8, -2.5)
            signals.append(("VWAP Position", f"{vwap_dev:+.2f}% below", contrib,
                           f"BEARISH — Spot {spot:,.0f} below session VWAP {vwap:,.0f}", "#F2555A"))
        score += contrib
    else:
        signals.append(("VWAP Position", f"{vwap_dev:+.2f}%", 0.0,
                       "NEUTRAL — Spot at VWAP", "#8A8A8A"))

    if pcr is not None:
        if pcr < 0.7:
            contrib = 2.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "BULLISH — Heavy call buying, strong risk appetite", "#3FCF8E"))
        elif pcr < 0.85:
            contrib = 1.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "MILDLY BULLISH — Moderate call skew", "#3FCF8E"))
        elif pcr > 1.3:
            contrib = -2.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "BEARISH — Heavy put hedging / fear", "#F2555A"))
        elif pcr > 1.0:
            contrib = -1.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "MILDLY BEARISH — Elevated put hedging", "#F2555A"))
        else:
            contrib = 0.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "NEUTRAL — Balanced call/put flow", "#8A8A8A"))
        score += contrib

    if max_pain:
        mp_dist = spot - max_pain
        mp_pct = mp_dist / spot * 100
        if abs(mp_pct) > 0.3:
            if mp_dist > 0:
                contrib = -1.5
                signals.append(("Max Pain Gravity", f"{max_pain:,.0f} ({mp_pct:+.1f}%)", contrib,
                               f"BEARISH PULL — Expiry magnet {abs(mp_dist):.0f} pts below spot", "#F2555A"))
            else:
                contrib = 1.5
                signals.append(("Max Pain Gravity", f"{max_pain:,.0f} ({mp_pct:+.1f}%)", contrib,
                               f"BULLISH PULL — Expiry magnet {abs(mp_dist):.0f} pts above spot", "#3FCF8E"))
            score += contrib
        else:
            signals.append(("Max Pain Gravity", f"{max_pain:,.0f} ({mp_pct:+.1f}%)", 0.0,
                           "PINNED — Spot near max pain; expect low range", "#8A8A8A"))

    if contango is not None:
        is_contango = bool(contango)
        if is_contango and vix < 20:
            contrib = 1.5
            vol_desc = "BULLISH — Contango + low vol: calm, risk-on regime"
            vol_color = "#3FCF8E"
            vol_val = f"Contango, VIX {vix:.1f}"
        elif is_contango and vix >= 20:
            contrib = 0.5
            vol_desc = "NEUTRAL — Contango but elevated VIX: cautious calm"
            vol_color = "#BDBDBD"
            vol_val = f"Contango, VIX {vix:.1f}"
        elif not is_contango and vix <= 30:
            contrib = -1.0
            vol_desc = "BEARISH — Backwardation + moderate VIX: stress building"
            vol_color = "#F2555A"
            vol_val = f"Backwardation, VIX {vix:.1f}"
        else:
            contrib = -2.0
            vol_desc = "CRISIS — Backwardation + extreme VIX: panic regime"
            vol_color = "#F2555A"
            vol_val = f"Backwardation, VIX {vix:.1f}"
        signals.append(("Vol Regime", vol_val, contrib, vol_desc, vol_color))
        score += contrib
    elif vix is not None:
        if vix < 15:
            contrib = 0.5
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "LOW VOL — Complacent, slight upward drift bias", "#3FCF8E"))
        elif vix <= 20:
            contrib = 0.0
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "NORMAL — Standard volatility regime", "#8A8A8A"))
        elif vix <= 30:
            contrib = -1.0
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "ELEVATED — Hedging spike", "#BDBDBD"))
        else:
            contrib = -1.5
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "CRISIS — Extreme fear", "#F2555A"))
        score += contrib

    try:
        spy_hist = get_spy_history().tail(90)
        if spy_hist is not None and len(spy_hist) >= 20:
            _closes = spy_hist["Close"]
            # Wilder RSI (shared implementation) — matches TradingView/Bloomberg
            rsi_val = wilder_rsi(_closes.values, 14)
            if rsi_val is None:
                rsi_val = 50.0

            # Realized vol vs VIX (IV premium/discount)
            rv20 = realized_volatility(_closes.values, window=20)
            if rv20 is not None and vix is not None:
                iv_rv_gap = (vix / 100.0) - rv20  # positive = IV rich vs realized
                if iv_rv_gap > 0.05:
                    contrib = -0.5
                    signals.append(("IV–RV", f"VIX {vix:.1f} vs RV20 {rv20*100:.1f}%", contrib,
                                   "IV RICH — Options premium elevated vs realized; mean-revert vol", "#BDBDBD"))
                    score += contrib
                elif iv_rv_gap < -0.02:
                    contrib = 0.5
                    signals.append(("IV–RV", f"VIX {vix:.1f} vs RV20 {rv20*100:.1f}%", contrib,
                                   "IV CHEAP — Realized outrunning implied; event risk underpriced", "#3FCF8E"))
                    score += contrib

            if rsi_val >= 70:
                contrib = -1.0
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "OVERBOUGHT — Momentum exhaustion, mean-reversion likely", "#F2555A"))
            elif rsi_val <= 30:
                contrib = 1.5
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "OVERSOLD — Extreme pessimism, bounce setup", "#3FCF8E"))
            elif 55 <= rsi_val < 70:
                contrib = 0.5
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "BULLISH MOMENTUM — Trend strength building", "#3FCF8E"))
            elif 30 < rsi_val <= 45:
                contrib = -0.5
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "BEARISH MOMENTUM — Selling pressure dominant", "#F2555A"))
            else:
                contrib = 0.0
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "NEUTRAL — No directional edge from momentum", "#8A8A8A"))
            score += contrib

            _m_line, _m_sig, _m_hist = macd_line(_closes.values)
            hist_now = float(_m_hist) if _m_hist is not None else 0.0
            # Prior histogram via full series for crossover detection
            _ema12 = _closes.ewm(span=12, adjust=False).mean()
            _ema26 = _closes.ewm(span=26, adjust=False).mean()
            _macd_s = _ema12 - _ema26
            _sig_s = _macd_s.ewm(span=9, adjust=False).mean()
            _histogram = _macd_s - _sig_s
            hist_prev = float(_histogram.iloc[-2]) if len(_histogram) >= 2 else 0.0
            if _m_hist is not None:
                hist_now = float(_m_hist)

            if hist_now > 0 and hist_prev <= 0:
                contrib = 1.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BULLISH CROSSOVER — MACD crossed above signal line", "#3FCF8E"))
            elif hist_now < 0 and hist_prev >= 0:
                contrib = -1.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BEARISH CROSSOVER — MACD crossed below signal line", "#F2555A"))
            elif hist_now > 0:
                contrib = 0.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BULLISH — MACD above signal, momentum positive", "#3FCF8E"))
            elif hist_now < 0:
                contrib = -0.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BEARISH — MACD below signal, momentum negative", "#F2555A"))
            else:
                contrib = 0.0
                signals.append(("MACD", "Flat", contrib,
                               "NEUTRAL — No MACD signal", "#8A8A8A"))
            score += contrib
    except Exception:
        pass

    max_possible = sum(abs(s[2]) for s in signals) or 1.0
    normalized = score / max_possible

    if score >= 4.0:
        direction, color = "BULLISH", "#3FCF8E"
        confidence = "HIGH" if score >= 6.5 else "MEDIUM"
    elif score >= 2.0:
        direction, color = "LEAN BULLISH", "#3FCF8E"
        confidence = "MEDIUM" if score >= 3.0 else "LOW"
    elif score <= -4.0:
        direction, color = "BEARISH", "#F2555A"
        confidence = "HIGH" if score <= -6.5 else "MEDIUM"
    elif score <= -2.0:
        direction, color = "LEAN BEARISH", "#F2555A"
        confidence = "MEDIUM" if score <= -3.0 else "LOW"
    else:
        direction, color = "NEUTRAL", "#BDBDBD"
        confidence = "LOW"

    if "BULLISH" in direction:
        range_low = f"{spot:,.0f}"
        range_high = f"{spot + daily_em * 0.6:,.0f}"
    elif "BEARISH" in direction:
        range_low = f"{spot - daily_em * 0.6:,.0f}"
        range_high = f"{spot:,.0f}"
    else:
        range_low = f"{spot - daily_em * 0.3:,.0f}"
        range_high = f"{spot + daily_em * 0.3:,.0f}"

    return {
        "direction": direction,
        "direction_color": color,
        "confidence": confidence,
        "score": round(score, 1),
        "max_score": round(max_possible, 1),
        "normalized": round(normalized, 2),
        "daily_em": round(daily_em, 1),
        "expected_range": f"{range_low} – {range_high}",
        "signals": signals,
        "spot": spot,
        "vwap": vwap,
        "gamma_flip": gamma_flip,
        "max_pain": max_pain,
        "pcr": pcr,
        "vix": vix,
    }


@st.cache_data(ttl=300)
def fetch_cboe_gex(ticker="SPX"):
    ticker = str(ticker).upper().lstrip("^")
    # Cash indexes live under an underscore prefix; stocks/ETFs do not (and 403 there).
    index = ticker in {"SPX", "NDX", "RUT", "VIX", "XSP", "DJX", "OEX", "XEO", "MRUT"}
    urls = [f"https://cdn.cboe.com/api/global/delayed_quotes/options/{'_' if index else ''}{ticker}.json"]
    for url in urls:
        try:
            data = _fetch_robust_json(url, timeout=15)
            if not data:
                continue
            raw = pd.DataFrame.from_dict(data)
            spot = float(raw.loc["current_price", "data"])
            opts = pd.DataFrame(raw.loc["options", "data"])

            parsed = opts["option"].astype(str).str.replace(" ", "", regex=False).str.upper().str.extract(
                r"(?P<root>[A-Z]+)(?P<ymd>\d{6})(?P<cp>[CP])(?P<k>\d{8})"
            )
            opts["type"] = parsed["cp"]
            opts["strike"] = pd.to_numeric(parsed["k"], errors="coerce") / 1000.0
            opts["expiration"] = pd.to_datetime(parsed["ymd"], format="%y%m%d", errors="coerce")
            opts = opts.dropna(subset=["type", "strike", "expiration"])

            for col in ("gamma", "open_interest", "iv", "delta", "theta", "vega"):
                if col in opts.columns:
                    opts[col] = pd.to_numeric(opts[col], errors="coerce").fillna(0)

            return spot, opts
        except Exception:
            continue
    return None, None


def compute_cboe_gex_profile(spot, option_df, expiry_limit_days=365, strike_pct=0.05):
    """Dealer GEX by strike ($M per 1% move). expiry_limit_days<=1 → nearest expiry only."""
    if option_df is None or option_df.empty or not spot or spot <= 0:
        return {}
    df = option_df
    today = pd.Timestamp.now(tz="US/Eastern").tz_localize(None).normalize()
    df = df[df["expiration"] >= today]
    if df.empty:
        return {}
    if expiry_limit_days <= 1:
        df = df[df["expiration"] == df["expiration"].min()]
    else:
        df = df[df["expiration"] <= today + pd.Timedelta(days=expiry_limit_days)]
    lo, hi = spot * (1 - strike_pct), spot * (1 + strike_pct)
    df = df[(df["strike"] >= lo) & (df["strike"] <= hi) & (df["gamma"] > 0) & (df["open_interest"] > 0)]
    if df.empty:
        return {}
    gex = spot * spot * 0.01 * df["gamma"] * df["open_interest"] * 100
    gex = np.where(df["type"] == "P", -gex, gex)
    by_strike = pd.Series(gex, index=df["strike"].values).groupby(level=0).sum() / 1_000_000
    return {float(k): float(v) for k, v in by_strike.items()}


def compute_cboe_total_gex(spot, option_df):
    """Net dealer GEX across all live expiries, $Bn per 1% move."""
    if option_df is None or option_df.empty or not spot or spot <= 0:
        return None
    today = pd.Timestamp.now(tz="US/Eastern").tz_localize(None).normalize()
    df = option_df[option_df["expiration"] >= today]
    gex = spot * spot * 0.01 * df["gamma"] * df["open_interest"] * 100
    gex = np.where(df["type"] == "P", -gex, gex)
    return round(float(np.sum(gex)) / 1e9, 3)


def compute_cboe_pcr(option_df):
    if option_df is None or option_df.empty: return None
    if "type" not in option_df.columns or "open_interest" not in option_df.columns: return None
    call_oi = option_df[option_df["type"] == "C"]["open_interest"].sum()
    put_oi  = option_df[option_df["type"] == "P"]["open_interest"].sum()
    return round(put_oi / call_oi, 2) if call_oi > 0 else None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_vix_data():
    result = {"vix": None, "vix9d": None, "contango": None}
    if yf is None: return result
    try:
        h = get_yf_ticker("^VIX").history(period="5d")
        if not h.empty: result["vix"] = round(h["Close"].iloc[-1], 2)
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    try:
        h9 = get_yf_ticker("^VIX9D").history(period="5d")
        if not h9.empty: result["vix9d"] = round(h9["Close"].iloc[-1], 2)
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    if result["vix"] is not None and result["vix9d"] is not None:
        result["contango"] = result["vix9d"] < result["vix"]
    return result


def _score_option(opt, chain_ivs, spot_spy, dte=0):
    """Score a single option contract for 0DTE selection."""
    import sys
    W1, W2, W3, W4, W5 = 0.25, 0.25, 0.20, 0.15, 0.15
    _EPS = sys.float_info.epsilon

    abs_delta = abs(opt.get("delta", 0))
    gamma     = abs(opt.get("gamma", 0))
    theta     = abs(opt.get("theta", 0))
    iv        = opt.get("iv", 0)
    bid, ask  = opt.get("bid", 0), opt.get("ask", 0)
    mid       = opt.get("mid", 0)
    vol, oi   = opt.get("volume", 0), max(opt.get("oi", 1), 1)

    if dte == 0:
        target_delta, sigma_delta = 0.40, 0.08
    elif dte <= 7:
        target_delta, sigma_delta = 0.35, 0.09
    else:
        target_delta, sigma_delta = 0.30, 0.10

    f1 = math.exp(-((abs_delta - target_delta) ** 2) / (2 * sigma_delta ** 2))

    gt_ratio = (gamma / theta) if theta > _EPS else 0.0
    f2 = 1 - 1 / (1 + gt_ratio)

    spread = ask - bid
    spread_pct = spread / mid if mid > 0 else 1.0
    f3 = max(0, 1 - spread_pct * 5)

    flow = vol / oi if oi > 0 else 0
    f4 = min(flow, 1.0)

    median_iv = sorted(chain_ivs)[len(chain_ivs) // 2] if chain_ivs else iv
    f5 = max(0, min(1, 2 - (iv / median_iv))) if median_iv > 0 else 0.5

    total = W1*f1 + W2*f2 + W3*f3 + W4*f4 + W5*f5

    breakdown = {
        "delta_score": round(f1, 3), "gt_score": round(f2, 3),
        "liq_score": round(f3, 3), "flow_score": round(f4, 3),
        "iv_score": round(f5, 3), "total": round(total, 4),
        "gt_ratio": round(gt_ratio, 2),
        "spread_pct": round(spread_pct * 100, 1),
        "flow_ratio": round(flow, 2),
    }
    return total, breakdown


def find_target_strike(chain, bias, dte=0):
    if bias == "bull": cands = [o for o in chain if o["type"] == "call" and 0.10 < o.get("delta", 0) < 0.50]
    else: cands = [o for o in chain if o["type"] == "put" and -0.50 < o.get("delta", 0) < -0.10]
    cands = [o for o in cands if o.get("mid", 0) > 0 and abs(o.get("gamma", 0)) > 0]
    if not cands: return None

    chain_ivs = [o["iv"] for o in chain if o.get("iv", 0) > 0]
    spot_spy = cands[0]["strike"]

    scored = []
    for o in cands:
        s, bd = _score_option(o, chain_ivs, spot_spy, dte)
        o_copy = dict(o)
        o_copy["_score"] = s
        o_copy["_breakdown"] = bd
        scored.append(o_copy)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[0]


def _spx_spy_ratio(spx_metrics, default=10.0):
    """Live SPX/SPY ratio — avoid the stale ×10 approximation."""
    try:
        r = float((spx_metrics or {}).get("spx_spy_ratio") or 0)
        if r > 0:
            return r
        spot = float((spx_metrics or {}).get("spot") or 0)
        spy = float((spx_metrics or {}).get("spy_spot") or 0)
        if spot > 0 and spy > 0:
            return spot / spy
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return default


def generate_recommendation(chain, spx_metrics, vix_data):
    if not chain or not spx_metrics:
        return None
    spot = spx_metrics["spot"]
    vwap = spx_metrics["vwap"]
    vix_val = (vix_data or {}).get("vix") or 20.0
    ratio = _spx_spy_ratio(spx_metrics)
    spy_spot = (spx_metrics or {}).get("spy_spot") or (spot / ratio if ratio else spot / 10.0)
    pcr = compute_pcr(chain)
    gex_profile = compute_gex_profile(chain, spy_spot)
    gamma_flip_spy = find_gamma_flip(gex_profile)
    gamma_flip = gamma_flip_spy * ratio if gamma_flip_spy else None
    max_pain_spy = compute_max_pain(chain)
    max_pain = max_pain_spy * ratio if max_pain_spy else None
    contango = (vix_data or {}).get("contango")

    ET = pytz.timezone("US/Eastern")
    now_et = datetime.now(ET)
    hour_et = now_et.hour
    if hour_et >= 15:
        return {
            "recommendation": "NO TRADE — Too Late in Session",
            "rationale": "0DTE entries after 3 PM ET carry excessive theta risk.",
            "stats": "", "action": "", "conditions_met": [], "conditions_failed": [],
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    daily_em = spot * (vix_val / 100) / (TRADING_DAYS_PER_YEAR ** 0.5)
    
    score = 0.0
    met, failed = [], []

    vwap_dev = ((spot - vwap) / vwap * 100) if vwap else 0.0
    if vwap_dev > 0.1:
        score += 3.0; met.append(f"Spot {vwap_dev:+.2f}% above VWAP")
    elif vwap_dev < -0.1:
        score -= 3.0; failed.append(f"Spot {vwap_dev:+.2f}% below VWAP")

    if gamma_flip:
        gf_dev = (spot - gamma_flip) / spot * 100
        if spot > gamma_flip:
            score += 2.5; met.append(f"Spot {gf_dev:+.1f}% above Gamma Flip ({int(gamma_flip)})")
        else:
            score -= 2.5; failed.append(f"Spot {gf_dev:+.1f}% below Gamma Flip ({int(gamma_flip)})")

    if pcr is not None:
        if pcr < 0.7:
            score += 2.0; met.append(f"PCR {pcr:.2f} — Strong Bullish Skew")
        elif pcr < 0.85:
            score += 1.0; met.append(f"PCR {pcr:.2f} — Mild Bullish Skew")
        elif pcr > 1.2:
            score -= 2.0; failed.append(f"PCR {pcr:.2f} — Strong Bearish Skew")
        elif pcr > 1.0:
            score -= 1.0; failed.append(f"PCR {pcr:.2f} — Mild Bearish Skew")

    if contango is not None:
        if contango:
            score += 1.5; met.append("VIX Contango — Regime Stable")
        else:
            score -= 1.5; failed.append("VIX Backwardation — Regime Unstable")

    if max_pain:
        mp_dist = spot - max_pain
        mp_pct = mp_dist / spot * 100
        if abs(mp_pct) > 0.5:
            if mp_pct > 0:
                score -= 1.0
                failed.append(f"Max Pain gravity {int(max_pain)} ({mp_pct:+.1f}% below spot)")
            else:
                score += 1.0
                met.append(f"Max Pain gravity {int(max_pain)} ({mp_pct:+.1f}% above spot)")

    BULL_THRESHOLD = 4.0
    BEAR_THRESHOLD = -4.0

    if score >= BULL_THRESHOLD:
        bias, _ = "bull", "bullish"
    elif score <= BEAR_THRESHOLD:
        bias, _ = "bear", "bearish"
        met, failed = failed, met
    else:
        return {
            "recommendation": f"NO TRADE — Weak Confluence (score: {score:+.1f})",
            "rationale": f"Weighted score {score:+.1f} is below ±{BULL_THRESHOLD} threshold. Wait for cleaner setup.",
            "stats": f"Expected 1-day move: ±{daily_em:.1f} pts",
            "action": "Stand aside. Monitor for VIX expansion or VWAP reclaim.",
            "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    target = find_target_strike(chain, bias, dte=0)
    if not target:
        return {
            "recommendation": "NO TRADE — No Suitable Option",
            "rationale": f"No viable {bias} options passed liquidity filters.",
            "stats": "", "action": "", "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    strike_spx = round(target["strike"] * ratio, 0)
    mid = target.get("mid", 0)

    dist_to_strike = abs(strike_spx - spot)
    if dist_to_strike > daily_em * 1.5:
        return {
            "recommendation": "NO TRADE — Strike Too Far OTM",
            "rationale": f"Strike {int(strike_spx)} is {dist_to_strike:.0f} from spot, "
                         f"exceeding 1.5× daily EM ({daily_em:.0f}). Low P(ITM).",
            "stats": f"Daily EM: ±{daily_em:.1f} | Strike dist: {dist_to_strike:.0f}",
            "action": "Choose a closer strike or wait for spot to move toward target.",
            "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    opt_label = "CALL" if target["type"] == "call" else "PUT"
    bd = target.get("_breakdown", {})
    delta_pct = round(abs(target["delta"]) * 100)

    hedge_wall = None
    if gex_profile:
        for gk, _ in sorted(gex_profile.items(), key=lambda x: abs(x[1]), reverse=True):
            gk_spx = gk * ratio
            if (bias == "bull" and gk_spx > strike_spx) or (bias == "bear" and gk_spx < strike_spx):
                hedge_wall = gk_spx
                break

    abs_score = abs(score)
    if abs_score >= 7.5:   confidence = "HIGH"
    elif abs_score >= 5.0: confidence = "MODERATE"
    else:                  confidence = "LOW"

    target_pts = abs(int(hedge_wall - strike_spx)) if hedge_wall else max(int(daily_em * 0.5), 5)


    target_desc = f"Target {int(hedge_wall)} GEX Wall (+{target_pts}pts)" if hedge_wall else f"Target +{target_pts}pts (0.5× daily EM)"
    stop_desc = f"Stop at 50% premium loss (−${mid/2:.2f} on the option)"

    stats_text = (
        f"Weighted Score: {score:+.1f}/±10 | Daily EM: ±{daily_em:.1f}\n"
        f"Greeks: Δ={target['delta']:+.3f} Γ={target['gamma']:.4f} Θ={target['theta']:.4f} V={target['vega']:.4f} IV={target['iv']:.1%}\n"
        f"Stats: ~{delta_pct}% P(ITM) | Γ/Θ: {bd.get('gt_ratio', 0):.1f}x | Spread: {bd.get('spread_pct', 0):.1f}% | Flow: {bd.get('flow_ratio', 0):.2f}× OI\n"
        f"Score Breakdown: Δ:{bd.get('delta_score',0):.2f} Γ/Θ:{bd.get('gt_score',0):.2f} Liq:{bd.get('liq_score',0):.2f} Flow:{bd.get('flow_score',0):.2f} IV:{bd.get('iv_score',0):.2f}"
    )

    return {
        "recommendation": f"RECOMMENDATION: BUY {int(strike_spx)} {opt_label}",
        "rationale": f"Weighted confluence score {score:+.1f}. " + " | ".join(met) + ".",
        "stats": stats_text,
        "action": f"Enter at market. {target_desc}. {stop_desc}.",
        "confidence": confidence,
        "conditions_met": met,
        "conditions_failed": failed,
        "strike_spx": strike_spx,
        "opt_type": opt_label,
        "mid_price": mid,
    }
