#!/usr/bin/env python3
"""SENTINEL — Bloomberg Professional Intelligence Terminal v3"""

import streamlit as st
import streamlit.components.v1 as components

try:
    import yfinance as yf
except ImportError:
    st.error("Missing: yfinance — check requirements.txt"); st.stop()

try:
    import plotly.graph_objects as go
    import plotly.express as px
except ImportError:
    st.error("Missing: plotly"); st.stop()

import requests, pandas as pd, json, pathlib, math
from datetime import datetime, timedelta
import pytz

st.set_page_config(page_title="SENTINEL", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")
PST = pytz.timezone("US/Pacific")
def now_pst(): return datetime.now(PST).strftime("%Y-%m-%d %H:%M PST")
def now_short(): return datetime.now(PST).strftime("%H:%M:%S")

# ════════════════════════════════════════════════════════════════════════════════
# BLOOMBERG TERMINAL CSS — 1:1 accurate
# ════════════════════════════════════════════════════════════════════════════════
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&display=swap');
:root {
  --blk:#000000; --bg1:#080808; --bg2:#0D0D0D; --bg3:#111111;
  --org:#FF6600; --org2:#FF8C00; --org3:#FF4500;
  --wht:#FFFFFF; --txt:#CCCCCC; --dim:#888888; --muted:#444444; --ghost:#222222;
  --grn:#00CC44; --red:#FF4444; --yel:#FFCC00; --blu:#00AAFF; --pur:#AA44FF;
  --mono:'IBM Plex Mono','Courier New',monospace;
}
*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: var(--blk) !important; color: var(--txt) !important;
  font-family: var(--mono) !important;
}
[data-testid="stHeader"] { background: var(--blk) !important; }
[data-testid="stSidebar"] {
  background: var(--bg1) !important;
  border-right: 1px solid var(--org) !important;
}
[data-testid="stSidebar"] * { font-family: var(--mono) !important; font-size: 11px !important; }
[data-testid="stSidebar"] label { color: var(--org2) !important; }

/* TABS — Bloomberg style: flat, uppercase, orange underline on active */
.stTabs [data-baseweb="tab-list"] {
  background: var(--blk); border-bottom: 1px solid var(--org) !important; gap: 0; padding: 0;
}
.stTabs [data-baseweb="tab"] {
  color: var(--muted) !important; font-family: var(--mono) !important;
  font-size: 11px !important; font-weight: 700 !important; letter-spacing: 1px !important;
  padding: 7px 14px !important; border-bottom: 2px solid transparent !important;
  border-right: 1px solid var(--ghost) !important; background: transparent !important;
  text-transform: uppercase; border-radius: 0 !important;
}
.stTabs [aria-selected="true"] {
  color: var(--org) !important; background: var(--bg1) !important;
  border-bottom: 2px solid var(--org) !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--org2) !important; }

/* METRICS */
[data-testid="stMetric"] {
  background: var(--bg1) !important; border: 1px solid var(--ghost) !important;
  border-top: 2px solid var(--org) !important; border-radius: 0 !important; padding: 8px 10px !important;
}
[data-testid="stMetric"] label { color: var(--dim) !important; font-size: 9px !important; letter-spacing: 2px !important; text-transform: uppercase !important; }
[data-testid="stMetricValue"] { color: var(--wht) !important; font-size: 18px !important; font-weight: 700 !important; font-family: var(--mono) !important; }
[data-testid="stMetricDelta"] { font-size: 11px !important; font-family: var(--mono) !important; }

/* BUTTONS */
.stButton > button {
  background: var(--bg1) !important; color: var(--org) !important;
  border: 1px solid var(--org) !important; border-radius: 0 !important;
  font-family: var(--mono) !important; font-size: 10px !important; font-weight: 700 !important;
  letter-spacing: 1px !important; text-transform: uppercase !important; padding: 4px 12px !important;
}
.stButton > button:hover { background: var(--org) !important; color: var(--blk) !important; }

/* INPUTS */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
  background: var(--bg2) !important; color: var(--org2) !important;
  border: 1px solid var(--muted) !important; border-radius: 0 !important;
  font-family: var(--mono) !important; font-size: 12px !important;
}
.stSelectbox > div > div { color: var(--org2) !important; }

/* EXPANDER */
.stExpander { border: 1px solid var(--ghost) !important; background: var(--bg1) !important; border-radius: 0 !important; }
.stExpander summary { color: var(--org2) !important; font-family: var(--mono) !important; }

/* SCROLLBAR */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--blk); }
::-webkit-scrollbar-thumb { background: var(--org); }

/* HIDE BRANDING */
div[data-testid="stDecoration"], footer, #MainMenu,
[data-testid="stToolbar"] { display: none !important; }

/* MOVE CONTENT UP — reduce default Streamlit top padding */
section.main > div.block-container {
  padding-top: 0.25rem !important;
  padding-bottom: 1rem !important;
}
[data-testid="stAppViewContainer"] > section.main {
  padding-top: 0 !important;
}

/* ─── BLOOMBERG COMPONENT STYLES ─── */
.bb-bar {
  background: var(--org); color: var(--blk);
  padding: 4px 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px;
  display: flex; justify-content: space-between; align-items: center;
  font-family: var(--mono);
}
.bb-ph {
  color: var(--org); font-size: 9px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; border-bottom: 1px solid var(--ghost);
  padding-bottom: 5px; margin-bottom: 8px; font-family: var(--mono);
}
.bb-panel {
  background: var(--bg1); border: 1px solid var(--ghost);
  border-top: 2px solid var(--org); padding: 10px 12px; margin: 4px 0;
  font-family: var(--mono);
}
.bb-divider { border: 0; border-top: 1px solid var(--ghost); margin: 10px 0; }

/* WATCHLIST */
.wl-hdr {
  display: grid; grid-template-columns: 75px 110px 90px 85px 80px 60px;
  gap: 6px; padding: 4px 8px; border-bottom: 1px solid var(--org);
  font-family: var(--mono); font-size: 9px; color: var(--org); letter-spacing: 1px;
}
.wl-row {
  display: grid; grid-template-columns: 75px 110px 90px 85px 80px 60px;
  gap: 6px; padding: 5px 8px; border-bottom: 1px solid var(--bg3);
  font-family: var(--mono); font-size: 12px; align-items: center;
}
.wl-row:hover { background: var(--bg2); }
.wl-ticker { color: var(--org); font-weight: 700; }
.wl-price  { color: var(--wht); font-weight: 600; }
.up { color: var(--grn); } .dn { color: var(--red); }
.wl-vol { color: var(--muted); font-size: 10px; }

/* NEWS */
.bb-news {
  background: var(--bg1); border-left: 3px solid var(--org);
  padding: 9px 12px; margin: 4px 0; font-family: var(--mono); cursor: pointer;
  transition: border-color 0.15s;
}
.bb-news:hover { border-left-color: var(--wht); background: var(--bg2); }
.bb-news a { color: var(--wht); text-decoration: none; font-size: 13px; font-weight: 500; line-height: 1.5; }
.bb-news a:hover { color: var(--org2); text-decoration: underline; }
.bb-meta { color: var(--muted); font-size: 10px; margin-top: 4px; letter-spacing: 0.5px; }
.bb-news-geo  { border-left-color: #FFFF00; }
.bb-news-macro{ border-left-color: var(--blu); }
.bb-news-poly { border-left-color: var(--pur); }
.bb-news-red  { border-left-color: var(--red); }

/* POLYMARKET */
.poly-card {
  background: var(--bg1); border: 1px solid var(--ghost); border-left: 3px solid var(--pur);
  padding: 11px 13px; margin: 5px 0; font-family: var(--mono); font-size: 13px;
}
.poly-card:hover { background: var(--bg2); border-left-color: var(--org); }
.poly-card a { color: var(--wht); text-decoration: none; font-weight: 600; }
.poly-card a:hover { color: var(--org2); }
.poly-status-active   { color: var(--grn); font-size: 9px; font-weight: 700; letter-spacing: 1px; }
.poly-status-resolved { color: var(--yel); font-size: 9px; font-weight: 700; letter-spacing: 1px; }
.poly-status-closed   { color: var(--red); font-size: 9px; font-weight: 700; letter-spacing: 1px; }
.poly-unusual-yes { color: var(--grn); font-size: 10px; font-weight: 700; }
.poly-unusual-no  { color: var(--red); font-size: 10px; font-weight: 700; }

/* OPTIONS CHAIN */
.opt-tbl { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 11px; }
.opt-tbl th {
  background: var(--bg3); color: var(--org); padding: 5px 7px;
  text-align: right; font-size: 9px; letter-spacing: 1px; text-transform: uppercase;
  border-bottom: 1px solid var(--org);
}
.opt-tbl th:first-child { text-align: left; }
.opt-tbl td { padding: 4px 7px; text-align: right; color: var(--txt); border-bottom: 1px solid var(--bg3); }
.opt-tbl td:first-child { text-align: left; font-weight: 600; }
.opt-tbl tr:hover td { background: var(--bg2); }
.opt-call { color: var(--grn) !important; }
.opt-put  { color: var(--red) !important; }
.opt-itm  { background: rgba(255,102,0,0.07) !important; }
.opt-hvol { color: var(--org2) !important; font-weight: 600 !important; }

/* INSIDER */
.ins-card {
  background: var(--bg1); border: 1px solid var(--ghost);
  border-left: 3px solid var(--muted);
  padding: 8px 12px; margin: 3px 0; font-family: var(--mono);
}
.ins-card.buy  { border-left-color: var(--grn); }
.ins-card.sell { border-left-color: var(--red); }
.ins-card:hover { background: var(--bg2); }
.ins-name  { color: var(--wht); font-weight: 700; font-size: 12px; }
.ins-role  { color: var(--org2); font-size: 10px; }
.ins-buy   { color: var(--grn); font-weight: 700; font-size: 12px; }
.ins-sell  { color: var(--red); font-weight: 700; font-size: 12px; }
.ins-meta  { color: var(--muted); font-size: 10px; }

/* SECTOR CELL */
.sec-cell {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 10px; margin: 2px 0; font-family: var(--mono); font-size: 11px;
}
.sec-cell.up { background: rgba(0,204,68,0.08); border-left: 3px solid var(--grn); }
.sec-cell.dn { background: rgba(255,68,68,0.08); border-left: 3px solid var(--red); }

/* GAINERS/LOSERS - wider grid */
.mover-row {
  display: grid; grid-template-columns: 70px 105px 80px 80px 80px;
  gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--bg3);
  font-family: var(--mono); font-size: 12px; align-items: center; width:100%;
}
.mover-row:hover { background: var(--bg2); }

/* FUTURES ROW */
.fut-row {
  display: grid; grid-template-columns: 90px 130px 120px 75px 85px 85px;
  gap: 6px; padding: 5px 10px; border-bottom: 1px solid var(--bg3);
  font-family: var(--mono); font-size: 12px; align-items: center; width:100%;
}
.fut-row:hover { background: var(--bg2); }

/* THEATER */
.theater-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 8px; margin: 2px 0; background: var(--bg1);
  border: 1px solid var(--bg3); font-family: var(--mono); font-size: 10px;
}

/* CHAT */
.chat-user {
  background: var(--bg2); border: 1px solid var(--muted); border-left: 3px solid var(--org);
  padding: 10px 14px; margin: 6px 0; font-family: var(--mono); font-size: 12px;
}
.chat-ai {
  background: var(--bg1); border: 1px solid var(--ghost); border-left: 3px solid var(--grn);
  padding: 10px 14px; margin: 6px 0; font-family: var(--mono); font-size: 12px;
  white-space: pre-wrap; color: var(--txt); line-height: 1.7;
}

/* WATCHLIST MANAGE */
.wl-manage { background: var(--bg2); border: 1px solid var(--ghost); padding: 8px 12px; margin: 4px 0; }

/* F&G GAUGE */
.fg-gauge {
  background: var(--bg1); border: 1px solid var(--ghost); border-top: 2px solid var(--org);
  padding: 10px; font-family: var(--mono); text-align: center;
}
.fg-num { font-size: 32px; font-weight: 700; }
.fg-lbl { font-size: 11px; letter-spacing: 2px; margin-top: 4px; }

/* EARN */
.earn-card {
  background: var(--bg1); border: 1px solid var(--ghost); border-left: 3px solid var(--blu);
  padding: 10px 14px; margin: 3px 0; display: grid;
  grid-template-columns: 85px 1fr auto auto auto;
  gap: 12px; align-items: center; font-family: var(--mono); font-size: 11px;
}
.earn-card:hover { background: var(--bg2); }
.earn-ticker { color: var(--org); font-weight: 700; font-size: 16px; }
.earn-date { color: var(--wht); font-weight: 700; font-size: 13px; }

