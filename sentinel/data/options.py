"""Listed options chains (yfinance): scoring, IV term structure, skew, squeeze scan."""
from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from sentinel.core.http import (
    get_yf_ticker, yf,
)
from sentinel.core.formatting import _safe_float
from sentinel.analytics.options_math import (
    bs_greeks_vectorized, year_fraction_to_expiry,
)

from sentinel.config import (
    OPTIONS_SCORE_W1, OPTIONS_SCORE_W2, OPTIONS_SCORE_W3, OPTIONS_UNUSUAL_VOL_OI_RATIO, TRADING_DAYS_PER_YEAR,
)
from sentinel.data.macro import get_risk_free_rate
from sentinel.data.market import get_vix_full

logger = logging.getLogger("sentinel.data")

def _spread_expiries(exps, targets=(2, 7, 14, 30, 45, 60, 90, 180, 365)):
    """Expiries nearest to each target DTE (dedup), so a term structure spans ~1 year
    instead of the first N listings (SPY lists daily expiries)."""
    today = datetime.today().date()
    dated = []
    for e in exps:
        try:
            dated.append(((datetime.strptime(e, "%Y-%m-%d").date() - today).days, e))
        except ValueError:
            continue
    out = []
    for t in targets:
        if not dated:
            break
        d, e = min(dated, key=lambda x: abs(x[0] - t))
        if e not in out:
            out.append(e)
    return sorted(out)



@st.cache_data(ttl=600)
def options_expiries(ticker):
    """Fetch available option expiry dates with retry.
    
    M14 fix: On retry, create a fresh yf.Ticker() bypassing the LRU cache,
    since the cached Ticker object caches .options internally and retries
    would return the same stale result.
    """
    import time
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(0.5 * (attempt + 1))
                tk = yf.Ticker(ticker) if yf else None
            else:
                tk = get_yf_ticker(ticker)
            if not tk: return []
            res = list(tk.options)
            if res: return res
        except Exception as e:
            logger.warning(f"options_expiries attempt {attempt+1}: {e}")
    logger.error(f"options_expiries failed after 3 attempts for {ticker}")
    return []


@st.cache_data(ttl=600)
def options_chain(ticker, expiry=None):
    import time
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(0.5 * (attempt + 1))
                # Fresh Ticker on retry — cached objects pin a stale .options result
                t = yf.Ticker(ticker) if yf else None
            else:
                t = get_yf_ticker(ticker)
            if t is None: return None, None, None
            exps = []
            for _ in range(2):
                exps = list(t.options)
                if exps: break
                time.sleep(0.5)
                
            if not exps: return None, None, None
            exp = expiry if expiry and expiry in exps else exps[0]
            chain = t.option_chain(exp)
            cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
            c, p = None, None
            if hasattr(chain, "calls") and not chain.calls.empty:
                c = chain.calls[[x for x in cols if x in chain.calls.columns]]
            if hasattr(chain, "puts") and not chain.puts.empty:
                p = chain.puts[[x for x in cols if x in chain.puts.columns]]
            if c is not None or p is not None:
                return c, p, exp
        except Exception as e:
            logger.warning(f"options_chain attempt {attempt+1}: {e}")
    logger.error(f"options_chain failed after 3 attempts for {ticker}")
    return None, None, None


