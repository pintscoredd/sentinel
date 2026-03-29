#!/usr/bin/env python3
"""SENTINEL — Data Fetchers Module
All @st.cache_data API functions, data utilities, and helpers.
"""

import streamlit as st
import requests
import asyncio
import pandas as pd
import math
import re
import logging
from datetime import datetime, timedelta, time as dtime
import pytz
from collections import defaultdict
import skyfield.api as sf
from skyfield.api import Topos, EarthSatellite
from skyfield.sgp4lib import EarthSatellite

# ── Newly Integrated Libraries ──
import pandas_market_calendars as mcal
# For Black-Scholes Greeks Engine
from scipy.stats import norm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    import orjson as json
except ImportError:
    import json

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    import yfinance as yf
except ImportError:
    yf = None

# ── Logging Setup ──
logger = logging.getLogger("sentinel.data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_YAHOO_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

# ── Yahoo Finance Global Rate Limiter ─────────────────────────────
# Prevents 429 errors by serializing requests with a minimum gap.
# All yfinance calls go through get_yf_ticker() which enforces the throttle.
import threading as _threading
import time as _time

_yf_lock = _threading.Lock()
_yf_last_request = 0.0
_YF_MIN_GAP = 0.35          # minimum seconds between Yahoo API calls
_yf_ticker_cache = {}        # symbol → (yf.Ticker, timestamp)
_YF_CACHE_TTL = 120          # reuse Ticker objects for 2 minutes

def get_yf_ticker(ticker):
    """Return a yfinance Ticker with global rate limiting.
    
    Serializes all Yahoo requests with a minimum gap to prevent 429 errors.
    Caches Ticker objects per-symbol to avoid redundant HTTP sessions.
    """
    if yf is None: return None
    global _yf_last_request
    
    now = _time.time()
    
    # Check cache first (no lock needed for read)
    cached = _yf_ticker_cache.get(ticker)
    if cached and (now - cached[1]) < _YF_CACHE_TTL:
        return cached[0]
    
    # Throttle: enforce minimum gap between Yahoo API requests
    with _yf_lock:
        elapsed = _time.time() - _yf_last_request
        if elapsed < _YF_MIN_GAP:
            _time.sleep(_YF_MIN_GAP - elapsed)
        _yf_last_request = _time.time()
    
    tk = yf.Ticker(ticker)
    _yf_ticker_cache[ticker] = (tk, _time.time())
    return tk



# ════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ════════════════════════════════════════════════════════════════════


def _safe_float(v, default=0.0):
    try:
        f = float(v) if v is not None else default
        return default if (math.isnan(f) or math.isinf(f)) else f
    except:
        return default

def _safe_int(v):
    try:
        f = float(v) if v is not None else 0.0
        return 0 if (math.isnan(f) or math.isinf(f)) else int(f)
    except:
        return 0

def _esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;") if t else ""

def fmt_p(p):
    """Format price — 2 decimal places always"""
    if p is None: return "—"
    if p < 0.01: return f"${p:.6f}"
    return f"${p:,.2f}"

def fmt_pct(p):
    if p is None: return "—"
    s = "+" if p >= 0 else ""
    return f"{s}{p:.2f}%"

def pct_color(v):
    return "#00CC44" if v >= 0 else "#FF4444"

def _is_english(text):
    if not text: return False
    return sum(1 for c in text if ord(c) < 128) / max(len(text), 1) > 0.72


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((requests.exceptions.RequestException, ValueError)))
def _fetch_robust_json(url, params=None, headers=None, timeout=10):
    """Centralized, robust external fetcher using exponential backoff and fast JSON parsing."""
    if headers is None:
        headers = {}
    
    # Many APIs (GDELT, Airplanes.live) block Python/Streamlit user-agents
    if "User-Agent" not in headers or "SENTINEL" in headers["User-Agent"]:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return json.loads(r.content)


def run_async(coro):
    """Helper to safely run async tasks in Streamlit threads.
    Uses asyncio.run() which creates and tears down a fresh event loop,
    avoiding RuntimeError collisions across Streamlit's multi-threaded sessions.
    """
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════
# MARKET STATUS
# ════════════════════════════════════════════════════════════════════

def is_market_open():
    """Check US equity market status using accurate NYSE calendar schedules."""
    try:
        ET = pytz.timezone("US/Eastern")
        now = datetime.now(ET)
        
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=now.date(), end_date=now.date())
        
        if schedule.empty:
            wd = now.weekday()  # Monday=0, Sunday=6
            if wd == 6 and now.time() >= dtime(18, 0):
                return "FUTURES OPEN", "#FF8C00", "US Equities Closed, Futures Live"
            return "CLOSED", "#FF4444", "Weekend / Holiday"
        
        market_open = schedule.iloc[0]['market_open'].astimezone(ET).time()
        market_close = schedule.iloc[0]['market_close'].astimezone(ET).time()
        
        t = now.time()
        if market_open <= t <= market_close:
            return "OPEN", "#00CC44", "Regular Hours"
        elif dtime(4, 0) <= t < market_open:
            return "PRE-MARKET", "#FF8C00", "Pre-Market"
        elif market_close < t <= dtime(20, 0):
            return "AFTER-HOURS", "#FF8C00", "After-Hours"
        else:
            return "CLOSED", "#FF4444", "Markets Closed"
    except Exception as e:
        logger.error({"error": str(e)}, "is_market_open fallback")
        return "UNKNOWN", "#555555", "Status Unknown"

def is_0dte_market_open():
    """Check if within regular US equity hours for Alpaca."""
    status, _, _ = is_market_open()
    if status == "OPEN":
        return True, f"Market OPEN"
    return False, f"Market {status}"


# ════════════════════════════════════════════════════════════════════
# YAHOO FINANCE & ASYNC BATCHING
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def yahoo_quote(ticker):
    TICKER_MAP = {"DXY": "DX-Y.NYB", "$DXY": "DX-Y.NYB"}
    t = TICKER_MAP.get(ticker, ticker)
    try:
        tk = get_yf_ticker(t)
        if tk is None: return None

        fi = tk.fast_info
        price = getattr(fi, "last_price", None)
        prev = None
        vol = 0

        # Always fetch history as fast_info.previous_close frequently caches incorrectly
        try:
            h = tk.history(period="5d")
            if not h.empty:
                if price is None or price <= 0:
                    price = float(h["Close"].iloc[-1])
                prev = float(h["Close"].iloc[-2]) if len(h) > 1 else float(h["Close"].iloc[-1])
                vol = int(h["Volume"].iloc[-1])
        except Exception:
            pass

        if prev is None:
            prev = getattr(fi, "previous_close", None)
        if price is None:
            return None
        if prev is None:
            prev = price
        if vol == 0:
            vol = int(getattr(fi, "three_month_average_volume", 0) or 0)

        price = float(price)
        prev  = float(prev)
        chg   = price - prev
        pct   = chg / prev * 100 if prev else 0.0

        return {
            "ticker": ticker, "price": round(price, 2),
            "change": round(chg, 2), "pct": round(pct, 2), "volume": vol,
        }
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_risk_free_rate(fred_key=None):
    """Fetch current 3-month T-bill rate as risk-free proxy."""
    if fred_key:
        df = fred_series("DTB3", fred_key, 5)
        if df is not None and not df.empty:
            return round(df["value"].iloc[-1] / 100, 4)
    # Fallback: fetch from Yahoo Finance
    try:
        h = get_yf_ticker("^IRX").history(period="5d")
        if not h.empty:
            return round(h["Close"].iloc[-1] / 100, 4)
    except Exception:
        pass
    return 0.045   # final fallback

async def _fetch_yahoo_quotes_async(tickers):
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, yahoo_quote, tkr) for tkr in tickers]
    return await asyncio.gather(*tasks, return_exceptions=True)

@st.cache_data(ttl=60)
def get_futures():
    FUTURES = [
        ("ES=F", "S&P 500 Futures"), ("NQ=F", "Nasdaq 100 Futures"), ("YM=F", "Dow Jones Futures"),
        ("RTY=F", "Russell 2000 Futures"), ("ZN=F", "10-Year Treasury Bond"), ("CL=F", "WTI Crude Oil"),
        ("GC=F", "Gold Futures"), ("SI=F", "Silver Futures"), ("NG=F", "Natural Gas"),
        ("ZW=F", "Wheat Futures"), ("ZC=F", "Corn Futures"), ("DX=F", "US Dollar Index"),
    ]
    rows = []
    try:
        tickers = [t[0] for t in FUTURES]
        results = run_async(_fetch_yahoo_quotes_async(tickers))
        for (ticker, name), q in zip(FUTURES, results):
            if isinstance(q, dict) and q:
                rows.append({"ticker": ticker, "name": name, "price": q["price"],
                             "change": q["change"], "pct": q["pct"]})
    except Exception:
        pass
    return rows

@st.cache_resource(ttl=300)
def get_heatmap_data():
    SECTOR_STOCKS = {
        "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "META", "ORCL", "AMD", "INTC", "QCOM", "TXN", "ADBE", "CRM", "INTU", "IBM", "ACN"],
        "Healthcare": ["UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "PFE", "DHR", "BMY", "ISRG", "GILD", "MDT", "CVS", "CI"],
        "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "C", "AXP", "COF", "PGR", "ICE", "CME", "SPGI", "V", "MA"],
        "Consumer Disc": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "BKNG", "TJX", "SBUX", "MAR", "TGT", "ROST", "ORLY", "DHI"],
        "Comm Svcs": ["GOOGL", "META", "DIS", "NFLX", "T", "VZ", "CMCSA", "TMUS", "EA", "TTWO"],
        "Industrials": ["GE", "RTX", "CAT", "HON", "UNP", "LMT", "DE", "WM", "NSC", "ITW", "ETN", "PH", "GD", "BA"],
        "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "OXY", "VLO", "HAL", "DVN", "BKR"],
        "Consumer Stap": ["WMT", "PG", "KO", "PEP", "PM", "MO", "CL", "GIS", "KHC", "KMB", "SYY"],
        "Utilities": ["NEE", "DUK", "SO", "AEP", "D", "EXC", "PCG", "SRE", "XEL", "CEG"],
        "Materials": ["LIN", "APD", "ECL", "SHW", "NEM", "FCX", "NUE", "VMC", "ALB", "MOS"],
        "Real Estate": ["PLD", "AMT", "CCI", "EQIX", "PSA", "SPG", "WELL", "O", "DLR", "AVB"],
    }
    flat_jobs = [(sector, tkr) for sector, tickers in SECTOR_STOCKS.items() for tkr in tickers]
    tickers = [tkr for _, tkr in flat_jobs]
    
    try:
        results = run_async(_fetch_yahoo_quotes_async(tickers))
        rows = []
        for (sector, tkr), q in zip(flat_jobs, results):
            if isinstance(q, dict) and q:
                rows.append({"ticker": tkr, "sector": sector, "pct": q["pct"], "price": q["price"], "change": q["change"]})
        return rows
    except Exception as e:
        logger.error({"error": str(e)}, "Heatmap Fetch Error")
        return []

@st.cache_data(ttl=300)
def multi_quotes(tickers):
    return [q for t in tickers if (q := yahoo_quote(t))]

@st.cache_data(ttl=300)
def vix_price():
    try:
        h = get_yf_ticker("^VIX").history(period="5d")
        return round(h["Close"].iloc[-1], 2) if not h.empty else None
    except:
        return None

@st.cache_data(ttl=3600)
def vix_with_percentile():
    """VIX with 1Y and 3Y percentile ranks + regime divergence flag."""
    try:
        h = get_yf_ticker("^VIX").history(period="3y")
        if h.empty or len(h) < 20:
            return None, None, None
        current = h["Close"].iloc[-1]
        
        # 3Y percentile rank (full history)
        pct_3y = (h["Close"] < current).mean() * 100
        
        # 1Y percentile rank (last ~252 trading days)
        h_1y = h.tail(252)
        pct_1y = (h_1y["Close"] < current).mean() * 100 if len(h_1y) >= 20 else pct_3y
        
        # Posture based on 1Y percentile
        if pct_1y < 30:   posture = "RISK-ON"
        elif pct_1y < 65: posture = "NEUTRAL"
        else:             posture = "RISK-OFF"
        
        # FIX-10: Regime divergence flag — 1Y says fear but 3Y says normal
        if pct_1y > 70 and pct_3y < 50:
            posture += " (REGIME: structurally normal)"
        
        return round(current, 2), round(pct_1y, 1), posture
    except Exception:
        return None, None, None

@st.cache_data(ttl=600)
def options_expiries(ticker):
    import time
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(0.5 * (attempt + 1))
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
                time.sleep(0.5 * (attempt + 1))  # 1.0s, 1.5s backoff
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


