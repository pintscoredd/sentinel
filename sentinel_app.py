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
    yahoo_quote, vix_price, vix_with_percentile, options_chain, options_expiries, sector_etfs, top_movers,
    detect_unusual_poly, market_snapshot_str, _parse_poly_field,
    score_options_chain, score_poly_mispricing,
    get_earnings_calendar, is_market_open,
    get_macro_overview, get_macro_calendar, get_ticker_exchange,
    get_full_financials, get_stock_news, get_earnings_matrix,
    is_0dte_market_open, get_stock_snapshot, get_spx_metrics,
    fetch_0dte_chain, compute_gex_profile, compute_max_pain, compute_pcr,
    find_gamma_flip, fetch_vix_data, find_target_strike, compute_spx_direction,
    parse_trade_input, generate_recommendation,
    fetch_cboe_gex, compute_cboe_gex_profile, compute_cboe_total_gex, compute_cboe_pcr,
    get_whale_trades, get_exchange_netflow, get_funding_rates,
    get_open_interest, get_liquidations,
    build_brief_context,
    fetch_btc_etf_flows, fetch_btc_etf_flows_fallback, _ETF_TICKERS,
    stat_arb_screener, get_finra_short_volume, bs_greeks_engine,
    # ─── New Feature Imports ───
    get_global_indices, get_net_liquidity, get_yield_curve_history,
    get_cross_asset_volatility, get_macro_correlation_matrix,
    get_sector_rrg, get_iv_term_structure, get_gamma_squeeze_scanner,
    get_finnhub_earnings_calendar, get_expected_move,
    get_ai_earnings_summary, get_margin_chart_data,
    # ─── FEAT additions ───
    get_iv_skew, get_rv_iv_spread, get_cot_positioning, get_economic_surprise_index,
)
from ui_components import (
    CHART_LAYOUT, dark_fig, tv_chart, tv_mini, tv_tape,
    yield_curve_chart, yield_history_chart, cpi_vs_rates_chart,
    render_news_card, render_wl_row, render_options_table,
    render_scored_options, render_unusual_trade,
    render_insider_cards, poly_url, poly_status, unusual_side,
    render_poly_card, render_crypto_etf_chart,
    SENTINEL_PROMPT, GEMINI_MODELS, list_gemini_models, gemini_response, format_gemini_msg,
    render_0dte_gex_chart, render_0dte_gex_decoder, render_0dte_recommendation, render_0dte_trade_log,
    render_geo_tab, render_stat_arb_cards,
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
display: flex; align-items: center; gap: 6px;
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

/* WEI ROW */
.wei-row {
display: grid; grid-template-columns: 35px 2fr 1.5fr 1.5fr 1fr 1fr 1fr;
gap: 6px; padding: 5px 10px; border-bottom: 1px solid var(--bg3);
font-family: var(--mono); font-size: 14px; align-items: center; width:100%;
}
.wei-row:hover { background: var(--bg2); }

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

/* EARNINGS MATRIX */
.em-container { background: #080808; border: 1px solid #1A1A1A; border-radius: 4px; padding: 14px; margin: 10px 0; }
.em-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.em-badge { background: #1A3A1A; color: #00CC44; padding: 2px 8px; border-radius: 3px; font-size: 9px; font-weight: 700; letter-spacing: 1px; font-family: var(--mono); }
.em-ticker-label { color: var(--org); font-weight: 700; font-size: 14px; font-family: var(--mono); }
.em-metric-label { color: #888; font-size: 10px; font-family: var(--mono); letter-spacing: 1px; }
.em-table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 11px; }
.em-table th { color: var(--org); font-size: 9px; letter-spacing: 1px; padding: 4px 8px; text-align: right; border-bottom: 1px solid var(--org); font-weight: 700; }
.em-table th:first-child { text-align: left; }
.em-table td { padding: 5px 8px; text-align: right; border-bottom: 1px solid #0D0D0D; color: #CCC; }
.em-table td:first-child { text-align: left; color: #888; font-size: 10px; }
.em-table tr:hover { background: #0A0A0A; }
.em-table .em-annual td { border-top: 1px solid #333; font-weight: 700; }
.em-positive { color: #00CC44 !important; }
.em-negative { color: #FF4444 !important; }
.em-neutral { color: #888 !important; }
.em-estimate { color: #666 !important; font-style: italic; }
.em-growth-toggle { display: flex; gap: 0; margin-bottom: 10px; }
.em-growth-btn { background: #111; color: #888; border: 1px solid #222; padding: 5px 14px; font-family: var(--mono); font-size: 10px; font-weight: 700; cursor: pointer; letter-spacing: 1px; transition: all 0.15s; }
.em-growth-btn:first-child { border-radius: 3px 0 0 3px; }
.em-growth-btn:last-child { border-radius: 0 3px 3px 0; }
.em-growth-btn.active { background: #1A3A1A; color: #00CC44; border-color: #00CC44; }
.em-val-table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 11px; margin-top: 8px; }
.em-val-table th { color: var(--org); font-size: 9px; letter-spacing: 1px; padding: 4px 6px; text-align: right; border-bottom: 1px solid var(--org); }
.em-val-table th:first-child { text-align: left; }
.em-val-table td { padding: 5px 6px; text-align: right; border-bottom: 1px solid #0D0D0D; color: #CCC; font-weight: 600; }
.em-val-table td:first-child { text-align: left; color: #888; }
.em-val-table tr:hover { background: #0A0A0A; }
.em-chart-tabs { display: flex; gap: 0; margin-bottom: 10px; }
.em-chart-tab { background: #111; color: #888; border: 1px solid #222; padding: 5px 14px; font-family: var(--mono); font-size: 10px; font-weight: 700; letter-spacing: 1px; }
.em-chart-tab:first-child { border-radius: 3px 0 0 3px; }
.em-chart-tab:last-child { border-radius: 0 3px 3px 0; }
.em-chart-tab.active { background: var(--bg2); color: var(--wht); border-color: #444; }
.em-legend { display: flex; gap: 16px; align-items: center; font-family: var(--mono); font-size: 9px; color: #888; margin-bottom: 6px; }
.em-legend-dot { width: 10px; height: 10px; display: inline-block; border-radius: 2px; margin-right: 4px; vertical-align: middle; }

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
    """Try st.secrets with exact name, then lowercase, then uppercase."""
    for k in [name, name.lower(), name.upper()]:
        try:
            val = st.secrets.get(k, None)
            if val:
                return str(val).strip()
        except Exception:
            pass
    # Also try nested [api_keys] section some users set up
    try:
        val = st.secrets.get("api_keys", {}).get(name, None)
        if val:
            return str(val).strip()
    except Exception:
        pass
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
    "cftc_key": _get_secret("CFTC_API_KEY"),
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

    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700">API STATUS</div>', unsafe_allow_html=True)

    _alpaca_ok = bool(_get_secret("ALPACA_API_KEY")) and bool(_get_secret("ALPACA_SECRET_KEY"))
    _keys_status = [
        ("Yahoo Finance", True, "always on"),
        ("Polymarket",    True, "always on"),
        ("GDELT",         True, "always on"),
        ("CFTC COT",      True, "always on (free CSV)"),
        ("Alpaca (0DTE)", _alpaca_ok, "ALPACA_API_KEY"),
        ("FRED",          bool(st.session_state.fred_key), "FRED_API_KEY"),
        ("Finnhub",       bool(st.session_state.finnhub_key), "FINNHUB_API_KEY"),
        ("NewsAPI",       bool(st.session_state.newsapi_key), "NEWSAPI_KEY"),
        ("Gemini AI",     bool(st.session_state.gemini_key), "GEMINI_API_KEY"),
        ("AISstream",     bool(_get_secret("AISSTREAM_API_KEY")), "AISSTREAM_API_KEY"),
        ("Marinesia",     bool(_get_secret("MARINESIA_API_KEY")), "MARINESIA_API_KEY"),
    ]
    for api, ok, secret_name in _keys_status:
        dot = "🟢" if ok else "🔴"
        c = "#CCCCCC" if ok else "#555"
        hint = "" if ok else f' <span style="color:#333;font-size:8px">[{secret_name}]</span>'
        st.markdown(f'<div style="font-family:monospace;font-size:10px;padding:1px 0">{dot} <span style="color:{c}">{api}</span>{hint}</div>', unsafe_allow_html=True)

    st.markdown('<hr style="border-top:1px solid #222;margin:8px 0">', unsafe_allow_html=True)
    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700">API KEY OVERRIDES</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#444;font-size:8px;font-family:monospace;margin-bottom:6px">Leave blank to use secrets.toml value</div>', unsafe_allow_html=True)

    _fred_input = st.text_input("FRED API Key", value="", type="password", placeholder="paste key to override…", key="fred_override")
    if _fred_input:
        st.session_state.fred_key = _fred_input.strip()
    _finnhub_input = st.text_input("Finnhub Key", value="", type="password", placeholder="paste key to override…", key="finnhub_override")
    if _finnhub_input:
        st.session_state.finnhub_key = _finnhub_input.strip()
    _cftc_input = st.text_input("CFTC API Key", value="", type="password", placeholder="optional — CSV is free", key="cftc_override")
    if _cftc_input:
        st.session_state.cftc_key = _cftc_input.strip()

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

    @st.fragment(run_every="30s")
    def render_morning_brief_header():
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
        if qs:
            cols = st.columns(len(qs))
            for col, q in zip(cols, qs):
                chg_str = f"{q['pct']:+.2f}% ({q['change']:+.2f})"
                with col: st.metric(KEY_T.get(q["ticker"],q["ticker"]), fmt_p(q["price"]), delta=chg_str)
        else:
            st.markdown('<div style="color:#FF4444;font-size:11px;font-family:monospace">Quotes unavailable. Rate limits or network error.</div>', unsafe_allow_html=True)
            
    render_morning_brief_header()

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
            vix_val, vix_pct, posture = vix_with_percentile()
            if vix_val:
                pc = {"RISK-ON": "#00CC44", "NEUTRAL": "#FF8C00", "RISK-OFF": "#FF4444"}[posture]
                st.markdown(
                    f'<div class="fg-gauge">'
                    f'<div style="color:#888;font-size:9px">POSTURE</div>'
                    f'<div class="fg-num" style="color:{pc};font-size:24px">{posture}</div>'
                    f'<div style="color:#555;font-size:9px">VIX {vix_val:.1f} — {vix_pct:.0f}th pctile</div>'
                    f'</div>', unsafe_allow_html=True)

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
            # Filter: only show markets closed within the last 2 months
            _cutoff = datetime.now(pytz.utc) - timedelta(days=60)
            _recent_closed = []
            for e in closed_poly:
                end = e.get("endDate","") or e.get("resolvedAt","") or ""
                if end:
                    try:
                        ed = datetime.fromisoformat(end.replace("Z","+00:00"))
                        if ed >= _cutoff:
                            _recent_closed.append(e)
                    except Exception:
                        pass
            for e in active_poly[:5]:
                st.markdown(render_poly_card(e), unsafe_allow_html=True)
            if _recent_closed:
                st.markdown('<div style="color:#FF6600;font-size:10px;letter-spacing:1px;margin:8px 0 4px">RECENTLY CLOSED</div>', unsafe_allow_html=True)
                for e in _recent_closed[:3]:
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
            if not expiries:
                options_expiries.clear(tkr)
            else:
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

                scored = score_options_chain(calls, puts, q["price"], vix=current_vix, expiry_date=selected_exp)

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
                
                with st.expander("🔧 TRUE BLACK-SCHOLES ENGINE (WHAT-IF)", expanded=False):
                    from scipy.stats import norm
                    import math
                    st.markdown('<div style="color:#888;font-size:10px;margin-bottom:8px">Calculate Delta, Gamma, Theta locally bypassing Alpaca endpoint limits.</div>', unsafe_allow_html=True)
                    wc1, wc2, wc3, wc4, wc5 = st.columns(5)
                    with wc1: bs_s = st.number_input("Spot Price", value=float(q["price"]), format="%.2f", key=f"bs_s_{tkr}")
                    with wc2: bs_k = st.number_input("Strike", value=float(q["price"]), format="%.2f", key=f"bs_k_{tkr}")
                    with wc3:
                        dt_exp = max((exp_dt.date() - datetime.today().date()).days, 1) if 'exp_dt' in locals() else 14
                        bs_t = st.number_input("Days to Expire", value=float(dt_exp), format="%.1f", key=f"bs_t_{tkr}")
                    with wc4:
                        bs_v = st.number_input("Implied Vol (%)", value=float(current_vix) if current_vix else 20.0, format="%.1f", key=f"bs_v_{tkr}")
                    with wc5: bs_side = st.selectbox("Type", ["call", "put"], key=f"bs_side_{tkr}")
                    
                    bs_res = bs_greeks_engine(bs_s, bs_k, bs_t / 365.0, 0.045, bs_v / 100.0, bs_side)
                    rc1, rc2, rc3, rc4, rc5 = st.columns(5)
                    rc1.metric("Delta", f"{bs_res['delta']:.4f}")
                    rc2.metric("Gamma", f"{bs_res['gamma']:.6f}")
                    rc3.metric("Theta (Daily)", f"{bs_res['theta']:.4f}")
                    rc4.metric("Vega (1%)", f"{bs_res.get('vega', 0):.4f}")
                    rc5.metric("Rho (1%)", f"{bs_res.get('rho', 0):.4f}")

                with st.expander("📊 **FULL OPTIONS CHAIN**", expanded=False):
                    fc, fp = st.columns(2)
                    with fc:
                        st.markdown('<div style="color:#00CC44;font-size:9px;font-weight:700;letter-spacing:2px">▲ ALL CALLS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(calls, "calls", q["price"]), unsafe_allow_html=True)
                    with fp:
                        st.markdown('<div style="color:#FF4444;font-size:9px;font-weight:700;letter-spacing:2px">▼ ALL PUTS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(puts, "puts", q["price"]), unsafe_allow_html=True)
            else:
                options_chain.clear(tkr, selected_exp)
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

            st.markdown('<div class="bb-ph" style="margin-top:12px">📉 SHORT VOLUME & DARK POOL PROXY (FINRA/YF)</div>', unsafe_allow_html=True)
            finra = get_finra_short_volume(tkr)
            if finra:
                c1, c2, c3 = st.columns(3)
                c1.metric("Short % of Float", f"{finra['short_pct_float']}%")
                c2.metric("Short Shares", f"{finra['short_shares']:,}")
                c3.metric("Days to Cover", f"{finra['days_to_cover']}")
            else:
                st.markdown('<div style="color:#555;font-size:11px">Short volume data unavailable for this ticker.</div>', unsafe_allow_html=True)
        else:
            st.error(f"No data for '{tkr}'. Check ticker symbol.")

    # ════════════════════════════════════════════════════════════════════
    # GLOBAL WEI MONITOR — above Futures
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-ph">🌍 GLOBAL EQUITY INDICES — WORLD MARKET MONITOR</div>', unsafe_allow_html=True)

    with st.spinner("Loading global indices…"):
        _wei_df = get_global_indices()

    if not _wei_df.empty:
        for _region in ["Americas", "EMEA", "APAC"]:
            _region_df = _wei_df[_wei_df["Region"] == _region]
            if _region_df.empty:
                continue
            st.markdown(
                f'<div class="wei-row" style="color:#FF6600;font-size:9px;letter-spacing:2px;'
                f'border-bottom:1px solid #333;padding:4px 0;margin-top:6px">'
                f'<span>{_region.upper()}</span>'
                f'<span>INDEX</span><span>LAST</span><span>CHG</span><span>%</span>'
                f'<span>10D σ</span><span>30D σ</span>'
                f'</div>',
                unsafe_allow_html=True)
            for _, row in _region_df.iterrows():
                _pct_val = float(row["% Chg"].replace("%","")) if isinstance(row["% Chg"], str) else row["% Chg"]
                _c = "#00CC44" if _pct_val >= 0 else "#FF4444"
                _arr = "▲" if _pct_val >= 0 else "▼"
                st.markdown(
                    f'<div class="wei-row">'
                    f'<span style="font-size:20px">{row["Flag"]}</span>'
                    f'<span style="color:#FFF;font-size:14px;font-weight:700">{row["Index"]}</span>'
                    f'<span style="color:{_c};font-weight:600">{row["Value"]:.3f}</span>'
                    f'<span style="color:{_c}">{row["Change"]:.3f}</span>'
                    f'<span style="color:{_c};font-weight:700">{_arr} {_pct_val:.3f}%</span>'
                    f'<span style="color:#888">{row["10D Vol"]:.3f}</span>'
                    f'<span style="color:#888">{row["30D Vol"]:.3f}</span>'
                    f'</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Global index data loading…</p>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    @st.fragment(run_every="30s")
    def render_futures_live():
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
                    f'<span style="color:{c}">{chr(43)+str(f["change"]) if f["change"]>=0 else str(f["change"])}</span>'
                    f'<span style="color:{sig_c};font-size:10px;font-weight:700">{sig_lbl}</span>'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Futures data loading…</p>', unsafe_allow_html=True)

    render_futures_live()

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTOR % CHANGE — above Top Movers
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="bb-ph">📊 SECTOR PERFORMANCE — % CHANGE</div>', unsafe_allow_html=True)
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

    # ════════════════════════════════════════════════════════════════════
    # SECTOR RELATIVE ROTATION GRAPH — under % change
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="bb-ph">🔄 SECTOR RELATIVE ROTATION GRAPH — RRG</div>', unsafe_allow_html=True)

    with st.spinner("Computing sector rotation…"):
        _rrg_data = get_sector_rrg()

    if _rrg_data:
        _rrg_colors = {
            "LEADING": "#00CC44", "WEAKENING": "#FFCC00",
            "LAGGING": "#FF4444", "IMPROVING": "#00AAFF"
        }
        fig_rrg = dark_fig(500)

        # Compute dynamic axis bounds from actual data for tighter zoom
        _rrg_ratios = [s["rs_ratio"] for s in _rrg_data]
        _rrg_moms   = [s["rs_momentum"] for s in _rrg_data]
        _x_pad = max(abs(r - 100) for r in _rrg_ratios) * 1.35 + 0.3
        _y_pad = max(abs(m - 100) for m in _rrg_moms) * 1.35 + 0.3
        _x_pad = max(_x_pad, 1.0)
        _y_pad = max(_y_pad, 1.0)
        _x0, _x1 = 100 - _x_pad, 100 + _x_pad
        _y0, _y1 = 100 - _y_pad, 100 + _y_pad

        # Quadrant background fills (clipped to data range)
        fig_rrg.add_shape(type="rect", x0=100, y0=100, x1=_x1, y1=_y1, fillcolor="rgba(0,204,68,0.06)",  line_width=0, layer="below")
        fig_rrg.add_shape(type="rect", x0=100, y0=_y0, x1=_x1, y1=100, fillcolor="rgba(255,204,0,0.06)", line_width=0, layer="below")
        fig_rrg.add_shape(type="rect", x0=_x0, y0=_y0, x1=100, y1=100, fillcolor="rgba(255,68,68,0.06)",  line_width=0, layer="below")
        fig_rrg.add_shape(type="rect", x0=_x0, y0=100, x1=100, y1=_y1, fillcolor="rgba(0,170,255,0.06)", line_width=0, layer="below")

        # Crosshairs
        fig_rrg.add_hline(y=100, line_dash="dot", line_color="#2A2A2A", line_width=1)
        fig_rrg.add_vline(x=100, line_dash="dot", line_color="#2A2A2A", line_width=1)

        for sector in _rrg_data:
            color = _rrg_colors.get(sector["quadrant"], "#888")
            fig_rrg.add_trace(go.Scatter(
                x=[sector["rs_ratio"]], y=[sector["rs_momentum"]],
                mode="markers+text",
                marker=dict(size=14, color=color, line=dict(width=1.5, color="#000")),
                text=[sector["sector"]],
                textposition="top center",
                textfont=dict(size=10, color=color, family="IBM Plex Mono"),
                name=sector["sector"],
                hovertext=(
                    f"{sector['sector']}<br>"
                    f"RS-Ratio: {sector['rs_ratio']:.2f}<br>"
                    f"RS-Mom: {sector['rs_momentum']:.2f}<br>"
                    f"{sector['quadrant']}"
                ),
                hoverinfo="text",
                showlegend=False,
            ))

        # Quadrant corner labels (placed near the edges of the data range)
        _ql_x_r = _x0 + (_x1 - _x0) * 0.78
        _ql_x_l = _x0 + (_x1 - _x0) * 0.22
        _ql_y_t = _y0 + (_y1 - _y0) * 0.88
        _ql_y_b = _y0 + (_y1 - _y0) * 0.12
        for label, x, y, color in [
            ("LEADING",   _ql_x_r, _ql_y_t, "#00CC44"),
            ("WEAKENING", _ql_x_r, _ql_y_b, "#FFCC00"),
            ("LAGGING",   _ql_x_l, _ql_y_b, "#FF4444"),
            ("IMPROVING", _ql_x_l, _ql_y_t, "#00AAFF"),
        ]:
            fig_rrg.add_annotation(
                x=x, y=y, text=label, showarrow=False,
                font=dict(size=9, color=color, family="IBM Plex Mono"),
                opacity=0.5,
            )

        fig_rrg.update_layout(
            margin=dict(l=50, r=30, t=40, b=50), height=500,
            title=dict(
                text="RS-RATIO vs RS-MOMENTUM  —  🟢 Leading · 🟡 Weakening · 🔴 Lagging · 🔵 Improving",
                font=dict(size=10, color="#FF6600"), x=0,
            ),
            xaxis=dict(
                title="RS-Ratio (Strength vs SPY)",
                range=[_x0, _x1],
                color="#555", gridcolor="#111",
                tickfont=dict(size=9), zeroline=False,
            ),
            yaxis=dict(
                title="RS-Momentum",
                range=[_y0, _y1],
                color="#555", gridcolor="#111",
                tickfont=dict(size=9), zeroline=False,
            ),
        )
        st.plotly_chart(fig_rrg, use_container_width=True)
    else:
        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Sector RRG data loading…</p>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # TOP MOVERS — Gainers / Losers
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="bb-ph">🏆 TOP MOVERS — S&P 500 UNIVERSE</div>', unsafe_allow_html=True)
    with st.spinner("Scanning S&P 500 for top movers…"):
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

    # ════════════════════════════════════════════════════════════════════
    # STATISTICAL ARBITRAGE
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="bb-ph">⚖️ STATISTICAL ARBITRAGE (Cointegration Screener)</div>', unsafe_allow_html=True)
    with st.spinner("Running Engle-Granger tests..."):
        arb_df = stat_arb_screener()
    if arb_df:
        st.markdown(render_stat_arb_cards(arb_df), unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#555;font-size:11px">Stat Arb data unavailable (statsmodels missing or fetch failed).</div>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # IV TERM STRUCTURE + GAMMA SQUEEZE — under Stat Arb
    # ════════════════════════════════════════════════════════════════════
    _iv_left, _iv_right = st.columns([3, 2])
    with _iv_left:
        st.markdown('<div class="bb-ph">📐 IV TERM STRUCTURE — ATM IMPLIED VOLATILITY</div>', unsafe_allow_html=True)
        _iv_ticker = st.text_input("IV Ticker", value="SPY", key="iv_ts_tkr", placeholder="SPY, QQQ, AAPL…")
        with st.spinner("Loading IV term structure…"):
            _iv_data = get_iv_term_structure(_iv_ticker.upper().strip())

        if _iv_data:
            _iv_dtes   = [d["dte"]    for d in _iv_data]
            _iv_vals   = [d["atm_iv"] for d in _iv_data]
            _iv_labels = [d["expiry"] for d in _iv_data]

            fig_iv = dark_fig(300)
            fig_iv.add_trace(go.Scatter(
                x=_iv_dtes, y=_iv_vals, mode="lines+markers+text",
                line=dict(color="#FF6600", width=2),
                marker=dict(size=8, color="#FF6600", line=dict(width=1, color="#000")),
                text=[f"{v:.1f}%" for v in _iv_vals],
                textposition="top center", textfont=dict(size=8, color="#FF8C00"),
                hovertext=[f"Expiry: {l}<br>DTE: {d}<br>ATM IV: {v:.2f}%" for l, d, v in zip(_iv_labels, _iv_dtes, _iv_vals)],
                hoverinfo="text",
            ))
            fig_iv.update_layout(
                margin=dict(l=40, r=10, t=30, b=40), height=300,
                title=dict(text=f"{_iv_ticker.upper()} IV TERM STRUCTURE", font=dict(size=10, color="#FF6600"), x=0),
                xaxis=dict(title="DTE", color="#555", gridcolor="#111", tickfont=dict(size=9)),
                yaxis=dict(title="ATM IV %", color="#555", gridcolor="#111", tickfont=dict(size=9), ticksuffix="%"),
            )
            st.plotly_chart(fig_iv, use_container_width=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">IV data unavailable.</p>', unsafe_allow_html=True)

    with _iv_right:
        st.markdown('<div class="bb-ph">🔫 GAMMA SQUEEZE SCANNER</div>', unsafe_allow_html=True)
        with st.spinner("Scanning for squeeze candidates…"):
            _squeeze_data = get_gamma_squeeze_scanner()

        if _squeeze_data:
            st.markdown(
                '<div style="display:grid;grid-template-columns:55px 65px 60px 55px 55px 55px 90px;gap:4px;'
                'padding:4px 8px;border-bottom:1px solid #FF6600;font-family:monospace;'
                'font-size:8px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                '<span>TICKER</span><span>PRICE</span><span>SI %</span><span>SI DAYS</span>'
                '<span>VOL ×</span><span>SCORE</span><span>SIGNAL</span></div>',
                unsafe_allow_html=True)

            for sq in _squeeze_data[:10]:
                _si_c = "#FF4444" if sq["short_pct"] > 15 else "#FF8C00" if sq["short_pct"] > 8 else "#888"
                _vr_c = "#FF4444" if sq["vol_ratio"] > 2.5 else "#FF8C00" if sq["vol_ratio"] > 1.5 else "#888"
                _sc_c = "#FF4444" if sq["squeeze_score"] >= 5 else "#FF8C00" if sq["squeeze_score"] >= 3 else "#888"
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:55px 65px 60px 55px 55px 55px 90px;gap:4px;'
                    f'padding:4px 8px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px">'
                    f'<span style="color:#FF6600;font-weight:700">{sq["ticker"]}</span>'
                    f'<span style="color:#CCC">${sq["price"]:,.2f}</span>'
                    f'<span style="color:{_si_c};font-weight:600">{sq["short_pct"]:.1f}%</span>'
                    f'<span style="color:#888">{sq["short_ratio"]:.1f}</span>'
                    f'<span style="color:{_vr_c};font-weight:600">{sq["vol_ratio"]:.1f}×</span>'
                    f'<span style="color:{_sc_c};font-weight:700">{sq["squeeze_score"]:.1f}</span>'
                    f'<span style="color:{_sc_c};font-size:9px">{sq["signal"]}</span></div>',
                    unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No squeeze candidates found.</p>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # FEAT-03: RV vs IV Spread — Vol Premium Signal
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Computing RV/IV spread…"):
        _rv_iv = get_rv_iv_spread(_iv_ticker.upper().strip() if '_iv_ticker' in dir() else "SPY")
    if _rv_iv:
        _rv_c1, _rv_c2, _rv_c3, _rv_c4 = st.columns(4)
        with _rv_c1:
            st.markdown(
                f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:3px solid #FF8C00;'
                f'padding:10px;font-family:monospace;text-align:center">'
                f'<div style="color:#555;font-size:8px;letter-spacing:1px">RV20 (REALIZED)</div>'
                f'<div style="color:#FFF;font-size:16px;font-weight:700">{_rv_iv["rv20"]:.1f}%</div></div>',
                unsafe_allow_html=True)
        with _rv_c2:
            st.markdown(
                f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:3px solid #FF8C00;'
                f'padding:10px;font-family:monospace;text-align:center">'
                f'<div style="color:#555;font-size:8px;letter-spacing:1px">FRONT IV ({_rv_iv["dte"]}D)</div>'
                f'<div style="color:#FFF;font-size:16px;font-weight:700">{_rv_iv["front_iv"]:.1f}%</div></div>',
                unsafe_allow_html=True)
        with _rv_c3:
            st.markdown(
                f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:3px solid #FF8C00;'
                f'padding:10px;font-family:monospace;text-align:center">'
                f'<div style="color:#555;font-size:8px;letter-spacing:1px">RV - IV SPREAD</div>'
                f'<div style="color:{_rv_iv["signal_color"]};font-size:16px;font-weight:700">{_rv_iv["spread"]:+.1f}%</div></div>',
                unsafe_allow_html=True)
        with _rv_c4:
            st.markdown(
                f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:3px solid {_rv_iv["signal_color"]};'
                f'padding:10px;font-family:monospace;text-align:center">'
                f'<div style="color:#555;font-size:8px;letter-spacing:1px">VOL SIGNAL</div>'
                f'<div style="color:{_rv_iv["signal_color"]};font-size:16px;font-weight:900">{_rv_iv["signal"]}</div></div>',
                unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # FEAT-02: IV Skew Surface — 25-Delta Put/Call Skew
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Computing IV skew surface…"):
        _skew_data = get_iv_skew(_iv_ticker.upper().strip() if '_iv_ticker' in dir() else "SPY")
    if _skew_data:
        st.markdown('<div class="bb-ph">📈 25-DELTA IV SKEW SURFACE</div>', unsafe_allow_html=True)
        _sk_dtes = [d["dte"] for d in _skew_data]
        _sk_atm = [d["iv_atm"] for d in _skew_data]
        _sk_25c = [d.get("iv_25c") for d in _skew_data]
        _sk_25p = [d.get("iv_25p") for d in _skew_data]
        _sk_skew = [d["skew"] for d in _skew_data]

        fig_skew = dark_fig(280)
        fig_skew.add_trace(go.Scatter(x=_sk_dtes, y=_sk_atm, name="ATM IV",
            mode="lines+markers", line=dict(color="#FF8C00", width=2),
            marker=dict(size=6)))
        if any(v is not None for v in _sk_25c):
            fig_skew.add_trace(go.Scatter(x=_sk_dtes, y=_sk_25c, name="25Δ Call IV",
                mode="lines+markers", line=dict(color="#00CC44", width=1, dash="dash"),
                marker=dict(size=5)))
        if any(v is not None for v in _sk_25p):
            fig_skew.add_trace(go.Scatter(x=_sk_dtes, y=_sk_25p, name="25Δ Put IV",
                mode="lines+markers", line=dict(color="#FF4444", width=1, dash="dash"),
                marker=dict(size=5)))
        # Skew as bars on secondary y-axis
        _skew_colors = ["#FF4444" if s > 0 else "#00CC44" for s in _sk_skew]
        fig_skew.add_trace(go.Bar(x=_sk_dtes, y=_sk_skew, name="Skew (P-C)",
            marker_color=_skew_colors, opacity=0.4, yaxis="y2"))

        fig_skew.update_layout(
            margin=dict(l=40, r=60, t=30, b=40), height=280,
            title=dict(text=f"{_iv_ticker.upper()} IV SKEW (25Δ PUT - CALL)", font=dict(size=10, color="#FF6600"), x=0),
            xaxis=dict(title="DTE", color="#555", gridcolor="#111", tickfont=dict(size=9)),
            yaxis=dict(title="IV %", color="#555", gridcolor="#111", tickfont=dict(size=9), ticksuffix="%"),
            yaxis2=dict(title="Skew %", overlaying="y", side="right", color="#555",
                       tickfont=dict(size=9, color="#888"), showgrid=False),
            legend=dict(font=dict(size=8, color="#888"), bgcolor="rgba(0,0,0,0)",
                       orientation="h", x=0, y=1.08),
            barmode="overlay",
        )
        st.plotly_chart(fig_skew, use_container_width=True)

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
        @st.fragment(run_every="10s")
        def render_0dte_fragment():
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
                _now_pst_str = datetime.now(PST).strftime("%H:%M:%S PST")
                st.markdown(f'<div style="text-align:right;font-family:monospace;padding:6px 0;color:#555;font-size:10px">'
                            f'Last refresh: {_now_pst_str} | Auto-refresh: 30s cache</div>', unsafe_allow_html=True)

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
                                _log_time = datetime.now(PST).strftime("%I:%M %p PST")
                                st.session_state.trade_log_0dte.append(
                                    f"[{_log_time}] {_rec['recommendation'].replace('RECOMMENDATION: ', '')}")

            if st.session_state.trade_log_0dte:
                _log_entries = st.session_state.trade_log_0dte[-10:]
                st.markdown(render_0dte_trade_log(_log_entries), unsafe_allow_html=True)

            with st.expander("⚖️ KELLY CRITERION POSITION SIZING", expanded=False):
                st.markdown('<div style="color:#888;font-family:monospace;font-size:10px;margin-bottom:8px">Institutional risk management optimal sizing calculator.</div>', unsafe_allow_html=True)
                kc1, kc2, kc3 = st.columns(3)
                with kc1: win_rate = st.number_input("Est. Win Rate (%)", min_value=1.0, max_value=99.0, value=55.0, step=1.0) / 100.0
                with kc2: risk_reward = st.number_input("Risk/Reward Ratio", min_value=0.1, max_value=100.0, value=1.5, step=0.1)
                with kc3: bankroll = st.number_input("Account Max Risk ($)", min_value=1.0, max_value=1000000000.0, value=10000.0, step=100.0)

                kelly_pct = max(0.0, win_rate - ((1.0 - win_rate) / risk_reward))
                half_kelly = kelly_pct / 2.0

                st.markdown(f"""
                <div style="padding:10px; background:#1A0500; border-left:4px solid #FF6600; margin-top:10px;">
                    <span style="color:#FFF; font-weight:bold; font-family:monospace; font-size:14px;">Full Kelly: {kelly_pct*100:.2f}% | Half Kelly (Rec): {half_kelly*100:.2f}%</span><br>
                    <span style="color:#00CC44; font-family:monospace; font-size:16px;">Recommended Max Capital Allocation: ${bankroll * half_kelly:.2f}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

            # ── SPX DIRECTION PREDICTOR ─────────────────────────────
            st.markdown('<div class="bb-ph">🧭 SPX DAILY DIRECTION PREDICTOR — QUANT ENGINE</div>', unsafe_allow_html=True)
            _dir_result = compute_spx_direction(_0dte_chain, _spx, _vix_data)
            if _dir_result:
                _d = _dir_result
                _conf_colors = {"HIGH": "#00CC44", "MEDIUM": "#FF8C00", "LOW": "#888"}
                _conf_c = _conf_colors.get(_d['confidence'], '#888')
                _score_bar_pct = min(abs(_d['normalized']) * 100, 100)
                _score_bar_color = _d['direction_color']

                # Direction header card
                st.markdown(f'''
                <div style="background:#080808;border:1px solid {_d["direction_color"]};border-left:5px solid {_d["direction_color"]};
                    padding:16px 20px;margin-bottom:10px;font-family:'IBM Plex Mono',monospace">
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
                    <div>
                    <div style="color:{_d["direction_color"]};font-size:22px;font-weight:800;letter-spacing:2px">
                        {_d["direction"]}</div>
                    <div style="color:#888;font-size:10px;margin-top:2px">Confidence:
                        <span style="color:{_conf_c};font-weight:700">{_d["confidence"]}</span>
                        &nbsp;|&nbsp; Score: <span style="color:{_d["direction_color"]};font-weight:700">{_d["score"]:+.1f}</span>
                        / ±{_d["max_score"]}</div>
                    </div>
                    <div style="text-align:right">
                    <div style="color:#888;font-size:9px;letter-spacing:1px">EXPECTED RANGE</div>
                    <div style="color:#FFF;font-size:16px;font-weight:700">{_d["expected_range"]}</div>
                    <div style="color:#555;font-size:9px">1σ Move: ±${_d["daily_em"]:.0f} pts (VIX {_d["vix"]:.0f})</div>
                    </div>
                </div>
                <div style="margin-top:10px;background:#111;border-radius:4px;height:6px;overflow:hidden">
                    <div style="width:{_score_bar_pct}%;height:100%;background:{_score_bar_color};
                        border-radius:4px;transition:width 0.3s"></div>
                </div>
                </div>''', unsafe_allow_html=True)

                # Signal breakdown table
                _sig_header = ('<div style="display:grid;grid-template-columns:140px 130px 60px 1fr;gap:6px;'
                            'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                            'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                            '<span>SIGNAL</span><span>VALUE</span><span>WEIGHT</span><span>INTERPRETATION</span></div>')
                st.markdown(_sig_header, unsafe_allow_html=True)

                for sig_name, sig_val, sig_weight, sig_desc, sig_color in _d["signals"]:
                    _w_sign = "+" if sig_weight >= 0 else ""
                    _w_color = "#00CC44" if sig_weight > 0 else ("#FF4444" if sig_weight < 0 else "#555")
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:140px 130px 60px 1fr;gap:6px;'
                        f'padding:5px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px;align-items:center">'
                        f'<span style="color:#CCC;font-weight:600">{sig_name}</span>'
                        f'<span style="color:{sig_color};font-weight:700">{sig_val}</span>'
                        f'<span style="color:{_w_color};font-weight:700">{_w_sign}{sig_weight:.1f}</span>'
                        f'<span style="color:#888;font-size:10px">{sig_desc}</span></div>',
                        unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#555;font-family:monospace;font-size:11px;padding:10px">'
                            'Direction predictor requires options chain + SPX data.</div>',
                            unsafe_allow_html=True)

            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

            st.markdown('<div class="bb-ph">📊 GAMMA EXPOSURE (GEX) PROFILE</div>', unsafe_allow_html=True)

            _exp_col, _range_col = st.columns([2, 2])
            with _exp_col:
                _exp_choice = st.selectbox(
                    "Expiration Filter",
                    options=["0DTE (Today Only)", "≤ 7 Days (Weekly)", "≤ 30 Days", "≤ 45 DTE", "All (≤ 1 Year)"],
                    index=0,
                    key="gex_exp_filter",
                    help="Which expirations to include in the GEX calculation"
                )
            with _range_col:
                _chart_range_pct = st.selectbox(
                    "Chart Strike Range",
                    options=["±2% (~±140 pts)", "±3% (~±210 pts)", "±5% (~±350 pts)", "±7% (~±490 pts)"],
                    index=0,
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

        render_0dte_fragment()

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

            # Big environment banner with trade implications
            _trade_guidance = {
                "EXPANSIONARY 🟢": "Favor: Equities (cyclicals, tech, small-caps) · Long risk-assets · Steepener trades · Commodities on reflation",
                "MIXED / NEUTRAL 🟡": "Favor: Quality large-caps · Sector-selective · Hedge with Treasuries · Reduce leverage · Watch credit spreads",
                "CAUTIONARY ⚠️": "Favor: Defensives (staples, healthcare, utilities) · Short duration · Gold hedge · Reduce cyclicals exposure",
                "CONTRACTIONARY 🔴": "Favor: Cash/T-Bills · Gold · Short equities (SPY puts) · Long USD · Avoid junk credit · Recession playbook",
            }
            _guidance = _trade_guidance.get(_env_label, "")
            st.markdown(
                f'<div style="background:#0A0A0A;border:1px solid {_env_color};border-left:5px solid {_env_color};'
                f'padding:14px 18px;font-family:monospace;margin-bottom:10px">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                f'<div style="flex:1">'
                f'<div style="color:{_env_color};font-size:18px;font-weight:900;letter-spacing:2px">{_env_label}</div>'
                f'<div style="color:#AAA;font-size:11px;margin-top:4px;line-height:1.6">{_env_desc}</div>'
                f'<div style="color:{_env_color};font-size:10px;margin-top:8px;border-top:1px solid #1A1A1A;padding-top:8px;">'
                f'<span style="color:#555">TRADE POSITIONING →</span> {_guidance}</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:90px;margin-left:16px">'
                f'<div style="color:{_env_color};font-size:30px;font-weight:900">{_total:+d}</div>'
                f'<div style="color:#555;font-size:10px">of ±{_max} pts</div>'
                f'</div>'
                f'</div></div>', unsafe_allow_html=True)

            # Signal grid — always 4 columns, signals wrap into new rows naturally
            _sig_list = list(_signals.items())
            _n_rows = (len(_sig_list) + 3) // 4
            for _row in range(_n_rows):
                _row_items = _sig_list[_row * 4 : _row * 4 + 4]
                _row_cols = st.columns(4)
                for _ci, (sig_name, sig) in enumerate(_row_items):
                    with _row_cols[_ci]:
                        _sc = sig["color"]
                        _arrow = "▲" if sig["score"] > 0 else ("▼" if sig["score"] < 0 else "─")
                        _score_dots = "●" * abs(sig["score"]) + "○" * (2 - abs(sig["score"]))
                        st.markdown(
                            f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:3px solid {_sc};'
                            f'padding:12px;font-family:monospace;height:80px;display:flex;flex-direction:column;justify-content:space-between">'
                            f'<div style="color:#555;font-size:9px;letter-spacing:1px">{sig_name.upper()}</div>'
                            f'<div style="color:{_sc};font-size:12px;font-weight:700;line-height:1.3">{_arrow} {sig["label"]}</div>'
                            f'<div style="color:{_sc};font-size:9px;opacity:0.6">{_score_dots}</div>'
                            f'</div>', unsafe_allow_html=True)
                # spacer between rows
                if _row < _n_rows - 1:
                    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
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
        # NET LIQUIDITY INDICATOR (Feature 2)
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">💧 NET LIQUIDITY INDICATOR — WALCL − TGA − RRP</div>', unsafe_allow_html=True)

        with st.spinner("Computing net liquidity…"):
            _nl_data = get_net_liquidity(st.session_state.fred_key)

        if _nl_data is not None and not _nl_data.empty:
            _nl_latest = _nl_data.iloc[-1]
            _nl_prev = _nl_data.iloc[-2] if len(_nl_data) > 1 else _nl_latest
            _nl_val = _nl_latest["Net_Liquidity_T"]
            _nl_chg = _nl_val - _nl_prev["Net_Liquidity_T"]
            _nl_c = "#00CC44" if _nl_chg >= 0 else "#FF4444"
            _nl_sign = "+" if _nl_chg >= 0 else ""

            # Summary cards
            _nl_c1, _nl_c2, _nl_c3, _nl_c4 = st.columns(4)
            with _nl_c1:
                st.markdown(f'<div style="background:#0A0A0A;border:1px solid #1A1A1A;border-top:3px solid {_nl_c};padding:12px;font-family:monospace;text-align:center">'
                            f'<div style="color:#555;font-size:9px;letter-spacing:1px">NET LIQUIDITY</div>'
                            f'<div style="color:{_nl_c};font-size:20px;font-weight:700">${_nl_val:.2f}T</div>'
                            f'<div style="color:{_nl_c};font-size:10px">{_nl_sign}{_nl_chg:.3f}T WoW</div></div>', unsafe_allow_html=True)
            with _nl_c2:
                st.markdown(f'<div style="background:#0A0A0A;border:1px solid #1A1A1A;border-top:3px solid #FF6600;padding:12px;font-family:monospace;text-align:center">'
                            f'<div style="color:#555;font-size:9px;letter-spacing:1px">FED ASSETS (WALCL)</div>'
                            f'<div style="color:#FF8C00;font-size:16px;font-weight:700">${_nl_latest["WALCL"]/1e6:.2f}T</div></div>', unsafe_allow_html=True)
            with _nl_c3:
                st.markdown(f'<div style="background:#0A0A0A;border:1px solid #1A1A1A;border-top:3px solid #FF4444;padding:12px;font-family:monospace;text-align:center">'
                            f'<div style="color:#555;font-size:9px;letter-spacing:1px">TGA (DRAIN)</div>'
                            f'<div style="color:#FF4444;font-size:16px;font-weight:700">${_nl_latest["TGA"]/1e6:.2f}T</div></div>', unsafe_allow_html=True)
            with _nl_c4:
                st.markdown(f'<div style="background:#0A0A0A;border:1px solid #1A1A1A;border-top:3px solid #FF4444;padding:12px;font-family:monospace;text-align:center">'
                            f'<div style="color:#555;font-size:9px;letter-spacing:1px">RRP (DRAIN)</div>'
                            f'<div style="color:#FF4444;font-size:16px;font-weight:700">${_nl_latest["RRP"]/1e6:.2f}T</div></div>', unsafe_allow_html=True)

            # Net Liquidity chart
            fig_nl = dark_fig(300)
            fig_nl.add_trace(go.Scatter(
                x=_nl_data["Date"], y=_nl_data["Net_Liquidity_T"],
                mode="lines", name="Net Liquidity",
                line=dict(color="#00CC44", width=2),
                fill="tozeroy", fillcolor="rgba(0,204,68,0.08)",
            ))
            fig_nl.update_layout(
                margin=dict(l=50, r=10, t=30, b=30), height=300,
                title=dict(text="FED NET LIQUIDITY ($T) — WALCL − TGA − RRP", font=dict(size=10, color="#FF6600"), x=0),
                xaxis=dict(color="#555", showgrid=False),
                yaxis=dict(color="#555", gridcolor="#111", tickprefix="$", ticksuffix="T"),
            )
            st.plotly_chart(fig_nl, use_container_width=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Net liquidity data requires FRED API key with WALCL, WTREGEN, RRPONTSYD.</p>', unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════════
        # YIELD CURVE 3D EVOLUTION (Feature 3)
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">🏔️ YIELD CURVE 3D EVOLUTION — 52 WEEK HISTORY</div>', unsafe_allow_html=True)

        with st.spinner("Loading yield curve evolution…"):
            _yc3d_data = get_yield_curve_history(st.session_state.fred_key, lookback_weeks=52)

        if _yc3d_data is not None and not _yc3d_data.empty:
            # Take latest 8 snapshots for readable 3D surface
            _yc3d_dates = sorted(_yc3d_data["Date"].unique())
            _selected_dates = _yc3d_dates[-8:] if len(_yc3d_dates) > 8 else _yc3d_dates
            _yc3d_filtered = _yc3d_data[_yc3d_data["Date"].isin(_selected_dates)]

            fig_yc3d = dark_fig(450)
            _colors_3d = ["#1a3a5c", "#2a5a8c", "#3a7abc", "#4a9adc", "#5abafc", "#8accff", "#bbddff", "#FF6600"]

            for i, date in enumerate(_selected_dates):
                _date_slice = _yc3d_filtered[_yc3d_filtered["Date"] == date].sort_values("Maturity_Num")
                if _date_slice.empty:
                    continue
                _date_str = date.strftime("%b %d") if hasattr(date, 'strftime') else str(date)[:10]
                _color = _colors_3d[min(i, len(_colors_3d) - 1)]
                _opacity = 0.4 + (i / max(len(_selected_dates) - 1, 1)) * 0.6

                fig_yc3d.add_trace(go.Scatter(
                    x=_date_slice["Maturity"], y=_date_slice["Yield"],
                    mode="lines+markers",
                    name=_date_str,
                    line=dict(color=_color, width=1.5 + i * 0.3),
                    marker=dict(size=4, color=_color),
                    opacity=_opacity,
                ))

            fig_yc3d.update_layout(
                margin=dict(l=40, r=10, t=30, b=40), height=450,
                title=dict(text="YIELD CURVE EVOLUTION — Opaque = Recent, Faded = Historical",
                           font=dict(size=10, color="#FF6600"), x=0),
                xaxis=dict(title="Maturity", color="#555", tickfont=dict(size=9), showgrid=False),
                yaxis=dict(title="Yield (%)", color="#555", gridcolor="#111", tickfont=dict(size=9), ticksuffix="%"),
                legend=dict(font=dict(size=8, color="#888"), bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_yc3d, use_container_width=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Yield curve 3D data loading…</p>', unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════════
        # CROSS-ASSET VOLATILITY (Feature 4) + CORRELATION MATRIX (Feature 5)
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        _vol_left, _vol_right = st.columns([3, 2])

        with _vol_left:
            st.markdown('<div class="bb-ph">⚡ CROSS-ASSET VOLATILITY MONITOR</div>', unsafe_allow_html=True)
            with st.spinner("Loading volatility data…"):
                _vol_data = get_cross_asset_volatility()

            if _vol_data:
                _vol_names = [v["label"] for v in _vol_data]
                _vol_vals = [v["current"] for v in _vol_data]
                _vol_pcts = [v["percentile"] for v in _vol_data]
                _vol_colors = ["#FF4444" if v["regime"] == "ELEVATED" else "#FF8C00" if v["regime"] == "NORMAL" else "#00CC44" for v in _vol_data]

                fig_vol_cross = dark_fig(300)
                fig_vol_cross.add_trace(go.Bar(
                    x=_vol_names, y=_vol_vals,
                    marker=dict(color=_vol_colors, line=dict(width=0), opacity=0.9),
                    text=[f"{v:.1f}" for v in _vol_vals],
                    textposition="outside", textfont=dict(size=10, color="#FF8C00"),
                    hovertext=[f"{v['label']}<br>Current: {v['current']:.2f}<br>Pctile: {v['percentile']:.0f}%<br>Regime: {v['regime']}" for v in _vol_data],
                    hoverinfo="text",
                ))
                fig_vol_cross.update_layout(
                    margin=dict(l=40, r=10, t=30, b=30), height=300,
                    title=dict(text="VIX · GVZ · OVX · EVZ — Current Levels (🟢 Low · 🟡 Normal · 🔴 Elevated)",
                               font=dict(size=10, color="#FF6600"), x=0),
                    xaxis=dict(color="#555", tickfont=dict(size=9)),
                    yaxis=dict(color="#555", gridcolor="#111", tickfont=dict(size=9)),
                )
                st.plotly_chart(fig_vol_cross, use_container_width=True)

                # Percentile bars
                for v in _vol_data:
                    _p_c = "#FF4444" if v["percentile"] > 75 else "#FF8C00" if v["percentile"] > 50 else "#00CC44"
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;margin:2px 0;font-family:monospace;font-size:10px">'
                        f'<span style="color:#888;min-width:80px">{v["label"][:12]}</span>'
                        f'<div style="flex:1;height:8px;background:#111;border-radius:2px;overflow:hidden">'
                        f'<div style="width:{v["percentile"]}%;height:100%;background:{_p_c}"></div></div>'
                        f'<span style="color:{_p_c};font-weight:700;min-width:40px;text-align:right">{v["percentile"]:.0f}%</span>'
                        f'<span style="color:#555;font-size:8px;min-width:55px">{v["regime"]}</span></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Volatility data loading…</p>', unsafe_allow_html=True)

        with _vol_right:
            st.markdown('<div class="bb-ph">🔗 CROSS-ASSET CORRELATION MATRIX (7 ASSETS)</div>', unsafe_allow_html=True)
            with st.spinner("Computing correlations…"):
                _corr_data = get_macro_correlation_matrix()

            if _corr_data is not None and isinstance(_corr_data, dict):
                _corr_method = st.radio("Method", ["Pearson ρ", "Spearman ρₛ"], horizontal=True, key="corr_method", label_visibility="collapsed")
                _corr_key = "pearson" if "Pearson" in _corr_method else "spearman"
                _corr_df = _corr_data[_corr_key]
                _corr_vals = _corr_df.values.tolist()
                _corr_labels = list(_corr_df.columns)
                _corr_text = [[f"{v:.2f}" for v in row] for row in _corr_vals]

                fig_corr = go.Figure(data=go.Heatmap(
                    z=_corr_vals, x=_corr_labels, y=_corr_labels,
                    text=_corr_text, texttemplate="%{text}",
                    colorscale=[[0, "#FF4444"], [0.5, "#111111"], [1, "#00CC44"]],
                    zmin=-1, zmax=1,
                    textfont=dict(size=9, color="#CCC"),
                ))
                _lb = _corr_data.get("lookback_days", 60)
                _method_label = "PEARSON" if _corr_key == "pearson" else "SPEARMAN"
                fig_corr.update_layout(
                    paper_bgcolor="#000", plot_bgcolor="#000",
                    font=dict(color="#888", family="IBM Plex Mono"),
                    margin=dict(l=80, r=10, t=30, b=50), height=380,
                    title=dict(text=f"{_method_label} — {_lb} DAY (7 ASSETS)", font=dict(size=10, color="#FF6600"), x=0),
                    xaxis=dict(tickfont=dict(size=8, color="#888")),
                    yaxis=dict(tickfont=dict(size=8, color="#888"), autorange="reversed"),
                )
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Correlation matrix loading…</p>', unsafe_allow_html=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # FEAT-05: ECONOMIC SURPRISE INDEX + FEAT-04: CFTC COT
    # ════════════════════════════════════════════════════════════════════
    _esi_col, _cot_col = st.columns([1, 2])

    with _esi_col:
        st.markdown('<div class="bb-ph">📊 ECONOMIC SURPRISE INDEX</div>', unsafe_allow_html=True)
        with st.spinner("Computing ESI…"):
            _esi = get_economic_surprise_index(st.session_state.fred_key)
        if _esi:
            st.markdown(
                f'<div style="background:#080808;border:1px solid #1A1A1A;border-left:4px solid {_esi["label_color"]};'
                f'padding:14px 18px;font-family:monospace;margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<div>'
                f'<div style="color:#555;font-size:9px;letter-spacing:1px">MACRO SURPRISES</div>'
                f'<div style="color:{_esi["label_color"]};font-size:22px;font-weight:900;margin-top:4px">{_esi["label"]}</div>'
                f'</div>'
                f'<div style="text-align:right">'
                f'<div style="color:{_esi["label_color"]};font-size:18px;font-weight:700">{_esi["avg_surprise_pct"]:+.1f}%</div>'
                f'<div style="color:#555;font-size:8px">AVG SURPRISE</div>'
                f'</div></div></div>',
                unsafe_allow_html=True)
            for _ei in _esi.get("items", [])[:5]:
                _s_c = "#00CC44" if _ei["surprise_pct"] > 0 else "#FF4444"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:3px 8px;'
                    f'font-family:monospace;font-size:10px;border-bottom:1px solid #0D0D0D">'
                    f'<span style="color:#888;flex:1">{_ei["name"][:30]}</span>'
                    f'<span style="color:{_s_c};font-weight:600;min-width:50px;text-align:right">{_ei["surprise_pct"]:+.1f}%</span>'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">ESI data requires macro calendar with actuals.</p>', unsafe_allow_html=True)

    with _cot_col:
        st.markdown('<div class="bb-ph">🏛️ INSTITUTIONAL POSITIONING (CFTC COT)</div>', unsafe_allow_html=True)
        with st.spinner("Loading CFTC data…"):
            _cot = get_cot_positioning()
        if _cot:
            # Header row
            st.markdown(
                '<div style="display:grid;grid-template-columns:1fr 100px 90px 90px;gap:8px;'
                'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                'font-size:8px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                '<span>CONTRACT</span><span>NET POS</span><span>WK CHG</span><span>SIGNAL</span></div>',
                unsafe_allow_html=True)
            for _ct in _cot:
                _chg_c = "#00CC44" if _ct["net_change"] > 0 else "#FF4444" if _ct["net_change"] < 0 else "#888"
                _chg_sign = "+" if _ct["net_change"] > 0 else ""
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:1fr 100px 90px 90px;gap:8px;'
                    f'padding:5px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px">'
                    f'<span style="color:#FFF;font-weight:600">{_ct["name"]}</span>'
                    f'<span style="color:{_ct["signal_color"]};font-weight:700">{_ct["net_noncomm"]:,}</span>'
                    f'<span style="color:{_chg_c}">{_chg_sign}{_ct["net_change"]:,}</span>'
                    f'<span style="color:{_ct["signal_color"]};font-size:9px;font-weight:700">{_ct["signal"]}</span></div>',
                    unsafe_allow_html=True)
            st.markdown(
                f'<div style="color:#444;font-size:8px;font-family:monospace;margin-top:4px">'
                f'Source: CFTC Commitment of Traders | Updated weekly (Fridays) | '
                f'Last: {_cot[0].get("date", "N/A") if _cot else "N/A"}</div>',
                unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">CFTC COT data unavailable.</p>', unsafe_allow_html=True)


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

    # ── Institutional BTC ETF Flows ───────────────────────────────────
    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="bb-ph">📊 BTC ETF DIRECTIONAL FLOW PROXY — DAILY NET (NOT AUM FLOWS)</div>', unsafe_allow_html=True)
    with st.spinner("Loading ETF flow data…"):
        _etf_df = fetch_btc_etf_flows()
        _etf_estimated = False
        if _etf_df is None or _etf_df.empty:
            _etf_df = fetch_btc_etf_flows_fallback()
            _etf_estimated = True
    if _etf_df is not None and not _etf_df.empty:
        _etf_fig = render_crypto_etf_chart(_etf_df, is_estimated=_etf_estimated)
        if _etf_fig:
            st.plotly_chart(_etf_fig, use_container_width=True, config={'displayModeBar': False})
        if _etf_estimated:
            st.markdown(
                '<div style="background:#0A0500;border-left:3px solid #FF8C00;padding:8px 12px;'
                'font-family:monospace;font-size:10px;color:#FF8C00">⚠️ Data estimated from yfinance '
                'volume × price action. Actual fund flow data from Farside Investors was unavailable.</div>',
                unsafe_allow_html=True
            )
        # FIX-13: Clarification caption
        st.markdown(
            '<div style="background:#050505;border-left:3px solid #555;padding:6px 12px;'
            'font-family:monospace;font-size:9px;color:#666;margin-top:4px">'
            'ℹ️ This is a directional volume approximation (volume × typical price × direction), '
            'not real AUM fund flow data. Values are in billions ($B). '
            'Treat as a sentiment proxy, not as actual institutional capital flows.</div>',
            unsafe_allow_html=True
        )

        # ── Mini summary dashboard for latest day ──────────────────────
        try:
            _latest = _etf_df.iloc[-1]
            _etf_only = {k: v for k, v in _latest.items() if k != "Total" and k in _ETF_TICKERS}
            _net = _latest.get("Total", sum(_etf_only.values()))
            _inflows = {k: v for k, v in _etf_only.items() if v > 0}
            _outflows = {k: v for k, v in _etf_only.items() if v < 0}
            _top_name, _top_val = max(_etf_only.items(), key=lambda x: abs(x[1])) if _etf_only else ("—", 0)
            _net_color = "#00CC44" if _net >= 0 else "#FF4444"
            _net_sign = "+" if _net >= 0 else ""
            _top_color = "#00CC44" if _top_val >= 0 else "#FF4444"
            _top_sign = "+" if _top_val >= 0 else ""
            _date_str = _etf_df.index[-1].strftime("%b %d, %Y")

            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;'
                f'background:#060606;border:1px solid #1A1A1A;border-radius:4px;padding:10px 14px;'
                f'margin:6px 0;font-family:\'IBM Plex Mono\',monospace">'
                # Net Flow
                f'<div style="text-align:center">'
                f'<div style="color:#555;font-size:9px;letter-spacing:1px">NET FLOW</div>'
                f'<div style="color:{_net_color};font-size:16px;font-weight:700">{_net_sign}${abs(_net):,.2f}B</div>'
                f'<div style="color:#444;font-size:8px">{_date_str}</div>'
                f'</div>'
                # Inflows
                f'<div style="text-align:center">'
                f'<div style="color:#555;font-size:9px;letter-spacing:1px">INFLOWS</div>'
                f'<div style="color:#00CC44;font-size:16px;font-weight:700">{len(_inflows)}</div>'
                f'<div style="color:#444;font-size:8px">ETFs positive</div>'
                f'</div>'
                # Outflows
                f'<div style="text-align:center">'
                f'<div style="color:#555;font-size:9px;letter-spacing:1px">OUTFLOWS</div>'
                f'<div style="color:#FF4444;font-size:16px;font-weight:700">{len(_outflows)}</div>'
                f'<div style="color:#444;font-size:8px">ETFs negative</div>'
                f'</div>'
                # Top Mover
                f'<div style="text-align:center">'
                f'<div style="color:#555;font-size:9px;letter-spacing:1px">TOP MOVER</div>'
                f'<div style="color:{_top_color};font-size:16px;font-weight:700">{_top_name}</div>'
                f'<div style="color:{_top_color};font-size:9px">{_top_sign}${abs(_top_val):,.2f}B</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        except Exception:
            pass

    else:
        st.markdown(
            '<p style="color:#555;font-family:monospace;font-size:11px">'
            'ETF flow data unavailable. Both Farside and yfinance sources failed.</p>',
            unsafe_allow_html=True
        )
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
        all_poly   = polymarket_events(100)
        all_mkts   = polymarket_markets(100)

    if not all_poly:
        st.markdown('<div style="background:#0A0500;border-left:4px solid #FF6600;padding:12px;font-family:monospace;font-size:12px;color:#FF8C00">⚠️ Could not reach Polymarket API.</div>', unsafe_allow_html=True)
    else:
        from datetime import timezone as _tz
        _now_utc = datetime.now(_tz.utc)
        _two_months_ago = _now_utc - timedelta(days=60)

        def is_active(e):
            if e.get("closed", False) or e.get("resolved", False): return False
            end = e.get("endDate","") or ""
            if end:
                try:
                    ed = datetime.fromisoformat(end.replace("Z","+00:00"))
                    if ed < _now_utc: return False
                except: pass
            return True

        def is_recently_closed(e):
            """Only show closed markets resolved within last 60 days."""
            if not (e.get("closed", False) or e.get("resolved", False)): return False
            end = e.get("endDate","") or e.get("resolvedAt","") or ""
            if end:
                try:
                    ed = datetime.fromisoformat(end.replace("Z","+00:00"))
                    return ed >= _two_months_ago
                except: pass
            return False

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

        # ═══════════════════════════════════════════════════════
        # SECTION 1: MISPRICING SCANNER (main alpha tool)
        # ═══════════════════════════════════════════════════════
        st.markdown('<div class="bb-ph" style="margin-top:4px">🔬 MISPRICING SCANNER — ALGORITHMIC ALPHA DETECTOR</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#555;font-family:monospace;font-size:10px;margin-bottom:8px">'
            'Finds markets where crowd pricing appears unreliable due to low liquidity, '
            'herd behavior, or extreme probability with thin volume. '
            '<b style="color:#00CC44">BET YES</b> / <b style="color:#FF4444">BET NO</b> = actionable edge. '
            '<b style="color:#00CC44">CONFIRMED</b> = deep market agrees. '
            '<b style="color:#FF8C00">WATCH</b> = wait for entry.</div>', unsafe_allow_html=True)

        if all_mkts:
            mispriced = score_poly_mispricing(all_mkts)
            if mispriced:
                # Table header
                st.markdown(
                    '<div style="display:grid;grid-template-columns:1fr 70px 70px 70px 70px 80px 80px;gap:6px;'
                    'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;font-size:9px;'
                    'color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                    '<span>MARKET</span><span>RAW %</span><span>ADJ %</span><span>LIQUIDITY</span>'
                    '<span>ACTIVITY</span><span>EDGE</span><span>SIGNAL</span></div>',
                    unsafe_allow_html=True)

                for mp in mispriced[:12]:
                    liq_c  = "#00CC44" if mp["liq_score"] >= 0.7 else ("#FF8C00" if mp["liq_score"] >= 0.4 else "#FF4444")
                    raw_c  = "#00CC44" if mp["raw_yes"] >= 50 else "#FF4444"
                    adj_c  = "#00CC44" if mp["adj_yes"] >= 50 else "#FF4444"
                    edge_c = "#FF6600" if mp["edge"] > 0.15 else "#888"
                    poly_link = f"https://polymarket.com/event/{mp['url']}" if mp['url'] else "#"
                    spread_info = f' [{mp["spread"]}]' if mp["spread"] else ""
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:1fr 70px 70px 70px 70px 80px 80px;gap:6px;'
                        f'padding:6px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px;align-items:center">'
                        f'<span><a href="{poly_link}" target="_blank" style="color:#CCC;text-decoration:none">{_esc(mp["title"])}</a></span>'
                        f'<span style="color:{raw_c};font-weight:700">{mp["raw_yes"]}%</span>'
                        f'<span style="color:{adj_c}">{mp["adj_yes"]}%</span>'
                        f'<span style="color:{liq_c};font-size:10px;font-weight:700">{mp["liq_tier"]}{spread_info}</span>'
                        f'<span style="color:#888;font-size:10px">{mp["activity_ratio"]*100:.0f}%</span>'
                        f'<span style="color:{edge_c};font-weight:700">{mp["edge"]:.3f}</span>'
                        f'<span style="color:{mp["signal_color"]};font-weight:700;font-size:10px">{mp["signal"]}</span>'
                        f'</div>', unsafe_allow_html=True)

                # ── Mispricing score bar chart — color = signal color, labeled clearly
                top8_mis = mispriced[:8]
                mis_labels = [m["title"][:45]+"…" if len(m["title"])>45 else m["title"] for m in top8_mis]
                mis_scores = [m["mispricing_score"]*1000 for m in top8_mis]
                mis_colors = [m["signal_color"] for m in top8_mis]
                mis_hover  = [f"Signal: {m['signal']}<br>Edge: {m['edge']:.3f}<br>Liq: {m['liq_tier']}<br>Raw: {m['raw_yes']}% → Adj: {m['adj_yes']}%"
                            for m in top8_mis]

                fig_mis = dark_fig(300)
                fig_mis.add_trace(go.Bar(
                    x=mis_scores, y=mis_labels, orientation="h",
                    marker=dict(color=mis_colors, line=dict(width=0), opacity=0.85),
                    hovertext=mis_hover, hoverinfo="text+x",
                    # No textposition="outside" — use annotations instead to avoid overlap
                ))
                # Add signal labels as annotations at right edge of each bar
                for i, (score, sig_label, color) in enumerate(zip(mis_scores, [m["signal"] for m in top8_mis], mis_colors)):
                    fig_mis.add_annotation(
                        x=score, y=i,
                        text=f"  {sig_label}",
                        showarrow=False,
                        xanchor="left", yanchor="middle",
                        font=dict(size=9, color=color, family="IBM Plex Mono"),
                    )
                fig_mis.update_layout(
                    margin=dict(l=10, r=160, t=32, b=0), height=300,
                    title=dict(text="MISPRICING SCORE — 🟢 BET YES / CONFIRMED · 🔴 BET NO / CONTRARIAN · 🟠 WATCH", font=dict(size=10, color="#FF6600"), x=0),
                    xaxis=dict(showgrid=False, color="#333", title=None),
                    yaxis=dict(autorange="reversed", tickfont=dict(size=9, color="#CCC"), title=None),
                )
                st.plotly_chart(fig_mis, width="stretch")

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ═══════════════════════════════════════════════════════
        # SECTION 2: DASHBOARD PANEL — Probability + Volume stacked vertically for readability
        # ═══════════════════════════════════════════════════════
        st.markdown('<div class="bb-ph">📊 TOP 10 ACTIVE EVENTS — PROBABILITY & VOLUME</div>', unsafe_allow_html=True)

        if top10:
            def _event_best_outcome(evt):
                """Return (leading_outcome_name, probability_0_to_100) for the best sub-market."""
                markets = evt.get("markets", [])
                best_name, best_p = None, 0.0
                for mk in markets:
                    pp = _parse_poly_field(mk.get("outcomePrices", []))
                    if not pp: continue
                    p = _safe_float(pp[0]) * 100
                    if p > best_p:
                        best_p = p
                        # Multi-outcome: groupItemTitle = candidate/team name
                        # Binary: fall back to question or generic "Yes"
                        candidate = mk.get("groupItemTitle") or mk.get("question", "")
                        best_name = str(candidate).strip()[:35] if candidate else None
                # Fallback to event-level data if no sub-markets found
                if best_name is None:
                    pp = _parse_poly_field(evt.get("outcomePrices", []))
                    outcomes = _parse_poly_field(evt.get("outcomes", []))
                    if pp:
                        best_p = max(0.0, min(100.0, _safe_float(pp[0]) * 100))
                    best_name = str(outcomes[0])[:35] if outcomes else "Yes"
                return best_name, round(best_p, 1)

            event_urls   = [poly_url(e) for e in top10]
            event_titles = [e.get("title", e.get("question",""))[:38] for e in top10]
            outcomes_data = [_event_best_outcome(e) for e in top10]
            outcome_names = [o[0] for o in outcomes_data]
            y_probs       = [o[1] for o in outcomes_data]
            vols    = [_safe_float(e.get("volume",0))/1e6 for e in top10]
            vols24  = [_safe_float(e.get("volume24hr",0))/1e6 for e in top10]  # in $M directly

            # ── Chart 1: Probability — full width, showing event title + leading outcome
            # Y-axis label = "Event title  →  Leading outcome"
            prob_labels = [f"{t}  →  {o}" for t, o in zip(event_titles, outcome_names)]
            prob_colors = ["#00CC44" if p >= 65 else "#FF8C00" if p >= 50 else "#FF4444" for p in y_probs]
            prob_hover  = [f"<b>{e.get('title','')}</b><br>Leading: {o} @ {p:.1f}%<br><a href='{u}'>Open on Polymarket ↗</a>"
                        for e, o, p, u in zip(top10, outcome_names, y_probs, event_urls)]

            fig_prob = dark_fig(360)
            fig_prob.add_trace(go.Bar(
                x=y_probs, y=prob_labels, orientation="h",
                marker=dict(color=prob_colors, line=dict(width=0), opacity=0.85),
                hovertext=prob_hover, hoverinfo="text",
            ))
            for i, (p, c, o) in enumerate(zip(y_probs, prob_colors, outcome_names)):
                fig_prob.add_annotation(
                    x=p + 1.5, y=i,
                    text=f"<b>{p:.0f}%</b>",
                    showarrow=False, xanchor="left", yanchor="middle",
                    font=dict(size=10, color=c, family="IBM Plex Mono"),
                )
            fig_prob.add_vline(x=50, line_dash="dash", line_color="#2A2A2A", line_width=1)
            fig_prob.add_vline(x=70, line_dash="dot",  line_color="#1A1A1A", line_width=1)
            fig_prob.update_layout(
                margin=dict(l=10, r=80, t=36, b=10), height=360,
                title=dict(text="LEADING OUTCOME PROBABILITY  (event → outcome name)",
                        font=dict(size=10, color="#FF6600"), x=0),
                xaxis=dict(range=[0, 115], showgrid=False, color="#333", showticklabels=False),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9, color="#AAA")),
            )
            st.plotly_chart(fig_prob, width="stretch")

            # ── Clickable event link list under chart
            st.markdown('<div style="font-family:monospace;font-size:9px;color:#444;margin-bottom:4px">CLICK TO OPEN ON POLYMARKET ↗</div>', unsafe_allow_html=True)
            link_html = "".join(
                f'<a href="{u}" target="_blank" style="display:inline-block;margin:2px 4px 2px 0;'
                f'padding:3px 8px;background:#0D0D0D;border:1px solid #1A1A1A;color:#FF6600;'
                f'font-family:monospace;font-size:10px;text-decoration:none;white-space:nowrap">'
                f'{t[:30]}{"…" if len(t)>30 else ""} ↗</a>'
                for t, u in zip(event_titles, event_urls)
            )
            st.markdown(f'<div style="line-height:2">{link_html}</div>', unsafe_allow_html=True)

            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

            # ── Chart 2: Volume — both in $M, clean overlay
            def _fmt_m(v):
                if v >= 1.0:   return f"${v:.2f}M"
                if v >= 0.001: return f"${v*1000:.0f}K"
                return f"${v*1e6:.0f}"

            vol_hover_t = [f"<b>{e.get('title','')}</b><br>Total Vol: {_fmt_m(v)}" for e, v in zip(top10, vols)]
            vol_hover_h = [f"<b>{e.get('title','')}</b><br>24H Vol: {_fmt_m(v)}"   for e, v in zip(top10, vols24)]

            fig_vol = dark_fig(360)
            fig_vol.add_trace(go.Bar(
                name="Total Volume", x=vols, y=event_titles, orientation="h",
                marker=dict(color="#3D1500", line=dict(color="#662200", width=1)),
                hovertext=vol_hover_t, hoverinfo="text",
            ))
            fig_vol.add_trace(go.Bar(
                name="24H Volume", x=vols24, y=event_titles, orientation="h",
                marker=dict(color="#FF6600", opacity=0.9, line=dict(width=0)),
                hovertext=vol_hover_h, hoverinfo="text",
            ))
            # Annotations — only on bars wide enough to label
            max_vol = max(vols) if vols else 1
            for i, (tv, hv) in enumerate(zip(vols, vols24)):
                if tv / max_vol > 0.08:
                    fig_vol.add_annotation(
                        x=tv / 2, y=i, text=_fmt_m(tv),
                        showarrow=False, xanchor="center", yanchor="middle",
                        font=dict(size=8, color="#FF8C00", family="IBM Plex Mono"),
                    )
                if hv > 0.001 and hv / max_vol > 0.02:
                    fig_vol.add_annotation(
                        x=hv, y=i, text=f"  {_fmt_m(hv)}",
                        showarrow=False, xanchor="left", yanchor="middle",
                        font=dict(size=8, color="#FFAA44", family="IBM Plex Mono"),
                    )
            fig_vol.update_layout(
                barmode="overlay", margin=dict(l=10, r=100, t=36, b=10), height=360,
                title=dict(text="VOLUME  ▓ Total ($M)  ▓ 24H Activity ($M)  — hover for details",
                        font=dict(size=10, color="#FF6600"), x=0),
                xaxis=dict(showgrid=False, color="#333", tickprefix="$", ticksuffix="M",
                        tickfont=dict(size=8, color="#444")),
                yaxis=dict(autorange="reversed", tickfont=dict(size=10, color="#CCC")),
                legend=dict(font=dict(size=9, color="#888"), bgcolor="rgba(0,0,0,0)",
                            orientation="h", x=0, y=1.06),
            )
            st.plotly_chart(fig_vol, width="stretch")

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        # ═══════════════════════════════════════════════════════
        # SECTION 3: EVENT CARDS + HOW-TO GUIDE
        # ═══════════════════════════════════════════════════════
        poly_col, guide_col = st.columns([3, 1])
        with poly_col:
            st.markdown(f'<div class="bb-ph">📋 TOP ACTIVE EVENTS ({len(active_events)} total active)</div>', unsafe_allow_html=True)
            for e in top10:
                st.markdown(render_poly_card(e), unsafe_allow_html=True)

        with guide_col:
            st.markdown("""<div style="background:#080808;border:1px solid #1A1A1A;padding:14px;font-family:monospace;font-size:10px;color:#888;line-height:2.0">
<span style="color:#FF6600;font-weight:700">HOW TO TRADE</span><br><br>
<span style="color:#00CC44">↑ BET YES</span><br>
Crowd underpriced YES<br>
→ Buy YES shares cheap<br><br>
<span style="color:#FF4444">↓ BET NO</span><br>
Crowd overpriced YES<br>
→ Buy NO shares cheap<br><br>
<span style="color:#00CC44">✓ CONFIRMED</span><br>
Deep market agrees with<br>
probability → safe to follow<br><br>
<span style="color:#FF4444">↓ CONTRARIAN</span><br>
Deep market prices NO<br>
strongly → consider NO<br><br>
<span style="color:#FF8C00">◌ WATCH</span><br>
Mixed signals — wait<br>for volume confirmation<br><br>
<span style="color:#FF6600">EDGE</span> = gap between raw<br>crowd price and adjusted<br>fair value. Higher = more<br>mispriced.<br><br>
<span style="color:#FF4444">ILLIQ</span> crowd unreliable<br>
<span style="color:#FF8C00">THIN</span> use with caution<br>
<span style="color:#888">MED</span> decent accuracy<br>
<span style="color:#00CC44">DEEP</span> crowd is sharp<br><br>
<span style="color:#444">⚠️ Crowd odds only.<br>Not financial advice.</span>
</div>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 6 — GEO (lazy-loaded: only fetches data when user clicks in)
# ════════════════════════════════════════════════════════════════════
with tabs[6]:
    if "geo_tab_active" not in st.session_state:
        st.session_state.geo_tab_active = False

    _geo_col_a, _geo_col_b = st.columns([4, 1])
    with _geo_col_a:
        if not st.session_state.geo_tab_active:
            st.markdown(
                '<div class="bb-ph">🌍 GEOPOLITICAL INTELLIGENCE</div>',
                unsafe_allow_html=True,
            )
    with _geo_col_b:
        if st.session_state.geo_tab_active:
            if st.button("🔄 REFRESH DATA", key="geo_refresh", use_container_width=True):
                # Clear cached geo data to force fresh fetch
                from data_fetchers import (
                    fetch_conflict_events_json, fetch_military_aircraft_json,
                    fetch_satellite_positions_json, fetch_ais_vessels,
                )
                for fn in [fetch_conflict_events_json, fetch_military_aircraft_json,
                        fetch_satellite_positions_json, fetch_ais_vessels]:
                    fn.clear()
        else:
            if st.button("▶ LOAD GEO INTEL", key="geo_load", use_container_width=True):
                st.session_state.geo_tab_active = True
                st.rerun()

    if st.session_state.geo_tab_active:
        render_geo_tab()
# ════════════════════════════════════════════════════════════════════
# TAB 7 — EARNINGS TRACKER
# ════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.markdown('<div class="bb-ph">📅 EARNINGS TRACKER — UPCOMING & RECENT</div>', unsafe_allow_html=True)

    ec1, ec2 = st.columns([2,3])
    with ec1:
        st.markdown('<div class="bb-ph">UPCOMING EARNINGS CALENDAR</div>', unsafe_allow_html=True)
        with st.spinner("Fetching earnings calendar (this may take 20-30s)…"):
            _today_key = datetime.now().strftime("%Y-%m-%d")  # cache busts at midnight
            earn_df = get_earnings_calendar(_today_key)
        if earn_df.empty:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No upcoming earnings found. Yahoo Finance may be rate-limiting. Try again shortly.</p>', unsafe_allow_html=True)
        else:
            today = datetime.now().date()
            for _, row in earn_df.iterrows():
                ed = row["EarningsDate"]
                days = (ed - today).days  # can be negative (past), 0 (today), or positive (future)
                if days == 0:
                    badge, bc, bc_bg = "TODAY", "#FF6600", "rgba(255,102,0,0.08)"
                elif days > 0 and days <= 1:
                    badge, bc, bc_bg = "TOMORROW", "#00AAFF", "rgba(0,170,255,0.06)"
                elif days > 0 and days < 7:
                    badge, bc, bc_bg = f"IN {days}D", "#00AAFF", "rgba(0,170,255,0.04)"
                elif days > 0:
                    badge, bc, bc_bg = f"IN {days}D", "#555", "transparent"
                elif days >= -3:
                    badge, bc, bc_bg = "RECENT", "#888", "transparent"
                else:
                    continue  # skip anything older than 3 days
                eps_str = f"${row['EPS Est']:.2f}" if row.get("EPS Est") is not None else "—"
                ed_fmt = ed.strftime("%b %d") if hasattr(ed, "strftime") else str(ed)
                company = str(row.get('Company',''))
                sector = str(row.get('Sector','—'))
                st.markdown(f"""<div class="earn-card" style="background:{bc_bg}">
<span class="earn-ticker">{row['Ticker']}</span>
<div style="min-width:0">
    <div style="color:#CCCCCC;font-size:16px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{company}</div>
    <div style="color:#FF6600;font-size:12px;margin-top:2px;letter-spacing:1px">{sector.upper()}</div>
</div>
<span style="color:{bc};font-size:10px;font-weight:700;letter-spacing:1px;white-space:nowrap">{badge}</span>
<span class="earn-date" style="white-space:nowrap">{ed_fmt}</span>
<span style="color:#888;font-size:11px;white-space:nowrap">EPS: <span style="color:#FFCC00;font-weight:700">{eps_str}</span></span>
</div>""", unsafe_allow_html=True)

    with ec2:
        st.markdown('<div class="bb-ph">📈 QUICK EARNINGS CHART + MATRIX</div>', unsafe_allow_html=True)
        earn_tkr = st.text_input("Ticker for chart & matrix", placeholder="NVDA, AAPL…", key="ec")

        # ── OPTIONS-IMPLIED EXPECTED MOVE (Feature 10) ──
        if earn_tkr:
            _em_tkr = earn_tkr.upper().strip()
            with st.spinner(f"Computing expected move for {_em_tkr}…"):
                _em_result = get_expected_move(_em_tkr)
            if _em_result:
                _em_range_color = "#FF6600"
                st.markdown(
                    f'<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;'
                    f'padding:12px 16px;margin-bottom:10px;font-family:monospace">'
                    f'<div style="color:#FF6600;font-size:10px;letter-spacing:1px;margin-bottom:6px">'
                    f'OPTIONS-IMPLIED EXPECTED MOVE — {_em_result["expiry"]} ({_em_result["dte"]}DTE)</div>'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<div style="text-align:center">'
                    f'<div style="color:#FF4444;font-size:18px;font-weight:700">${_em_result["range_low"]:,.2f}</div>'
                    f'<div style="color:#555;font-size:8px">LOW</div></div>'
                    f'<div style="text-align:center">'
                    f'<div style="color:#FFF;font-size:24px;font-weight:900">${_em_result["price"]:,.2f}</div>'
                    f'<div style="color:#FF6600;font-size:12px;font-weight:700">±${_em_result["expected_move_dollars"]:,.2f} ({_em_result["expected_move_pct"]:+.2f}%)</div></div>'
                    f'<div style="text-align:center">'
                    f'<div style="color:#00CC44;font-size:18px;font-weight:700">${_em_result["range_high"]:,.2f}</div>'
                    f'<div style="color:#555;font-size:8px">HIGH</div></div>'
                    f'</div>'
                    f'<div style="margin-top:8px;display:flex;gap:16px;font-size:9px;color:#888">'
                    f'<span>Call: ${_em_result["call_premium"]:.2f}</span>'
                    f'<span>Put: ${_em_result["put_premium"]:.2f}</span>'
                    f'<span>ATM Strike: ${_em_result["atm_strike"]:,.2f}</span></div>'
                    f'</div>', unsafe_allow_html=True)
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
                    hdr_str = "".join(f'<span style="color:#FF6600;font-weight:700;text-align:right">{q}</span>' for q in quarters_sorted)
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

            # ════════════════════════════════════════════════════════════
            # EARNINGS MATRIX — auto-linked to Quick Earnings Chart ticker
            # ════════════════════════════════════════════════════════════
            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
            with st.spinner(f"Building Earnings Matrix for {et}…"):
                _em_data = get_earnings_matrix(et)

            if _em_data is None:
                st.markdown(f'<p style="color:#555;font-family:monospace;font-size:11px">No earnings matrix data available for {et}.</p>', unsafe_allow_html=True)
            else:
                _em_years = _em_data["years"]
                _em_qlabels = _em_data["q_labels"]
                _em_quarterly = _em_data["quarterly"]
                _em_estimates = _em_data.get("estimates", {})
                _em_surprise = _em_data.get("surprise_pct", {})
                _em_beats = _em_data.get("beats", {})
                _em_revenue_q = _em_data.get("revenue_q", {})
                _em_annual = _em_data["annual"]
                _em_annual_rev = _em_data.get("annual_revenue", {})
                _em_yoy = _em_data["yoy_growth"]
                _em_ann_growth = _em_data["annual_growth"]
                _em_rev_growth = _em_data.get("rev_growth", {})
                _em_ann_rev_growth = _em_data.get("annual_rev_growth", {})
                _em_vals = _em_data["valuations"]
                _em_currency = _em_data["currency"]
                _em_company = _em_data.get("company", et)
                _em_streak = _em_data.get("streak", 0)
                _em_beat_rate = _em_data.get("beat_rate", 0)

                # ── Header with beat/miss streak ──
                if _em_streak > 0:
                    _streak_txt = f"🔥 {_em_streak}Q BEAT STREAK"
                    _streak_c = "#00CC44"
                elif _em_streak < 0:
                    _streak_txt = f"⚠️ {abs(_em_streak)}Q MISS STREAK"
                    _streak_c = "#FF4444"
                else:
                    _streak_txt = "— NO STREAK"
                    _streak_c = "#888"
                _beat_rate_c = "#00CC44" if _em_beat_rate >= 75 else "#FF8C00" if _em_beat_rate >= 50 else "#FF4444"

                st.markdown(f'''<div class="em-container">
<div class="em-header">
<span class="em-badge">Earnings Matrix</span>
<span class="em-ticker-label">● {et}</span>
<span class="em-metric-label">EPS (GAAP)</span>
<span style="margin-left:auto;font-family:monospace;font-size:10px;color:{_streak_c};font-weight:700">{_streak_txt}</span>
<span style="margin-left:12px;font-family:monospace;font-size:10px;color:{_beat_rate_c}">Beat Rate: {_em_beat_rate:.0f}%</span>
</div>''', unsafe_allow_html=True)

                _em_left, _em_right = st.columns(2)

                with _em_left:
                    st.markdown(f'<div style="color:#555;font-family:monospace;font-size:9px;margin-bottom:6px;letter-spacing:1px">EPS ACTUAL vs ESTIMATE — {_em_currency} ($)</div>', unsafe_allow_html=True)
                    year_headers = "".join(f"<th>{yr}</th>" for yr in _em_years)
                    eps_html = f'<table class="em-table"><thead><tr><th></th>{year_headers}</tr></thead><tbody>'
                    for ql in _em_qlabels:
                        eps_html += f"<tr><td>{ql}</td>"
                        for yr in _em_years:
                            val = _em_quarterly.get(yr, {}).get(ql)
                            est = _em_estimates.get(yr, {}).get(ql)
                            beat = _em_beats.get(yr, {}).get(ql)
                            surp = _em_surprise.get(yr, {}).get(ql)
                            if val is not None:
                                color = "#00CC44" if val >= 0 else "#FF4444"
                                # Beat/miss indicator
                                if beat is True:
                                    icon = ' <span style="color:#00CC44;font-size:8px">✓</span>'
                                elif beat is False:
                                    icon = ' <span style="color:#FF4444;font-size:8px">✗</span>'
                                else:
                                    icon = ""
                                # Surprise tooltip
                                surp_str = ""
                                if surp is not None:
                                    s_c = "#00CC44" if surp >= 0 else "#FF4444"
                                    surp_str = f'<br><span style="color:{s_c};font-size:8px">{surp:+.1f}%</span>'
                                est_str = ""
                                if est is not None:
                                    est_str = f'<br><span style="color:#555;font-size:8px">est {est:.2f}</span>'
                                eps_html += f'<td style="color:{color}">{val:.2f}{icon}{est_str}{surp_str}</td>'
                            else:
                                eps_html += '<td style="color:#333">—</td>'
                        eps_html += "</tr>"
                    eps_html += '<tr class="em-annual"><td>Annual</td>'
                    for yr in _em_years:
                        val = _em_annual.get(yr)
                        if val is not None:
                            color = "#00CC44" if val >= 0 else "#FF4444"
                            eps_html += f'<td style="color:{color};font-weight:700">{val:.2f}</td>'
                        else:
                            eps_html += '<td style="color:#333">—</td>'
                    eps_html += "</tr></tbody></table>"
                    st.markdown(eps_html, unsafe_allow_html=True)

                with _em_right:
                    st.markdown('<div class="em-growth-toggle"><span class="em-growth-btn active">YoY % Growth</span></div>', unsafe_allow_html=True)
                    year_headers_g = "".join(f"<th>{yr}</th>" for yr in _em_years)
                    growth_html = f'<table class="em-table"><thead><tr><th></th>{year_headers_g}</tr></thead><tbody>'
                    for ql in _em_qlabels:
                        growth_html += f"<tr><td>{ql}</td>"
                        for yr in _em_years:
                            val = _em_yoy.get(yr, {}).get(ql)
                            if val is not None:
                                color = "#00CC44" if val >= 0 else "#FF4444"
                                growth_html += f'<td style="color:{color}">{val:+.1f}%</td>'
                            else:
                                growth_html += '<td style="color:#333">—</td>'
                        growth_html += "</tr>"
                    growth_html += '<tr class="em-annual"><td>Annual</td>'
                    for yr in _em_years:
                        val = _em_ann_growth.get(yr)
                        if val is not None:
                            color = "#00CC44" if val >= 0 else "#FF4444"
                            growth_html += f'<td style="color:{color};font-weight:700">{val:+.1f}%</td>'
                        else:
                            growth_html += '<td style="color:#333">—</td>'
                    growth_html += "</tr></tbody></table>"
                    st.markdown(growth_html, unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

                # ── Revenue table (if data exists) ──
                if _em_revenue_q:
                    st.markdown('<div class="em-container" style="margin-top:8px">', unsafe_allow_html=True)
                    _rev_left, _rev_right = st.columns(2)
                    with _rev_left:
                        st.markdown('<div style="color:#555;font-family:monospace;font-size:9px;margin-bottom:6px;letter-spacing:1px">QUARTERLY REVENUE</div>', unsafe_allow_html=True)
                        rev_year_headers = "".join(f"<th>{yr}</th>" for yr in _em_years)
                        rev_html = f'<table class="em-table"><thead><tr><th></th>{rev_year_headers}</tr></thead><tbody>'
                        for ql in _em_qlabels:
                            rev_html += f"<tr><td>{ql}</td>"
                            for yr in _em_years:
                                val = _em_revenue_q.get(yr, {}).get(ql)
                                if val is not None:
                                    if abs(val) >= 1e9:
                                        rev_html += f'<td style="color:#CCC">${val/1e9:.1f}B</td>'
                                    elif abs(val) >= 1e6:
                                        rev_html += f'<td style="color:#CCC">${val/1e6:.0f}M</td>'
                                    else:
                                        rev_html += f'<td style="color:#CCC">${val:,.0f}</td>'
                                else:
                                    rev_html += '<td style="color:#333">—</td>'
                            rev_html += "</tr>"
                        rev_html += '<tr class="em-annual"><td>Annual</td>'
                        for yr in _em_years:
                            val = _em_annual_rev.get(yr)
                            if val is not None:
                                if abs(val) >= 1e9:
                                    rev_html += f'<td style="color:#FF8C00;font-weight:700">${val/1e9:.1f}B</td>'
                                else:
                                    rev_html += f'<td style="color:#FF8C00;font-weight:700">${val/1e6:.0f}M</td>'
                            else:
                                rev_html += '<td style="color:#333">—</td>'
                        rev_html += "</tr></tbody></table>"
                        st.markdown(rev_html, unsafe_allow_html=True)

                    with _rev_right:
                        st.markdown('<div class="em-growth-toggle"><span class="em-growth-btn active">Revenue YoY %</span></div>', unsafe_allow_html=True)
                        rev_g_headers = "".join(f"<th>{yr}</th>" for yr in _em_years)
                        rev_g_html = f'<table class="em-table"><thead><tr><th></th>{rev_g_headers}</tr></thead><tbody>'
                        for ql in _em_qlabels:
                            rev_g_html += f"<tr><td>{ql}</td>"
                            for yr in _em_years:
                                val = _em_rev_growth.get(yr, {}).get(ql)
                                if val is not None:
                                    color = "#00CC44" if val >= 0 else "#FF4444"
                                    rev_g_html += f'<td style="color:{color}">{val:+.1f}%</td>'
                                else:
                                    rev_g_html += '<td style="color:#333">—</td>'
                            rev_g_html += "</tr>"
                        rev_g_html += '<tr class="em-annual"><td>Annual</td>'
                        for yr in _em_years:
                            val = _em_ann_rev_growth.get(yr)
                            if val is not None:
                                color = "#00CC44" if val >= 0 else "#FF4444"
                                rev_g_html += f'<td style="color:{color};font-weight:700">{val:+.1f}%</td>'
                            else:
                                rev_g_html += '<td style="color:#333">—</td>'
                        rev_g_html += "</tr></tbody></table>"
                        st.markdown(rev_g_html, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                _em_chart_col, _em_val_col = st.columns([3, 2])

                with _em_chart_col:
                    st.markdown('<div class="em-container">', unsafe_allow_html=True)
                    _ann_years_sorted = sorted(_em_annual.keys())
                    if _ann_years_sorted:
                        ann_labels = [str(yr) for yr in _ann_years_sorted]
                        ann_values = [_em_annual[yr] for yr in _ann_years_sorted]
                        fig_eps_line = dark_fig(250)
                        fig_eps_line.add_trace(go.Scatter(
                            x=ann_labels, y=ann_values, mode="lines+markers",
                            name="EPS",
                            line=dict(color="#00CC44", width=2),
                            marker=dict(size=8, color="#00CC44", line=dict(width=1, color="#000")),
                            text=[f"FY{yr}: ${v:.2f}" for yr, v in zip(_ann_years_sorted, ann_values)],
                            hoverinfo="text",
                        ))
                        # Overlay annual revenue on secondary axis if available
                        if _em_annual_rev:
                            rev_labels = [str(yr) for yr in _ann_years_sorted if yr in _em_annual_rev]
                            rev_values = [_em_annual_rev[yr] / 1e9 for yr in _ann_years_sorted if yr in _em_annual_rev]
                            if rev_values:
                                fig_eps_line.add_trace(go.Bar(
                                    x=rev_labels, y=rev_values, name="Revenue ($B)",
                                    marker=dict(color="rgba(255,102,0,0.15)", line=dict(color="#FF6600", width=1)),
                                    yaxis="y2",
                                    hovertext=[f"Rev: ${v:.1f}B" for v in rev_values],
                                    hoverinfo="text",
                                ))
                                fig_eps_line.update_layout(
                                    yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                                tickfont=dict(size=8, color="#FF6600"), tickprefix="$", ticksuffix="B",
                                                title=None),
                                    legend=dict(font=dict(size=8, color="#888"), bgcolor="rgba(0,0,0,0)",
                                                orientation="h", x=0, y=1.08),
                                )
                        fig_eps_line.update_layout(
                            margin=dict(l=40, r=50, t=30, b=30), height=250,
                            title=dict(text="ANNUAL EPS + REVENUE OVERLAY", font=dict(size=10, color="#FF6600"), x=0),
                            xaxis=dict(color="#555", tickfont=dict(size=9), showgrid=False),
                            yaxis=dict(color="#555", tickfont=dict(size=9), gridcolor="#111", title=None, tickprefix="$"),
                        )
                        st.plotly_chart(fig_eps_line, use_container_width=True, config={'displayModeBar': False})

                    # ── Quarterly EPS: Actual vs Estimate with beat/miss coloring ──
                    _q_bar_labels, _q_bar_actuals, _q_bar_estimates = [], [], []
                    _q_bar_colors, _q_bar_beat_icons = [], []
                    for yr in _em_years:
                        for ql in _em_qlabels:
                            val = _em_quarterly.get(yr, {}).get(ql)
                            if val is not None:
                                label = f"{ql[:2]} {yr}"
                                _q_bar_labels.append(label)
                                _q_bar_actuals.append(val)
                                est = _em_estimates.get(yr, {}).get(ql)
                                _q_bar_estimates.append(est)
                                beat = _em_beats.get(yr, {}).get(ql)
                                if beat is True:
                                    _q_bar_colors.append("#00CC44")
                                    _q_bar_beat_icons.append("✓ BEAT")
                                elif beat is False:
                                    _q_bar_colors.append("#FF4444")
                                    _q_bar_beat_icons.append("✗ MISS")
                                else:
                                    _q_bar_colors.append("#FF8C00")
                                    _q_bar_beat_icons.append("")
                    if _q_bar_labels:
                        fig_q_bar = dark_fig(260)
                        # Estimate bars (background)
                        est_vals_clean = [e if e is not None else 0 for e in _q_bar_estimates]
                        if any(e > 0 for e in est_vals_clean):
                            fig_q_bar.add_trace(go.Bar(
                                name="Estimate", x=_q_bar_labels, y=est_vals_clean,
                                marker=dict(color="rgba(255,255,255,0.06)", line=dict(color="#333", width=1)),
                                hovertext=[f"Est: ${e:.2f}" if e else "—" for e in est_vals_clean],
                                hoverinfo="text",
                            ))
                        # Actual bars (foreground)
                        fig_q_bar.add_trace(go.Bar(
                            name="Actual", x=_q_bar_labels, y=_q_bar_actuals,
                            marker=dict(color=_q_bar_colors, line=dict(width=0), opacity=0.9),
                            text=[f"${v:.2f}" for v in _q_bar_actuals],
                            textposition="outside", textfont=dict(size=7, color="#888"),
                            hovertext=[f"Actual: ${a:.2f} | {b}" for a, b in zip(_q_bar_actuals, _q_bar_beat_icons)],
                            hoverinfo="text",
                        ))
                        fig_q_bar.update_layout(
                            barmode="overlay",
                            margin=dict(l=40, r=10, t=30, b=40), height=260,
                            title=dict(text="QUARTERLY EPS — ACTUAL vs ESTIMATE  (🟢 Beat · 🔴 Miss)", font=dict(size=10, color="#FF6600"), x=0),
                            xaxis=dict(color="#555", tickfont=dict(size=7, color="#666"), tickangle=-45, showgrid=False),
                            yaxis=dict(color="#555", tickfont=dict(size=9), gridcolor="#111", title=None, tickprefix="$"),
                            legend=dict(font=dict(size=8, color="#888"), bgcolor="rgba(0,0,0,0)",
                                        orientation="h", x=0, y=1.08),
                            showlegend=True,
                        )
                        st.plotly_chart(fig_q_bar, use_container_width=True, config={'displayModeBar': False})

                    # ── Revenue trend chart ──
                    if _em_revenue_q:
                        _rev_labels, _rev_values = [], []
                        for yr in _em_years:
                            for ql in _em_qlabels:
                                val = _em_revenue_q.get(yr, {}).get(ql)
                                if val is not None:
                                    _rev_labels.append(f"{ql[:2]} {yr}")
                                    _rev_values.append(val / 1e9)
                        if _rev_labels:
                            fig_rev = dark_fig(200)
                            fig_rev.add_trace(go.Scatter(
                                x=_rev_labels, y=_rev_values, mode="lines+markers+text",
                                line=dict(color="#FF6600", width=2),
                                marker=dict(size=6, color="#FF6600", line=dict(width=1, color="#000")),
                                text=[f"${v:.1f}B" for v in _rev_values],
                                textposition="top center", textfont=dict(size=7, color="#FF8C00"),
                                hoverinfo="text",
                            ))
                            fig_rev.update_layout(
                                margin=dict(l=40, r=10, t=30, b=40), height=200,
                                title=dict(text="QUARTERLY REVENUE TREND ($B)", font=dict(size=10, color="#FF6600"), x=0),
                                xaxis=dict(color="#555", tickfont=dict(size=7, color="#666"), tickangle=-45, showgrid=False),
                                yaxis=dict(color="#555", tickfont=dict(size=9), gridcolor="#111", title=None, tickprefix="$", ticksuffix="B"),
                            )
                            st.plotly_chart(fig_rev, use_container_width=True, config={'displayModeBar': False})
                    st.markdown('</div>', unsafe_allow_html=True)

                with _em_val_col:
                    st.markdown('<div class="em-container">', unsafe_allow_html=True)
                    st.markdown('<div style="color:#FF6600;font-size:10px;letter-spacing:1px;font-family:monospace;font-weight:700;margin-bottom:8px">VALUATION MULTIPLES</div>', unsafe_allow_html=True)
                    if _em_vals:
                        val_html = '<table class="em-val-table"><thead><tr><th></th><th>Last 4Q</th><th>Forward</th></tr></thead><tbody>'
                        for metric_name, periods in _em_vals.items():
                            last4q = periods.get("Last 4Q", "—")
                            fwd = periods.get("Forward", "—")
                            def _val_color(v_str):
                                try:
                                    v = float(v_str.replace("x", ""))
                                    if v < 15: return "#00CC44"
                                    elif v < 25: return "#FF8C00"
                                    else: return "#FF6600"
                                except:
                                    return "#888"
                            l_color = _val_color(last4q)
                            f_color = _val_color(fwd)
                            val_html += f'<tr><td>{metric_name}</td><td style="color:{l_color}">{last4q}</td><td style="color:{f_color}">{fwd}</td></tr>'
                        val_html += "</tbody></table>"
                        st.markdown(val_html, unsafe_allow_html=True)
                    else:
                        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Valuation data unavailable.</p>', unsafe_allow_html=True)

                    st.markdown('<div style="margin-top:16px;color:#FF6600;font-size:10px;letter-spacing:1px;font-family:monospace;font-weight:700;margin-bottom:6px">EPS GROWTH SUMMARY</div>', unsafe_allow_html=True)
                    for yr in _em_years:
                        g_val = _em_ann_growth.get(yr)
                        if g_val is not None:
                            g_color = "#00CC44" if g_val >= 0 else "#FF4444"
                            g_icon = "▲" if g_val >= 0 else "▼"
                            # Revenue growth alongside
                            r_val = _em_ann_rev_growth.get(yr)
                            rev_str = ""
                            if r_val is not None:
                                r_color = "#00CC44" if r_val >= 0 else "#FF4444"
                                rev_str = f' <span style="color:#555">|</span> <span style="color:{r_color};font-size:9px">Rev {r_val:+.1f}%</span>'
                            st.markdown(
                                f'<div style="display:flex;justify-content:space-between;padding:3px 0;font-family:monospace;font-size:11px;border-bottom:1px solid #0D0D0D">'
                                f'<span style="color:#888">FY {yr}</span>'
                                f'<span style="color:{g_color};font-weight:700">{g_icon} {g_val:+.1f}%{rev_str}</span></div>',
                                unsafe_allow_html=True)

                    # ── Company info card ──
                    _mcap = _em_data.get("market_cap", 0)
                    _mcap_str = f"${_mcap/1e12:.2f}T" if _mcap >= 1e12 else (f"${_mcap/1e9:.1f}B" if _mcap >= 1e9 else (f"${_mcap/1e6:.0f}M" if _mcap >= 1e6 else "—"))
                    _t_eps = _em_data.get("trailing_eps", 0)
                    _f_eps = _em_data.get("forward_eps", 0)
                    st.markdown(
                        f'<div style="margin-top:14px;padding:10px;background:#0A0A0A;border:1px solid #1A1A1A;border-radius:3px;font-family:monospace;font-size:10px">'
                        f'<div style="color:#FF6600;font-weight:700;margin-bottom:4px">{_em_company}</div>'
                        f'<div style="color:#888">Currency: {_em_currency} · FY End: Mo {_em_data["fiscal_end_month"]}</div>'
                        f'<div style="color:#00CC44;margin-top:4px">Price: ${_em_data.get("price", 0):,.2f}</div>'
                        f'<div style="color:#888;margin-top:2px">Mkt Cap: {_mcap_str}</div>'
                        f'<div style="color:#888;margin-top:2px">TTM EPS: <span style="color:#CCC">${_t_eps:.2f}</span> · Fwd EPS: <span style="color:#CCC">${_f_eps:.2f}</span></div>'
                        f'<div style="margin-top:6px;padding-top:6px;border-top:1px solid #1A1A1A">'
                        f'<span style="color:{_beat_rate_c};font-weight:700">Beat Rate: {_em_beat_rate:.0f}%</span>'
                        f' · <span style="color:{_streak_c}">{_streak_txt}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True)
                        
                    _analyst_targets = _em_data.get("analyst_targets", [])
                    if _analyst_targets:
                        at_html = '<div style="margin-top:14px;padding:10px;background:#0A0A0A;border:1px solid #1A1A1A;border-radius:3px;font-family:monospace;font-size:10px">'
                        at_html += '<div style="color:#00AAFF;font-weight:700;margin-bottom:6px">TOP ANALYST TARGETS <span style="font-weight:100;color:#555;font-size:8px">(Track Record)</span></div>'
                        for tg in _analyst_targets:
                            firm_str = tg["firm"][:14] + "…" if len(tg["firm"]) > 15 else tg["firm"]
                            tgt_val = tg["target"]
                            action = tg["action"]
                            action_str = f' <span style="color:#555">·</span> <span style="color:#888">{action}</span>' if action else ""
                            c_price = _em_data.get("price", 0)
                            color = "#00CC44" if (c_price > 0 and tgt_val > c_price) else ("#FF4444" if (c_price > 0 and tgt_val < c_price) else "#FF8C00")
                            at_html += f'<div style="display:flex;justify-content:space-between;margin-top:4px"><span style="color:#CCC">{firm_str}{action_str}</span><span style="color:{color};font-weight:700">${tgt_val:,.2f}</span></div>'
                        at_html += '</div>'
                        st.markdown(at_html, unsafe_allow_html=True)
                        
                    st.markdown('</div>', unsafe_allow_html=True)

            # ═══════════════════════════════════════════════════════
            # VISUAL MARGIN EXPANSION CHART (Feature 12)
            # ═══════════════════════════════════════════════════════
            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
            st.markdown(f'<div class="bb-ph">📊 MARGIN EXPANSION — {et}</div>', unsafe_allow_html=True)
            with st.spinner("Loading margin data…"):
                _margin_data = get_margin_chart_data(et)

            if _margin_data:
                _m_labels = [d["quarter"][:10] for d in _margin_data]
                _m_rev = [d["revenue_b"] for d in _margin_data]
                _m_gm = [d["gross_margin"] for d in _margin_data]
                _m_om = [d["op_margin"] for d in _margin_data]
                _m_nm = [d["net_margin"] for d in _margin_data]

                fig_margin = dark_fig(300)
                # Revenue bars on primary axis
                fig_margin.add_trace(go.Bar(
                    x=_m_labels, y=_m_rev, name="Revenue ($B)",
                    marker=dict(color="rgba(255,102,0,0.15)", line=dict(color="#FF6600", width=1)),
                    hovertext=[f"Rev: ${r:.1f}B" for r in _m_rev], hoverinfo="text",
                ))
                # Margin lines on secondary axis
                if any(v is not None for v in _m_gm):
                    fig_margin.add_trace(go.Scatter(
                        x=_m_labels, y=_m_gm, name="Gross Margin",
                        mode="lines+markers", yaxis="y2",
                        line=dict(color="#00CC44", width=2), marker=dict(size=5),
                    ))
                if any(v is not None for v in _m_om):
                    fig_margin.add_trace(go.Scatter(
                        x=_m_labels, y=_m_om, name="Op Margin",
                        mode="lines+markers", yaxis="y2",
                        line=dict(color="#00AAFF", width=2), marker=dict(size=5),
                    ))
                if any(v is not None for v in _m_nm):
                    fig_margin.add_trace(go.Scatter(
                        x=_m_labels, y=_m_nm, name="Net Margin",
                        mode="lines+markers", yaxis="y2",
                        line=dict(color="#FF8C00", width=2), marker=dict(size=5),
                    ))
                fig_margin.update_layout(
                    margin=dict(l=40, r=50, t=30, b=40), height=300,
                    title=dict(text=f"{et} MARGIN EXPANSION + REVENUE", font=dict(size=10, color="#FF6600"), x=0),
                    xaxis=dict(color="#555", tickfont=dict(size=7), tickangle=-45, showgrid=False),
                    yaxis=dict(color="#555", gridcolor="#111", tickprefix="$", ticksuffix="B", title=None),
                    yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix="%",
                                tickfont=dict(size=8, color="#888"), title=None),
                    legend=dict(font=dict(size=8, color="#888"), bgcolor="rgba(0,0,0,0)",
                                orientation="h", x=0, y=1.08),
                    barmode="overlay",
                )
                st.plotly_chart(fig_margin, use_container_width=True)
            else:
                st.markdown(f'<p style="color:#555;font-family:monospace;font-size:11px">Margin data unavailable for {et}.</p>', unsafe_allow_html=True)

            # ═══════════════════════════════════════════════════════
            # AI-POWERED GUIDANCE SUMMARY (Feature 11)
            # ═══════════════════════════════════════════════════════
            if st.session_state.get("gemini_key"):
                st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
                st.markdown(f'<div class="bb-ph">🤖 AI GUIDANCE SUMMARY — {et}</div>', unsafe_allow_html=True)
                with st.spinner(f"Generating AI summary for {et}…"):
                    _ai_summary = get_ai_earnings_summary(
                        et,
                        gemini_api_key=st.session_state.gemini_key,
                        finnhub_key=st.session_state.get("finnhub_key"),
                        newsapi_key=st.session_state.get("newsapi_key"),
                    )
                if _ai_summary:
                    _summary_text = _ai_summary["summary"].replace("\n", "<br>")
                    st.markdown(
                        f'<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;'
                        f'padding:14px 16px;font-family:monospace;font-size:11px;color:#CCC;line-height:1.8">'
                        f'<div style="color:#FF6600;font-size:10px;letter-spacing:1px;margin-bottom:8px">'
                        f'⚡ SENTINEL AI ({_ai_summary["news_count"]} news sources analyzed)</div>'
                        f'{_summary_text}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">AI summary unavailable. Check Gemini key.</p>', unsafe_allow_html=True)

            # ── Stock-specific news (after margin + AI) ──
            st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
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
                st.markdown(f'<div class="chat-ai">⚡ SENTINEL<br><br>{format_gemini_msg(msg["content"])}</div>', unsafe_allow_html=True)

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
                    # Use enriched context (with geo headlines + macro rates) for /brief and /geo
                    _is_brief_geo = cmd.startswith("/brief") or cmd.startswith("/geo")
                    _ctx = build_brief_context() if _is_brief_geo else market_snapshot_str()
                    placeholder = st.empty()
                    resp_text = ""
                    for chunk in gemini_response(cmd, st.session_state.chat_history[:-1], _ctx):
                        resp_text += chunk
                        placeholder.markdown(f'<div class="chat-ai">⚡ SENTINEL<br><br>{format_gemini_msg(resp_text)}</div>', unsafe_allow_html=True)
                    st.session_state.chat_history.append({"role":"assistant","content":resp_text})
                    st.rerun()

        if st.button("🗑 CLEAR CHAT"):
            st.session_state.chat_history = []; st.rerun()

        if (send or user_input) and user_input:
            st.session_state.chat_history.append({"role":"user","content":user_input})
            # Use enriched context (geo headlines + macro rates) for /brief and /geo commands
            _ui_lower = user_input.strip().lower()
            _is_brief_geo = _ui_lower.startswith("/brief") or _ui_lower.startswith("/geo")
            _ctx = build_brief_context() if _is_brief_geo else market_snapshot_str()
            placeholder = st.empty()
            resp_text = ""
            for chunk in gemini_response(user_input, st.session_state.chat_history[:-1], _ctx):
                resp_text += chunk
                placeholder.markdown(f'<div class="chat-ai">⚡ SENTINEL<br><br>{format_gemini_msg(resp_text)}</div>', unsafe_allow_html=True)
            st.session_state.chat_history.append({"role":"assistant","content":resp_text})
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
