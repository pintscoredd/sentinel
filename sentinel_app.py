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

import requests, pandas as pd, json, pathlib, math, re
from datetime import datetime, timedelta
import pytz

from data_fetchers import (
    _safe_float, _safe_int, _esc, fmt_p, fmt_pct, pct_color, _is_english,
    yahoo_quote, get_futures, get_heatmap_data, multi_quotes,
    fred_series, polymarket_events, polymarket_markets,
    fear_greed_crypto, calc_stock_fear_greed,
    crypto_markets, crypto_global,
    gdelt_news, newsapi_headlines, finnhub_news, finnhub_insider, finnhub_officers,
    vix_price, options_chain, options_expiries, sector_etfs, top_movers,
    detect_unusual_poly, market_snapshot_str, _parse_poly_field,
    score_options_chain,
    get_earnings_calendar, is_market_open,
    get_macro_overview, get_macro_calendar, get_ticker_exchange,
    get_full_financials, get_stock_news,
    is_0dte_market_open, get_stock_snapshot, get_spx_metrics,
    fetch_0dte_chain, compute_gex_profile, compute_max_pain, compute_pcr,
    find_gamma_flip, fetch_vix_data, find_target_strike,
    parse_trade_input, generate_recommendation,
    fetch_cboe_gex, compute_cboe_gex_profile, compute_cboe_total_gex, compute_cboe_pcr,
    get_whale_trades, get_exchange_netflow, get_funding_rates,
    get_open_interest, get_liquidations,
)
from ui_components import (
    CHART_LAYOUT, dark_fig, tv_chart, tv_mini, tv_tape,
    yield_curve_chart, yield_history_chart, cpi_vs_rates_chart,
    render_news_card, render_wl_row, render_options_table,
    render_scored_options, render_unusual_trade,
    render_insider_cards, poly_url, poly_status, unusual_side,
    render_poly_card,
    SENTINEL_PROMPT, GEMINI_MODELS, list_gemini_models, gemini_response,
    render_0dte_gex_chart, render_0dte_gex_decoder, render_0dte_recommendation, render_0dte_trade_log
)

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

/* TABS */
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

/* BUTTONS — global */
.stButton > button {
  background: var(--bg1) !important; color: var(--org) !important;
  border: 1px solid var(--org) !important; border-radius: 0 !important;
  font-family: var(--mono) !important; font-size: 10px !important; font-weight: 700 !important;
  letter-spacing: 1px !important; text-transform: uppercase !important; padding: 4px 12px !important;
}
.stButton > button:hover { background: var(--org) !important; color: var(--blk) !important; }

/* ── WATCHLIST DELETE BUTTON — refined, compact, proportional ── */
.wl-delete-col .stButton > button {
  background: transparent !important;
  color: #444 !important;
  border: 1px solid #2A2A2A !important;
  border-radius: 2px !important;
  font-size: 11px !important;
  font-weight: 400 !important;
  letter-spacing: 0 !important;
  padding: 2px 6px !important;
  min-height: 24px !important;
  height: 24px !important;
  line-height: 1 !important;
  width: 24px !important;
  transition: all 0.15s ease !important;
}
.wl-delete-col .stButton > button:hover {
  background: rgba(255, 68, 68, 0.12) !important;
  color: #FF4444 !important;
  border-color: #FF4444 !important;
}

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

/* Keep sidebar toggle always visible */
button[data-testid="stSidebarNavCollapseButton"],
button[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  z-index: 999999 !important;
  position: fixed !important;
  top: 0.5rem !important;
  left: 0.5rem !important;
}

/* MOVE CONTENT UP */
section.main > div.block-container {
  padding-top: 0.25rem !important;
  padding-bottom: 1rem !important;
}
[data-testid="stAppViewContainer"] > section.main {
  padding-top: 0 !important;
}

