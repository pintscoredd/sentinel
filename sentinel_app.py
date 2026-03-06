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
    import yfinance as yf
except ImportError:
    yf = None

# ── Logging Setup ──
logger = logging.getLogger("sentinel.data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS & ONLINE VARIANCE
# ════════════════════════════════════════════════════════════════════

class OnlineVariance:
    """Welford's Online Algorithm for O(1) running variance on tick streams."""
    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self.M2 = 0.0

    def update(self, new_value):
        self.count += 1
        delta = new_value - self.mean
        self.mean += delta / self.count
        delta2 = new_value - self.mean
        self.M2 += delta * delta2

    def variance(self):
        return self.M2 / self.count if self.count > 1 else 0.0


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
    """Helper to safely run async tasks in Streamlit threads."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


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

@st.cache_data(ttl=300)
def yahoo_quote(ticker):
    TICKER_MAP = {"DXY": "DX-Y.NYB", "$DXY": "DX-Y.NYB"}
    t = TICKER_MAP.get(ticker, ticker)
    try:
        tk = yf.Ticker(t)

        # fast_info gives live price during market hours
        fi = tk.fast_info
        price = getattr(fi, "last_price", None)
        prev  = getattr(fi, "previous_close", None)

        if price is None or prev is None:
            # Fallback to history if fast_info unavailable
            h = tk.history(period="5d")
            if h.empty: return None
            price = h["Close"].iloc[-1]
            prev  = h["Close"].iloc[-2] if len(h) > 1 else price

        price = float(price)
        prev  = float(prev)
        chg   = price - prev
        pct   = chg / prev * 100 if prev else 0.0

        # Volume from fast_info
        vol = int(getattr(fi, "three_month_average_volume", 0) or 0)
        try:
            h = tk.history(period="2d")
            if not h.empty:
                vol = int(h["Volume"].iloc[-1])
        except Exception:
            pass

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
        h = yf.Ticker("^IRX").history(period="5d")
        if not h.empty:
            return round(h["Close"].iloc[-1] / 100, 4)
    except Exception:
        pass
    return 0.045   # final fallback

async def _fetch_yahoo_quotes_async(tickers):
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, yahoo_quote, tkr) for tkr in tickers]
    return await asyncio.gather(*tasks, return_exceptions=True)

@st.cache_data(ttl=120)
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
        h = yf.Ticker("^VIX").history(period="5d")
        return round(h["Close"].iloc[-1], 2) if not h.empty else None
    except:
        return None

@st.cache_data(ttl=3600)
def vix_with_percentile():
    try:
        h = yf.Ticker("^VIX").history(period="1y")
        if h.empty or len(h) < 20:
            return None, None, None
        current = h["Close"].iloc[-1]
        pct_rank = (h["Close"] < current).mean() * 100   # percentile rank
        # Posture based on percentile
        if pct_rank < 30:   posture = "RISK-ON"
        elif pct_rank < 65: posture = "NEUTRAL"
        else:               posture = "RISK-OFF"
        return round(current, 2), round(pct_rank, 1), posture
    except Exception:
        return None, None, None

@st.cache_data(ttl=600)
def options_expiries(ticker):
    try:
        return list(yf.Ticker(ticker).options)
    except:
        return []

@st.cache_data(ttl=600)
def options_chain(ticker, expiry=None):
    try:
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps: return None, None, None
        exp = expiry if expiry and expiry in exps else exps[0]
        chain = t.option_chain(exp)
        cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
        c = chain.calls[[x for x in cols if x in chain.calls.columns]]
        p = chain.puts[[x for x in cols if x in chain.puts.columns]]
        return c, p, exp
    except:
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
        def _bs_delta(S, K, T, r, sigma, side):
            if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.5
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            return norm.cdf(d1) if side == "call" else norm.cdf(d1) - 1.0

        if current_price and current_price > 0 and "strike" in df.columns:
            df["_delta_proxy"] = df.apply(
                lambda r: abs(_bs_delta(current_price, r.get("strike", current_price), T_approx, r_risk_free, max(r.get("impliedVolatility", 0.2), 0.01), side)), axis=1
            )
        else:
            df["_delta_proxy"] = 0.5

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

def bs_price(S, K, T, r, sigma, side="call"):
    """Calculate theoretical option price using Black-Scholes."""
    try:
        # Prevent math domain errors on edge cases
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0: return 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if side == "call":
            p = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            p = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return max(p, 0.0)
    except Exception:
        return 0.0

def get_iv_newton(S, K, T, r, target_price, side="call"):
    """Newton-Raphson root solver to back out Implied Volatility from market price."""
    from scipy.optimize import newton
    if target_price <= 0 or S <= 0 or K <= 0 or T <= 0: return 0.0
    
    def objective(sigma):
        return bs_price(S, K, T, r, sigma, side) - target_price
        
    try:
        # Newton solver with an initial guess of 20% IV
        iv = newton(objective, x0=0.20, tol=1e-4, maxiter=50)
        return float(max(iv, 0.0))
    except Exception:
        # Fallback to 0 if solver fails to converge (e.g. deep OTM)
        return 0.0

def bs_greeks_engine(S, K, T, r, sigma, side="call"):
    """True Black-Scholes Greeks Engine computing Delta, Gamma, Theta locally for 'what-if' shifting."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return {"delta": 0.5 if side == "call" else -0.5, "gamma": 0.0, "theta": 0.0}
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        N_d1 = norm.cdf(d1)
        N_d2 = norm.cdf(d2)
        n_d1 = norm.pdf(d1)
        
        delta = N_d1 if side == "call" else N_d1 - 1.0
        gamma = n_d1 / (S * sigma * math.sqrt(T))
        
        theta_d1 = -(S * n_d1 * sigma) / (2 * math.sqrt(T))
        if side == "call":
            theta = (theta_d1 - r * K * math.exp(-r * T) * N_d2) / 365.0
        else:
            theta = (theta_d1 + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365.0
            
        return {"delta": round(delta, 4), "gamma": round(gamma, 6), "theta": round(theta, 4)}
    except Exception:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0}

@st.cache_data(ttl=21600)
def get_finra_short_volume(ticker):
    """Free Short Volume Data via FINRA/yfinance fallback."""
    try:
        t = yf.Ticker(ticker)
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
    """Statistical Arbitrage Screener using Engle-Granger Cointegration & OLS Half-Life."""
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
                
            # Engle-Granger Cointegration Test
            score, pvalue, _ = coint(df[t1], df[t2])
            
            # OLS for Hedge Ratio (Beta)
            Y = df[t1]
            X = sm.add_constant(df[t2])
            model = sm.OLS(Y, X).fit()
            beta = model.params.iloc[1]
            
            # Spread = Y - beta * X
            spread = df[t1] - beta * df[t2]
            mean_spread = spread.mean()
            std_spread = spread.std()
            z_score = (spread.iloc[-1] - mean_spread) / std_spread
            
            # Ornstein-Uhlenbeck Process for Half-Life
            spread_lag = spread.shift(1).dropna()
            spread_diff = spread.diff().dropna()
            lag_with_const = sm.add_constant(spread_lag)
            ou_model = sm.OLS(spread_diff, lag_with_const).fit()
            ou_lambda = -ou_model.params.iloc[1]
            half_life = np.log(2) / ou_lambda if ou_lambda > 0 else float('inf')
            
            signal = "Neutral"
            if z_score < -2: signal = "Long T1 / Short T2"
            elif z_score > 2: signal = "Short T1 / Long T2"
            elif z_score < -1: signal = "Leaning Long T1"
            elif z_score > 1: signal = "Leaning Short T1"
            
            results.append({
                "t1": t1, "t2": t2,
                "pvalue": round(float(pvalue), 4),
                "zscore": round(float(z_score), 2),
                "half_life": round(float(half_life), 1),
                "beta": round(float(beta), 3),
                "coint": pvalue < 0.05,
                "signal": signal
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

        # --- Signal 1: VIX Level (market volatility) ---
        v = yahoo_quote("^VIX")
        if v:
            vix = v["price"]
            # VIX 10=100 (extreme greed), VIX 40=0 (extreme fear), linear
            vix_score = max(0, min(100, 100 - (vix - 10) / 30 * 100))
            scores.append(("VIX", vix_score))

        # --- Signal 2: Market Momentum (SPY vs 125-day MA) ---
        try:
            h = yf.Ticker("SPY").history(period="7mo")
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
            t = yf.Ticker("SPY")
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

    if not role_map:
        try:
            officers = yf.Ticker(ticker).info.get("companyOfficers", [])
            for o in officers:
                name = str(o.get("name", "")).strip()
                title = str(o.get("title", "")).strip()
                if not name or not title: continue
                
                clean_name = name.upper().replace(".", "").replace(",", "")
                for pfx in ["MR ", "MS ", "MRS ", "DR ", "PROF "]:
                    if clean_name.startswith(pfx):
                        clean_name = clean_name[len(pfx):].strip()
                role_map[clean_name] = title
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
            t = yf.Ticker(tkr)
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
                    ed = ed[0] if isinstance(ed, list) else ed
                    eps = cal.get("EPS Estimate", None)
                else:
                    continue
                if ed is None: continue
                rows.append({
                    "Ticker": tkr,
                    "Company": info.get("shortName", tkr)[:22],
                    "EarningsDate": pd.to_datetime(ed).date(),
                    "EPS Est": round(float(eps), 2) if eps else None,
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
            if calculated_iv > 0:
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
            
        con = duckdb.connect(database=':memory:')
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
        h = yf.Ticker("^VIX").history(period="5d")
        if not h.empty: result["vix"] = round(h["Close"].iloc[-1], 2)
    except Exception: pass
    try:
        h9 = yf.Ticker("^VIX9D").history(period="5d")
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
        info = yf.Ticker(ticker).info
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
        t = yf.Ticker(ticker)
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
        info = yf.Ticker(ticker).info if yf else {}
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

            # --- TRUE EDGE: deviation between raw and liquidity-adjusted ---
            # In illiquid markets the crowd is unreliable → adj_prob pulls toward 50%
            # The "edge" is how much the raw price overstates the true probability
            raw_edge    = abs(raw_yes - 0.5)           # how extreme is raw
            adj_edge    = abs(adj_prob - 0.5)           # how extreme after discount
            crowd_error = raw_edge - adj_edge           # error from overcrowding

            # Bet signal: only flag when crowd_error is meaningful
            # High crowd_error + illiquid = fade opportunity
            # High adj_edge + liquid = real momentum (ride)
            vol24_weight = math.log1p(vol24) / math.log1p(1_000_000) if vol24 > 0 else 0.0
            vol24_weight = min(vol24_weight, 1.0)

            # Mispricing score: high when crowd_error is large AND there's real activity
            mispricing_score = round(
                crowd_error * vol24_weight * (1.0 - liq_score + 0.1) * (0.5 + activity_ratio),
                5
            )

            # Spread for display
            spread_str = ""
            best_bid = _safe_float(m.get("bestBid", 0))
            best_ask = _safe_float(m.get("bestAsk", 0)) or _safe_float(m.get("bestOffer", 0))
            if best_bid > 0 and best_ask > 0:
                spread = best_ask - best_bid
                spread_str = f"{spread*100:.1f}¢"

            # Signal: fade overcrowded thin markets, ride confirmed deep markets
            if liq_score < 0.40 and raw_yes > 0.70 and crowd_error > 0.05:
                signal, signal_color = "FADE YES", "#FF4444"
            elif liq_score < 0.40 and raw_yes < 0.30 and crowd_error > 0.05:
                signal, signal_color = "FADE NO", "#00CC44"
            elif liq_score >= 0.70 and raw_yes > 0.65:
                signal, signal_color = "RIDE YES", "#00CC44"
            elif liq_score >= 0.70 and raw_yes < 0.35:
                signal, signal_color = "RIDE NO", "#FF4444"
            else:
                signal, signal_color = "MONITOR", "#FF8C00"

            results.append({
                "title": title[:80], "url": m.get("slug", ""),
                "raw_yes": round(raw_yes * 100, 1),
                "adj_yes": round(adj_prob * 100, 1),
                "liq_score": liq_score,
                "reliability": round(reliability, 2),
                "edge": round(crowd_error, 3),   # now: true crowd error
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
        url = "https://api.gdeltproject.org/api/v2/geo/geo?query=(strike%20OR%20attack%20OR%20bombing%20OR%20explosion)&mode=pointdata&format=geojson&timespan=1h"
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
_YAHOO_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

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
                # Using VWAP for accumulation mathematically handles intraday volatility
                ticker_flows[_pd.Timestamp.fromtimestamp(ts).normalize()] = round((volume * vwap * direction * 0.10) / 1e6, 2)
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
                hist = yf.Ticker(ticker).history(period="60d")
                if hist is None or hist.empty or len(hist) < 2: continue
                prev_close = hist["Close"].shift(1)
                vwap = (hist["High"] + hist["Low"] + hist["Close"]) / 3.0
                direction = (hist["Close"] - prev_close).apply(lambda x: 1.0 if x >= 0 else -1.0)
                all_data[ticker] = ((hist["Volume"] * vwap * direction * 0.10) / 1e6).iloc[1:]
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