/* CAPS */
[data-testid="column"] { padding: 0 4px !important; }
small, .stCaption { color: var(--muted) !important; font-size: 10px !important; }
.stMarkdown p { font-family: var(--mono) !important; }
h1,h2,h3,h4 { color: var(--org) !important; font-family: var(--mono) !important; text-transform: uppercase; letter-spacing: 2px; }
</style>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════════════
DEFAULTS = {
    "gemini_key":"", "fred_key":"", "finnhub_key":"",
    "newsapi_key":"", "coingecko_key":"",
    "chat_history":[],
    "watchlist":["SPY","QQQ","NVDA","AAPL","GLD","TLT","BTC-USD"],
    "macro_theses":"", "geo_watch":"",
    "wl_add_input":"", "api_panel_open": True,  # Open by default
}
for k,v in DEFAULTS.items():
    if k not in st.session_state: st.session_state[k]=v

# ════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"""
<div style="background:var(--org,#FF6600);padding:6px 10px;margin-bottom:10px">
  <div style="color:#000;font-size:18px;font-weight:900;letter-spacing:4px;font-family:monospace">⚡ SENTINEL</div>
  <div style="color:#000;font-size:9px;opacity:0.6">{now_pst()}</div>
</div>""", unsafe_allow_html=True)

    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700;margin-bottom:6px">🔑 API KEYS</div>', unsafe_allow_html=True)
    with st.expander("🤖 Gemini AI — Required", expanded=not bool(st.session_state.gemini_key)):
        st.caption("[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)")
        st.session_state.gemini_key = st.text_input("Gemini Key", value=st.session_state.gemini_key, type="password", key="gk")
    with st.expander("📊 Finnhub"):
        st.caption("[finnhub.io/register](https://finnhub.io/register)")
        st.session_state.finnhub_key = st.text_input("Finnhub Key", value=st.session_state.finnhub_key, type="password", key="fhk")
    with st.expander("📈 FRED Macro"):
        st.caption("[fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)")
        st.session_state.fred_key = st.text_input("FRED Key", value=st.session_state.fred_key, type="password", key="frk")
    with st.expander("📰 NewsAPI"):
        st.caption("[newsapi.org/register](https://newsapi.org/register)")
        st.session_state.newsapi_key = st.text_input("NewsAPI Key", value=st.session_state.newsapi_key, type="password", key="nak")
    with st.expander("💰 CoinGecko"):
        st.caption("[coingecko.com](https://www.coingecko.com/en/api/pricing)")
        st.session_state.coingecko_key = st.text_input("CoinGecko Key", value=st.session_state.coingecko_key, type="password", key="cgk")

    st.markdown('<hr style="border-top:1px solid #222;margin:8px 0">', unsafe_allow_html=True)
    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700">STATUS</div>', unsafe_allow_html=True)

    for api, ok in [
        ("Yahoo Finance",True),("Polymarket",True),("GDELT",True),
        ("FRED", bool(st.session_state.fred_key)),
        ("Finnhub", bool(st.session_state.finnhub_key)),
        ("NewsAPI", bool(st.session_state.newsapi_key)),
        ("Gemini AI", bool(st.session_state.gemini_key)),
    ]:
        dot = "🟢" if ok else "🔴"
        c = "#CCCCCC" if ok else "#444"
        st.markdown(f'<div style="font-family:monospace;font-size:10px;padding:1px 0">{dot} <span style="color:{c}">{api}</span></div>', unsafe_allow_html=True)

    st.markdown('<hr style="border-top:1px solid #222;margin:8px 0">', unsafe_allow_html=True)
    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700">MY CONTEXT</div>', unsafe_allow_html=True)
    st.session_state.macro_theses = st.text_area("Macro theses", value=st.session_state.macro_theses, placeholder="Watching Fed pivot...", height=55)
    st.session_state.geo_watch    = st.text_area("Geo watch",    value=st.session_state.geo_watch,    placeholder="Red Sea, Taiwan...",   height=45)

# ════════════════════════════════════════════════════════════════════
# DATA FETCHERS
# ════════════════════════════════════════════════════════════════════

def _safe_float(v, default=0.0):
    try:
        f = float(v) if v is not None else default
        return default if (math.isnan(f) or math.isinf(f)) else f
    except: return default

def _safe_int(v):
    try:
        f = float(v) if v is not None else 0.0
        return 0 if (math.isnan(f) or math.isinf(f)) else int(f)
    except: return 0

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

@st.cache_data(ttl=300)
def yahoo_quote(ticker):
    # Map problematic tickers
    TICKER_MAP = {"DXY":"DX-Y.NYB", "$DXY":"DX-Y.NYB"}
    t = TICKER_MAP.get(ticker, ticker)
    try:
        h = yf.Ticker(t).history(period="2d")
        if h.empty: return None
        price = h["Close"].iloc[-1]; prev = h["Close"].iloc[-2] if len(h)>1 else price
        chg = price-prev; pct = chg/prev*100; vol = int(h["Volume"].iloc[-1]) if "Volume" in h.columns else 0
        return {"ticker":ticker,"price":round(price,2),"change":round(chg,2),"pct":round(pct,2),"volume":vol}
    except: return None

@st.cache_data(ttl=120)
def get_futures():
    """Fetch key futures contracts"""
    FUTURES = [
        ("ES=F","S&P 500 Fut"),("NQ=F","Nasdaq Fut"),("YM=F","Dow Fut"),
        ("RTY=F","Russell Fut"),("ZN=F","10Y Bond Fut"),("CL=F","WTI Crude"),
        ("GC=F","Gold"),("SI=F","Silver"),("NG=F","Nat Gas"),
        ("ZW=F","Wheat"),("ZC=F","Corn"),("DX=F","USD Index"),
    ]
    rows=[]
    for ticker, name in FUTURES:
        try:
            h=yf.Ticker(ticker).history(period="2d")
            if h.empty: continue
            price=h["Close"].iloc[-1]; prev=h["Close"].iloc[-2] if len(h)>1 else price
            chg=price-prev; pct=chg/prev*100
            rows.append({"ticker":ticker,"name":name,"price":round(price,2),
                          "change":round(chg,2),"pct":round(pct,2)})
        except: pass
    return rows

@st.cache_data(ttl=300)
def get_heatmap_data():
    """Fetch S&P sector heatmap data for FinViz-style display"""
    SECTOR_STOCKS = {
        "Technology":["AAPL","MSFT","NVDA","AVGO","META","ORCL","AMD","INTC","QCOM","TXN","ADBE","CRM","INTU","IBM","ACN"],
        "Healthcare":["UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","PFE","DHR","BMY","ISRG","GILD","MDT","CVS","CI"],
        "Financials":["JPM","BAC","WFC","GS","MS","BLK","C","AXP","COF","PGR","ICE","CME","SPGI","V","MA"],
        "Consumer Disc":["AMZN","TSLA","HD","MCD","NKE","LOW","BKNG","TJX","SBUX","MAR","TGT","ROST","ORLY","DHI"],
        "Comm Svcs":["GOOGL","META","DIS","NFLX","T","VZ","CMCSA","TMUS","EA","TTWO"],
        "Industrials":["GE","RTX","CAT","HON","UNP","LMT","DE","WM","NSC","ITW","ETN","PH","GD","BA"],
        "Energy":["XOM","CVX","COP","SLB","EOG","PSX","MPC","OXY","VLO","HAL","DVN","BKR"],
        "Consumer Stap":["WMT","PG","KO","PEP","PM","MO","CL","GIS","KHC","KMB","SYY"],
        "Utilities":["NEE","DUK","SO","AEP","D","EXC","PCG","SRE","XEL","CEG"],
        "Materials":["LIN","APD","ECL","SHW","NEM","FCX","NUE","VMC","ALB","MOS"],
        "Real Estate":["PLD","AMT","CCI","EQIX","PSA","SPG","WELL","O","DLR","AVB"],
    }
    rows=[]
    for sector, tickers in SECTOR_STOCKS.items():
        for tkr in tickers:
            q=yahoo_quote(tkr)
            if q: rows.append({"ticker":tkr,"sector":sector,"pct":q["pct"],"price":q["price"],"change":q["change"]})
    return rows

@st.cache_data(ttl=300)
def multi_quotes(tickers):
    return [q for t in tickers if (q:=yahoo_quote(t))]

@st.cache_data(ttl=600)
def fred_series(series_id, key, limit=36):
    if not key: return None
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id":series_id,"api_key":key,"sort_order":"desc","limit":limit,"file_type":"json"},timeout=10)
        df = pd.DataFrame(r.json().get("observations",[]))
        df["value"] = pd.to_numeric(df["value"],errors="coerce")
        df["date"]  = pd.to_datetime(df["date"])
        return df.dropna(subset=["value"]).sort_values("date")
    except: return None

@st.cache_data(ttl=300)
def polymarket_events(limit=60):
    """Fetch from EVENTS endpoint — has correct slugs for URLs"""
    try:
        r = requests.get("https://gamma-api.polymarket.com/events",
            params={"limit":limit,"order":"volume","ascending":"false","active":"true"},timeout=10)
        return r.json()
    except: return []

@st.cache_data(ttl=300)
def polymarket_markets(limit=60):
    try:
        r = requests.get("https://gamma-api.polymarket.com/markets",
            params={"limit":limit,"order":"volume24hr","ascending":"false","active":"true"},timeout=10)
        return r.json()
    except: return []

@st.cache_data(ttl=300)
def fear_greed_crypto():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1",timeout=8).json()
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except: return None, None

def calc_stock_fear_greed():
    """Calculate stock market fear & greed from VIX + momentum"""
    try:
        v = yahoo_quote("^VIX")
        spy = yahoo_quote("SPY")
        if not v: return None, None
        vix = v["price"]
        # VIX component (inverted — low VIX = greed)
        vix_score = max(0, min(100, 100 - (vix - 10) / 30 * 100))
        # Momentum component
        mom_score = 50
        if spy:
            h = yf.Ticker("SPY").history(period="3mo")
            if not h.empty and len(h) > 60:
                current = h["Close"].iloc[-1]; ma60 = h["Close"].iloc[-60:].mean()
                mom_score = 75 if current > ma60*1.02 else (25 if current < ma60*0.98 else 50)
        score = int(vix_score * 0.6 + mom_score * 0.4)
        if score >= 75: label = "Extreme Greed"
        elif score >= 55: label = "Greed"
        elif score >= 45: label = "Neutral"
        elif score >= 25: label = "Fear"
        else: label = "Extreme Fear"
        return score, label
    except: return None, None

@st.cache_data(ttl=600)
def crypto_markets(key=""):
    try:
        headers = {"x-cg-demo-api-key":key} if key else {}
        r = requests.get("https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency":"usd","order":"market_cap_desc","per_page":20,"page":1,"price_change_percentage":"24h"},
            headers=headers,timeout=10)
        return r.json()
    except: return []

@st.cache_data(ttl=600)
def crypto_global(key=""):
    try:
        headers = {"x-cg-demo-api-key":key} if key else {}
        return requests.get("https://api.coingecko.com/api/v3/global",headers=headers,timeout=8).json().get("data",{})
    except: return {}

def _is_english(text):
    if not text: return False
    return sum(1 for c in text if ord(c)<128) / max(len(text),1) > 0.72

@st.cache_data(ttl=600)
def gdelt_news(query, max_rec=15):
    """Fetch from GDELT with multiple endpoint fallbacks"""
    # Try V2 artlist first, then V2 timelinevol, then older format
    endpoints = [
        {"url":"https://api.gdeltproject.org/api/v2/doc/doc",
         "params":{"query":query+" sourcelang:english","mode":"artlist","maxrecords":max_rec,
                   "format":"json","timespan":"72h"}},
        {"url":"https://api.gdeltproject.org/api/v2/doc/doc",
         "params":{"query":query+" sourcelang:english","mode":"artlist","maxrecords":max_rec,
                   "format":"json","timespan":"168h"}},  # fallback to 7 days
    ]
    for ep in endpoints:
        try:
            r = requests.get(ep["url"], params=ep["params"], timeout=18)
            if r.status_code != 200: continue
            data = r.json()
            arts = data.get("articles", [])
            if arts:
                filtered = [a for a in arts if _is_english(a.get("title",""))][:max_rec]
                if filtered: return filtered
        except Exception: continue
    return []

@st.cache_data(ttl=300)
def newsapi_headlines(key, query="stock market finance"):
    if not key: return []
    try:
        r = requests.get("https://newsapi.org/v2/everything",
            params={"q":query,"language":"en","sortBy":"publishedAt","pageSize":10,"apiKey":key},timeout=10)
        return r.json().get("articles",[])
    except: return []

@st.cache_data(ttl=300)
def finnhub_news(key):
    if not key: return []
    try:
        return requests.get("https://finnhub.io/api/v1/news",params={"category":"general","token":key},timeout=10).json()[:12]
    except: return []

@st.cache_data(ttl=600)
def finnhub_insider(ticker, key):
    if not key: return []
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/insider-transactions",params={"symbol":ticker,"token":key},timeout=10)
        return r.json().get("data",[])[:15]
    except: return []

@st.cache_data(ttl=1800)
def finnhub_officers(ticker, key):
    """Fetch company officers to map insider names to roles"""
    if not key: return {}
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/profile2",params={"symbol":ticker,"token":key},timeout=10)
        data = r.json()
        role_map = {}
        for o in data.get("companyOfficers", []) or []:
            name = str(o.get("name","")).upper()
            role_map[name] = o.get("title","")
        return role_map
    except: return {}

@st.cache_data(ttl=300)
def vix_price():
    try:
        h = yf.Ticker("^VIX").history(period="2d")
        return round(h["Close"].iloc[-1],2) if not h.empty else None
    except: return None

@st.cache_data(ttl=600)
def options_chain(ticker):
    try:
        t = yf.Ticker(ticker); exps = t.options
        if not exps: return None,None,None
        chain = t.option_chain(exps[0])
        cols = ["strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility"]
        c = chain.calls[[x for x in cols if x in chain.calls.columns]].head(12)
        p = chain.puts[[x  for x in cols if x in chain.puts.columns]].head(12)
        return c, p, exps[0]
    except: return None,None,None

@st.cache_data(ttl=600)
def sector_etfs():
    S = {"Technology":"XLK","Financials":"XLF","Energy":"XLE","Healthcare":"XLV",
         "Cons Staples":"XLP","Utilities":"XLU","Cons Disc":"XLY","Materials":"XLB",
         "Comm Svcs":"XLC","Real Estate":"XLRE","Industrials":"XLI"}
    rows = []
    for name,tkr in S.items():
        q = yahoo_quote(tkr)
        if q: rows.append({"Sector":name,"ETF":tkr,"Price":q["price"],"Pct":q["pct"]})
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def top_movers():
    """Get top gainers and losers from S&P 100 components"""
    UNIVERSE = [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","UNH","XOM",
        "JPM","JNJ","V","PG","MA","HD","CVX","MRK","ABBV","PFE","LLY","KO",
        "BAC","PEP","TMO","COST","AVGO","CSCO","ABT","WFC","DIS","ACN","MCD",
        "NEE","VZ","ADBE","PM","NKE","T","INTC","AMD","CRM","ORCL","QCOM",
        "TXN","HON","GE","RTX","CAT","GS","BMY","MDT","AMGN","GILD",
        "SBUX","ISRG","SPGI","BLK","AXP","CI","DE","INTU","ADI"
    ]
    quotes = multi_quotes(UNIVERSE)
    sorted_q = sorted(quotes, key=lambda x: x["pct"], reverse=True)
    return sorted_q[:8], sorted_q[-8:]

def detect_unusual_poly(markets):
    out = []
    for m in markets:
        try:
            v24 = _safe_float(m.get("volume24hr",0)); vtot = _safe_float(m.get("volume",0))
            if vtot>0 and v24/vtot>0.38 and v24>5000: out.append(m)
        except: pass
    return out[:6]

def market_snapshot_str():
    try:
        qs = multi_quotes(["SPY","QQQ","DX-Y.NYB","GLD","BTC-USD"])
        parts = [f"{q['ticker']}: ${q['price']:,.2f} ({q['pct']:+.2f}%)" for q in qs]
        v = vix_price()
        if v: parts.append(f"VIX: {v}")
        return " | ".join(parts)
    except: return ""

# ════════════════════════════════════════════════════════════════════
# GEMINI AI
# ════════════════════════════════════════════════════════════════════
SENTINEL_PROMPT = """You are SENTINEL — a professional Bloomberg-grade financial and geopolitical intelligence terminal.
VOICE: Concise, data-first. Define jargon once. Trace 2nd and 3rd-order effects.
RULES: Never fabricate. Always include bear case. Label confidence HIGH/MEDIUM/LOW/UNCONFIRMED.
Timestamp PST. End trade ideas with: ⚠️ Research only, not financial advice.
FORMATS: /brief /flash [ticker] /scenario [asset] /geo [region] /poly [topic] /rotate /sentiment /earnings"""

GEMINI_MODELS = ["gemini-2.0-flash","gemini-1.5-flash","gemini-1.5-pro","gemini-1.0-pro"]

def list_gemini_models(key):
    try:
        import google.generativeai as genai; genai.configure(api_key=key)
        return [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
    except Exception as e: return [f"Error: {e}"]

def gemini_response(user_msg, history, context=""):
    if not st.session_state.gemini_key:
        return "⚠️ Add your Gemini API key in the sidebar."
    try:
        import google.generativeai as genai
        genai.configure(api_key=st.session_state.gemini_key)
        last_err = ""
        for model_name in GEMINI_MODELS:
            try:
                model = genai.GenerativeModel(model_name=model_name, system_instruction=SENTINEL_PROMPT)
                ctx = ""
                if st.session_state.macro_theses: ctx += f"\nMacro: {st.session_state.macro_theses}"
                if st.session_state.geo_watch:    ctx += f"\nGeo: {st.session_state.geo_watch}"
                if st.session_state.watchlist:    ctx += f"\nWatchlist: {','.join(st.session_state.watchlist)}"
                if context: ctx += f"\nLive: {context}"
                gh = [{"role":"user" if m["role"]=="user" else "model","parts":[m["content"]]} for m in history[-12:]]
                chat = model.start_chat(history=gh)
                return chat.send_message(f"{ctx}\n\nQuery: {user_msg}" if ctx else user_msg).text
            except Exception as e:
                last_err = str(e)
                if "not found" in last_err.lower() or "404" in last_err: continue
                return f"⚠️ Gemini error: {e}"
        return f"⚠️ All models failed. Last error: {last_err}"
    except ImportError: return "⚠️ google-generativeai not installed."
    except Exception as e: return f"⚠️ Error: {e}"

# ════════════════════════════════════════════════════════════════════
# CHART HELPERS
# ════════════════════════════════════════════════════════════════════
CHART_LAYOUT = dict(
    paper_bgcolor="#000000", plot_bgcolor="#050505",
    font=dict(color="#FF8C00", family="IBM Plex Mono"),
    xaxis=dict(gridcolor="#111111", color="#555555", showgrid=True),
    yaxis=dict(gridcolor="#111111", color="#555555", showgrid=True),
    showlegend=False
)

def dark_fig(height=300):
    fig = go.Figure()
    fig.update_layout(**CHART_LAYOUT, height=height, margin=dict(l=0,r=10,t=24,b=0))
    return fig

def tv_chart(symbol, height=450):
    # Replace MACD with SMA60
    return f"""<!DOCTYPE html><html>
