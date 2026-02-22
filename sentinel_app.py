#!/usr/bin/env python3
"""
⚡ SENTINEL — Professional Financial Intelligence Terminal
Bloomberg-style | TradingView Charts | Live Globe | Gemini AI
"""

import streamlit as st
import streamlit.components.v1 as components

try:
    import yfinance as yf
except ImportError:
    st.error("⚠️ Missing: yfinance")
    st.stop()

try:
    import plotly.graph_objects as go
except ImportError:
    st.error("⚠️ Missing: plotly")
    st.stop()

import requests
import pandas as pd
import json
import pathlib
from datetime import datetime, timedelta
import pytz

# ── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SENTINEL",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

PST = pytz.timezone("US/Pacific")

def now_pst():
    return datetime.now(PST).strftime("%Y-%m-%d %H:%M PST")

def now_pst_short():
    return datetime.now(PST).strftime("%H:%M:%S")

# ── BLOOMBERG TERMINAL CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap');

  /* ── Core Terminal Background ── */
  .stApp, [data-testid="stAppViewContainer"] {
    background: #000000 !important;
    color: #FF8C00 !important;
    font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
  }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: #0A0A0A !important;
    border-right: 1px solid #FF6600 !important;
  }
  [data-testid="stSidebar"] * { color: #FF8C00 !important; }

  /* ── Headers ── */
  h1, h2, h3, h4 { 
    color: #FFFFFF !important; 
    font-family: 'IBM Plex Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 2px;
  }

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab-list"] {
    background: #000000;
    border-bottom: 1px solid #FF6600 !important;
    gap: 0;
  }
  .stTabs [data-baseweb="tab"] {
    color: #666666 !important;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
    background: transparent;
    text-transform: uppercase;
  }
  .stTabs [aria-selected="true"] {
    color: #FF6600 !important;
    border-bottom: 2px solid #FF6600 !important;
    background: #0A0A0A !important;
  }
  .stTabs [data-baseweb="tab"]:hover { color: #FF8C00 !important; }

  /* ── Metrics ── */
  [data-testid="stMetric"] {
    background: #0A0A0A;
    border: 1px solid #1A1A1A;
    border-top: 1px solid #FF6600;
    border-radius: 0;
    padding: 8px 10px;
  }
  [data-testid="stMetric"] label {
    color: #888888 !important;
    font-size: 9px !important;
    letter-spacing: 2px;
    text-transform: uppercase;
  }
  [data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-size: 18px !important;
    font-weight: 600 !important;
    font-family: 'IBM Plex Mono', monospace !important;
  }
  [data-testid="stMetricDelta"] { font-size: 11px !important; }

  /* ── Buttons ── */
  .stButton > button {
    background: #0A0A0A !important;
    color: #FF6600 !important;
    border: 1px solid #FF6600 !important;
    border-radius: 0 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 4px 12px;
  }
  .stButton > button:hover {
    background: #FF6600 !important;
    color: #000000 !important;
  }

  /* ── Inputs ── */
  .stTextInput > div > div > input,
  .stTextArea > div > div > textarea,
  .stSelectbox > div > div {
    background: #0A0A0A !important;
    color: #FF8C00 !important;
    border: 1px solid #333333 !important;
    border-radius: 0 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px;
  }
  .stSelectbox > div > div { color: #FF8C00 !important; }

  /* ── DataFrames ── */
  .stDataFrame { 
    background: #000000 !important;
    border: 1px solid #1A1A1A;
  }
  .stDataFrame th {
    background: #0A0A0A !important;
    color: #FF6600 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1px solid #FF6600 !important;
  }
  .stDataFrame td {
    color: #FFFFFF !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px;
    border-bottom: 1px solid #111111 !important;
  }

  /* ── Bloomberg Panel Cards ── */
  .bb-panel {
    background: #0A0A0A;
    border: 1px solid #1A1A1A;
    border-top: 2px solid #FF6600;
    padding: 10px 12px;
    margin: 4px 0;
    font-family: 'IBM Plex Mono', monospace;
  }
  .bb-panel-header {
    color: #FF6600;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    border-bottom: 1px solid #1A1A1A;
    padding-bottom: 6px;
    margin-bottom: 8px;
  }

  /* ── News/Event Cards ── */
  .bb-news {
    background: #050505;
    border-left: 3px solid #FF6600;
    padding: 8px 12px;
    margin: 4px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .bb-news:hover { border-left-color: #FFFFFF; background: #0A0A0A; }
  .bb-news-alert { border-left-color: #FF0000; }
  .bb-news-geo   { border-left-color: #FFFF00; }
  .bb-news-macro { border-left-color: #00AAFF; }
  .bb-news-poly  { border-left-color: #AA44FF; }
  .bb-news-green { border-left-color: #00CC44; }

  .bb-news a {
    color: #FFFFFF;
    text-decoration: none;
    font-weight: 500;
  }
  .bb-news a:hover { color: #FF8C00; text-decoration: underline; }
  .bb-news .bb-meta {
    color: #555555;
    font-size: 9px;
    margin-top: 3px;
    letter-spacing: 1px;
  }

  /* ── Options Chain ── */
  .options-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
  }
  .options-table th {
    background: #111111;
    color: #FF6600;
    padding: 5px 8px;
    text-align: right;
    font-size: 9px;
    letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 1px solid #FF6600;
  }
  .options-table th:first-child { text-align: left; }
  .options-table td {
    padding: 4px 8px;
    text-align: right;
    color: #CCCCCC;
    border-bottom: 1px solid #0D0D0D;
  }
  .options-table td:first-child { color: #FFFFFF; font-weight: 600; text-align: left; }
  .options-table tr:hover td { background: #0A0A0A; }
  .opt-call { color: #00CC44 !important; }
  .opt-put  { color: #FF4444 !important; }
  .opt-itm  { background: rgba(255,102,0,0.06) !important; }
  .opt-high-vol { color: #FF8C00 !important; font-weight: 600; }

  /* ── Insider Transactions ── */
  .insider-card {
    background: #050505;
    border: 1px solid #1A1A1A;
    border-radius: 0;
    padding: 8px 12px;
    margin: 3px 0;
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    gap: 12px;
    align-items: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
  }
  .insider-card:hover { background: #0A0A0A; }
  .insider-name { color: #FFFFFF; font-weight: 600; }
  .insider-buy  { color: #00CC44; font-weight: 700; }
  .insider-sell { color: #FF4444; font-weight: 700; }
  .insider-shares { color: #FF8C00; }
  .insider-date { color: #555555; font-size: 10px; }

  /* ── Polymarket Card ── */
  .poly-card {
    background: #050505;
    border: 1px solid #1A1A1A;
    border-left: 3px solid #AA44FF;
    padding: 10px 12px;
    margin: 4px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    cursor: pointer;
  }
  .poly-card:hover { background: #0A0A0A; border-left-color: #FF6600; }
  .poly-card a {
    color: #FFFFFF;
    text-decoration: none;
    font-weight: 500;
  }
  .poly-card a:hover { color: #FF8C00; }
  .poly-bar-bg {
    height: 4px;
    background: #1A1A1A;
    margin-top: 6px;
    border-radius: 2px;
    overflow: hidden;
  }
  .poly-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #00CC44, #00FF55);
    border-radius: 2px;
    transition: width 0.3s;
  }
  .poly-bar-fill-red {
    background: linear-gradient(90deg, #CC0000, #FF4444);
  }

  /* ── Earnings Card ── */
  .earn-card {
    background: #050505;
    border: 1px solid #1A1A1A;
    border-left: 3px solid #00AAFF;
    padding: 8px 12px;
    margin: 3px 0;
    display: grid;
    grid-template-columns: 80px 1fr auto auto auto;
    gap: 10px;
    align-items: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
  }
  .earn-card:hover { background: #0A0A0A; }
  .earn-ticker { color: #FF6600; font-weight: 700; font-size: 13px; }
  .earn-company { color: #888888; font-size: 10px; }
  .earn-date { color: #FFFFFF; font-weight: 600; }
  .earn-eps-beat { color: #00CC44; }
  .earn-eps-miss { color: #FF4444; }
  .earn-est { color: #888888; font-size: 10px; }

  /* ── Theater Status ── */
  .theater-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 8px;
    margin: 2px 0;
    background: #050505;
    border: 1px solid #111111;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
  }
  .theater-row:hover { background: #0A0A0A; }

  /* ── Bloomberg Header ── */
  .bb-topbar {
    background: #FF6600;
    color: #000000;
    padding: 4px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .bb-logo {
    font-size: 22px;
    font-weight: 900;
    letter-spacing: 4px;
    color: #FFFFFF;
    font-family: 'IBM Plex Mono', monospace;
  }
  .bb-ticker-tape {
    background: #0A0A0A;
    border-top: 1px solid #FF6600;
    border-bottom: 1px solid #1A1A1A;
    padding: 4px 0;
    overflow: hidden;
    white-space: nowrap;
    margin-bottom: 8px;
  }

  /* ── Watchlist row ── */
  .wl-row {
    display: grid;
    grid-template-columns: 80px 110px 90px 90px 80px;
    gap: 8px;
    padding: 5px 8px;
    margin: 1px 0;
    background: #050505;
    border-bottom: 1px solid #0D0D0D;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    align-items: center;
  }
  .wl-row:hover { background: #0A0A0A; }
  .wl-ticker { color: #FF6600; font-weight: 700; }
  .wl-price { color: #FFFFFF; font-weight: 600; }
  .wl-up { color: #00CC44; }
  .wl-down { color: #FF4444; }
  .wl-vol { color: #555555; font-size: 10px; }

  /* ── Sector heatmap cell ── */
  .sector-cell-up   { background: rgba(0, 204, 68, 0.15); border-left: 3px solid #00CC44; }
  .sector-cell-down { background: rgba(255, 68, 68, 0.15); border-left: 3px solid #FF4444; }
  .sector-cell {
    padding: 6px 10px;
    margin: 2px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  /* ── Chat ── */
  .chat-user {
    background: #0A0A0A;
    border: 1px solid #333333;
    border-left: 3px solid #FF6600;
    padding: 10px 14px;
    margin: 6px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
  }
  .chat-ai {
    background: #050505;
    border: 1px solid #1A1A1A;
    border-left: 3px solid #00CC44;
    padding: 10px 14px;
    margin: 6px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    white-space: pre-wrap;
    color: #CCCCCC;
  }

  /* ── Divider ── */
  .bb-divider { border: 0; border-top: 1px solid #1A1A1A; margin: 12px 0; }

  /* ── Hide Streamlit branding ── */
  div[data-testid="stDecoration"], footer, #MainMenu { display: none !important; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: #000000; }
  ::-webkit-scrollbar-thumb { background: #FF6600; border-radius: 2px; }

  /* ── Caption / small text ── */
  .stCaption, .stMarkdown p { font-family: 'IBM Plex Mono', monospace !important; }
  small, .stCaption { color: #555555 !important; font-size: 10px !important; }

  /* ── Expander ── */
  .stExpander { 
    border: 1px solid #1A1A1A !important;
    background: #050505 !important;
    border-radius: 0 !important;
  }
  .stExpander summary { color: #FF8C00 !important; }

  /* ── Warning/info boxes ── */
  .stAlert { 
    font-family: 'IBM Plex Mono', monospace !important;
    border-radius: 0 !important;
  }

  /* Streamlit column gaps */
  [data-testid="column"] { padding: 0 4px !important; }
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ────────────────────────────────────────────────────────────
DEFAULTS = {
    "gemini_key": "", "fred_key": "", "finnhub_key": "",
    "alphavantage_key": "", "newsapi_key": "", "coingecko_key": "",
    "chat_history": [],
    "watchlist": ["SPY", "QQQ", "NVDA", "AAPL", "GLD", "TLT", "BTC-USD"],
    "macro_theses": "", "geo_watch": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="bb-logo">⚡ SENTINEL</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="color:#555;font-size:9px;font-family:\'IBM Plex Mono\',monospace;letter-spacing:1px">{now_pst()}</div>', unsafe_allow_html=True)
    st.markdown('<hr style="border-top:1px solid #FF6600;margin:8px 0">', unsafe_allow_html=True)

    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700;font-family:\'IBM Plex Mono\',monospace">API KEYS</div>', unsafe_allow_html=True)

    with st.expander("🤖 Gemini AI (Required)"):
        st.caption("[Get free key → aistudio.google.com](https://aistudio.google.com/app/apikey)")
        st.session_state.gemini_key = st.text_input("Gemini API Key", value=st.session_state.gemini_key, type="password", key="gin")

    with st.expander("📊 Finnhub + Alpha Vantage"):
        st.caption("[Finnhub → finnhub.io](https://finnhub.io/register)")
        st.session_state.finnhub_key = st.text_input("Finnhub Key", value=st.session_state.finnhub_key, type="password", key="fh")
        st.caption("[Alpha Vantage → alphavantage.co](https://www.alphavantage.co/support/#api-key)")
        st.session_state.alphavantage_key = st.text_input("Alpha Vantage Key", value=st.session_state.alphavantage_key, type="password", key="av")

    with st.expander("📈 FRED (Macro)"):
        st.caption("[fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)")
        st.session_state.fred_key = st.text_input("FRED Key", value=st.session_state.fred_key, type="password", key="fr")

    with st.expander("📰 NewsAPI"):
        st.caption("[newsapi.org](https://newsapi.org/register)")
        st.session_state.newsapi_key = st.text_input("NewsAPI Key", value=st.session_state.newsapi_key, type="password", key="na")

    with st.expander("💰 CoinGecko"):
        st.caption("[coingecko.com](https://www.coingecko.com/en/api/pricing)")
        st.session_state.coingecko_key = st.text_input("CoinGecko Key", value=st.session_state.coingecko_key, type="password", key="cg")

    st.markdown('<hr style="border-top:1px solid #1A1A1A;margin:8px 0">', unsafe_allow_html=True)
    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700;font-family:\'IBM Plex Mono\',monospace">CONNECTION STATUS</div>', unsafe_allow_html=True)

    STATUS = {
        "Yahoo Finance": True, "Polymarket": True, "GDELT": True,
        "Fear & Greed": True, "CoinGecko": True,
        "FRED": bool(st.session_state.fred_key),
        "Finnhub": bool(st.session_state.finnhub_key),
        "Alpha Vantage": bool(st.session_state.alphavantage_key),
        "NewsAPI": bool(st.session_state.newsapi_key),
        "Gemini AI": bool(st.session_state.gemini_key),
    }
    for api, ok in STATUS.items():
        dot = "🟢" if ok else "🔴"
        st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;padding:1px 0">{dot} <span style="color:{"#CCCCCC" if ok else "#555"}">{api}</span></div>', unsafe_allow_html=True)

    st.markdown('<hr style="border-top:1px solid #1A1A1A;margin:8px 0">', unsafe_allow_html=True)
    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700;font-family:\'IBM Plex Mono\',monospace">MY CONTEXT</div>', unsafe_allow_html=True)
    st.session_state.macro_theses = st.text_area("Macro theses", value=st.session_state.macro_theses, placeholder="e.g. Watching Fed pivot...", height=60)
    st.session_state.geo_watch    = st.text_area("Geo watch", value=st.session_state.geo_watch, placeholder="e.g. Red Sea, Taiwan...", height=50)
    wl_raw = st.text_input("Watchlist (comma-separated)", value=",".join(st.session_state.watchlist))
    st.session_state.watchlist = [t.strip().upper() for t in wl_raw.split(",") if t.strip()]

# ── DATA FETCHERS ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def yahoo_quote(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="2d")
        if hist.empty: return None
        price = hist["Close"].iloc[-1]
        prev  = hist["Close"].iloc[-2] if len(hist) > 1 else price
        chg   = price - prev
        pct   = chg / prev * 100
        vol   = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0
        return {"ticker": ticker, "price": round(price, 4), "change": round(chg, 4), "pct": round(pct, 2), "volume": vol}
    except Exception:
        return None

@st.cache_data(ttl=300)
def multi_quotes(tickers):
    return [q for t in tickers if (q := yahoo_quote(t))]

@st.cache_data(ttl=600)
def fred_series(series_id, key, limit=36):
    if not key: return None
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": key, "sort_order": "desc",
                    "limit": limit, "file_type": "json"}, timeout=10)
        obs = r.json().get("observations", [])
        df  = pd.DataFrame(obs)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"]  = pd.to_datetime(df["date"])
        return df.dropna(subset=["value"]).sort_values("date")
    except Exception:
        return None

@st.cache_data(ttl=300)
def polymarket_markets(limit=60):
    try:
        r = requests.get("https://gamma-api.polymarket.com/markets",
            params={"limit": limit, "order": "volume24hr", "ascending": "false", "active": "true"}, timeout=10)
        return r.json()
    except Exception:
        return []

@st.cache_data(ttl=300)
def fear_greed():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except Exception:
        return None, None

@st.cache_data(ttl=600)
def crypto_markets(key=""):
    try:
        headers = {"x-cg-demo-api-key": key} if key else {}
        r = requests.get("https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 15,
                    "page": 1, "price_change_percentage": "24h"},
            headers=headers, timeout=10)
        return r.json()
    except Exception:
        return []

@st.cache_data(ttl=600)
def crypto_global(key=""):
    try:
        headers = {"x-cg-demo-api-key": key} if key else {}
        return requests.get("https://api.coingecko.com/api/v3/global",
            headers=headers, timeout=8).json().get("data", {})
    except Exception:
        return {}

@st.cache_data(ttl=600)
def gdelt_news(query, max_rec=12):
    try:
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": query, "mode": "artlist", "maxrecords": max_rec,
                    "format": "json", "timespan": "24h"}, timeout=12)
        return r.json().get("articles", [])
    except Exception:
        return []

@st.cache_data(ttl=300)
def newsapi_headlines(key, query="stock market finance"):
    if not key: return []
    try:
        r = requests.get("https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt",
                    "pageSize": 10, "apiKey": key}, timeout=10)
        return r.json().get("articles", [])
    except Exception:
        return []

@st.cache_data(ttl=300)
def finnhub_news(key, category="general"):
    if not key: return []
    try:
        return requests.get("https://finnhub.io/api/v1/news",
            params={"category": category, "token": key}, timeout=10).json()[:10]
    except Exception:
        return []

@st.cache_data(ttl=600)
def finnhub_insider(ticker, key):
    if not key: return []
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": ticker, "token": key}, timeout=10)
        return r.json().get("data", [])[:12]
    except Exception:
        return []

@st.cache_data(ttl=300)
def vix_price():
    try:
        h = yf.Ticker("^VIX").history(period="2d")
        return round(h["Close"].iloc[-1], 2) if not h.empty else None
    except Exception:
        return None

@st.cache_data(ttl=600)
def options_chain(ticker):
    try:
        t    = yf.Ticker(ticker)
        exps = t.options
        if not exps: return None, None
        chain = t.option_chain(exps[0])
        cols  = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
        c = chain.calls[[c for c in cols if c in chain.calls.columns]].head(12)
        p = chain.puts[[c  for c in cols if c in chain.puts.columns]].head(12)
        return c, p, exps[0]
    except Exception:
        return None, None, None

@st.cache_data(ttl=600)
def sector_etfs():
    SECTORS = {
        "Technology": "XLK", "Financials": "XLF", "Energy": "XLE",
        "Healthcare": "XLV", "Consumer Staples": "XLP", "Utilities": "XLU",
        "Consumer Disc.": "XLY", "Materials": "XLB", "Comm. Services": "XLC",
        "Real Estate": "XLRE", "Industrials": "XLI"
    }
    rows = []
    for name, tkr in SECTORS.items():
        q = yahoo_quote(tkr)
        if q:
            rows.append({"Sector": name, "ETF": tkr, "Price": q["price"], "Change %": q["pct"]})
    return pd.DataFrame(rows)

@st.cache_data(ttl=1800)
def get_earnings_calendar():
    """Fetch upcoming earnings from multiple tickers"""
    MAJOR = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","JPM","GS","BAC",
             "NFLX","AMD","INTC","CRM","ORCL","V","MA","WMT","XOM","CVX",
             "UNH","JNJ","PFE","ABBV","LLY","BRK-B","HD","DIS","BABA","SHOP"]
    rows = []
    for tkr in MAJOR:
        try:
            t    = yf.Ticker(tkr)
            info = t.info
            name = info.get("shortName", tkr)
            # Next earnings date
            cal = t.calendar
            if cal is not None and not cal.empty:
                if "Earnings Date" in cal.index:
                    ed = cal.loc["Earnings Date"]
                    if hasattr(ed, "__iter__") and not isinstance(ed, str):
                        ed = ed.iloc[0] if len(ed) > 0 else None
                    if ed is not None:
                        try:
                            eps_est = cal.loc["EPS Estimate"].iloc[0] if "EPS Estimate" in cal.index else None
                        except Exception:
                            eps_est = None
                        rows.append({
                            "Ticker": tkr,
                            "Company": name[:22],
                            "EarningsDate": pd.to_datetime(ed).date(),
                            "EPS Est": eps_est,
                            "Sector": info.get("sector","—")[:12],
                        })
        except Exception:
            pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["EarningsDate"])
    df = df.sort_values("EarningsDate")
    return df

def detect_unusual_poly(markets):
    out = []
    for m in markets:
        try:
            v24  = float(m.get("volume24hr", 0) or 0)
            vtot = float(m.get("volume", 0) or 0)
            if vtot > 0 and v24 / vtot > 0.38 and v24 > 5000:
                out.append(m)
        except Exception:
            pass
    return out[:6]

def market_snapshot_str():
    try:
        qs    = multi_quotes(["SPY","QQQ","DXY","GLD","TLT","BTC-USD"])
        parts = [f"{q['ticker']}: ${q['price']:,.2f} ({q['pct']:+.2f}%)" for q in qs]
        v     = vix_price()
        if v: parts.append(f"VIX: {v}")
        fv, fl = fear_greed()
        if fv:  parts.append(f"Crypto F&G: {fv} ({fl})")
        return " | ".join(parts)
    except Exception:
        return ""

# ── GEMINI (with model fallback + ListModels) ─────────────────────────────────
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
]

def list_gemini_models(api_key):
    """List available Gemini models for generateContent"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        models = genai.list_models()
        return [m.name for m in models if "generateContent" in m.supported_generation_methods]
    except Exception as e:
        return [f"Error: {e}"]

def gemini_response(user_msg, history, context=""):
    if not st.session_state.gemini_key:
        return "⚠️ Add your Gemini API key in the sidebar."
    try:
        import google.generativeai as genai
        genai.configure(api_key=st.session_state.gemini_key)

        # Try models in order
        last_err = ""
        for model_name in GEMINI_MODELS:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SENTINEL_PROMPT
                )
                ctx  = ""
                if st.session_state.macro_theses: ctx += f"\nUser macro theses: {st.session_state.macro_theses}"
                if st.session_state.geo_watch:    ctx += f"\nUser geo watch: {st.session_state.geo_watch}"
                if st.session_state.watchlist:    ctx += f"\nWatchlist: {', '.join(st.session_state.watchlist)}"
                if context:                        ctx += f"\nLive market snapshot: {context}"

                gemini_history = []
                for msg in history[-12:]:
                    role = "user" if msg["role"] == "user" else "model"
                    gemini_history.append({"role": role, "parts": [msg["content"]]})

                chat = model.start_chat(history=gemini_history)
                full = f"{ctx}\n\nQuery: {user_msg}" if ctx else user_msg
                return chat.send_message(full).text
            except Exception as e:
                last_err = str(e)
                if "not found" in str(e).lower() or "404" in str(e):
                    continue
                return f"⚠️ Gemini error: {e}"

        return f"⚠️ All Gemini models failed. Last error: {last_err}\n\nAvailable models:\n" + "\n".join(list_gemini_models(st.session_state.gemini_key))
    except ImportError:
        return "⚠️ google-generativeai not installed. Run: pip install google-generativeai"
    except Exception as e:
        return f"⚠️ Error: {e}"

SENTINEL_PROMPT = """
You are SENTINEL — a professional financial and geopolitical intelligence terminal.

PERSONA: Concise, data-first. Bloomberg terminal analyst style. Define jargon on first use.

CAPABILITIES: Macro (CPI/PCE/Fed/yields), Equity analysis, Crypto, Geopolitical intel, Polymarket prediction markets, Cross-asset correlations, Scenario trees.

RULES:
1. Never fabricate data.
2. Always include bear case with bullish ideas.
3. Label confidence: HIGH / MEDIUM / LOW / UNCONFIRMED
4. Separate facts from interpretation.
5. Trace ripple chains: never stop at first-order effects.
6. Everything = research, not financial advice.

OUTPUT FORMATS:
/brief → Full morning briefing
/flash [ticker] → Quick snapshot: price, catalyst, options pulse
/geo [region] → Geopolitical dashboard
/scenario [asset] → Bull/base/bear scenario tree with probabilities
/poly [topic] → Polymarket analysis
/rotate → Sector rotation read
/sentiment → Market sentiment dashboard
/earnings → Upcoming earnings calendar analysis

Always timestamp PST. End trade ideas with: ⚠️ Research only, not financial advice.
""".strip()

# ── CHART THEME (for plotly fallback) ────────────────────────────────────────
CHART = dict(
    paper_bgcolor="#000000", plot_bgcolor="#050505",
    font=dict(color="#FF8C00", family="IBM Plex Mono, Courier New"),
    xaxis=dict(gridcolor="#111111", color="#555555"),
    yaxis=dict(gridcolor="#111111", color="#555555"),
    margin=dict(l=0, r=10, t=24, b=0)
)

def dark_fig(height=300):
    fig = go.Figure()
    fig.update_layout(**CHART, height=height, showlegend=False)
    return fig

# ── TRADINGVIEW WIDGET ────────────────────────────────────────────────────────
def tradingview_chart(symbol, height=450, interval="D", style="1"):
    """Embed a TradingView advanced chart widget"""
    tv_symbol = symbol.replace("-", "")
    if "USD" in tv_symbol and tv_symbol != "AAAUSD":
        tv_symbol = f"COINBASE:{tv_symbol}" if "BTC" in tv_symbol or "ETH" in tv_symbol else tv_symbol
    html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ margin:0; padding:0; background:#000000; overflow:hidden; }}
  .tradingview-widget-container {{ width:100%; height:{height}px; }}
</style>
</head>
<body>
<div class="tradingview-widget-container">
  <div id="tv_chart_container"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "width": "100%",
    "height": {height},
    "symbol": "{symbol}",
    "interval": "{interval}",
    "timezone": "America/Los_Angeles",
    "theme": "dark",
    "style": "{style}",
    "locale": "en",
    "toolbar_bg": "#000000",
    "enable_publishing": false,
    "hide_side_toolbar": false,
    "allow_symbol_change": true,
    "save_image": false,
    "container_id": "tv_chart_container",
    "backgroundColor": "rgba(0, 0, 0, 1)",
    "gridColor": "rgba(30, 30, 30, 1)",
    "studies": ["RSI@tv-basicstudies", "MACD@tv-basicstudies"],
    "show_popup_button": true,
    "popup_width": "1000",
    "popup_height": "650"
  }});
  </script>
</div>
</body>
</html>"""
    return html

def tradingview_mini(symbol, height=180):
    html = f"""
<!DOCTYPE html>
<html>
<head><style>body{{margin:0;padding:0;background:#000;overflow:hidden}}</style></head>
<body>
<div class="tradingview-widget-container">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
  {{
    "symbol": "{symbol}",
    "width": "100%",
    "height": {height},
    "locale": "en",
    "dateRange": "3M",
    "colorTheme": "dark",
    "trendLineColor": "rgba(255, 102, 0, 1)",
    "underLineColor": "rgba(255, 102, 0, 0.1)",
    "underLineBottomColor": "rgba(0, 0, 0, 0)",
    "isTransparent": true,
    "autosize": false,
    "largeChartUrl": ""
  }}
  </script>
</div>
</body>
</html>"""
    return html

# ── HELPERS ─────────────────────────────────────────────────────────────────

def fmt_price(p):
    return f"${p:,.4f}" if p and p < 5 else f"${p:,.2f}" if p else "—"

def fmt_pct(p, color=True):
    if p is None: return "—"
    sign = "+" if p >= 0 else ""
    if color:
        cls = "wl-up" if p >= 0 else "wl-down"
        return f'<span class="{cls}">{sign}{p:.2f}%</span>'
    return f"{sign}{p:.2f}%"

def pct_color(v):
    return "#00CC44" if v >= 0 else "#FF4444"

def render_watchlist_row(q):
    color = "#00CC44" if q["pct"] >= 0 else "#FF4444"
    arrow = "▲" if q["pct"] >= 0 else "▼"
    vol_k = f"{q['volume']/1e6:.1f}M" if q['volume'] > 1e6 else f"{q['volume']/1e3:.0f}K"
    return f"""
<div class="wl-row">
  <span class="wl-ticker">{q['ticker']}</span>
  <span class="wl-price">{fmt_price(q['price'])}</span>
  <span style="color:{color};font-size:12px">{arrow} {abs(q['pct']):.2f}%</span>
  <span style="color:{color};font-size:11px">{'+' if q['change']>=0 else ''}{q['change']:.2f}</span>
  <span class="wl-vol">{vol_k}</span>
</div>"""

def render_options_table(df, side="calls", current_price=None):
    if df is None or df.empty:
        return "<p style='color:#555;font-family:IBM Plex Mono;font-size:11px'>No data</p>"
    
    color_cls = "opt-call" if side == "calls" else "opt-put"
    rows_html = ""
    for _, row in df.iterrows():
        strike = row.get("strike", 0)
        last   = row.get("lastPrice", 0)
        bid    = row.get("bid", 0)
        ask    = row.get("ask", 0)
        vol    = int(row.get("volume", 0) or 0)
        oi     = int(row.get("openInterest", 0) or 0)
        iv     = row.get("impliedVolatility", 0)
        
        # ITM highlight
        itm = ""
        if current_price:
            if side == "calls" and strike < current_price: itm = " opt-itm"
            if side == "puts"  and strike > current_price: itm = " opt-itm"
        
        high_vol = " opt-high-vol" if vol and oi and oi > 0 and vol / oi > 0.5 else ""
        
        rows_html += f"""
        <tr class="{itm}">
          <td class="{color_cls}">{strike:.1f}</td>
          <td>{last:.2f}</td>
          <td>{bid:.2f}</td>
          <td>{ask:.2f}</td>
          <td class="{high_vol}">{vol:,}</td>
          <td>{oi:,}</td>
          <td>{iv:.1%}</td>
        </tr>"""
    
    return f"""
<table class="options-table">
  <thead>
    <tr>
      <th>Strike</th><th>Last</th><th>Bid</th><th>Ask</th>
      <th>Volume</th><th>OI</th><th>IV</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>"""

def render_insider_cards(data):
    if not data:
        return "<p style='color:#555;font-family:IBM Plex Mono;font-size:11px'>No insider data. Add Finnhub key.</p>"
    
    code_map = {"P": ("BUY", "insider-buy"), "S": ("SELL", "insider-sell"),
                "A": ("AWARD", "insider-buy"), "D": ("DISPOSE", "insider-sell")}
    
    html = ""
    for tx in data[:10]:
        name    = tx.get("name", "Unknown")[:20]
        chg     = int(tx.get("change", 0) or 0)
        shares  = int(tx.get("share", 0) or 0)
        date    = str(tx.get("transactionDate", ""))[:10]
        code    = tx.get("transactionCode", "?")
        lbl, cls = code_map.get(code, (code, "insider-date"))
        chg_str = f"{chg:+,}"
        
        html += f"""
<div class="insider-card">
  <span class="insider-name">{name}</span>
  <span class="{cls}">{lbl}</span>
  <span class="insider-shares">{chg_str} sh</span>
  <span class="insider-date">{date}</span>
</div>"""
    return html

def render_poly_card(m, clickable=True):
    title  = m.get("question", m.get("title", "Unknown"))
    url    = m.get("url", "") or m.get("marketMakerAddress", "")
    # Try to build polymarket URL
    slug   = m.get("slug", "")
    if slug:
        url = f"https://polymarket.com/event/{slug}"
    
    v24    = float(m.get("volume24hr", 0) or 0)
    vtot   = float(m.get("volume", 0) or 0)
    
    prob_html = ""
    outcomes   = m.get("outcomes", [])
    out_prices = m.get("outcomePrices", [])
    if outcomes and out_prices:
        try:
            prices = json.loads(out_prices) if isinstance(out_prices, str) else out_prices
            for i, outcome in enumerate(outcomes[:2]):
                if i < len(prices):
                    p    = float(prices[i]) * 100
                    bar_cls = "" if p >= 50 else " poly-bar-fill-red"
                    prob_html += f"""
            <div style="display:flex;align-items:center;gap:8px;margin-top:4px">
              <span style="color:{'#00CC44' if p>=50 else '#FF4444'};font-size:10px;min-width:40px">{p:.0f}%</span>
              <span style="color:#777;font-size:10px;flex:1">{outcome}</span>
              <div class="poly-bar-bg" style="width:80px">
                <div class="poly-bar-fill{bar_cls}" style="width:{p:.0f}%"></div>
              </div>
            </div>"""
        except Exception:
            pass
    
    if url:
        title_html = f'<a href="{url}" target="_blank">{title[:85]}</a>'
    else:
        title_html = f'<span style="color:#CCCCCC">{title[:85]}</span>'
    
    return f"""
<div class="poly-card">
  <div style="font-size:12px;font-weight:600">{title_html}</div>
  {prob_html}
  <div style="color:#444;font-size:9px;margin-top:5px;letter-spacing:1px">
    24H VOL: ${v24:,.0f} &nbsp;|&nbsp; TOTAL: ${vtot:,.0f}
  </div>
</div>"""

def render_news_card(title, url, source, date_str, card_class="bb-news"):
    if url and url != "#":
        t_html = f'<a href="{url}" target="_blank">{title[:95]}</a>'
    else:
        t_html = f'<span style="color:#CCCCCC">{title[:95]}</span>'
    
    return f"""
<div class="{card_class}">
  {t_html}
  <div class="bb-meta">{source} &nbsp;|&nbsp; {date_str}</div>
</div>"""

# ── BLOOMBERG HEADER ─────────────────────────────────────────────────────────
st.markdown(f"""
<div class="bb-topbar">
  <div style="display:flex;align-items:center;gap:16px">
    <span style="font-size:18px;font-weight:900;letter-spacing:4px">SENTINEL</span>
    <span style="font-size:10px;color:#333;background:#000;padding:2px 8px">TERMINAL</span>
    <span style="font-size:10px;color:#000;opacity:0.7">PROFESSIONAL INTELLIGENCE</span>
  </div>
  <div style="font-size:10px;color:#000;opacity:0.7">{now_pst()} &nbsp;|&nbsp; LIVE</div>
</div>
""", unsafe_allow_html=True)

# ── TABS ─────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "BRIEF", "MARKETS", "MACRO", "CRYPTO",
    "POLYMARKET", "GEO", "EARNINGS", "SENTINEL AI"
])

# ════════════════════════════════════════
# TAB 0 — MORNING BRIEF
# ════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="bb-panel-header">⚡ SENTINEL MORNING BRIEF</div>', unsafe_allow_html=True)

    if st.button("↺ REFRESH ALL DATA"):
        st.cache_data.clear()
        st.rerun()

    # ── Market Snapshot ──
    KEY_TICKERS = {
        "SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones",
        "IWM": "Russell 2K", "^TNX": "10Y Yield", "DXY": "USD Index",
        "GLD": "Gold", "CL=F": "WTI Crude", "BTC-USD": "Bitcoin"
    }
    qs   = multi_quotes(list(KEY_TICKERS.keys()))
    cols = st.columns(len(qs))
    for col, q in zip(cols, qs):
        label = KEY_TICKERS.get(q["ticker"], q["ticker"])
        delta_color = "normal" if q["pct"] >= 0 else "inverse"
        with col:
            st.metric(label, fmt_price(q["price"]), delta=f"{q['pct']:+.2f}%")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown('<div class="bb-panel-header">⚡ SENTIMENT PULSE</div>', unsafe_allow_html=True)
        s1, s2, s3 = st.columns(3)
        v = vix_price()
        with s1:
            if v:
                lbl = "LOW FEAR" if v < 15 else ("MODERATE" if v < 25 else ("HIGH FEAR" if v < 35 else "PANIC"))
                st.metric("VIX", f"{v:.2f}", delta=lbl)
        fg_val, fg_lbl = fear_greed()
        with s2:
            if fg_val:
                st.metric("Crypto F&G", f"{fg_val}/100", delta=fg_lbl)
        with s3:
            if v:
                posture = "RISK-ON" if v < 18 else ("NEUTRAL" if v < 25 else "RISK-OFF")
                st.metric("SENTINEL Posture", posture)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Watchlist ──
        st.markdown('<div class="bb-panel-header">👁 WATCHLIST</div>', unsafe_allow_html=True)
        st.markdown("""
<div class="wl-row" style="border-bottom:1px solid #FF6600;opacity:0.7">
  <span style="color:#FF6600;font-size:9px;letter-spacing:1px">TICKER</span>
  <span style="color:#FF6600;font-size:9px;letter-spacing:1px">PRICE</span>
  <span style="color:#FF6600;font-size:9px;letter-spacing:1px">CHG%</span>
  <span style="color:#FF6600;font-size:9px;letter-spacing:1px">CHG$</span>
  <span style="color:#FF6600;font-size:9px;letter-spacing:1px">VOLUME</span>
</div>""", unsafe_allow_html=True)
        wl_qs = multi_quotes(st.session_state.watchlist)
        wl_html = "".join(render_watchlist_row(q) for q in wl_qs)
        st.markdown(wl_html, unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Sector Pulse ──
        st.markdown('<div class="bb-panel-header">🔄 SECTOR PULSE</div>', unsafe_allow_html=True)
        sec_df = sector_etfs()
        if not sec_df.empty:
            sec_sorted = sec_df.sort_values("Change %", ascending=False)
            for _, row in sec_sorted.iterrows():
                pct   = row["Change %"]
                cls   = "sector-cell-up" if pct >= 0 else "sector-cell-down"
                color = "#00CC44" if pct >= 0 else "#FF4444"
                bar   = min(abs(pct) * 8, 60)
                st.markdown(f"""
<div class="sector-cell {cls}">
  <span style="font-size:11px;color:#FFFFFF">{row['Sector']}</span>
  <span style="font-size:10px;color:#555">{row['ETF']}</span>
  <span style="font-size:12px;font-weight:700;color:{color}">{'+' if pct>=0 else ''}{pct:.2f}%</span>
</div>""", unsafe_allow_html=True)

    with col_r:
        # ── Polymarket Top ──
        st.markdown('<div class="bb-panel-header">🎲 POLYMARKET TOP MARKETS</div>', unsafe_allow_html=True)
        poly = polymarket_markets(20)
        for m in poly[:5]:
            st.markdown(render_poly_card(m), unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── GDELT Geo Headlines ──
        st.markdown('<div class="bb-panel-header">🌍 GEO WATCH</div>', unsafe_allow_html=True)
        geo_arts = gdelt_news("geopolitical conflict oil market", max_rec=6)
        for art in geo_arts[:5]:
            t   = art.get("title", "")[:80]
            u   = art.get("url", "#")
            dom = art.get("domain", "GDELT")
            sd  = art.get("seendate", "")
            d   = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
            st.markdown(render_news_card(t, u, dom, d, "bb-news bb-news-geo"), unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 1 — MARKETS
# ════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="bb-panel-header">📊 MARKETS — EQUITIES | OPTIONS | ROTATION</div>', unsafe_allow_html=True)

    # Flash lookup
    flash_col, _ = st.columns([2, 3])
    with flash_col:
        flash_ticker = st.text_input("⚡ TICKER LOOKUP", placeholder="NVDA, AAPL, TSLA, SPY…", key="flash")

    if flash_ticker:
        tkr = flash_ticker.upper().strip()
        q   = yahoo_quote(tkr)
        if q:
            st.markdown(f'<div class="bb-panel-header">⚡ FLASH: {tkr}</div>', unsafe_allow_html=True)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("PRICE",   fmt_price(q["price"]), delta=f"{q['pct']:+.2f}%")
            m2.metric("CHANGE",  f"${q['change']:+.4f}")
            m3.metric("VOLUME",  f"{q['volume']:,}")
            m4.metric("1D CHG%", f"{q['pct']:+.2f}%")

            # TradingView Chart
            st.markdown('<div class="bb-panel-header">CHART — TRADINGVIEW</div>', unsafe_allow_html=True)
            components.html(tradingview_chart(tkr, height=460), height=465, scrolling=False)

            # Options + Insider side by side
            opt_col, ins_col = st.columns([3, 2])

            with opt_col:
                st.markdown('<div class="bb-panel-header">📋 OPTIONS CHAIN — NEAREST EXPIRY</div>', unsafe_allow_html=True)
                calls, puts, exp_date = options_chain(tkr)
                if calls is not None:
                    st.markdown(f'<div style="color:#555;font-size:9px;font-family:IBM Plex Mono;margin-bottom:6px">EXPIRY: {exp_date} &nbsp;|&nbsp; CURRENT PRICE: {fmt_price(q["price"])}</div>', unsafe_allow_html=True)
                    cc, pc = st.columns(2)
                    with cc:
                        st.markdown('<div style="color:#00CC44;font-size:9px;font-weight:700;letter-spacing:2px;margin-bottom:4px">CALLS ▲</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(calls, "calls", q["price"]), unsafe_allow_html=True)
                    with pc:
                        st.markdown('<div style="color:#FF4444;font-size:9px;font-weight:700;letter-spacing:2px;margin-bottom:4px">PUTS ▼</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(puts, "puts", q["price"]), unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:IBM Plex Mono;font-size:11px">Options data unavailable for this ticker.</p>', unsafe_allow_html=True)

            with ins_col:
                st.markdown('<div class="bb-panel-header">🔍 INSIDER TRANSACTIONS</div>', unsafe_allow_html=True)
                if st.session_state.finnhub_key:
                    ins = finnhub_insider(tkr, st.session_state.finnhub_key)
                    st.markdown(render_insider_cards(ins), unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:IBM Plex Mono;font-size:11px">Add Finnhub key in sidebar to see insider transactions.</p>', unsafe_allow_html=True)

        else:
            st.error(f"Could not fetch data for {tkr}. Check ticker symbol.")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # Sector Heatmap
    st.markdown('<div class="bb-panel-header">🔄 SECTOR ROTATION HEATMAP</div>', unsafe_allow_html=True)
    sec_df = sector_etfs()
    if not sec_df.empty:
        sec_sorted = sec_df.sort_values("Change %")
        colors     = [pct_color(x) for x in sec_sorted["Change %"]]
        fig2 = go.Figure(go.Bar(
            x=sec_sorted["Change %"], y=sec_sorted["Sector"], orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=sec_sorted["Change %"].apply(lambda x: f"{x:+.2f}%"),
            textposition="outside", textfont=dict(color="#FF8C00", size=10)
        ))
        fig2.update_layout(**CHART, height=350)
        fig2.update_layout(xaxis_title="% Change", margin=dict(l=0, r=70, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)

        top_sec   = sec_df.nlargest(1, "Change %")["Sector"].values[0]
        DEFENSIVE = {"Utilities", "Consumer Staples", "Healthcare"}
        OFFENSIVE = {"Technology", "Consumer Disc.", "Comm. Services"}
        if top_sec in DEFENSIVE:
            sig = f"⚠️ DEFENSIVE ROTATION — {top_sec} leading. Late-cycle signal. Consider de-risking."
            bc  = "#1A0000"
        elif top_sec in OFFENSIVE:
            sig = f"✅ OFFENSIVE ROTATION — {top_sec} leading. Risk appetite intact."
            bc  = "#001A00"
        elif top_sec == "Energy":
            sig = "⚡ ENERGY LEADING — Inflation regime. Watch CPI."
            bc  = "#1A1000"
        else:
            sig = f"◦ MIXED SIGNAL — {top_sec} leading. No clear rotation direction."
            bc  = "#0A0A0A"
        st.markdown(f'<div style="background:{bc};border:1px solid #333;border-left:3px solid #FF6600;padding:8px 12px;font-family:IBM Plex Mono;font-size:11px;color:#CCCCCC">{sig}</div>', unsafe_allow_html=True)

    # Market News
    if st.session_state.finnhub_key:
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-panel-header">📰 MARKET NEWS — FINNHUB</div>', unsafe_allow_html=True)
        fh_news = finnhub_news(st.session_state.finnhub_key, "general")
        for art in fh_news[:6]:
            title = art.get("headline", "")[:90]
            url   = art.get("url", "#")
            src   = art.get("source", "")
            ts    = art.get("datetime", 0)
            d     = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
            st.markdown(render_news_card(title, url, src, d, "bb-news bb-news-macro"), unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 2 — MACRO
# ════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="bb-panel-header">📈 MACRO — FRED DATA DASHBOARD</div>', unsafe_allow_html=True)

    if not st.session_state.fred_key:
        st.markdown("""
<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;padding:16px;font-family:IBM Plex Mono;font-size:12px;color:#FF8C00">
⚠️ FRED API key required for macro data.<br><br>
<a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank" style="color:#FF6600">Get your free FRED key in 30 seconds →</a>
</div>""", unsafe_allow_html=True)
    else:
        YC = {"3M": "DTB3", "2Y": "DGS2", "5Y": "DGS5", "10Y": "DGS10", "30Y": "DGS30"}
        yc_vals = {}
        for lbl, code in YC.items():
            df = fred_series(code, st.session_state.fred_key, 5)
            if df is not None and not df.empty:
                yc_vals[lbl] = df["value"].iloc[-1]

        mc1, mc2 = st.columns([2, 2])
        with mc1:
            st.markdown('<div class="bb-panel-header">📉 YIELD CURVE</div>', unsafe_allow_html=True)
            if yc_vals:
                fig_yc = dark_fig(240)
                fig_yc.add_trace(go.Scatter(
                    x=list(yc_vals.keys()), y=list(yc_vals.values()),
                    mode="lines+markers", line=dict(color="#FF6600", width=2.5),
                    marker=dict(size=8, color="#FF6600"), fill="tozeroy",
                    fillcolor="rgba(255,102,0,0.08)"
                ))
                fig_yc.add_hline(y=0, line_dash="dash", line_color="#FF4444", opacity=0.6)
                fig_yc.update_layout(yaxis_title="Yield (%)")
                st.plotly_chart(fig_yc, use_container_width=True)
                if "2Y" in yc_vals and "10Y" in yc_vals:
                    spread = yc_vals["10Y"] - yc_vals["2Y"]
                    if spread < 0:
                        st.markdown(f'<div style="background:#1A0000;border-left:3px solid #FF0000;padding:8px 12px;font-family:IBM Plex Mono;font-size:11px;color:#FF8C00">⚠️ INVERTED: 10Y-2Y = {spread:.2f}%. Historical recession signal. Avg lead: 12-18 months.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="background:#001A00;border-left:3px solid #00CC44;padding:8px 12px;font-family:IBM Plex Mono;font-size:11px;color:#CCCCCC">✅ NORMAL: 10Y-2Y = +{spread:.2f}%</div>', unsafe_allow_html=True)

        with mc2:
            st.markdown('<div class="bb-panel-header">📊 KEY INDICATORS</div>', unsafe_allow_html=True)
            MACRO = {
                "CPI": "CPIAUCSL", "Core PCE": "PCEPILFE",
                "Fed Funds": "FEDFUNDS", "Unemployment": "UNRATE",
                "M2 Supply": "M2SL", "HY Spread": "BAMLH0A0HYM2",
            }
            for name, code in MACRO.items():
                df = fred_series(code, st.session_state.fred_key, 3)
                if df is not None and not df.empty:
                    val  = df["value"].iloc[-1]
                    prev = df["value"].iloc[-2] if len(df) > 1 else val
                    chg  = val - prev
                    st.metric(name, f"{val:.2f}", delta=f"{chg:+.2f}")

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-panel-header">📈 10Y TREASURY TREND</div>', unsafe_allow_html=True)
        ty_df = fred_series("DGS10", st.session_state.fred_key, 36)
        if ty_df is not None and not ty_df.empty:
            fig_ty = dark_fig(220)
            fig_ty.add_trace(go.Scatter(
                x=ty_df["date"], y=ty_df["value"], fill="tozeroy",
                line=dict(color="#FF6600", width=2),
                fillcolor="rgba(255,102,0,0.08)"
            ))
            fig_ty.update_layout(yaxis_title="Yield (%)")
            st.plotly_chart(fig_ty, use_container_width=True)

        # TradingView charts for treasuries
        st.markdown('<div class="bb-panel-header">TREASURY LIVE CHARTS — TRADINGVIEW</div>', unsafe_allow_html=True)
        tc1, tc2 = st.columns(2)
        with tc1:
            components.html(tradingview_mini("TVC:US10Y", 200), height=205)
        with tc2:
            components.html(tradingview_mini("TVC:US02Y", 200), height=205)

# ════════════════════════════════════════
# TAB 3 — CRYPTO
# ════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="bb-panel-header">💰 CRYPTO — COINGECKO + TRADINGVIEW</div>', unsafe_allow_html=True)

    gdata = crypto_global(st.session_state.coingecko_key)
    if gdata:
        g1, g2, g3, g4 = st.columns(4)
        total_cap = gdata.get("total_market_cap", {}).get("usd", 0)
        btc_dom   = gdata.get("market_cap_percentage", {}).get("btc", 0)
        eth_dom   = gdata.get("market_cap_percentage", {}).get("eth", 0)
        fv, fl    = fear_greed()
        g1.metric("Total Market Cap", f"${total_cap/1e12:.2f}T")
        g2.metric("BTC Dominance",    f"{btc_dom:.1f}%")
        g3.metric("ETH Dominance",    f"{eth_dom:.1f}%")
        if fv: g4.metric("Fear & Greed",  f"{fv}/100", delta=fl)

        if btc_dom > 55:
            st.markdown('<div style="background:#1A0000;border-left:3px solid #FF4444;padding:8px 12px;font-family:IBM Plex Mono;font-size:11px;color:#FF8C00">⚠️ BTC Dominance >55% — Altcoin pressure. Risk-off within crypto.</div>', unsafe_allow_html=True)
        elif btc_dom < 45:
            st.markdown('<div style="background:#001A00;border-left:3px solid #00CC44;padding:8px 12px;font-family:IBM Plex Mono;font-size:11px;color:#CCCCCC">✅ BTC Dominance <45% — Altcoin season conditions.</div>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    cr1, cr2 = st.columns([2, 3])
    with cr1:
        st.markdown('<div class="bb-panel-header">💹 TOP 15 BY MARKET CAP</div>', unsafe_allow_html=True)
        cdata = crypto_markets(st.session_state.coingecko_key)
        rows = []
        for c in cdata:
            if not c.get("current_price"): continue
            pct = c.get("price_change_percentage_24h", 0) or 0
            rows.append({
                "COIN": f"{c['symbol'].upper()}",
                "PRICE": fmt_price(c["current_price"]),
                "24H %": f"{'+'if pct>=0 else ''}{pct:.2f}%",
                "MCap": f"${c['market_cap']/1e9:.1f}B",
            })
        if rows:
            rows_html = ""
            for r in rows:
                color = "#00CC44" if "+" in r["24H %"] else "#FF4444"
                rows_html += f"""
<div style="display:grid;grid-template-columns:60px 100px 70px 80px;gap:8px;padding:4px 8px;border-bottom:1px solid #0D0D0D;font-family:IBM Plex Mono;font-size:11px;align-items:center">
  <span style="color:#FF6600;font-weight:700">{r['COIN']}</span>
  <span style="color:#FFFFFF">{r['PRICE']}</span>
  <span style="color:{color};font-weight:600">{r['24H %']}</span>
  <span style="color:#555">{r['MCap']}</span>
</div>"""
            st.markdown(rows_html, unsafe_allow_html=True)

    with cr2:
        st.markdown('<div class="bb-panel-header">📈 BTC/USD — TRADINGVIEW</div>', unsafe_allow_html=True)
        components.html(tradingview_chart("COINBASE:BTCUSD", height=340), height=345, scrolling=False)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-panel-header">📈 ETH/USD — TRADINGVIEW</div>', unsafe_allow_html=True)
    components.html(tradingview_chart("COINBASE:ETHUSD", height=320), height=325, scrolling=False)

# ════════════════════════════════════════
# TAB 4 — POLYMARKET
# ════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="bb-panel-header">🎲 POLYMARKET — PREDICTION INTELLIGENCE & UNUSUAL FLOW</div>', unsafe_allow_html=True)

    poly_col, guide_col = st.columns([3, 1])

    with poly_col:
        poly_search = st.text_input("🔍 FILTER MARKETS", placeholder="Fed rate, oil, Taiwan, gold, recession…")
        all_poly     = polymarket_markets(60)
        filtered     = [m for m in all_poly if not poly_search or
                        poly_search.lower() in str(m.get("question","")).lower()] if poly_search else all_poly

        # Unusual activity
        unusual = detect_unusual_poly(all_poly)
        if unusual:
            st.markdown('<div class="bb-panel-header" style="color:#FF4444;border-top-color:#FF4444">🚨 UNUSUAL ACTIVITY DETECTED</div>', unsafe_allow_html=True)
            st.markdown('<p style="color:#555;font-family:IBM Plex Mono;font-size:9px">Markets where 24h vol ≥38% of total — signals recent surge in positioning</p>', unsafe_allow_html=True)
            for m in unusual:
                title = m.get("question", m.get("title", ""))[:80]
                v24   = float(m.get("volume24hr", 0) or 0)
                vtot  = float(m.get("volume", 0) or 0)
                ratio = v24 / vtot * 100 if vtot > 0 else 0
                slug  = m.get("slug", "")
                url   = f"https://polymarket.com/event/{slug}" if slug else "#"
                t_html = f'<a href="{url}" target="_blank" style="color:#FF4444">{title}</a>'
                st.markdown(f"""
<div style="background:#0D0000;border:1px solid #FF0000;border-left:4px solid #FF0000;padding:10px 12px;margin:4px 0;font-family:IBM Plex Mono;font-size:11px">
  🚨 {t_html}<br>
  <span style="color:#FF6600">24h: ${v24:,.0f} ({ratio:.0f}% of total)</span> &nbsp;|&nbsp; <span style="color:#555">Total: ${vtot:,.0f}</span>
</div>""", unsafe_allow_html=True)

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        st.markdown(f'<div class="bb-panel-header">📋 ACTIVE MARKETS — SORTED BY 24H VOLUME ({len(filtered)} shown)</div>', unsafe_allow_html=True)
        for m in filtered[:25]:
            st.markdown(render_poly_card(m), unsafe_allow_html=True)

    with guide_col:
        st.markdown('<div class="bb-panel-header">📖 HOW TO READ</div>', unsafe_allow_html=True)
        st.markdown("""
<div style="background:#050505;border:1px solid #1A1A1A;padding:12px;font-family:IBM Plex Mono;font-size:10px;color:#888;line-height:1.8">
<span style="color:#FF6600;font-weight:700">UNUSUAL TRIGGERS</span><br>
• 24h vol ≥38% of total<br>
• Sudden prob shift<br>
• Heavy pre-event flow<br>
• New market w/ instant liquidity<br><br>
<span style="color:#FF6600;font-weight:700">CONVERGENCE SIGNAL</span><br>
Polymarket + FRED pointing same direction = strongest free signal<br><br>
<span style="color:#00CC44">GREEN bar</span> = YES/higher<br>
<span style="color:#FF4444">RED bar</span> = NO/lower<br><br>
<span style="color:#555">⚠️ Prediction markets = crowd odds. Not guaranteed. Use alongside macro + geo data.</span>
</div>""", unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 5 — GEO (Globe)
# ════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="bb-panel-header">🌍 GEOPOLITICAL INTELLIGENCE — LIVE GLOBE + GDELT</div>', unsafe_allow_html=True)
    st.markdown('<p style="color:#555;font-family:IBM Plex Mono;font-size:10px">Drag to rotate · Scroll to zoom · Hover markers for intel · Events auto-updated from GDELT</p>', unsafe_allow_html=True)

    globe_path = pathlib.Path(__file__).parent / "globe.html"
    if globe_path.exists():
        globe_html = globe_path.read_text(encoding="utf-8")
        components.html(globe_html, height=600, scrolling=False)
    else:
        st.error("globe.html not found in same folder as sentinel_app.py")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    THEATERS = {
        "Middle East + Oil + Hormuz": "Middle East Iran oil Hormuz",
        "China + Taiwan + Semiconductors": "China Taiwan semiconductor chips trade",
        "Russia + Ukraine + Energy": "Russia Ukraine energy grain NATO",
        "Africa + Cobalt + Lithium + Coup": "Africa cobalt lithium coup Sahel",
        "Red Sea + Suez + Shipping": "Red Sea Suez shipping Houthi container",
        "South China Sea + Trade": "South China Sea shipping trade",
    }

    geo_col1, geo_col2 = st.columns([3, 1])

    with geo_col1:
        theater_sel = st.selectbox("📡 THEATER FEED", list(THEATERS.keys()) + ["Custom search…"])
        custom_q    = ""
        if theater_sel == "Custom search…":
            custom_q = st.text_input("Custom GDELT query")
        query = custom_q if custom_q else THEATERS.get(theater_sel, "")
        if query:
            st.markdown(f'<div class="bb-panel-header">GDELT FEED — {query.upper()}</div>', unsafe_allow_html=True)
            arts = gdelt_news(query, max_rec=12)
            for art in arts:
                t   = art.get("title", "")[:90]
                u   = art.get("url", "#")
                dom = art.get("domain", "GDELT")
                sd  = art.get("seendate", "")
                d   = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
                st.markdown(render_news_card(t, u, dom, d, "bb-news bb-news-geo"), unsafe_allow_html=True)

            if st.session_state.newsapi_key:
                st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
                st.markdown('<div class="bb-panel-header">NEWSAPI LAYER</div>', unsafe_allow_html=True)
                for art in newsapi_headlines(st.session_state.newsapi_key, query)[:5]:
                    title = art.get("title", "")
                    if not title or "[Removed]" in title: continue
                    u   = art.get("url", "#")
                    src = art.get("source", {}).get("name", "")
                    pub = art.get("publishedAt", "")[:10]
                    st.markdown(render_news_card(title, u, src, pub, "bb-news bb-news-macro"), unsafe_allow_html=True)

    with geo_col2:
        st.markdown('<div class="bb-panel-header">⚠️ THEATERS</div>', unsafe_allow_html=True)
        THEATER_STATUS = {
            "Middle East": ("CRITICAL", "#FF0000"),
            "Ukraine": ("ACTIVE", "#FF4444"),
            "Red Sea": ("DISRUPTED", "#FF4444"),
            "Sahel": ("ELEVATED", "#FF8C00"),
            "Hormuz": ("ELEVATED", "#FF8C00"),
            "Taiwan": ("MONITORING", "#FFFF00"),
            "S.China Sea": ("MONITORING", "#FFFF00"),
        }
        for name, (status, color) in THEATER_STATUS.items():
            st.markdown(f"""
<div class="theater-row">
  <span style="color:#CCCCCC">{name}</span>
  <span style="color:{color};font-size:9px;font-weight:700">{status}</span>
</div>""", unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-panel-header">📖 CONFIDENCE</div>', unsafe_allow_html=True)
        for label, desc, color in [
            ("HIGH", "Multiple confirmed sources", "#00CC44"),
            ("MEDIUM", "Limited sources", "#FF8C00"),
            ("LOW", "Single source", "#FFFF00"),
            ("UNCONFIRMED", "Unverified", "#555555"),
        ]:
            st.markdown(f'<div style="font-family:IBM Plex Mono;font-size:10px;padding:3px 0"><span style="color:{color};font-weight:700">{label}</span> <span style="color:#444">{desc}</span></div>', unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 6 — EARNINGS TRACKER
# ════════════════════════════════════════
with tabs[6]:
    st.markdown('<div class="bb-panel-header">📅 EARNINGS TRACKER — UPCOMING & RECENT</div>', unsafe_allow_html=True)

    earn_col1, earn_col2 = st.columns([3, 2])

    with earn_col1:
        st.markdown('<div class="bb-panel-header">UPCOMING EARNINGS CALENDAR</div>', unsafe_allow_html=True)
        
        with st.spinner("Fetching earnings calendar…"):
            earn_df = get_earnings_calendar()

        if earn_df.empty:
            st.markdown('<p style="color:#555;font-family:IBM Plex Mono;font-size:11px">No upcoming earnings found. Yahoo Finance may be rate-limiting. Try again shortly.</p>', unsafe_allow_html=True)
        else:
            today = datetime.now().date()
            
            # Group by upcoming days
            for i, (_, row) in enumerate(earn_df.iterrows()):
                ed      = row["EarningsDate"]
                days    = (ed - today).days if ed > today else 0
                badge   = f"TODAY" if days == 0 else (f"IN {days}D" if days > 0 else "RECENT")
                b_color = "#FF6600" if days == 0 else ("#00AAFF" if days < 7 else "#555")
                eps_str = f"${row['EPS Est']:.2f}" if pd.notna(row.get("EPS Est")) else "—"
                
                st.markdown(f"""
<div class="earn-card">
  <span class="earn-ticker">{row['Ticker']}</span>
  <div>
    <div class="earn-company">{row['Company']}</div>
    <div style="color:#555;font-size:9px">{row['Sector']}</div>
  </div>
  <span style="color:{b_color};font-size:9px;font-weight:700;letter-spacing:1px">{badge}</span>
  <span class="earn-date">{ed}</span>
  <span class="earn-est">EPS est: {eps_str}</span>
</div>""", unsafe_allow_html=True)

    with earn_col2:
        # Earnings TradingView quick lookup
        st.markdown('<div class="bb-panel-header">📈 QUICK EARNINGS CHART</div>', unsafe_allow_html=True)
        earn_tkr = st.text_input("Ticker for earnings chart", placeholder="NVDA, AAPL…", key="earn_chart")
        if earn_tkr:
            et = earn_tkr.upper().strip()
            components.html(tradingview_chart(et, height=320), height=325, scrolling=False)
            
            # Earnings history from yfinance
            try:
                t_obj  = yf.Ticker(et)
                income = t_obj.quarterly_financials
                if income is not None and not income.empty:
                    st.markdown('<div class="bb-panel-header" style="margin-top:10px">QUARTERLY FINANCIALS</div>', unsafe_allow_html=True)
                    rev  = income.loc["Total Revenue"] / 1e9 if "Total Revenue" in income.index else None
                    ni   = income.loc["Net Income"] / 1e6   if "Net Income" in income.index else None
                    cols = list(income.columns[:4])
                    for col in cols:
                        col_str = str(col)[:10]
                        rv  = f"${rev[col]:.1f}B"  if rev is not None and col in rev.index else "—"
                        net = f"${ni[col]:.0f}M"   if ni  is not None and col in ni.index  else "—"
                        color = "#00CC44" if ni is not None and col in ni.index and ni[col] > 0 else "#FF4444"
                        st.markdown(f"""
<div style="display:flex;justify-content:space-between;padding:5px 8px;border-bottom:1px solid #0D0D0D;font-family:IBM Plex Mono;font-size:11px">
  <span style="color:#888">{col_str}</span>
  <span style="color:#CCCCCC">Rev: {rv}</span>
  <span style="color:{color}">NI: {net}</span>
</div>""", unsafe_allow_html=True)
            except Exception:
                pass

        # Earnings season key dates
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-panel-header">📊 EARNINGS SEASON GUIDE</div>', unsafe_allow_html=True)
        st.markdown("""
<div style="background:#050505;border:1px solid #1A1A1A;padding:12px;font-family:IBM Plex Mono;font-size:10px;color:#888;line-height:2">
<span style="color:#FF6600;font-weight:700">Q1 SEASON</span> &nbsp; Jan–Feb<br>
<span style="color:#FF6600;font-weight:700">Q2 SEASON</span> &nbsp; Apr–May<br>
<span style="color:#FF6600;font-weight:700">Q3 SEASON</span> &nbsp; Jul–Aug<br>
<span style="color:#FF6600;font-weight:700">Q4 SEASON</span> &nbsp; Oct–Nov<br><br>
<span style="color:#00CC44">BEAT</span> = EPS > consensus<br>
<span style="color:#FF4444">MISS</span> = EPS < consensus<br>
<span style="color:#FFFF00">IN-LINE</span> = within ±2%<br><br>
<span style="color:#555">Watch guidance revisions<br>more than the print itself.</span>
</div>""", unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 7 — SENTINEL AI
# ════════════════════════════════════════
with tabs[7]:
    st.markdown('<div class="bb-panel-header">🤖 SENTINEL AI — POWERED BY GOOGLE GEMINI</div>', unsafe_allow_html=True)

    if not st.session_state.gemini_key:
        st.markdown("""
<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;padding:16px;font-family:IBM Plex Mono;font-size:12px;color:#FF8C00">
⚠️ Gemini API key required to activate SENTINEL AI.<br><br>
<a href="https://aistudio.google.com/app/apikey" target="_blank" style="color:#FF6600">Get a free key at Google AI Studio →</a><br><br>
<span style="color:#555">Once activated, SENTINEL AI provides:<br>
• /brief — Morning intelligence briefing<br>
• /flash NVDA — Rapid stock analysis<br>
• /geo Red Sea — Geopolitical dashboard<br>
• /scenario Gold — Bull/base/bear scenarios<br>
• /poly Fed — Polymarket analysis<br>
• /rotate — Sector rotation read<br>
• /earnings — Earnings calendar analysis</span>
</div>""", unsafe_allow_html=True)
    else:
        # List models button
        if st.button("🔍 LIST AVAILABLE GEMINI MODELS"):
            with st.spinner("Fetching model list…"):
                model_list = list_gemini_models(st.session_state.gemini_key)
            st.markdown('<div class="bb-panel-header">AVAILABLE MODELS</div>', unsafe_allow_html=True)
            for m in model_list:
                st.markdown(f'<div style="font-family:IBM Plex Mono;font-size:11px;padding:2px 0;color:#FF8C00">{m}</div>', unsafe_allow_html=True)
            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # Welcome
        if not st.session_state.chat_history:
            st.markdown("""
<div style="background:#001A00;border:1px solid #1A1A1A;border-left:4px solid #00CC44;padding:14px;font-family:IBM Plex Mono;font-size:12px;color:#CCCCCC;line-height:1.8">
⚡ SENTINEL AI ONLINE<br><br>
Try: <span style="color:#FF6600">/brief</span> &nbsp; <span style="color:#FF6600">/flash NVDA</span> &nbsp; <span style="color:#FF6600">/scenario Gold</span> &nbsp; <span style="color:#FF6600">/geo Red Sea</span> &nbsp; <span style="color:#FF6600">/poly Fed</span><br>
Or ask anything in plain English. Live market data injected into every response.
</div>""", unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">▶ &nbsp;{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                content = msg["content"].replace("<", "&lt;").replace(">", "&gt;")
                st.markdown(f'<div class="chat-ai">⚡ SENTINEL<br><br>{content}</div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        inp_col, btn_col = st.columns([5, 1])
        with inp_col:
            user_input = st.text_input("QUERY SENTINEL…",
                placeholder="/brief  |  /flash TSLA  |  /scenario Gold  |  or plain English",
                key="chat_inp", label_visibility="collapsed")
        with btn_col:
            send = st.button("⚡ SEND", use_container_width=True)

        st.markdown('<div style="color:#555;font-size:9px;font-family:IBM Plex Mono;margin-bottom:4px">QUICK COMMANDS</div>', unsafe_allow_html=True)
        qb = st.columns(7)
        QUICK = {
            "BRIEF": "/brief",
            "ROTATE": "/rotate",
            "SENTIMENT": "/sentiment",
            "POLY FED": "/poly Fed rate cut",
            "RED SEA": "/geo Red Sea",
            "SCENARIO BTC": "/scenario Bitcoin",
            "EARNINGS": "/earnings",
        }
        for col, (label, cmd) in zip(qb, QUICK.items()):
            with col:
                if st.button(label, use_container_width=True, key=f"qb_{label}"):
                    st.session_state.chat_history.append({"role": "user", "content": cmd})
                    with st.spinner("⚡ SENTINEL processing…"):
                        resp = gemini_response(cmd, st.session_state.chat_history[:-1], market_snapshot_str())
                    st.session_state.chat_history.append({"role": "assistant", "content": resp})
                    st.rerun()

        cc, dc = st.columns([1, 1])
        with cc:
            if st.button("🗑 CLEAR CHAT"):
                st.session_state.chat_history = []
                st.rerun()

        if (send or user_input) and user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.spinner("⚡ SENTINEL processing…"):
                resp = gemini_response(user_input, st.session_state.chat_history[:-1], market_snapshot_str())
            st.session_state.chat_history.append({"role": "assistant", "content": resp})
            st.rerun()

# ── FOOTER ───────────────────────────────────────────────────────────────────
st.markdown('<hr style="border-top:1px solid #1A1A1A;margin:16px 0">', unsafe_allow_html=True)
st.markdown(f"""
<div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:#333;text-align:center;letter-spacing:1px">
SENTINEL TERMINAL &nbsp;|&nbsp; {now_pst()} &nbsp;|&nbsp; 
Yahoo Finance · FRED · Polymarket · GDELT · CoinGecko · Finnhub · NewsAPI · TradingView · Gemini<br>
For research purposes only. Not financial advice.
</div>
""", unsafe_allow_html=True)