def score_options_chain(calls_df, puts_df, current_price, vix=None, expiry_date=None):
    import pandas as pd
    result = {"top_calls": [], "top_puts": [], "unusual": None}
    if calls_df is None or puts_df is None:
        return result
    if calls_df.empty and puts_df.empty:
        return result

    w1, w2, w3 = 0.40, 0.30, 0.30
    vix_val = float(vix) if vix is not None else 20.0
    if vix_val > 25:
        w3 += 0.15; w1 -= 0.075; w2 -= 0.075
    elif vix_val < 15:
        w1 += 0.15; w2 -= 0.075; w3 -= 0.075

    def _score_side(df, side):
        if df is None or df.empty:
            return []
        df = df.copy()
        for col in ["strike", "volume", "openInterest", "impliedVolatility"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        if current_price and "strike" in df.columns and len(df) > 30:
            df["_dist"] = (df["strike"] - current_price).abs()
            df = df.nsmallest(30, "_dist").drop(columns=["_dist"])

        if df.empty:
            return []

        df["_voi"] = df.apply(lambda r: r.get("volume", 0) / max(r.get("openInterest", 1), 1), axis=1)
        max_voi = df["_voi"].max()
        df["_norm_voi"] = df["_voi"] / max_voi if max_voi > 0 else 0

        iv_col = "impliedVolatility"
        if iv_col in df.columns:
            iv_min, iv_max = df[iv_col].min(), df[iv_col].max()
            iv_range = iv_max - iv_min
            df["_iv_pct"] = (df[iv_col] - iv_min) / iv_range if iv_range > 0 else 0.5
        else:
            df["_iv_pct"] = 0.5

        # Precise Delta using Black-Scholes Approximation
        if expiry_date is not None:
            try:
                exp_dt = datetime.strptime(str(expiry_date), "%Y-%m-%d")
                dte = max((exp_dt.date() - datetime.today().date()).days, 0)
                T_approx = max(dte / 365.0, 1 / 365.0)   # min 1 day to avoid div/0
            except Exception:
                T_approx = 14 / 365.0
        else:
            T_approx = 14 / 365.0

        try:
            fred_key = st.session_state.get("fred_key")
        except:
            fred_key = None
        r_risk_free = get_risk_free_rate(fred_key)        

        if current_price and current_price > 0 and "strike" in df.columns:
            # Use full bs_greeks_engine for Delta + Vega + Rho
            def _row_greeks(row):
                sigma = max(row.get("impliedVolatility", 0.2), 0.01)
                g = bs_greeks_engine(current_price, row.get("strike", current_price), T_approx, r_risk_free, sigma, side)
                return pd.Series({"_delta_proxy": abs(g["delta"]), "_vega": g.get("vega", 0.0), "_rho": g.get("rho", 0.0), "_delta_raw": g["delta"]})
            greeks_df = df.apply(_row_greeks, axis=1)
            df = pd.concat([df, greeks_df], axis=1)
        else:
            df["_delta_proxy"] = 0.5
            df["_vega"] = 0.0
            df["_rho"] = 0.0
            df["_delta_raw"] = 0.5 if side == "call" else -0.5

        df["_score"] = (df["_norm_voi"] * w1 + df["_iv_pct"] * w2 - (df["_delta_proxy"] - 0.5).abs() * w3)

        rows = []
        for _, r in df.iterrows():
            rows.append({
                "strike": float(r.get("strike", 0)),
                "lastPrice": float(r.get("lastPrice", 0)),
                "bid": float(r.get("bid", 0)),
                "ask": float(r.get("ask", 0)),
                "volume": int(r.get("volume", 0)),
                "openInterest": int(r.get("openInterest", 0)),
                "iv": float(r.get("impliedVolatility", 0)),
                "voi": round(float(r.get("_voi", 0)), 2),
                "score": round(float(r.get("_score", 0)), 4),
                "side": side,
                "delta": round(float(r.get("_delta_raw", 0)), 4),
                "vega": round(float(r.get("_vega", 0)), 4),
                "rho": round(float(r.get("_rho", 0)), 4),
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
        result["unusual"] = max(all_rows, key=lambda r: r["voi"])

    return result

def bs_price(S, K, T, r, sigma, side="call", q=0.0):
    """Calculate theoretical option price using Black-Scholes with dividend yield.
    
    Args:
        S: Spot price
        K: Strike price  
        T: Time to expiry in years
        r: Risk-free rate
        sigma: Volatility
        side: 'call' or 'put'
        q: Continuous dividend yield (default 0.0)
    """
    try:
        # Prevent math domain errors on edge cases
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0: return 0.0
        S_adj = S * math.exp(-q * T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if side == "call":
            p = S_adj * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            p = K * math.exp(-r * T) * norm.cdf(-d2) - S_adj * norm.cdf(-d1)
        return max(p, 0.0)
    except Exception:
        return 0.0

def get_iv_brentq(S, K, T, r, target_price, side="call", q=0.0):
    """Brentq bracket solver to back out Implied Volatility from market price.
    
    Uses scipy.optimize.brentq over [1e-6, 10.0] — bracket-guaranteed convergence
    without requiring a good initial seed. Far more robust than Newton-Raphson
    for deep ITM/OTM options.
    
    Returns None if the solver fails, signaling the caller to
    fall back to broker-provided IV instead of injecting a bogus 0.0.
    """
    from scipy.optimize import brentq
    if target_price <= 0 or S <= 0 or K <= 0 or T <= 0: return None
    
    def objective(sigma):
        return bs_price(S, K, T, r, sigma, side, q) - target_price
    
    try:
        # Verify bracket: price at low vol should be below target, at high vol above
        lo_val = objective(1e-6)
        hi_val = objective(10.0)
        if lo_val * hi_val > 0:
            # Target price outside achievable range — no valid IV
            return None
        iv = brentq(objective, 1e-6, 10.0, xtol=1e-6, maxiter=100)
        return float(max(iv, 0.0))
    except Exception:
        return None

# Backward-compatible alias
def get_iv_newton(S, K, T, r, target_price, side="call", q=0.0):
    """Alias for get_iv_brentq — kept for backward compatibility."""
    return get_iv_brentq(S, K, T, r, target_price, side, q)

def bs_greeks_engine(S, K, T, r, sigma, side="call", q=0.0):
    """True Black-Scholes Greeks Engine with dividend yield.
    
    Returns Delta, Gamma, Theta, Vega, and Rho.
    Vega and Rho are expressed per 1% move (divided by 100).
    """
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return {"delta": 0.5 if side == "call" else -0.5, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    try:
        S_adj = S * math.exp(-q * T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        N_d1 = norm.cdf(d1)
        N_d2 = norm.cdf(d2)
        n_d1 = norm.pdf(d1)
        discount = math.exp(-r * T)
        
        # Delta (adjusted for dividends)
        delta = math.exp(-q * T) * N_d1 if side == "call" else math.exp(-q * T) * (N_d1 - 1.0)
        
        # Gamma
        gamma = math.exp(-q * T) * n_d1 / (S * sigma * math.sqrt(T))
        
        # Theta
        theta_d1 = -(S_adj * n_d1 * sigma) / (2 * math.sqrt(T))
        if side == "call":
            theta = (theta_d1 + q * S_adj * N_d1 - r * K * discount * N_d2) / 365.0
        else:
            theta = (theta_d1 - q * S_adj * norm.cdf(-d1) + r * K * discount * norm.cdf(-d2)) / 365.0
        
        # Vega: sensitivity to 1% move in IV  →  S * e^(-qT) * N'(d1) * sqrt(T) / 100
        vega = S_adj * n_d1 * math.sqrt(T) / 100.0
        
        # Rho: sensitivity to 1% move in rates
        if side == "call":
            rho = K * T * discount * N_d2 / 100.0
        else:
            rho = -K * T * discount * norm.cdf(-d2) / 100.0
            
        return {
            "delta": round(delta, 4), "gamma": round(gamma, 6), "theta": round(theta, 4),
            "vega": round(vega, 4), "rho": round(rho, 4)
        }
    except Exception:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

@st.cache_data(ttl=21600)
def get_finra_short_volume(ticker):
    """Free Short Volume Data via FINRA/yfinance fallback."""
    try:
        t = get_yf_ticker(ticker)
        if t is None: return []
        i = t.fast_info
        # Attempt to get short data via ticker info
        info = t.info
        s_pct = info.get("shortPercentOfFloat", 0)
        s_shares = info.get("sharesShort", 0)
        s_ratio = info.get("shortRatio", 0)
        if s_pct or s_shares:
            return {
                "short_pct_float": round(float(s_pct)*100, 2) if s_pct else 0,
                "short_shares": s_shares,
                "days_to_cover": s_ratio
            }
    except Exception:
        pass
    return None

@st.cache_data(ttl=3600)
def stat_arb_screener(pairs=None):
    """Statistical Arbitrage Screener using Engle-Granger Cointegration & OLS Half-Life.
    
    FIX-07: Tests cointegration in both directions, keeps lower p-value.
    FIX-08: Uses OU equilibrium mean instead of biased full-window average.
    FIX-09: Scales entry thresholds by half-life.
    """
    try:
        import statsmodels.api as sm
        from statsmodels.tsa.stattools import coint
        import numpy as np
    except ImportError:
        return None
        
    if not pairs:
        pairs = [("GLD", "GDX"), ("XOM", "CVX"), ("JPM", "BAC"), ("QQQ", "XLK"), ("SPY", "TLT")]
    
    results = []
    end = datetime.today()
    start = end - timedelta(days=252)
    
    for t1, t2 in pairs:
        try:
            stk1 = yf.download(t1, start=start, end=end, progress=False)["Close"].dropna()
            stk2 = yf.download(t2, start=start, end=end, progress=False)["Close"].dropna()
            if isinstance(stk1, pd.DataFrame): stk1 = stk1.iloc[:, 0]
            if isinstance(stk2, pd.DataFrame): stk2 = stk2.iloc[:, 0]
            
            df = pd.DataFrame({t1: stk1, t2: stk2}).dropna()
            if len(df) < 100:
                continue
            
            # FIX-07: Test cointegration in both directions, keep lower p-value
            _, pvalue_fwd, _ = coint(df[t1], df[t2])
            _, pvalue_rev, _ = coint(df[t2], df[t1])
            
            if pvalue_fwd <= pvalue_rev:
                pvalue = pvalue_fwd
                dep, indep = t1, t2
                direction_label = f"{t1} ~ {t2}"
            else:
                pvalue = pvalue_rev
                dep, indep = t2, t1
                direction_label = f"{t2} ~ {t1}"
            
            # OLS for Hedge Ratio (Beta) using the canonical direction
            Y = df[dep]
            X = sm.add_constant(df[indep])
            model = sm.OLS(Y, X).fit()
            beta = model.params.iloc[1]
            
            # Spread = dep - beta * indep
            spread = df[dep] - beta * df[indep]
            std_spread = spread.std()
            
            # Ornstein-Uhlenbeck Process for Half-Life
            spread_lag = spread.shift(1).dropna()
            spread_diff = spread.diff().dropna()
            lag_with_const = sm.add_constant(spread_lag)
            ou_model = sm.OLS(spread_diff, lag_with_const).fit()
            ou_intercept = ou_model.params.iloc[0]
            ou_lambda = -ou_model.params.iloc[1]
            half_life = np.log(2) / ou_lambda if ou_lambda > 0 else float('inf')
            
            # FIX-08: Use OU equilibrium mean instead of biased full-window mean
            if ou_lambda > 0:
                eq_mean = ou_intercept / ou_lambda
            else:
                eq_mean = spread.mean()  # fallback if OU not mean-reverting
            
            z_score = (spread.iloc[-1] - eq_mean) / std_spread if std_spread > 0 else 0.0
            
            # FIX-09: Scale entry thresholds by half-life
            # Fast-reverting (3-day HL) → tight thresholds (~1.0)
            # Slow-reverting (60-day HL) → wide thresholds (~2.5)
            clamped_hl = max(3.0, min(float(half_life), 60.0))
            entry_thresh = 1.0 + (clamped_hl / 60.0) * 1.5
            lean_thresh = entry_thresh * 0.6
            
            signal = "Neutral"
            if z_score < -entry_thresh: signal = f"Long {dep} / Short {indep}"
            elif z_score > entry_thresh: signal = f"Short {dep} / Long {indep}"
            elif z_score < -lean_thresh: signal = f"Leaning Long {dep}"
            elif z_score > lean_thresh: signal = f"Leaning Short {dep}"
            
            results.append({
                "t1": t1, "t2": t2,
                "direction": direction_label,
                "pvalue": round(float(pvalue), 4),
                "zscore": round(float(z_score), 2),
                "half_life": round(float(half_life), 1),
                "beta": round(float(beta), 3),
                "coint": pvalue < 0.05,
                "signal": signal,
                "entry_thresh": round(entry_thresh, 2),
            })
        except Exception:
            continue
            
    if results:
        results.sort(key=lambda x: abs(x["zscore"]), reverse=True)
        return results
    return None

@st.cache_data(ttl=600)
def sector_etfs():
    S = {"Technology": "XLK", "Financials": "XLF", "Energy": "XLE", "Healthcare": "XLV",
         "Consumer Staples": "XLP", "Utilities": "XLU", "Consumer Discretionary": "XLY", "Materials": "XLB",
         "Communication Services": "XLC", "Real Estate": "XLRE", "Industrials": "XLI"}
    rows = []
    for name, tkr in S.items():
        q = yahoo_quote(tkr)
        if q: rows.append({"Sector": name, "ETF": tkr, "Price": q["price"], "Pct": q["pct"]})
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def top_movers():
    UNIVERSE = [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","ORCL","CRM",
        "AMD","INTC","QCOM","TXN","ADI","AMAT","LRCX","KLAC","MRVL","SNPS","CDNS",
        "ADBE","INTU","NOW","PANW","CRWD","ZS","FTNT","ANSS","EPAM",
        "JPM","BAC","WFC","GS","MS","BLK","C","AXP","COF","PGR",
        "ICE","CME","SPGI","MCO","V","MA","PYPL","FIS","FISV","WEX",
        "UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","PFE","DHR","BMY",
        "HD","MCD","NKE","LOW","BKNG","TJX","SBUX","MAR",
        "WMT","PG","KO","PEP","PM","MO","CL","GIS","KHC","KMB",
        "GE","RTX","CAT","HON","UNP","LMT","DE","WM","NSC","ITW",
        "XOM","CVX","COP","SLB","EOG","PSX","MPC","OXY","VLO","HAL",
        "LIN","APD","ECL","SHW","NEM","FCX","NUE","VMC","ALB","MOS",
        "PLD","AMT","CCI","EQIX","PSA","SPG","WELL","O","DLR","AVB",
        "NEE","DUK","SO","AEP","D","EXC","PCG","SRE","XEL","CEG",
    ]
    seen = set()
    UNIVERSE = [x for x in UNIVERSE if not (x in seen or seen.add(x))]

    try:
        raw_results = run_async(_fetch_yahoo_quotes_async(UNIVERSE))
        results = [q for q in raw_results if isinstance(q, dict) and q]
        sorted_q = sorted(results, key=lambda x: x["pct"], reverse=True)
        return sorted_q[:10], sorted_q[-10:]
    except Exception as e:
        logger.error({"error": str(e)}, "Top Movers Error")
        return [], []


def calc_stock_fear_greed():
    """5-signal Fear & Greed: VIX, Momentum, Safe Haven, PCR, Junk Demand."""
    try:
        scores = []

        # --- Signal 1: VIX Level — 1-year rolling percentile rank (self-calibrating) ---
        v = yahoo_quote("^VIX")
        if v:
            vix = v["price"]
            # FIX-05: Use 1Y rolling percentile rank instead of hardcoded linear bounds
            try:
                vix_hist = get_yf_ticker("^VIX").history(period="1y")
                if vix_hist is not None and len(vix_hist) >= 20:
                    pct_rank = (vix_hist["Close"] < vix).mean()  # 0..1
                    vix_score = (1 - pct_rank) * 100  # high percentile = fear = low score
                else:
                    vix_score = max(0, min(100, 100 - (vix - 10) / 30 * 100))  # fallback
            except Exception:
                vix_score = max(0, min(100, 100 - (vix - 10) / 30 * 100))  # fallback
            scores.append(("VIX", vix_score))

        # --- Signal 2: Market Momentum (SPY vs 125-day MA) ---
        try:
            h = get_yf_ticker("SPY").history(period="7mo")
            if len(h) >= 125:
                current = h["Close"].iloc[-1]
                ma125 = h["Close"].iloc[-125:].mean()
                # How far above/below MA, mapped 0-100
                pct_above = (current / ma125 - 1) * 100
                mom_score = max(0, min(100, 50 + pct_above * 5))
                scores.append(("Momentum", mom_score))
        except Exception:
            pass

        # --- Signal 3: Safe Haven Demand (TLT vs SPY 20-day relative perf) ---
        try:
            tlt = yahoo_quote("TLT")
            spy = yahoo_quote("SPY")
            if tlt and spy:
                # Positive TLT outperformance = fear; underperformance = greed
                relative = tlt["pct"] - spy["pct"]
                # TLT outperforms by >1% → fear (score 0-30); underperforms → greed (70-100)
                sh_score = max(0, min(100, 50 - relative * 15))
                scores.append(("SafeHaven", sh_score))
        except Exception:
            pass

        # --- Signal 4: Put/Call Ratio (equity options) ---
        try:
            # Use SPY options PCR as proxy
            t = get_yf_ticker("SPY")
            opts = t.options
            if opts:
                chain = t.option_chain(opts[0])
                call_vol = chain.calls["volume"].sum()
                put_vol = chain.puts["volume"].sum()
                pcr = put_vol / call_vol if call_vol > 0 else 1.0
                # PCR 0.5 = extreme greed (100), PCR 1.5 = extreme fear (0)
                pcr_score = max(0, min(100, (1.5 - pcr) / 1.0 * 100))
                scores.append(("PCR", pcr_score))
        except Exception:
            pass

        # --- Signal 5: Junk Bond Demand (HYG vs LQD spread proxy) ---
        try:
            hyg = yahoo_quote("HYG")
            lqd = yahoo_quote("LQD")
            if hyg and lqd:
                # HYG outperforming LQD = risk-on = greed
                spread = hyg["pct"] - lqd["pct"]
                junk_score = max(0, min(100, 50 + spread * 20))
                scores.append(("Junk", junk_score))
        except Exception:
            pass

        if not scores:
            return None, None

        # Equal-weight composite
        total = sum(s for _, s in scores) / len(scores)
        score = int(total)

        if score >= 75:   label = "Extreme Greed"
        elif score >= 55: label = "Greed"
        elif score >= 45: label = "Neutral"
        elif score >= 25: label = "Fear"
        else:             label = "Extreme Fear"

        return score, label
    except Exception:
        return None, None

def market_snapshot_str():
    try:
        pst = pytz.timezone("US/Pacific")
        now_str = datetime.now(pytz.utc).astimezone(pst).strftime("%A, %B %d, %Y %H:%M PST")
        spx_q  = yahoo_quote("^GSPC")
        spy_q  = yahoo_quote("SPY")
        qs     = multi_quotes(["QQQ", "IWM", "DX-Y.NYB", "GLD", "TLT", "BTC-USD", "CL=F"])
        v      = vix_price()

        parts = []
        if spx_q: parts.append(f"SPX: {spx_q['price']:,.2f} ({spx_q['pct']:+.2f}%)")
        if spy_q: parts.append(f"SPY: ${spy_q['price']:,.2f} ({spy_q['pct']:+.2f}%)")
        parts += [f"{q['ticker']}: ${q['price']:,.2f} ({q['pct']:+.2f}%)" for q in qs]
        if v: parts.append(f"VIX: {v}")

        prices = " | ".join(parts)
        return "CURRENT DATE/TIME: " + now_str + "\nLIVE MARKET DATA: " + prices
    except Exception:
        return ""


@st.cache_data(ttl=300)
def build_brief_context():
    """Assembles the enriched context for /brief and /geo."""
    GEO_QUERY = (
        "war OR strike OR attack OR sanctions OR geopolitical OR crisis "
        "OR central bank OR interest rate OR oil OR tariff OR embargo "
        "OR Israel OR Iran OR Hamas OR Hezbollah OR Ukraine OR Russia "
        "OR Taiwan OR China OR Red Sea OR Houthi OR Gaza OR nuclear "
        "OR missile OR airstrike OR invasion OR ceasefire"
    )

    def _fetch_geo():
        try:
            r = requests.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": GEO_QUERY + " sourcelang:english", "mode": "artlist",
                        "maxrecords": 20, "format": "json", "timespan": "72h"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"},
                timeout=8,
            )
            if r.status_code != 200: return []
            arts = [a for a in r.json().get("articles", []) if _is_english(a.get("title", ""))]
            lines, seen = [], set()
            for a in arts:
                title = a.get("title", "").strip()
                if not title or title in seen: continue
                seen.add(title)
                domain = a.get("domain", "")
                sd = a.get("seendate", "")
                date_str = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
                lines.append(f"  • [{date_str}] {title} ({domain})")
            return lines
        except Exception:
            return []

    # Simple sequential wait since we got rid of ThreadPoolExecutor entirely
    base = market_snapshot_str()
    geo_headlines = _fetch_geo()

    if geo_headlines:
        headlines_block = "LIVE GEOPOLITICAL & MACRO HEADLINES (last 72h, via GDELT):\n" + "\n".join(geo_headlines[:20])
    else:
        headlines_block = "LIVE GEO HEADLINES: unavailable (GDELT timeout — use model knowledge for recent conflicts)"

    try:
        macro_qs = multi_quotes(["^TNX", "^TYX", "DX-Y.NYB", "GC=F", "CL=F", "TLT", "GLD", "UUP", "HYG", "LQD"])
        macro_lines = []
        labels = {"^TNX": "10Y Yield", "^TYX": "30Y Yield", "DX-Y.NYB": "DXY",
                  "GC=F": "Gold", "CL=F": "WTI Crude", "TLT": "TLT (20Y Bond)",
                  "GLD": "GLD ETF", "UUP": "Dollar ETF", "HYG": "HY Credit", "LQD": "IG Credit"}
        for q in macro_qs:
            lbl = labels.get(q["ticker"], q["ticker"])
            macro_lines.append(f"  {lbl}: {q['price']:,.2f} ({q['pct']:+.2f}%)")
        macro_block = "MACRO & RATES DATA (for trade context):\n" + "\n".join(macro_lines)
    except Exception:
        macro_block = ""

    sections = [base, headlines_block]
    if macro_block: sections.append(macro_block)
    return "\n\n".join(s for s in sections if s)


# ════════════════════════════════════════════════════════════════════
# FRED
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def fred_series(series_id, key, limit=36):
    if not key: return None
    try:
        data = _fetch_robust_json("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": key, "sort_order": "desc",
                    "limit": limit, "file_type": "json"}, timeout=10)
        df = pd.DataFrame(data.get("observations", []))
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        return df.dropna(subset=["value"]).sort_values("date")
    except:
        return None

# ════════════════════════════════════════════════════════════════════
# POLYMARKET
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def polymarket_events(limit=60):
    try:
        return _fetch_robust_json("https://gamma-api.polymarket.com/events",
            params={"limit": limit, "order": "volume", "ascending": "false", "active": "true"}, timeout=10)
    except:
        return []

@st.cache_data(ttl=300)
def polymarket_markets(limit=60):
    try:
        return _fetch_robust_json("https://gamma-api.polymarket.com/markets",
            params={"limit": limit, "order": "volume24hr", "ascending": "false", "active": "true"}, timeout=10)
    except:
        return []

def detect_unusual_poly(markets):
    out = []
    for m in markets:
        try:
            v24 = _safe_float(m.get("volume24hr", 0))
            vtot = _safe_float(m.get("volume", 0))
            if vtot > 0 and v24 / vtot > 0.38 and v24 > 5000: out.append(m)
        except:
            pass
    return out[:6]

def _parse_poly_field(field):
    if not field: return []
    if isinstance(field, str):
        try: return json.loads(field)
        except: return []
    return field if isinstance(field, list) else []

# ════════════════════════════════════════════════════════════════════
# CRYPTO
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def fear_greed_crypto():
    try:
        d = _fetch_robust_json("https://api.alternative.me/fng/?limit=1", timeout=8)
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except:
        return None, None

@st.cache_data(ttl=600)
def crypto_markets():
    try:
        data = _fetch_robust_json("https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 20,
                    "page": 1, "price_change_percentage": "24h"}, timeout=15)
        if isinstance(data, list):
            return data
    except:
        return []

@st.cache_data(ttl=600)
def crypto_global():
    try:
        return _fetch_robust_json("https://api.coingecko.com/api/v3/global", timeout=8).get("data", {})
    except:
        return {}


# ════════════════════════════════════════════════════════════════════
# NEWS
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def gdelt_news(query, max_rec=15):
    endpoints = [
        {"url": "https://api.gdeltproject.org/api/v2/doc/doc",
         "params": {"query": query + " sourcelang:english", "mode": "artlist", "maxrecords": max_rec, "format": "json", "timespan": "72h"}},
        {"url": "https://api.gdeltproject.org/api/v2/doc/doc",
         "params": {"query": query, "mode": "artlist", "maxrecords": max_rec, "format": "json", "timespan": "168h"}},
    ]
    for ep in endpoints:
        try:
            data = _fetch_robust_json(ep["url"], params=ep["params"], timeout=8)
            arts = data.get("articles", [])
            if arts:
                filtered = [a for a in arts if _is_english(a.get("title", ""))][:max_rec]
                if filtered: return filtered
        except Exception:
            continue
    return []

@st.cache_data(ttl=300)
def newsapi_headlines(key, query="stock market finance"):
    if not key: return []
    try:
        return _fetch_robust_json("https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt", "pageSize": 10, "apiKey": key}, timeout=10).get("articles", [])
    except:
        return []

@st.cache_data(ttl=300)
def finnhub_news(key):
    if not key: return []
    try:
        return _fetch_robust_json("https://finnhub.io/api/v1/news",
            params={"category": "general", "token": key}, timeout=10)[:12]
    except:
        return []

@st.cache_data(ttl=600)
def finnhub_insider(ticker, key):
    if not key: return []
    try:
        return _fetch_robust_json("https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": ticker, "token": key}, timeout=10).get("data", [])[:15]
    except:
        return []

@st.cache_data(ttl=1800)
def finnhub_officers(ticker, key):
    role_map = {}
    if key:
        try:
            data = _fetch_robust_json("https://finnhub.io/api/v1/stock/executive",
                params={"symbol": ticker, "token": key}, timeout=10)
            for o in data.get("executive", []) or []:
                name = str(o.get("name", "")).strip()
                title = str(o.get("position", "") or o.get("title", "") or "")
                if not name or not title: continue
                name_upper = name.upper()
                role_map[name_upper] = title
                parts = name.split()
                if len(parts) >= 2:
                    last_first = (parts[-1] + " " + " ".join(parts[:-1])).upper()
                    role_map[last_first] = title
                    role_map[(parts[-1] + " " + parts[0]).upper()] = title
        except:
            pass

    try:
        tk = get_yf_ticker(ticker)
        if tk:
            # 1. Extract from insider_transactions FIRST (generic titles like "Officer")
            try:
                idf = tk.insider_transactions
                if idf is not None and not idf.empty:
                    if 'Insider' in idf.columns and 'Position' in idf.columns:
                        for _, row in idf.iterrows():
                            ins_name = str(row['Insider']).strip().upper()
                            pos = str(row['Position']).strip()
                            if ins_name and pos and ins_name not in role_map:
                                role_map[ins_name] = pos
            except:
                pass

            # 2. companyOfficers override generic titles with real ones
            _generic = {"Officer", "Director", "officer", "director", ""}
            officers = tk.info.get("companyOfficers", [])
            for o in officers:
                name = str(o.get("name", "")).strip()
                title = str(o.get("title", "")).strip()
                if not name or not title: continue
                clean_name = name.upper().replace(".", "").replace(",", "")
                for pfx in ["MR ", "MS ", "MRS ", "DR ", "PROF "]:
                    if clean_name.startswith(pfx):
                        clean_name = clean_name[len(pfx):].strip()
                # Always overwrite if existing entry is generic
                if clean_name not in role_map or role_map.get(clean_name) in _generic:
                    role_map[clean_name] = title
                # Create reversed-name entries (LAST FIRST / LAST FIRST MIDDLE)
                parts = clean_name.split()
                if len(parts) >= 2:
                    last_first_all = parts[-1] + " " + " ".join(parts[:-1])
                    last_first = parts[-1] + " " + parts[0]
                    for variant in (last_first_all, last_first):
                        if variant not in role_map or role_map.get(variant) in _generic:
                            role_map[variant] = title
    except:
        pass

    return role_map


# ════════════════════════════════════════════════════════════════════
# EARNINGS
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def get_earnings_calendar(today_str=None):
    MAJOR = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "GS", "BAC",
             "NFLX", "AMD", "INTC", "CRM", "ORCL", "V", "MA", "WMT", "XOM", "CVX", "UNH",
             "JNJ", "PFE", "ABBV", "LLY", "BRK-B", "HD", "DIS", "SHOP", "PLTR", "SNOW"]
    rows = []
    for tkr in MAJOR:
        try:
            t = get_yf_ticker(tkr)
            if t is None: continue
            info = t.info
            cal = t.calendar
            if cal is not None and not (cal.empty if hasattr(cal, "empty") else False):
                if isinstance(cal, pd.DataFrame):
                    if "Earnings Date" in cal.index:
                        ed = cal.loc["Earnings Date"]
                        ed = ed.iloc[0] if hasattr(ed, "iloc") else ed
                        eps = float(cal.loc["EPS Estimate"].iloc[0]) if "EPS Estimate" in cal.index else None
                    else:
                        continue
                elif isinstance(cal, dict):
                    ed = cal.get("Earnings Date", [None])
                    ed = ed[0] if isinstance(ed, list) and len(ed) > 0 else (ed if not isinstance(ed, list) else None)
                    eps = cal.get("EPS Estimate", cal.get("Earnings Average", None))
                else:
                    continue
                if ed is None: continue
                rows.append({
                    "Ticker": tkr,
                    "Company": info.get("shortName", tkr)[:22],
                    "EarningsDate": pd.to_datetime(ed).date(),
                    "EPS Est": round(float(eps), 2) if eps is not None else None,
                    "Sector": info.get("sector", "—"), 
                })
        except:
            pass
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows).dropna(subset=["EarningsDate"]).sort_values("EarningsDate")

# ════════════════════════════════════════════════════════════════════
# 0DTE — ALPACA REST API 
# ════════════════════════════════════════════════════════════════════

def _alpaca_headers():
    try:
        return {
            "APCA-API-KEY-ID": st.secrets["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": st.secrets["ALPACA_SECRET_KEY"],
            "Accept": "application/json",
        }
    except (KeyError, FileNotFoundError):
        return None

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
            "volume": int(_safe_float(daily_bar.get("v"))),
            "minute_vwap": _safe_float(minute_bar.get("vw")),
        }
    except Exception:
        return None

def get_spx_metrics():
    spy_snap = get_stock_snapshot("SPY")
    try:
        spx_q = yahoo_quote("^GSPC")
        spx_price = round(spx_q["price"], 2) if spx_q and spx_q.get("price", 0) > 0 else None
    except Exception:
        spx_price = None

    if spy_snap:
        spot = spx_price if spx_price else round(spy_snap["price"] * 10, 2)
        return {
            "spot": spot,
            "vwap": round(spy_snap["vwap"] * 10, 2),
            "open": round(spy_snap["open"] * 10, 2),
            "high": round(spy_snap["high"] * 10, 2),
            "low": round(spy_snap["low"] * 10, 2),
            "volume": spy_snap["volume"],
        }
    elif spx_price:
        return {"spot": spx_price, "vwap": spx_price, "open": 0, "high": 0, "low": 0, "volume": 0}
    return None

def _parse_strike_from_symbol(sym):
    try: return int(sym[-8:]) / 1000.0
    except Exception: return 0.0

def _parse_type_from_symbol(sym):
    try:
        for i, ch in enumerate(sym):
            if ch in ("C", "P") and i > 3:
                return "call" if ch == "C" else "put"
        return "unknown"
    except Exception: return "unknown"

