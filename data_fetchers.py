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

@st.cache_data(ttl=300)
def get_heatmap_data():
    """Fetch S&P sector heatmap data for FinViz-style display"""
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
    rows = []
    for sector, tickers in SECTOR_STOCKS.items():
        for tkr in tickers:
            q = yahoo_quote(tkr)
            if q: rows.append({"ticker": tkr, "sector": sector, "pct": q["pct"],
                               "price": q["price"], "change": q["change"]})
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
    """Get top gainers and losers from S&P 100 components"""
    UNIVERSE = [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "UNH", "XOM",
        "JPM", "JNJ", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PFE", "LLY", "KO",
        "BAC", "PEP", "TMO", "COST", "AVGO", "CSCO", "ABT", "WFC", "DIS", "ACN", "MCD",
        "NEE", "VZ", "ADBE", "PM", "NKE", "T", "INTC", "AMD", "CRM", "ORCL", "QCOM",
        "TXN", "HON", "GE", "RTX", "CAT", "GS", "BMY", "MDT", "AMGN", "GILD",
        "SBUX", "ISRG", "SPGI", "BLK", "AXP", "CI", "DE", "INTU", "ADI"
    ]
    quotes = multi_quotes(UNIVERSE)
    sorted_q = sorted(quotes, key=lambda x: x["pct"], reverse=True)
    return sorted_q[:8], sorted_q[-8:]

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

@st.cache_data(ttl=1800)
def get_earnings_calendar():
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
# SPX 0DTE MODULE v3
# ════════════════════════════════════════════════════════════════════

import math
from datetime import datetime
import pytz

def _ncdf(x):
    a = [0, 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429]
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    p = t * (a[1] + t * (a[2] + t * (a[3] + t * (a[4] + t * a[5]))))
    c = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * p
    return c if x >= 0 else 1.0 - c

def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def sabr_iv(F, K, T, alpha, beta, rho, nu):
    if T <= 0 or alpha <= 0:
        return max(abs(F - K) / F, 0.001) if F > 0 else 0.20
    try:
        if abs(F - K) < 1e-4 * F:
            Fb = F ** (1.0 - beta)
            corr = (
                (1.0 - beta)**2 / 24.0 * alpha**2 / F**(2.0 - 2.0*beta)
                + rho * beta * nu * alpha / (4.0 * Fb)
                + (2.0 - 3.0*rho**2) / 24.0 * nu**2
            )
            return max((alpha / Fb) * (1.0 + corr * T), 0.001)
        FK   = math.sqrt(F * K)
        FKb  = FK ** (1.0 - beta)
        lfk  = math.log(F / K)
        z    = (nu / alpha) * FKb * lfk
        arg  = (math.sqrt(1.0 - 2.0*rho*z + z*z) + z - rho) / (1.0 - rho)
        chi  = math.log(max(arg, 1e-10))
        zchi = z / chi if abs(chi) > 1e-10 else 1.0
        denom = FKb * (1.0 + (1.0-beta)**2/24.0*lfk**2 + (1.0-beta)**4/1920.0*lfk**4)
        corr  = (
            (1.0-beta)**2/24.0 * alpha**2 / FK**(2.0-2.0*beta)
            + rho*beta*nu*alpha / (4.0*FKb)
            + (2.0-3.0*rho**2)/24.0 * nu**2
        )
        return max((alpha / denom) * zchi * (1.0 + corr * T), 0.001)
    except (ValueError, ZeroDivisionError, OverflowError):
        return 0.20

def _nelder_mead(f, x0, bounds, max_iter=500, tol=1e-8):
    n = len(x0)
    def clip(x):
        return [max(bounds[i][0], min(bounds[i][1], x[i])) for i in range(n)]
    simplex = [clip(x0)]
    for i in range(n):
        xi = x0[:]; xi[i] += max(0.05 * abs(x0[i]), 0.01)
        simplex.append(clip(xi))
    fvals = [f(s) for s in simplex]
    for _ in range(max_iter):
        order   = sorted(range(n+1), key=lambda i: fvals[i])
        simplex = [simplex[i] for i in order]
        fvals   = [fvals[i]   for i in order]
        if fvals[-1] - fvals[0] < tol:
            break
        xc = [sum(simplex[i][j] for i in range(n)) / n for j in range(n)]
        xr = clip([xc[j] + 1.0*(xc[j] - simplex[-1][j]) for j in range(n)])
        fr = f(xr)
        if fr < fvals[0]:
            xe = clip([xc[j] + 2.0*(xr[j] - xc[j]) for j in range(n)])
            fe = f(xe)
            simplex[-1], fvals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < fvals[-2]:
            simplex[-1], fvals[-1] = xr, fr
        else:
            xcon = clip([xc[j] + 0.5*(simplex[-1][j] - xc[j]) for j in range(n)])
            fcon = f(xcon)
            if fcon < fvals[-1]:
                simplex[-1], fvals[-1] = xcon, fcon
            else:
                best = simplex[0]
                simplex = [best] + [
                    clip([best[j] + 0.5*(simplex[i][j]-best[j]) for j in range(n)])
                    for i in range(1, n+1)
                ]
                fvals = [f(s) for s in simplex]
    return simplex[0]