def score_options_chain(calls_df, puts_df, current_price, vix=None, expiry_date=None, fred_key=None):
    """Score near-ATM options. Numpy path — avoids pandas setitem/to_dict churn."""
    result = {"top_calls": [], "top_puts": [], "unusual": None}
    if calls_df is None or puts_df is None:
        return result
    empty_c = getattr(calls_df, "empty", True)
    empty_p = getattr(puts_df, "empty", True)
    if empty_c and empty_p:
        return result

    w1, w2, w3 = OPTIONS_SCORE_W1, OPTIONS_SCORE_W2, OPTIONS_SCORE_W3
    vix_val = float(vix) if vix is not None else 20.0
    if vix_val > 25:
        w3 += 0.15; w1 -= 0.075; w2 -= 0.075
    elif vix_val < 15:
        w1 += 0.15; w2 -= 0.075; w3 -= 0.075
    w1, w2, w3 = max(w1, 0), max(w2, 0), max(w3, 0)
    if abs(w1 + w2 + w3 - 1.0) > 1e-6:
        w1, w2, w3 = OPTIONS_SCORE_W1, OPTIONS_SCORE_W2, OPTIONS_SCORE_W3

    if expiry_date is not None:
        try:
            T_approx = year_fraction_to_expiry(str(expiry_date)[:10])
        except Exception:
            T_approx = 14 / 365.0
    else:
        T_approx = 14 / 365.0
    r_risk_free = get_risk_free_rate(fred_key)
    spot = float(current_price) if current_price else 0.0

    def _col(df, name, default=0.0):
        if df is None or name not in df.columns:
            return None
        return pd.to_numeric(df[name], errors="coerce").fillna(default).to_numpy(dtype=np.float64)

    def _score_side(df, side):
        if df is None or getattr(df, "empty", True):
            return []
        strike = _col(df, "strike")
        if strike is None or strike.size == 0:
            return []
        volume = _col(df, "volume")
        oi = _col(df, "openInterest")
        iv = _col(df, "impliedVolatility")
        last = _col(df, "lastPrice")
        bid = _col(df, "bid")
        ask = _col(df, "ask")
        n = strike.size
        if volume is None:
            volume = np.zeros(n)
        if oi is None:
            oi = np.zeros(n)
        if iv is None:
            iv = np.full(n, 0.2)
        if last is None:
            last = np.zeros(n)
        if bid is None:
            bid = np.zeros(n)
        if ask is None:
            ask = np.zeros(n)

        # Near-ATM window (max 30)
        if spot > 0 and n > 30:
            idx = np.argpartition(np.abs(strike - spot), 30)[:30]
            idx = np.sort(idx)
            strike, volume, oi, iv = strike[idx], volume[idx], oi[idx], iv[idx]
            last, bid, ask = last[idx], bid[idx], ask[idx]
            n = strike.size

        oi_safe = np.maximum(oi, 1.0)
        voi = volume / oi_safe
        max_voi = float(voi.max()) if n else 0.0
        norm_voi = voi / max_voi if max_voi > 0 else np.zeros(n)

        iv_min, iv_max = float(iv.min()), float(iv.max())
        iv_range = iv_max - iv_min
        iv_pct = (iv - iv_min) / iv_range if iv_range > 0 else np.full(n, 0.5)

        if spot > 0:
            greeks = bs_greeks_vectorized(
                S=spot, K=strike, T=T_approx, r=r_risk_free,
                sigma=np.maximum(iv, 0.01), side=side,
            )
            delta_raw = np.asarray(greeks["delta"], dtype=np.float64)
            vega = np.asarray(greeks["vega"], dtype=np.float64)
            rho = np.asarray(greeks["rho"], dtype=np.float64)
        else:
            delta_raw = np.full(n, 0.5 if side == "call" else -0.5)
            vega = np.zeros(n)
            rho = np.zeros(n)
        delta_proxy = np.abs(delta_raw)
        score = norm_voi * w1 + iv_pct * w2 - np.abs(delta_proxy - 0.5) * w3

        rows = []
        for i in range(n):
            rows.append({
                "strike": float(strike[i]),
                "lastPrice": float(last[i]),
                "bid": float(bid[i]),
                "ask": float(ask[i]),
                "volume": int(volume[i]),
                "openInterest": int(oi[i]),
                "iv": float(iv[i]),
                "voi": round(float(voi[i]), 2),
                "score": round(float(score[i]), 4),
                "side": side,
                "delta": round(float(delta_raw[i]), 4),
                "vega": round(float(vega[i]), 4),
                "rho": round(float(rho[i]), 4),
            })
        return rows

    call_rows = _score_side(calls_df, "call")
    put_rows = _score_side(puts_df, "put")
    call_rows.sort(key=lambda r: r["score"], reverse=True)
    put_rows.sort(key=lambda r: r["score"], reverse=True)
    result["top_calls"] = call_rows[:2]
    result["top_puts"] = put_rows[:2]
    all_rows = call_rows + put_rows
    if all_rows:
        best = max(all_rows, key=lambda r: r["voi"])
        if best.get("voi", 0) >= OPTIONS_UNUSUAL_VOL_OI_RATIO:
            result["unusual"] = best
    return result