@st.cache_resource(ttl=30)
def fetch_0dte_chain(underlying="SPY"):
    headers = _alpaca_headers()
    if not headers: return [], "No Alpaca API keys configured"

    snap = get_stock_snapshot(underlying)
    if not snap or snap["price"] <= 0: return [], "Could not fetch spot price"
    spot = snap["price"]
    today_str = datetime.today().strftime("%Y-%m-%d")

    try:
        c_data = _fetch_robust_json("https://paper-api.alpaca.markets/v2/options/contracts", 
                                    headers=headers, params={"underlying_symbols": underlying, "status": "active", "limit": 1000}, timeout=10)
        dates = [c.get("expiration_date") for c in c_data.get("option_contracts", []) if c.get("expiration_date") and c.get("expiration_date") >= today_str]
        if not dates: return [], "No active option contracts found"
        target_expiry = sorted(list(set(dates)))[0]
    except Exception as e:
        return [], f"Error locating expiry: {str(e)}"

    try:
        url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{underlying}"
        params = {"feed": "indicative", "limit": 250, "expiration_date": target_expiry}
        data = _fetch_robust_json(url, headers=headers, params=params, timeout=15)
        snapshots = data.get("snapshots", {})
        seen_tokens = set()
        pages = 0

        while data.get("next_page_token") and pages < 10:
            token = data["next_page_token"]
            if token in seen_tokens:
                break
            seen_tokens.add(token)
            params["page_token"] = token
            data = _fetch_robust_json(url, headers=headers, params=params, timeout=15)
            snapshots.update(data.get("snapshots", {}))
            pages += 1

        chain = []
        lower_bound, upper_bound = spot * 0.98, spot * 1.02

        for sym, snap_data in snapshots.items():
            greeks = snap_data.get("greeks", {})
            quote = snap_data.get("latestQuote", {})
            trade = snap_data.get("latestTrade", {})
            strike = _parse_strike_from_symbol(sym)
            opt_type = _parse_type_from_symbol(sym)

            if strike <= 0 or strike < lower_bound or strike > upper_bound: continue
            bid = _safe_float(quote.get("bp"))
            ask = _safe_float(quote.get("ap"))
            last = _safe_float(trade.get("p"))
            mid = round((bid + ask) / 2, 2) if (bid + ask) > 0 else last
            
            # Use Newton-Raphson dynamically if mid price is available
            r_rate = 0.045
            T_val = 0.5 / 365.0  # Appx half a trading day for 0DTE flow
            
            calculated_iv = get_iv_newton(spot, strike, T_val, r_rate, mid, opt_type)
            if calculated_iv is not None and calculated_iv > 0:
                bs_override = bs_greeks_engine(spot, strike, T_val, r_rate, calculated_iv, opt_type)
                final_iv = calculated_iv
                final_delta = bs_override["delta"]
                final_gamma = bs_override["gamma"]
                final_theta = bs_override["theta"]
            else:
                final_iv = _safe_float(snap_data.get("impliedVolatility"))
                final_delta = _safe_float(greeks.get("delta"))
                final_gamma = _safe_float(greeks.get("gamma"))
                final_theta = _safe_float(greeks.get("theta"))

            chain.append({
                "symbol": sym, "strike": strike, "type": opt_type,
                "bid": bid, "ask": ask, "mid": mid, "last": last,
                "iv": final_iv,
                "delta": final_delta, "gamma": final_gamma,
                "theta": final_theta, "vega": _safe_float(greeks.get("vega")),
                "oi": int(_safe_float(snap_data.get("openInterest", 0))), "volume": int(_safe_float(trade.get("s", 0))),
            })
        chain.sort(key=lambda x: x["strike"])
        return chain, "OK"
    except Exception as e:
        return [], f"Error: {str(e)}"

def compute_gex_profile(chain, spot):
    """Local DuckDB Time-Series Engine for instantaneous querying of aggregations."""
    gex = {}
    if spot <= 0 or not chain: return gex
    
    try:
        import duckdb
        import pandas as pd
        df = pd.DataFrame(chain)
        if "gamma" not in df.columns or "oi" not in df.columns or "strike" not in df.columns:
            raise ValueError("Missing columns")
            
        with duckdb.connect(database=':memory:') as con:
            con.execute("CREATE TABLE options_chain AS SELECT * FROM df")
            
            query = f"""
                SELECT strike, 
                       SUM(CASE WHEN type = 'call' THEN 1 ELSE -1 END * oi * 100 * ABS(gamma) * POWER({spot}, 2) * 0.01 / 1000000) as gex
                FROM options_chain
                GROUP BY strike
                ORDER BY strike
            """
            res = con.execute(query).df()
            gex = {row['strike']: row['gex'] for _, row in res.iterrows()}
            return gex
    except Exception as e:
        logger.error({"error": str(e)}, "DuckDB Engine Error")
        # fallback
        for opt in chain:
            k = opt["strike"]
            oi = opt.get("oi", 0)
            gamma = abs(opt.get("gamma", 0))
            raw_gex = oi * 100 * gamma * (spot ** 2) * 0.01
            sign = 1.0 if opt["type"] == "call" else -1.0
            gex[k] = gex.get(k, 0) + sign * raw_gex / 1_000_000
        return dict(sorted(gex.items()))

def find_gamma_flip(gex_profile):
    if not gex_profile: return None
    strikes = sorted(gex_profile.keys())
    for i in range(1, len(strikes)):
        if gex_profile[strikes[i - 1]] <= 0 and gex_profile[strikes[i]] > 0: return strikes[i]
    vals = list(gex_profile.values())
    return strikes[0] if all(v >= 0 for v in vals) else strikes[-1]


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

    # Compute GEX if not provided
    if gex_profile is None:
        gex_profile = compute_gex_profile(chain, spot / 10)

    gamma_flip_spy = find_gamma_flip(gex_profile)
    gamma_flip = gamma_flip_spy * 10 if gamma_flip_spy else None
    max_pain_spy = compute_max_pain(chain)
    max_pain = max_pain_spy * 10 if max_pain_spy else None
    pcr = compute_pcr(chain)

    # Expected move from VIX (annualized → daily)
    daily_em = spot * (vix / 100) / (252 ** 0.5)

    score = 0.0
    signals = []  # list of (name, value, weight, direction_str, color)

    # ──────────────────────────────────────────────────────────
    # SIGNAL 1: Gamma Regime (weight: 3.0)
    # Positive net GEX = dealers long gamma → mean-reversion (bullish, damped)
    # Negative net GEX = dealers short gamma → trend-following (bearish, volatile)
    # ──────────────────────────────────────────────────────────
    if gex_profile:
        net_gex = sum(gex_profile.values())
        if net_gex > 0:
            contrib = 2.5
            signals.append(("Gamma Regime", f"Net +{net_gex:.1f}M", contrib,
                           "POSITIVE — Dealers hedge → dampened, mean-reverting", "#00CC44"))
        elif net_gex < -0.5:
            contrib = -2.5
            signals.append(("Gamma Regime", f"Net {net_gex:.1f}M", contrib,
                           "NEGATIVE — Dealers amplify → trending, volatile", "#FF4444"))
        else:
            contrib = 0.0
            signals.append(("Gamma Regime", f"Net {net_gex:.1f}M", contrib,
                           "NEUTRAL — Near gamma-neutral zone", "#FF8C00"))
        score += contrib

    # ──────────────────────────────────────────────────────────
    # SIGNAL 2: GEX Tilt — Call-side vs Put-side gamma mass
    # More call gamma above spot = resistance (bearish pressure)
    # More put gamma below spot = support (bullish floor)
    # ──────────────────────────────────────────────────────────
    if gex_profile and gamma_flip:
        above_gex = sum(v for k, v in gex_profile.items() if k * 10 > spot)
        below_gex = sum(v for k, v in gex_profile.items() if k * 10 < spot)
        total_abs = abs(above_gex) + abs(below_gex)
        if total_abs > 0:
            tilt_ratio = (above_gex - below_gex) / total_abs
            # Positive tilt = more call gamma above = cap/resistance = slightly bearish for breakout
            # But if we're below gamma flip, net puts dominate = bearish
            if spot > gamma_flip:
                contrib = 1.5  # above flip = bullish regime
                signals.append(("GEX Tilt", f"Above Gamma Flip (Δ{spot-gamma_flip:+.0f})", contrib,
                               "BULLISH — Spot above dealer flip point", "#00CC44"))
            else:
                contrib = -1.5
                signals.append(("GEX Tilt", f"Below Gamma Flip (Δ{spot-gamma_flip:+.0f})", contrib,
                               "BEARISH — Spot below dealer flip point", "#FF4444"))
            score += contrib

    # ──────────────────────────────────────────────────────────
    # SIGNAL 3: Typical Price vs Average (weight: 2.5)
    # FIX-11: Renamed from "VWAP Position" — (H+L+C)/3 is Typical Price, not VWAP
    # Price > typical price average = buyers in control
    # Price < typical price average = sellers in control
    # ──────────────────────────────────────────────────────────
    vwap_dev = (spot - vwap) / vwap * 100
    if abs(vwap_dev) > 0.05:
        if vwap_dev > 0:
            contrib = min(vwap_dev * 8, 2.5)  # scaled, capped at 2.5
            signals.append(("Typical Price vs Avg", f"{vwap_dev:+.2f}% above", contrib,
                           f"BULLISH — Spot ${spot:,.0f} above daily typical price (H+L+C)/3 ${vwap:,.0f}", "#00CC44"))
        else:
            contrib = max(vwap_dev * 8, -2.5)
            signals.append(("Typical Price vs Avg", f"{vwap_dev:+.2f}% below", contrib,
                           f"BEARISH — Spot ${spot:,.0f} below daily typical price (H+L+C)/3 ${vwap:,.0f}", "#FF4444"))
        score += contrib
    else:
        signals.append(("Typical Price vs Avg", f"{vwap_dev:+.2f}%", 0.0,
                       "NEUTRAL — Spot at typical price equilibrium", "#888888"))

    # ──────────────────────────────────────────────────────────
    # SIGNAL 4: Put/Call Ratio (weight: 2.0)
    # Low PCR (<0.7) = extreme call buying = bullish sentiment
    # High PCR (>1.2) = extreme put buying = bearish sentiment / hedging
    # ──────────────────────────────────────────────────────────
    if pcr is not None:
        if pcr < 0.7:
            contrib = 2.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "BULLISH — Heavy call buying, strong risk appetite", "#00CC44"))
        elif pcr < 0.85:
            contrib = 1.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "MILDLY BULLISH — Moderate call skew", "#00CC44"))
        elif pcr > 1.3:
            contrib = -2.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "BEARISH — Heavy put hedging / fear", "#FF4444"))
        elif pcr > 1.0:
            contrib = -1.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "MILDLY BEARISH — Elevated put hedging", "#FF4444"))
        else:
            contrib = 0.0
            signals.append(("Put/Call Ratio", f"{pcr:.2f}", contrib,
                           "NEUTRAL — Balanced call/put flow", "#888888"))
        score += contrib

    # ──────────────────────────────────────────────────────────
    # SIGNAL 5: Max Pain Gravity (weight: 1.5)
    # SPX tends to pin near max pain at expiry (dealer hedging effect)
    # If spot > max_pain: bearish pull. If spot < max_pain: bullish pull.
    # ──────────────────────────────────────────────────────────
    if max_pain:
        mp_dist = spot - max_pain
        mp_pct = mp_dist / spot * 100
        if abs(mp_pct) > 0.3:
            if mp_dist > 0:
                contrib = -1.5  # spot above max pain → pull down
                signals.append(("Max Pain Gravity", f"${max_pain:,.0f} ({mp_pct:+.1f}%)", contrib,
                               f"BEARISH PULL — Expiry magnet ${abs(mp_dist):.0f} pts below spot", "#FF4444"))
            else:
                contrib = 1.5  # spot below max pain → pull up
                signals.append(("Max Pain Gravity", f"${max_pain:,.0f} ({mp_pct:+.1f}%)", contrib,
                               f"BULLISH PULL — Expiry magnet ${abs(mp_dist):.0f} pts above spot", "#00CC44"))
            score += contrib
        else:
            signals.append(("Max Pain Gravity", f"${max_pain:,.0f} ({mp_pct:+.1f}%)", 0.0,
                           "PINNED — Spot near max pain; expect low range", "#888888"))

    # ──────────────────────────────────────────────────────────
    # SIGNAL 6: Vol Regime (weight: 2.0)
    # FIX-06: Collapsed VIX Term Structure + VIX Level into a single signal
    # to avoid double-counting volatility. Uses a 2×2 grid:
    #   contango + low vol  = +1.5 (bullish)
    #   contango + elevated = +0.5 (neutral-ish)
    #   backwardation + moderate = -1.0
    #   backwardation + crisis  = -2.0
    # ──────────────────────────────────────────────────────────
    if contango is not None:
        is_contango = bool(contango)
        if is_contango and vix < 20:
            contrib = 1.5
            vol_desc = "BULLISH — Contango + low vol: calm, risk-on regime"
            vol_color = "#00CC44"
            vol_val = f"Contango, VIX {vix:.1f}"
        elif is_contango and vix >= 20:
            contrib = 0.5
            vol_desc = "NEUTRAL — Contango but elevated VIX: cautious calm"
            vol_color = "#FF8C00"
            vol_val = f"Contango, VIX {vix:.1f}"
        elif not is_contango and vix <= 30:
            contrib = -1.0
            vol_desc = "BEARISH — Backwardation + moderate VIX: stress building"
            vol_color = "#FF4444"
            vol_val = f"Backwardation, VIX {vix:.1f}"
        else:  # backwardation + vix > 30
            contrib = -2.0
            vol_desc = "CRISIS — Backwardation + extreme VIX: panic regime"
            vol_color = "#FF4444"
            vol_val = f"Backwardation, VIX {vix:.1f}"
        signals.append(("Vol Regime", vol_val, contrib, vol_desc, vol_color))
        score += contrib
    elif vix is not None:
        # Fallback if contango data unavailable — use VIX level only
        if vix < 15:
            contrib = 0.5
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "LOW VOL — Complacent, slight upward drift bias", "#00CC44"))
        elif vix <= 20:
            contrib = 0.0
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "NORMAL — Standard volatility regime", "#888888"))
        elif vix <= 30:
            contrib = -1.0
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "ELEVATED — Hedging spike", "#FF8C00"))
        else:
            contrib = -1.5
            signals.append(("Vol Regime", f"VIX {vix:.1f}", contrib,
                           "CRISIS — Extreme fear", "#FF4444"))
        score += contrib

    # ──────────────────────────────────────────────────────────
    # SIGNAL 7: RSI(14) — Momentum Oscillator (weight: ±1.0/1.5)
    # ──────────────────────────────────────────────────────────
    try:
        import numpy as np
        spy_hist = get_yf_ticker("SPY").history(period="60d")
        if spy_hist is not None and len(spy_hist) >= 20:
            _closes = spy_hist["Close"]
            # RSI(14) calculation
            _delta_r = _closes.diff()
            _gain = _delta_r.where(_delta_r > 0, 0.0).rolling(14).mean()
            _loss = (-_delta_r.where(_delta_r < 0, 0.0)).rolling(14).mean()
            _rs = _gain / _loss.replace(0, np.nan)
            _rsi = 100.0 - (100.0 / (1.0 + _rs))
            rsi_val = float(_rsi.iloc[-1]) if not _rsi.empty else 50.0

            if rsi_val >= 70:
                contrib = -1.0
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "OVERBOUGHT — Momentum exhaustion, mean-reversion likely", "#FF4444"))
            elif rsi_val <= 30:
                contrib = 1.5
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "OVERSOLD — Extreme pessimism, bounce setup", "#00CC44"))
            elif 55 <= rsi_val < 70:
                contrib = 0.5
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "BULLISH MOMENTUM — Trend strength building", "#00CC44"))
            elif 30 < rsi_val <= 45:
                contrib = -0.5
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "BEARISH MOMENTUM — Selling pressure dominant", "#FF4444"))
            else:
                contrib = 0.0
                signals.append(("RSI(14)", f"{rsi_val:.1f}", contrib,
                               "NEUTRAL — No directional edge from momentum", "#888888"))
            score += contrib

            # SIGNAL 8: MACD(12,26,9) — Trend Following (weight: ±0.5/1.5)
            _ema12 = _closes.ewm(span=12, adjust=False).mean()
            _ema26 = _closes.ewm(span=26, adjust=False).mean()
            _macd_line = _ema12 - _ema26
            _signal_line = _macd_line.ewm(span=9, adjust=False).mean()
            _histogram = _macd_line - _signal_line

            hist_now = float(_histogram.iloc[-1])
            hist_prev = float(_histogram.iloc[-2]) if len(_histogram) >= 2 else 0.0

            # Crossover detection
            if hist_now > 0 and hist_prev <= 0:
                contrib = 1.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BULLISH CROSSOVER — MACD crossed above signal line", "#00CC44"))
            elif hist_now < 0 and hist_prev >= 0:
                contrib = -1.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BEARISH CROSSOVER — MACD crossed below signal line", "#FF4444"))
            elif hist_now > 0:
                contrib = 0.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BULLISH — MACD above signal, momentum positive", "#00CC44"))
            elif hist_now < 0:
                contrib = -0.5
                signals.append(("MACD", f"Histogram {hist_now:+.2f}", contrib,
                               "BEARISH — MACD below signal, momentum negative", "#FF4444"))
            else:
                contrib = 0.0
                signals.append(("MACD", "Flat", contrib,
                               "NEUTRAL — No MACD signal", "#888888"))
            score += contrib
    except Exception:
        pass  # Technical signals are optional; don't break if yf fails

    # ──────────────────────────────────────────────────────────
    # DECISION: weighted score → direction + confidence
    # ──────────────────────────────────────────────────────────
    max_possible = sum(abs(s[2]) for s in signals) or 1.0
    normalized = score / max_possible  # -1.0 to +1.0

    if score >= 4.0:
        direction, color = "BULLISH", "#00CC44"
        confidence = "HIGH" if score >= 6.5 else "MEDIUM"
    elif score >= 2.0:
        direction, color = "LEAN BULLISH", "#00CC44"
        confidence = "MEDIUM" if score >= 3.0 else "LOW"
    elif score <= -4.0:
        direction, color = "BEARISH", "#FF4444"
        confidence = "HIGH" if score <= -6.5 else "MEDIUM"
    elif score <= -2.0:
        direction, color = "LEAN BEARISH", "#FF4444"
        confidence = "MEDIUM" if score <= -3.0 else "LOW"
    else:
        direction, color = "NEUTRAL", "#FF8C00"
        confidence = "LOW"

    # Expected range based on direction + VIX
    if "BULLISH" in direction:
        range_low = f"${spot:,.0f}"
        range_high = f"${spot + daily_em * 0.6:,.0f}"
    elif "BEARISH" in direction:
        range_low = f"${spot - daily_em * 0.6:,.0f}"
        range_high = f"${spot:,.0f}"
    else:
        range_low = f"${spot - daily_em * 0.3:,.0f}"
        range_high = f"${spot + daily_em * 0.3:,.0f}"

    return {
        "direction": direction,
        "direction_color": color,
        "confidence": confidence,
        "score": round(score, 1),
        "max_score": round(max_possible, 1),
        "normalized": round(normalized, 2),
        "daily_em": round(daily_em, 1),
        "expected_range": f"{range_low} – {range_high}",
        "signals": signals,  # list of (name, value, weight, description, color)
        "spot": spot,
        "vwap": vwap,
        "gamma_flip": gamma_flip,
        "max_pain": max_pain,
        "pcr": pcr,
        "vix": vix,
    }


def compute_max_pain(chain):
    """O(N) prefix-sum max pain using Kahan Summation."""
    if not chain: return None
    strikes = sorted(set(opt["strike"] for opt in chain))
    if not strikes: return None
    
    call_oi, put_oi = {}, {}
    for opt in chain:
        k = opt["strike"]
        if opt["type"] == "call": call_oi[k] = call_oi.get(k, 0) + opt.get("oi", 0)
        else: put_oi[k] = put_oi.get(k, 0) + opt.get("oi", 0)

    s0 = strikes[0]
    pain = 0.0
    pain_c = 0.0
    for k in strikes:
        c, p = call_oi.get(k, 0), put_oi.get(k, 0)
        val = 0
        if s0 > k: val = c * (s0 - k)
        if s0 < k: val = p * (k - s0)
        y = val - pain_c
        t = pain + y
        pain_c = (t - pain) - y
        pain = t

    min_pain, mp_strike = pain, s0
    cum_call_left = call_oi.get(s0, 0)
    total_put = sum(put_oi.values())
    cum_put_left = put_oi.get(s0, 0)

    for i in range(1, len(strikes)):
        gap = strikes[i] - strikes[i - 1]
        put_right = total_put - cum_put_left
        val = (gap * cum_call_left) - (gap * put_right)
        y = val - pain_c
        t = pain + y
        pain_c = (t - pain) - y
        pain = t

        if pain < min_pain:
            min_pain = pain
            mp_strike = strikes[i]

        cum_call_left += call_oi.get(strikes[i], 0)
        cum_put_left += put_oi.get(strikes[i], 0)

    return mp_strike


def compute_pcr(chain):
    call_oi = sum(o.get("oi", 0) for o in chain if o["type"] == "call")
    put_oi = sum(o.get("oi", 0) for o in chain if o["type"] == "put")
    return round(put_oi / call_oi, 2) if call_oi > 0 else None

# ════════════════════════════════════════════════════════════════════
# CBOE GEX 
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def fetch_cboe_gex(ticker="SPX"):
    urls = [
        f"https://cdn.cboe.com/api/global/delayed_quotes/options/_{ticker}.json",
        f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json",
    ]
    for url in urls:
        try:
            data = _fetch_robust_json(url, timeout=15)
            raw = pd.DataFrame.from_dict(data)
            spot = float(raw.loc["current_price", "data"])
            opts = pd.DataFrame(raw.loc["options", "data"])

            opts["type"] = opts["option"].str.extract(r"\d([A-Z])\d")
            opts["strike"] = opts["option"].str.extract(r"\d[A-Z](\d+)\d\d\d").astype(float)
            opts["expiration"] = pd.to_datetime(opts["option"].str.extract(r"[A-Z](\d+)")[0], format="%y%m%d")

            for col in ("gamma", "open_interest", "iv", "delta", "theta", "vega"):
                if col in opts.columns:
                    opts[col] = pd.to_numeric(opts[col], errors="coerce").fillna(0)

            return spot, opts
        except Exception:
            continue
    return None, None

def compute_cboe_gex_profile(spot, option_df, expiry_limit_days=365, strike_pct=0.05):
    if option_df is None or option_df.empty or spot <= 0: return {}
    df = option_df.copy()
    cutoff = pd.Timestamp("today") + pd.Timedelta(days=expiry_limit_days)
    lo, hi = spot * (1 - strike_pct), spot * (1 + strike_pct)

    df = df[(df["expiration"] <= cutoff) & (df["strike"] >= lo) & (df["strike"] <= hi) & (df["gamma"] > 0) & (df["open_interest"] > 0)]
    if df.empty: return {}

    df["gex"] = spot * df["gamma"] * df["open_interest"] * 100 * spot * 0.01
    df["gex"] = df.apply(lambda r: -r["gex"] if r["type"] == "P" else r["gex"], axis=1)

    by_strike = df.groupby("strike")["gex"].sum() / 1_000_000
    return {k / 10: v for k, v in by_strike.items()}