/* ── AUTO-DISMISS ALERT ANIMATION (3 seconds) ── */
@keyframes sentinelFadeOut {
  0%   { opacity: 1; max-height: 120px; margin-bottom: 8px; }
  70%  { opacity: 1; max-height: 120px; margin-bottom: 8px; }
  100% { opacity: 0; max-height: 0; margin-bottom: 0; padding: 0; overflow: hidden; }
}
.sentinel-alert-dismiss {
  animation: sentinelFadeOut 3s ease-out forwards;
  overflow: hidden;
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
.bb-news a { color: var(--wht); text-decoration: none; font-size: 17px; font-weight: 600; line-height: 1.5; }
.bb-news a:hover { color: var(--org2); text-decoration: underline; }
.bb-meta { color: #AAA; font-size: 11px; margin-top: 4px; letter-spacing: 0.5px; text-align: right; }
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
.opt-tbl { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 13px; }
.opt-tbl th {
  background: var(--bg3); color: var(--org); padding: 6px 9px;
  text-align: right; font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
  border-bottom: 1px solid var(--org);
}
.opt-tbl th:first-child { text-align: left; }
.opt-tbl td { padding: 6px 9px; text-align: right; color: var(--txt); border-bottom: 1px solid var(--bg3); }
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
  padding: 10px 14px; margin: 3px 0; font-family: var(--mono);
}
.ins-card.buy  { border-left-color: var(--grn); }
.ins-card.sell { border-left-color: var(--red); }
.ins-card:hover { background: var(--bg2); }
.ins-name  { color: var(--wht); font-weight: 700; font-size: 14px; }
.ins-role  { color: var(--org2); font-size: 11px; }
.ins-buy   { color: var(--grn); font-weight: 700; font-size: 13px; }
.ins-sell  { color: var(--red); font-weight: 700; font-size: 13px; }
.ins-meta  { color: #AAA; font-size: 11px; }

/* SECTOR CELL */
.sec-cell {
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 12px; margin: 2px 0; font-family: var(--mono); font-size: 13px;
}
.sec-cell.up { background: rgba(0,204,68,0.08); border-left: 3px solid var(--grn); }
.sec-cell.dn { background: rgba(255,68,68,0.08); border-left: 3px solid var(--red); }

/* GAINERS/LOSERS */
.mover-row {
  display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr;
  gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--bg3);
  font-family: var(--mono); font-size: 14px; align-items: center; width:100%;
}
.mover-row:hover { background: var(--bg2); }

/* FUTURES ROW */
.fut-row {
  display: grid; grid-template-columns: 1fr 1.4fr 1.2fr 0.8fr 0.9fr 0.8fr;
  gap: 6px; padding: 5px 10px; border-bottom: 1px solid var(--bg3);
  font-family: var(--mono); font-size: 14px; align-items: center; width:100%;
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
def _get_secret(name, default=""):
    try:
        val = st.secrets[name]
        return val if val else default
    except (KeyError, FileNotFoundError, AttributeError, Exception):
        return default

WATCHLIST_FILE = pathlib.Path(".streamlit/watchlist.json")

def _load_watchlist():
    try:
        if WATCHLIST_FILE.exists():
            return json.loads(WATCHLIST_FILE.read_text())
    except Exception:
        pass
    return ["SPY","QQQ","NVDA","AAPL","GLD","TLT","BTC-USD"]

def _save_watchlist(wl):
    try:
        WATCHLIST_FILE.parent.mkdir(exist_ok=True)
        WATCHLIST_FILE.write_text(json.dumps(wl))
    except Exception:
        pass

DEFAULTS = {
    "gemini_key": _get_secret("GEMINI_API_KEY"),
    "fred_key": _get_secret("FRED_API_KEY"),
    "finnhub_key": _get_secret("FINNHUB_API_KEY"),
    "newsapi_key": _get_secret("NEWSAPI_KEY"),
    "chat_history":[],
    "watchlist": _load_watchlist(),
    "macro_theses":"", "geo_watch":"",
    "wl_add_input":"", "api_panel_open": True,
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

    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700">STATUS</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#555;font-size:9px;font-family:monospace;margin-bottom:4px">Keys loaded from .streamlit/secrets.toml</div>', unsafe_allow_html=True)

    _alpaca_ok = bool(_get_secret("ALPACA_API_KEY")) and bool(_get_secret("ALPACA_SECRET_KEY"))
    for api, ok in [
        ("Yahoo Finance",True),("Polymarket",True),("GDELT",True),
        ("Alpaca (0DTE)", _alpaca_ok),
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

tabs = st.tabs(["BRIEF","MARKETS","SPX 0DTE","MACRO","CRYPTO","POLYMARKET","GEO","EARNINGS","SENTINEL AI"])

# ════════════════════════════════════════════════════════════════════
# TAB 0 — MORNING BRIEF
# ════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="bb-ph">⚡ SENTINEL MORNING BRIEF</div>', unsafe_allow_html=True)

    ref_col, mkt_col = st.columns([1, 1])
    with ref_col:
        if st.button("↺ REFRESH ALL DATA"):
            st.cache_data.clear(); st.rerun()
    with mkt_col:
        mkt_status, mkt_color, mkt_detail = is_market_open()
        st.markdown(
            f'<div style="text-align:right;font-family:monospace;padding:4px 0">'
            f'<span style="color:{mkt_color};font-size:14px;font-weight:900">● {mkt_status}</span>'
            f' <span style="color:#555;font-size:10px">{mkt_detail}</span></div>',
            unsafe_allow_html=True)

    KEY_T = {"SPY":"S&P 500","QQQ":"Nasdaq 100","DIA":"Dow Jones","IWM":"Russell 2K",
             "^TNX":"10Y Yield","DX-Y.NYB":"USD Index","GLD":"Gold","CL=F":"WTI Crude","BTC-USD":"Bitcoin"}
    qs = multi_quotes(list(KEY_T.keys()))
    cols = st.columns(len(qs))
    for col, q in zip(cols, qs):
        chg_str = f"{q['pct']:+.2f}% ({q['change']:+.2f})"
        with col: st.metric(KEY_T.get(q["ticker"],q["ticker"]), fmt_p(q["price"]), delta=chg_str)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    L, R = st.columns([3,2])

    with L:
        st.markdown('<div class="bb-ph">⚡ MARKET SENTIMENT</div>', unsafe_allow_html=True)
        s1,s2,s3 = st.columns(3)
        v = vix_price()
        vix_q = yahoo_quote("^VIX")
        with s1:
            if v:
                lbl = "LOW FEAR" if v<15 else ("MODERATE" if v<25 else ("HIGH FEAR" if v<35 else "PANIC"))
                vix_chg = f"{vix_q['pct']:+.2f}%" if vix_q else ""
                vix_chg_c = pct_color(vix_q['pct']) if vix_q else "#888"
                st.markdown(f'<div class="fg-gauge"><div class="fg-num">{v:.2f}</div><div class="fg-lbl" style="color:#FF8C00">{lbl}</div><div style="color:{vix_chg_c};font-size:13px;font-weight:700;margin-top:4px">{vix_chg}</div><div style="color:#555;font-size:8px;margin-top:2px">VIX</div></div>', unsafe_allow_html=True)
        sfg_val, sfg_lbl = calc_stock_fear_greed()
        with s2:
            if sfg_val:
                sfg_c = "#00CC44" if sfg_val>=55 else ("#FF4444" if sfg_val<35 else "#FF8C00")
                st.markdown(f'<div class="fg-gauge"><div class="fg-num" style="color:{sfg_c}">{sfg_val}</div><div class="fg-lbl" style="color:{sfg_c}">{sfg_lbl}</div><div style="color:#555;font-size:8px;margin-top:2px">STOCK MARKET F&G</div></div>', unsafe_allow_html=True)
        with s3:
            if v:
                posture = "RISK-ON" if v<18 else ("NEUTRAL" if v<25 else "RISK-OFF")
                pc = {"RISK-ON":"#00CC44","NEUTRAL":"#FF8C00","RISK-OFF":"#FF4444"}[posture]
                st.markdown(f'<div class="fg-gauge"><div style="color:#888;font-size:9px;letter-spacing:1px">POSTURE</div><div class="fg-num" style="color:{pc};font-size:24px">{posture}</div></div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Watchlist with full management
        st.markdown('<div class="bb-ph">👁 WATCHLIST</div>', unsafe_allow_html=True)

        wl_a, wl_b = st.columns([3,1])
        with wl_a:
            new_ticker = st.text_input("Add ticker", placeholder="e.g. TSLA", label_visibility="collapsed", key="wl_add")
        with wl_b:
            if st.button("＋ ADD", use_container_width=True):
                t = new_ticker.upper().strip()
                if t and t not in st.session_state.watchlist:
                    st.session_state.watchlist.append(t)
                    _save_watchlist(st.session_state.watchlist)
                    st.rerun()

        wl_qs = multi_quotes(st.session_state.watchlist)

        # ── FIX: Header uses same st.columns proportions as data rows
        # Data row columns: [1.5, 2.0, 1.7, 1.7, 1.5, 0.8]
        hdr_cols = st.columns([1.5, 2.0, 1.7, 1.7, 1.5, 0.8])
        hdr_labels = ["TICKER", "PRICE", "CHG %", "CHG $", "VOLUME", "DEL"]
        for hcol, hlbl in zip(hdr_cols, hdr_labels):
            with hcol:
                st.markdown(
                    f'<div style="font-family:monospace;font-size:9px;color:#FF6600;'
                    f'letter-spacing:1px;padding:4px 0;border-bottom:1px solid #FF6600;'
                    f'font-weight:700">{hlbl}</div>',
                    unsafe_allow_html=True)

        st.markdown('<div style="margin-bottom:4px"></div>', unsafe_allow_html=True)

        for q in wl_qs:
            c = "#00CC44" if q["pct"]>=0 else "#FF4444"
            arr = "▲" if q["pct"]>=0 else "▼"
            # ── FIX: Volume color based on direction (bullish/bearish volume context)
            vol_color = "#00CC44" if q["pct"] >= 0 else "#FF4444"
            vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
            chg_str = f"+{q['change']:.2f}" if q["change"]>=0 else f"{q['change']:.2f}"

            crow = st.columns([1.5, 2.0, 1.7, 1.7, 1.5, 0.8])
            with crow[0]:
                st.markdown(
                    f'<div style="color:#FF6600;font-weight:700;font-family:monospace;'
                    f'font-size:13px;padding:5px 0">{q["ticker"]}</div>',
                    unsafe_allow_html=True)
            with crow[1]:
                st.markdown(
                    f'<div style="color:#FFF;font-family:monospace;font-size:13px;'
                    f'font-weight:600;padding:5px 0">{fmt_p(q["price"])}</div>',
                    unsafe_allow_html=True)
            with crow[2]:
                st.markdown(
                    f'<div style="color:{c};font-family:monospace;font-size:13px;'
                    f'font-weight:700;padding:5px 0">{arr} {abs(q["pct"]):.2f}%</div>',
                    unsafe_allow_html=True)
            with crow[3]:
                st.markdown(
                    f'<div style="color:{c};font-family:monospace;font-size:13px;'
                    f'padding:5px 0">{chg_str}</div>',
                    unsafe_allow_html=True)
            with crow[4]:
                # ── FIX: Volume same font size (13px), color based on daily direction
                st.markdown(
                    f'<div style="color:{vol_color};font-family:monospace;font-size:13px;'
                    f'padding:5px 0;font-weight:500">{vol}</div>',
                    unsafe_allow_html=True)
            with crow[5]:
                # ── FIX: Styled delete button using CSS class
                st.markdown('<div class="wl-delete-col">', unsafe_allow_html=True)
                if st.button("✕", key=f"rm_{q['ticker']}", help=f"Remove {q['ticker']}"):
                    st.session_state.watchlist = [x for x in st.session_state.watchlist if x!=q["ticker"]]
                    _save_watchlist(st.session_state.watchlist)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div style="border-bottom:1px solid #111;margin:0 0 2px 0"></div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ── Sector Pulse
        st.markdown('<div class="bb-ph">🔄 SECTOR PULSE</div>', unsafe_allow_html=True)
        sec_df = sector_etfs()
        if not sec_df.empty:
            for _, row in sec_df.sort_values("Pct",ascending=False).iterrows():
                p = row["Pct"]; cls = "up" if p>=0 else "dn"; sign = "+" if p>=0 else ""
                st.markdown(f'<div class="sec-cell {cls}"><span style="color:#FFF">{row["Sector"]}</span><span style="color:#888;font-size:11px">{row["ETF"]}</span><span style="color:{"#00CC44" if p>=0 else "#FF4444"};font-weight:700">{sign}{p:.2f}%</span></div>', unsafe_allow_html=True)

    with R:
        st.markdown('<div class="bb-ph">🎲 POLYMARKET ACTIVE MARKETS</div>', unsafe_allow_html=True)
        with st.spinner("Loading markets…"):
            poly = polymarket_events(30)
        if poly:
            active_poly = [e for e in poly if poly_status(e)[0]=="ACTIVE"]
            closed_poly = [e for e in poly if poly_status(e)[0] in ("RESOLVED","CLOSED","EXPIRED (pending resolve)")]
            for e in active_poly[:5]:
                st.markdown(render_poly_card(e), unsafe_allow_html=True)
            if closed_poly:
                st.markdown('<div style="color:#FF6600;font-size:10px;letter-spacing:1px;margin:8px 0 4px">RECENTLY CLOSED</div>', unsafe_allow_html=True)
                for e in closed_poly[:3]:
                    st.markdown(render_poly_card(e), unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Could not reach Polymarket API. Check network connectivity.</p>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        st.markdown('<div class="bb-ph">🌍 GEO WATCH</div>', unsafe_allow_html=True)
        with st.spinner("Loading geo feed…"):
            geo_arts = gdelt_news("geopolitical conflict oil market",8)
        if geo_arts:
            seen_titles = set()
            for art in geo_arts[:8]:
                t=art.get("title","")[:90]; u=art.get("url","#"); dom=art.get("domain","GDELT"); sd=art.get("seendate","")
                t_key = t.strip().lower()
                if t_key in seen_titles: continue
                seen_titles.add(t_key)
                if len(seen_titles) > 5: break
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
            _prc = q["price"]
            _chg = q["change"]
            _pct = q["pct"]
            _vol = q["volume"]
            _up = _chg >= 0
            _c = "#00CC44" if _up else "#FF4444"
            _sign = "+" if _up else ""
            _vol_c = "#00CC44" if _vol > 0 else "#888"
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:10px">'
                f'<span style="color:#FFF;font-size:28px;font-weight:700;font-family:monospace">{fmt_p(_prc)}</span>'
                f'<span style="color:{_c};font-size:16px;font-weight:600;font-family:monospace">{_sign}{_pct:.2f}%</span>'
                f'</div>', unsafe_allow_html=True)
            m2, m3, m4 = st.columns(3)
            _card = lambda label, val, color: (
                f'<div style="background:#0A0A0A;border:1px solid #1A1A1A;border-top:2px solid {color};'
                f'padding:10px 14px;font-family:monospace">'
                f'<div style="color:#666;font-size:10px;letter-spacing:1px;margin-bottom:4px">{label}</div>'
                f'<div style="color:{color};font-size:16px;font-weight:700">{val}</div></div>'
            )
            m2.markdown(_card("CHANGE", f"{_sign}{_chg:.2f}", _c), unsafe_allow_html=True)
            m3.markdown(_card("VOLUME", f"{_vol:,}", _vol_c), unsafe_allow_html=True)
            m4.markdown(_card("1D CHG%", f"{_sign}{_pct:.2f}%", _c), unsafe_allow_html=True)

            TV_MAP = {"SPY":"AMEX:SPY","QQQ":"NASDAQ:QQQ","NVDA":"NASDAQ:NVDA","AAPL":"NASDAQ:AAPL",
                      "TSLA":"NASDAQ:TSLA","MSFT":"NASDAQ:MSFT","GOOGL":"NASDAQ:GOOGL","AMZN":"NASDAQ:AMZN",
                      "META":"NASDAQ:META","GLD":"AMEX:GLD","TLT":"NASDAQ:TLT","IWM":"AMEX:IWM",
                      "BTC-USD":"COINBASE:BTCUSD","ETH-USD":"COINBASE:ETHUSD",
                      "GC=F":"COMEX:GC1!","CL=F":"NYMEX:CL1!","^TNX":"TVC:TNX","^VIX":"TVC:VIX","DXY":"TVC:DXY"}
            if tkr in TV_MAP:
                tv_sym = TV_MAP[tkr]
            else:
                with st.spinner("Detecting exchange…"):
                    tv_sym = get_ticker_exchange(tkr)
            st.markdown('<div class="bb-ph" style="margin-top:8px">CHART — TRADINGVIEW (RSI + SMA)</div>', unsafe_allow_html=True)
            components.html(tv_chart(tv_sym, 480), height=485, scrolling=False)

            st.markdown('<div class="bb-ph">📋 OPTIONS INTELLIGENCE — ADAPTIVE SCORING ENGINE</div>', unsafe_allow_html=True)
            expiries = options_expiries(tkr)
            selected_exp = None
            if expiries:
                def _fmt_exp(d):
                    try: return datetime.strptime(str(d), "%Y-%m-%d").strftime("%B %-d, %Y")
                    except: return str(d)
                selected_exp = st.selectbox("EXPIRY DATE", expiries, index=0, key=f"exp_{tkr}", format_func=_fmt_exp)
            with st.spinner("Loading options…"):
                calls, puts, exp_date = options_chain(tkr, selected_exp)
            if calls is not None:
                try:
                    exp_dt = datetime.strptime(str(exp_date), "%Y-%m-%d")
                    exp_fmt = exp_dt.strftime("%B %-d, %Y")
                except:
                    exp_fmt = str(exp_date)

                try:
                    current_vix = vix_price()
                except:
                    current_vix = 20.0

                scored = score_options_chain(calls, puts, q["price"], vix=current_vix)

                vix_str = f"{current_vix:.1f}" if current_vix else "N/A"
                if current_vix and current_vix > 25:
                    regime = f'<span style="color:#FF4444;font-weight:700">HIGH VOL (VIX {vix_str})</span> — Δ-weighted'
                elif current_vix and current_vix < 15:
                    regime = f'<span style="color:#00CC44;font-weight:700">LOW VOL (VIX {vix_str})</span> — Flow-weighted'
                else:
                    regime = f'<span style="color:#FF8C00;font-weight:700">NEUTRAL (VIX {vix_str})</span> — Balanced'

                st.markdown(f'<div style="color:#888;font-size:11px;font-family:monospace;margin-bottom:6px">EXPIRY: {exp_fmt} | CURRENT: {fmt_p(q["price"])} | REGIME: {regime}</div>', unsafe_allow_html=True)

                cc, pc = st.columns(2)
                with cc:
                    st.markdown('<div style="color:#00CC44;font-size:10px;font-weight:700;letter-spacing:2px">▲ TOP CALLS (by score)</div>', unsafe_allow_html=True)
                    st.markdown(render_scored_options(scored["top_calls"], side="calls"), unsafe_allow_html=True)
                with pc:
                    st.markdown('<div style="color:#FF4444;font-size:10px;font-weight:700;letter-spacing:2px">▼ TOP PUTS (by score)</div>', unsafe_allow_html=True)
                    st.markdown(render_scored_options(scored["top_puts"], side="puts"), unsafe_allow_html=True)

                if scored.get("unusual"):
                    st.markdown(render_unusual_trade(scored["unusual"], ticker=tkr, expiry=exp_fmt), unsafe_allow_html=True)

                with st.expander("📊 **FULL OPTIONS CHAIN**", expanded=False):
                    fc, fp = st.columns(2)
                    with fc:
                        st.markdown('<div style="color:#00CC44;font-size:9px;font-weight:700;letter-spacing:2px">▲ ALL CALLS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(calls, "calls", q["price"]), unsafe_allow_html=True)
                    with fp:
                        st.markdown('<div style="color:#FF4444;font-size:9px;font-weight:700;letter-spacing:2px">▼ ALL PUTS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(puts, "puts", q["price"]), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Options unavailable for this ticker.</p>', unsafe_allow_html=True)

            st.markdown('<div class="bb-ph" style="margin-top:12px">🔍 INSIDER TRANSACTIONS</div>', unsafe_allow_html=True)
            if st.session_state.finnhub_key:
                with st.spinner("Loading insider data…"):
                    ins = finnhub_insider(tkr, st.session_state.finnhub_key)
                if ins:
                    st.markdown(render_insider_cards(ins[:10], tkr, st.session_state.finnhub_key), unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No recent insider transactions found.</p>', unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Add Finnhub key in sidebar.</p>', unsafe_allow_html=True)
        else:
            st.error(f"No data for '{tkr}'. Check ticker symbol.")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

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
    st.markdown('<div class="bb-ph">🗺 S&P 500 MARKET HEATMAP — FINVIZ STYLE</div>', unsafe_allow_html=True)
    with st.spinner("Building heatmap (scanning ~120 stocks)…"):
        hm_data = get_heatmap_data()
    if hm_data:
        hm_df = pd.DataFrame(hm_data)
        hm_df["pct_capped"] = hm_df["pct"].clip(-5, 5)
        hm_df["label"] = hm_df.apply(lambda r: f"{r['ticker']}<br>{r['pct']:+.2f}%", axis=1)

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
        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Heatmap data loading…</p>', unsafe_allow_html=True)

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
# TAB 2 — SPX 0DTE
# ════════════════════════════════════════════════════════════════════
with tabs[2]:
    if "trade_log_0dte" not in st.session_state:
        st.session_state.trade_log_0dte = []

    _alpaca_present = bool(_get_secret("ALPACA_API_KEY")) and bool(_get_secret("ALPACA_SECRET_KEY"))
    if not _alpaca_present:
        st.markdown("""<div style="background:#1A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;
padding:16px;font-family:monospace;font-size:12px;color:#FF8C00">
🔴 ALPACA API KEYS MISSING — Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .streamlit/secrets.toml<br><br>
<a href="https://app.alpaca.markets/signup" target="_blank" style="color:#FF6600">
Get your free Alpaca API keys → alpaca.markets</a></div>""", unsafe_allow_html=True)
    else:
        _0dte_open, _0dte_msg = is_0dte_market_open()

        # ── FIX: Market status alert auto-dismisses after 3 seconds via CSS animation
        if _0dte_open:
            st.markdown(
                '<div class="sentinel-alert-dismiss" style="font-family:monospace;font-size:12px;'
                'color:#00CC44;font-weight:700;background:#002200;border:1px solid #00CC44;'
                'padding:8px 14px;letter-spacing:1px;">'
                '⚡ ALPACA API ACTIVE: Institutional Real-Time Options Feed'
                '</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="sentinel-alert-dismiss" style="background:#220000;border:1px solid #FF4444;'
                'padding:12px 14px;font-family:monospace;font-size:13px;color:#FF4444;'
                'font-weight:700;letter-spacing:1px;">'
                '🛑 MARKET CLOSED: Showing latest available 0DTE chain.'
                f'<br><span style="color:#888;font-size:11px;font-weight:400">{_0dte_msg}</span>'
                '</div>', unsafe_allow_html=True)

        st.markdown('<div class="bb-ph">⚡ SPX 0DTE — GAMMA EXPOSURE & TRADE ENGINE</div>', unsafe_allow_html=True)

        _0dte_ref, _0dte_stat = st.columns([1, 4])
        with _0dte_ref:
            if st.button("↺ REFRESH 0DTE", key="refresh_0dte"):
                fetch_0dte_chain.clear()
                get_stock_snapshot.clear()
                fetch_vix_data.clear()
                st.rerun()
        with _0dte_stat:
            _ET = pytz.timezone("US/Eastern")
            _now_et = datetime.now(_ET).strftime("%H:%M:%S ET")
            st.markdown(f'<div style="text-align:right;font-family:monospace;padding:6px 0;color:#555;font-size:10px">'
                        f'Last refresh: {_now_et} | Auto-refresh: 30s cache</div>', unsafe_allow_html=True)

        _spx = get_spx_metrics()
        _vix_data = fetch_vix_data()
        _0dte_chain, _chain_status = fetch_0dte_chain("SPY")

        if _spx:
            _spot, _vwap, _em = _spx["spot"], _spx["vwap"], round(_spx["high"] - _spx["low"], 1)
            _m1, _m2, _m3, _m4 = st.columns(4)
            with _m1: st.metric("SPX SPOT", f"${_spot:,.2f}")
            with _m2: st.metric("EXPECTED MOVE", f"±{_em:.1f}")
            with _m3:
                _vd = _spot - _vwap
                st.metric("VWAP", f"${_vwap:,.2f}", delta=f"{_vd:+.1f} vs Spot",
                          delta_color="normal" if _vd >= 0 else "inverse")
            with _m4: st.metric("CONTRACTS", f"{len(_0dte_chain)}",
                                delta=_chain_status if _chain_status != "OK" else "Live")
        else:
            st.markdown('<div style="color:#888;font-family:monospace;font-size:11px;padding:8px">'
                        'SPX data unavailable — check Alpaca API connection.</div>', unsafe_allow_html=True)

        _v1, _v2, _v3, _v4 = st.columns(4)
        with _v1:
            _vix_val = _vix_data.get("vix")
            if _vix_val:
                _vl = "LOW" if _vix_val < 15 else ("MOD" if _vix_val < 25 else "HIGH")
                st.metric("VIX", f"{_vix_val:.2f}", delta=_vl)
            else: st.metric("VIX", "—")
        with _v2:
            _v9d = _vix_data.get("vix9d")
            st.metric("VIX9D", f"{_v9d:.2f}" if _v9d else "—")
        with _v3:
            _ctg = _vix_data.get("contango")
            if _ctg is not None:
                st.metric("TERM STRUCTURE", "✅ Contango" if _ctg else "⚠️ Backwardation",
                          delta_color="normal" if _ctg else "inverse")
            else: st.metric("TERM STRUCTURE", "—")
        with _v4:
            _pcr = compute_pcr(_0dte_chain) if _0dte_chain else None
            if _pcr is None:
                _cboe_spot_pcr, _cboe_opts_pcr = fetch_cboe_gex("SPX")
                _pcr = compute_cboe_pcr(_cboe_opts_pcr)
                _pcr_src = "CBOE" if _pcr is not None else None
            else:
                _pcr_src = "0DTE"
            if _pcr is not None:
                _pl = "Bullish" if _pcr < 0.8 else ("Bearish" if _pcr > 1.0 else "Neutral")
                st.metric("PUT/CALL RATIO", f"{_pcr:.2f}", delta=f"{_pl} ({_pcr_src})" if _pcr_src else _pl)
            else: st.metric("PUT/CALL RATIO", "—")

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        with st.expander("⚡ AUTONOMOUS TRADE ANALYZER", expanded=False):
            st.markdown('<div style="color:#888;font-family:monospace;font-size:10px;margin-bottom:8px">'
                        'Automatically evaluates real-time VWAP, Gamma profile, PCR, and Volatility to generate '
                        'a directional bias and trading target.</div>',
                        unsafe_allow_html=True)

            _ac, _cc = st.columns([1, 4])
            with _ac: _analyze_clicked = st.button("⚡ ANALYZE NOW", key="analyze_0dte", use_container_width=True)
            with _cc:
                if st.button("CLEAR LOG", key="clear_log_0dte"):
                    st.session_state.trade_log_0dte = []
                    st.rerun()

            if _analyze_clicked:
                if not _0dte_chain:
                    st.markdown('<div style="color:#FF4444;font-family:monospace;font-size:12px;padding:8px">'
                                '⚠️ No options data available.</div>',
                                unsafe_allow_html=True)
                else:
                    _rec = generate_recommendation(_0dte_chain, _spx, _vix_data)
                    if _rec:
                        st.markdown(render_0dte_recommendation(_rec), unsafe_allow_html=True)
                        if "NO TRADE" not in _rec['recommendation']:
                            _ET_log = pytz.timezone("US/Eastern")
                            _log_time = datetime.now(_ET_log).strftime("%I:%M %p")
                            st.session_state.trade_log_0dte.append(
                                f"[{_log_time}] {_rec['recommendation'].replace('RECOMMENDATION: ', '')}")

        if st.session_state.trade_log_0dte:
            _log_entries = st.session_state.trade_log_0dte[-10:]
            st.markdown(render_0dte_trade_log(_log_entries), unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        st.markdown('<div class="bb-ph">📊 GAMMA EXPOSURE (GEX) PROFILE</div>', unsafe_allow_html=True)

        _exp_col, _range_col = st.columns([2, 2])
        with _exp_col:
            _exp_choice = st.selectbox(
                "Expiration Filter",
                options=["0DTE (Today Only)", "≤ 7 Days (Weekly)", "≤ 30 Days", "≤ 45 DTE", "All (≤ 1 Year)"],
                index=3,
                key="gex_exp_filter",
                help="Which expirations to include in the GEX calculation"
            )
        with _range_col:
            _chart_range_pct = st.selectbox(
                "Chart Strike Range",
                options=["±2% (~±140 pts)", "±3% (~±210 pts)", "±5% (~±350 pts)", "±7% (~±490 pts)"],
                index=2,
                key="gex_range",
                help="Strike range displayed on the chart"
            )

        _exp_days_map = {
            "0DTE (Today Only)": 1, "≤ 7 Days (Weekly)": 7,
            "≤ 30 Days": 30, "≤ 45 DTE": 45, "All (≤ 1 Year)": 365,
        }
        _range_pct_map = {
            "±2% (~±140 pts)": 0.02, "±3% (~±210 pts)": 0.03,
            "±5% (~±350 pts)": 0.05, "±7% (~±490 pts)": 0.07,
        }
        _exp_limit = _exp_days_map.get(_exp_choice, 45)
        _chart_pct = _range_pct_map.get(_chart_range_pct, 0.05)

        _cboe_spot, _cboe_opts = fetch_cboe_gex("SPX")
        _use_cboe = _cboe_spot is not None and _cboe_opts is not None

        if _use_cboe:
            _gex = compute_cboe_gex_profile(_cboe_spot, _cboe_opts,
                                             expiry_limit_days=_exp_limit,
                                             strike_pct=_chart_pct + 0.02)
            _total_gex_bn = compute_cboe_total_gex(_cboe_spot, _cboe_opts)
            _spy_spot_gex = _cboe_spot / 10
            _gex_source = f"CBOE Delayed • {_exp_choice} • Spot: ${_cboe_spot:,.0f}"
        elif _0dte_chain and _spx:
            _spy_spot_gex = _spx["spot"] / 10
            _gex = compute_gex_profile(_0dte_chain, _spy_spot_gex)
            _total_gex_bn = None
            _gex_source = "Alpaca 0DTE (CBOE unavailable)"
        else:
            _gex = {}
            _total_gex_bn = None
            _gex_source = ""

        _gf_spy = find_gamma_flip(_gex) if _gex else None
        _mp_spy = compute_max_pain(_0dte_chain) if _0dte_chain else None
        _spot_for_chart = _cboe_spot if _use_cboe else (_spx["spot"] if _spx else None)

        if _gex:
            _src_html = (f'<div style="color:#555;font-family:monospace;font-size:10px;margin-bottom:4px">'
                         f'Source: {_gex_source}')
            if _total_gex_bn is not None:
                _gex_clr = "#00CC44" if _total_gex_bn >= 0 else "#FF4444"
                _src_html += (f' &nbsp;|&nbsp; Total Net GEX: '
                              f'<span style="color:{_gex_clr};font-weight:600">'
                              f'${_total_gex_bn:+.2f} Bn</span>')
            _src_html += "</div>"
            st.markdown(_src_html, unsafe_allow_html=True)

            _gex_col, _info_col = st.columns([3, 2])
            with _gex_col:
                _fig = render_0dte_gex_chart(_gex, _gf_spy, _mp_spy,
                                             spot_spx=_spot_for_chart,
                                             display_pct=_chart_pct)
                if _fig:
                    st.plotly_chart(_fig, width="stretch", config={'displayModeBar': False})
                else:
                    st.markdown('<div style="color:#555;font-family:monospace;font-size:11px">GEX data unavailable.</div>', unsafe_allow_html=True)
            with _info_col:
                _wall_strike, _wall_gex = None, 0
                for _wk, _wv in _gex.items():
                    if abs(_wv) > abs(_wall_gex):
                        _wall_gex, _wall_strike = _wv, _wk
                _wall_spx = f"${_wall_strike * 10:,.0f}" if _wall_strike else "—"
                _wall_dir = "Call Wall" if _wall_gex >= 0 else "Put Wall"
                st.markdown(render_0dte_gex_decoder(
                    _gf_spy, _mp_spy, _wall_spx, _wall_dir,
                    spot_spx=_spot_for_chart,
                    wall_gex_m=abs(_wall_gex) if _wall_gex else None
                ), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#555;font-family:monospace;font-size:11px;padding:20px;text-align:center">'
                        '📊 GEX Profile unavailable — CBOE could not be fetched and no 0DTE chain loaded.</div>',
                        unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 3 — MACRO
# ════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="bb-ph">📈 MACRO — FRED DATA DASHBOARD</div>', unsafe_allow_html=True)

    if not st.session_state.fred_key:
        st.markdown("""<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;
padding:16px;font-family:monospace;font-size:12px;color:#FF8C00">
⚠️ FRED API key required for macro data.<br><br>
<a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank" style="color:#FF6600">
Get your free FRED key in 30 seconds →</a></div>""", unsafe_allow_html=True)
    else:
        # ════════════════════════════════════════
        # MACRO OVERVIEW — AI-style environment scorecard
        # ════════════════════════════════════════
        st.markdown('<div class="bb-ph">🧠 US MACRO ENVIRONMENT OVERVIEW</div>', unsafe_allow_html=True)
        with st.spinner("Computing macro environment…"):
            macro_ov = get_macro_overview(st.session_state.fred_key)

        if macro_ov:
            _env_label = macro_ov["env_label"]
            _env_color = macro_ov["env_color"]
            _env_desc  = macro_ov["env_desc"]
            _signals   = macro_ov["signals"]
            _pct       = macro_ov["pct"]
            _total     = macro_ov["total_score"]
            _max       = macro_ov["max_score"]

            # Big environment banner
            st.markdown(
                f'<div style="background:#0A0A0A;border:1px solid {_env_color};border-left:5px solid {_env_color};'
                f'padding:14px 18px;font-family:monospace;margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<div>'
                f'<div style="color:{_env_color};font-size:18px;font-weight:900;letter-spacing:2px">{_env_label}</div>'
                f'<div style="color:#AAA;font-size:11px;margin-top:4px;max-width:580px;line-height:1.6">{_env_desc}</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:90px">'
                f'<div style="color:{_env_color};font-size:30px;font-weight:900">{_total:+d}</div>'
                f'<div style="color:#555;font-size:10px">of ±{_max} pts</div>'
                f'</div>'
                f'</div></div>', unsafe_allow_html=True)

            # Signal grid
            _sig_cols = st.columns(len(_signals) if len(_signals) <= 4 else 4)
            for i, (sig_name, sig) in enumerate(_signals.items()):
                col_idx = i % 4
                with _sig_cols[col_idx]:
                    _sc = sig["color"]
                    _arrow = "▲" if sig["score"] > 0 else ("▼" if sig["score"] < 0 else "─")
                    st.markdown(
                        f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid {_sc};'
                        f'padding:10px 12px;font-family:monospace;margin-bottom:6px">'
                        f'<div style="color:#666;font-size:9px;letter-spacing:1px;margin-bottom:3px">{sig_name.upper()}</div>'
                        f'<div style="color:{_sc};font-size:12px;font-weight:700">{_arrow} {sig["label"]}</div>'
                        f'</div>', unsafe_allow_html=True)

            # Second row of signals if > 4
            if len(_signals) > 4:
                _sig_list = list(_signals.items())
                _sig_cols2 = st.columns(min(len(_sig_list) - 4, 4))
                for i, (sig_name, sig) in enumerate(_sig_list[4:8]):
                    with _sig_cols2[i]:
                        _sc = sig["color"]
                        _arrow = "▲" if sig["score"] > 0 else ("▼" if sig["score"] < 0 else "─")
                        st.markdown(
                            f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid {_sc};'
                            f'padding:10px 12px;font-family:monospace;margin-bottom:6px">'
                            f'<div style="color:#666;font-size:9px;letter-spacing:1px;margin-bottom:3px">{sig_name.upper()}</div>'
                            f'<div style="color:{_sc};font-size:12px;font-weight:700">{_arrow} {sig["label"]}</div>'
                            f'</div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Macro overview loading…</p>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ════════════════════════════════════════
        # MACRO CALENDAR — Upcoming economic events
        # ════════════════════════════════════════
        st.markdown('<div class="bb-ph">📅 MACRO ECONOMIC CALENDAR — UPCOMING RELEASES</div>', unsafe_allow_html=True)
        with st.spinner("Loading macro calendar…"):
            macro_cal = get_macro_calendar(st.session_state.fred_key)

        if macro_cal:
            from datetime import date as _today_date
            _today = _today_date.today()
            _cal_hdr = (
                '<div style="display:grid;grid-template-columns:100px 1fr 90px;gap:8px;'
                'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                '<span>DATE</span><span>EVENT</span><span>IMPORTANCE</span></div>'
            )
            st.markdown(_cal_hdr, unsafe_allow_html=True)
            for evt in macro_cal[:20]:
                _ed = evt["date"]
                _days_away = (_ed - _today).days
                _date_str = _ed.strftime("%b %d, %Y")
                _badge = "TODAY" if _days_away == 0 else (f"IN {_days_away}D" if _days_away > 0 else "PAST")
                _imp = evt.get("importance", "MEDIUM")
                _imp_c = "#FF4444" if _imp == "HIGH" else "#FF8C00"
                _row_bg = "background:rgba(255,102,0,0.05);" if _days_away <= 2 else ""
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:100px 1fr 90px;gap:8px;'
                    f'padding:6px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:12px;{_row_bg}">'
                    f'<span style="color:#888">{_date_str}</span>'
                    f'<span style="color:#CCC">{evt["name"]} '
                    f'<span style="color:#555;font-size:10px">({_badge})</span></span>'
                    f'<span style="color:{_imp_c};font-weight:700;font-size:10px">{_imp}</span>'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="background:#080808;border-left:3px solid #FF6600;padding:10px 14px;'
                'font-family:monospace;font-size:11px;color:#888">'
                'Economic calendar requires FRED API key. Releases shown include: CPI, Jobs Report, '
                'FOMC decisions, PCE, GDP, Retail Sales, PPI, PMIs, and more.</div>',
                unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        mc1, mc2 = st.columns([2, 2])
        with mc1:
            st.markdown('<div class="bb-ph">📉 YIELD CURVE (LIVE FROM FRED)</div>', unsafe_allow_html=True)
            with st.spinner("Loading yield curve…"):
                fig_yc = yield_curve_chart(st.session_state.fred_key, 260)
            if fig_yc:
                st.plotly_chart(fig_yc, width="stretch")
                df_2y = fred_series("DGS2", st.session_state.fred_key, 3)
                df_10y = fred_series("DGS10", st.session_state.fred_key, 3)
                if df_2y is not None and df_10y is not None and not df_2y.empty and not df_10y.empty:
                    sp = round(df_10y["value"].iloc[-1] - df_2y["value"].iloc[-1], 2)
                    if sp < 0:
                        st.markdown(f'<div style="background:#1A0000;border-left:3px solid #FF0000;padding:8px 12px;font-family:monospace;font-size:11px;color:#FF8C00">⚠️ INVERTED: 10Y-2Y = {sp:.2f}%. Recession lead: 12-18 months avg.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="background:#001A00;border-left:3px solid #00CC44;padding:8px 12px;font-family:monospace;font-size:11px;color:#CCC">✅ NORMAL: 10Y-2Y = +{sp:.2f}%</div>', unsafe_allow_html=True)

                st.markdown('<div class="bb-ph" style="margin-top:8px">📊 CPI vs FED FUNDS vs CORE PCE</div>', unsafe_allow_html=True)
                with st.spinner("Loading inflation data…"):
                    fig_cpi = cpi_vs_rates_chart(st.session_state.fred_key, 250)
                if fig_cpi:
                    st.plotly_chart(fig_cpi, width="stretch")
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

        st.markdown('<div class="bb-ph">📈 MULTI-MATURITY YIELD HISTORY — 3 YEARS (LIVE FRED)</div>', unsafe_allow_html=True)
        with st.spinner("Loading yield history…"):
            fig_hist = yield_history_chart(st.session_state.fred_key, 240)
        if fig_hist:
            st.plotly_chart(fig_hist, width="stretch")
        else:
            st.markdown('<p style="color:#555;font-family:monospace">Yield history data loading…</p>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        st.markdown('<div class="bb-ph">USD INDEX — DXY (YAHOO FINANCE)</div>', unsafe_allow_html=True)
        dxy_q = yahoo_quote("DX-Y.NYB")
        if dxy_q:
            dxy_c = pct_color(dxy_q["pct"])
            st.markdown(f'<div style="background:#0D0D0D;border:1px solid #222;border-top:2px solid #FF6600;padding:14px;font-family:monospace">'
                        f'<div style="color:#FF6600;font-size:10px;letter-spacing:1px">DXY — US DOLLAR INDEX</div>'
                        f'<div style="color:#FFF;font-size:28px;font-weight:700;margin-top:4px">{dxy_q["price"]:.2f}</div>'
                        f'<div style="color:{dxy_c};font-size:14px;font-weight:600;margin-top:2px">{dxy_q["pct"]:+.2f}% ({dxy_q["change"]:+.2f})</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">DXY data unavailable</p>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 4 — CRYPTO
# ════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="bb-ph">💰 CRYPTO — COINGECKO + TRADINGVIEW</div>', unsafe_allow_html=True)

    with st.spinner("Loading crypto globals…"):
        gdata = crypto_global()
    if gdata:
        g1,g2,g3,g4 = st.columns(4)
        total_cap = gdata.get("total_market_cap",{}).get("usd",0)
        btc_dom   = gdata.get("market_cap_percentage",{}).get("btc",0)
        eth_dom   = gdata.get("market_cap_percentage",{}).get("eth",0)
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
            cdata = crypto_markets()
        if cdata and isinstance(cdata, list):
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
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">CoinGecko data unavailable. Rate limits may apply — try again in a minute.</p>', unsafe_allow_html=True)

    with cr2:
        st.markdown('<div class="bb-ph">📈 BTC/USD — TRADINGVIEW</div>', unsafe_allow_html=True)
        components.html(tv_chart("COINBASE:BTCUSD", 460), height=465, scrolling=False)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-ph">📈 ETH/USD — TRADINGVIEW</div>', unsafe_allow_html=True)
    components.html(tv_chart("COINBASE:ETHUSD", 320), height=325, scrolling=False)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-ph">🐋 WHALE FLOWS — LARGE TRADES (≥$500K) + EXCHANGE NETFLOW</div>', unsafe_allow_html=True)

    whale_col, exch_col = st.columns([3, 2])

    with whale_col:
        whale_asset = st.radio("Asset", ["BTCUSDT", "ETHUSDT"], horizontal=True, key="whale_asset")
        with st.spinner("Loading whale trades…"):
            whales = get_whale_trades(whale_asset)
        if whales:
            total_buy = sum(t["usd"] for t in whales if t["side"] == "BUY")
            total_sell = sum(t["usd"] for t in whales if t["side"] == "SELL")
            net = total_buy - total_sell
            net_c = "#00CC44" if net >= 0 else "#FF4444"
            net_lbl = "NET BUY" if net >= 0 else "NET SELL"
            st.markdown(
                f'<div style="display:flex;gap:18px;margin-bottom:8px;font-family:monospace;font-size:12px">'
                f'<span style="color:#00CC44;font-weight:700">BUY: ${total_buy:,.0f}</span>'
                f'<span style="color:#FF4444;font-weight:700">SELL: ${total_sell:,.0f}</span>'
                f'<span style="color:{net_c};font-weight:700">{net_lbl}: ${abs(net):,.0f}</span>'
                f'</div>', unsafe_allow_html=True)
            hdr = ('<div style="display:grid;grid-template-columns:70px 55px 100px 110px 100px;gap:6px;'
                   'padding:4px 8px;border-bottom:1px solid #FF6600;font-family:monospace;'
                   'font-size:9px;color:#FF6600;letter-spacing:1px">'
                   '<span>TIME</span><span>SIDE</span><span>AMOUNT</span><span>USD VALUE</span><span>PRICE</span></div>')
            st.markdown(hdr, unsafe_allow_html=True)
            for t in whales:
                sc = "#00CC44" if t["side"] == "BUY" else "#FF4444"
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:70px 55px 100px 110px 100px;gap:6px;'
                    f'padding:4px 8px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:12px">'
                    f'<span style="color:#888">{t["time"]}</span>'
                    f'<span style="color:{sc};font-weight:700">{t["side"]}</span>'
                    f'<span style="color:#FFF">{t["qty"]:,.4f}</span>'
                    f'<span style="color:{sc};font-weight:600">${t["usd"]:,.0f}</span>'
                    f'<span style="color:#888">${t["price"]:,.2f}</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No whale trades detected in recent window.</p>', unsafe_allow_html=True)

    with exch_col:
        st.markdown('<div style="color:#FF6600;font-size:10px;letter-spacing:1px;margin-bottom:6px;font-family:monospace">EXCHANGE BTC VOLUME (24H)</div>', unsafe_allow_html=True)
        with st.spinner("Loading exchanges…"):
            exchanges = get_exchange_netflow()
        if exchanges:
            names = [e["name"][:15] for e in exchanges]
            vols = [e["btc_vol_24h"] for e in exchanges]
            trusts = [e["trust_score"] for e in exchanges]
            colors = ["#FF6600" if t >= 8 else "#AA3300" if t >= 5 else "#442200" for t in trusts]
            fig_ex = dark_fig(340)
            fig_ex.add_trace(go.Bar(
                x=vols, y=names, orientation="h",
                marker=dict(color=colors, line=dict(width=0)),
                text=[f"{v:,.0f} BTC (Trust:{t})" for v, t in zip(vols, trusts)],
                textposition="outside",
                textfont=dict(size=9, color="#FF8C00"),
            ))
            fig_ex.update_layout(
                margin=dict(l=0, r=100, t=10, b=0), height=340,
                xaxis=dict(showgrid=False, color="#444"),
                yaxis=dict(autorange="reversed", tickfont=dict(size=10, color="#CCC")),
            )
            st.plotly_chart(fig_ex, width="stretch")
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Exchange data unavailable.</p>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-ph">💥 LIQUIDATION HEATMAP + CRYPTO RISK DASHBOARD</div>', unsafe_allow_html=True)

    liq_col, risk_col = st.columns([3, 2])

    with liq_col:
        with st.spinner("Loading liquidations…"):
            liqs = get_liquidations()
        if liqs:
            coins_l = list(liqs.keys())
            long_vals = [liqs[c]["long_liq"] / 1e6 for c in coins_l]
            short_vals = [liqs[c]["short_liq"] / 1e6 for c in coins_l]
            fig_liq = dark_fig(280)
            fig_liq.add_trace(go.Bar(name="Long Liqs", x=coins_l, y=long_vals,
                                     marker_color="#FF4444", text=[f"${v:.1f}M" for v in long_vals],
                                     textposition="outside", textfont=dict(size=9, color="#FF4444")))
            fig_liq.add_trace(go.Bar(name="Short Liqs", x=coins_l, y=short_vals,
                                     marker_color="#00CC44", text=[f"${v:.1f}M" for v in short_vals],
                                     textposition="outside", textfont=dict(size=9, color="#00CC44")))
            fig_liq.update_layout(
                barmode="group", margin=dict(l=0, r=0, t=30, b=0), height=280,
                title=dict(text="LIQUIDATIONS ($M) — LONG vs SHORT", font=dict(size=11, color="#FF6600"), x=0),
                xaxis=dict(color="#666"), yaxis=dict(showgrid=False, color="#444"),
                legend=dict(font=dict(size=9, color="#888"), bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_liq, width="stretch")
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Liquidation data unavailable.</p>', unsafe_allow_html=True)

        with st.spinner("Loading open interest…"):
            oi_data = get_open_interest()
        if oi_data:
            oi_coins = [o["symbol"] for o in oi_data]
            oi_vals = [o["oi_usd"] / 1e9 for o in oi_data]
            fig_oi = dark_fig(250)
            fig_oi.add_trace(go.Bar(
                x=oi_coins, y=oi_vals,
                marker_color="#FF8C00",
                text=[f"${v:.2f}B" for v in oi_vals],
                textposition="outside",
                textfont=dict(size=9, color="#FF8C00"),
            ))
            fig_oi.update_layout(
                margin=dict(l=0, r=0, t=30, b=0), height=250,
                title=dict(text="OPEN INTEREST ($B)", font=dict(size=11, color="#FF6600"), x=0),
                xaxis=dict(color="#666"), yaxis=dict(showgrid=False, color="#444"),
            )
            st.plotly_chart(fig_oi, width="stretch")

    with risk_col:
        with st.spinner("Loading funding rates…"):
            funding = get_funding_rates()
        if funding:
            st.markdown(
                '<div style="display:grid;grid-template-columns:55px 75px 80px 100px;gap:6px;'
                'padding:4px 8px;border-bottom:1px solid #FF6600;font-family:monospace;'
                'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                '<span>COIN</span><span>RATE 8H</span><span>RATE ANN</span><span>SIGNAL</span></div>',
                unsafe_allow_html=True)
            for f in funding:
                rate = f["rate_pct"]
                if rate > 0.05: sig, sig_c = "OVER-LONG", "#FF4444"
                elif rate > 0.01: sig, sig_c = "LONG SKEW", "#FF8C00"
                elif rate < -0.05: sig, sig_c = "OVER-SHORT", "#00CC44"
                elif rate < -0.01: sig, sig_c = "SHORT SKEW", "#4488FF"
                else: sig, sig_c = "NEUTRAL", "#666"
                rc = "#00CC44" if rate < 0 else "#FF4444" if rate > 0.03 else "#FF8C00"
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:55px 75px 80px 100px;gap:6px;'
                    f'padding:5px 8px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:12px">'
                    f'<span style="color:#FF6600;font-weight:700">{f["symbol"]}</span>'
                    f'<span style="color:{rc};font-weight:600">{rate:+.4f}%</span>'
                    f'<span style="color:#888">{f["rate_ann"]:+.1f}%</span>'
                    f'<span style="color:{sig_c};font-weight:700;font-size:10px">{sig}</span></div>',
                    unsafe_allow_html=True)

            avg_rate = sum(f["rate_pct"] for f in funding) / len(funding) if funding else 0
            if avg_rate > 0.03: agg_sig, agg_c, agg_bg = "⚠️ MARKET OVER-LEVERAGED LONG", "#FF4444", "#1A0000"
            elif avg_rate > 0.005: agg_sig, agg_c, agg_bg = "📊 MILD LONG BIAS", "#FF8C00", "#0A0500"
            elif avg_rate < -0.03: agg_sig, agg_c, agg_bg = "⚠️ MARKET OVER-LEVERAGED SHORT", "#00CC44", "#001A00"
            elif avg_rate < -0.005: agg_sig, agg_c, agg_bg = "📊 MILD SHORT BIAS", "#4488FF", "#000A1A"
            else: agg_sig, agg_c, agg_bg = "✅ NEUTRAL — NO EXTREME POSITIONING", "#888", "#0A0A0A"
            st.markdown(
                f'<div style="background:{agg_bg};border:1px solid {agg_c};border-left:4px solid {agg_c};'
                f'padding:10px 14px;margin:10px 0;font-family:monospace;font-size:12px;color:{agg_c};font-weight:700">'
                f'{agg_sig}<br><span style="font-size:10px;font-weight:400;color:#888">Avg Funding: {avg_rate:+.4f}%</span></div>',
                unsafe_allow_html=True)

            total_liq = sum(liqs[c]["total"] for c in liqs) if liqs else 0
            btc_oi = next((o["oi_usd"] for o in oi_data if o["symbol"] == "BTC"), 0) if oi_data else 0

            risk_factors = 0
            if abs(avg_rate) > 0.03: risk_factors += 1
            if total_liq > 50_000_000: risk_factors += 1
            if btc_oi > 10_000_000_000: risk_factors += 1

            if risk_factors >= 2: risk_lvl, risk_c = "HIGH", "#FF4444"
            elif risk_factors == 1: risk_lvl, risk_c = "MEDIUM", "#FF8C00"
            else: risk_lvl, risk_c = "LOW", "#00CC44"

            st.markdown(
                f'<div style="background:#0A0A0A;border:1px solid {risk_c};border-left:4px solid {risk_c};'
                f'padding:14px 16px;margin:8px 0;font-family:monospace">'
                f'<div style="color:{risk_c};font-size:14px;font-weight:700;letter-spacing:1px;margin-bottom:8px">'
                f'🛡️ CRYPTO RISK LEVEL: {risk_lvl}</div>'
                f'<div style="font-size:11px;color:#888;line-height:1.8">'
                f'Funding: <span style="color:{"#FF4444" if abs(avg_rate)>0.03 else "#00CC44"}">{"ELEVATED" if abs(avg_rate)>0.03 else "NORMAL"}</span><br>'
                f'Liquidations: <span style="color:{"#FF4444" if total_liq>50e6 else "#00CC44"}">${total_liq/1e6:.1f}M {"(HIGH)" if total_liq>50e6 else "(NORMAL)"}</span><br>'
                f'BTC OI: <span style="color:{"#FF4444" if btc_oi>10e9 else "#00CC44"}">${btc_oi/1e9:.1f}B {"(CROWDED)" if btc_oi>10e9 else "(HEALTHY)"}</span>'
                f'</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Funding rate data unavailable.</p>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 5 — POLYMARKET
# ════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="bb-ph">🎲 POLYMARKET — PREDICTION INTELLIGENCE & UNUSUAL FLOW</div>', unsafe_allow_html=True)

    with st.spinner("Loading Polymarket…"):
        all_poly = polymarket_events(100)

    if not all_poly:
        st.markdown('<div style="background:#0A0500;border-left:4px solid #FF6600;padding:12px;font-family:monospace;font-size:12px;color:#FF8C00">⚠️ Could not reach Polymarket API. May be temporarily unavailable.</div>', unsafe_allow_html=True)
    else:
        def is_active(e):
            if e.get("closed", False) or e.get("resolved", False): return False
            end = e.get("endDate","") or ""
            if end:
                try:
                    from datetime import timezone
                    ed = datetime.fromisoformat(end.replace("Z","+00:00"))
                    if ed < datetime.now(timezone.utc): return False
                except: pass
            return True

        active_events = [e for e in all_poly if is_active(e)]
        active_events.sort(key=lambda e: _safe_float(e.get("volume",0)), reverse=True)
        top10 = active_events[:10]

        poly_search = st.text_input("🔍 SEARCH ALL ACTIVE EVENTS", placeholder="Fed rate, oil, Taiwan, BTC…", key="ps")
        if poly_search:
            top10 = [e for e in active_events if poly_search.lower() in str(e.get("title","")).lower()][:10]

        def _event_lead_prob(evt):
            markets = evt.get("markets", [])
            if not markets: return 50.0
            best = 0.0
            for mk in markets:
                pp = _parse_poly_field(mk.get("outcomePrices", []))
                p = _safe_float(pp[0]) if pp else 0.0
                if p > best: best = p
            return max(0.0, min(100.0, best * 100))

        st.markdown('<div class="bb-ph" style="margin-top:10px">📊 EVENT INTELLIGENCE DASHBOARD</div>', unsafe_allow_html=True)

        if top10:
            def make_poly_label(e, max_len=35):
                q = e.get("title", e.get("question",""))
                url = poly_url(e)
                short = q[:max_len]+"…" if len(q)>max_len else q
                return short, url

            labels_with_url = [make_poly_label(e) for e in top10]
            labels = [l for l,u in labels_with_url]
            urls   = [u for l,u in labels_with_url]

            vols   = [_safe_float(e.get("volume",0))/1e6 for e in top10]
            colors = ["#FF6600" if i==0 else "#AA3300" if i<3 else "#662200" for i in range(len(top10))]
            fig_vol = dark_fig(320)
            fig_vol.add_trace(go.Bar(
                x=vols, y=labels, orientation="h",
                marker=dict(color=colors, line=dict(width=0)),
                text=[f"${v:,.1f}M" for v in vols], textposition="outside",
                textfont=dict(size=10, color="#FF8C00"),
                customdata=urls,
            ))
            fig_vol.update_layout(
                margin=dict(l=10,r=80,t=32,b=0), height=320,
                title=dict(text="TOTAL VOLUME ($M)", font=dict(size=11,color="#FF6600"), x=0),
                xaxis=dict(showgrid=False, color="#444"),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9,color="#CCC"))
            )
            st.plotly_chart(fig_vol, width="stretch")

            with st.expander("🔗 CLICK TO OPEN EVENTS", expanded=False):
                for e in top10:
                    q = e.get("title", e.get("question",""))[:70]
                    url = poly_url(e)
                    p = _event_lead_prob(e)
                    c = "#00CC44" if p>=50 else "#FF4444"
                    st.markdown(f'<div style="padding:3px 0;font-family:monospace;font-size:11px"><a href="{url}" target="_blank" style="color:#FF6600">↗ {_esc(q)}</a> <span style="color:{c};font-weight:700">{p:.0f}%</span></div>', unsafe_allow_html=True)

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

            y_probs = [_event_lead_prob(e) for e in top10]
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
                title=dict(text="LEADING OUTCOME PROBABILITY (%)", font=dict(size=11,color="#FF6600"), x=0),
                xaxis=dict(range=[0,115], showgrid=False, color="#444"),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9,color="#CCC"))
            )
            st.plotly_chart(fig_prob, width="stretch")

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        poly_col, guide_col = st.columns([3,1])
        with poly_col:
            st.markdown(f'<div class="bb-ph">📋 TOP 10 ACTIVE EVENTS ({len(active_events)} active total)</div>', unsafe_allow_html=True)
            for e in top10:
                st.markdown(render_poly_card(e), unsafe_allow_html=True)

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
# TAB 6 — GEO GLOBE
# ════════════════════════════════════════════════════════════════════
with tabs[6]:
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
                st.markdown('<div style="background:#0D0D0D;border-left:3px solid #FF6600;padding:10px 12px;font-family:monospace;font-size:11px;color:#888">No articles found in GDELT for this query in the last 48h.</div>', unsafe_allow_html=True)

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
        st.markdown('<div class="bb-ph">📊 COMMODITY & CURRENCY IMPACT RADAR</div>', unsafe_allow_html=True)
        impact_tickers = {"WTI Crude": "CL=F", "Brent Crude": "BZ=F", "Natural Gas": "NG=F",
                          "Gold": "GC=F", "Silver": "SI=F", "Wheat": "ZW=F",
                          "USD Index": "DX-Y.NYB", "EUR/USD": "EURUSD=X", "10Y Yield": "^TNX"}
        impact_qs = multi_quotes(list(impact_tickers.values()))
        for q in impact_qs:
            name = [k for k,v in impact_tickers.items() if v == q['ticker']]
            name = name[0] if name else q['ticker']
            c = pct_color(q['pct'])
            arr = "▲" if q['pct'] >= 0 else "▼"
            st.markdown(f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #111;font-family:monospace;font-size:12px">'
                        f'<span style="color:#CCC">{name}</span>'
                        f'<span style="color:{c};font-weight:700">{arr} {q["pct"]:+.2f}% &nbsp; {fmt_p(q["price"])}</span></div>', unsafe_allow_html=True)

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">📖 CONFIDENCE LEVELS</div>', unsafe_allow_html=True)
        for lbl, c, desc in [("HIGH","#00CC44","Multiple verified sources"),("MEDIUM","#FF8C00","Single source / partial confirm"),("LOW","#FFCC00","Unverified rumor"),("UNCONFIRMED","#555","Raw signal only")]:
            st.markdown(f'<div style="font-family:monospace;font-size:10px;padding:3px 0"><span style="color:{c};font-weight:700">{lbl}</span> <span style="color:#444">— {desc}</span></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 7 — EARNINGS TRACKER
# ════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.markdown('<div class="bb-ph">📅 EARNINGS TRACKER — UPCOMING & RECENT</div>', unsafe_allow_html=True)

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
            with st.spinner("Detecting exchange…"):
                tv_sym_earn = get_ticker_exchange(et)
            components.html(tv_chart(tv_sym_earn,320), height=325, scrolling=False)
            try:
                with st.spinner("Loading financials…"):
                    fin_data = get_full_financials(et)
                if fin_data:
                    st.markdown('<div class="bb-ph" style="margin-top:10px">📊 QUARTERLY FINANCIALS</div>', unsafe_allow_html=True)

                    # Header row
                    quarters_sorted = sorted(fin_data.keys(), reverse=True)
                    hdr_str = "".join(f'<span style="color:#FF6600;font-weight:700">{q}</span>' for q in quarters_sorted)
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:130px repeat({len(quarters_sorted)},1fr);'
                        f'gap:6px;padding:5px 8px;border-bottom:1px solid #FF6600;font-family:monospace;font-size:10px;color:#FF6600;letter-spacing:1px">'
                        f'<span>METRIC</span>{hdr_str}</div>', unsafe_allow_html=True)

                    def _fmt_val(v, unit="M", decimals=1):
                        if v is None: return '<span style="color:#444">—</span>'
                        if unit == "B": v_disp = v / 1e9; suffix = "B"
                        elif unit == "M": v_disp = v / 1e6; suffix = "M"
                        elif unit == "%": return f'<span style="color:#CCC">{v:.1f}%</span>'
                        else: return f'<span style="color:#CCC">{v:.2f}</span>'
                        color = "#00CC44" if v >= 0 else "#FF4444"
                        return f'<span style="color:{color};font-weight:600">{v_disp:,.{decimals}f}{suffix}</span>'

                    METRICS = [
                        ("Revenue",      "revenue",       "B"),
                        ("Gross Profit", "gross_profit",  "B"),
                        ("Op. Income",   "op_income",     "B"),
                        ("Net Income",   "net_income",    "B"),
                        ("EBITDA",       "ebitda",        "B"),
                        ("Free CF",      "free_cashflow", "B"),
                        ("Op. CF",       "op_cashflow",   "B"),
                        ("Gross Margin", "gross_margin",  "%"),
                        ("Op. Margin",   "op_margin",     "%"),
                        ("Net Margin",   "net_margin",    "%"),
                        ("Total Debt",   "total_debt",    "B"),
                        ("Cash",         "cash",          "B"),
                        ("EPS (Dil.)",   "eps",           "raw"),
                    ]

                    for label, key, unit in METRICS:
                        cells = "".join(
                            f'<span style="text-align:right">{_fmt_val(fin_data.get(q, {}).get(key), unit)}</span>'
                            for q in quarters_sorted
                        )
                        row_bg = "background:#050505;" if METRICS.index((label, key, unit)) % 2 == 0 else ""
                        st.markdown(
                            f'<div style="display:grid;grid-template-columns:130px repeat({len(quarters_sorted)},1fr);'
                            f'gap:6px;padding:5px 8px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px;{row_bg}">'
                            f'<span style="color:#888">{label}</span>{cells}</div>', unsafe_allow_html=True)
            except Exception:
                pass

            # ── Stock-specific news ──
            st.markdown('<div class="bb-ph" style="margin-top:10px">📰 NEWS — {}</div>'.format(et), unsafe_allow_html=True)
            with st.spinner("Loading stock news…"):
                stock_news = get_stock_news(
                    et,
                    finnhub_key=st.session_state.get("finnhub_key"),
                    newsapi_key=st.session_state.get("newsapi_key"),
                )
            if stock_news:
                for art in stock_news:
                    st.markdown(render_news_card(art["title"], art["url"], art["source"], art["date"], "bb-news"), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No recent news found. Add Finnhub or NewsAPI key for richer coverage.</p>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 8 — SENTINEL AI
# ════════════════════════════════════════════════════════════════════
with tabs[8]:
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