@st.cache_data(ttl=600)
def get_iv_term_structure(ticker="SPY"):
    """Get ATM implied volatility across multiple expiration dates."""
    if yf is None:
        return None
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None

        fi = tk.fast_info
        price = getattr(fi, "last_price", None)
        if price is None or float(price) <= 0:
            h = tk.history(period="1d")
            price = float(h["Close"].iloc[-1]) if not h.empty else None
        if price is None:
            return None

        exps = list(tk.options)
        if not exps:
            return None

        selected_exps = _spread_expiries(exps)
        today = datetime.today().date()

        def _interp_atm_iv(df_side, spot):
            df_side = df_side.copy()
            if "impliedVolatility" in df_side.columns:
                df_side = df_side[df_side["impliedVolatility"].notna() & (df_side["impliedVolatility"] > 0)]
            if df_side.empty:
                return None
            df_side["_dist"] = (df_side["strike"] - spot).abs()
            nearest = df_side.nsmallest(2, "_dist")
            if len(nearest) == 0: return None
            if len(nearest) == 1: return float(nearest["impliedVolatility"].iloc[0])
            k1, k2 = nearest["strike"].values
            v1, v2 = nearest["impliedVolatility"].values
            if k1 == k2: return float(v1)
            d1 = abs(np.log(spot / k1))
            d2 = abs(np.log(spot / k2))
            if d1 + d2 == 0: return float(v1)
            w1 = d2 / (d1 + d2)
            w2 = d1 / (d1 + d2)
            return float(v1 * w1 + v2 * w2)

        rows = []
        for exp in selected_exps:
            try:
                chain = tk.option_chain(exp)
                if chain is None:
                    continue

                calls, puts = chain.calls.copy(), chain.puts.copy()
                if calls.empty and puts.empty:
                    continue

                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                dte = max((exp_date - today).days, 1)

                call_iv = _interp_atm_iv(calls, price) if not calls.empty and "strike" in calls.columns else None
                put_iv = _interp_atm_iv(puts, price) if not puts.empty and "strike" in puts.columns else None

                if not calls.empty and "strike" in calls.columns:
                    calls["_dist"] = (calls["strike"] - price).abs()
                atm_call = calls.nsmallest(1, "_dist") if not calls.empty and "_dist" in calls.columns else pd.DataFrame()


                ivs = [v for v in [call_iv, put_iv] if v is not None and v > 0]
                if not ivs:
                    continue

                avg_iv = sum(ivs) / len(ivs)

                rows.append({
                    "expiry": exp,
                    "dte": dte,
                    "atm_iv": round(avg_iv * 100, 2),
                    "call_iv": round(call_iv * 100, 2) if call_iv is not None else None,
                    "put_iv": round(put_iv * 100, 2) if put_iv is not None else None,
                    "atm_strike": float(atm_call["strike"].iloc[0]) if not atm_call.empty else price,
                })
            except (KeyError, IndexError, ValueError) as e:
                logger.warning("IV term structure expiry skip: %s", {"expiry": exp, "error": str(e)})
                continue

        return rows if rows else None
    except Exception as e:
        logger.error("IV term structure fetch failed: %s", {"error": str(e)})
        return None


