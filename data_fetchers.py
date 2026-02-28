#!/usr/bin/env python3
"""SENTINEL — Data Fetchers Module
All @st.cache_data API functions, data utilities, and helpers.
"""

import streamlit as st
import requests
import pandas as pd
import json
import math
import re
from datetime import datetime, timedelta, time as dtime
import pytz

try:
    import yfinance as yf
except ImportError:
    yf = None

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

# ════════════════════════════════════════════════════════════════════
# MARKET STATUS
# ════════════════════════════════════════════════════════════════════

def is_market_open():
    """Check US equity market status based on current Eastern Time."""
    ET = pytz.timezone("US/Eastern")
    now = datetime.now(ET)
    wd = now.weekday()  # 0=Mon, 6=Sun
    t = now.time()
    open_t, close_t = dtime(9, 30), dtime(16, 0)
    if wd >= 5:
        return "CLOSED", "#FF4444", "Weekend"
    if open_t <= t <= close_t:
        return "OPEN", "#00CC44", "Regular Hours"
    elif dtime(4, 0) <= t < open_t:
        return "PRE-MARKET", "#FF8C00", "Pre-Market"
    elif dtime(16, 0) < t <= dtime(20, 0):
        return "AFTER-HOURS", "#FF8C00", "After-Hours"
    else:
        return "CLOSED", "#FF4444", "Markets Closed"

# ════════════════════════════════════════════════════════════════════
# YAHOO FINANCE
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def yahoo_quote(ticker):
    TICKER_MAP = {"DXY": "DX-Y.NYB", "$DXY": "DX-Y.NYB"}
    t = TICKER_MAP.get(ticker, ticker)
    try:
        h = yf.Ticker(t).history(period="5d")
        if h.empty: return None
        price = h["Close"].iloc[-1]
        prev = h["Close"].iloc[-2] if len(h) > 1 else price
        chg = price - prev
        pct = chg / prev * 100
        vol = int(h["Volume"].iloc[-1]) if "Volume" in h.columns else 0
        return {"ticker": ticker, "price": round(price, 2), "change": round(chg, 2),
                "pct": round(pct, 2), "volume": vol}
    except:
        return None

@st.cache_data(ttl=120)
def get_futures():
    """Fetch key futures contracts"""
    FUTURES = [
        ("ES=F", "S&P 500 Futures"), ("NQ=F", "Nasdaq 100 Futures"), ("YM=F", "Dow Jones Futures"),
        ("RTY=F", "Russell 2000 Futures"), ("ZN=F", "10-Year Treasury Bond"), ("CL=F", "WTI Crude Oil"),
        ("GC=F", "Gold Futures"), ("SI=F", "Silver Futures"), ("NG=F", "Natural Gas"),
        ("ZW=F", "Wheat Futures"), ("ZC=F", "Corn Futures"), ("DX=F", "US Dollar Index"),
    ]
    rows = []
    for ticker, name in FUTURES:
        try:
            h = yf.Ticker(ticker).history(period="5d")
            if h.empty: continue
            price = h["Close"].iloc[-1]
            prev = h["Close"].iloc[-2] if len(h) > 1 else price
            chg = price - prev
            pct = chg / prev * 100
            rows.append({"ticker": ticker, "name": name, "price": round(price, 2),
                         "change": round(chg, 2), "pct": round(pct, 2)})
        except:
            pass
    return rows