def compute_cboe_total_gex(spot, option_df):
    if option_df is None or option_df.empty or spot <= 0: return None
    df = option_df.copy()
    df["gex"] = spot * df["gamma"] * df["open_interest"] * 100 * spot * 0.01
    df["gex"] = df.apply(lambda r: -r["gex"] if r["type"] == "P" else r["gex"], axis=1)
    return round(df["gex"].sum() / 1_000_000_000, 4)

def compute_cboe_pcr(option_df):
    if option_df is None or option_df.empty: return None
    if "type" not in option_df.columns or "open_interest" not in option_df.columns: return None
    call_oi = option_df[option_df["type"] == "C"]["open_interest"].sum()
    put_oi  = option_df[option_df["type"] == "P"]["open_interest"].sum()
    return round(put_oi / call_oi, 2) if call_oi > 0 else None

@st.cache_resource(ttl=60)
def fetch_vix_data():
    result = {"vix": None, "vix9d": None, "contango": None}
    if yf is None: return result
    try:
        h = get_yf_ticker("^VIX").history(period="5d")
        if not h.empty: result["vix"] = round(h["Close"].iloc[-1], 2)
    except Exception: pass
    try:
        h9 = get_yf_ticker("^VIX9D").history(period="5d")
        if not h9.empty: result["vix9d"] = round(h9["Close"].iloc[-1], 2)
    except Exception: pass
    if result["vix"] is not None and result["vix9d"] is not None:
        result["contango"] = result["vix"] > result["vix9d"]
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

    # DTE-aware delta target: 0DTE wants 0.35-0.45, longer-dated 0.25-0.35
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

def parse_trade_input(text):
    text_lower = text.lower().strip()
    result = {"bias": None, "price_ref": None, "raw": text}
    if "bull" in text_lower: result["bias"] = "bull"
    elif "bear" in text_lower: result["bias"] = "bear"
    m = re.search(r'@(\d+\.?\d*)', text)
    if m: result["price_ref"] = float(m.group(1))
    return result