<head><style>body{{margin:0;padding:0;background:#000000;overflow:hidden}}
.tradingview-widget-container{{width:100%;height:{height}px}}</style></head>
<body><div class="tradingview-widget-container">
<div id="tv_c_{symbol.replace(':','_').replace('-','_')}"></div>
<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
<script type="text/javascript">
new TradingView.widget({{
  "width":"100%","height":{height},"symbol":"{symbol}","interval":"D",
  "timezone":"America/Los_Angeles","theme":"dark","style":"1","locale":"en",
  "toolbar_bg":"#000000","enable_publishing":false,"hide_side_toolbar":false,
  "allow_symbol_change":true,"save_image":false,
  "container_id":"tv_c_{symbol.replace(':','_').replace('-','_')}",
  "backgroundColor":"rgba(0,0,0,1)","gridColor":"rgba(20,20,20,1)",
  "studies":["RSI@tv-basicstudies","MASimple@tv-basicstudies|length=60"],
  "show_popup_button":true,"popup_width":"1000","popup_height":"650"
}});
</script></div></body></html>"""

def tv_mini(symbol, height=180):
    return f"""<!DOCTYPE html><html>
<head><style>body{{margin:0;padding:0;background:#000;overflow:hidden}}</style></head>
<body><div class="tradingview-widget-container">
<div class="tradingview-widget-container__widget"></div>
<script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
{{"symbol":"{symbol}","width":"100%","height":{height},"locale":"en","dateRange":"3M",
"colorTheme":"dark","trendLineColor":"rgba(255,102,0,1)",
"underLineColor":"rgba(255,102,0,0.1)","underLineBottomColor":"rgba(0,0,0,0)",
"isTransparent":true,"autosize":false}}
</script></div></body></html>"""

def tv_tape():
    return """<!DOCTYPE html><html>
<head><style>body{margin:0;padding:0;background:#000;overflow:hidden}</style></head>
<body><div class="tradingview-widget-container">
<div class="tradingview-widget-container__widget"></div>
<script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
{"symbols":[
{"proName":"FOREXCOM:SPXUSD","title":"S&P 500"},
{"proName":"FOREXCOM:NSXUSD","title":"Nasdaq 100"},
{"proName":"BITSTAMP:BTCUSD","title":"BTC"},
{"proName":"BITSTAMP:ETHUSD","title":"ETH"},
{"description":"Gold","proName":"OANDA:XAUUSD"},
{"description":"Oil WTI","proName":"NYMEX:CL1!"},
{"description":"DXY","proName":"TVC:DXY"},
{"proName":"TVC:VIX","title":"VIX"}
],"showSymbolLogo":true,"colorTheme":"dark","isTransparent":true,"displayMode":"compact","locale":"en"}
</script></div></body></html>"""

def yield_curve_chart(fred_key, height=260):
    """Plotly yield curve chart — replaces TradingView for Treasury display"""
    if not fred_key: return None
    MATURITIES = [("3M","DTB3"),("6M","DTB6"),("1Y","DGS1"),("2Y","DGS2"),
                  ("3Y","DGS3"),("5Y","DGS5"),("7Y","DGS7"),("10Y","DGS10"),
                  ("20Y","DGS20"),("30Y","DGS30")]
    labels,vals = [],[]
    for lbl,code in MATURITIES:
        df = fred_series(code, fred_key, 3)
        if df is not None and not df.empty:
            labels.append(lbl); vals.append(round(df["value"].iloc[-1],2))
    if not labels: return None
    fig = dark_fig(height)
    fig.add_trace(go.Scatter(x=labels,y=vals,mode="lines+markers+text",
        line=dict(color="#FF6600",width=2.5),marker=dict(size=9,color="#FF6600"),
        text=[f"{v:.2f}%" for v in vals],textposition="top center",
        textfont=dict(size=10,color="#FF8C00"),fill="tozeroy",
        fillcolor="rgba(255,102,0,0.08)"))
    fig.add_hline(y=0,line_dash="dash",line_color="#FF4444",opacity=0.5)
    fig.update_layout(yaxis_title="Yield (%)",
        title=dict(text=f"US TREASURY YIELD CURVE — {datetime.now().strftime('%Y-%m-%d')}",
                   font=dict(size=11,color="#FF6600"),x=0))
    return fig

def yield_history_chart(fred_key, height=220):
    """Multi-maturity yield history chart"""
    if not fred_key: return None
    LINES = [("2Y","DGS2","#FF4444"),("5Y","DGS5","#FF8C00"),
             ("10Y","DGS10","#FFCC00"),("30Y","DGS30","#00AAFF")]
    fig = dark_fig(height)
    for lbl, code, color in LINES:
        df = fred_series(code, fred_key, 36)
        if df is not None and not df.empty:
            fig.add_trace(go.Scatter(x=df["date"],y=df["value"],mode="lines",
                name=lbl,line=dict(color=color,width=1.8)))
    fig.update_layout(showlegend=True,
        legend=dict(bgcolor="#050505",bordercolor="#333",font=dict(size=10,color="#FF8C00")),
        yaxis_title="Yield (%)", title=dict(text="MULTI-MATURITY YIELD HISTORY (3Y)",
            font=dict(size=11,color="#FF6600"),x=0))
    return fig

# ════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ════════════════════════════════════════════════════════════════════
def render_news_card(title, url, source, date_str, card_class="bb-news"):
    t_html = f'<a href="{_esc(url)}" target="_blank">{_esc(title[:100])}</a>' if url and url!="#" else f'<span style="color:#CCC">{_esc(title[:100])}</span>'
    return f'<div class="{card_class}">{t_html}<div class="bb-meta">{_esc(source)} &nbsp;|&nbsp; {date_str}</div></div>'

def render_wl_row(q):
    c = "#00CC44" if q["pct"]>=0 else "#FF4444"; arr = "▲" if q["pct"]>=0 else "▼"
    vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
    return (f'<div class="wl-row"><span class="wl-ticker">{q["ticker"]}</span>'
            f'<span class="wl-price">{fmt_p(q["price"])}</span>'
            f'<span style="color:{c};font-weight:600">{arr} {abs(q["pct"]):.2f}%</span>'
            f'<span style="color:{c}">{"+"+fmt_p(q["change"]) if q["change"]>=0 else fmt_p(q["change"])}</span>'
            f'<span class="wl-vol">{vol}</span>'
            f'</div>')

def render_options_table(df, side="calls", current_price=None):
    if df is None or df.empty: return '<p style="color:#555;font-family:monospace;font-size:11px">No data</p>'
    cls = "opt-call" if side=="calls" else "opt-put"; rows = ""
    for _, row in df.iterrows():
        s=_safe_float(row.get("strike",0)); lp=_safe_float(row.get("lastPrice",0))
        b=_safe_float(row.get("bid",0)); a=_safe_float(row.get("ask",0))
        v=_safe_int(row.get("volume",0)); oi=_safe_int(row.get("openInterest",0))
        iv=_safe_float(row.get("impliedVolatility",0))
        itm=""
        if current_price:
            if side=="calls" and s<current_price: itm=" opt-itm"
            if side=="puts"  and s>current_price: itm=" opt-itm"
        hv=" opt-hvol" if v>0 and oi>0 and v/max(oi,1)>0.5 else ""
        rows += (f'<tr class="{itm}"><td class="{cls}">{s:.2f}</td>'
                 f'<td>{lp:.2f}</td><td>{b:.2f}</td><td>{a:.2f}</td>'
                 f'<td class="{hv}">{v:,}</td><td>{oi:,}</td><td>{iv:.1%}</td></tr>')
    return (f'<table class="opt-tbl"><thead><tr>'
            f'<th>Strike</th><th>Last</th><th>Bid</th><th>Ask</th>'
            f'<th>Volume</th><th>OI</th><th>IV</th></tr></thead><tbody>{rows}</tbody></table>')

ROLE_SHORTCUTS = {
    "CEO":"CEO","C.E.O.":"CEO","CHIEF EXECUTIVE":"CEO","PRESIDENT":"President",
    "CFO":"CFO","CHIEF FINANCIAL":"CFO","COO":"COO","CHIEF OPERATING":"COO",
    "CTO":"CTO","CHIEF TECHNOLOGY":"CTO","CMO":"CMO","CHIEF MARKETING":"CMO",
    "GENERAL COUNSEL":"Gen Counsel","DIRECTOR":"Director","CHAIRMAN":"Chairman",
    "VP ":"VP","VICE PRESIDENT":"VP","SVP":"SVP","EVP":"EVP","TREASURER":"Treasurer",
    "SECRETARY":"Secretary","CONTROLLER":"Controller","10% OWNER":"10% Owner",
    "BENEFICIAL OWNER":"Beneficial Owner",
}

def classify_role(raw_role):
    if not raw_role: return "Insider"
    upper = raw_role.upper()
    for key, short in ROLE_SHORTCUTS.items():
        if key in upper: return short
    return raw_role[:22]

def render_insider_cards(data, ticker="", finnhub_key=""):
    if not data:
        return '<p style="color:#555;font-family:monospace;font-size:11px">No insider data. Add Finnhub key.</p>'
    role_map = finnhub_officers(ticker, finnhub_key) if ticker and finnhub_key else {}
    CODE = {"P":("PURCHASE","buy"),"S":("SALE","sell"),"A":("AWARD","buy"),"D":("DISPOSAL","sell")}
    html = ""
    for tx in data[:10]:
        name = _esc(str(tx.get("name","Unknown"))[:24])
        chg  = _safe_int(tx.get("change",0)); date = str(tx.get("transactionDate",""))[:10]
        code = tx.get("transactionCode","?"); shares_own = _safe_int(tx.get("share",0))
        lbl,cls = CODE.get(code,(code,"buy"))
        # Role lookup
        name_upper = str(tx.get("name","")).upper()
        raw_role = role_map.get(name_upper,"")
        role = classify_role(raw_role) if raw_role else ("Beneficial Owner" if abs(chg)>100000 else "Insider")
        chg_str = f"{abs(chg):,}"
        own_str = f"{shares_own:,} sh owned" if shares_own else ""
        html += (f'<div class="ins-card {cls}">'
                 f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
                 f'<span class="ins-name">{name}</span>'
                 f'<span class="ins-{"buy" if cls=="buy" else "sell"}">{"▲ "+lbl if cls=="buy" else "▼ "+lbl}</span>'
                 f'</div>'
                 f'<div style="display:flex;justify-content:space-between;margin-top:3px">'
                 f'<span class="ins-role">{role}</span>'
                 f'<span class="ins-meta">{chg_str} sh &nbsp;|&nbsp; {date}</span>'
                 f'</div>'
                 + (f'<div class="ins-meta" style="margin-top:2px">{own_str}</div>' if own_str else '')
                 + '</div>')
    return html

def poly_url(m):
    """Build correct Polymarket URL — use conditionId or slug"""
    slug = m.get("slug","") or ""
    cond = m.get("conditionId","") or ""
    evt_slug = m.get("eventSlug","") or ""
    # Clean slug
    def clean(s): return s.strip().strip("/")
    if evt_slug: return f"https://polymarket.com/event/{clean(evt_slug)}"
    if slug: return f"https://polymarket.com/event/{clean(slug)}"
    if cond: return f"https://polymarket.com/market/{clean(cond)}"
    # Last resort: build slug from question title
    q = m.get("question","") or ""
    if q:
        import re
        auto_slug = re.sub(r'[^a-z0-9]+','-',q.lower())[:60].strip('-')
        if auto_slug: return f"https://polymarket.com/event/{auto_slug}"
    return "https://polymarket.com"

def poly_status(m):
    """Determine if market is active, resolved, or expired"""
    closed = m.get("closed", False)
    resolved = m.get("resolved", False)
    end_date_iso = m.get("endDate","") or m.get("end_date_utc","") or ""
    if resolved: return "RESOLVED", "poly-status-resolved"
    if closed:   return "CLOSED",   "poly-status-closed"
    if end_date_iso:
        try:
            end = datetime.fromisoformat(end_date_iso.replace("Z","+00:00"))
            if end < datetime.now(pytz.utc): return "EXPIRED (pending resolve)", "poly-status-closed"
        except: pass
    return "ACTIVE", "poly-status-active"

def unusual_side(m):
    """Determine which side unusual volume favors"""
    try:
        outcomes   = _parse_poly_field(m.get("outcomes",[]))
        out_prices = _parse_poly_field(m.get("outcomePrices",[]))
        if not out_prices or not outcomes: return None, None
        yes_p = _safe_float(out_prices[0]) * 100
        yes_name = str(outcomes[0]) if outcomes else "YES"
        no_name  = str(outcomes[1]) if len(outcomes)>1 else "NO"
        if yes_p > 60: return yes_name, "poly-unusual-yes"
        elif yes_p < 40: return no_name, "poly-unusual-no"
        else: return "BOTH SIDES", "poly-unusual-yes"
    except: return None, None

def _parse_poly_field(field):
    """Parse a Polymarket field that may be a JSON string or already a list."""
    if not field: return []
    if isinstance(field, str):
        try: return json.loads(field)
        except: return []
    return field if isinstance(field, list) else []

def render_poly_card(m, show_unusual=False):
    raw_title = m.get("question", m.get("title","Unknown")) or "Unknown"
    title_esc = _esc(raw_title[:100])
    url = poly_url(m)
    v24 = _safe_float(m.get("volume24hr",0)); vtot = _safe_float(m.get("volume",0))
    status_lbl, status_cls = poly_status(m)
    t_html = f'<a href="{url}" target="_blank">{title_esc}</a>'

    # Parse outcomes — always JSON strings from API e.g. '["Yes","No"]'
    outcomes   = _parse_poly_field(m.get("outcomes",[]))
    out_prices = _parse_poly_field(m.get("outcomePrices",[]))

    # Detect resolved winner: the outcome whose price is closest to 1.0
    winner_idx = None
    is_settled = status_lbl in ("RESOLVED", "CLOSED")
    if is_settled and out_prices:
        prices_f = [_safe_float(p) for p in out_prices]
        if prices_f:
            max_p = max(prices_f)
            if max_p >= 0.95:  # clear winner
                winner_idx = prices_f.index(max_p)

    # Outcome bars
    prob_rows = ""
    if outcomes and out_prices:
        try:
            for i, outcome in enumerate(outcomes[:2]):
                if i >= len(out_prices): break
                p = max(0.0, min(100.0, _safe_float(out_prices[i]) * 100))
                bar_c = "#00CC44" if p >= 50 else "#FF4444"
                is_winner = (winner_idx == i)
                winner_tag = (f' &nbsp;<span style="background:#00CC44;color:#000;'
                              f'font-size:9px;font-weight:700;padding:1px 5px">✓ WINNER</span>'
                              if is_winner else "")
                outcome_name = _esc(str(outcome)[:30]) if isinstance(outcome, str) else _esc(str(outcome)[:30])
                prob_rows += (
                    f'<div style="display:flex;align-items:center;gap:8px;margin-top:6px">'
                    f'<span style="color:{bar_c};font-size:11px;min-width:44px;font-weight:700">{p:.0f}%</span>'
                    f'<span style="color:#888;font-size:10px;flex:1">{outcome_name}{winner_tag}</span>'
                    f'<div style="width:90px;height:5px;background:#1A1A1A;border-radius:1px;overflow:hidden">'
                    f'<div style="width:{p:.0f}%;height:100%;background:{bar_c};border-radius:1px"></div>'
                    f'</div></div>')
        except: pass

    unusual_html = ""
    if show_unusual:
        side, side_cls = unusual_side(m)
        ratio = v24/vtot*100 if vtot>0 else 0
        if side:
            unusual_html = (f'<div style="margin-top:5px;padding:3px 6px;background:rgba(255,102,0,0.08);border-left:2px solid #FF6600">'
                            f'⚡ Unusual volume favoring <span class="{side_cls}">{side}</span>'
                            f' &nbsp;({ratio:.0f}% of total in 24h)</div>')

    vol_str = f"24H: ${v24:,.0f} &nbsp;|&nbsp; TOTAL: ${vtot:,.0f}"

    return (f'<div class="poly-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px">'
            f'<div style="font-size:13px;font-weight:600;flex:1">{t_html}</div>'
            f'<span class="{status_cls}" style="margin-left:8px;white-space:nowrap">{status_lbl}</span>'
            f'</div>'
            f'{prob_rows}{unusual_html}'
            f'<div style="color:#444;font-size:10px;margin-top:6px;letter-spacing:0.5px">{vol_str}</div>'
            f'</div>')

# ════════════════════════════════════════════════════════════════════
# HEADER + TABS
# ════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div style="background:#FF6600;padding:5px 14px;display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
  <div style="display:flex;align-items:center;gap:14px">
    <span style="font-size:20px;font-weight:900;letter-spacing:5px;color:#000;font-family:monospace">⚡ SENTINEL</span>
    <span style="font-size:10px;color:#000;background:rgba(0,0,0,0.15);padding:2px 8px">PROFESSIONAL INTELLIGENCE</span>
  </div>
  <div style="font-size:10px;color:#000;opacity:0.75">{now_pst()} &nbsp;|&nbsp; LIVE</div>
</div>""", unsafe_allow_html=True)

tabs = st.tabs(["BRIEF","MARKETS","MACRO","CRYPTO","POLYMARKET","GEO","EARNINGS","SENTINEL AI"])

# ════════════════════════════════════════════════════════════════════
# TAB 0 — MORNING BRIEF
# ════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="bb-ph">⚡ SENTINEL MORNING BRIEF</div>', unsafe_allow_html=True)

    if st.button("↺ REFRESH ALL DATA"):
        st.cache_data.clear(); st.rerun()

    KEY_T = {"SPY":"S&P 500","QQQ":"Nasdaq 100","DIA":"Dow Jones","IWM":"Russell 2K",
             "^TNX":"10Y Yield","DX-Y.NYB":"USD Index","GLD":"Gold","CL=F":"WTI Crude","BTC-USD":"Bitcoin"}
    qs = multi_quotes(list(KEY_T.keys()))
    cols = st.columns(len(qs))
    for col, q in zip(cols, qs):
        with col: st.metric(KEY_T.get(q["ticker"],q["ticker"]), fmt_p(q["price"]), delta=f"{q['pct']:+.2f}%")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    L, R = st.columns([3,2])

    with L:
        # ── Sentiment (Stock F&G here, Crypto F&G moves to Crypto tab)
        st.markdown('<div class="bb-ph">⚡ MARKET SENTIMENT</div>', unsafe_allow_html=True)
        s1,s2,s3 = st.columns(3)
        v = vix_price()
        with s1:
            if v:
                lbl = "LOW FEAR" if v<15 else ("MODERATE" if v<25 else ("HIGH FEAR" if v<35 else "PANIC"))
                st.metric("VIX", f"{v:.2f}", delta=lbl)
        # Stock F&G
        sfg_val, sfg_lbl = calc_stock_fear_greed()
        with s2:
            if sfg_val:
                sfg_c = "#00CC44" if sfg_val>=55 else ("#FF4444" if sfg_val<35 else "#FF8C00")
                st.markdown(f'<div class="fg-gauge"><div class="fg-num" style="color:{sfg_c}">{sfg_val}</div><div class="fg-lbl" style="color:{sfg_c}">{sfg_lbl}</div><div style="color:#555;font-size:8px;margin-top:2px">STOCK MARKET F&G</div></div>', unsafe_allow_html=True)
        with s3:
            if v:
                posture = "RISK-ON" if v<18 else ("NEUTRAL" if v<25 else "RISK-OFF")
                pc = {"RISK-ON":"#00CC44","NEUTRAL":"#FF8C00","RISK-OFF":"#FF4444"}[posture]
                st.markdown(f'<div style="background:#0D0D0D;border:1px solid #222;border-top:2px solid {pc};padding:8px;text-align:center"><div style="color:#888;font-size:9px;letter-spacing:1px">POSTURE</div><div style="color:{pc};font-size:18px;font-weight:700">{posture}</div></div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Watchlist with full management
        st.markdown('<div class="bb-ph">👁 WATCHLIST</div>', unsafe_allow_html=True)

        # Add/Remove controls
        wl_a, wl_b = st.columns([3,1])
        with wl_a:
            new_ticker = st.text_input("Add ticker", placeholder="e.g. TSLA", label_visibility="collapsed", key="wl_add")
        with wl_b:
            if st.button("＋ ADD", use_container_width=True):
                t = new_ticker.upper().strip()
                if t and t not in st.session_state.watchlist:
                    st.session_state.watchlist.append(t); st.rerun()

        # Display watchlist with remove buttons
        wl_qs = multi_quotes(st.session_state.watchlist)
        # Header row
        st.markdown("""<div style="display:grid;grid-template-columns:90px 120px 100px 100px 90px 50px;
gap:12px;padding:6px 10px;border-bottom:1px solid #FF6600;
font-family:monospace;font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">
<span>TICKER</span><span>PRICE</span><span>CHG %</span><span>CHG $</span><span>VOLUME</span><span>DEL</span>
</div>""", unsafe_allow_html=True)
        for q in wl_qs:
            c = "#00CC44" if q["pct"]>=0 else "#FF4444"; arr = "▲" if q["pct"]>=0 else "▼"
            vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
            chg_str = f"+{q['change']:.2f}" if q["change"]>=0 else f"{q['change']:.2f}"
            crow = st.columns([1.5, 2.0, 1.7, 1.7, 1.5, 0.8])
            with crow[0]: st.markdown(f'<div style="color:#FF6600;font-weight:700;font-family:monospace;padding:4px 0">{q["ticker"]}</div>', unsafe_allow_html=True)
            with crow[1]: st.markdown(f'<div style="color:#FFF;font-family:monospace;padding:4px 0">{fmt_p(q["price"])}</div>', unsafe_allow_html=True)
            with crow[2]: st.markdown(f'<div style="color:{c};font-family:monospace;padding:4px 0">{arr} {abs(q["pct"]):.2f}%</div>', unsafe_allow_html=True)
            with crow[3]: st.markdown(f'<div style="color:{c};font-family:monospace;padding:4px 0">{chg_str}</div>', unsafe_allow_html=True)
            with crow[4]: st.markdown(f'<div style="color:#555;font-family:monospace;font-size:11px;padding:4px 0">{vol}</div>', unsafe_allow_html=True)
            with crow[5]:
                if st.button("✕", key=f"rm_{q['ticker']}", help=f"Remove {q['ticker']}"):
                    st.session_state.watchlist = [x for x in st.session_state.watchlist if x!=q["ticker"]]
                    st.rerun()
            st.markdown('<div style="border-bottom:1px solid #111;margin:0 0 2px 0"></div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Sector Pulse
        st.markdown('<div class="bb-ph">🔄 SECTOR PULSE</div>', unsafe_allow_html=True)
        sec_df = sector_etfs()
        if not sec_df.empty:
            for _, row in sec_df.sort_values("Pct",ascending=False).iterrows():
                p = row["Pct"]; cls = "up" if p>=0 else "dn"; sign = "+" if p>=0 else ""
                st.markdown(f'<div class="sec-cell {cls}"><span style="color:#FFF">{row["Sector"]}</span><span style="color:#555;font-size:10px">{row["ETF"]}</span><span style="color:{"#00CC44" if p>=0 else "#FF4444"};font-weight:700">{sign}{p:.2f}%</span></div>', unsafe_allow_html=True)

    with R:
        # ── Polymarket top
        st.markdown('<div class="bb-ph">🎲 POLYMARKET TOP MARKETS</div>', unsafe_allow_html=True)
        with st.spinner("Loading markets…"):
            poly = polymarket_markets(20)
        if poly:
            for m in poly[:5]:
                st.markdown(render_poly_card(m), unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Could not reach Polymarket API. Check network connectivity.</p>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Geo Watch (GDELT)
        st.markdown('<div class="bb-ph">🌍 GEO WATCH</div>', unsafe_allow_html=True)
        with st.spinner("Loading geo feed…"):
            geo_arts = gdelt_news("geopolitical conflict oil market",8)
        if geo_arts:
            for art in geo_arts[:5]:
                t=art.get("title","")[:90]; u=art.get("url","#"); dom=art.get("domain","GDELT"); sd=art.get("seendate","")
                d=f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd)>=8 else ""
                st.markdown(render_news_card(t,u,dom,d,"bb-news bb-news-geo"), unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">GDELT feed temporarily unavailable. Will auto-retry.</p>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 1 — MARKETS
# ════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="bb-ph">📊 MARKETS — EQUITIES | OPTIONS | MOVERS | ROTATION</div>', unsafe_allow_html=True)

    fc, _ = st.columns([2,3])
    with fc:
        flash_ticker = st.text_input("⚡ TICKER LOOKUP", placeholder="NVDA, AAPL, TSLA, SPY, GLD…", key="flash")

    if flash_ticker:
        tkr = flash_ticker.upper().strip()
        q = yahoo_quote(tkr)
        if q:
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("PRICE",  fmt_p(q["price"]), delta=fmt_pct(q["pct"]))
            m2.metric("CHANGE", f"{'+' if q['change']>=0 else ''}{q['change']:.2f}")
            m3.metric("VOLUME", f"{q['volume']:,}")
            m4.metric("1D CHG%",fmt_pct(q["pct"]))

            # TradingView Chart (SMA60 instead of MACD)
            TV_MAP = {"SPY":"AMEX:SPY","QQQ":"NASDAQ:QQQ","NVDA":"NASDAQ:NVDA","AAPL":"NASDAQ:AAPL",
                      "TSLA":"NASDAQ:TSLA","MSFT":"NASDAQ:MSFT","GOOGL":"NASDAQ:GOOGL","AMZN":"NASDAQ:AMZN",
                      "META":"NASDAQ:META","GLD":"AMEX:GLD","TLT":"NASDAQ:TLT","IWM":"AMEX:IWM",
                      "BTC-USD":"COINBASE:BTCUSD","ETH-USD":"COINBASE:ETHUSD",
                      "GC=F":"COMEX:GC1!","CL=F":"NYMEX:CL1!","^TNX":"TVC:TNX","^VIX":"TVC:VIX","DXY":"TVC:DXY"}
            tv_sym = TV_MAP.get(tkr, f"NASDAQ:{tkr}")
            st.markdown('<div class="bb-ph" style="margin-top:8px">CHART — TRADINGVIEW (RSI + SMA60)</div>', unsafe_allow_html=True)
            components.html(tv_chart(tv_sym, 480), height=485, scrolling=False)

            oc, ic = st.columns([3,2])
            with oc:
                st.markdown('<div class="bb-ph">📋 OPTIONS CHAIN — NEAREST EXPIRY</div>', unsafe_allow_html=True)
                with st.spinner("Loading options…"):
                    calls, puts, exp_date = options_chain(tkr)
                if calls is not None:
                    st.markdown(f'<div style="color:#555;font-size:9px;font-family:monospace;margin-bottom:6px">EXPIRY: {exp_date} | CURRENT: {fmt_p(q["price"])}</div>', unsafe_allow_html=True)
                    cc, pc = st.columns(2)
                    with cc:
                        st.markdown('<div style="color:#00CC44;font-size:9px;font-weight:700;letter-spacing:2px">▲ CALLS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(calls,"calls",q["price"]), unsafe_allow_html=True)
                    with pc:
                        st.markdown('<div style="color:#FF4444;font-size:9px;font-weight:700;letter-spacing:2px">▼ PUTS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(puts,"puts",q["price"]), unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Options unavailable for this ticker.</p>', unsafe_allow_html=True)

            with ic:
                st.markdown('<div class="bb-ph">🔍 INSIDER TRANSACTIONS</div>', unsafe_allow_html=True)
                if st.session_state.finnhub_key:
                    with st.spinner("Loading insider data…"):
                        ins = finnhub_insider(tkr, st.session_state.finnhub_key)
                    if ins:
                        st.markdown(render_insider_cards(ins, tkr, st.session_state.finnhub_key), unsafe_allow_html=True)
                    else:
                        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No recent insider transactions found.</p>', unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Add Finnhub key in sidebar.</p>', unsafe_allow_html=True)
        else:
            st.error(f"No data for '{tkr}'. Check ticker symbol.")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ── FUTURES TRACKER ──────────────────────────────────────────
    st.markdown('<div class="bb-ph">📡 FUTURES — LIVE TRACKING</div>', unsafe_allow_html=True)
    with st.spinner("Loading futures…"):
        fut_data = get_futures()
    if fut_data:
        st.markdown(
            '<div class="fut-row" style="color:#FF6600;font-size:9px;letter-spacing:1px;border-bottom:1px solid #FF6600">'
            '<span>CONTRACT</span><span>NAME</span><span>PRICE</span><span>CHG%</span><span>CHG $</span><span>SIGNAL</span>'
            '</div>', unsafe_allow_html=True)
        for f in fut_data:
            c = "#00CC44" if f["pct"]>=0 else "#FF4444"
            arr = "▲" if f["pct"]>=0 else "▼"
            sig_lbl = "BULL" if f["pct"]>=0.5 else ("BEAR" if f["pct"]<=-0.5 else "FLAT")
            sig_c = "#00CC44" if sig_lbl=="BULL" else ("#FF4444" if sig_lbl=="BEAR" else "#555")
            st.markdown(
                f'<div class="fut-row">'
                f'<span style="color:#FF6600;font-weight:700">{f["ticker"]}</span>'
                f'<span style="color:#AAA;font-size:10px">{f["name"]}</span>'
                f'<span style="color:#FFF;font-weight:600">{fmt_p(f["price"])}</span>'
                f'<span style="color:{c};font-weight:700">{arr}{abs(f["pct"]):.2f}%</span>'
                f'<span style="color:{c}">{"+"+str(f["change"]) if f["change"]>=0 else str(f["change"])}</span>'
                f'<span style="color:{sig_c};font-size:10px;font-weight:700">{sig_lbl}</span>'
                f'</div>', unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Futures data loading…</p>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ── Top Gainers & Losers — FULL WIDTH ─────────────────────────
    st.markdown('<div class="bb-ph">🏆 TOP MOVERS — S&P 100 UNIVERSE</div>', unsafe_allow_html=True)
    with st.spinner("Scanning universe for top movers…"):
        gainers, losers = top_movers()
    gco, lco = st.columns(2)
    with gco:
        st.markdown('<div style="color:#00CC44;font-size:11px;font-weight:700;letter-spacing:1px;margin-bottom:4px">▲ TOP GAINERS</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="mover-row" style="color:#FF6600;font-size:9px;letter-spacing:1px;border-bottom:1px solid #FF6600">'
            '<span>TICKER</span><span>PRICE</span><span>CHG%</span><span>CHG $</span><span>VOLUME</span>'
            '</div>', unsafe_allow_html=True)
        for q in gainers:
            vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
            chg_str = f"+${q['change']:.2f}"
            st.markdown(
                f'<div class="mover-row">'
                f'<span style="color:#FF6600;font-weight:700">{q["ticker"]}</span>'
                f'<span style="color:#FFF;font-weight:600">{fmt_p(q["price"])}</span>'
                f'<span class="up" style="font-weight:700">+{q["pct"]:.2f}%</span>'
                f'<span style="color:#00CC44">{chg_str}</span>'
                f'<span style="color:#555;font-size:10px">{vol}</span>'
                f'</div>', unsafe_allow_html=True)
    with lco:
        st.markdown('<div style="color:#FF4444;font-size:11px;font-weight:700;letter-spacing:1px;margin-bottom:4px">▼ TOP LOSERS</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="mover-row" style="color:#FF6600;font-size:9px;letter-spacing:1px;border-bottom:1px solid #FF6600">'
            '<span>TICKER</span><span>PRICE</span><span>CHG%</span><span>CHG $</span><span>VOLUME</span>'
            '</div>', unsafe_allow_html=True)
        for q in losers:
            vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
            chg_str = f"-${abs(q['change']):.2f}"
            st.markdown(
                f'<div class="mover-row">'
                f'<span style="color:#FF6600;font-weight:700">{q["ticker"]}</span>'
                f'<span style="color:#FFF;font-weight:600">{fmt_p(q["price"])}</span>'
                f'<span class="dn" style="font-weight:700">{q["pct"]:.2f}%</span>'
                f'<span style="color:#FF4444">{chg_str}</span>'
                f'<span style="color:#555;font-size:10px">{vol}</span>'
                f'</div>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ── Sector Rotation (Plotly bar chart)
    st.markdown('<div class="bb-ph">🔄 SECTOR ROTATION HEATMAP</div>', unsafe_allow_html=True)
    sec_df = sector_etfs()
    if not sec_df.empty:
        ss = sec_df.sort_values("Pct")
        fig2 = go.Figure(go.Bar(x=ss["Pct"],y=ss["Sector"],orientation="h",
            marker=dict(color=[pct_color(x) for x in ss["Pct"]],line=dict(width=0)),
            text=ss["Pct"].apply(lambda x: f"{x:+.2f}%"),textposition="outside",
            textfont=dict(color="#FF8C00",size=10)))
        fig2.update_layout(**CHART_LAYOUT,height=350,xaxis_title="% Change",margin=dict(l=0,r=70,t=10,b=0))
        st.plotly_chart(fig2, width="stretch")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    # ── FinViz-Style Market Heatmap
    st.markdown('<div class="bb-ph">🗺 S&P 500 MARKET HEATMAP — FINVIZ STYLE</div>', unsafe_allow_html=True)
    with st.spinner("Building heatmap (scanning ~120 stocks)…"):
        hm_data = get_heatmap_data()
    if hm_data:
        hm_df = pd.DataFrame(hm_data)
        hm_df["pct_capped"] = hm_df["pct"].clip(-5, 5)
        hm_df["label"] = hm_df.apply(lambda r: f"{r['ticker']}<br>{r['pct']:+.2f}%", axis=1)

        # Build treemap with proper root structure
        # Add sector rows (parent = "")
        sectors = hm_df["sector"].unique().tolist()
        sec_rows = pd.DataFrame({
            "label": sectors, "sector": [""] * len(sectors),
            "pct_capped": [0]*len(sectors), "values": [1]*len(sectors),
            "ticker": sectors, "price": [0]*len(sectors),
            "pct": [0]*len(sectors), "change": [0]*len(sectors),
        })
        stock_rows = hm_df.copy()
        stock_rows["values"] = 1

        all_labels    = list(sec_rows["label"]) + list(stock_rows["label"])
        all_parents   = list(sec_rows["sector"]) + list(stock_rows["sector"])
        all_values    = list(sec_rows["values"]) + list(stock_rows["values"])
        all_colors    = [0.0]*len(sec_rows) + list(stock_rows["pct_capped"])
        all_custom    = [[r, 0, 0, 0, r] for r in sectors] + list(stock_rows[["ticker","price","pct","change","sector"]].values.tolist())

        fig_hm = go.Figure(go.Treemap(
            labels=all_labels, parents=all_parents, values=all_values,
            customdata=all_custom,
            hovertemplate="<b>%{customdata[0]}</b><br>Price: $%{customdata[1]:.2f}<br>Change: %{customdata[2]:+.2f}%<br>$Change: %{customdata[3]:+.2f}<extra></extra>",
            marker=dict(
                colors=all_colors,
                colorscale=[
                    [0.0,  "#8B0000"],
                    [0.3,  "#CC2222"],
                    [0.45, "#441111"],
                    [0.5,  "#111111"],
                    [0.55, "#114411"],
                    [0.7,  "#22AA44"],
                    [1.0,  "#007A2F"],
                ],
                cmid=0, cmin=-5, cmax=5,
                showscale=True,
                colorbar=dict(
                    title=dict(text="% CHG", font=dict(color="#FF6600",size=10)),
                    tickfont=dict(color="#888",size=9),
                    thickness=10, len=0.6, bgcolor="#050505", bordercolor="#333",
                ),
                line=dict(width=1, color="#1a1a1a"),
            ),
            textfont=dict(color="#FFFFFF", size=11),
            tiling=dict(squarifyratio=1.618),
            pathbar=dict(visible=False),
        ))
        fig_hm.update_layout(
            paper_bgcolor="#000000", plot_bgcolor="#000000",
            font=dict(color="#FF8C00", family="IBM Plex Mono"),
            height=580, margin=dict(l=0,r=0,t=10,b=0),
        )
        st.plotly_chart(fig_hm, width="stretch")
    else:
        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Heatmap data loading… (requires fetching ~120 stocks)</p>', unsafe_allow_html=True)

    # ── Market news
    if st.session_state.finnhub_key:
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">📰 MARKET NEWS — FINNHUB LIVE</div>', unsafe_allow_html=True)
        with st.spinner("Loading news…"):
            fn = finnhub_news(st.session_state.finnhub_key)
        for art in fn[:8]:
            title=art.get("headline","")[:100]; url=art.get("url","#"); src=art.get("source","")
            ts=art.get("datetime",0)
            d=datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
            st.markdown(render_news_card(title,url,src,d,"bb-news bb-news-macro"), unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 2 — MACRO
# ════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="bb-ph">📈 MACRO — FRED DATA DASHBOARD</div>', unsafe_allow_html=True)

    if not st.session_state.fred_key:
        st.markdown("""<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;
padding:16px;font-family:monospace;font-size:12px;color:#FF8C00">
⚠️ FRED API key required for macro data.<br><br>
<a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank" style="color:#FF6600">
Get your free FRED key in 30 seconds →</a></div>""", unsafe_allow_html=True)
    else:
        # ── Yield Curve (Plotly — replacing TradingView)
        mc1, mc2 = st.columns([2,2])
        with mc1:
            st.markdown('<div class="bb-ph">📉 YIELD CURVE (LIVE FROM FRED)</div>', unsafe_allow_html=True)
            with st.spinner("Loading yield curve…"):
                fig_yc = yield_curve_chart(st.session_state.fred_key, 260)
            if fig_yc:
                st.plotly_chart(fig_yc, width="stretch")
                # Spread signal
                df_2y = fred_series("DGS2", st.session_state.fred_key, 3)
                df_10y = fred_series("DGS10", st.session_state.fred_key, 3)
                if df_2y is not None and df_10y is not None and not df_2y.empty and not df_10y.empty:
                    sp = round(df_10y["value"].iloc[-1] - df_2y["value"].iloc[-1], 2)
                    if sp < 0:
                        st.markdown(f'<div style="background:#1A0000;border-left:3px solid #FF0000;padding:8px 12px;font-family:monospace;font-size:11px;color:#FF8C00">⚠️ INVERTED: 10Y-2Y = {sp:.2f}%. Recession lead: 12-18 months avg.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="background:#001A00;border-left:3px solid #00CC44;padding:8px 12px;font-family:monospace;font-size:11px;color:#CCC">✅ NORMAL: 10Y-2Y = +{sp:.2f}%</div>', unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace">Yield data loading…</p>', unsafe_allow_html=True)

        with mc2:
            st.markdown('<div class="bb-ph">📊 KEY MACRO INDICATORS</div>', unsafe_allow_html=True)
            MACRO = {"CPI":"CPIAUCSL","Core PCE":"PCEPILFE","Fed Funds":"FEDFUNDS",
                     "Unemployment":"UNRATE","U6 Rate":"U6RATE","M2 Supply":"M2SL",
                     "HY Spread":"BAMLH0A0HYM2"}
            for name, code in MACRO.items():
                df = fred_series(code, st.session_state.fred_key, 3)
                if df is not None and not df.empty:
                    val = round(df["value"].iloc[-1], 2)
                    prev = round(df["value"].iloc[-2], 2) if len(df)>1 else val
                    chg = round(val-prev, 2)
                    st.metric(name, f"{val:.2f}", delta=f"{chg:+.2f}")

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Multi-maturity yield history (Plotly)
        st.markdown('<div class="bb-ph">📈 MULTI-MATURITY YIELD HISTORY — 3 YEARS (LIVE FRED)</div>', unsafe_allow_html=True)
        with st.spinner("Loading yield history…"):
            fig_hist = yield_history_chart(st.session_state.fred_key, 240)
        if fig_hist:
            st.plotly_chart(fig_hist, width="stretch")
        else:
            st.markdown('<p style="color:#555;font-family:monospace">Yield history data loading…</p>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── DXY and Gold from TradingView mini widgets
        tc1, tc2 = st.columns(2)
        with tc1:
            st.markdown('<div class="bb-ph">USD INDEX — DXY</div>', unsafe_allow_html=True)
            components.html(tv_mini("TVC:DXY", 185), height=190)
        with tc2:
            st.markdown('<div class="bb-ph">GOLD — COMEX</div>', unsafe_allow_html=True)
            components.html(tv_mini("COMEX:GC1!", 185), height=190)

# ════════════════════════════════════════════════════════════════════
# TAB 3 — CRYPTO
# ════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="bb-ph">💰 CRYPTO — COINGECKO + TRADINGVIEW</div>', unsafe_allow_html=True)

    with st.spinner("Loading crypto globals…"):
        gdata = crypto_global(st.session_state.coingecko_key)
    if gdata:
        g1,g2,g3,g4 = st.columns(4)
        total_cap = gdata.get("total_market_cap",{}).get("usd",0)
        btc_dom   = gdata.get("market_cap_percentage",{}).get("btc",0)
        eth_dom   = gdata.get("market_cap_percentage",{}).get("eth",0)
        # Crypto F&G goes here, not on Brief tab
        fv, fl = fear_greed_crypto()
        g1.metric("Total Mkt Cap",  f"${total_cap/1e12:.2f}T")
        g2.metric("BTC Dominance",  f"{btc_dom:.1f}%")
        g3.metric("ETH Dominance",  f"{eth_dom:.1f}%")
        if fv:
            cfg_c = "#00CC44" if fv>=55 else ("#FF4444" if fv<35 else "#FF8C00")
            with g4:
                st.markdown(f'<div class="fg-gauge"><div class="fg-num" style="color:{cfg_c}">{fv}</div><div class="fg-lbl" style="color:{cfg_c}">{fl}</div><div style="color:#555;font-size:8px;margin-top:2px">CRYPTO FEAR & GREED</div></div>', unsafe_allow_html=True)

        if btc_dom > 55:
            st.markdown('<div style="background:#1A0000;border-left:3px solid #FF4444;padding:8px 12px;font-family:monospace;font-size:11px;color:#FF8C00">⚠️ BTC Dominance >55% — Altcoin pressure. Risk-off within crypto.</div>', unsafe_allow_html=True)
        elif btc_dom < 45:
            st.markdown('<div style="background:#001A00;border-left:3px solid #00CC44;padding:8px 12px;font-family:monospace;font-size:11px;color:#CCC">✅ BTC Dominance <45% — Altcoin season conditions.</div>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    cr1, cr2 = st.columns([3,3])

    with cr1:
        st.markdown('<div class="bb-ph">💹 TOP 20 BY MARKET CAP</div>', unsafe_allow_html=True)
        with st.spinner("Loading crypto markets…"):
            cdata = crypto_markets(st.session_state.coingecko_key)
        if cdata and isinstance(cdata, list):
            # Header row
            st.markdown(
                '<div style="display:grid;grid-template-columns:80px 130px 90px 110px;gap:8px;'
                'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                'font-size:10px;color:#FF6600;letter-spacing:1px;margin-bottom:3px">'
                '<span>SYMBOL</span><span>PRICE</span><span>24H %</span><span>MKT CAP</span></div>',
                unsafe_allow_html=True)
            for c in cdata:
                if not isinstance(c, dict) or not c.get("current_price"): continue
                pct = c.get("price_change_percentage_24h",0) or 0; color = pct_color(pct)
                sign = "+" if pct>=0 else ""
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:80px 130px 90px 110px;gap:8px;'
                    f'padding:6px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:13px;align-items:center">'
                    f'<span style="color:#FF6600;font-weight:700">{c["symbol"].upper()}</span>'
                    f'<span style="color:#FFF;font-weight:600">{fmt_p(c["current_price"])}</span>'
                    f'<span style="color:{color};font-weight:700">{sign}{pct:.2f}%</span>'
                    f'<span style="color:#777">${c["market_cap"]/1e9:.1f}B</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">CoinGecko data unavailable. Rate limits may apply — try adding a CoinGecko key.</p>', unsafe_allow_html=True)

    with cr2:
        st.markdown('<div class="bb-ph">📈 BTC/USD — TRADINGVIEW</div>', unsafe_allow_html=True)
        components.html(tv_chart("COINBASE:BTCUSD", 460), height=465, scrolling=False)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-ph">📈 ETH/USD — TRADINGVIEW</div>', unsafe_allow_html=True)
    components.html(tv_chart("COINBASE:ETHUSD", 320), height=325, scrolling=False)

# ════════════════════════════════════════════════════════════════════
# TAB 4 — POLYMARKET
# ════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="bb-ph">🎲 POLYMARKET — PREDICTION INTELLIGENCE & UNUSUAL FLOW</div>', unsafe_allow_html=True)

    with st.spinner("Loading Polymarket…"):
        all_poly = polymarket_markets(100)

    if not all_poly:
        st.markdown('<div style="background:#0A0500;border-left:4px solid #FF6600;padding:12px;font-family:monospace;font-size:12px;color:#FF8C00">⚠️ Could not reach Polymarket API. May be temporarily unavailable.</div>', unsafe_allow_html=True)
    else:
        # ── Filter to ACTIVE markets only, sorted by 24h volume, top 10
        def is_active(m):
            if m.get("closed", False) or m.get("resolved", False): return False
            end = m.get("endDate","") or ""
            if end:
                try:
                    from datetime import timezone
                    e = datetime.fromisoformat(end.replace("Z","+00:00"))
                    if e < datetime.now(timezone.utc): return False
                except: pass
            return True

        active_markets = [m for m in all_poly if is_active(m)]
        active_markets.sort(key=lambda m: _safe_float(m.get("volume24hr",0)), reverse=True)
        top10 = active_markets[:10]

        poly_search = st.text_input("🔍 SEARCH ALL ACTIVE MARKETS", placeholder="Fed rate, oil, Taiwan, BTC…", key="ps")
        if poly_search:
            top10 = [m for m in active_markets if poly_search.lower() in str(m.get("question","")).lower()][:10]

        # ── VISUALIZATIONS — STACKED VERTICALLY ─────────────────
        st.markdown('<div class="bb-ph" style="margin-top:10px">📊 MARKET INTELLIGENCE DASHBOARD</div>', unsafe_allow_html=True)

        if top10:
            # Build clickable labels with URLs
            def make_poly_label(m, max_len=35):
                q = m.get("question","")
                url = poly_url(m)
                short = q[:max_len]+"…" if len(q)>max_len else q
                return short, url

            labels_with_url = [make_poly_label(m) for m in top10]
            labels = [l for l,u in labels_with_url]
            urls   = [u for l,u in labels_with_url]

            # Chart 1: 24h Volume bar chart (full width)
            vols   = [_safe_float(m.get("volume24hr",0))/1e3 for m in top10]
            colors = ["#FF6600" if i==0 else "#AA3300" if i<3 else "#662200" for i in range(len(top10))]
            fig_vol = dark_fig(320)
            fig_vol.add_trace(go.Bar(
                x=vols, y=labels, orientation="h",
                marker=dict(color=colors, line=dict(width=0)),
                text=[f"${v:,.0f}K" for v in vols], textposition="outside",
                textfont=dict(size=10, color="#FF8C00"),
                customdata=urls,
            ))
            fig_vol.update_layout(
                margin=dict(l=10,r=80,t=32,b=0), height=320,
                title=dict(text="24H VOLUME ($K) — Click bars to open market", font=dict(size=11,color="#FF6600"), x=0),
                xaxis=dict(showgrid=False, color="#444"),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9,color="#CCC"))
            )
            st.plotly_chart(fig_vol, width="stretch")

            # Clickable market links below chart 1
            with st.expander("🔗 CLICK TO OPEN MARKETS", expanded=False):
                for m in top10:
                    q = m.get("question","")[:70]
                    url = poly_url(m)
                    pp = _parse_poly_field(m.get("outcomePrices",[]))
                    p = _safe_float(pp[0])*100 if pp else 50
                    c = "#00CC44" if p>=50 else "#FF4444"
                    st.markdown(f'<div style="padding:3px 0;font-family:monospace;font-size:11px"><a href="{url}" target="_blank" style="color:#FF6600">↗ {_esc(q)}</a> <span style="color:{c};font-weight:700">{p:.0f}%</span></div>', unsafe_allow_html=True)

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

            # Chart 2: YES probability (full width)
            y_probs = []
            for m in top10:
                pp = _parse_poly_field(m.get("outcomePrices",[]))
                p = _safe_float(pp[0])*100 if pp else 50
                y_probs.append(round(p,1))
            bar_colors = ["#00CC44" if p>=50 else "#FF4444" for p in y_probs]
            fig_prob = dark_fig(320)
            fig_prob.add_trace(go.Bar(
                x=y_probs, y=labels, orientation="h",
                marker=dict(color=bar_colors, line=dict(width=0)),
                text=[f"{p:.0f}%" for p in y_probs], textposition="outside",
                textfont=dict(size=10, color="#CCCCCC"),
                customdata=urls,
            ))
            fig_prob.add_vline(x=50, line_dash="dash", line_color="#555", opacity=0.6)
            fig_prob.update_layout(
                margin=dict(l=10,r=60,t=32,b=0), height=320,
                title=dict(text="YES PROBABILITY (%)", font=dict(size=11,color="#FF6600"), x=0),
                xaxis=dict(range=[0,115], showgrid=False, color="#444"),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9,color="#CCC"))
            )
            st.plotly_chart(fig_prob, width="stretch")

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

            # Chart 3: Activity ratio (full width)
            ratios = []
            for m in top10:
                v24 = _safe_float(m.get("volume24hr",0))
                vt  = _safe_float(m.get("volume",1))
                ratios.append(round(v24/vt*100,1) if vt>0 else 0)
            r_colors = ["#FF4444" if r>=38 else "#FF6600" if r>=20 else "#333333" for r in ratios]
            fig_ratio = dark_fig(320)
            fig_ratio.add_trace(go.Bar(
                x=ratios, y=labels, orientation="h",
                marker=dict(color=r_colors, line=dict(width=0)),
                text=[f"{r:.0f}%" for r in ratios], textposition="outside",
                textfont=dict(size=10, color="#CCCCCC"),
                customdata=urls,
            ))
            fig_ratio.add_vline(x=38, line_dash="dash", line_color="#FF4444", opacity=0.5)
            fig_ratio.update_layout(
                margin=dict(l=10,r=60,t=32,b=0), height=320,
                title=dict(text="24H / TOTAL VOLUME RATIO — ≥38% = UNUSUAL ACTIVITY", font=dict(size=11,color="#FF6600"), x=0),
                xaxis=dict(range=[0,115], showgrid=False, color="#444"),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9,color="#CCC"))
            )
            st.plotly_chart(fig_ratio, width="stretch")

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Unusual activity ──
        unusual = detect_unusual_poly(active_markets)
        if unusual:
            st.markdown('<div class="bb-ph" style="color:#FF4444;border-color:#FF4444">🚨 UNUSUAL ACTIVITY DETECTED</div>', unsafe_allow_html=True)
            for m in unusual:
                raw_t = m.get("question",m.get("title","")) or ""
                v24 = _safe_float(m.get("volume24hr",0)); vtot = _safe_float(m.get("volume",0))
                ratio = v24/vtot*100 if vtot>0 else 0
                url = poly_url(m)
                side, side_cls = unusual_side(m)
                side_html = f' &nbsp;— <span class="{side_cls or "poly-unusual-yes"}" style="font-size:13px">Favoring {side or "UNKNOWN"}</span>' if side else ""
                st.markdown(
                    f'<div style="background:#0D0000;border:1px solid #FF0000;border-left:4px solid #FF0000;'
                    f'padding:14px 16px;margin:6px 0;font-family:monospace">'
                    f'🚨 <a href="{url}" target="_blank" style="color:#FF4444;font-weight:700;font-size:15px">{_esc(raw_t[:90])}</a>'
                    f'<div style="margin-top:7px;font-size:13px"><span style="color:#FF6600;font-weight:600">24h Vol: ${v24:,.0f} &nbsp;({ratio:.0f}% of total volume)</span>'
                    f'{side_html}</div></div>', unsafe_allow_html=True)
            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Top 10 ACTIVE market cards + guide ──
        poly_col, guide_col = st.columns([3,1])
        with poly_col:
            st.markdown(f'<div class="bb-ph">📋 TOP 10 ACTIVE MARKETS BY 24H VOLUME ({len(active_markets)} active total)</div>', unsafe_allow_html=True)
            for m in top10:
                is_unusual = m in unusual
                st.markdown(render_poly_card(m, show_unusual=is_unusual), unsafe_allow_html=True)

        with guide_col:
            st.markdown("""<div style="background:#080808;border:1px solid #1A1A1A;padding:12px;font-family:monospace;font-size:10px;color:#888;line-height:1.9">
<span style="color:#FF6600;font-weight:700">HOW TO READ</span><br><br>
<span style="color:#00CC44">ACTIVE</span> = Market open<br>
<span style="color:#FFCC00">RESOLVED</span> = Settled ✓<br>
<span style="color:#FF4444">CLOSED/EXP</span> = Inactive<br><br>
<span style="color:#FF6600">CHARTS ABOVE</span><br>
• Bar 1: 24h volume<br>
• Bar 2: YES probability<br>
• Bar 3: Activity ratio<br><br>
<span style="color:#FF4444">🚨 UNUSUAL</span><br>
≥38% of total vol in 24h<br><br>
<span style="color:#AA44FF">⚡ SIDE LABEL</span><br>
Which outcome unusual volume favors<br><br>
<span style="color:#00CC44">GREEN</span> = YES/higher<br>
<span style="color:#FF4444">RED</span> = NO/lower<br><br>
<span style="color:#444">⚠️ Crowd odds only.<br>Not financial advice.</span>
</div>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 5 — GEO GLOBE (Fixed loading with error handling)
# ════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="bb-ph">🌍 GEOPOLITICAL INTELLIGENCE — LIVE GLOBE + GDELT</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#555;font-family:monospace;font-size:10px;margin-bottom:6px">Drag to rotate · Scroll to zoom · Click markers for intel</div>', unsafe_allow_html=True)

    globe_path = pathlib.Path(__file__).parent / "globe.html"
    if globe_path.exists():
        try:
            globe_html = globe_path.read_text(encoding="utf-8")
            components.html(globe_html, height=600, scrolling=False)
        except Exception as e:
            st.error(f"Error loading globe: {e}")
    else:
        st.markdown("""<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;
padding:16px;font-family:monospace;font-size:12px;color:#FF8C00">
⚠️ globe.html not found in the same folder as sentinel_app.py<br><br>
Place globe.html in your GitHub repo root alongside sentinel_app.py and redeploy.
</div>""", unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    THEATERS = {
        "Middle East + Oil + Hormuz": "Middle East Iran oil Hormuz",
        "China + Taiwan + Semiconductors": "China Taiwan semiconductor chips TSMC",
        "Russia + Ukraine + Energy": "Russia Ukraine energy grain NATO",
        "Africa + Cobalt + Lithium + Coup": "Africa cobalt lithium coup Sahel Mali",
        "Red Sea + Suez + Shipping": "Red Sea Suez shipping Houthi container",
        "South China Sea + Trade": "South China Sea shipping Philippines trade",
    }
    geo_col1, geo_col2 = st.columns([3,1])

    with geo_col1:
        theater_sel = st.selectbox("📡 THEATER INTEL FEED", list(THEATERS.keys()) + ["Custom query…"])
        custom_q = ""
        if theater_sel == "Custom query…":
            custom_q = st.text_input("Custom GDELT query", key="cq")
        query = custom_q if custom_q else THEATERS.get(theater_sel,"")

        if query:
            with st.spinner(f"Fetching GDELT feed for: {query}…"):
                arts = gdelt_news(query, max_rec=12)

            if arts:
                st.markdown(f'<div class="bb-ph">GDELT LIVE FEED — {len(arts)} articles</div>', unsafe_allow_html=True)
                for art in arts:
                    t=art.get("title","")[:100]; u=art.get("url","#")
                    dom=art.get("domain","GDELT"); sd=art.get("seendate","")
                    d=f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd)>=8 else ""
                    st.markdown(render_news_card(t,u,dom,d,"bb-news bb-news-geo"), unsafe_allow_html=True)
            else:
                st.markdown('<div style="background:#0D0D0D;border-left:3px solid #FF6600;padding:10px 12px;font-family:monospace;font-size:11px;color:#888">No articles found in GDELT for this query in the last 48h. Try broadening the search or check back later.</div>', unsafe_allow_html=True)

            if st.session_state.newsapi_key:
                with st.spinner("Loading NewsAPI layer…"):
                    na_arts = newsapi_headlines(st.session_state.newsapi_key, query)
                if na_arts:
                    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
                    st.markdown('<div class="bb-ph">NEWSAPI LAYER — 150K+ SOURCES</div>', unsafe_allow_html=True)
                    for art in na_arts[:8]:
                        title = art.get("title","")
                        if not title or "[Removed]" in title: continue
                        u=art.get("url","#"); src=art.get("source",{}).get("name",""); pub=art.get("publishedAt","")[:10]
                        st.markdown(render_news_card(title[:100],u,src,pub,"bb-news bb-news-macro"), unsafe_allow_html=True)

    with geo_col2:
        st.markdown('<div class="bb-ph">⚠️ THEATER STATUS</div>', unsafe_allow_html=True)
        for name, status, color in [
            ("Middle East","CRITICAL","#FF0000"),("Ukraine","ACTIVE","#FF4444"),
            ("Red Sea","DISRUPTED","#FF4444"),("Sahel","ELEVATED","#FF8C00"),
            ("Hormuz","ELEVATED","#FF8C00"),("Taiwan","MONITORING","#FFCC00"),
            ("S.China Sea","MONITORING","#FFCC00")]:
            st.markdown(f'<div class="theater-row"><span style="color:#CCC">{name}</span><span style="color:{color};font-size:9px;font-weight:700">{status}</span></div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">📖 CONFIDENCE</div>', unsafe_allow_html=True)
        for lbl,c in [("HIGH","#00CC44"),("MEDIUM","#FF8C00"),("LOW","#FFCC00"),("UNCONFIRMED","#555")]:
            st.markdown(f'<div style="font-family:monospace;font-size:10px;padding:3px 0"><span style="color:{c};font-weight:700">{lbl}</span></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 6 — EARNINGS TRACKER
# ════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown('<div class="bb-ph">📅 EARNINGS TRACKER — UPCOMING & RECENT</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=1800)
    def get_earnings_calendar():
        MAJOR = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","JPM","GS","BAC",
                 "NFLX","AMD","INTC","CRM","ORCL","V","MA","WMT","XOM","CVX","UNH",
                 "JNJ","PFE","ABBV","LLY","BRK-B","HD","DIS","SHOP","PLTR","SNOW"]
        rows = []
        for tkr in MAJOR:
            try:
                t = yf.Ticker(tkr); info = t.info; cal = t.calendar
                if cal is not None and not (cal.empty if hasattr(cal,"empty") else False):
                    if isinstance(cal, pd.DataFrame):
                        if "Earnings Date" in cal.index:
                            ed = cal.loc["Earnings Date"]
                            ed = ed.iloc[0] if hasattr(ed,"iloc") else ed
                            eps = float(cal.loc["EPS Estimate"].iloc[0]) if "EPS Estimate" in cal.index else None
                        else: continue
                    elif isinstance(cal, dict):
                        ed = cal.get("Earnings Date", [None]); ed = ed[0] if isinstance(ed,list) else ed
                        eps = cal.get("EPS Estimate",None)
                    else: continue
                    if ed is None: continue
                    rows.append({"Ticker":tkr,"Company":info.get("shortName",tkr)[:22],
                        "EarningsDate":pd.to_datetime(ed).date(),
                        "EPS Est":round(float(eps),2) if eps else None,
                        "Sector":info.get("sector","—")[:14]})
            except: pass
        if not rows: return pd.DataFrame()
        return pd.DataFrame(rows).dropna(subset=["EarningsDate"]).sort_values("EarningsDate")

    ec1, ec2 = st.columns([3,2])
    with ec1:
        st.markdown('<div class="bb-ph">UPCOMING EARNINGS CALENDAR</div>', unsafe_allow_html=True)
        with st.spinner("Fetching earnings calendar (this may take 20-30s)…"):
            earn_df = get_earnings_calendar()
        if earn_df.empty:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No upcoming earnings found. Yahoo Finance may be rate-limiting. Try again shortly.</p>', unsafe_allow_html=True)
        else:
            today = datetime.now().date()
            for _, row in earn_df.iterrows():
                ed = row["EarningsDate"]; days = (ed-today).days if ed>today else 0
                badge = "TODAY" if days==0 else (f"IN {days}D" if days>0 else "RECENT")
                bc = "#FF6600" if days==0 else ("#00AAFF" if days<7 else "#555")
                bc_bg = "rgba(255,102,0,0.08)" if days==0 else ("rgba(0,170,255,0.06)" if days<7 else "transparent")
                eps_str = f"${row['EPS Est']:.2f}" if row.get("EPS Est") is not None else "—"
                ed_fmt = ed.strftime("%b %d") if hasattr(ed, "strftime") else str(ed)
                company = str(row.get('Company',''))
                sector = str(row.get('Sector','—'))
                st.markdown(f"""<div class="earn-card" style="background:{bc_bg}">
  <span class="earn-ticker">{row['Ticker']}</span>
  <div style="min-width:0">
    <div style="color:#CCCCCC;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{company}</div>
    <div style="color:#FF6600;font-size:10px;margin-top:2px;letter-spacing:1px">{sector.upper()}</div>
  </div>
  <span style="color:{bc};font-size:10px;font-weight:700;letter-spacing:1px;white-space:nowrap">{badge}</span>
  <span class="earn-date" style="white-space:nowrap">{ed_fmt}</span>
  <span style="color:#888;font-size:11px;white-space:nowrap">EPS: <span style="color:#FFCC00;font-weight:700">{eps_str}</span></span>
</div>""", unsafe_allow_html=True)

    with ec2:
        st.markdown('<div class="bb-ph">📈 QUICK EARNINGS CHART</div>', unsafe_allow_html=True)
        earn_tkr = st.text_input("Ticker for chart", placeholder="NVDA, AAPL…", key="ec")
        if earn_tkr:
            et = earn_tkr.upper().strip()
            tv_sym_earn = f"NASDAQ:{et}"
            components.html(tv_chart(tv_sym_earn,320), height=325, scrolling=False)
            try:
                income = yf.Ticker(et).quarterly_financials
                if income is not None and not income.empty:
                    st.markdown('<div class="bb-ph" style="margin-top:10px">QUARTERLY FINANCIALS</div>', unsafe_allow_html=True)
                    rev = income.loc["Total Revenue"]/1e9 if "Total Revenue" in income.index else None
                    ni  = income.loc["Net Income"]/1e6   if "Net Income"    in income.index else None
                    for col in list(income.columns[:4]):
                        cstr = str(col)[:10]
                        rv  = f"${rev[col]:.1f}B" if rev is not None and col in rev.index else "—"
                        net_v = float(ni[col]) if ni is not None and col in ni.index else None
                        nc  = "#00CC44" if net_v and net_v>0 else "#FF4444"
                        net_s = f"${net_v:.0f}M" if net_v else "—"
                        st.markdown(f'<div style="display:flex;justify-content:space-between;padding:5px 8px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px"><span style="color:#888">{cstr}</span><span style="color:#CCC">Rev: {rv}</span><span style="color:{nc}">NI: {net_s}</span></div>', unsafe_allow_html=True)
            except: pass

# ════════════════════════════════════════════════════════════════════
# TAB 7 — SENTINEL AI
# ════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.markdown('<div class="bb-ph">🤖 SENTINEL AI — POWERED BY GOOGLE GEMINI</div>', unsafe_allow_html=True)

    if not st.session_state.gemini_key:
        st.markdown("""<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;
padding:16px;font-family:monospace;font-size:12px;color:#FF8C00">
⚠️ Gemini API key required to activate SENTINEL AI.<br><br>
<a href="https://aistudio.google.com/app/apikey" target="_blank" style="color:#FF6600">Get a free key at Google AI Studio →</a><br><br>
<span style="color:#555">Once activated, SENTINEL AI provides:<br>
• /brief — Morning intelligence briefing<br>
• /flash NVDA — Rapid stock analysis<br>
• /geo Red Sea — Geopolitical dashboard<br>
• /scenario Gold — Bull/base/bear scenarios<br>
• /poly Fed — Polymarket analysis<br>
• /rotate — Sector rotation read<br>
• /earnings — Earnings calendar analysis</span></div>""", unsafe_allow_html=True)
    else:
        if st.button("🔍 LIST AVAILABLE GEMINI MODELS"):
            with st.spinner("Fetching model list…"):
                mlist = list_gemini_models(st.session_state.gemini_key)
            for m in mlist:
                st.markdown(f'<div style="font-family:monospace;font-size:11px;padding:2px 0;color:#FF8C00">{m}</div>', unsafe_allow_html=True)
            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        if not st.session_state.chat_history:
            st.markdown("""<div style="background:#001A00;border:1px solid #1A1A1A;border-left:4px solid #00CC44;
padding:14px;font-family:monospace;font-size:12px;color:#CCC;line-height:1.8">
⚡ SENTINEL AI ONLINE — Live market data injected.<br><br>
Try: <span style="color:#FF6600">/brief</span> &nbsp; 
<span style="color:#FF6600">/flash NVDA</span> &nbsp; 
<span style="color:#FF6600">/scenario Gold</span> &nbsp; 
<span style="color:#FF6600">/geo Red Sea</span> &nbsp; 
<span style="color:#FF6600">/poly Fed</span>
</div>""", unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            if msg["role"]=="user":
                st.markdown(f'<div class="chat-user">▶ &nbsp;{_esc(msg["content"])}</div>', unsafe_allow_html=True)
            else:
                content = msg["content"].replace("<","&lt;").replace(">","&gt;")
                st.markdown(f'<div class="chat-ai">⚡ SENTINEL<br><br>{content}</div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        ic, bc = st.columns([5,1])
        with ic:
            user_input = st.text_input("QUERY…",
                placeholder="/brief | /flash TSLA | /scenario Gold | /geo Red Sea | or plain English",
                key="chat_inp", label_visibility="collapsed")
        with bc:
            send = st.button("⚡ SEND", use_container_width=True)

        st.markdown('<div style="color:#555;font-size:9px;font-family:monospace;margin-bottom:4px">QUICK COMMANDS</div>', unsafe_allow_html=True)
        qb = st.columns(7)
        QUICK = {"BRIEF":"/brief","ROTATE":"/rotate","SENTIMENT":"/sentiment",
                 "POLY FED":"/poly Fed rate","RED SEA":"/geo Red Sea",
                 "BTC SCEN":"/scenario Bitcoin","EARNINGS":"/earnings"}
        for col,(lbl,cmd) in zip(qb,QUICK.items()):
            with col:
                if st.button(lbl,use_container_width=True,key=f"qb_{lbl}"):
                    st.session_state.chat_history.append({"role":"user","content":cmd})
                    with st.spinner("⚡ SENTINEL processing…"):
                        resp = gemini_response(cmd,st.session_state.chat_history[:-1],market_snapshot_str())
                    st.session_state.chat_history.append({"role":"assistant","content":resp})
                    st.rerun()

        if st.button("🗑 CLEAR CHAT"):
            st.session_state.chat_history = []; st.rerun()

        if (send or user_input) and user_input:
            st.session_state.chat_history.append({"role":"user","content":user_input})
            with st.spinner("⚡ SENTINEL processing…"):
                resp = gemini_response(user_input,st.session_state.chat_history[:-1],market_snapshot_str())
            st.session_state.chat_history.append({"role":"assistant","content":resp})
            st.rerun()

# ════════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════════
st.markdown('<hr style="border-top:1px solid #1A1A1A;margin:16px 0">', unsafe_allow_html=True)
st.markdown(f"""<div style="font-family:monospace;font-size:9px;color:#333;text-align:center;letter-spacing:1px">
SENTINEL TERMINAL &nbsp;|&nbsp; {now_pst()} &nbsp;|&nbsp;
Yahoo Finance · FRED · Polymarket · GDELT · CoinGecko · Finnhub · NewsAPI · TradingView · Gemini<br>
For research purposes only. Not financial advice.
</div>""", unsafe_allow_html=True)