def calibrate_sabr(F, T, strikes, market_ivs, beta=0.5):
    pairs = [(k, iv) for k, iv in zip(strikes, market_ivs)
             if iv and 0.005 < iv < 5.0 and k > 0]
    if len(pairs) < 3:
        atm = market_ivs[len(market_ivs)//2] if market_ivs else 0.15
        return max(atm, 0.01) * (F**(1-beta)), beta, -0.5, 0.5
    ks, ivs = [p[0] for p in pairs], [p[1] for p in pairs]
    weights  = [3.0 if abs(k-F)/F < 0.005 else 1.0/(1.0 + abs(k-F)/F*8) for k in ks]
    def obj(params):
        a, rho, nu = params
        if a <= 0 or nu <= 0 or abs(rho) >= 1:
            return 1e10
        err = 0.0
        for k, iv, w in zip(ks, ivs, weights):
            try:
                err += w * (sabr_iv(F, k, T, a, beta, rho, nu) - iv)**2
            except Exception:
                err += w
        return err
    atm_iv = min(ivs, key=lambda iv: abs(ks[ivs.index(iv)] - F))
    alpha0 = max(atm_iv * (F**(1-beta)), 0.01)
    bounds = [(0.001, 5.0), (-0.999, -0.05), (0.05, 3.0)]
    try:
        a, rho, nu = _nelder_mead(obj, [alpha0, -0.5, 0.5], bounds)
        if abs(sabr_iv(F, F, T, a, beta, rho, nu) - atm_iv) > 0.05:
            raise ValueError("diverged")
        return a, beta, rho, nu
    except Exception:
        return alpha0, beta, -0.5, 0.5

def _bs_greeks(F, K, T, r, sigma, opt):
    if T <= 0 or sigma <= 0:
        d = (1.0 if F > K else 0.0) if opt == "call" else (-1.0 if F < K else 0.0)
        return d, 0.0, 0.0
    d1    = (math.log(F/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    gamma = _npdf(d1) / (F * sigma * math.sqrt(T))
    vega  = F * _npdf(d1) * math.sqrt(T)
    delta = _ncdf(d1) if opt == "call" else _ncdf(d1) - 1.0
    return delta, gamma, vega

def calc_sabr_greeks(F, K, T, r, alpha, beta, rho, nu, opt_type="call"):
    if T <= 0:
        d = (1.0 if F > K else 0.0) if opt_type=="call" else (-1.0 if F < K else 0.0)
        return d, 0.0
    try:
        dF   = F * 0.001
        s0   = sabr_iv(F,    K, T, alpha, beta, rho, nu)
        s_up = sabr_iv(F+dF, K, T, alpha, beta, rho, nu)
        s_dn = sabr_iv(F-dF, K, T, alpha, beta, rho, nu)
        ds   = (s_up - s_dn) / (2.0*dF)
        d2s  = (s_up - 2.0*s0 + s_dn) / (dF**2)
        delta_bs, gamma_bs, vega_bs = _bs_greeks(F, K, T, r, s0, opt_type)
        dsig = 0.001
        d_up, _, _ = _bs_greeks(F, K, T, r, s0+dsig, opt_type)
        d_dn, _, _ = _bs_greeks(F, K, T, r, s0-dsig, opt_type)
        vanna = (d_up - d_dn) / (2.0*dsig)
        delta = delta_bs + vega_bs * ds
        gamma = gamma_bs + 2.0*vanna*ds + vega_bs*d2s
        delta = max(0.0, min(1.0, delta)) if opt_type=="call" else max(-1.0, min(0.0, delta))
        gamma = max(0.0, gamma)
        return round(delta, 4), round(gamma, 8)
    except Exception:
        try:
            s = sabr_iv(F, K, T, alpha, beta, rho, nu)
            d, g, _ = _bs_greeks(F, K, T, r, s, opt_type)
            return round(d, 4), round(max(g, 0), 8)
        except Exception:
            return (0.5, 0.0) if opt_type=="call" else (-0.5, 0.0)

@st.cache_data(ttl=60)
def spx_spot():
    for tkr, scale in [("^GSPC", 1.0), ("SPY", 10.0)]:
        try:
            h = yf.Ticker(tkr).history(period="1d")
            if not h.empty:
                return round(float(h["Close"].iloc[-1]) * scale, 2)
        except Exception:
            pass
    return None

@st.cache_data(ttl=60)
def spx_intraday():
    try:
        df = yf.Ticker("SPY").history(period="1d", interval="5m")
        if not df.empty:
            df = df.reset_index()
            df.columns = [c.replace(" ", "_") for c in df.columns]
            return df
    except Exception:
        pass
    return None

@st.cache_data(ttl=90)
def spx_0dte_chain():
    ET        = pytz.timezone("US/Eastern")
    today_str = datetime.now(ET).strftime("%Y-%m-%d")
    for tkr, is_spy in [("^SPX", False), ("^GSPC", False), ("SPY", True)]:
        try:
            t    = yf.Ticker(tkr)
            exps = t.options
            if not exps: continue
            exp  = today_str if today_str in exps else next((e for e in exps if e >= today_str), None)
            if not exp: continue
            chain = t.option_chain(exp)
            calls, puts = chain.calls.copy(), chain.puts.copy()
            h = t.history(period="1d")
            if h.empty: continue
            raw = round(float(h["Close"].iloc[-1]), 2)
            if is_spy:
                calls["strike"] *= 10.0
                puts["strike"]  *= 10.0
                spot = raw * 10.0
            else:
                spot = raw
            lo, hi = spot * 0.97, spot * 1.03
            calls = calls[(calls["strike"] >= lo) & (calls["strike"] <= hi)].copy()
            puts  = puts [(puts["strike"]  >= lo) & (puts["strike"]  <= hi)].copy()
            if len(calls) < 3: continue
            return calls, puts, spot, exp, is_spy
        except Exception:
            continue
    return None, None, None, None, False

def enrich_0dte_with_greeks(calls, puts, spot, expiry_str):
    if calls is None or puts is None or spot is None:
        return calls, puts
    ET     = pytz.timezone("US/Eastern")
    now_et = datetime.now(ET)
    try:
        exp_dt = ET.localize(datetime.strptime(expiry_str, "%Y-%m-%d").replace(hour=16, minute=0, second=0))
        T = max((exp_dt - now_et).total_seconds() / (365.25 * 24 * 3600), 1e-7)
    except Exception:
        T = 1.0 / 365.0
    r, beta, F = 0.053, 0.5, spot
    ks, ivs = [], []
    for df in [calls, puts]:
        for _, row in df.iterrows():
            k  = float(row.get("strike", 0))
            iv = float(row.get("impliedVolatility", 0) or 0)
            if k > 0 and 0.005 < iv < 5.0:
                ks.append(k); ivs.append(iv)
    alpha, beta, rho, nu = calibrate_sabr(F, T, ks, ivs, beta=beta)
    def _enrich(df, opt):
        dl, gl, sv = [], [], []
        for _, row in df.iterrows():
            K = float(row.get("strike", F))
            d, g = calc_sabr_greeks(F, K, T, r, alpha, beta, rho, nu, opt)
            dl.append(d); gl.append(g)
            sv.append(round(sabr_iv(F, K, T, alpha, beta, rho, nu), 4))
        df = df.copy()
        df["delta"] = dl; df["gamma"] = gl; df["sabr_vol"] = sv
        return df
    calls = _enrich(calls, "call")
    puts  = _enrich(puts,  "put")
    meta  = {"alpha": round(alpha,4), "beta": beta, "rho": round(rho,3),
             "nu": round(nu,3), "T_days": round(T*365, 2)}
    calls.attrs["sabr"] = meta
    puts.attrs["sabr"]  = meta
    return calls, puts

def calc_max_pain(calls, puts):
    if calls is None or puts is None: return None
    try:
        strikes = sorted(set(list(calls["strike"].dropna()) + list(puts["strike"].dropna())))
        if not strikes: return None
        pain = {}
        for t in strikes:
            cp = sum(float(r.get("openInterest",0) or 0) * max(t - float(r["strike"]), 0) for _, r in calls.iterrows())
            pp = sum(float(r.get("openInterest",0) or 0) * max(float(r["strike"]) - t, 0) for _, r in puts.iterrows())
            pain[t] = cp + pp
        return min(pain, key=pain.get)
    except Exception:
        return None

def calc_expected_move(calls, puts, spot, is_spy=False):
    if calls is None or puts is None or spot is None: return None, None
    try:
        cc = calls.copy(); cc["_d"] = abs(cc["strike"] - spot)
        atm_call   = cc.loc[cc["_d"].idxmin()]
        atm_strike = float(atm_call["strike"])
        tol        = 1.5 if is_spy else 12.5
        puts_atm   = puts[abs(puts["strike"] - atm_strike) < tol]
        if puts_atm.empty: return None, None
        atm_put = puts_atm.iloc[0]
        def mid(row):
            b = float(row.get("bid", 0) or 0)
            a = float(row.get("ask", 0) or 0)
            if b > 0 and a >= b: return (b + a) / 2.0
            lp = float(row.get("lastPrice", 0) or 0)
            return lp if lp > 0 else None
        cm, pm = mid(atm_call), mid(atm_put)
        if cm is None or pm is None: return None, None
        straddle = (cm + pm) * (10.0 if is_spy else 1.0)
        return (round(straddle, 2), round(straddle / spot * 100, 3)) if straddle > 0 else (None, None)
    except Exception:
        return None, None

def calc_gex_profile(calls, puts, spot):
    if calls is None or puts is None or spot is None: return []
    try:
        result = {}
        for _, r in calls.iterrows():
            k = float(r.get("strike", 0))
            result[k] = result.get(k, 0) + float(r.get("openInterest",0) or 0) * float(r.get("gamma",0) or 0) * spot * spot * 100
        for _, r in puts.iterrows():
            k = float(r.get("strike", 0))
            result[k] = result.get(k, 0) - float(r.get("openInterest",0) or 0) * float(r.get("gamma",0) or 0) * spot * spot * 100
        return [{"strike": k, "gex_raw": v, "gex_m": round(v/1e6, 2)} for k, v in sorted(result.items())]
    except Exception:
        return []

def calc_gex_key_levels(gex_data, spot):
    if not gex_data or spot is None: return {}
    try:
        net   = sum(d["gex_raw"] for d in gex_data)
        net_m = round(net / 1e6, 1)
        pos   = net >= 0
        r_color  = "#00CC44" if pos else "#FF4444"
        r_label  = "POSITIVE GAMMA — PINNING ENVIRONMENT" if pos else "NEGATIVE GAMMA — TRENDING / EXPLOSIVE"
        r_detail = (
            "Dealers are net LONG gamma. They buy dips and sell rips. Dampens volatility, pins SPX near high-OI strikes. Best: Iron condors, credit spreads."
            if pos else
            "Dealers are net SHORT gamma. Their hedging AMPLIFIES moves. Rallies run further, selloffs cascade. Best: Long calls/puts, debit spreads."
        )
        above_pos = [d for d in gex_data if d["strike"] >= spot and d["gex_raw"] > 0]
        below_neg = [d for d in gex_data if d["strike"] <= spot and d["gex_raw"] < 0]
        gw = max(above_pos, key=lambda d: d["gex_raw"])["strike"] if above_pos else None
        pw = min(below_neg, key=lambda d: d["gex_raw"])["strike"] if below_neg else None
        cum, gex_flip = 0.0, None
        for d in sorted(gex_data, key=lambda d: d["strike"], reverse=True):
            cum += d["gex_raw"]
            if cum < 0 and d["strike"] <= spot:
                gex_flip = d["strike"]; break
        levels = []
        if gw:
            levels.append({"strike": gw, "type": "GAMMA WALL", "color": "#00CC44", "icon": "🟢",
                "dist_str": f"+{gw-spot:.0f} pts above spot",
                "what_happens": (f"As SPX approaches {gw:,.0f}: dealers short calls SELL stock to delta-hedge. "
                    "Natural ceiling. Price stalls or pins here. Clean break ABOVE triggers short-covering → squeeze to next wall.")})
        if pw:
            levels.append({"strike": pw, "type": "PUT WALL / SUPPORT", "color": "#00AAFF", "icon": "🔵",
                "dist_str": f"-{spot-pw:.0f} pts below spot",
                "what_happens": (f"As SPX approaches {pw:,.0f}: dealers short puts BUY stock to delta-hedge. "
                    "Mechanical support. Watch for bounce. Clean break with no bounce = next put cluster is new target.")})
        if gex_flip:
            levels.append({"strike": gex_flip, "type": "GEX FLIP", "color": "#FF8C00", "icon": "🟠",
                "dist_str": f"-{spot-gex_flip:.0f} pts below spot",
                "what_happens": (f"Regime-change line at {gex_flip:,.0f}. Above: dealers stabilise. Below: dealers amplify. "
                    "Classic breach: initial close below → retest → flush if held below. Most important level in a breakdown.")})
        return {"net_gex_m": net_m, "regime": "POSITIVE" if pos else "NEGATIVE",
                "regime_color": r_color, "regime_label": r_label, "regime_detail": r_detail,
                "gamma_wall": gw, "put_wall": pw, "gex_flip": gex_flip, "levels": levels}
    except Exception:
        return {}

def calc_pcr(calls, puts):
    if calls is None or puts is None: return None, None
    try:
        co = float(calls["openInterest"].fillna(0).sum())
        po = float(puts["openInterest"].fillna(0).sum())
        cv = float(calls["volume"].fillna(0).sum())
        pv = float(puts["volume"].fillna(0).sum())
        return (round(po/co, 2) if co > 0 else None, round(pv/cv, 2) if cv > 0 else None)
    except Exception:
        return None, None

@st.cache_data(ttl=120)
def vix_term_structure():
    vals = {}
    for key, tkr in [("vix9d","^VIX9D"), ("vix","^VIX"), ("vix3m","^VIX3M")]:
        try:
            h = yf.Ticker(tkr).history(period="5d")
            if not h.empty: vals[key] = round(float(h["Close"].iloc[-1]), 2)
        except Exception: pass
    if "vix9d" in vals and "vix" in vals:
        sp = round(vals["vix9d"] - vals["vix"], 2)
        vals["spread_9d_30d"] = sp
        if   sp < -2.0: vals["slope_signal"] = f"CONTANGO ({sp:+.1f}) — 0DTE vol cheap, favour selling premium";  vals["slope_color"] = "#00CC44"
        elif sp >  2.0: vals["slope_signal"] = f"BACKWARDATION ({sp:+.1f}) — near-term fear, 0DTE expensive";      vals["slope_color"] = "#FF4444"
        else:           vals["slope_signal"] = f"FLAT ({sp:+.1f}) — mixed signal, follow price action";             vals["slope_color"] = "#FF8C00"
    if "vix3m" in vals and "vix" in vals:
        vals["long_signal"] = (
            f"INVERTED: VIX3M ({vals['vix3m']}) < VIX ({vals['vix']}) — immediate fear dominant"
            if vals["vix3m"] < vals["vix"] else
            f"NORMAL: VIX3M ({vals['vix3m']}) > VIX ({vals['vix']})")
    return vals

@st.cache_data(ttl=300)
def spx_key_levels(spot):
    if not spot: return {}
    try:
        h = yf.Ticker("^GSPC").history(period="5d")
        if h.empty: return {}
        base   = round(spot / 25) * 25
        rounds = sorted({base-50, base-25, base, base+25, base+50})
        return {
            "prev_close":   round(float(h["Close"].iloc[-2]), 2) if len(h) > 1 else None,
            "prev_high":    round(float(h["High"].iloc[-2]),  2) if len(h) > 1 else None,
            "prev_low":     round(float(h["Low"].iloc[-2]),   2) if len(h) > 1 else None,
            "week_high":    round(float(h["High"].max()), 2),
            "week_low":     round(float(h["Low"].min()),  2),
            "round_levels": rounds,
        }
    except Exception: return {}

def calc_vwap(intraday_df):
    if intraday_df is None or intraday_df.empty: return None
    try:
        vol = intraday_df["Volume"].fillna(0)
        if vol.sum() == 0: return None
        typ  = (intraday_df["High"] + intraday_df["Low"] + intraday_df["Close"]) / 3.0
        vwap = (typ * vol).sum() / vol.sum()
        return round(float(vwap) * 10.0, 2)
    except Exception: return None
