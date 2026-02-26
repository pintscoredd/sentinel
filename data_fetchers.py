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
    """Get SPX-equivalent spot and VWAP by scaling SPY x10."""
    snap = get_stock_snapshot("SPY")
    if not snap:
        return None
    return {
        "spot": round(snap["price"] * 10, 2),
        "vwap": round(snap["vwap"] * 10, 2),
        "open": round(snap["open"] * 10, 2),
        "high": round(snap["high"] * 10, 2),
        "low": round(snap["low"] * 10, 2),
        "volume": snap["volume"],
    }


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
    """GEX at strike K = OI * gamma * S^2 * 100. Calls +, Puts -. Returns {strike: $M}."""
    gex = {}
    if spot <= 0:
        return gex
    for opt in chain:
        k = opt["strike"]
        raw_gex = opt.get("oi", 0) * abs(opt.get("gamma", 0)) * (spot ** 2) * 100
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