@st.cache_data(ttl=600)
def get_iv_skew(ticker="SPY"):
    """Compute 25-delta put/call IV skew across first 6 expiries.
    
    For each expiry, finds strikes closest to 25-delta for calls and puts
    using bs_greeks_engine, then computes ATM IV, 25Δ call IV, 25Δ put IV,
    and the skew (put IV - call IV).
    
    Zero additional API calls — uses option chains already being fetched.
    """
    if yf is None:
        return None
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None

        fi = tk.fast_info
        price = getattr(fi, "last_price", None)
        if price is None or float(price) <= 0:
            h = tk.history(period="1d")
            price = float(h["Close"].iloc[-1]) if not h.empty else None
        if price is None:
            return None

        exps = list(tk.options)
        if not exps:
            return None

        selected_exps = _spread_expiries(exps, (7, 14, 30, 60, 90, 180))
        today = datetime.today().date()
        r = get_risk_free_rate()
        results = []
        for exp in selected_exps:
            try:
                chain = tk.option_chain(exp)
                if chain is None:
                    continue
                calls, puts = chain.calls.copy(), chain.puts.copy()
                if calls.empty or puts.empty:
                    continue

                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                dte = max((exp_date - today).days, 1)
                T = dte / 365.0

                calls["_dist"] = (calls["strike"] - price).abs()
                atm_call = calls.nsmallest(1, "_dist")
                atm_iv_c = float(atm_call["impliedVolatility"].iloc[0]) if not atm_call.empty else None
                
                puts["_dist"] = (puts["strike"] - price).abs()
                atm_put = puts.nsmallest(1, "_dist")
                atm_iv_p = float(atm_put["impliedVolatility"].iloc[0]) if not atm_put.empty else None

                ivs = [v for v in (atm_iv_c, atm_iv_p) if v]
                atm_iv = sum(ivs) / len(ivs) if ivs else None

                otm_calls = calls[calls["strike"] >= price].copy()
                if not otm_calls.empty and "impliedVolatility" in otm_calls.columns:
                    sigma = np.maximum(otm_calls["impliedVolatility"].fillna(0.2).values, 0.01)
                    g_c = bs_greeks_vectorized(price, otm_calls["strike"].values, T, r, sigma, "call")
                    otm_calls["_delta"] = np.abs(g_c["delta"])
                    otm_calls["_d25_diff"] = (otm_calls["_delta"] - 0.25).abs()
                    c25_row = otm_calls.nsmallest(1, "_d25_diff")
                    iv_25c = float(c25_row["impliedVolatility"].iloc[0]) if not c25_row.empty else None
                else:
                    iv_25c = None

                otm_puts = puts[puts["strike"] <= price].copy()
                if not otm_puts.empty and "impliedVolatility" in otm_puts.columns:
                    sigma = np.maximum(otm_puts["impliedVolatility"].fillna(0.2).values, 0.01)
                    g_p = bs_greeks_vectorized(price, otm_puts["strike"].values, T, r, sigma, "put")
                    otm_puts["_delta"] = np.abs(g_p["delta"])
                    otm_puts["_d25_diff"] = (otm_puts["_delta"] - 0.25).abs()
                    p25_row = otm_puts.nsmallest(1, "_d25_diff")
                    iv_25p = float(p25_row["impliedVolatility"].iloc[0]) if not p25_row.empty else None
                else:
                    iv_25p = None

                if atm_iv is None:
                    continue

                skew = ((iv_25p or 0) - (iv_25c or 0)) * 100
                skew_label = "PUT PREMIUM" if skew > 2 else "CALL PREMIUM" if skew < -2 else "FLAT"

                results.append({
                    "expiry": exp,
                    "dte": dte,
                    "iv_atm": round(atm_iv * 100, 2),
                    "iv_25c": round(iv_25c * 100, 2) if iv_25c is not None else None,
                    "iv_25p": round(iv_25p * 100, 2) if iv_25p is not None else None,
                    "skew": round(skew, 2),
                    "skew_label": skew_label,
                })
            except Exception:
                continue

        return results if results else None
    except Exception as e:
        logger.error("IV skew fetch failed: %s", {"error": str(e)})
        return None


@st.cache_data(ttl=600)
def get_rv_iv_spread(ticker="SPY"):
    """Compute 20-day realized vol vs front-month ATM IV.
    
    RV20 - IV spread is the canonical vol premium signal:
      spread > +3%  → BUY VOL  (IV cheap relative to realized)
      spread < -3%  → SELL VOL (IV expensive relative to realized)
    
    Zero new API calls — uses yf history + existing IV term structure.
    """
    import numpy as np
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None
        h = tk.history(period="60d")
        if h is None or len(h) < 25:
            return None

        returns = np.log(h["Close"] / h["Close"].shift(1)).dropna()
        rv20 = float(returns.tail(20).std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100)

        iv_data = get_iv_term_structure(ticker)
        if iv_data and len(iv_data) > 0:
            best_iv = min(iv_data, key=lambda x: abs(x["dte"] - 30))
            front_iv = best_iv["atm_iv"]
            dte = best_iv["dte"]
        else:
            return None

        vix_price, _, _ = get_vix_full()
        vix = float(vix_price) if vix_price else 20.0
        thresh = 3.0 * (vix / 20.0)

        spread = rv20 - front_iv
        if spread > thresh:
            signal, signal_color = "BUY VOL", "#3FCF8E"
        elif spread < -thresh:
            signal, signal_color = "SELL VOL", "#F2555A"
        else:
            signal, signal_color = "NEUTRAL", "#8A8A8A"

        return {
            "rv20": round(rv20, 2),
            "front_iv": round(front_iv, 2),
            "spread": round(spread, 2),
            "signal": signal,
            "signal_color": signal_color,
            "dte": dte,
        }
    except Exception as e:
        logger.error("RV/IV spread failed: %s", {"error": str(e)})
        return None