@st.cache_resource(ttl=300)
def get_heatmap_data():
    """Fetch S&P sector heatmap data — concurrent batched fetching."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
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
    all_jobs = [(sector, tkr) for sector, tickers in SECTOR_STOCKS.items() for tkr in tickers]
    rows = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(yahoo_quote, tkr): (sector, tkr) for sector, tkr in all_jobs}
        for f in as_completed(futures):
            sector, tkr = futures[f]
            try:
                q = f.result()
                if q:
                    rows.append({"ticker": tkr, "sector": sector, "pct": q["pct"],
                                 "price": q["price"], "change": q["change"]})
            except Exception:
                pass
    return rows

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

@st.cache_data(ttl=600)
def options_expiries(ticker):
    """Get all available options expiry dates"""
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
        c = chain.calls[[x for x in cols if x in chain.calls.columns]].head(26)
        p = chain.puts[[x for x in cols if x in chain.puts.columns]].head(26)
        return c, p, exp
    except:
        return None, None, None


def score_options_chain(calls_df, puts_df, current_price, vix=None):
    """Adaptive options scoring engine.

    1. Trims 13 deep OTM/ITM strikes (furthest from current price).
    2. Scores each contract: S = (norm_VOI * w1) + (IV_pct * w2) - (|delta_proxy - 0.5| * w3)
    3. Adapts weights based on VIX regime.
    4. Returns dict with 'top_calls' (2), 'top_puts' (2), 'unusual' (single highest V/OI).
    """
    import pandas as pd

    result = {"top_calls": [], "top_puts": [], "unusual": None}
    if calls_df is None or puts_df is None:
        return result
    if calls_df.empty and puts_df.empty:
        return result

    # ── Adaptive Weights ──
    w1, w2, w3 = 0.40, 0.30, 0.30
    vix_val = float(vix) if vix is not None else 20.0
    if vix_val > 25:
        # High-vol regime: prioritize directional certainty (delta)
        w3 += 0.15
        w1 -= 0.075
        w2 -= 0.075
    elif vix_val < 15:
        # Low-vol regime: prioritize unusual volume flow
        w1 += 0.15
        w2 -= 0.075
        w3 -= 0.075

    def _score_side(df, side):
        if df is None or df.empty:
            return []
        df = df.copy()
        # Ensure numeric columns
        for col in ["strike", "volume", "openInterest", "impliedVolatility"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # ── Trim deep OTM/ITM: keep strikes nearest to current_price ──
        if current_price and "strike" in df.columns and len(df) > 13:
            df["_dist"] = (df["strike"] - current_price).abs()
            df = df.nsmallest(len(df) - 13, "_dist").drop(columns=["_dist"])

        if df.empty:
            return []

        # ── Volume / OI ratio ──
        df["_voi"] = df.apply(
            lambda r: r.get("volume", 0) / max(r.get("openInterest", 1), 1), axis=1
        )
        max_voi = df["_voi"].max()
        df["_norm_voi"] = df["_voi"] / max_voi if max_voi > 0 else 0

        # ── IV Percentile within this side ──
        iv_col = "impliedVolatility"
        if iv_col in df.columns:
            iv_min, iv_max = df[iv_col].min(), df[iv_col].max()
            iv_range = iv_max - iv_min
            df["_iv_pct"] = (df[iv_col] - iv_min) / iv_range if iv_range > 0 else 0.5
        else:
            df["_iv_pct"] = 0.5

        # ── Delta proxy from moneyness ──
        if current_price and current_price > 0 and "strike" in df.columns:
            df["_delta_proxy"] = 1.0 - (df["strike"] - current_price).abs() / current_price
            df["_delta_proxy"] = df["_delta_proxy"].clip(0, 1)
        else:
            df["_delta_proxy"] = 0.5

        # ── Score ──
        df["_score"] = (
            df["_norm_voi"] * w1
            + df["_iv_pct"] * w2
            - (df["_delta_proxy"] - 0.5).abs() * w3
        )

        # Build output rows
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

    # Top 2 per side by score
    call_rows.sort(key=lambda r: r["score"], reverse=True)
    put_rows.sort(key=lambda r: r["score"], reverse=True)
    result["top_calls"] = call_rows[:2]
    result["top_puts"] = put_rows[:2]

    # Unusual: single highest V/OI across entire chain
    all_rows = call_rows + put_rows
    if all_rows:
        result["unusual"] = max(all_rows, key=lambda r: r["voi"])

    return result

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
    """Get top gainers and losers from S&P 500 components (batched for performance)."""
    # Core S&P 500 — grouped by sector, 500 total
    UNIVERSE = [
        # Mega-cap tech
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","ORCL","CRM",
        "AMD","INTC","QCOM","TXN","ADI","AMAT","LRCX","KLAC","MRVL","SNPS","CDNS",
        "ADBE","INTU","NOW","PANW","CRWD","ZS","FTNT","ANSS","EPAM",
        # Financials
        "JPM","BAC","WFC","GS","MS","BLK","C","AXP","COF","PGR",
        "ICE","CME","SPGI","MCO","V","MA","PYPL","FIS","FISV","WEX",
        "TRV","HIG","MET","PRU","AFL","AIG","CB","ALL","LNC","GL",
        # Healthcare
        "UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","PFE","DHR","BMY",
        "ISRG","GILD","MDT","CVS","CI","HUM","ELV","CNC","MOH","ALGN",
        "VRTX","REGN","BIIB","ILMN","IDXX","IQV","PKI","ZBH","BSX","SYK",
        # Consumer Discretionary
        "AMZN","TSLA","HD","MCD","NKE","LOW","BKNG","TJX","SBUX","MAR",
        "TGT","ROST","ORLY","DHI","LEN","PHM","NVR","MTH","MHO","GRMN",
        "F","GM","RIVN","LCID","APTV","BWA","LEA","MGA","ALV","VC",
        # Consumer Staples
        "WMT","PG","KO","PEP","PM","MO","CL","GIS","KHC","KMB",
        "SYY","HSY","MKC","CAG","CPB","SJM","HRL","LW","K","TSN",
        # Industrials
        "GE","RTX","CAT","HON","UNP","LMT","DE","WM","NSC","ITW",
        "ETN","PH","GD","BA","FDX","UPS","EXPD","CHRW","XPO","JBHT",
        "MMM","EMR","ROK","AME","GNRC","TT","IR","IEX","FAST","GWW",
        # Energy
        "XOM","CVX","COP","SLB","EOG","PSX","MPC","OXY","VLO","HAL",
        "DVN","BKR","FANG","APA","MRO","HES","EQT","CTRA","AR","LNG",
        # Materials
        "LIN","APD","ECL","SHW","NEM","FCX","NUE","VMC","ALB","MOS",
        "CF","FMC","IFF","PPG","RPM","SEE","SON","PKG","IP","WRK",
        # Real Estate
        "PLD","AMT","CCI","EQIX","PSA","SPG","WELL","O","DLR","AVB",
        "EQR","VTR","BXP","ARE","KIM","REG","FRT","MAC","WPM","UDR",
        # Utilities
        "NEE","DUK","SO","AEP","D","EXC","PCG","SRE","XEL","CEG",
        "ES","ETR","PPL","WEC","AWK","DTE","AES","NI","CMS","CNP",
        # Communication Services
        "GOOGL","META","DIS","NFLX","T","VZ","CMCSA","TMUS","EA","TTWO",
        "CHTR","FOXA","NWSA","IPG","OMC","PARA","WBD","LYV","ZM","MTCH",
        # More large-caps
        "BRK-B","LLY","COST","TMO","ACN","MCD","HON","GE","ABBV","TXN",
        "AMGN","NEE","BMY","GILD","MDT","SBUX","ISRG","SPGI","BLK","AXP",
    ]
    # Deduplicate while preserving order
    seen = set()
    UNIVERSE = [x for x in UNIVERSE if not (x in seen or seen.add(x))]

    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futs = {pool.submit(yahoo_quote, tkr): tkr for tkr in UNIVERSE}
        for f in as_completed(futs):
            try:
                q = f.result()
                if q: results.append(q)
            except Exception:
                pass

    sorted_q = sorted(results, key=lambda x: x["pct"], reverse=True)
    return sorted_q[:10], sorted_q[-10:]

def calc_stock_fear_greed():
    """Calculate stock market fear & greed from VIX + momentum"""
    try:
        v = yahoo_quote("^VIX")
        spy = yahoo_quote("SPY")
        if not v: return None, None
        vix = v["price"]
        vix_score = max(0, min(100, 100 - (vix - 10) / 30 * 100))
        mom_score = 50
        if spy:
            h = yf.Ticker("SPY").history(period="3mo")
            if not h.empty and len(h) > 60:
                current = h["Close"].iloc[-1]
                ma60 = h["Close"].iloc[-60:].mean()
                mom_score = 75 if current > ma60 * 1.02 else (25 if current < ma60 * 0.98 else 50)
        score = int(vix_score * 0.6 + mom_score * 0.4)
        if score >= 75: label = "Extreme Greed"
        elif score >= 55: label = "Greed"
        elif score >= 45: label = "Neutral"
        elif score >= 25: label = "Fear"
        else: label = "Extreme Fear"
        return score, label
    except:
        return None, None

def market_snapshot_str():
    try:
        qs = multi_quotes(["SPY", "QQQ", "DX-Y.NYB", "GLD", "BTC-USD"])
        parts = [f"{q['ticker']}: ${q['price']:,.2f} ({q['pct']:+.2f}%)" for q in qs]
        v = vix_price()
        if v: parts.append(f"VIX: {v}")
        return " | ".join(parts)
    except:
        return ""

# ════════════════════════════════════════════════════════════════════
# FRED
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def fred_series(series_id, key, limit=36):
    if not key: return None
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": key, "sort_order": "desc",
                    "limit": limit, "file_type": "json"}, timeout=10)
        df = pd.DataFrame(r.json().get("observations", []))
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
    """Fetch from EVENTS endpoint — has correct slugs for URLs"""
    try:
        r = requests.get("https://gamma-api.polymarket.com/events",
            params={"limit": limit, "order": "volume", "ascending": "false", "active": "true"}, timeout=10)
        return r.json()
    except:
        return []

@st.cache_data(ttl=300)
def polymarket_markets(limit=60):
    try:
        r = requests.get("https://gamma-api.polymarket.com/markets",
            params={"limit": limit, "order": "volume24hr", "ascending": "false", "active": "true"}, timeout=10)
        return r.json()
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
    """Parse a Polymarket field that may be a JSON string or already a list."""
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
        d = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except:
        return None, None

@st.cache_data(ttl=600)
def crypto_markets():
    import time
    for attempt in range(3):
        try:
            r = requests.get("https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 20,
                        "page": 1, "price_change_percentage": "24h"}, timeout=15)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return data
            return []
        except Exception:
            if attempt < 2:
                time.sleep(1)
            continue
    return []

@st.cache_data(ttl=600)
def crypto_global():
    try:
        return requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json().get("data", {})
    except:
        return {}

# ════════════════════════════════════════════════════════════════════
# NEWS
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def gdelt_news(query, max_rec=15):
    """Fetch from GDELT with multiple endpoint fallbacks"""
    endpoints = [
        {"url": "https://api.gdeltproject.org/api/v2/doc/doc",
         "params": {"query": query + " sourcelang:english", "mode": "artlist",
                    "maxrecords": max_rec, "format": "json", "timespan": "72h"}},
        {"url": "https://api.gdeltproject.org/api/v2/doc/doc",
         "params": {"query": query + " sourcelang:english", "mode": "artlist",
                    "maxrecords": max_rec, "format": "json", "timespan": "168h"}},
    ]
    for ep in endpoints:
        try:
            r = requests.get(ep["url"], params=ep["params"], timeout=18)
            if r.status_code != 200: continue
            data = r.json()
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
        r = requests.get("https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt",
                    "pageSize": 10, "apiKey": key}, timeout=10)
        return r.json().get("articles", [])
    except:
        return []

@st.cache_data(ttl=300)
def finnhub_news(key):
    if not key: return []
    try:
        return requests.get("https://finnhub.io/api/v1/news",
            params={"category": "general", "token": key}, timeout=10).json()[:12]
    except:
        return []

@st.cache_data(ttl=600)
def finnhub_insider(ticker, key):
    if not key: return []
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": ticker, "token": key}, timeout=10)
        return r.json().get("data", [])[:15]
    except:
        return []

@st.cache_data(ttl=1800)
def finnhub_officers(ticker, key):
    """Fetch company executives from Finnhub /stock/executive endpoint"""
    if not key: return {}
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/executive",
            params={"symbol": ticker, "token": key}, timeout=10)
        data = r.json()
        role_map = {}
        for o in data.get("executive", []) or []:
            name = str(o.get("name", "")).strip()
            title = str(o.get("position", "") or o.get("title", "") or "")
            if not name or not title: continue
            # Store with multiple name formats for fuzzy matching
            name_upper = name.upper()
            role_map[name_upper] = title
            # Also store "LAST FIRST" format since Finnhub insider uses that
            parts = name.split()
            if len(parts) >= 2:
                # "Colette Kress" → "KRESS COLETTE"
                last_first = (parts[-1] + " " + " ".join(parts[:-1])).upper()
                role_map[last_first] = title
                # Also try just "LAST FIRST_INITIAL"
                role_map[(parts[-1] + " " + parts[0]).upper()] = title
        return role_map
    except:
        return {}

# ════════════════════════════════════════════════════════════════════
# EARNINGS
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def get_earnings_calendar(today_str=None):
    """Fetch upcoming earnings. today_str acts as a cache-bust key — call with
    datetime.now().strftime('%Y-%m-%d') so the cache resets every new day."""
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
                    "Sector": info.get("sector", "—"),  # Full sector — no truncation
                })
        except:
            pass
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows).dropna(subset=["EarningsDate"]).sort_values("EarningsDate")

# ════════════════════════════════════════════════════════════════════
# 0DTE — ALPACA REST API (options chain, Greeks, stock snapshots)
# yfinance ONLY for ^VIX and ^VIX9D
# ════════════════════════════════════════════════════════════════════

def _alpaca_headers():
    """Build Alpaca auth headers from st.secrets."""
    try:
        return {
            "APCA-API-KEY-ID": st.secrets["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": st.secrets["ALPACA_SECRET_KEY"],
            "Accept": "application/json",
        }
    except (KeyError, FileNotFoundError):
        return None


def is_0dte_market_open():
    """Check if within regular US equity hours (9:30-16:00 ET, weekday).
    Returns (is_open: bool, status_msg: str).
    """
    ET = pytz.timezone("US/Eastern")
    now = datetime.now(ET)
    wd = now.weekday()
    t = now.time()
    if wd >= 5:
        return False, "Weekend — markets closed"
    if dtime(9, 30) <= t <= dtime(16, 0):
        return True, f"Market OPEN — {now.strftime('%H:%M ET')}"
    elif dtime(4, 0) <= t < dtime(9, 30):
        return False, f"Pre-market — opens 9:30 ET ({now.strftime('%H:%M ET')} now)"
    elif dtime(16, 0) < t <= dtime(20, 0):
        return False, f"After-hours — closed at 16:00 ET ({now.strftime('%H:%M ET')} now)"
    else:
        return False, "Markets closed — overnight"


@st.cache_data(ttl=30)
def get_stock_snapshot(symbol="SPY"):
    """Fetch latest stock snapshot from Alpaca (spot, native VWAP, daily bar).
    GET https://data.alpaca.markets/v2/stocks/{symbol}/snapshot
    """
    headers = _alpaca_headers()
    if not headers:
        return None
    try:
        url = f"https://data.alpaca.markets/v2/stocks/{symbol}/snapshot"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
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
    """Get SPX spot directly from ^GSPC (accurate), VWAP/range from SPY×10 (Alpaca)."""
    spy_snap = get_stock_snapshot("SPY")
    # Prefer real SPX price from Yahoo Finance to avoid SPY tracking-error offset
    try:
        spx_q = yahoo_quote("^GSPC")
        spx_price = round(spx_q["price"], 2) if spx_q and spx_q.get("price", 0) > 0 else None
    except Exception:
        spx_price = None

    if spy_snap:
        # Use actual SPX for spot; SPY×10 for intraday levels (VWAP, range)
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
    """Parse strike from OCC symbol. Last 8 chars = strike * 1000."""
    try:
        return int(sym[-8:]) / 1000.0
    except Exception:
        return 0.0


def _parse_type_from_symbol(sym):
    """Parse call/put from OCC symbol (C or P after the date)."""
    try:
        for i, ch in enumerate(sym):
            if ch in ("C", "P") and i > 3:
                return "call" if ch == "C" else "put"
        return "unknown"
    except Exception:
        return "unknown"


@st.cache_resource(ttl=30)
def fetch_0dte_chain(underlying="SPY"):
    """Fetch nearest options chain with Greeks from Alpaca snapshots.
    Gets nearest active expiry first, then fetches snapshots.
    Filters to strikes within [0.98S : 1.02S]. Returns (chain_list, status).
    """
    headers = _alpaca_headers()
    if not headers:
        return [], "No Alpaca API keys configured"

    snap = get_stock_snapshot(underlying)
    if not snap or snap["price"] <= 0:
        return [], "Could not fetch spot price"

    spot = snap["price"]
    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d")

    # 1. Find nearest active expiration date
    try:
        url_contracts = "https://paper-api.alpaca.markets/v2/options/contracts"
        params_c = {"underlying_symbols": underlying, "status": "active", "limit": 1000}
        rc = requests.get(url_contracts, headers=headers, params=params_c, timeout=10)
        if rc.status_code != 200:
            return [], f"Alpaca API error (contracts): {rc.status_code}"
        
        c_data = rc.json()
        dates = []
        for c in c_data.get("option_contracts", []):
            d = c.get("expiration_date")
            if d and d >= today_str:
                dates.append(d)
        
        if not dates:
            return [], "No active option contracts found"
            
        target_expiry = sorted(list(set(dates)))[0]
    except Exception as e:
        return [], f"Error locating expiry: {str(e)}"

    # 2. Fetch snapshots for the target expiry
    try:
        url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{underlying}"
        params = {"feed": "indicative", "limit": 250, "expiration_date": target_expiry}
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return [], f"Alpaca API error (snapshots): {r.status_code}"

        data = r.json()
        snapshots = data.get("snapshots", {})

        while data.get("next_page_token"):
            params["page_token"] = data["next_page_token"]
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            snapshots.update(data.get("snapshots", {}))

        chain = []
        lower_bound, upper_bound = spot * 0.98, spot * 1.02

        for sym, snap_data in snapshots.items():
            greeks = snap_data.get("greeks", {})
            quote = snap_data.get("latestQuote", {})
            trade = snap_data.get("latestTrade", {})
            strike = _parse_strike_from_symbol(sym)
            opt_type = _parse_type_from_symbol(sym)

            if strike <= 0 or strike < lower_bound or strike > upper_bound:
                continue

            bid = _safe_float(quote.get("bp"))
            ask = _safe_float(quote.get("ap"))
            mid = round((bid + ask) / 2, 2) if (bid + ask) > 0 else _safe_float(trade.get("p"))

            chain.append({
                "symbol": sym, "strike": strike, "type": opt_type,
                "bid": bid, "ask": ask, "mid": mid,
                "last": _safe_float(trade.get("p")),
                "iv": _safe_float(snap_data.get("impliedVolatility")),
                "delta": _safe_float(greeks.get("delta")),
                "gamma": _safe_float(greeks.get("gamma")),
                "theta": _safe_float(greeks.get("theta")),
                "vega": _safe_float(greeks.get("vega")),
                "oi": int(_safe_float(snap_data.get("openInterest", 0))),
                "volume": int(_safe_float(trade.get("s", 0))),
            })

        chain.sort(key=lambda x: x["strike"])
        return chain, "OK"
    except Exception as e:
        return [], f"Error: {str(e)}"


def compute_gex_profile(chain, spot):
    """GEX at strike K = OI * gamma * S^2 * contract_size * 0.01.
    Calls +, Puts -. Returns {strike: $M}.
    contract_size=100, notional_pct=0.01 → net multiplier = 1 (not 100).
    """
    gex = {}
    if spot <= 0:
        return gex
    for opt in chain:
        k = opt["strike"]
        raw_gex = opt.get("oi", 0) * abs(opt.get("gamma", 0)) * (spot ** 2)
        sign = 1.0 if opt["type"] == "call" else -1.0
        gex[k] = gex.get(k, 0) + sign * raw_gex / 1_000_000
    return dict(sorted(gex.items()))


def find_gamma_flip(gex_profile):
    """Strike where GEX flips from negative to positive (dealer hedging pivot)."""
    if not gex_profile:
        return None
    strikes = sorted(gex_profile.keys())
    for i in range(1, len(strikes)):
        if gex_profile[strikes[i - 1]] <= 0 and gex_profile[strikes[i]] > 0:
            return strikes[i]
    vals = list(gex_profile.values())
    return strikes[0] if all(v >= 0 for v in vals) else strikes[-1]


def compute_max_pain(chain):
    """O(N) prefix-sum max pain: argmin_K Σ(OI × |K-strike|)."""
    if not chain:
        return None
    strikes = sorted(set(opt["strike"] for opt in chain))
    if not strikes:
        return None
    call_oi, put_oi = {}, {}
    for opt in chain:
        k = opt["strike"]
        if opt["type"] == "call":
            call_oi[k] = call_oi.get(k, 0) + opt.get("oi", 0)
        else:
            put_oi[k] = put_oi.get(k, 0) + opt.get("oi", 0)

    # Baseline pain at strikes[0]
    s0 = strikes[0]
    pain = 0
    for k in strikes:
        c = call_oi.get(k, 0)
        p = put_oi.get(k, 0)
        if s0 > k:
            pain += c * (s0 - k)
        if s0 < k:
            pain += p * (k - s0)

    min_pain = pain
    mp_strike = s0

    # Running tallies: cumulative call OI to the left, put OI to the right
    cum_call_left = call_oi.get(s0, 0)   # calls at or below current sp
    total_put = sum(put_oi.get(k, 0) for k in strikes)
    cum_put_left = put_oi.get(s0, 0)     # puts at or below current sp
    # put_right = total_put - cum_put_left

    for i in range(1, len(strikes)):
        gap = strikes[i] - strikes[i - 1]
        # Moving sp up by 'gap':
        #   All calls at strikes <= sp(i-1) now cost +gap more each → +gap * cum_call_left
        #   All puts at strikes > sp(i-1) now cost -gap less each  → -gap * (total_put - cum_put_left)
        put_right = total_put - cum_put_left
        pain += gap * cum_call_left - gap * put_right

        if pain < min_pain:
            min_pain = pain
            mp_strike = strikes[i]

        # Update running tallies for the current strike
        cum_call_left += call_oi.get(strikes[i], 0)
        cum_put_left += put_oi.get(strikes[i], 0)

    return mp_strike


def compute_pcr(chain):
    """Put/Call ratio from total put OI / total call OI."""
    call_oi = sum(o.get("oi", 0) for o in chain if o["type"] == "call")
    put_oi = sum(o.get("oi", 0) for o in chain if o["type"] == "put")
    return round(put_oi / call_oi, 2) if call_oi > 0 else None


# ════════════════════════════════════════════════════════════════════
# CBOE GEX — Full option surface (all expirations, all strikes)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def fetch_cboe_gex(ticker="SPX"):
    """Fetch full option surface from CBOE delayed quotes API.
    Returns (spot_price: float, option_df: DataFrame | None).
    Tries underscore-prefix URL first (required for index tickers like SPX/NDX).
    """
    urls = [
        f"https://cdn.cboe.com/api/global/delayed_quotes/options/_{ticker}.json",
        f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                continue
            raw = pd.DataFrame.from_dict(r.json())
            spot = float(raw.loc["current_price", "data"])
            opts = pd.DataFrame(raw.loc["options", "data"])

            # Parse option symbol → type, strike, expiration
            opts["type"] = opts["option"].str.extract(r"\d([A-Z])\d")
            opts["strike"] = opts["option"].str.extract(r"\d[A-Z](\d+)\d\d\d").astype(float)
            opts["expiration"] = pd.to_datetime(
                opts["option"].str.extract(r"[A-Z](\d+)")[0], format="%y%m%d"
            )

            for col in ("gamma", "open_interest", "iv", "delta", "theta", "vega"):
                if col in opts.columns:
                    opts[col] = pd.to_numeric(opts[col], errors="coerce").fillna(0)

            return spot, opts
        except Exception:
            continue
    return None, None


def compute_cboe_gex_profile(spot, option_df, expiry_limit_days=365, strike_pct=0.05):
    """Compute GEX-by-strike from CBOE surface.

    Args:
        spot: SPX spot price
        option_df: DataFrame from fetch_cboe_gex
        expiry_limit_days: max days to expiration to include
        strike_pct: ±% band around spot (default 0.05 = ±5%)

    Returns:
        dict {spy_key: gex_millions}  (keys = SPX/10 for chart compat)
    """
    if option_df is None or option_df.empty or spot <= 0:
        return {}

    df = option_df.copy()
    cutoff = pd.Timestamp("today") + pd.Timedelta(days=expiry_limit_days)
    lo, hi = spot * (1 - strike_pct), spot * (1 + strike_pct)

    df = df[
        (df["expiration"] <= cutoff)
        & (df["strike"] >= lo)
        & (df["strike"] <= hi)
        & (df["gamma"] > 0)
        & (df["open_interest"] > 0)
    ]

    if df.empty:
        return {}

    # Correct formula: spot * gamma * OI * 100 * spot * 0.01 = spot² × gamma × OI
    df = df.copy()
    df["gex"] = spot * df["gamma"] * df["open_interest"] * 100 * spot * 0.01
    df["gex"] = df.apply(lambda r: -r["gex"] if r["type"] == "P" else r["gex"], axis=1)

    by_strike = df.groupby("strike")["gex"].sum() / 1_000_000
    # Return as spy-scale keys (SPX/10) for chart compat with render_0dte_gex_chart
    return {k / 10: v for k, v in by_strike.items()}


def compute_cboe_total_gex(spot, option_df):
    """Total net notional GEX in $Bn from full CBOE surface."""
    if option_df is None or option_df.empty or spot <= 0:
        return None
    df = option_df.copy()
    df["gex"] = spot * df["gamma"] * df["open_interest"] * 100 * spot * 0.01
    df["gex"] = df.apply(lambda r: -r["gex"] if r["type"] == "P" else r["gex"], axis=1)
    return round(df["gex"].sum() / 1_000_000_000, 4)


def compute_cboe_pcr(option_df):
    """Put/Call Open Interest ratio from full CBOE surface."""
    if option_df is None or option_df.empty:
        return None
    if "type" not in option_df.columns or "open_interest" not in option_df.columns:
        return None
    call_oi = option_df[option_df["type"] == "C"]["open_interest"].sum()
    put_oi  = option_df[option_df["type"] == "P"]["open_interest"].sum()
    return round(put_oi / call_oi, 2) if call_oi > 0 else None


@st.cache_resource(ttl=60)
def fetch_vix_data():
    """Fetch VIX and VIX9D from yfinance. Contango = VIX > VIX9D."""
    result = {"vix": None, "vix9d": None, "contango": None}
    if yf is None:
        return result
    try:
        h = yf.Ticker("^VIX").history(period="5d")
        if not h.empty:
            result["vix"] = round(h["Close"].iloc[-1], 2)
    except Exception:
        pass
    try:
        h9 = yf.Ticker("^VIX9D").history(period="5d")
        if not h9.empty:
            result["vix9d"] = round(h9["Close"].iloc[-1], 2)
    except Exception:
        pass
    if result["vix"] is not None and result["vix9d"] is not None:
        result["contango"] = result["vix"] > result["vix9d"]
    return result


def _score_option(opt, chain_ivs, spot_spy):
    """Score a single option candidate using multi-factor Greeks analysis.
    Returns (score, breakdown_dict). Higher score = better trade.

    Factors (each normalised 0-1, then weighted):
      W1  Delta Sweet Spot   — peak at |Δ|=0.30, penalise <0.15 or >0.50
      W2  Gamma/Theta Ratio  — intraday edge: high γ relative to θ decay
      W3  Bid-Ask Tightness  — liquidity proxy; tighter spread = better fills
      W4  Volume/OI Flow     — detects unusual institutional activity today
      W5  IV Relative Value   — prefer options near/below chain median IV
    """
    import math, sys
    W1, W2, W3, W4, W5 = 0.25, 0.25, 0.20, 0.15, 0.15
    _EPS = sys.float_info.epsilon

    abs_delta = abs(opt.get("delta", 0))
    gamma    = abs(opt.get("gamma", 0))
    theta    = abs(opt.get("theta", 0))
    iv       = opt.get("iv", 0)
    bid      = opt.get("bid", 0)
    ask      = opt.get("ask", 0)
    mid      = opt.get("mid", 0)
    vol      = opt.get("volume", 0)
    oi       = max(opt.get("oi", 1), 1)

    # ── F1: Delta Sweet-Spot  (Gaussian around 0.30, σ=0.10)
    f1 = math.exp(-((abs_delta - 0.30) ** 2) / (2 * 0.10 ** 2))

    # ── F2: Gamma/Theta Ratio  (higher = more intraday leverage per $ decay)
    #    Normalise via sigmoid so extreme values don't blow up the score
    gt_ratio = (gamma / theta) if theta > _EPS else 0.0
    f2 = 1 - 1 / (1 + gt_ratio)  # sigmoid: 0→0, 1→0.5, ∞→1

    # ── F3: Bid-Ask Tightness  (spread as % of mid; 0 spread → score 1)
    spread = ask - bid
    spread_pct = spread / mid if mid > 0 else 1.0
    f3 = max(0, 1 - spread_pct * 5)  # 0% → 1.0, 20%+ → 0.0

    # ── F4: Volume/OI Flow Ratio (>0.5 is unusual; cap at 1.0)
    flow = vol / oi if oi > 0 else 0
    f4 = min(flow, 1.0)

    # ── F5: IV Relative Value  (prefer below median IV in the chain)
    median_iv = sorted(chain_ivs)[len(chain_ivs) // 2] if chain_ivs else iv
    if median_iv > 0:
        iv_ratio = iv / median_iv
        f5 = max(0, min(1, 2 - iv_ratio))  # ratio 1→1.0, ratio 2→0.0
    else:
        f5 = 0.5

    total = W1 * f1 + W2 * f2 + W3 * f3 + W4 * f4 + W5 * f5

    breakdown = {
        "delta_score": round(f1, 3), "gt_score": round(f2, 3),
        "liq_score": round(f3, 3), "flow_score": round(f4, 3),
        "iv_score": round(f5, 3), "total": round(total, 4),
        "gt_ratio": round(gt_ratio, 2), "spread_pct": round(spread_pct * 100, 1),
        "flow_ratio": round(flow, 2),
    }
    return total, breakdown


def find_target_strike(chain, bias):
    """Greeks-weighted option selection. Scores every OTM candidate and picks the best.

    Candidate filters:
      Bull → calls with 0.10 < Δ < 0.50  (OTM calls)
      Bear → puts  with -0.50 < Δ < -0.10 (OTM puts)

    Returns the option dict augmented with '_score' and '_breakdown' keys,
    or None if no viable candidates exist.
    """
    if bias == "bull":
        cands = [o for o in chain if o["type"] == "call" and 0.10 < o.get("delta", 0) < 0.50]
    else:
        cands = [o for o in chain if o["type"] == "put" and -0.50 < o.get("delta", 0) < -0.10]

    # Require at least a valid mid price and non-zero gamma
    cands = [o for o in cands if o.get("mid", 0) > 0 and abs(o.get("gamma", 0)) > 0]

    if not cands:
        return None

    # Pre-compute chain IV distribution for relative value scoring
    chain_ivs = [o["iv"] for o in chain if o.get("iv", 0) > 0]
    spot_spy = cands[0]["strike"]  # approximate; not critical

    scored = []
    for o in cands:
        s, bd = _score_option(o, chain_ivs, spot_spy)
        o_copy = dict(o)
        o_copy["_score"] = s
        o_copy["_breakdown"] = bd
        scored.append(o_copy)

    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[0]


def parse_trade_input(text):
    """Parse input like 'SPX@6025 bull $5k size 1R risk 2:15pm ET'."""
    import re as _re
    text_lower = text.lower().strip()
    result = {"bias": None, "price_ref": None, "raw": text}
    if "bull" in text_lower:
        result["bias"] = "bull"
    elif "bear" in text_lower:
        result["bias"] = "bear"
    m = _re.search(r'@(\d+\.?\d*)', text)
    if m:
        result["price_ref"] = float(m.group(1))
    return result


def generate_recommendation(chain, spx_metrics, vix_data):
    """Auto-generate complete trade recommendation based on confluence scoring."""
    if not chain or not spx_metrics:
        return None
    spot = spx_metrics["spot"]
    vwap = spx_metrics["vwap"]
    pcr = compute_pcr(chain)
    gex_profile = compute_gex_profile(chain, spx_metrics["spot"] / 10)
    gamma_flip_spy = find_gamma_flip(gex_profile)
    gamma_flip = gamma_flip_spy * 10 if gamma_flip_spy else None
    max_pain_spy = compute_max_pain(chain)
    max_pain = max_pain_spy * 10 if max_pain_spy else None
    contango = vix_data.get("contango")

    # Automated Scoring Logic (-4 to +4)
    # ----------------------------------------------------------------
    score = 0
    met, failed = [], []

    # 1. Spot vs VWAP
    if spot > vwap:
        score += 1
        met.append("Spot > VWAP")
    else:
        score -= 1
        failed.append("Spot < VWAP")

    # 2. Spot vs Gamma Flip
    if gamma_flip:
        if spot > gamma_flip:
            score += 1
            met.append("Spot > Gamma Flip")
        else:
            score -= 1
            failed.append("Spot < Gamma Flip")

    # 3. Sentiment (PCR)
    if pcr is not None:
        if pcr < 0.8:
            score += 1
            met.append("PCR < 0.8 (Bullish)")
        elif pcr > 1.0:
            score -= 1
            failed.append("PCR > 1.0 (Bearish)")

    # 4. Volatility Term Structure
    if contango is not None:
        if contango:
            score += 1
            met.append("VIX in Contango")
        else:
            score -= 1
            failed.append("VIX in Backwardation")

    # Determine Bias 
    # ----------------------------------------------------------------
    if score >= 2:
        bias = "bull"
        direction = "bullish"
    elif score <= -2:
        bias = "bear"
        direction = "bearish"
        # Swap met/failed arrays for the display outpt since 'failed' just meant bear conditions
        met, failed = failed, met
    else:
        # Neutral / Chop — score was -1, 0, or 1. No clear confluence.
        return {
            "recommendation": "NO TRADE — Mixed Signals",
            "rationale": "The confluence score is too low (-1 to +1). Market state is mixed or choppy.",
            "stats": "", "action": "Wait for better alignment across indicators.",
            "conditions_met": met, "conditions_failed": failed,
            "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0
        }

    # Find Target Strike & Build Output
    # ----------------------------------------------------------------
    target = find_target_strike(chain, bias)
    if not target:
        return {"recommendation": "NO TRADE — No suitable option found",
                "rationale": f"No viable {bias} options passed the Greeks quality filter.",
                "stats": "", "action": "", "conditions_met": met, "conditions_failed": failed,
                "confidence": "LOW", "strike_spx": 0, "opt_type": "", "mid_price": 0}

    strike_spx = round(target["strike"] * 10, 0)
    delta_pct = round(abs(target["delta"]) * 100)
    opt_label = "CALL" if target["type"] == "call" else "PUT"
    bd = target.get("_breakdown", {})

    # Find hedging wall
    hedge_wall = None
    if gex_profile:
        for gk, gv in sorted(gex_profile.items(), key=lambda x: abs(x[1]), reverse=True):
            gk_spx = gk * 10
            if (bias == "bull" and gk_spx > strike_spx) or (bias == "bear" and gk_spx < strike_spx):
                hedge_wall = gk_spx
                break

    confidence = "HIGH" if abs(score) >= 3 else "MODERATE"

    # Rationale Texts
    parts_map = {
        "bull": {"Spot > VWAP": "SPX is trading above its daily volume-weighted average (VWAP)",
                 "Spot > Gamma Flip": "dealers are supporting the rally (Positive Gamma)",
                 "VIX in Contango": "Fear is dropping (VIX Contango)",
                 "PCR < 0.8 (Bullish)": "Options sentiment is bullish (low Put/Call Ratio)"},
        "bear": {"Spot < VWAP": "SPX is trading below its daily volume-weighted average (VWAP)",
                 "Spot < Gamma Flip": "dealers are pressuring prices lower (Negative Gamma)",
                 "PCR > 1.0 (Bearish)": "Options sentiment is bearish (high Put/Call Ratio)",
                 "VIX in Backwardation": "Fear is elevating (VIX Backwardation)"},
    }
    rp = [parts_map.get(bias, {}).get(c, "") for c in met if c in parts_map.get(bias, {})]
    rationale = f"Confluence score is **{score:+d}**. The market is showing strong {direction} momentum because " + " and ".join(rp) + "."

    target_pts = abs(int(hedge_wall - strike_spx)) if hedge_wall else 10
    target_pts = target_pts if target_pts > 0 else 10
    stop_pts = int(abs(strike_spx - max_pain)) if max_pain else 10
    stop_pts = stop_pts if stop_pts > 0 else 10

    target_desc = f"Target the {int(hedge_wall)} Hedging Wall (+{target_pts}pts)" if hedge_wall else "Target +10pts"
    stop_desc = f"Set a strict stop-loss at Max Pain {int(max_pain)} (-{stop_pts}pts)" if max_pain else "Set a strict stop-loss at -10pts"

    # Greeks Detail Line
    greeks_line = (
        f"Δ={target['delta']:+.3f}  Γ={target['gamma']:.4f}  "
        f"Θ={target['theta']:.4f}  V={target['vega']:.4f}  IV={target['iv']:.1%}"
    )
    scoring_line = (
        f"Selection Score: {bd.get('total', 0):.3f} "
        f"(Δ-fit:{bd.get('delta_score', 0):.2f} "
        f"Γ/Θ:{bd.get('gt_score', 0):.2f} "
        f"Liq:{bd.get('liq_score', 0):.2f} "
        f"Flow:{bd.get('flow_score', 0):.2f} "
        f"IV-val:{bd.get('iv_score', 0):.2f})"
    )
    stats_text = (
        f"Greeks: {greeks_line}\n"
        f"Stats: ~{delta_pct}% P(ITM) | Γ/Θ ratio: {bd.get('gt_ratio', 0):.1f}x | "
        f"Spread: {bd.get('spread_pct', 0):.1f}% | Flow: {bd.get('flow_ratio', 0):.2f}x OI\n"
        f"{scoring_line}"
    )

    return {
        "recommendation": f"RECOMMENDATION: BUY {int(strike_spx)} {opt_label}",
        "rationale": f"Rationale: {rationale}",
        "stats": stats_text,
        "action": f"Action Plan: Enter now. {target_desc}. {stop_desc}. Size: 1 contract.",
        "confidence": confidence, "conditions_met": met, "conditions_failed": failed,
        "strike_spx": strike_spx, "opt_type": opt_label, "mid_price": target.get("mid", 0),
    }

# ════════════════════════════════════════════════════════════════════
# CRYPTO WHALE FLOWS & ON-CHAIN DATA  (US-accessible APIs)
# ════════════════════════════════════════════════════════════════════

_COINBASE_MAP = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}

@st.cache_data(ttl=120)
def get_whale_trades(symbol="BTCUSDT", min_usd=500_000):
    """Coinbase Exchange public trades — filter for whale-size orders.
    Returns top 25 by USD value descending.
    """
    product = _COINBASE_MAP.get(symbol, "BTC-USD")
    try:
        r = requests.get(
            f"https://api.exchange.coinbase.com/products/{product}/trades",
            params={"limit": 1000},
            timeout=10,
        )
        r.raise_for_status()
        trades = r.json()
        result = []
        for t in trades:
            price = float(t.get("price", "0"))
            qty = float(t.get("size", "0"))
            usd = price * qty
            if usd < min_usd:
                continue
            side = "BUY" if t.get("side", "") == "buy" else "SELL"
            time_str = ""
            iso = t.get("time", "")
            if iso:
                try:
                    from datetime import datetime as _dt
                    time_str = _dt.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M:%S")
                except:
                    time_str = str(iso)[:8]
            result.append({
                "time": time_str,
                "side": side,
                "qty": round(qty, 4),
                "usd": round(usd, 2),
                "price": round(price, 2),
            })
        result.sort(key=lambda x: x["usd"], reverse=True)
        return result[:25]
    except:
        return []


@st.cache_data(ttl=600)
def get_exchange_netflow():
    """CoinGecko public exchanges — top 10 by BTC volume with trust score.
    Includes 1s sleep to avoid 429 rate limits.
    """
    import time as _time
    try:
        _time.sleep(1)
        r = requests.get(
            "https://api.coingecko.com/api/v3/exchanges",
            params={"per_page": 10, "page": 1},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        result = []
        for ex in data:
            result.append({
                "name": ex.get("name", ""),
                "btc_vol_24h": float(ex.get("trade_volume_24h_btc", 0) or 0),
                "trust_score": int(ex.get("trust_score", 0) or 0),
            })
        result.sort(key=lambda x: x["btc_vol_24h"], reverse=True)
        return result
    except:
        return []


_FUNDING_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                     "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT", "ADAUSDT"]

@st.cache_data(ttl=120)
def get_funding_rates():
    """Bybit v5 linear tickers — funding rates for top 10 coins.
    Sorted by abs(rate_pct) descending.
    """
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear"},
            timeout=10,
        )
        r.raise_for_status()
        tickers = r.json().get("result", {}).get("list", [])
        lookup = {t["symbol"]: t for t in tickers if t.get("symbol") in _FUNDING_SYMBOLS}
        result = []
        for sym in _FUNDING_SYMBOLS:
            t = lookup.get(sym)
            if not t:
                continue
            rate = float(t.get("fundingRate", "0") or "0")
            mark = float(t.get("markPrice", "0") or "0")
            rate_pct = round(rate * 100, 4)
            result.append({
                "symbol": sym.replace("USDT", ""),
                "rate_pct": rate_pct,
                "rate_ann": round(rate_pct * 3 * 365, 2),
                "mark_price": round(mark, 2),
            })
        result.sort(key=lambda x: abs(x["rate_pct"]), reverse=True)
        return result
    except:
        return []


_OI_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT"]

@st.cache_data(ttl=120)
def get_open_interest():
    """Bybit v5 open interest per coin, enriched with mark price for USD value."""
    try:
        # Fetch mark prices in one call
        tr = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear"},
            timeout=10,
        )
        tr.raise_for_status()
        tickers = tr.json().get("result", {}).get("list", [])
        marks = {t["symbol"]: float(t.get("markPrice", "0") or "0") for t in tickers}

        result = []
        for sym in _OI_SYMBOLS:
            try:
                r = requests.get(
                    "https://api.bybit.com/v5/market/open-interest",
                    params={"category": "linear", "symbol": sym, "intervalTime": "5min", "limit": 1},
                    timeout=8,
                )
                r.raise_for_status()
                items = r.json().get("result", {}).get("list", [])
                if not items:
                    continue
                oi_coins = float(items[0].get("openInterest", "0") or "0")
                mark = marks.get(sym, 0)
                result.append({
                    "symbol": sym.replace("USDT", ""),
                    "oi_coins": round(oi_coins, 4),
                    "oi_usd": round(oi_coins * mark, 2),
                })
            except:
                continue
        result.sort(key=lambda x: x["oi_usd"], reverse=True)
        return result
    except:
        return []


_LIQ_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]

@st.cache_data(ttl=180)
def get_liquidations():
    """Coinglass public liquidation data (no API key).
    Per-coin requests — individual failures are skipped gracefully.
    """
    result = {}
    for coin in _LIQ_COINS:
        try:
            r = requests.get(
                "https://open-api.coinglass.com/public/v2/liquidation_chart",
                params={"ex": "Bybit", "pair": f"{coin}USDT", "interval": "0"},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if r.status_code in (403, 429):
                result[coin] = {"long_liq": 0, "short_liq": 0, "total": 0}
                continue
            r.raise_for_status()
            data = r.json().get("data", {})
            long_liq = float(data.get("longLiquidationUsd", 0) or 0)
            short_liq = float(data.get("shortLiquidationUsd", 0) or 0)
            result[coin] = {
                "long_liq": round(long_liq, 2),
                "short_liq": round(short_liq, 2),
                "total": round(long_liq + short_liq, 2),
            }
        except:
            result[coin] = {"long_liq": 0, "short_liq": 0, "total": 0}
    return result


# ════════════════════════════════════════════════════════════════════
# MACRO OVERVIEW & CALENDAR
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_macro_overview(fred_key):
    """Compute a scored US macro environment overview from FRED data.
    Returns a dict with individual signal scores, an overall score, and a narrative."""
    if not fred_key:
        return None

    signals = {}

    # ── 1. Inflation (CPI YoY)
    try:
        df_cpi = fred_series("CPIAUCSL", fred_key, 24)
        if df_cpi is not None and len(df_cpi) >= 13:
            latest = df_cpi["value"].iloc[-1]
            year_ago = df_cpi["value"].iloc[-13]
            cpi_yoy = round((latest / year_ago - 1) * 100, 2)
            if cpi_yoy < 2.5:
                cpi_score, cpi_label, cpi_color = 2, f"Cooling ({cpi_yoy:.1f}%)", "#00CC44"
            elif cpi_yoy < 3.5:
                cpi_score, cpi_label, cpi_color = 1, f"Elevated ({cpi_yoy:.1f}%)", "#FF8C00"
            elif cpi_yoy < 5.0:
                cpi_score, cpi_label, cpi_color = -1, f"High ({cpi_yoy:.1f}%)", "#FF4444"
            else:
                cpi_score, cpi_label, cpi_color = -2, f"Very High ({cpi_yoy:.1f}%)", "#FF0000"
            signals["CPI Inflation"] = {"score": cpi_score, "label": cpi_label, "color": cpi_color, "val": cpi_yoy}
    except Exception:
        pass

    # ── 2. Core PCE YoY (Fed's preferred measure)
    try:
        df_pce = fred_series("PCEPILFE", fred_key, 24)
        if df_pce is not None and len(df_pce) >= 13:
            latest = df_pce["value"].iloc[-1]
            year_ago = df_pce["value"].iloc[-13]
            pce_yoy = round((latest / year_ago - 1) * 100, 2)
            if pce_yoy < 2.5:
                pce_score, pce_label, pce_color = 2, f"Near Target ({pce_yoy:.1f}%)", "#00CC44"
            elif pce_yoy < 3.0:
                pce_score, pce_label, pce_color = 1, f"Slightly Elevated ({pce_yoy:.1f}%)", "#FF8C00"
            else:
                pce_score, pce_label, pce_color = -1, f"Above Target ({pce_yoy:.1f}%)", "#FF4444"
            signals["Core PCE"] = {"score": pce_score, "label": pce_label, "color": pce_color, "val": pce_yoy}
    except Exception:
        pass

    # ── 3. Unemployment Rate
    try:
        df_unemp = fred_series("UNRATE", fred_key, 6)
        if df_unemp is not None and not df_unemp.empty:
            urate = df_unemp["value"].iloc[-1]
            prev = df_unemp["value"].iloc[-2] if len(df_unemp) > 1 else urate
            trend = "↑" if urate > prev else "↓"
            if urate < 4.0:
                u_score, u_label, u_color = 2, f"Full Employment ({urate:.1f}% {trend})", "#00CC44"
            elif urate < 4.5:
                u_score, u_label, u_color = 1, f"Near Full Emp. ({urate:.1f}% {trend})", "#FF8C00"
            elif urate < 5.5:
                u_score, u_label, u_color = -1, f"Rising ({urate:.1f}% {trend})", "#FF4444"
            else:
                u_score, u_label, u_color = -2, f"High Unemployment ({urate:.1f}% {trend})", "#FF0000"
            signals["Unemployment"] = {"score": u_score, "label": u_label, "color": u_color, "val": urate}
    except Exception:
        pass

    # ── 4. Yield Curve (10Y - 2Y)
    try:
        df_2y  = fred_series("DGS2",  fred_key, 3)
        df_10y = fred_series("DGS10", fred_key, 3)
        if df_2y is not None and df_10y is not None and not df_2y.empty and not df_10y.empty:
            spread = round(df_10y["value"].iloc[-1] - df_2y["value"].iloc[-1], 2)
            if spread > 0.5:
                yc_score, yc_label, yc_color = 2, f"Steep (+{spread:.2f}% — Growth signal)", "#00CC44"
            elif spread > 0:
                yc_score, yc_label, yc_color = 1, f"Flat (+{spread:.2f}%) — Flattening", "#FF8C00"
            elif spread > -0.5:
                yc_score, yc_label, yc_color = -1, f"Inverted ({spread:.2f}%) — Caution", "#FF4444"
            else:
                yc_score, yc_label, yc_color = -2, f"Deep Inversion ({spread:.2f}%) — Recession Risk", "#FF0000"
            signals["Yield Curve (10-2Y)"] = {"score": yc_score, "label": yc_label, "color": yc_color, "val": spread}
    except Exception:
        pass

    # ── 5. Fed Funds Rate
    try:
        df_ff = fred_series("FEDFUNDS", fred_key, 6)
        if df_ff is not None and not df_ff.empty:
            ffr = df_ff["value"].iloc[-1]
            prev_ffr = df_ff["value"].iloc[-2] if len(df_ff) > 1 else ffr
            ff_trend = "cutting" if ffr < prev_ffr else ("hiking" if ffr > prev_ffr else "hold")
            if ff_trend == "cutting" and ffr < 4.0:
                ff_score, ff_label, ff_color = 2, f"Easing ({ffr:.2f}% — {ff_trend.upper()})", "#00CC44"
            elif ff_trend == "cutting":
                ff_score, ff_label, ff_color = 1, f"Beginning Cuts ({ffr:.2f}%)", "#FF8C00"
            elif ff_trend == "hiking":
                ff_score, ff_label, ff_color = -1, f"Tightening ({ffr:.2f}% — {ff_trend.upper()})", "#FF4444"
            elif ffr > 5.0:
                ff_score, ff_label, ff_color = -1, f"Restrictive ({ffr:.2f}% — HOLD)", "#FF4444"
            else:
                ff_score, ff_label, ff_color = 1, f"Neutral ({ffr:.2f}% — HOLD)", "#FF8C00"
            signals["Fed Funds Rate"] = {"score": ff_score, "label": ff_label, "color": ff_color, "val": ffr}
    except Exception:
        pass

    # ── 6. HY Credit Spread
    try:
        df_hy = fred_series("BAMLH0A0HYM2", fred_key, 6)
        if df_hy is not None and not df_hy.empty:
            hy = df_hy["value"].iloc[-1]
            prev_hy = df_hy["value"].iloc[-2] if len(df_hy) > 1 else hy
            hy_trend = "↑" if hy > prev_hy else "↓"
            if hy < 3.5:
                hy_score, hy_label, hy_color = 2, f"Tight ({hy:.2f}% {hy_trend} — Risk-On)", "#00CC44"
            elif hy < 4.5:
                hy_score, hy_label, hy_color = 1, f"Normal ({hy:.2f}% {hy_trend})", "#FF8C00"
            elif hy < 6.0:
                hy_score, hy_label, hy_color = -1, f"Wide ({hy:.2f}% {hy_trend} — Stress)", "#FF4444"
            else:
                hy_score, hy_label, hy_color = -2, f"Very Wide ({hy:.2f}% {hy_trend} — Crisis)", "#FF0000"
            signals["HY Credit Spread"] = {"score": hy_score, "label": hy_label, "color": hy_color, "val": hy}
    except Exception:
        pass

    # ── 7. M2 Money Supply trend
    try:
        df_m2 = fred_series("M2SL", fred_key, 18)
        if df_m2 is not None and len(df_m2) >= 13:
            latest_m2 = df_m2["value"].iloc[-1]
            year_ago_m2 = df_m2["value"].iloc[-13]
            m2_yoy = round((latest_m2 / year_ago_m2 - 1) * 100, 2)
            if m2_yoy > 5:
                m2_score, m2_label, m2_color = -1, f"Expanding Rapidly ({m2_yoy:+.1f}% YoY — Inflationary)", "#FF4444"
            elif m2_yoy > 0:
                m2_score, m2_label, m2_color = 1, f"Modest Growth ({m2_yoy:+.1f}% YoY)", "#FF8C00"
            else:
                m2_score, m2_label, m2_color = 2, f"Contracting ({m2_yoy:+.1f}% YoY — Tightening)", "#00CC44"
            signals["M2 Money Supply"] = {"score": m2_score, "label": m2_label, "color": m2_color, "val": m2_yoy}
    except Exception:
        pass

    # ── 8. GDP Growth (Real GDP YoY proxy via quarterly change annualized)
    try:
        df_gdp = fred_series("GDPC1", fred_key, 12)  # Real GDP, quarterly
        if df_gdp is not None and len(df_gdp) >= 5:
            latest_gdp  = df_gdp["value"].iloc[-1]
            prev_gdp    = df_gdp["value"].iloc[-2]
            year_ago_gdp= df_gdp["value"].iloc[-5]
            gdp_yoy = round((latest_gdp / year_ago_gdp - 1) * 100, 2)
            gdp_q   = round((latest_gdp / prev_gdp - 1) * 4 * 100, 2)  # annualized QoQ
            if gdp_yoy >= 3.0:
                gdp_score, gdp_label, gdp_color = 2, f"Strong ({gdp_yoy:.1f}% YoY, {gdp_q:+.1f}% ann.)", "#00CC44"
            elif gdp_yoy >= 2.0:
                gdp_score, gdp_label, gdp_color = 1, f"Moderate ({gdp_yoy:.1f}% YoY)", "#FF8C00"
            elif gdp_yoy >= 0.5:
                gdp_score, gdp_label, gdp_color = -1, f"Slowing ({gdp_yoy:.1f}% YoY)", "#FF4444"
            else:
                gdp_score, gdp_label, gdp_color = -2, f"Contraction ({gdp_yoy:.1f}% YoY)", "#FF0000"
            signals["GDP Growth"] = {"score": gdp_score, "label": gdp_label, "color": gdp_color, "val": gdp_yoy}
    except Exception:
        pass

    # ── Aggregate Score
    total_score = sum(s["score"] for s in signals.values())
    max_score = len(signals) * 2
    pct = (total_score / max_score * 100) if max_score else 0

    if pct >= 60:
        env_label, env_color = "EXPANSIONARY 🟢", "#00CC44"
        env_desc = "Macro conditions are broadly supportive. Inflation cooling, labor market healthy, credit spreads tight. Risk-on bias."
    elif pct >= 20:
        env_label, env_color = "MIXED / NEUTRAL 🟡", "#FF8C00"
        env_desc = "Macro signals are mixed. Some positive factors offset by headwinds. Selective positioning warranted."
    elif pct >= -20:
        env_label, env_color = "CAUTIONARY ⚠️", "#FFCC00"
        env_desc = "More headwinds than tailwinds. Elevated inflation or tightening financial conditions weigh on outlook."
    else:
        env_label, env_color = "CONTRACTIONARY 🔴", "#FF4444"
        env_desc = "Multiple macro red flags. Inverted yield curve, high inflation, or rising credit stress signal elevated recession risk."

    return {
        "signals": signals,
        "total_score": total_score,
        "max_score": max_score,
        "pct": pct,
        "env_label": env_label,
        "env_color": env_color,
        "env_desc": env_desc,
    }


@st.cache_data(ttl=3600)
def get_macro_calendar(fred_key=None):
    """Fetch upcoming US economic calendar.
    Source priority: 1) Finnhub (free, no key needed for basic)
                     2) FRED releases API (if key available)
                     3) Smart static schedule (always works)
    Returns list of dicts: {date, name, importance, time, actual, forecast, previous}
    """
    from datetime import date as _date, timedelta as _td
    import calendar as _cal

    today = _date.today()
    horizon = today + _td(days=45)
    results = []

    # ── Source 1: Finnhub economic calendar (free tier works without key for basic)
    try:
        params = {
            "from": today.strftime("%Y-%m-%d"),
            "to":   horizon.strftime("%Y-%m-%d"),
        }
        if fred_key:
            pass  # FRED key not used for Finnhub
        # Try picking up Finnhub key from secrets if available
        try:
            import streamlit as _st
            fk = _st.secrets.get("FINNHUB_API_KEY") or _st.secrets.get("finnhub_api_key") or ""
            if fk: params["token"] = str(fk).strip()
        except Exception:
            pass

        r = requests.get("https://finnhub.io/api/v1/calendar/economic",
                         params=params, timeout=12)
        if r.status_code == 200:
            events = r.json().get("economicCalendar", [])
            HIGH_KW = ["cpi","fomc","fed","nonfarm","non-farm","payroll","gdp","pce","employment situation"]
            MED_KW  = ["ppi","retail sales","ism","pmi","housing starts","durable goods","jolts",
                       "adp","jobless","consumer confidence","industrial production","trade balance"]
            for ev in events:
                name = (ev.get("event") or "").strip()
                if not name: continue
                nl = name.lower()
                impact = (ev.get("impact") or "").upper()
                is_high = impact == "HIGH" or any(kw in nl for kw in HIGH_KW)
                is_med  = any(kw in nl for kw in MED_KW)
                if not (is_high or is_med or impact in ("HIGH","MEDIUM")): continue
                try:
                    ev_date = _date.fromisoformat((ev.get("time") or "")[:10])
                except Exception:
                    continue
                if not (today <= ev_date <= horizon): continue
                results.append({
                    "date":       ev_date,
                    "name":       name,
                    "importance": "HIGH" if is_high else "MEDIUM",
                    "time":       "",
                    "actual":     str(ev.get("actual",""))   if ev.get("actual")   is not None else "",
                    "forecast":   str(ev.get("estimate","")) if ev.get("estimate") is not None else "",
                    "previous":   str(ev.get("prev",""))     if ev.get("prev")     is not None else "",
                    "source":     "finnhub",
                })
            if results:
                results.sort(key=lambda x: x["date"])
                return results[:35]
    except Exception:
        pass

    # ── Source 2: FRED releases endpoint (if key available)
    if fred_key:
        try:
            r = requests.get(
                "https://api.stlouisfed.org/fred/releases/dates",
                params={
                    "api_key": fred_key, "file_type": "json",
                    "realtime_start": today.strftime("%Y-%m-%d"),
                    "realtime_end":   horizon.strftime("%Y-%m-%d"),
                    "limit": 150, "sort_order": "asc",
                    "include_release_dates_with_no_data": "false",
                },
                timeout=12,
            )
            if r.status_code == 200:
                FRED_NAMES = {
                    "10":("Consumer Price Index (CPI)","HIGH"),
                    "21":("Employment Situation (Jobs Report)","HIGH"),
                    "46":("Personal Income & PCE","HIGH"),
                    "20":("GDP (Advance/Preliminary/Final)","HIGH"),
                    "9": ("FOMC Meeting / Fed Decision","HIGH"),
                    "15":("Producer Price Index (PPI)","MEDIUM"),
                    "14":("Retail Sales","MEDIUM"),
                    "17":("Industrial Production","MEDIUM"),
                    "19":("Housing Starts & Building Permits","MEDIUM"),
                    "11":("Consumer Confidence","MEDIUM"),
                    "22":("Initial Jobless Claims","MEDIUM"),
                    "175":("ISM Manufacturing PMI","MEDIUM"),
                    "184":("ISM Services PMI","MEDIUM"),
                    "13":("Durable Goods Orders","MEDIUM"),
                    "69":("ADP Employment Report","MEDIUM"),
                    "23":("JOLTS Job Openings","MEDIUM"),
                    "55":("Trade Balance","MEDIUM"),
                }
                for rel in r.json().get("release_dates", []):
                    rid = str(rel.get("release_id",""))
                    if rid not in FRED_NAMES: continue
                    name, imp = FRED_NAMES[rid]
                    for d in rel.get("release_dates",[]):
                        try:
                            rel_date = _date.fromisoformat(d)
                            if today <= rel_date <= horizon:
                                results.append({"date":rel_date,"name":name,"importance":imp,
                                                "time":"","actual":"","forecast":"","previous":"","source":"fred"})
                        except Exception:
                            continue
                if results:
                    results.sort(key=lambda x: x["date"])
                    return results[:35]
        except Exception:
            pass

    # ── Source 3: Smart static fallback — algorithmically computed approximate dates
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
            if _date(year, month, day).weekday() == weekday:
                last = _date(year, month, day)
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
        d = _nth_weekday(y, m, 3, 3)
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
        d = _nth_weekday(y, m, 4, 2)
        if d: static_events.append(("Durable Goods Orders", d, "MEDIUM"))
        d = _last_weekday(y, m, 3)
        if d: static_events.append(("GDP (Advance Estimate)", d, "HIGH"))

    FOMC_APPROX = [
        _date(2025,3,19), _date(2025,5,7), _date(2025,6,18),
        _date(2025,7,30), _date(2025,9,17), _date(2025,10,29),
        _date(2025,12,10), _date(2026,1,28), _date(2026,3,18),
        _date(2026,4,29), _date(2026,6,17), _date(2026,7,29),
        _date(2026,9,16), _date(2026,10,28), _date(2026,12,16),
    ]
    for fd in FOMC_APPROX:
        if today <= fd <= horizon:
            static_events.append(("FOMC Meeting (Fed Rate Decision)", fd, "HIGH"))

    seen = set()
    for name, date, imp in static_events:
        key = (date, name)
        if key in seen or not (today <= date <= horizon): continue
        seen.add(key)
        results.append({"date":date,"name":name,"importance":imp,
                        "time":"","actual":"","forecast":"","previous":"","source":"est."})

    results.sort(key=lambda x: x["date"])
    return results[:35]

# ════════════════════════════════════════════════════════════════════
# STOCK EXCHANGE LOOKUP (for TradingView symbol mapping)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_ticker_exchange(ticker):
    """Determine the correct exchange for a ticker using yfinance info.
    Returns a TradingView-compatible symbol prefix."""
    EXCHANGE_MAP = {
        "NMS": "NASDAQ",  # NASDAQ Global Select
        "NGM": "NASDAQ",  # NASDAQ Global Market
        "NCM": "NASDAQ",  # NASDAQ Capital Market
        "NYQ": "NYSE",
        "ASE": "AMEX",
        "AMEX": "AMEX",
        "PCX": "AMEX",    # NYSE Arca
        "PNK": "OTC",
        "OTC": "OTC",
        "BTT": "NYSE",
        "NYSEArca": "AMEX",
        "NasdaqCM": "NASDAQ",
        "NasdaqGS": "NASDAQ",
        "NasdaqGM": "NASDAQ",
        "NYSE": "NYSE",
    }
    try:
        info = yf.Ticker(ticker).info
        exch = info.get("exchange", "") or info.get("fullExchangeName", "")
        tv_prefix = EXCHANGE_MAP.get(exch, None)
        if tv_prefix:
            return f"{tv_prefix}:{ticker}"
    except Exception:
        pass
    # Try each major exchange prefix
    for prefix in ["NASDAQ", "NYSE", "AMEX"]:
        return f"{prefix}:{ticker}"
    return f"NASDAQ:{ticker}"


# ════════════════════════════════════════════════════════════════════
# FULL FINANCIALS FOR EARNINGS TAB
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800)
def get_full_financials(ticker):
    """Fetch comprehensive quarterly financials: Income, Balance Sheet, Cash Flow.
    Returns a dict with standardized metrics per quarter."""
    if yf is None:
        return {}
    try:
        t = yf.Ticker(ticker)
        income = t.quarterly_financials
        cashflow = t.quarterly_cashflow
        balance = t.quarterly_balance_sheet
        info = t.info or {}

        if income is None or income.empty:
            return {}

        quarters = list(income.columns[:4])
        results = {}

        for q in quarters:
            q_str = str(q)[:10]
            row = {}

            # Income Statement
            def _get(df, *keys):
                for k in keys:
                    if df is not None and not df.empty and k in df.index and q in df.columns:
                        v = df.loc[k, q]
                        if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                            return float(v)
                return None

            row["revenue"]    = _get(income, "Total Revenue")
            row["gross_profit"]= _get(income, "Gross Profit")
            row["op_income"]  = _get(income, "Operating Income", "EBIT")
            row["net_income"] = _get(income, "Net Income")
            row["ebitda"]     = _get(income, "EBITDA", "Normalized EBITDA")
            row["eps"]        = _get(income, "Diluted EPS", "Basic EPS")
            row["int_expense"]= _get(income, "Interest Expense")

            # Cash Flow
            row["free_cashflow"] = _get(cashflow, "Free Cash Flow")
            row["op_cashflow"]   = _get(cashflow, "Operating Cash Flow")
            row["capex"]         = _get(cashflow, "Capital Expenditure")

            # Balance Sheet
            row["total_debt"]    = _get(balance, "Total Debt", "Long Term Debt And Capital Lease Obligation")
            row["cash"]          = _get(balance, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")

            # Derived margins
            if row["revenue"] and row["revenue"] > 0:
                if row["gross_profit"] is not None:
                    row["gross_margin"] = row["gross_profit"] / row["revenue"] * 100
                if row["op_income"] is not None:
                    row["op_margin"] = row["op_income"] / row["revenue"] * 100
                if row["net_income"] is not None:
                    row["net_margin"] = row["net_income"] / row["revenue"] * 100

            results[q_str] = row

        return results
    except Exception:
        return {}


@st.cache_data(ttl=600)
def get_stock_news(ticker, finnhub_key=None, newsapi_key=None):
    """Fetch news for a specific stock ticker from multiple sources.
    Uses Finnhub company news first, then GDELT, then NewsAPI."""
    results = []

    # ── 1. Finnhub company-specific news
    if finnhub_key:
        try:
            from datetime import date as _date
            today = _date.today()
            from_dt = (today - __import__("datetime").timedelta(days=7)).strftime("%Y-%m-%d")
            to_dt = today.strftime("%Y-%m-%d")
            r = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": ticker, "from": from_dt, "to": to_dt, "token": finnhub_key},
                timeout=10,
            )
            articles = r.json() if r.status_code == 200 else []
            for art in articles[:8]:
                headline = art.get("headline", "")
                if not headline or not _is_english(headline):
                    continue
                ts = art.get("datetime", 0)
                d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
                results.append({
                    "title": headline[:110],
                    "url": art.get("url", "#"),
                    "source": art.get("source", "Finnhub"),
                    "date": d,
                })
            if results:
                return results
        except Exception:
            pass

    # ── 2. GDELT with ticker + company name
    try:
        info = yf.Ticker(ticker).info if yf else {}
        co_name = info.get("shortName", ticker).split()[0] if info else ticker
        query = f"{ticker} {co_name} stock"
        arts = gdelt_news(query, max_rec=8)
        for art in arts:
            title = art.get("title", "")
            if not title:
                continue
            sd = art.get("seendate", "")
            d = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
            results.append({
                "title": title[:110],
                "url": art.get("url", "#"),
                "source": art.get("domain", "GDELT"),
                "date": d,
            })
        if results:
            return results
    except Exception:
        pass

    # ── 3. NewsAPI
    if newsapi_key:
        try:
            arts = newsapi_headlines(newsapi_key, query=f"{ticker} stock earnings")
            for art in arts[:8]:
                title = art.get("title", "")
                if not title or "[Removed]" in title:
                    continue
                results.append({
                    "title": title[:110],
                    "url": art.get("url", "#"),
                    "source": art.get("source", {}).get("name", "NewsAPI"),
                    "date": art.get("publishedAt", "")[:10],
                })
        except Exception:
            pass

    return results


# ════════════════════════════════════════════════════════════════════
# POLYMARKET MISPRICING ALGORITHM
# ════════════════════════════════════════════════════════════════════

def _poly_liquidity_score(market):
    """Score liquidity 0-1. Low liquidity = crowd prices less reliable."""
    vol   = _safe_float(market.get("volume", 0))
    vol24 = _safe_float(market.get("volume24hr", 0))
    liq   = _safe_float(market.get("liquidity", 0))
    # Tier breakpoints tuned to Polymarket distribution
    if vol > 1_000_000 and liq > 100_000:  return 1.0   # Deep liquid
    if vol > 250_000  and liq > 30_000:    return 0.80
    if vol > 50_000   and liq > 10_000:    return 0.60
    if vol > 10_000   and liq > 2_000:     return 0.40
    if vol > 1_000:                         return 0.20
    return 0.05  # Effectively illiquid — strong crowd discount

def _poly_crowd_accuracy_discount(liq_score):
    """Returns a reliability multiplier [0.3 – 1.0].
    In low-liquidity markets the crowd is more susceptible to herding /
    pack-following, so we shrink the implied probability toward 50%.
    Formula: P_adj = 0.5 + (P_raw - 0.5) × reliability
    """
    # reliability falls off quadratically with liquidity
    return 0.30 + 0.70 * (liq_score ** 0.6)

def score_poly_mispricing(markets, base_rate_fn=None):
    """
    Mathematical mispricing detector for Polymarket prediction markets.

    For each binary market the algorithm computes:

      1. raw_prob    — crowd YES price (0-1)
      2. liq_score   — liquidity quality score (0-1)
      3. reliability — crowd accuracy discount for low-liquidity herding
      4. adj_prob    — probability adjusted toward 50% by (1 - reliability)
                       adj_prob = 0.5 + (raw_prob - 0.5) × reliability
      5. edge        — |adj_prob - 0.5| — how far from coin-flip AFTER discount
      6. mispricing_score — composite anomaly score:
                            = edge × vol24_weight × (1 - liq_score)
                              The last factor is the KEY: high-vol, low-liquidity
                              markets with extreme prices are the most mispriced.
      7. fade_signal — whether to FADE (bet against) or RIDE the crowd

    Returns list of dicts sorted by mispricing_score descending.
    """
    results = []
    for m in markets:
        try:
            title = m.get("question", m.get("title", ""))
            if not title:
                continue

            # ── Parse outcome prices
            pp = _parse_poly_field(m.get("outcomePrices", []))
            outcomes = _parse_poly_field(m.get("outcomes", []))
            if not pp or len(pp) < 2:
                continue

            raw_yes = _safe_float(pp[0])
            raw_no  = _safe_float(pp[1]) if len(pp) > 1 else (1 - raw_yes)

            # Skip resolved / edge-case markets
            if raw_yes <= 0 or raw_yes >= 1:
                continue
            # Sanity-check: prices should sum to ~1
            if abs(raw_yes + raw_no - 1.0) > 0.15:
                continue

            # ── Liquidity & crowd discount
            liq_score   = _poly_liquidity_score(m)
            reliability = _poly_crowd_accuracy_discount(liq_score)
            adj_prob    = 0.5 + (raw_yes - 0.5) * reliability

            # ── Volume activity ratio (24h / total) — measures recency of bets
            vol   = _safe_float(m.get("volume", 0))
            vol24 = _safe_float(m.get("volume24hr", 0))
            activity_ratio = min(vol24 / vol, 1.0) if vol > 0 else 0.0

            # ── Volume weight (log-scaled so huge markets don't dominate)
            import math as _math
            vol24_weight = _math.log1p(vol24) / _math.log1p(1_000_000) if vol24 > 0 else 0.0
            vol24_weight = min(vol24_weight, 1.0)

            # ── Edge: how extreme is the crowd price, post-discount?
            edge = abs(adj_prob - 0.5)

            # ── Core mispricing score
            # High score = high activity in a low-liquidity market with extreme pricing
            mispricing_score = round(
                edge * vol24_weight * (1.0 - liq_score + 0.1) * (0.5 + activity_ratio),
                5
            )

            # ── Bid-ask spread proxy (if available)
            spread_str = ""
            best_bid = _safe_float(m.get("bestBid", 0))
            best_ask = _safe_float(m.get("bestAsk", 0)) or _safe_float(m.get("bestOffer", 0))
            if best_bid > 0 and best_ask > 0:
                spread = best_ask - best_bid
                spread_str = f"{spread*100:.1f}¢"

            # ── Fade vs Ride signal
            # Fade: low-liquidity extreme crowd → regression to mean expected
            # Ride: high-liquidity market with extreme but well-supported price
            if liq_score < 0.40 and raw_yes > 0.70:
                signal = "FADE YES"
                signal_color = "#FF4444"
            elif liq_score < 0.40 and raw_yes < 0.30:
                signal = "FADE NO"
                signal_color = "#00CC44"
            elif liq_score >= 0.70 and raw_yes > 0.65:
                signal = "RIDE YES"
                signal_color = "#00CC44"
            elif liq_score >= 0.70 and raw_yes < 0.35:
                signal = "RIDE NO"
                signal_color = "#FF4444"
            else:
                signal = "MONITOR"
                signal_color = "#FF8C00"

            results.append({
                "title":           title[:80],
                "url":             m.get("slug", ""),
                "raw_yes":         round(raw_yes * 100, 1),
                "adj_yes":         round(adj_prob * 100, 1),
                "liq_score":       liq_score,
                "reliability":     round(reliability, 2),
                "edge":            round(edge, 3),
                "mispricing_score": mispricing_score,
                "vol":             vol,
                "vol24":           vol24,
                "activity_ratio":  round(activity_ratio, 3),
                "signal":          signal,
                "signal_color":    signal_color,
                "spread":          spread_str,
                "liq_tier":        ("DEEP" if liq_score >= 0.8 else "MED" if liq_score >= 0.5 else "THIN" if liq_score >= 0.2 else "ILLIQ"),
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["mispricing_score"], reverse=True)
    return results[:15]  # Top 15 anomalies