def generate_recommendation(chain, spx_metrics, vix_data):
    if not chain or not spx_metrics:
        return None
    spot = spx_metrics["spot"]
    vwap = spx_metrics["vwap"]
    vix_val = vix_data.get("vix") or 20.0
    pcr = compute_pcr(chain)
    gex_profile = compute_gex_profile(chain, spot / 10)
    gamma_flip_spy = find_gamma_flip(gex_profile)
    gamma_flip = gamma_flip_spy * 10 if gamma_flip_spy else None
    max_pain_spy = compute_max_pain(chain)
    max_pain = max_pain_spy * 10 if max_pain_spy else None
    contango = vix_data.get("contango")

    # --- Time-of-day gating ---
    PST = pytz.timezone("US/Pacific")
    now_pst = datetime.now(PST)
    hour_et = now_pst.hour + 3   # PST → ET offset
    if hour_et >= 15:   # After 3 PM ET — no new 0DTE entries
        return {
            "recommendation": "NO TRADE — Too Late in Session",
            "rationale": "0DTE entries after 3 PM ET carry excessive theta risk.",
            "stats": "", "action": "", "conditions_met": [], "conditions_failed": [],
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    # --- Expected Move check ---
    # VIX → 1-day expected move for SPX
    daily_em = spot * (vix_val / 100) / (252 ** 0.5)
    
    # --- Weighted Signal Scoring (max ±10) ---
    score = 0.0
    met, failed = [], []

    # VWAP: highest weight — institutional anchor
    vwap_dev = (spot - vwap) / vwap * 100
    if vwap_dev > 0.1:
        score += 3.0; met.append(f"Spot {vwap_dev:+.2f}% above VWAP")
    elif vwap_dev < -0.1:
        score -= 3.0; failed.append(f"Spot {vwap_dev:+.2f}% below VWAP")
    # else: flat VWAP — neutral, no score

    # Gamma Flip: second highest
    if gamma_flip:
        gf_dev = (spot - gamma_flip) / spot * 100
        if spot > gamma_flip:
            score += 2.5; met.append(f"Spot {gf_dev:+.1f}% above Gamma Flip ({int(gamma_flip)})")
        else:
            score -= 2.5; failed.append(f"Spot {gf_dev:+.1f}% below Gamma Flip ({int(gamma_flip)})")

    # PCR
    if pcr is not None:
        if pcr < 0.7:
            score += 2.0; met.append(f"PCR {pcr:.2f} — Strong Bullish Skew")
        elif pcr < 0.85:
            score += 1.0; met.append(f"PCR {pcr:.2f} — Mild Bullish Skew")
        elif pcr > 1.2:
            score -= 2.0; failed.append(f"PCR {pcr:.2f} — Strong Bearish Skew")
        elif pcr > 1.0:
            score -= 1.0; failed.append(f"PCR {pcr:.2f} — Mild Bearish Skew")

    # VIX term structure
    if contango is not None:
        if contango:
            score += 1.5; met.append("VIX Contango — Regime Stable")
        else:
            score -= 1.5; failed.append("VIX Backwardation — Regime Unstable")

    # Max Pain gravity: if spot far from max pain, fade the move
    if max_pain:
        mp_dist = spot - max_pain
        mp_pct = mp_dist / spot * 100
        if abs(mp_pct) > 0.5:
            # Spot will be pulled back toward max pain at expiry — fade
            if mp_pct > 0:
                score -= 1.0
                failed.append(f"Max Pain gravity {int(max_pain)} ({mp_pct:+.1f}% below spot)")
            else:
                score += 1.0
                met.append(f"Max Pain gravity {int(max_pain)} ({mp_pct:+.1f}% above spot)")

    # --- Decision thresholds ---
    BULL_THRESHOLD = 4.0   # need strong confluence to trade
    BEAR_THRESHOLD = -4.0

    if score >= BULL_THRESHOLD:
        bias, direction = "bull", "bullish"
    elif score <= BEAR_THRESHOLD:
        bias, direction = "bear", "bearish"
        met, failed = failed, met
    else:
        return {
            "recommendation": f"NO TRADE — Weak Confluence (score: {score:+.1f})",
            "rationale": f"Weighted score {score:+.1f} is below ±{BULL_THRESHOLD} threshold. Wait for cleaner setup.",
            "stats": f"Expected 1-day move: ±${daily_em:.1f} pts",
            "action": "Stand aside. Monitor for VIX expansion or VWAP reclaim.",
            "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    target = find_target_strike(chain, bias, dte=0)
    if not target:
        return {
            "recommendation": f"NO TRADE — No Suitable Option",
            "rationale": f"No viable {bias} options passed liquidity filters.",
            "stats": "", "action": "", "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    strike_spx = round(target["strike"] * 10, 0)
    mid = target.get("mid", 0)

    # --- Expected move sanity: don't buy if strike is beyond 1 daily EM ---
    dist_to_strike = abs(strike_spx - spot)
    if dist_to_strike > daily_em * 1.5:
        return {
            "recommendation": f"NO TRADE — Strike Too Far OTM",
            "rationale": f"Strike {int(strike_spx)} is ${dist_to_strike:.0f} from spot, "
                         f"exceeding 1.5× daily EM (${daily_em:.0f}). Low P(ITM).",
            "stats": f"Daily EM: ±${daily_em:.1f} | Strike dist: ${dist_to_strike:.0f}",
            "action": "Choose a closer strike or wait for spot to move toward target.",
            "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    opt_label = "CALL" if target["type"] == "call" else "PUT"
    bd = target.get("_breakdown", {})
    delta_pct = round(abs(target["delta"]) * 100)

    # --- Find hedge wall ---
    hedge_wall = None
    if gex_profile:
        for gk, gv in sorted(gex_profile.items(), key=lambda x: abs(x[1]), reverse=True):
            gk_spx = gk * 10
            if (bias == "bull" and gk_spx > strike_spx) or (bias == "bear" and gk_spx < strike_spx):
                hedge_wall = gk_spx
                break

    abs_score = abs(score)
    if abs_score >= 7.5:   confidence = "HIGH"
    elif abs_score >= 5.0: confidence = "MODERATE"
    else:                  confidence = "LOW"

    target_pts = abs(int(hedge_wall - strike_spx)) if hedge_wall else max(int(daily_em * 0.5), 5)
    stop_pts = max(int(mid * 0.5 / 10), 5)   # Stop at 50% of premium paid, in SPX pts

    target_desc = f"Target {int(hedge_wall)} GEX Wall (+{target_pts}pts)" if hedge_wall else f"Target +{target_pts}pts (0.5× daily EM)"
    stop_desc = f"Stop at 50% premium loss (−${mid/2:.2f} on the option)"

    stats_text = (
        f"Weighted Score: {score:+.1f}/±10 | Daily EM: ±${daily_em:.1f}\n"
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


# ════════════════════════════════════════════════════════════════════
# CRYPTO WHALE FLOWS & ON-CHAIN DATA
# ════════════════════════════════════════════════════════════════════

_COINBASE_MAP = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}

@st.cache_data(ttl=120)
def get_whale_trades(symbol="BTCUSDT", min_usd=500_000):
    product = _COINBASE_MAP.get(symbol, "BTC-USD")
    try:
        trades = _fetch_robust_json(f"https://api.exchange.coinbase.com/products/{product}/trades", params={"limit": 1000}, timeout=10)
        result = []
        for t in trades:
            price, qty = float(t.get("price", "0")), float(t.get("size", "0"))
            usd = price * qty
            if usd < min_usd: continue
            side = "BUY" if t.get("side", "") == "buy" else "SELL"
            iso = t.get("time", "")
            try: time_str = datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M:%S")
            except: time_str = str(iso)[:8]
            result.append({"time": time_str, "side": side, "qty": round(qty, 4), "usd": round(usd, 2), "price": round(price, 2)})
        result.sort(key=lambda x: x["usd"], reverse=True)
        return result[:25]
    except:
        return []

@st.cache_data(ttl=600)
def get_exchange_netflow():
    import time
    try:
        time.sleep(1)
        data = _fetch_robust_json("https://api.coingecko.com/api/v3/exchanges", params={"per_page": 10, "page": 1}, timeout=10)
        result = [{"name": ex.get("name", ""), "btc_vol_24h": float(ex.get("trade_volume_24h_btc", 0) or 0), "trust_score": int(ex.get("trust_score", 0) or 0)} for ex in data]
        result.sort(key=lambda x: x["btc_vol_24h"], reverse=True)
        return result
    except:
        return []

_FUNDING_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT", "ADAUSDT"]

@st.cache_data(ttl=120)
def get_funding_rates():
    try:
        data = _fetch_robust_json("https://api.bybit.com/v5/market/tickers", params={"category": "linear"}, timeout=10)
        tickers = data.get("result", {}).get("list", [])
        lookup = {t["symbol"]: t for t in tickers if t.get("symbol") in _FUNDING_SYMBOLS}
        result = []
        for sym in _FUNDING_SYMBOLS:
            t = lookup.get(sym)
            if not t: continue
            rate, mark = float(t.get("fundingRate", "0") or "0"), float(t.get("markPrice", "0") or "0")
            rate_pct = round(rate * 100, 4)
            result.append({"symbol": sym.replace("USDT", ""), "rate_pct": rate_pct, "rate_ann": round(rate_pct * 3 * 365, 2), "mark_price": round(mark, 2)})
        result.sort(key=lambda x: abs(x["rate_pct"]), reverse=True)
        return result
    except:
        return []

_OI_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT"]

@st.cache_data(ttl=120)
def get_open_interest():
    try:
        data = _fetch_robust_json("https://api.bybit.com/v5/market/tickers", params={"category": "linear"}, timeout=10)
        tickers = data.get("result", {}).get("list", [])
        marks = {t["symbol"]: float(t.get("markPrice", "0") or "0") for t in tickers}
        result = []
        for sym in _OI_SYMBOLS:
            try:
                oi_data = _fetch_robust_json("https://api.bybit.com/v5/market/open-interest", params={"category": "linear", "symbol": sym, "intervalTime": "5min", "limit": 1}, timeout=8)
                items = oi_data.get("result", {}).get("list", [])
                if not items: continue
                oi_coins = float(items[0].get("openInterest", "0") or "0")
                result.append({"symbol": sym.replace("USDT", ""), "oi_coins": round(oi_coins, 4), "oi_usd": round(oi_coins * marks.get(sym, 0), 2)})
            except:
                continue
        result.sort(key=lambda x: x["oi_usd"], reverse=True)
        return result
    except:
        return []

_LIQ_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]

@st.cache_data(ttl=180)
def get_liquidations():
    result = {}
    for coin in _LIQ_COINS:
        try:
            r = requests.get("https://open-api.coinglass.com/public/v2/liquidation_chart", params={"ex": "Bybit", "pair": f"{coin}USDT", "interval": "0"}, headers={"Accept": "application/json"}, timeout=10)
            if r.status_code in (403, 429):
                result[coin] = {"long_liq": 0, "short_liq": 0, "total": 0}; continue
            data = r.json().get("data", {})
            long_liq, short_liq = float(data.get("longLiquidationUsd", 0) or 0), float(data.get("shortLiquidationUsd", 0) or 0)
            result[coin] = {"long_liq": round(long_liq, 2), "short_liq": round(short_liq, 2), "total": round(long_liq + short_liq, 2)}
        except:
            result[coin] = {"long_liq": 0, "short_liq": 0, "total": 0}
    return result

# ════════════════════════════════════════════════════════════════════
# MACRO OVERVIEW & CALENDAR
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_macro_overview(fred_key):
    if not fred_key: return None
    signals = {}

    try:
        df_cpi = fred_series("CPIAUCSL", fred_key, 24)
        if df_cpi is not None and len(df_cpi) >= 13:
            cpi_yoy = round((df_cpi["value"].iloc[-1] / df_cpi["value"].iloc[-13] - 1) * 100, 2)
            if cpi_yoy < 2.5: cpi_score, cpi_label, cpi_color = 2, f"Cooling ({cpi_yoy:.1f}%)", "#00CC44"
            elif cpi_yoy < 3.5: cpi_score, cpi_label, cpi_color = 1, f"Elevated ({cpi_yoy:.1f}%)", "#FF8C00"
            elif cpi_yoy < 5.0: cpi_score, cpi_label, cpi_color = -1, f"High ({cpi_yoy:.1f}%)", "#FF4444"
            else: cpi_score, cpi_label, cpi_color = -2, f"Very High ({cpi_yoy:.1f}%)", "#FF0000"
            signals["CPI Inflation"] = {"score": cpi_score, "label": cpi_label, "color": cpi_color, "val": cpi_yoy}
    except Exception: pass

    try:
        df_pce = fred_series("PCEPILFE", fred_key, 24)
        if df_pce is not None and len(df_pce) >= 13:
            pce_yoy = round((df_pce["value"].iloc[-1] / df_pce["value"].iloc[-13] - 1) * 100, 2)
            if pce_yoy < 2.5: pce_score, pce_label, pce_color = 2, f"Near Target ({pce_yoy:.1f}%)", "#00CC44"
            elif pce_yoy < 3.0: pce_score, pce_label, pce_color = 1, f"Slightly Elevated ({pce_yoy:.1f}%)", "#FF8C00"
            else: pce_score, pce_label, pce_color = -1, f"Above Target ({pce_yoy:.1f}%)", "#FF4444"
            signals["Core PCE"] = {"score": pce_score, "label": pce_label, "color": pce_color, "val": pce_yoy}
    except Exception: pass

    try:
        df_unemp = fred_series("UNRATE", fred_key, 6)
        if df_unemp is not None and not df_unemp.empty:
            urate = df_unemp["value"].iloc[-1]
            trend = "↑" if urate > (df_unemp["value"].iloc[-2] if len(df_unemp) > 1 else urate) else "↓"
            if urate < 4.0: u_score, u_label, u_color = 2, f"Full Employment ({urate:.1f}% {trend})", "#00CC44"
            elif urate < 4.5: u_score, u_label, u_color = 1, f"Near Full Emp. ({urate:.1f}% {trend})", "#FF8C00"
            elif urate < 5.5: u_score, u_label, u_color = -1, f"Rising ({urate:.1f}% {trend})", "#FF4444"
            else: u_score, u_label, u_color = -2, f"High Unemployment ({urate:.1f}% {trend})", "#FF0000"
            signals["Unemployment"] = {"score": u_score, "label": u_label, "color": u_color, "val": urate}
    except Exception: pass

    try:
        df_2y, df_10y = fred_series("DGS2", fred_key, 3), fred_series("DGS10", fred_key, 3)
        if df_2y is not None and df_10y is not None and not df_2y.empty and not df_10y.empty:
            spread = round(df_10y["value"].iloc[-1] - df_2y["value"].iloc[-1], 2)
            if spread > 0.5: yc_score, yc_label, yc_color = 2, f"Steep (+{spread:.2f}% — Growth)", "#00CC44"
            elif spread > 0: yc_score, yc_label, yc_color = 1, f"Flat (+{spread:.2f}%)", "#FF8C00"
            elif spread > -0.5: yc_score, yc_label, yc_color = -1, f"Inverted ({spread:.2f}%)", "#FF4444"
            else: yc_score, yc_label, yc_color = -2, f"Deep Inversion ({spread:.2f}%)", "#FF0000"
            signals["Yield Curve (10-2Y)"] = {"score": yc_score, "label": yc_label, "color": yc_color, "val": spread}
    except Exception: pass

    try:
        df_ff = fred_series("FEDFUNDS", fred_key, 6)
        if df_ff is not None and not df_ff.empty:
            ffr = df_ff["value"].iloc[-1]
            prev_ffr = df_ff["value"].iloc[-2] if len(df_ff) > 1 else ffr
            ff_trend = "cutting" if ffr < prev_ffr else ("hiking" if ffr > prev_ffr else "hold")
            if ff_trend == "cutting" and ffr < 4.0: ff_score, ff_label, ff_color = 2, f"Easing ({ffr:.2f}% — {ff_trend.upper()})", "#00CC44"
            elif ff_trend == "cutting": ff_score, ff_label, ff_color = 1, f"Beginning Cuts ({ffr:.2f}%)", "#FF8C00"
            elif ff_trend == "hiking": ff_score, ff_label, ff_color = -1, f"Tightening ({ffr:.2f}% — {ff_trend.upper()})", "#FF4444"
            elif ffr > 5.0: ff_score, ff_label, ff_color = -1, f"Restrictive ({ffr:.2f}% — HOLD)", "#FF4444"
            else: ff_score, ff_label, ff_color = 1, f"Neutral ({ffr:.2f}% — HOLD)", "#FF8C00"
            signals["Fed Funds Rate"] = {"score": ff_score, "label": ff_label, "color": ff_color, "val": ffr}
    except Exception: pass

    try:
        df_hy = fred_series("BAMLH0A0HYM2", fred_key, 6)
        if df_hy is not None and not df_hy.empty:
            hy = df_hy["value"].iloc[-1]
            hy_trend = "↑" if hy > (df_hy["value"].iloc[-2] if len(df_hy) > 1 else hy) else "↓"
            if hy < 3.5: hy_score, hy_label, hy_color = 2, f"Tight ({hy:.2f}% {hy_trend} — Risk-On)", "#00CC44"
            elif hy < 4.5: hy_score, hy_label, hy_color = 1, f"Normal ({hy:.2f}% {hy_trend})", "#FF8C00"
            elif hy < 6.0: hy_score, hy_label, hy_color = -1, f"Wide ({hy:.2f}% {hy_trend} — Stress)", "#FF4444"
            else: hy_score, hy_label, hy_color = -2, f"Very Wide ({hy:.2f}% {hy_trend} — Crisis)", "#FF0000"
            signals["HY Credit Spread"] = {"score": hy_score, "label": hy_label, "color": hy_color, "val": hy}
    except Exception: pass

    try:
        df_m2 = fred_series("M2SL", fred_key, 18)
        if df_m2 is not None and len(df_m2) >= 13:
            m2_yoy = round((df_m2["value"].iloc[-1] / df_m2["value"].iloc[-13] - 1) * 100, 2)
            if m2_yoy > 5: m2_score, m2_label, m2_color = -1, f"Expanding Rapidly ({m2_yoy:+.1f}% YoY)", "#FF4444"
            elif m2_yoy > 0: m2_score, m2_label, m2_color = 1, f"Modest Growth ({m2_yoy:+.1f}% YoY)", "#FF8C00"
            else: m2_score, m2_label, m2_color = 2, f"Contracting ({m2_yoy:+.1f}% YoY)", "#00CC44"
            signals["M2 Money Supply"] = {"score": m2_score, "label": m2_label, "color": m2_color, "val": m2_yoy}
    except Exception: pass

    try:
        df_gdp = fred_series("GDPC1", fred_key, 12)
        if df_gdp is not None and len(df_gdp) >= 5:
            latest_gdp, prev_gdp, year_ago_gdp = df_gdp["value"].iloc[-1], df_gdp["value"].iloc[-2], df_gdp["value"].iloc[-5]
            gdp_yoy, gdp_q = round((latest_gdp / year_ago_gdp - 1) * 100, 2), round((latest_gdp / prev_gdp - 1) * 4 * 100, 2)
            if gdp_yoy >= 3.0: gdp_score, gdp_label, gdp_color = 2, f"Strong ({gdp_yoy:.1f}% YoY, {gdp_q:+.1f}% ann.)", "#00CC44"
            elif gdp_yoy >= 2.0: gdp_score, gdp_label, gdp_color = 1, f"Moderate ({gdp_yoy:.1f}% YoY)", "#FF8C00"
            elif gdp_yoy >= 0.5: gdp_score, gdp_label, gdp_color = -1, f"Slowing ({gdp_yoy:.1f}% YoY)", "#FF4444"
            else: gdp_score, gdp_label, gdp_color = -2, f"Contraction ({gdp_yoy:.1f}% YoY)", "#FF0000"
            signals["GDP Growth"] = {"score": gdp_score, "label": gdp_label, "color": gdp_color, "val": gdp_yoy}
    except Exception: pass

    total_score = sum(s["score"] for s in signals.values())
    max_score = len(signals) * 2
    pct = (total_score / max_score * 100) if max_score else 0

    if pct >= 50:   env_label, env_color, env_desc = "EXPANSIONARY 🟢", "#00CC44", "Macro conditions are broadly supportive. Risk-on bias."
    elif pct >= 10: env_label, env_color, env_desc = "MIXED / NEUTRAL 🟡", "#FF8C00", "Macro signals are mixed. Selective positioning warranted."
    elif pct >= -30: env_label, env_color, env_desc = "CAUTIONARY ⚠️", "#FFCC00", "More headwinds than tailwinds. Elevated inflation or tightening financial conditions."
    else:            env_label, env_color, env_desc = "CONTRACTIONARY 🔴", "#FF4444", "Multiple macro red flags. Elevated recession risk."

    return {"signals": signals, "total_score": total_score, "max_score": max_score, "pct": pct, "env_label": env_label, "env_color": env_color, "env_desc": env_desc}

@st.cache_data(ttl=3600)
def get_macro_calendar(fred_key=None):
    from datetime import date as _date, timedelta as _td
    import calendar as _cal
    today = _date.today()
    horizon = today + _td(days=45)
    results = []

    try:
        params = {"from": today.strftime("%Y-%m-%d"), "to": horizon.strftime("%Y-%m-%d")}
        fk = st.secrets.get("FINNHUB_API_KEY") or st.secrets.get("finnhub_api_key") or ""
        if fk: params["token"] = str(fk).strip()
        data = _fetch_robust_json("https://finnhub.io/api/v1/calendar/economic", params=params, timeout=12)
        events = data.get("economicCalendar", [])
        HIGH_KW = ["cpi","fomc","fed","nonfarm","non-farm","payroll","gdp","pce","employment situation"]
        MED_KW  = ["ppi","retail sales","ism","pmi","housing starts","durable goods","jolts","adp","jobless","consumer confidence","industrial production","trade balance"]
        for ev in events:
            name = (ev.get("event") or "").strip()
            if not name: continue
            nl, impact = name.lower(), (ev.get("impact") or "").upper()
            is_high = impact == "HIGH" or any(kw in nl for kw in HIGH_KW)
            is_med  = any(kw in nl for kw in MED_KW)
            if not (is_high or is_med or impact in ("HIGH","MEDIUM")): continue
            try: ev_date = _date.fromisoformat((ev.get("time") or "")[:10])
            except Exception: continue
            if not (today <= ev_date <= horizon): continue
            results.append({
                "date": ev_date, "name": name, "importance": "HIGH" if is_high else "MEDIUM", "time": "",
                "actual": str(ev.get("actual","")) if ev.get("actual") is not None else "",
                "forecast": str(ev.get("estimate","")) if ev.get("estimate") is not None else "",
                "previous": str(ev.get("prev","")) if ev.get("prev") is not None else "",
                "source": "finnhub",
            })
        if results:
            results.sort(key=lambda x: x["date"])
            return results[:35]
    except Exception: pass

    if fred_key:
        try:
            data = _fetch_robust_json("https://api.stlouisfed.org/fred/releases/dates", params={"api_key": fred_key, "file_type": "json", "realtime_start": today.strftime("%Y-%m-%d"), "realtime_end": horizon.strftime("%Y-%m-%d"), "limit": 150, "sort_order": "asc", "include_release_dates_with_no_data": "false"}, timeout=12)
            FRED_NAMES = {"10":("CPI","HIGH"), "21":("Jobs Report","HIGH"), "46":("PCE","HIGH"), "20":("GDP","HIGH"), "9":("FOMC","HIGH"), "15":("PPI","MEDIUM"), "14":("Retail Sales","MEDIUM"), "17":("Industrial Production","MEDIUM"), "19":("Housing Starts","MEDIUM"), "11":("Consumer Confidence","MEDIUM"), "22":("Initial Jobless Claims","MEDIUM"), "175":("ISM Mfg PMI","MEDIUM"), "184":("ISM Services PMI","MEDIUM"), "13":("Durable Goods","MEDIUM"), "69":("ADP Employment","MEDIUM"), "23":("JOLTS","MEDIUM"), "55":("Trade Balance","MEDIUM")}
            for rel in data.get("release_dates", []):
                rid = str(rel.get("release_id",""))
                if rid not in FRED_NAMES: continue
                name, imp = FRED_NAMES[rid]
                for d in rel.get("release_dates",[]):
                    try:
                        rel_date = _date.fromisoformat(d)
                        if today <= rel_date <= horizon: results.append({"date":rel_date,"name":name,"importance":imp, "time":"","actual":"","forecast":"","previous":"","source":"fred"})
                    except: continue
            if results:
                results.sort(key=lambda x: x["date"])
                return results[:35]
        except Exception: pass

    def _nth_weekday(year, month, n, weekday):
        count = 0
        for day in range(1, _cal.monthrange(year, month)[1] + 1):
            if _date(year, month, day).weekday() == weekday:
                count += 1
                if count == n: return _date(year, month, day)
        return None

    def _last_weekday(year, month, weekday):
        last = None
        for day in range(1, _cal.monthrange(year, month)[1] + 1):
            if _date(year, month, day).weekday() == weekday: last = _date(year, month, day)
        return last

    static_events = []
    for delta_m in range(0, 3):
        m = ((today.month - 1 + delta_m) % 12) + 1
        y = today.year + ((today.month - 1 + delta_m) // 12)
        d = _nth_weekday(y, m, 1, 4)
        if d: static_events.append(("Employment Situation (Jobs Report)", d, "HIGH"))
        d = _nth_weekday(y, m, 2, 2)
        if d: static_events.append(("Consumer Price Index (CPI)", d + _td(days=1), "HIGH"))
        d = _nth_weekday(y, m, 2, 3)
        if d: static_events.append(("Producer Price Index (PPI)", d, "MEDIUM"))
        d = _nth_weekday(y, m, 2, 4)
        if d: static_events.append(("Retail Sales", d + _td(days=1), "MEDIUM"))
        d = _nth_weekday(y, m, 1, 3)
        if d: static_events.append(("Initial Jobless Claims", d, "MEDIUM"))
        d = _last_weekday(y, m, 4)
        if d: static_events.append(("Personal Income & PCE", d, "HIGH"))
        d = _date(y, m, 1)
        while d.weekday() >= 5: d += _td(days=1)
        static_events.append(("ISM Manufacturing PMI", d, "MEDIUM"))
        d = _date(y, m, 3)
        while d.weekday() >= 5: d += _td(days=1)
        static_events.append(("ISM Services PMI", d, "MEDIUM"))
        d = _last_weekday(y, m, 1)
        if d: static_events.append(("Consumer Confidence (CB)", d, "MEDIUM"))
        d = _last_weekday(y, m, 3)
        if d: static_events.append(("GDP (Advance Estimate)", d, "HIGH"))

    FOMC_APPROX = [_date(2025,3,19), _date(2025,5,7), _date(2025,6,18), _date(2025,7,30), _date(2025,9,17), _date(2025,10,29), _date(2025,12,10), _date(2026,1,28), _date(2026,3,18), _date(2026,4,29), _date(2026,6,17), _date(2026,7,29), _date(2026,9,16), _date(2026,10,28), _date(2026,12,16)]
    for fd in FOMC_APPROX:
        if today <= fd <= horizon: static_events.append(("FOMC Meeting (Fed Rate Decision)", fd, "HIGH"))

    seen = set()
    for name, date, imp in static_events:
        key = (date, name)
        if key in seen or not (today <= date <= horizon): continue
        seen.add(key)
        results.append({"date":date,"name":name,"importance":imp, "time":"","actual":"","forecast":"","previous":"","source":"est."})

    results.sort(key=lambda x: x["date"])
    return results[:35]

@st.cache_data(ttl=3600)
def get_ticker_exchange(ticker):
    EXCHANGE_MAP = {
        "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE",
        "ASE": "AMEX", "AMEX": "AMEX", "PCX": "AMEX", "PNK": "OTC", "OTC": "OTC",
        "BTT": "NYSE", "NYSEArca": "AMEX", "NasdaqCM": "NASDAQ", "NasdaqGS": "NASDAQ", "NasdaqGM": "NASDAQ", "NYSE": "NYSE",
    }
    try:
        tk = get_yf_ticker(ticker)
        info = tk.info if tk else {}
        exch = info.get("exchange", "") or info.get("fullExchangeName", "")
        tv_prefix = EXCHANGE_MAP.get(exch, None)
        if tv_prefix: return f"{tv_prefix}:{ticker}"
    except Exception: pass
    for prefix in ["NASDAQ", "NYSE", "AMEX"]: return f"{prefix}:{ticker}"
    return f"NASDAQ:{ticker}"


@st.cache_data(ttl=1800)
def get_full_financials(ticker):
    if yf is None: return {}
    try:
        t = get_yf_ticker(ticker)
        if t is None: return {}
        income, cashflow, balance = t.quarterly_financials, t.quarterly_cashflow, t.quarterly_balance_sheet
        if income is None or income.empty: return {}

        quarters = list(income.columns[:4])
        results = {}

        for q in quarters:
            q_str = str(q)[:10]
            row = {}

            def _get(df, *keys):
                for k in keys:
                    if df is not None and not df.empty and k in df.index and q in df.columns:
                        v = df.loc[k, q]
                        if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return float(v)
                return None

            row["revenue"]    = _get(income, "Total Revenue")
            row["gross_profit"]= _get(income, "Gross Profit")
            row["op_income"]  = _get(income, "Operating Income", "EBIT")
            row["net_income"] = _get(income, "Net Income")
            row["ebitda"]     = _get(income, "EBITDA", "Normalized EBITDA")
            row["eps"]        = _get(income, "Diluted EPS", "Basic EPS")
            row["int_expense"]= _get(income, "Interest Expense")
            row["free_cashflow"] = _get(cashflow, "Free Cash Flow")
            row["op_cashflow"]   = _get(cashflow, "Operating Cash Flow")
            row["capex"]         = _get(cashflow, "Capital Expenditure")
            row["total_debt"]    = _get(balance, "Total Debt", "Long Term Debt And Capital Lease Obligation")
            row["cash"]          = _get(balance, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")

            if row["revenue"] and row["revenue"] > 0:
                if row["gross_profit"] is not None: row["gross_margin"] = row["gross_profit"] / row["revenue"] * 100
                if row["op_income"] is not None: row["op_margin"] = row["op_income"] / row["revenue"] * 100
                if row["net_income"] is not None: row["net_margin"] = row["net_income"] / row["revenue"] * 100

            results[q_str] = row
        return results
    except Exception:
        return {}

@st.cache_data(ttl=1800)
def get_earnings_matrix(ticker):
    """Build Bloomberg-style Earnings Matrix data for a ticker.

    Pulls from multiple yfinance sources for maximum data coverage:
      1) t.earnings_dates  — reported EPS actual + estimate for 12+ quarters
      2) t.quarterly_financials — Diluted EPS from income statement
      3) t.earnings  — annual/quarterly dicts (legacy API, older history)

    Returns dict with:
        - quarterly: {year: {q_label: eps_value}}
        - estimates: {year: {q_label: eps_estimate}}
        - surprise_pct: {year: {q_label: surprise_%}}
        - beats: {year: {q_label: True/False/None}}
        - revenue_q: {year: {q_label: revenue_value}}
        - annual: {year: total_eps}
        - annual_revenue: {year: total_revenue}
        - yoy_growth: {year: {q_label: pct_growth}}
        - annual_growth: {year: pct_growth}
        - rev_growth: {year: {q_label: pct_growth}}
        - annual_rev_growth: {year: pct_growth}
        - valuations: {metric: {period: value}}
        - fiscal_end_month: int (1-12)
        - currency: str
        - years: sorted list of years
        - q_labels: ordered list of quarter labels
        - streak: int (consecutive beats, negative = misses)
        - beat_rate: float (% of quarters that beat)
    """
    if yf is None:
        return None
    try:
        t = get_yf_ticker(ticker)
        if t is None:
            return None
        info = t.info or {}

        # ── Determine fiscal year end month ──
        fiscal_end_month = info.get("fiscalYearEnd") or info.get("lastFiscalYearEnd")
        if isinstance(fiscal_end_month, str):
            _month_map = {"january": 1, "february": 2, "march": 3, "april": 4,
                          "may": 5, "june": 6, "july": 7, "august": 8,
                          "september": 9, "october": 10, "november": 11, "december": 12}
            fiscal_end_month = _month_map.get(fiscal_end_month.lower(), 12)
        elif not isinstance(fiscal_end_month, int):
            fiscal_end_month = 12

        # Map each fiscal quarter-end month → Q label
        import calendar
        _q_month_labels = {}
        for qi in range(4):
            m = ((fiscal_end_month - 3 * (3 - qi)) % 12) or 12
            _q_month_labels[m] = f"Q{qi+1} {calendar.month_abbr[m]}"
        q_labels = [f"Q{qi+1} {calendar.month_abbr[((fiscal_end_month - 3*(3-qi)) % 12) or 12]}" for qi in range(4)]

        def _month_to_qlabel(month):
            """Map a calendar month to the nearest fiscal quarter label."""
            if month in _q_month_labels:
                return _q_month_labels[month]
            best_m = min(_q_month_labels.keys(), key=lambda m: min(abs(m - month), 12 - abs(m - month)))
            return _q_month_labels[best_m]

        def _fiscal_year(month, year):
            """Determine fiscal year from calendar month/year."""
            return year if month <= fiscal_end_month else year + 1

        quarterly = {}   # {fy: {q_label: eps_actual}}
        estimates = {}   # {fy: {q_label: eps_estimate}}
        surprise_pct = {}  # {fy: {q_label: surprise_%}}
        beats = {}       # {fy: {q_label: True/False/None}}
        revenue_q = {}   # {fy: {q_label: revenue}}

        # ────────────────────────────────────────────────
        # SOURCE 1: earnings_dates (best for actual + estimate + surprise)
        # ────────────────────────────────────────────────
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                for idx, row in ed.iterrows():
                    dt = pd.to_datetime(idx)
                    month, year = dt.month, dt.year
                    ql = _month_to_qlabel(month)
                    fy = _fiscal_year(month, year)

                    # Reported EPS
                    actual = row.get("Reported EPS")
                    if actual is not None and not (isinstance(actual, float) and math.isnan(actual)):
                        actual = round(float(actual), 2)
                        if fy not in quarterly:
                            quarterly[fy] = {}
                        quarterly[fy][ql] = actual

                    # EPS Estimate
                    est = row.get("EPS Estimate")
                    if est is not None and not (isinstance(est, float) and math.isnan(est)):
                        est = round(float(est), 2)
                        if fy not in estimates:
                            estimates[fy] = {}
                        estimates[fy][ql] = est

                    # Surprise %
                    surp = row.get("Surprise(%)")
                    if surp is not None and not (isinstance(surp, float) and math.isnan(surp)):
                        if fy not in surprise_pct:
                            surprise_pct[fy] = {}
                        surprise_pct[fy][ql] = round(float(surp), 1)

                    # Beat/miss
                    if actual is not None and est is not None:
                        if fy not in beats:
                            beats[fy] = {}
                        beats[fy][ql] = actual >= est
        except Exception:
            pass

        # ────────────────────────────────────────────────
        # SOURCE 2: quarterly_financials (fills EPS + revenue gaps)
        # ────────────────────────────────────────────────
        try:
            income = t.quarterly_financials
            if income is not None and not income.empty:
                for col in income.columns:
                    dt = pd.to_datetime(col)
                    month, year = dt.month, dt.year
                    ql = _month_to_qlabel(month)
                    fy = _fiscal_year(month, year)

                    # EPS — only if not already filled by earnings_dates
                    if fy not in quarterly or ql not in quarterly.get(fy, {}):
                        for key in ["Diluted EPS", "Basic EPS"]:
                            if key in income.index:
                                v = income.loc[key, col]
                                if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                                    if fy not in quarterly:
                                        quarterly[fy] = {}
                                    quarterly[fy][ql] = round(float(v), 2)
                                    break

                    # Revenue
                    for key in ["Total Revenue", "Revenue"]:
                        if key in income.index:
                            v = income.loc[key, col]
                            if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                                if fy not in revenue_q:
                                    revenue_q[fy] = {}
                                revenue_q[fy][ql] = float(v)
                                break
        except Exception:
            pass

        # ────────────────────────────────────────────────
        # SOURCE 3: t.earnings (legacy — fills older years)
        # ────────────────────────────────────────────────
        try:
            earnings_obj = t.earnings
            if isinstance(earnings_obj, dict):
                # quarterly earnings: list of {date, actual, estimate}
                for qe in earnings_obj.get("quarterly", []):
                    try:
                        dt = pd.to_datetime(qe.get("date"))
                        month, year = dt.month, dt.year
                        ql = _month_to_qlabel(month)
                        fy = _fiscal_year(month, year)
                        actual = qe.get("actual")
                        if actual is not None and not math.isnan(float(actual)):
                            if fy not in quarterly:
                                quarterly[fy] = {}
                            if ql not in quarterly[fy]:
                                quarterly[fy][ql] = round(float(actual), 2)
                        est = qe.get("estimate")
                        if est is not None and not math.isnan(float(est)):
                            if fy not in estimates:
                                estimates[fy] = {}
                            if ql not in estimates[fy]:
                                estimates[fy][ql] = round(float(est), 2)
                        if actual is not None and est is not None:
                            a_, e_ = float(actual), float(est)
                            if not math.isnan(a_) and not math.isnan(e_):
                                if fy not in beats:
                                    beats[fy] = {}
                                if ql not in beats[fy]:
                                    beats[fy][ql] = a_ >= e_
                                if fy not in surprise_pct:
                                    surprise_pct[fy] = {}
                                if ql not in surprise_pct[fy] and e_ != 0:
                                    surprise_pct[fy][ql] = round((a_ - e_) / abs(e_) * 100, 1)
                    except Exception:
                        continue
        except Exception:
            pass

        # Also try quarterly_earnings attribute (some yfinance versions)
        try:
            qe_df = t.quarterly_earnings
            if qe_df is not None and not qe_df.empty:
                for idx, row in qe_df.iterrows():
                    dt = pd.to_datetime(idx)
                    month, year = dt.month, dt.year
                    ql = _month_to_qlabel(month)
                    fy = _fiscal_year(month, year)
                    rev = row.get("Revenue")
                    if rev is not None and not (isinstance(rev, float) and math.isnan(rev)):
                        if fy not in revenue_q:
                            revenue_q[fy] = {}
                        if ql not in revenue_q[fy]:
                            revenue_q[fy][ql] = float(rev)
                    eps = row.get("Earnings")
                    if eps is not None and not (isinstance(eps, float) and math.isnan(eps)):
                        if fy not in quarterly:
                            quarterly[fy] = {}
                        if ql not in quarterly[fy]:
                            quarterly[fy][ql] = round(float(eps), 2)
        except Exception:
            pass

        if not quarterly:
            return None

        years = sorted(quarterly.keys())

        # ── Annual totals ──
        annual = {}
        annual_revenue = {}
        for yr in years:
            vals = [v for v in quarterly.get(yr, {}).values() if v is not None]
            if vals:
                annual[yr] = round(sum(vals), 2)
            rev_vals = [v for v in revenue_q.get(yr, {}).values() if v is not None]
            if rev_vals:
                annual_revenue[yr] = sum(rev_vals)

        # ── YoY growth (EPS) ──
        yoy_growth = {}
        annual_growth = {}
        for yr in years:
            yoy_growth[yr] = {}
            for ql in q_labels:
                cur = quarterly.get(yr, {}).get(ql)
                prev = quarterly.get(yr - 1, {}).get(ql)
                if cur is not None and prev is not None and prev != 0:
                    yoy_growth[yr][ql] = round((cur - prev) / abs(prev) * 100, 1)
            cur_ann = annual.get(yr)
            prev_ann = annual.get(yr - 1)
            if cur_ann is not None and prev_ann is not None and prev_ann != 0:
                annual_growth[yr] = round((cur_ann - prev_ann) / abs(prev_ann) * 100, 1)

        # ── Revenue YoY growth ──
        rev_growth = {}
        annual_rev_growth = {}
        for yr in years:
            rev_growth[yr] = {}
            for ql in q_labels:
                cur = revenue_q.get(yr, {}).get(ql)
                prev = revenue_q.get(yr - 1, {}).get(ql)
                if cur is not None and prev is not None and prev != 0:
                    rev_growth[yr][ql] = round((cur - prev) / abs(prev) * 100, 1)
            cur_rev = annual_revenue.get(yr)
            prev_rev = annual_revenue.get(yr - 1)
            if cur_rev is not None and prev_rev is not None and prev_rev != 0:
                annual_rev_growth[yr] = round((cur_rev - prev_rev) / abs(prev_rev) * 100, 1)

        # ── Beat/miss streak & rate ──
        beat_list = []
        for yr in sorted(quarterly.keys()):
            for ql in q_labels:
                b = beats.get(yr, {}).get(ql)
                if b is not None:
                    beat_list.append(b)
        streak = 0
        if beat_list:
            direction = beat_list[-1]
            for b in reversed(beat_list):
                if b == direction:
                    streak += 1 if direction else -1
                else:
                    break
            if not direction:
                streak = -abs(streak)
        beat_rate = round(sum(1 for b in beat_list if b) / len(beat_list) * 100, 0) if beat_list else 0

        # ── Compute estimate-based surprise where missing ──
        for yr in years:
            for ql in q_labels:
                act = quarterly.get(yr, {}).get(ql)
                est = estimates.get(yr, {}).get(ql)
                if act is not None and est is not None and est != 0:
                    if yr not in surprise_pct:
                        surprise_pct[yr] = {}
                    if ql not in surprise_pct[yr]:
                        surprise_pct[yr][ql] = round((act - est) / abs(est) * 100, 1)
                    if yr not in beats:
                        beats[yr] = {}
                    if ql not in beats[yr]:
                        beats[yr][ql] = act >= est

        # ── Valuation multiples ──
        valuations = {}
        price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"), 0)
        if price > 0:
            trailing_pe = _safe_float(info.get("trailingPE"), 0)
            forward_pe = _safe_float(info.get("forwardPE"), 0)
            trailing_ps = _safe_float(info.get("priceToSalesTrailing12Months"), 0)
            pb = _safe_float(info.get("priceToBook"), 0)
            opcf = _safe_float(info.get("operatingCashflow"), 0)
            shares = _safe_float(info.get("sharesOutstanding"), 0)
            pcf = round(price / (opcf / shares), 1) if opcf > 0 and shares > 0 else 0
            ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0)
            forward_eps = _safe_float(info.get("forwardEps"), 0)

            valuations = {
                "P/E": {
                    "Last 4Q": f"{trailing_pe:.1f}x" if trailing_pe > 0 else "—",
                    "Forward": f"{forward_pe:.1f}x" if forward_pe > 0 else "—",
                },
                "EV/EBITDA": {
                    "Last 4Q": f"{ev_ebitda:.1f}x" if ev_ebitda > 0 else "—",
                    "Forward": "—",
                },
                "P/S": {
                    "Last 4Q": f"{trailing_ps:.1f}x" if trailing_ps > 0 else "—",
                    "Forward": "—",
                },
                "P/B": {
                    "Last 4Q": f"{pb:.1f}x" if pb > 0 else "—",
                    "Forward": "—",
                },
                "P/CF": {
                    "Last 4Q": f"{pcf:.1f}x" if pcf > 0 else "—",
                    "Forward": "—",
                },
            }

        currency = info.get("currency", "USD")

        # ── Analyst Price Targets (Top 5 tracked) ──
        analyst_targets = []
        try:
            ud = t.upgrades_downgrades
            if ud is not None and not ud.empty:
                ud = ud.reset_index().sort_values("GradeDate", ascending=False)
                ud = ud.drop_duplicates(subset=["Firm"])
                ud = ud[ud["currentPriceTarget"].notna() & (ud["currentPriceTarget"] > 0)]
                
                track_record_firms = ["B of A Securities", "Bank of America", "Needham", "TD Cowen", "Cowen & Co.", "RBC Capital", "Oppenheimer"]
                best_targets = []
                other_targets = []
                
                for _, row in ud.iterrows():
                    firm = row["Firm"]
                    pt = float(row["currentPriceTarget"])
                    action = row.get("ToGrade", "") or row.get("Action", "")
                    if pd.isna(action): action = ""
                    else: action = str(action)
                    
                    obj = {"firm": firm, "target": pt, "action": action[:20]}
                    if firm in track_record_firms:
                        best_targets.append(obj)
                    else:
                        other_targets.append(obj)
                        
                analyst_targets = (best_targets + other_targets)[:5]
        except Exception:
            pass

        return {
            "quarterly": quarterly,
            "estimates": estimates,
            "surprise_pct": surprise_pct,
            "beats": beats,
            "revenue_q": revenue_q,
            "annual": annual,
            "annual_revenue": annual_revenue,
            "yoy_growth": yoy_growth,
            "annual_growth": annual_growth,
            "rev_growth": rev_growth,
            "annual_rev_growth": annual_rev_growth,
            "valuations": valuations,
            "fiscal_end_month": fiscal_end_month,
            "currency": currency,
            "years": years,
            "q_labels": q_labels,
            "price": price,
            "company": info.get("shortName", ticker),
            "streak": streak,
            "beat_rate": beat_rate,
            "forward_eps": _safe_float(info.get("forwardEps"), 0),
            "trailing_eps": _safe_float(info.get("trailingEps"), 0),
            "market_cap": _safe_float(info.get("marketCap"), 0),
            "analyst_targets": analyst_targets,
        }
    except Exception as e:
        logger.error({"error": str(e)}, "Earnings Matrix Error")
        return None


@st.cache_data(ttl=600)
def get_stock_news(ticker, finnhub_key=None, newsapi_key=None):
    results = []
    if finnhub_key:
        try:
            from datetime import date as _date
            today = _date.today()
            from_dt = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            to_dt = today.strftime("%Y-%m-%d")
            articles = _fetch_robust_json("https://finnhub.io/api/v1/company-news", params={"symbol": ticker, "from": from_dt, "to": to_dt, "token": finnhub_key}, timeout=10)
            for art in articles[:8]:
                headline = art.get("headline", "")
                if not headline or not _is_english(headline): continue
                ts = art.get("datetime", 0)
                d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
                results.append({"title": headline[:110], "url": art.get("url", "#"), "source": art.get("source", "Finnhub"), "date": d})
            if results: return results
        except Exception: pass

    try:
        tk = get_yf_ticker(ticker)
        info = tk.info if tk else {}
        co_name = info.get("shortName", ticker).split()[0] if info else ticker
        query = f"{ticker} {co_name} stock"
        arts = gdelt_news(query, max_rec=8)
        for art in arts:
            title = art.get("title", "")
            if not title: continue
            sd = art.get("seendate", "")
            d = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
            results.append({"title": title[:110], "url": art.get("url", "#"), "source": art.get("domain", "GDELT"), "date": d})
        if results: return results
    except Exception: pass

    if newsapi_key:
        try:
            arts = newsapi_headlines(newsapi_key, query=f"{ticker} stock earnings")
            for art in arts[:8]:
                title = art.get("title", "")
                if not title or "[Removed]" in title: continue
                results.append({"title": title[:110], "url": art.get("url", "#"), "source": art.get("source", {}).get("name", "NewsAPI"), "date": art.get("publishedAt", "")[:10]})
        except Exception: pass

    return results


# ════════════════════════════════════════════════════════════════════
# POLYMARKET MISPRICING ALGORITHM
# ════════════════════════════════════════════════════════════════════

def _poly_liquidity_score(market):
    vol   = _safe_float(market.get("volume", 0))
    vol24 = _safe_float(market.get("volume24hr", 0))
    liq   = _safe_float(market.get("liquidity", 0))
    if vol > 1_000_000 and liq > 100_000:  return 1.0   
    if vol > 250_000  and liq > 30_000:    return 0.80
    if vol > 50_000   and liq > 10_000:    return 0.60
    if vol > 10_000   and liq > 2_000:     return 0.40
    if vol > 1_000:                         return 0.20
    return 0.05  

def _poly_crowd_accuracy_discount(liq_score):
    return 0.30 + 0.70 * (liq_score ** 0.6)

def score_poly_mispricing(markets, base_rate_fn=None):
    results = []
    for m in markets:
        try:
            title = m.get("question", m.get("title", ""))
            if not title: continue

            pp = _parse_poly_field(m.get("outcomePrices", []))
            if not pp or len(pp) < 2: continue

            raw_yes = _safe_float(pp[0])
            raw_no  = _safe_float(pp[1]) if len(pp) > 1 else (1 - raw_yes)

            if raw_yes <= 0 or raw_yes >= 1: continue
            if abs(raw_yes + raw_no - 1.0) > 0.15: continue

            liq_score   = _poly_liquidity_score(m)
            reliability = _poly_crowd_accuracy_discount(liq_score)
            adj_prob    = 0.5 + (raw_yes - 0.5) * reliability

            vol   = _safe_float(m.get("volume", 0))
            vol24 = _safe_float(m.get("volume24hr", 0))
            activity_ratio = min(vol24 / vol, 1.0) if vol > 0 else 0.0

            # --- EDGE: gap between raw crowd price and liquidity-adjusted fair value ---
            edge = abs(raw_yes - adj_prob)

            # Confidence: how much to trust this edge (high liq + active = trustworthy)
            confidence = liq_score * activity_ratio

            # Volume weight: normalize 24h volume on a log scale
            vol_weight = min(math.log1p(vol24) / math.log1p(1_000_000), 1.0) if vol24 > 0 else 0.0

            # Mispricing score: edge × (1 + confidence) × volume
            # Unlike old formula, deep-liq markets aren't suppressed
            mispricing_score = round(edge * (1.0 + confidence) * vol_weight, 5)

            # Spread for display
            spread_str = ""
            best_bid = _safe_float(m.get("bestBid", 0))
            best_ask = _safe_float(m.get("bestAsk", 0)) or _safe_float(m.get("bestOffer", 0))
            if best_bid > 0 and best_ask > 0:
                spread = best_ask - best_bid
                spread_str = f"{spread*100:.1f}¢"

            # --- ACTION SIGNALS (clear, no ambiguity) ---
            if liq_score < 0.40 and raw_yes > 0.70 and edge > 0.05:
                signal, signal_color = "BET NO", "#FF4444"       # crowd overpriced YES
            elif liq_score < 0.40 and raw_yes < 0.30 and edge > 0.05:
                signal, signal_color = "BET YES", "#00CC44"      # crowd overpriced NO
            elif liq_score >= 0.70 and raw_yes > 0.65:
                signal, signal_color = "CONFIRMED", "#00CC44"    # deep market agrees
            elif liq_score >= 0.70 and raw_yes < 0.35:
                signal, signal_color = "CONTRARIAN", "#FF4444"   # deep market prices NO
            else:
                signal, signal_color = "WATCH", "#FF8C00"        # wait for clarity

            results.append({
                "title": title[:80], "url": m.get("slug", ""),
                "raw_yes": round(raw_yes * 100, 1),
                "adj_yes": round(adj_prob * 100, 1),
                "liq_score": liq_score,
                "reliability": round(reliability, 2),
                "edge": round(edge, 3),
                "mispricing_score": mispricing_score,
                "vol": vol, "vol24": vol24,
                "activity_ratio": round(activity_ratio, 3),
                "signal": signal, "signal_color": signal_color,
                "spread": spread_str,
                "liq_tier": ("DEEP" if liq_score >= 0.8 else "MED" if liq_score >= 0.5
                              else "THIN" if liq_score >= 0.2 else "ILLIQ"),
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["mispricing_score"], reverse=True)
    return results[:15]


# ════════════════════════════════════════════════════════════════════
# GEO TAB — DATA FETCHERS & CONSTANTS
# ════════════════════════════════════════════════════════════════════

GEO_FINANCIAL_NETWORKS = [
    {"name": "Bloomberg",  "channel_id": "UCIALMKvObZNtJ6AmdCLP7Lg", "embed_url": "https://www.youtube.com/embed/iEpJwprxDdk?autoplay=1&mute=1"},
    {"name": "CNBC",       "channel_id": "UCvJJ_dzjViJCoLf5uKUTwoA", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCvJJ_dzjViJCoLf5uKUTwoA&autoplay=1&mute=1"},
    {"name": "Euronews",   "channel_id": "UCW2QcKZiU8aUGg4yxCIditg", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCW2QcKZiU8aUGg4yxCIditg&autoplay=1&mute=1"},
    {"name": "France 24",  "channel_id": "UCQfwfsi5VrQ8yKZ-UWmAoBw", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCQfwfsi5VrQ8yKZ-UWmAoBw&autoplay=1&mute=1"},
    {"name": "Al Jazeera", "channel_id": "UCNye-wNBqNL5ZzHSJj3l8Bg", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCNye-wNBqNL5ZzHSJj3l8Bg&autoplay=1&mute=1"},
    {"name": "DW News",    "channel_id": "UCknLrEdhRCp1aegoMqRaCZg", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCknLrEdhRCp1aegoMqRaCZg&autoplay=1&mute=1"},
    {"name": "Sky News",   "channel_id": "UCoMdktPbSTixAyNGwb-UYkQ", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ&autoplay=1&mute=1"},
]

GEO_WEBCAM_FEEDS = [
    {"id": "tehran", "city": "Tehran", "country": "Iran", "region": "Middle East", "fallbackVideoId": "-zGuR1qVKrU"},
    {"id": "tel-aviv", "city": "Tel Aviv", "country": "Israel", "region": "Middle East", "fallbackVideoId": "JHwwZRH2wz8"},
    {"id": "jerusalem", "city": "Jerusalem", "country": "Israel", "region": "Middle East", "fallbackVideoId": "UyduhBUpO7Q"},
    {"id": "dubai", "city": "Dubai", "country": "UAE", "region": "Middle East", "fallbackVideoId": "MfIpyflPbHQ"},
    {"id": "kyiv", "city": "Kyiv", "country": "Ukraine", "region": "Europe", "fallbackVideoId": "-Q7FuPINDjA"},
    {"id": "odessa", "city": "Odessa", "country": "Ukraine", "region": "Europe", "fallbackVideoId": "e2gC37ILQmk"},
    {"id": "paris", "city": "Paris", "country": "France", "region": "Europe", "fallbackVideoId": "OzYp4NRZlwQ"},
    {"id": "st-petersburg", "city": "St. Petersburg","country": "Russia", "region": "Europe", "fallbackVideoId": "CjtIYbmVfck"},
    {"id": "london", "city": "London", "country": "UK", "region": "Europe", "fallbackVideoId": "M3EYAY2MftI"},
    {"id": "washington", "city": "Washington DC","country": "USA", "region": "Americas", "fallbackVideoId": "1wV9lLe14aU"},
    {"id": "new-york", "city": "New York", "country": "USA", "region": "Americas", "fallbackVideoId": "4qyZLflp-sI"},
    {"id": "los-angeles", "city": "Los Angeles", "country": "USA", "region": "Americas", "fallbackVideoId": "EO_1LWqsCNE"},
    {"id": "miami", "city": "Miami", "country": "USA", "region": "Americas", "fallbackVideoId": "5YCajRjvWCg"},
    {"id": "taipei", "city": "Taipei", "country": "Taiwan", "region": "Asia-Pacific", "fallbackVideoId": "z_fY1pj1VBw"},
    {"id": "shanghai", "city": "Shanghai", "country": "China", "region": "Asia-Pacific", "fallbackVideoId": "76EwqI5XZIc"},
    {"id": "tokyo", "city": "Tokyo", "country": "Japan", "region": "Asia-Pacific", "fallbackVideoId": "4pu9sF5Qssw"},
    {"id": "seoul", "city": "Seoul", "country": "South Korea", "region": "Asia-Pacific", "fallbackVideoId": "-JhoMGoAfFc"},
    {"id": "sydney", "city": "Sydney", "country": "Australia", "region": "Asia-Pacific", "fallbackVideoId": "7pcL-0Wo77U"},
]

GEO_SHIPPING_LANES = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"name": "Trans-Pacific", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[121.5, 31.2], [140.0, 35.0], [160.0, 38.0], [180.0, 35.0], [-160.0, 28.0], [-140.0, 24.0], [-118.2, 33.7]]}},
        {"type": "Feature", "properties": {"name": "Trans-Atlantic", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[2.35, 48.85], [-5.0, 48.0], [-20.0, 42.0], [-40.0, 38.0], [-60.0, 35.0], [-74.0, 40.7]]}},
        {"type": "Feature", "properties": {"name": "Suez / Red Sea", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[5.0, 36.0], [15.0, 37.0], [25.0, 35.0], [32.0, 31.0], [32.5, 29.9], [33.5, 27.0], [38.0, 23.0], [43.5, 12.5], [50.0, 10.0]]}},
        {"type": "Feature", "properties": {"name": "Strait of Hormuz", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[50.0, 10.0], [55.0, 15.0], [58.0, 20.0], [56.5, 24.0], [57.5, 23.6]]}},
        {"type": "Feature", "properties": {"name": "Malacca / SCS", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[80.0, 5.0], [90.0, 3.0], [100.0, 2.5], [104.5, 1.3], [108.0, 3.5], [110.0, 5.0], [115.0, 8.0], [121.5, 22.0], [121.5, 31.2]]}},
        {"type": "Feature", "properties": {"name": "Cape of Good Hope", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[2.35, 48.85], [-10.0, 30.0], [-17.0, 14.0], [-14.0, -8.0], [0.0, -20.0], [18.5, -34.0], [25.0, -34.5], [35.0, -28.0], [43.5, -12.0], [50.0, 10.0]]}},
    ],
}

GEO_THEATERS = {
    "Middle East + Oil + Hormuz":         "Middle East Iran oil Hormuz",
    "China + Taiwan + Semiconductors":    "China Taiwan semiconductor chips TSMC",
    "Russia + Ukraine + Energy":          "Russia Ukraine energy grain NATO",
    "Africa + Cobalt + Lithium + Coup":   "Africa cobalt lithium coup Sahel Mali",
    "Red Sea + Suez + Shipping":          "Red Sea Suez shipping Houthi container",
    "South China Sea + Trade":            "South China Sea shipping Philippines trade",
}

GEO_IMPACT_TICKERS = {
    "WTI Crude": "CL=F", "Brent Crude": "BZ=F", "Natural Gas": "NG=F",
    "Gold":      "GC=F", "Silver":      "SI=F", "Wheat":       "ZW=F",
    "USD Index": "DX-Y.NYB", "EUR/USD": "EURUSD=X", "10Y Yield": "^TNX",
}


def fetch_military_aircraft() -> "pd.DataFrame":
    import pandas as _pd
    try:
        data = _fetch_robust_json("https://api.airplanes.live/v2/mil", timeout=15)
        ac_list = data.get("ac", [])
        rows = []
        for ac in ac_list:
            lat, lon = ac.get("lat"), ac.get("lon")
            if lat is None or lon is None: continue
            rows.append({
                "hex": ac.get("hex", ""), "lat": float(lat), "lon": float(lon),
                "alt_baro": int(ac.get("alt_baro") or 0), "gs": int(ac.get("gs") or 0),
                "flight": str(ac.get("flight") or ac.get("hex", "UNKN")).strip(),
                "track": float(ac.get("track") or 0), "size": 48,
            })
        df = _pd.DataFrame(rows)
        if not df.empty:
            df["photo_url"] = df["hex"].apply(lambda h: f"https://api.planespotters.net/pub/photos/hex/{h}")
        return df
    except Exception as e:
        logger.error("Military Flight Fetch Error: %s", str(e))
        return _pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_satellite_positions():
    import pandas as _pd
    try:
        from skyfield.api import EarthSatellite, load, wgs84 as _wgs84
        import numpy as _np
    except ImportError:
        logger.error("Satellite Tracker: Missing skyfield")
        return _pd.DataFrame(), []

    try:
        r = requests.get("https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle", timeout=15, headers={"User-Agent": "SENTINEL/3.0"})
        r.raise_for_status()
        lines = [l.strip() for l in r.text.strip().splitlines() if l.strip()]
    except Exception as e:
        logger.error("Celestrak Error: %s", str(e))
        return _pd.DataFrame(), []

    from datetime import timezone as _tz, timedelta as _td
    ts = load.timescale()
    now_utc = datetime.now(_tz.utc)
    t_now = ts.from_datetime(now_utc)

    sats, i = [], 0
    while i + 2 < len(lines):
        name, tle1, tle2 = lines[i], lines[i + 1], lines[i + 2]
        if tle1.startswith("1 ") and tle2.startswith("2 "):
            try: sats.append(EarthSatellite(tle1, tle2, name, ts))
            except Exception: pass
            i += 3
        else: i += 1

    sats = sats[:50]
    rows, path_features = [], []

    for sat in sats:
        try:
            geo = _wgs84.geographic_position_of(sat.at(t_now))
            lat, lon, alt_km = float(geo.latitude.degrees), float(geo.longitude.degrees), float(geo.elevation.km)
            try: n = sat.model.no_kozai * (1440 / (2 * _np.pi))
            except Exception: n = 15.5
            vel_kms = round(n * 2 * _np.pi * (6371 + alt_km) / 86400, 2)

            rows.append({"name": sat.name, "lat": lat, "lon": lon, "alt_km": round(alt_km, 1), "vel_kms": vel_kms, "size": 32})
            path_coords = []
            for offset in range(0, 91, 5):
                t_f = ts.from_datetime(now_utc + _td(minutes=offset))
                g = _wgs84.geographic_position_of(sat.at(t_f))
                path_coords.append([float(g.longitude.degrees), float(g.latitude.degrees)])
            path_features.append({"path": path_coords, "name": sat.name, "color": [0, 180, 255, 100]})
        except Exception: continue

    return _pd.DataFrame(rows), path_features


@st.cache_data(ttl=300)
def fetch_conflict_events() -> "pd.DataFrame":
    import pandas as _pd
    try:
        url = "https://api.gdeltproject.org/api/v2/geo/geo?query=(strike%20OR%20attack%20OR%20bombing%20OR%20explosion%20OR%20war%20OR%20conflict)&mode=pointdata&format=geojson&timespan=24h"
        data = _fetch_robust_json(url, timeout=12, headers={"User-Agent": "SENTINEL/3.0"})
        features = data.get("features", [])
        rows = []
        for f in features:
            coords = f.get("geometry", {}).get("coordinates", [])
            props  = f.get("properties", {})
            if len(coords) < 2: continue
            rows.append({"lon": float(coords[0]), "lat": float(coords[1]), "name": props.get("name", "Event"), "url": props.get("url", "")})
        return _pd.DataFrame(rows)
    except Exception:
        return _pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_conflict_events_json():
    df = fetch_conflict_events()
    return [] if df is None or df.empty else df.to_dict("records")


def _strip_llm_json(raw: str) -> str:
    """Strip markdown code fences and trailing commas from LLM output."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"```\s*$", "", text).strip()
    # Remove trailing commas before ] or } (common LLM hallucination)
    text = re.sub(r",\s*([\]}])", r"\1", text)
    return text


@st.cache_data(ttl=43200)
def fetch_ai_hotspots_json(gemini_api_key: str) -> list:
    """Use Gemini + Google Search grounding to discover top breaking conflicts.

    Cached for 12 hours (ttl=43200) to prevent API quota burn.
    Returns a list of dicts with keys: lat, lon, name, url.
    Returns [] on any failure — never crashes the UI.
    """
    if not gemini_api_key or genai is None:
        return []
    try:
        client = genai.Client(api_key=gemini_api_key)
        grounding_tool = genai_types.Tool(
            google_search=genai_types.GoogleSearch()
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                "Search the web for the top 5 most critical breaking geopolitical "
                "conflicts or military escalations happening in the world RIGHT NOW. "
                "For each, determine the approximate latitude and longitude of the "
                "primary location. Return ONLY a raw JSON array — no explanation, "
                "no markdown fences. Format: "
                '[{"lat": float, "lon": float, "name": "Event Name", "url": "source_url"}]'
            ),
            config=genai_types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )
        cleaned = _strip_llm_json(response.text)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            logger.warning({"msg": "AI hotspots returned non-list JSON"})
            return []
        # Validate each entry has the required keys
        valid = []
        for item in parsed:
            if isinstance(item, dict) and "lat" in item and "lon" in item and "name" in item:
                valid.append({
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "name": str(item["name"]),
                    "url": str(item.get("url", "")),
                })
        logger.info({"count": len(valid)}, "AI hotspots fetched")
        return valid
    except Exception as exc:
        logger.error({"error": str(exc)}, "AI hotspots fetch failed")
        return []

@st.cache_data(ttl=300)
def fetch_military_aircraft_json():
    df = fetch_military_aircraft()
    return [] if df is None or df.empty else df.to_dict("records")

@st.cache_data(ttl=300)
def fetch_satellite_positions_json():
    df, _ = fetch_satellite_positions()
    return [] if df is None or df.empty else df.to_dict("records")

@st.cache_data(ttl=300)
def fetch_ais_vessels():
    vessels = []
    ais_key = st.secrets.get("AISSTREAM_API_KEY", "") or ""
    if ais_key:
        try:
            data = _fetch_robust_json("https://api.aisstream.io/v0/ships", params={"apikey": ais_key}, timeout=12, headers={"User-Agent": "SENTINEL/3.0"})
            ships = data if isinstance(data, list) else data.get("data", data.get("ships", []))
            for s in ships[:200]:
                pos = s.get("position", s)
                lat, lon = pos.get("lat", pos.get("latitude")), pos.get("lon", pos.get("longitude"))
                if lat is None or lon is None: continue
                vessels.append({"mmsi": str(s.get("mmsi", s.get("MMSI", ""))), "lat": float(lat), "lon": float(lon), "speed": float(s.get("speed", s.get("sog", 0)) or 0), "heading": float(s.get("heading", s.get("cog", 0)) or 0), "name": str(s.get("name", s.get("shipName", "VESSEL"))).strip()[:30], "type": str(s.get("shipType", s.get("type", "cargo")))})
        except Exception: pass

    mar_key = st.secrets.get("MARINESIA_API_KEY", "") or ""
    if mar_key:
        import time as _time
        _CHOKEPOINT_BOXES = [("suez", 29.0, 30.5, 32.0, 33.5), ("hormuz", 25.5, 27.5, 55.0, 57.0), ("mandeb", 12.0, 13.5, 42.5, 44.0), ("malacca", 0.5, 2.5, 103.0, 104.5), ("taiwan", 23.5, 25.5, 118.5, 120.5), ("gibraltar", 35.5, 36.5, -6.0, -5.0)]
        for name, lat_min, lat_max, lon_min, lon_max in _CHOKEPOINT_BOXES:
            try:
                data = _fetch_robust_json("https://api.marinesia.com/api/v2/vessel/area", params={"lat_min": lat_min, "lat_max": lat_max, "long_min": lon_min, "long_max": lon_max, "key": mar_key}, timeout=10, headers={"User-Agent": "SENTINEL/3.0"})
                if not data.get("error") and data.get("data"):
                    for s in data["data"][:30]:
                        lat, lng = s.get("lat"), s.get("lng")
                        if lat is None or lng is None: continue
                        vessels.append({"mmsi": str(s.get("mmsi", "")), "lat": float(lat), "lon": float(lng), "speed": float(s.get("sog", 0) or 0), "heading": float(s.get("cog", s.get("hdt", 0)) or 0), "name": str(s.get("name", f"MMSI-{s.get('mmsi','')}"))[:30], "type": str(s.get("type", "cargo")).lower()})
                _time.sleep(1.0)
            except Exception: continue

    try:
        data = _fetch_robust_json("https://meri.digitraffic.fi/api/ais/v1/locations", timeout=12, headers={"User-Agent": "SENTINEL/3.0", "Accept": "application/json"})
        for f in data.get("features", [])[:200]:
            props, coords = f.get("properties", {}), f.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2: continue
            vessels.append({"mmsi": str(props.get("mmsi", "")), "lat": float(coords[1]), "lon": float(coords[0]), "speed": float(props.get("sog", 0) or 0), "heading": float(props.get("cog", props.get("heading", 0)) or 0), "name": f"MMSI-{props.get('mmsi', 'UNKN')}", "type": "cargo"})
    except Exception: pass

    try:
        data = _fetch_robust_json("https://ais.dma.dk/ais-api/getAisData", timeout=12, headers={"User-Agent": "SENTINEL/3.0", "Accept": "application/json"})
        ships = data if isinstance(data, list) else data.get("aisData", data.get("ships", []))
        for s in (ships or [])[:200]:
            lat, lon = s.get("lat", s.get("latitude")), s.get("lon", s.get("longitude"))
            if lat is None or lon is None: continue
            vessels.append({"mmsi": str(s.get("mmsi", "")), "lat": float(lat), "lon": float(lon), "speed": float(s.get("sog", s.get("speed", 0)) or 0), "heading": float(s.get("cog", s.get("heading", 0)) or 0), "name": str(s.get("name", f"MMSI-{s.get('mmsi','UNKN')}")).strip()[:30], "type": str(s.get("shipType", "cargo"))})
    except Exception: pass

    _STATIC = [
        {"mmsi": "STATIC-001", "lat": 29.95, "lon": 32.55, "speed": 8, "heading": 160, "name": "SUEZ CANAL TRANSIT", "type": "tanker"},
        {"mmsi": "STATIC-002", "lat": 26.55, "lon": 56.25, "speed": 10, "heading": 310, "name": "HORMUZ TRANSIT", "type": "tanker"},
        {"mmsi": "STATIC-003", "lat": 12.60, "lon": 43.20, "speed": 12, "heading": 340, "name": "BAB EL-MANDEB TRANSIT", "type": "cargo"},
        {"mmsi": "STATIC-004", "lat": 1.28, "lon": 103.85, "speed": 9, "heading": 45, "name": "MALACCA STRAIT TRANSIT", "type": "container"},
        {"mmsi": "STATIC-005", "lat": -34.20, "lon": 18.50, "speed": 14, "heading": 90, "name": "CAPE GOOD HOPE TRANSIT", "type": "tanker"},
        {"mmsi": "STATIC-006", "lat": 9.10, "lon": -79.70, "speed": 11, "heading": 270, "name": "PANAMA CANAL TRANSIT", "type": "container"},
        {"mmsi": "STATIC-007", "lat": 35.00, "lon": 136.00, "speed": 10, "heading": 200, "name": "JAPAN STRAIT TRANSIT", "type": "cargo"},
        {"mmsi": "STATIC-008", "lat": 51.00, "lon": 1.50, "speed": 8, "heading": 220, "name": "ENGLISH CHANNEL TRANSIT", "type": "container"},
        {"mmsi": "STATIC-009", "lat": 13.50, "lon": 48.00, "speed": 14, "heading": 30, "name": "GULF OF ADEN CONVOY", "type": "tanker"},
        {"mmsi": "STATIC-010", "lat": 15.80, "lon": 41.80, "speed": 10, "heading": 350, "name": "RED SEA NORTHBOUND", "type": "cargo"},
        {"mmsi": "STATIC-011", "lat": 10.50, "lon": 114.00, "speed": 12, "heading": 30, "name": "SCS PARACEL ROUTE", "type": "container"},
        {"mmsi": "STATIC-012", "lat": 7.50, "lon": 116.50, "speed": 11, "heading": 315, "name": "SCS SPRATLY ROUTE", "type": "tanker"},
        {"mmsi": "STATIC-013", "lat": 24.50, "lon": 119.50, "speed": 13, "heading": 20, "name": "TAIWAN STRAIT TRANSIT", "type": "cargo"},
        {"mmsi": "STATIC-014", "lat": 31.35, "lon": 121.50, "speed": 5, "heading": 90, "name": "SHANGHAI APPROACH", "type": "container"},
        {"mmsi": "STATIC-015", "lat": 22.30, "lon": 114.15, "speed": 6, "heading": 180, "name": "HONG KONG APPROACH", "type": "container"},
        {"mmsi": "STATIC-016", "lat": 40.67, "lon": -74.05, "speed": 7, "heading": 0, "name": "NEW YORK APPROACH", "type": "tanker"},
        {"mmsi": "STATIC-017", "lat": 51.90, "lon": 4.50, "speed": 6, "heading": 90, "name": "ROTTERDAM APPROACH", "type": "container"},
        {"mmsi": "STATIC-018", "lat": 35.50, "lon": 139.80, "speed": 5, "heading": 270, "name": "TOKYO BAY APPROACH", "type": "cargo"},
        {"mmsi": "STATIC-019", "lat": 41.20, "lon": 29.00, "speed": 9, "heading": 210, "name": "BOSPHORUS TRANSIT", "type": "tanker"},
        {"mmsi": "STATIC-020", "lat": 36.00, "lon": -5.40, "speed": 11, "heading": 90, "name": "GIBRALTAR TRANSIT", "type": "cargo"},
    ]
    vessels.extend(_STATIC)

    seen = {}
    for v in vessels:
        mmsi = v.get("mmsi", "")
        if not mmsi: continue
        existing = seen.get(mmsi)
        if existing is None: seen[mmsi] = v
        else:
            new_name, old_name = v.get("name", ""), existing.get("name", "")
            if (old_name.startswith("MMSI-") or old_name == "VESSEL") and not new_name.startswith("MMSI-") and new_name != "VESSEL":
                seen[mmsi] = v

    return list(seen.values())

# ════════════════════════════════════════════════════════════════════
# CRYPTO — INSTITUTIONAL BTC ETF FLOWS
# ════════════════════════════════════════════════════════════════════

_ETF_TICKERS = ["IBIT", "FBTC", "ARKB", "BITB", "GBTC", "HODL", "BRRR", "EZBC", "BTCO", "BTCW"]
_ETF_COLORS = {"IBIT": "#00CC44", "FBTC": "#00AA88", "ARKB": "#44BB66", "BITB": "#66CC88", "GBTC": "#FF4444", "HODL": "#55DD99", "BRRR": "#33CC77", "EZBC": "#77DDAA", "BTCO": "#88CCBB", "BTCW": "#99BBAA"}
def _fetch_yahoo_v8_chart(ticker, range_str="5d", interval="1d"):
    import random
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval={interval}"
    try:
        ua = random.choice(_YAHOO_UAS)
        data = _fetch_robust_json(url, headers={"User-Agent": ua}, timeout=10)
        result = data.get("chart", {}).get("result", [])
        if not result: return []
        meta = result[0]
        timestamps, indicators = meta.get("timestamp", []), meta.get("indicators", {}).get("quote", [{}])[0]
        highs, lows = indicators.get("high", []), indicators.get("low", [])
        closes, volumes = indicators.get("close", []), indicators.get("volume", [])
        if not timestamps or not closes: return []

        rows = []
        for i, ts in enumerate(timestamps):
            c = closes[i] if i < len(closes) else None
            h = highs[i] if i < len(highs) else c
            l = lows[i] if i < len(lows) else c
            v = volumes[i] if i < len(volumes) else None
            if c is None or v is None: continue
            rows.append({
                "timestamp": ts, 
                "close": float(c), 
                "high": float(h) if h else float(c),
                "low": float(l) if l else float(c),
                "volume": int(v)
            })
        return rows
    except Exception as e:
        logger.error("Failed to fetch Yahoo V8 chart for %s: %s", ticker, str(e))
        return []

@st.cache_data(ttl=600)
def fetch_btc_etf_flows():
    import pandas as _pd
    import time as _time
    all_flows = {}
    
    for ticker in _ETF_TICKERS:
        try:
            _time.sleep(1.0 + (_time.time() % 1.5))
            rows = _fetch_yahoo_v8_chart(ticker, range_str="5d", interval="1d")
            if not rows or len(rows) < 2: continue
            ticker_flows = {}
            for i in range(1, len(rows)):
                prev_close = rows[i - 1]["close"]
                curr_close, curr_high, curr_low = rows[i]["close"], rows[i]["high"], rows[i]["low"]
                volume, ts = rows[i]["volume"], rows[i]["timestamp"]
                
                if prev_close <= 0 or curr_close <= 0: continue
                vwap = (curr_high + curr_low + curr_close) / 3.0
                direction = 1.0 if (curr_close - prev_close) >= 0 else -1.0
                # FIX-13: Removed arbitrary 0.10 multiplier; express in billions
                ticker_flows[_pd.Timestamp.fromtimestamp(ts).normalize()] = round((volume * vwap * direction) / 1e9, 4)
            if ticker_flows: all_flows[ticker] = ticker_flows
            _time.sleep(1.0)
        except Exception as e:
            logger.error("BTC ETF Flow specific fallback error for %s: %s", ticker, str(e))
            continue

    if not all_flows: return None
    df = _pd.DataFrame(all_flows)
    df.index = _pd.to_datetime(df.index)
    df = df.sort_index().fillna(0)
    df["Total"] = df[[c for c in df.columns if c in _ETF_TICKERS]].sum(axis=1)
    return df if len(df) > 0 else None

@st.cache_data(ttl=1800)
def fetch_btc_etf_flows_fallback():
    import pandas as _pd
    if yf is None: return None
    try:
        all_data = {}
        for ticker in _ETF_TICKERS:
            try:
                tk = get_yf_ticker(ticker)
                if tk is None: continue
                hist = tk.history(period="60d")
                if hist is None or hist.empty or len(hist) < 2: continue
                prev_close = hist["Close"].shift(1)
                vwap = (hist["High"] + hist["Low"] + hist["Close"]) / 3.0
                direction = (hist["Close"] - prev_close).apply(lambda x: 1.0 if x >= 0 else -1.0)
                # FIX-13: Removed arbitrary 0.10 multiplier; express in billions
                all_data[ticker] = ((hist["Volume"] * vwap * direction) / 1e9).iloc[1:]
            except Exception as e:
                logger.error("BTC ETF Fallback flow error for %s: %s", ticker, str(e))
                continue

        if not all_data: return None
        df = _pd.DataFrame(all_data)
        df.index = _pd.to_datetime(df.index).tz_localize(None)
        df = df.fillna(0)
        df["Total"] = df[[c for c in df.columns if c in _ETF_TICKERS]].sum(axis=1)
        return df.tail(30) if len(df) > 0 else None
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 1: GLOBAL WEI MONITOR (World Equity Indices)
# ════════════════════════════════════════════════════════════════════

_GLOBAL_INDICES = {
    "Americas": [
        ("^GSPC", "S&P 500", "🇺🇸"),
        ("^DJI", "Dow Jones", "🇺🇸"),
        ("^IXIC", "Nasdaq Composite", "🇺🇸"),
        ("^RUT", "Russell 2000", "🇺🇸"),
        ("^GSPTSE", "TSX Composite", "🇨🇦"),
        ("^BVSP", "Bovespa", "🇧🇷"),
    ],
    "EMEA": [
        ("^FTSE", "FTSE 100", "🇬🇧"),
        ("^GDAXI", "DAX", "🇩🇪"),
        ("^FCHI", "CAC 40", "🇫🇷"),
        ("^STOXX50E", "Euro Stoxx 50", "🇪🇺"),
        ("^AEX", "AEX", "🇳🇱"),
        ("^TA125.TA", "TA-125", "🇮🇱"),
    ],
    "APAC": [
        ("^N225", "Nikkei 225", "🇯🇵"),
        ("^HSI", "Hang Seng", "🇭🇰"),
        ("000001.SS", "Shanghai Comp", "🇨🇳"),
        ("^KS11", "KOSPI", "🇰🇷"),
        ("^AXJO", "ASX 200", "🇦🇺"),
        ("^BSESN", "Sensex", "🇮🇳"),
    ],
}

@st.cache_data(ttl=300)
def get_global_indices():
    """Fetch global equity indices with sparkline data using yf.download bulk."""
    import numpy as np
    if yf is None:
        return pd.DataFrame()

    all_tickers = []
    ticker_meta = {}
    for region, indices in _GLOBAL_INDICES.items():
        for ticker, name, flag in indices:
            all_tickers.append(ticker)
            ticker_meta[ticker] = {"name": name, "flag": flag, "region": region}

    try:
        # Bulk download: 35 trading-day history for sparkline + volatility
        data = yf.download(all_tickers, period="35d", progress=False, threads=True)
        if data.empty:
            return pd.DataFrame()

        rows = []
        for ticker in all_tickers:
            try:
                meta = ticker_meta[ticker]
                # Handle MultiIndex columns from yf.download
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"][ticker].dropna()
                else:
                    close = data["Close"].dropna()

                if close.empty or len(close) < 2:
                    continue

                current = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                change = round(current - prev, 2)
                pct = round(change / prev * 100, 2) if prev != 0 else 0.0

                # Sparkline: last 2 trading days (intraday proxy from close values)
                sparkline = close.tail(10).tolist()

                # 10D and 30D annualized volatility
                returns = close.pct_change().dropna()
                vol_10d = round(float(returns.tail(10).std() * np.sqrt(252) * 100), 2) if len(returns) >= 10 else 0.0
                vol_30d = round(float(returns.tail(30).std() * np.sqrt(252) * 100), 2) if len(returns) >= 20 else 0.0

                rows.append({
                    "Region": meta["region"],
                    "Flag": meta["flag"],
                    "Index": meta["name"],
                    "Ticker": ticker,
                    "Value": current,
                    "Change": change,
                    "% Chg": pct,
                    "10D Vol": vol_10d,
                    "30D Vol": vol_30d,
                    "Sparkline": sparkline,
                })
            except (KeyError, IndexError, TypeError) as e:
                logger.warning("Global index skip", extra={"ticker": ticker, "error": str(e)})
                continue

        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except requests.exceptions.RequestException as e:
        logger.error("Global indices fetch failed", extra={"error": str(e)})
        return pd.DataFrame()
    except Exception as e:
        logger.error("Global indices unexpected error", extra={"error": str(e)})
        return pd.DataFrame()


# ════════════════════════════════════════════════════════════════════
# FEATURE 2: NET LIQUIDITY INDICATOR (FRED: WALCL - WTREGEN - RRPONTSYD)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_net_liquidity(fred_key, lookback=365):
    """Calculate Net Liquidity = WALCL - WTREGEN - RRPONTSYD from FRED.
    
    WALCL: Fed Total Assets (Millions)
    WTREGEN: Treasury General Account (Millions)
    RRPONTSYD: Reverse Repo (Billions → converted to Millions)
    """
    if not fred_key:
        return None
    try:
        walcl = fred_series("WALCL", fred_key, lookback)
        wtregen = fred_series("WTREGEN", fred_key, lookback)
        rrp = fred_series("RRPONTSYD", fred_key, lookback)

        if walcl is None or wtregen is None or rrp is None:
            return None
        if walcl.empty or wtregen.empty or rrp.empty:
            return None

        # Align to weekly (Wednesday) — use forward-fill to handle different frequencies
        walcl = walcl.set_index("date").resample("W-WED")["value"].last().ffill()
        wtregen = wtregen.set_index("date").resample("W-WED")["value"].last().ffill()
        # RRPONTSYD is in billions, convert to millions to match WALCL/WTREGEN
        rrp = rrp.set_index("date").resample("W-WED")["value"].last().ffill() * 1000

        # Align indices
        df = pd.DataFrame({
            "WALCL": walcl,
            "TGA": wtregen,
            "RRP": rrp,
        }).dropna()

        if df.empty:
            return None

        df["Net_Liquidity"] = df["WALCL"] - df["TGA"] - df["RRP"]
        df["Net_Liquidity_T"] = df["Net_Liquidity"] / 1e6  # Convert millions to trillions
        df = df.reset_index().rename(columns={"date": "Date"})
        return df
    except requests.exceptions.RequestException as e:
        logger.error("Net liquidity FRED fetch failed", extra={"error": str(e)})
        return None
    except Exception as e:
        logger.error("Net liquidity calculation error", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 3: YIELD CURVE EVOLUTION (FRED: DGS1MO through DGS30)
# ════════════════════════════════════════════════════════════════════

_YIELD_MATURITIES = [
    ("DGS1MO", "1M"), ("DGS3MO", "3M"), ("DGS6MO", "6M"),
    ("DGS1", "1Y"), ("DGS2", "2Y"), ("DGS3", "3Y"),
    ("DGS5", "5Y"), ("DGS7", "7Y"), ("DGS10", "10Y"),
    ("DGS20", "20Y"), ("DGS30", "30Y"),
]

@st.cache_data(ttl=3600)
def get_yield_curve_history(fred_key, lookback_weeks=52):
    """Fetch yield curve data across all maturities for 3D surface/animation.
    
    Returns DataFrame with columns: Date, Maturity, Yield, Maturity_Num
    """
    if not fred_key:
        return None
    try:
        all_data = {}
        for series_id, label in _YIELD_MATURITIES:
            df = fred_series(series_id, fred_key, lookback_weeks * 5)
            if df is not None and not df.empty:
                s = df.set_index("date")["value"]
                all_data[label] = s

        if len(all_data) < 5:
            return None

        combined = pd.DataFrame(all_data).dropna(how="all")
        combined = combined.ffill()

        # Sample weekly for animation frames
        combined = combined.resample("W-FRI").last().dropna(how="all")

        # Melt to long format for Plotly
        maturity_map = {"1M": 1/12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2,
                        "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30}

        rows = []
        for date_idx, row in combined.iterrows():
            for mat_label, val in row.items():
                if pd.notna(val):
                    rows.append({
                        "Date": date_idx,
                        "Maturity": mat_label,
                        "Yield": float(val),
                        "Maturity_Num": maturity_map.get(mat_label, 0),
                    })

        return pd.DataFrame(rows) if rows else None
    except Exception as e:
        logger.error("Yield curve history fetch failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 4: CROSS-ASSET VOLATILITY MONITOR
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def get_cross_asset_volatility():
    """Fetch VIX, GVZ (gold), OVX (oil), EVZ (euro) volatility indices."""
    if yf is None:
        return None
    vol_tickers = ["^VIX", "^GVZ", "^OVX", "^EVZ"]
    labels = {"^VIX": "VIX (Equity)", "^GVZ": "GVZ (Gold)", "^OVX": "OVX (Oil)", "^EVZ": "EVZ (Euro)"}

    try:
        data = yf.download(vol_tickers, period="6mo", progress=False, threads=True)
        if data.empty:
            return None

        rows = []
        for ticker in vol_tickers:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"][ticker].dropna()
                else:
                    close = data["Close"].dropna()

                if close.empty or len(close) < 5:
                    continue

                current = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                pct = round((current - prev) / prev * 100, 2) if prev else 0.0

                # Percentile rank over 6 months
                pct_rank = round((close < current).mean() * 100, 1)

                # Determine regime
                if pct_rank < 25:
                    regime = "LOW"
                elif pct_rank < 75:
                    regime = "NORMAL"
                else:
                    regime = "ELEVATED"

                sparkline = close.tail(60).tolist()

                rows.append({
                    "ticker": ticker,
                    "label": labels.get(ticker, ticker),
                    "current": round(current, 2),
                    "change_pct": pct,
                    "percentile": pct_rank,
                    "regime": regime,
                    "sparkline": sparkline,
                    "history": close.reset_index().rename(columns={"Date": "date", ticker: "value"}).to_dict("records") if not isinstance(data.columns, pd.MultiIndex) else [],
                })
            except (KeyError, IndexError) as e:
                logger.warning("Vol index skip", extra={"ticker": ticker, "error": str(e)})
                continue

        return rows if rows else None
    except Exception as e:
        logger.error("Cross-asset vol fetch failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 5: MACRO CORRELATION MATRIX (Pearson + Spearman)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_macro_correlation_matrix(lookback_days=60):
    """Compute Pearson and Spearman correlation matrices for cross-asset analysis.
    
    FEAT-06: Expanded from 5 to 7 assets (added ^TNX + HYG).
    Returns dict with {pearson, spearman, labels, lookback_days} or None.
    """
    import numpy as np
    if yf is None:
        return None

    assets = {
        "SPY": "S&P 500", "TLT": "Bonds (20Y)", "GLD": "Gold",
        "USO": "Oil", "UUP": "Dollar", "^TNX": "10Y Yield", "HYG": "HY Credit",
    }
    tickers = list(assets.keys())

    try:
        data = yf.download(tickers, period=f"{lookback_days + 10}d", progress=False, threads=True)
        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            closes = data[["Close"]]

        returns = closes.pct_change().dropna().tail(lookback_days)

        if returns.empty or len(returns) < 20:
            return None

        pearson = returns.corr(method="pearson")
        spearman = returns.corr(method="spearman")
        labels = [assets.get(t, t) for t in pearson.columns]
        
        pearson.columns = labels
        pearson.index = labels
        spearman.columns = labels
        spearman.index = labels

        return {
            "pearson": pearson,
            "spearman": spearman,
            "labels": labels,
            "lookback_days": lookback_days,
        }
    except Exception as e:
        logger.error("Correlation matrix calculation failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 6: SECTOR RELATIVE ROTATION GRAPH (RRG)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_sector_rrg():
    """Calculate Relative Rotation Graph data: RS-Ratio vs RS-Momentum for sector ETFs vs SPY."""
    import numpy as np
    if yf is None:
        return None

    sector_etf_map = {
        "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
        "XLV": "Healthcare", "XLP": "Staples", "XLU": "Utilities",
        "XLY": "Discretionary", "XLB": "Materials", "XLC": "Comm Svcs",
        "XLRE": "Real Estate", "XLI": "Industrials",
    }

    tickers = list(sector_etf_map.keys()) + ["SPY"]

    try:
        data = yf.download(tickers, period="6mo", progress=False, threads=True)
        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            return None

        spy_close = closes["SPY"].dropna()
        if spy_close.empty or len(spy_close) < 60:
            return None

        rows = []
        for etf, sector_name in sector_etf_map.items():
            try:
                etf_close = closes[etf].dropna()
                if len(etf_close) < 60:
                    continue

                # Align to common dates
                aligned = pd.DataFrame({"etf": etf_close, "spy": spy_close}).dropna()
                if len(aligned) < 60:
                    continue

                # Relative Strength = ETF / SPY
                rs = aligned["etf"] / aligned["spy"]
                # Normalize RS to 100-centered using 60-day SMA
                rs_sma = rs.rolling(60).mean()
                rs_ratio = (rs / rs_sma * 100).dropna()

                if rs_ratio.empty:
                    continue

                # RS-Momentum = rate of change of RS-Ratio
                rs_momentum = rs_ratio.pct_change(periods=10) * 100 + 100  # centered at 100

                current_ratio = float(rs_ratio.iloc[-1])
                current_momentum = float(rs_momentum.dropna().iloc[-1]) if not rs_momentum.dropna().empty else 100.0

                # Trail: last 4 weekly points for animation
                trail_ratio = rs_ratio.resample("W").last().dropna().tail(4).tolist()
                trail_momentum = rs_momentum.resample("W").last().dropna().tail(4).tolist()

                # Quadrant classification
                if current_ratio >= 100 and current_momentum >= 100:
                    quadrant = "LEADING"
                elif current_ratio >= 100 and current_momentum < 100:
                    quadrant = "WEAKENING"
                elif current_ratio < 100 and current_momentum < 100:
                    quadrant = "LAGGING"
                else:
                    quadrant = "IMPROVING"

                rows.append({
                    "etf": etf,
                    "sector": sector_name,
                    "rs_ratio": round(current_ratio, 2),
                    "rs_momentum": round(current_momentum, 2),
                    "quadrant": quadrant,
                    "trail_ratio": trail_ratio,
                    "trail_momentum": trail_momentum,
                })
            except (KeyError, IndexError, ZeroDivisionError) as e:
                logger.warning("RRG sector skip", extra={"etf": etf, "error": str(e)})
                continue

        return rows if rows else None
    except Exception as e:
        logger.error("Sector RRG calculation failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 7: IV TERM STRUCTURE (SPY ATM IV across 5+ expiries)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def get_iv_term_structure(ticker="SPY"):
    """Get ATM implied volatility across multiple expiration dates."""
    if yf is None:
        return None
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None

        # Get current price
        fi = tk.fast_info
        price = getattr(fi, "last_price", None)
        if price is None or price <= 0:
            h = tk.history(period="1d")
            price = float(h["Close"].iloc[-1]) if not h.empty else None
        if price is None:
            return None

        exps = list(tk.options)
        if not exps:
            return None

        # Take up to 8 expiries for the term structure
        selected_exps = exps[:min(8, len(exps))]
        today = datetime.today().date()

        rows = []
        for exp in selected_exps:
            try:
                chain = tk.option_chain(exp)
                if chain is None:
                    continue

                calls, puts = chain.calls, chain.puts
                if calls.empty and puts.empty:
                    continue

                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                dte = max((exp_date - today).days, 1)

                # Find ATM strike (closest to current price)
                if not calls.empty and "strike" in calls.columns:
                    calls["_dist"] = (calls["strike"] - price).abs()
                    atm_call = calls.nsmallest(1, "_dist")
                    call_iv = float(atm_call["impliedVolatility"].iloc[0]) if not atm_call.empty else None
                else:
                    call_iv = None

                if not puts.empty and "strike" in puts.columns:
                    puts["_dist"] = (puts["strike"] - price).abs()
                    atm_put = puts.nsmallest(1, "_dist")
                    put_iv = float(atm_put["impliedVolatility"].iloc[0]) if not atm_put.empty else None
                else:
                    put_iv = None

                # Average call and put ATM IV
                ivs = [v for v in [call_iv, put_iv] if v is not None and v > 0]
                if not ivs:
                    continue

                avg_iv = sum(ivs) / len(ivs)

                rows.append({
                    "expiry": exp,
                    "dte": dte,
                    "atm_iv": round(avg_iv * 100, 2),
                    "call_iv": round(call_iv * 100, 2) if call_iv else None,
                    "put_iv": round(put_iv * 100, 2) if put_iv else None,
                    "atm_strike": float(atm_call["strike"].iloc[0]) if not atm_call.empty else price,
                })
            except (KeyError, IndexError, ValueError) as e:
                logger.warning("IV term structure expiry skip", extra={"expiry": exp, "error": str(e)})
                continue

        return rows if rows else None
    except Exception as e:
        logger.error("IV term structure fetch failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 7B: IV SKEW SURFACE — 25-DELTA PUT/CALL SKEW
# ════════════════════════════════════════════════════════════════════

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
        if price is None or price <= 0:
            h = tk.history(period="1d")
            price = float(h["Close"].iloc[-1]) if not h.empty else None
        if price is None:
            return None

        exps = list(tk.options)
        if not exps:
            return None

        selected_exps = exps[:min(6, len(exps))]
        today = datetime.today().date()
        r = 0.045  # risk-free rate assumption

        results = []
        for exp in selected_exps:
            try:
                chain = tk.option_chain(exp)
                if chain is None:
                    continue
                calls, puts = chain.calls, chain.puts
                if calls.empty or puts.empty:
                    continue

                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                dte = max((exp_date - today).days, 1)
                T = dte / 365.0

                # ATM IV (closest strike to spot)
                calls["_dist"] = (calls["strike"] - price).abs()
                atm_call = calls.nsmallest(1, "_dist")
                atm_iv = float(atm_call["impliedVolatility"].iloc[0]) if not atm_call.empty else None

                # Find 25-delta call strike: iterate OTM calls, find closest to |delta| = 0.25
                otm_calls = calls[calls["strike"] >= price].copy()
                if not otm_calls.empty and "impliedVolatility" in otm_calls.columns:
                    otm_calls["_delta"] = otm_calls.apply(
                        lambda row: abs(bs_greeks_engine(price, row["strike"], T, r, max(row.get("impliedVolatility", 0.2), 0.01), "call")["delta"]),
                        axis=1)
                    otm_calls["_d25_diff"] = (otm_calls["_delta"] - 0.25).abs()
                    c25_row = otm_calls.nsmallest(1, "_d25_diff")
                    iv_25c = float(c25_row["impliedVolatility"].iloc[0]) if not c25_row.empty else None
                else:
                    iv_25c = None

                # Find 25-delta put strike: iterate OTM puts, find closest to |delta| = 0.25
                otm_puts = puts[puts["strike"] <= price].copy()
                if not otm_puts.empty and "impliedVolatility" in otm_puts.columns:
                    otm_puts["_delta"] = otm_puts.apply(
                        lambda row: abs(bs_greeks_engine(price, row["strike"], T, r, max(row.get("impliedVolatility", 0.2), 0.01), "put")["delta"]),
                        axis=1)
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
                    "iv_25c": round(iv_25c * 100, 2) if iv_25c else None,
                    "iv_25p": round(iv_25p * 100, 2) if iv_25p else None,
                    "skew": round(skew, 2),
                    "skew_label": skew_label,
                })
            except Exception:
                continue

        return results if results else None
    except Exception as e:
        logger.error("IV skew fetch failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 7C: REALIZED VS IMPLIED VOLATILITY SPREAD
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def get_rv_iv_spread(ticker="SPY"):
    """Compute 20-day realized vol vs front-month ATM IV.
    
    RV20 - IV spread is the canonical vol premium signal:
      spread > +3%  → SELL VOL (IV cheap relative to realized)
      spread < -3%  → BUY VOL  (IV expensive relative to realized)
    
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

        # 20-day realized volatility (annualized, close-to-close)
        returns = h["Close"].pct_change().dropna()
        rv20 = float(returns.tail(20).std() * np.sqrt(252) * 100)

        # Front-month ATM IV from existing term structure
        iv_data = get_iv_term_structure(ticker)
        if iv_data and len(iv_data) > 0:
            front_iv = iv_data[0]["atm_iv"]
            dte = iv_data[0]["dte"]
        else:
            return None

        spread = rv20 - front_iv
        if spread > 3:
            signal, signal_color = "SELL VOL", "#FF4444"
        elif spread < -3:
            signal, signal_color = "BUY VOL", "#00CC44"
        else:
            signal, signal_color = "NEUTRAL", "#888888"

        return {
            "rv20": round(rv20, 2),
            "front_iv": round(front_iv, 2),
            "spread": round(spread, 2),
            "signal": signal,
            "signal_color": signal_color,
            "dte": dte,
        }
    except Exception as e:
        logger.error("RV/IV spread failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 7D: CFTC COMMITMENT OF TRADERS (COT) INSTITUTIONAL POSITIONING
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def get_cot_positioning():
    """Fetch CFTC Commitment of Traders data for key futures contracts.
    
    Parses net non-commercial positions for ES, NQ, GC, CL, ZN from the
    CFTC bulk CSV (free, no API key). Updates weekly on Fridays.
    """
    import io
    import zipfile
    
    # Contract code map: CFTC commodity code → display name
    CONTRACT_MAP = {
        "13874+": ("S&P 500 (ES)", "ES"),
        "209742": ("Nasdaq 100 (NQ)", "NQ"),
        "088691": ("Gold (GC)", "GC"),
        "067651": ("WTI Crude (CL)", "CL"),
        "043602": ("10Y T-Note (ZN)", "ZN"),
    }

    year = datetime.today().year
    results = []

    try:
        # Try current year first, then previous year if not yet available
        for yr in [year, year - 1]:
            url = f"https://www.cftc.gov/files/dea/history/fut_fin_xls_{yr}.zip"
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code != 200:
                    continue
                with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                    csv_names = [n for n in z.namelist() if n.endswith('.csv') or n.endswith('.txt')]
                    if not csv_names:
                        continue
                    with z.open(csv_names[0]) as f:
                        import csv as _csv
                        raw_text = io.TextIOWrapper(f, encoding='utf-8', errors='replace')
                        reader = _csv.DictReader(raw_text)
                        
                        # Collect last 2 weeks of data for each contract
                        contract_data = {}
                        for row in reader:
                            cftc_code = (row.get("CFTC_Contract_Market_Code") or "").strip()
                            if cftc_code not in CONTRACT_MAP:
                                continue
                            name, symbol = CONTRACT_MAP[cftc_code]
                            try:
                                noncomm_long = int(float(row.get("NonComm_Positions_Long_All", 0)))
                                noncomm_short = int(float(row.get("NonComm_Positions_Short_All", 0)))
                                net = noncomm_long - noncomm_short
                                report_date = row.get("Report_Date_as_YYYY-MM-DD", "")
                                if cftc_code not in contract_data:
                                    contract_data[cftc_code] = []
                                contract_data[cftc_code].append({
                                    "name": name, "symbol": symbol,
                                    "net_noncomm": net, "date": report_date,
                                    "long": noncomm_long, "short": noncomm_short,
                                })
                            except (ValueError, TypeError):
                                continue

                        # Get latest + previous for weekly change
                        for cftc_code, entries in contract_data.items():
                            entries.sort(key=lambda x: x["date"], reverse=True)
                            if not entries:
                                continue
                            latest = entries[0]
                            prev_net = entries[1]["net_noncomm"] if len(entries) > 1 else latest["net_noncomm"]
                            net_change = latest["net_noncomm"] - prev_net

                            if latest["net_noncomm"] > 0:
                                signal, signal_color = "NET LONG", "#00CC44"
                            elif latest["net_noncomm"] < 0:
                                signal, signal_color = "NET SHORT", "#FF4444"
                            else:
                                signal, signal_color = "FLAT", "#888888"

                            results.append({
                                "name": latest["name"],
                                "symbol": latest["symbol"],
                                "net_noncomm": latest["net_noncomm"],
                                "net_change": net_change,
                                "date": latest["date"],
                                "signal": signal,
                                "signal_color": signal_color,
                            })
                if results:
                    break
            except Exception:
                continue

        return results if results else None
    except Exception as e:
        logger.error("CFTC COT fetch failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 7E: ECONOMIC SURPRISE INDEX (ESI PROXY)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_economic_surprise_index(fred_key=None):
    """Compute Economic Surprise Index from macro calendar actual vs forecast.
    
    For HIGH importance events with both actual and forecast populated,
    computes surprise_pct = (actual - forecast) / |forecast| * 100.
    Averages across major releases: CPI, NFP, PCE, GDP, Retail Sales, ISM.
    
    Zero new API calls — processes data from get_macro_calendar().
    """
    try:
        cal = get_macro_calendar(fred_key)
        if not cal:
            return None

        MARKET_MOVERS = ["cpi", "nonfarm", "payroll", "pce", "gdp", "retail sales", "ism"]
        items = []
        for ev in cal:
            if ev.get("importance") != "HIGH":
                continue
            actual_str = str(ev.get("actual", "")).strip().replace("%", "").replace(",", "")
            forecast_str = str(ev.get("forecast", "")).strip().replace("%", "").replace(",", "")
            if not actual_str or not forecast_str:
                continue
            try:
                actual = float(actual_str)
                forecast = float(forecast_str)
            except (ValueError, TypeError):
                continue
            if abs(forecast) < 0.001:
                continue

            name = ev.get("name", "")
            name_l = name.lower()
            is_mover = any(kw in name_l for kw in MARKET_MOVERS)
            surprise_pct = (actual - forecast) / abs(forecast) * 100

            items.append({
                "name": name,
                "date": str(ev.get("date", "")),
                "actual": actual,
                "forecast": forecast,
                "surprise_pct": round(surprise_pct, 2),
                "is_market_mover": is_mover,
            })

        if not items:
            return None

        # Average of market-mover surprises (or all if insufficient)
        mover_items = [i for i in items if i["is_market_mover"]]
        avg_pool = mover_items if len(mover_items) >= 2 else items
        avg_surprise = sum(i["surprise_pct"] for i in avg_pool) / len(avg_pool)

        if avg_surprise > 1.0:
            label, label_color = "BEATS", "#00CC44"
        elif avg_surprise < -1.0:
            label, label_color = "MISSES", "#FF4444"
        else:
            label, label_color = "IN LINE", "#FF8C00"

        return {
            "items": items[:10],
            "avg_surprise_pct": round(avg_surprise, 2),
            "label": label,
            "label_color": label_color,
        }
    except Exception as e:
        logger.error("Economic surprise index failed", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 8: GAMMA SQUEEZE SCANNER
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_gamma_squeeze_scanner():
    """Scan for gamma squeeze candidates: high short interest + high options volume."""
    import numpy as np
    if yf is None:
        return None

    # Universe of meme/squeeze-prone stocks + high SI names
    # FIX-01: Removed BBBY, WISH, GOEV — all delisted; yf.download returns empty data
    SCAN_UNIVERSE = [
        "GME", "AMC", "KOSS", "BB", "NOK", "PLTR", "SOFI",
        "RIVN", "LCID", "MARA", "RIOT", "COIN", "CVNA", "UPST",
        "SNOW", "DKNG", "SPCE", "BYND", "FUBO", "WKHS",
        "TLRY", "SNDL", "CLOV", "SKLZ", "RKT", "OPEN",
    ]

    try:
        # Bulk download for volume and price data
        data = yf.download(SCAN_UNIVERSE, period="30d", progress=False, threads=True)
        if data.empty:
            return []

        rows = []
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

                # Volume surge ratio
                vol_ratio = round(latest_vol / avg_vol_20d, 2) if avg_vol_20d > 0 else 0.0

                # Short interest data via yfinance info
                tk = get_yf_ticker(ticker)
                if tk is None:
                    continue
                info = tk.info or {}
                short_pct = _safe_float(info.get("shortPercentOfFloat", 0)) * 100
                short_ratio = _safe_float(info.get("shortRatio", 0))
                shares_short = _safe_int(info.get("sharesShort", 0))

                # Score: combine short interest + volume surge
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

                if squeeze_score < 2.0:
                    continue

                # Signal classification
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
            except (KeyError, IndexError) as e:
                continue

        rows.sort(key=lambda x: x["squeeze_score"], reverse=True)
        return rows[:15]
    except Exception as e:
        logger.error("Gamma squeeze scanner failed", extra={"error": str(e)})
        return []


# ════════════════════════════════════════════════════════════════════
# FEATURE 9: DYNAMIC EARNINGS CALENDAR (Finnhub)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_finnhub_earnings_calendar(finnhub_key, days_ahead=14):
    """Fetch upcoming earnings from Finnhub /calendar/earnings API."""
    if not finnhub_key:
        return None
    try:
        today = datetime.today().date()
        end = today + timedelta(days=days_ahead)
        data = _fetch_robust_json(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={
                "from": today.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "token": finnhub_key,
            },
            timeout=12,
        )
        earnings = data.get("earningsCalendar", [])
        if not earnings:
            return None

        rows = []
        for e in earnings:
            symbol = e.get("symbol", "")
            if not symbol or "." in symbol:  # Skip non-US
                continue
            rows.append({
                "ticker": symbol,
                "date": e.get("date", ""),
                "hour": e.get("hour", ""),  # bmo, amc, dmh
                "eps_estimate": e.get("epsEstimate"),
                "eps_actual": e.get("epsActual"),
                "revenue_estimate": e.get("revenueEstimate"),
                "revenue_actual": e.get("revenueActual"),
                "quarter": e.get("quarter"),
                "year": e.get("year"),
            })

        return sorted(rows, key=lambda x: x["date"]) if rows else None
    except requests.exceptions.RequestException as e:
        logger.error("Finnhub earnings calendar fetch failed", extra={"error": str(e)})
        return None
    except Exception as e:
        logger.error("Finnhub earnings calendar error", extra={"error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 10: OPTIONS-IMPLIED EXPECTED MOVE
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def get_expected_move(ticker):
    """Calculate options-implied expected move = ATM Call + Put premium / Spot."""
    if yf is None:
        return None
    try:
        tk = get_yf_ticker(ticker)
        if tk is None:
            return None

        fi = tk.fast_info
        price = getattr(fi, "last_price", None)
        if price is None or price <= 0:
            h = tk.history(period="1d")
            price = float(h["Close"].iloc[-1]) if not h.empty else None
        if price is None or price <= 0:
            return None

        exps = list(tk.options)
        if not exps:
            return None

        # Use nearest expiry
        exp = exps[0]
        chain = tk.option_chain(exp)
        if chain is None:
            return None

        calls, puts = chain.calls, chain.puts
        if calls.empty or puts.empty:
            return None

        # Find ATM strike
        calls["_dist"] = (calls["strike"] - price).abs()
        puts["_dist"] = (puts["strike"] - price).abs()
        atm_call = calls.nsmallest(1, "_dist")
        atm_put = puts.nsmallest(1, "_dist")

        if atm_call.empty or atm_put.empty:
            return None

        call_mid = (float(atm_call["bid"].iloc[0]) + float(atm_call["ask"].iloc[0])) / 2
        put_mid = (float(atm_put["bid"].iloc[0]) + float(atm_put["ask"].iloc[0])) / 2

        # If bid/ask is 0, use lastPrice
        if call_mid <= 0:
            call_mid = float(atm_call["lastPrice"].iloc[0])
        if put_mid <= 0:
            put_mid = float(atm_put["lastPrice"].iloc[0])

        expected_move_dollars = call_mid + put_mid
        expected_move_pct = round(expected_move_dollars / price * 100, 2)

        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        dte = max((exp_date - datetime.today().date()).days, 1)

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "expiry": exp,
            "dte": dte,
            "expected_move_dollars": round(expected_move_dollars, 2),
            "expected_move_pct": expected_move_pct,
            "call_premium": round(call_mid, 2),
            "put_premium": round(put_mid, 2),
            "atm_strike": float(atm_call["strike"].iloc[0]),
            "range_low": round(price - expected_move_dollars, 2),
            "range_high": round(price + expected_move_dollars, 2),
        }
    except Exception as e:
        logger.error("Expected move calculation failed", extra={"ticker": ticker, "error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 11: AI-POWERED GUIDANCE SUMMARIES
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_ai_earnings_summary(ticker, gemini_api_key, finnhub_key=None, newsapi_key=None):
    """Aggregate recent earnings news and summarize with Gemini AI."""
    if not gemini_api_key or genai is None:
        return None
    try:
        # Gather recent news
        news_items = get_stock_news(ticker, finnhub_key=finnhub_key, newsapi_key=newsapi_key)
        if not news_items:
            return None

        headlines = "\n".join([f"- {n['title']} ({n['source']}, {n['date']})" for n in news_items[:10]])

        # Get basic financial context
        q = yahoo_quote(ticker)
        price_ctx = f"Current price: ${q['price']:,.2f}, Change: {q['pct']:+.2f}%" if q else ""

        prompt = (
            f"You are a senior equity analyst. Analyze the following recent news headlines "
            f"for {ticker} and provide a concise earnings/guidance summary.\n\n"
            f"{price_ctx}\n\n"
            f"Recent Headlines:\n{headlines}\n\n"
            f"Provide:\n"
            f"1. GUIDANCE SENTIMENT (Bullish/Neutral/Bearish)\n"
            f"2. KEY THEMES (2-3 bullet points)\n"
            f"3. RISK FLAGS (if any)\n"
            f"4. CONSENSUS OUTLOOK (1 sentence)\n"
            f"Keep it under 200 words. Use plain text, no markdown."
        )

        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=512,
            ),
        )
        return {
            "ticker": ticker,
            "summary": response.text,
            "news_count": len(news_items),
        }
    except Exception as e:
        logger.error("AI earnings summary failed", extra={"ticker": ticker, "error": str(e)})
        return None


# ════════════════════════════════════════════════════════════════════
# FEATURE 12: VISUAL MARGIN EXPANSION CHART DATA
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800)
def get_margin_chart_data(ticker):
    """Get quarterly revenue + margin data for Plotly dual-axis chart."""
    fin = get_full_financials(ticker)
    if not fin:
        return None

    rows = []
    for q_str, data_item in sorted(fin.items()):
        rev = data_item.get("revenue")
        gm = data_item.get("gross_margin")
        om = data_item.get("op_margin")
        nm = data_item.get("net_margin")

        if rev is None:
            continue

        rows.append({
            "quarter": q_str,
            "revenue": rev,
            "revenue_b": round(rev / 1e9, 2),
            "gross_margin": round(gm, 1) if gm is not None else None,
            "op_margin": round(om, 1) if om is not None else None,
            "net_margin": round(nm, 1) if nm is not None else None,
        })

    return rows if rows else None