@st.cache_data(ttl=3600)
def get_gamma_squeeze_scanner():
    """Scan for gamma squeeze candidates: high short interest + high options volume."""

    if yf is None:
        return None

    SCAN_UNIVERSE = [
        "GME", "AMC", "KOSS", "BB", "NOK", "PLTR", "SOFI",
        "RIVN", "LCID", "MARA", "RIOT", "COIN", "CVNA", "UPST",
        "SNOW", "DKNG", "SPCE", "BYND", "FUBO", "WKHS",
        "TLRY", "SNDL", "CLOV", "SKLZ", "RKT", "OPEN",
    ]

    try:
        data = yf.download(SCAN_UNIVERSE, period="30d", progress=False, threads=True)
        if data.empty:
            return []

        pre_filtered = []
        for ticker in SCAN_UNIVERSE:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"][ticker].dropna()
                    volume = data["Volume"][ticker].dropna()
                else:
                    continue

                if close.empty or len(close) < 10:
                    continue

                current_price = float(close.iloc[-1])
                avg_vol_20d = float(volume.tail(20).mean())
                latest_vol = float(volume.iloc[-1])

                vol_ratio = round(latest_vol / avg_vol_20d, 2) if avg_vol_20d > 0 else 0.0
                if vol_ratio > 0.5:
                    pre_filtered.append({
                        "ticker": ticker,
                        "current_price": current_price,
                        "avg_vol_20d": avg_vol_20d,
                        "latest_vol": latest_vol,
                        "vol_ratio": vol_ratio
                    })
            except (KeyError, IndexError):
                continue

        pre_filtered.sort(key=lambda x: x["vol_ratio"], reverse=True)
        top_candidates = pre_filtered[:10]

        rows = []
        for cand in top_candidates:
            try:
                ticker = cand["ticker"]
                current_price = cand["current_price"]
                avg_vol_20d = cand["avg_vol_20d"]
                latest_vol = cand["latest_vol"]
                vol_ratio = cand["vol_ratio"]

                tk = get_yf_ticker(ticker)
                if tk is None:
                    continue
                info = tk.info or {}
                short_pct = _safe_float(info.get("shortPercentOfFloat", 0), default=0) * 100
                short_ratio = _safe_float(info.get("shortRatio", 0))

                squeeze_score = 0.0
                if short_pct > 20:
                    squeeze_score += 3.0
                elif short_pct > 10:
                    squeeze_score += 2.0
                elif short_pct > 5:
                    squeeze_score += 1.0

                if vol_ratio > 3.0:
                    squeeze_score += 3.0
                elif vol_ratio > 2.0:
                    squeeze_score += 2.0
                elif vol_ratio > 1.5:
                    squeeze_score += 1.0

                if short_ratio > 5:
                    squeeze_score += 1.0

                if squeeze_score < 1.0:
                    continue

                if squeeze_score >= 5:
                    signal = "🔴 HIGH SQUEEZE"
                elif squeeze_score >= 3:
                    signal = "🟡 MODERATE"
                else:
                    signal = "🟢 LOW"

                rows.append({
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "short_pct": round(short_pct, 1),
                    "short_ratio": round(short_ratio, 1),
                    "vol_ratio": vol_ratio,
                    "squeeze_score": round(squeeze_score, 1),
                    "signal": signal,
                    "avg_vol": int(avg_vol_20d),
                    "latest_vol": int(latest_vol),
                })
            except (KeyError, IndexError):
                continue

        rows.sort(key=lambda x: x["squeeze_score"], reverse=True)
        return rows[:15]
    except Exception as e:
        logger.error("Gamma squeeze scanner failed: %s", {"error": str(e)})
        return []
