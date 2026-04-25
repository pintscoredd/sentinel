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
import numpy as np
from scipy.stats import norm as _norm_dist
from datetime import datetime, timedelta
import pytz

from data_fetchers import (
    _safe_float, _safe_int, _esc, fmt_p, fmt_pct, pct_color, _is_english,
    yahoo_quote, get_futures, get_heatmap_data, multi_quotes,
    fred_series, polymarket_events, polymarket_markets,
    fear_greed_crypto, calc_stock_fear_greed,
    crypto_markets, crypto_global,
    gdelt_news, newsapi_headlines, finnhub_news, finnhub_insider, finnhub_officers, get_yf_ticker,
    options_chain, options_expiries, sector_etfs, top_movers,
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
    smart_money_conviction_buys,
    # ─── New Feature Imports ───
    get_global_indices, get_net_liquidity, get_yield_curve_history,
    get_cross_asset_volatility, get_macro_correlation_matrix,
    get_sector_rrg, get_iv_term_structure, get_gamma_squeeze_scanner,
    get_finnhub_earnings_calendar, get_expected_move,
    get_ai_earnings_summary, get_margin_chart_data,
    get_vix_full, get_spy_history, get_tlt_history,
    # ─── FEAT additions ───
    get_iv_skew, get_rv_iv_spread, get_cot_positioning, get_economic_surprise_index,
    # ─── Macro Sovereign + Stock Fundamentals + News Filter ───
    get_sovereign_10y_yields, get_sovereign_cds_proxy, get_central_bank_rates,
    get_yield_curve_inversions, get_profitability_metrics, get_balance_sheet_metrics,
    filter_market_news, is_market_relevant,
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
import time

PST = pytz.timezone("US/Pacific")
def _update_time_cache():
    t = time.time()
    if t - st.session_state.get("_time_last_update", 0.0) > 1.0:
        now = datetime.now(PST)
        st.session_state._cached_pst = now.strftime("%Y-%m-%d %H:%M PST")
        st.session_state._cached_short = now.strftime("%H:%M:%S")
        st.session_state._time_last_update = t

def now_pst():
    _update_time_cache()
    return st.session_state._cached_pst

def now_short():
    _update_time_cache()
    return st.session_state._cached_short

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
.stSelectbox > div > div,
.stNumberInput > div > div > input {
background: var(--bg2) !important; color: var(--org2) !important;
border: 1px solid var(--muted) !important; border-radius: 0 !important;
font-family: var(--mono) !important; font-size: 12px !important;
}
.stNumberInput > div > div > button,
.stNumberInput button {
background: var(--bg1) !important; color: var(--org) !important;
border: 1px solid var(--muted) !important; border-radius: 0 !important;
font-family: var(--mono) !important; font-size: 13px !important;
font-weight: 700 !important;
}
.stNumberInput > div > div > button:hover,
.stNumberInput button:hover {
background: var(--org) !important; color: var(--blk) !important;
}
/* Force number input container to match selectbox style */
.stNumberInput > div {
background: var(--bg1) !important;
border: 1px solid var(--muted) !important;
border-radius: 0 !important;
}
.stNumberInput > div > div {
background: transparent !important;
border: none !important;
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
from collections import namedtuple

class SecretStr(namedtuple("SecretStr", ["value"])):
    def __repr__(self): return "***"
    def __str__(self): return "***"
    def get_secret_value(self): return self.value
    def __bool__(self): return bool(self.value)

def _get_secret(name, default=""):
    """Try st.secrets with exact name, then lowercase, then uppercase."""
    for k in [name, name.lower(), name.upper()]:
        try:
            val = st.secrets.get(k, None)
            if val:
                return SecretStr(str(val).strip())
        except Exception:
            pass
    # Also try nested [api_keys] section some users set up
    try:
        val = st.secrets.get("api_keys", {}).get(name, None)
        if val:
            return SecretStr(str(val).strip())
    except Exception:
        pass
    return SecretStr(default) if default else SecretStr("")

def _load_watchlist():
    return ["SPY","QQQ","NVDA","AAPL","GLD","TLT","BTC-USD"]

def _save_watchlist(wl):
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
    "master_ticker": "",  # State-preserving ticker across all tabs
}
for k,v in DEFAULTS.items():
    if k not in st.session_state: st.session_state[k]=v

def warm_caches_on_startup(watchlist):
    """Fire-and-forget background cache warming — NOT cached since it spawns threads.
    Uses a module-level guard to ensure it only runs once per process."""
    import threading
    def _warm():
        try:
            get_vix_full()
            sector_etfs()
            get_futures()
            polymarket_events(30)
            multi_quotes(watchlist)
            stat_arb_screener()
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True).start()
    return True

if "_caches_warmed" not in st.session_state:
    warm_caches_on_startup(st.session_state.watchlist)
    st.session_state._caches_warmed = True

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
        ("FRED",          bool(st.session_state.fred_key.get_secret_value()), "FRED_API_KEY"),
        ("Finnhub",       bool(st.session_state.finnhub_key.get_secret_value()), "FINNHUB_API_KEY"),
        ("NewsAPI",       bool(st.session_state.newsapi_key.get_secret_value()), "NEWSAPI_KEY"),
        ("Gemini AI",     bool(st.session_state.gemini_key.get_secret_value()), "GEMINI_API_KEY"),
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

    with st.form("api_key_overrides", clear_on_submit=True):
        _fred_input = st.text_input("FRED API Key", value="", type="password", placeholder="paste key to override…")
        _finnhub_input = st.text_input("Finnhub Key", value="", type="password", placeholder="paste key to override…")
        _cftc_input = st.text_input("CFTC API Key", value="", type="password", placeholder="optional — CSV is free")
        if st.form_submit_button("Update Keys"):
            if _fred_input: st.session_state.fred_key = SecretStr(_fred_input.strip())
            if _finnhub_input: st.session_state.finnhub_key = SecretStr(_finnhub_input.strip())
            if _cftc_input: st.session_state.cftc_key = SecretStr(_cftc_input.strip())
            st.rerun()

    st.markdown('<hr style="border-top:1px solid #222;margin:8px 0">', unsafe_allow_html=True)
    st.markdown('<div style="color:#FF6600;font-size:9px;letter-spacing:2px;font-weight:700">MY CONTEXT</div>', unsafe_allow_html=True)
    st.session_state.macro_theses = st.text_area("Macro theses", value=st.session_state.macro_theses, placeholder="Watching Fed pivot...", height=55)
    st.session_state.geo_watch    = st.text_area("Geo watch",    value=st.session_state.geo_watch,    placeholder="Red Sea, Taiwan...",   height=45)

    # ────────────────────────────────────────────────────────────────
    # 🚨 THRESHOLD ALERTS ENGINE
    # ────────────────────────────────────────────────────────────────
    st.markdown('<hr style="border-top:1px solid #222;margin:8px 0">', unsafe_allow_html=True)

    with st.expander("🚨 THRESHOLD ALERTS", expanded=False):
        st.markdown(
            '<div style="color:#888;font-size:9px;font-family:monospace;margin-bottom:6px">'
            'Set thresholds for VIX, PCR, and individual tickers. Alerts fire as toasts '
            'and optionally POST to your webhook. 5-min cooldown per alert type.</div>',
            unsafe_allow_html=True)

        # Initialize alert state
        if "alert_cooldowns" not in st.session_state:
            st.session_state.alert_cooldowns = {}
        if "alert_vix_threshold" not in st.session_state:
            st.session_state.alert_vix_threshold = 25.0
        if "alert_pcr_threshold" not in st.session_state:
            st.session_state.alert_pcr_threshold = 1.2
        if "alert_tickers" not in st.session_state:
            st.session_state.alert_tickers = ""
        if "alert_ticker_prices" not in st.session_state:
            st.session_state.alert_ticker_prices = ""
        if "alert_webhook_url" not in st.session_state:
            st.session_state.alert_webhook_url = ""
        if "alerts_enabled" not in st.session_state:
            st.session_state.alerts_enabled = False

        st.session_state.alerts_enabled = st.toggle("Enable Alerts", value=st.session_state.alerts_enabled, key="alert_toggle_ui")

        _ac1, _ac2 = st.columns(2)
        with _ac1:
            st.session_state.alert_vix_threshold = st.number_input(
                "VIX Above", value=st.session_state.alert_vix_threshold,
                min_value=5.0, max_value=100.0, step=1.0, format="%.1f",
                key="alert_vix_input",
                help="Alert fires when VIX exceeds this level")
        with _ac2:
            st.session_state.alert_pcr_threshold = st.number_input(
                "PCR Above", value=st.session_state.alert_pcr_threshold,
                min_value=0.1, max_value=5.0, step=0.1, format="%.2f",
                key="alert_pcr_input",
                help="Alert fires when Put/Call Ratio exceeds this level")

        st.session_state.alert_tickers = st.text_input(
            "Price Alert Tickers", value=st.session_state.alert_tickers,
            placeholder="AAPL, TSLA, NVDA", key="alert_tickers_input",
            help="Comma-separated tickers to monitor for price thresholds")

        st.session_state.alert_ticker_prices = st.text_input(
            "Price Thresholds (above)", value=st.session_state.alert_ticker_prices,
            placeholder="200.00, 350.00, 150.00", key="alert_prices_input",
            help="Corresponding price thresholds (above). Match order with tickers above.")

        st.session_state.alert_webhook_url = st.text_input(
            "Webhook URL (optional)", value=st.session_state.alert_webhook_url,
            type="password", placeholder="https://hooks.slack.com/...", key="alert_webhook_input",
            help="Optional webhook URL for external notifications (Slack, Discord, etc.)")

        # Alert status indicator
        if st.session_state.alerts_enabled:
            _active_count = 0
            if st.session_state.alert_vix_threshold > 0: _active_count += 1
            if st.session_state.alert_pcr_threshold > 0: _active_count += 1
            _tkr_list = [t.strip().upper() for t in st.session_state.alert_tickers.split(",") if t.strip()]
            _active_count += len(_tkr_list)
            st.markdown(
                f'<div style="font-family:monospace;font-size:9px;color:#00CC44;padding:4px 0">'
                f'✅ MONITORING {_active_count} THRESHOLD(S) — refreshing every 30s</div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="font-family:monospace;font-size:9px;color:#555;padding:4px 0">'
                '⏸ Alerts paused</div>',
                unsafe_allow_html=True)

    # ── Alert Fragment (runs in background every 30s) ──
    if st.session_state.get("alerts_enabled", False):
        @st.fragment(run_every="30s")
        def _run_alert_monitor():
            import time as _alert_time
            _now = _alert_time.time()
            _cooldown_secs = 300  # 5-minute cooldown

            def _can_fire(alert_key):
                last = st.session_state.alert_cooldowns.get(alert_key, 0)
                return (_alert_time.monotonic() - last) > _cooldown_secs

            def _mark_fired(alert_key):
                st.session_state.alert_cooldowns[alert_key] = _alert_time.monotonic()

            def _send_webhook(msg):
                url = st.session_state.get("alert_webhook_url", "")
                if url:
                    try:
                        import requests
                        import logging
                        if url.startswith("http://"):
                            logging.getLogger("sentinel.app").warning("Webhook URL is non-HTTPS. Transmitting payload in clear text.")
                        requests.post(url, json={"text": msg, "source": "Sentinel Terminal"}, timeout=5)
                    except Exception:
                        pass

            _alerts_fired = []

            # VIX check
            try:
                _v = get_vix_full()
                if _v and _v[0] and _v[0] > st.session_state.alert_vix_threshold:
                    if _can_fire("vix"):
                        _msg = f"🚨 VIX ALERT: {_v[0]:.2f} > {st.session_state.alert_vix_threshold:.1f}"
                        st.toast(_msg, icon="🔴")
                        _send_webhook(_msg)
                        _mark_fired("vix")
                        _alerts_fired.append(_msg)
            except Exception:
                pass

            # PCR check
            try:
                _0c, _ = fetch_0dte_chain("SPY") if bool(_get_secret("ALPACA_API_KEY")) else (None, None)
                _pcr_val = compute_pcr(_0c) if _0c else None
                if _pcr_val is None:
                    _, _cboe_o = fetch_cboe_gex("SPX")
                    _pcr_val = compute_cboe_pcr(_cboe_o)
                if _pcr_val and _pcr_val > st.session_state.alert_pcr_threshold:
                    if _can_fire("pcr"):
                        _msg = f"🚨 PCR ALERT: {_pcr_val:.2f} > {st.session_state.alert_pcr_threshold:.2f}"
                        st.toast(_msg, icon="📊")
                        _send_webhook(_msg)
                        _mark_fired("pcr")
                        _alerts_fired.append(_msg)
            except Exception:
                pass

            # Ticker price checks
            _tkrs = [t.strip().upper() for t in st.session_state.get("alert_tickers", "").split(",") if t.strip()]
            _prices = st.session_state.get("alert_ticker_prices", "").split(",")
            for i, t in enumerate(_tkrs):
                try:
                    _thresh = float(_prices[i].strip()) if i < len(_prices) and _prices[i].strip() else None
                    if _thresh is None:
                        continue
                    _q = yahoo_quote(t)
                    if _q and _q["price"] > _thresh:
                        _ak = f"ticker_{t}"
                        if _can_fire(_ak):
                            _msg = f"🚨 {t} PRICE ALERT: ${_q['price']:.2f} > ${_thresh:.2f}"
                            st.toast(_msg, icon="💰")
                            _send_webhook(_msg)
                            _mark_fired(_ak)
                            _alerts_fired.append(_msg)
                except Exception:
                    continue

        _run_alert_monitor()


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

tabs = st.tabs(["BRIEF","MARKETS","OPTIONS","MACRO","CRYPTO","POLYMARKET","GEO","EARNINGS","SENTINEL AI"])

# ════════════════════════════════════════════════════════════════════
# TAB 0 — MORNING BRIEF
# ════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="bb-ph">⚡ SENTINEL MORNING BRIEF</div>', unsafe_allow_html=True)

    @st.fragment(run_every="60s")
    def render_morning_brief_header():
        ref_col, mkt_col = st.columns([1, 1])
        with ref_col:
            if st.button("↺ REFRESH ALL DATA"):
                try: multi_quotes.clear()
                except: pass
                try: get_vix_full.clear()
                except: pass
                try: get_futures.clear()
                except: pass
                st.rerun()
            st.markdown(f'<div style="color:#888;font-size:10px;margin-top:4px">Last updated: {now_pst()}</div>', unsafe_allow_html=True)
        with mkt_col:
            mkt_status, mkt_color, mkt_detail = is_market_open()
            st.markdown(
                f'<div style="text-align:right;font-family:monospace;padding:4px 0">'
                f'<span style="color:{mkt_color};font-size:14px;font-weight:900">● {mkt_status}</span>'
                f' <span style="color:#555;font-size:10px">{mkt_detail}</span></div>',
                unsafe_allow_html=True)

        # Order: SPX, SPY, DOW, RUSSELL, USD INDEX, GOLD, 10Y YIELD, WTI CRUDE, BTC
        KEY_T_ORDERED = [
            ("^SPX",     "SPX"),
            ("SPY",      "S&P 500"),
            ("DIA",      "DOW JONES"),
            ("IWM",      "RUSSELL 2K"),
            ("DX-Y.NYB", "USD INDEX"),
            ("GLD",      "GOLD"),
            ("^TNX",     "10Y YIELD"),
            ("CL=F",     "WTI CRUDE"),
            ("BTC-USD",  "BITCOIN"),
        ]
        _strip_tickers = [t for t, _ in KEY_T_ORDERED]
        qs = multi_quotes(_strip_tickers)
        _strip_map = {q["ticker"]: q for q in qs} if qs else {}
        if qs:
            cols = st.columns(len(KEY_T_ORDERED))
            for col, (tkr_s, lbl_s) in zip(cols, KEY_T_ORDERED):
                q = _strip_map.get(tkr_s)
                if not q:
                    continue
                _pct = q["pct"]
                _chg = q["change"]
                _up = _pct >= 0
                _c = "#00CC44" if _up else "#FF4444"
                _arr = "↑" if _up else "↓"
                _sign = "+" if _up else ""
                with col:
                    st.markdown(
                        f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #FF6600;'
                        f'padding:10px 10px 8px 10px;font-family:monospace;min-height:85px">'
                        f'<div style="color:#888;font-size:9px;letter-spacing:1px;margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{lbl_s}</div>'
                        f'<div style="color:#FFF;font-size:16px;font-weight:700;white-space:nowrap">{fmt_p(q["price"])}</div>'
                        f'<div style="color:{_c};font-size:10px;font-weight:600;margin-top:4px">'
                        f'{_arr} {_sign}{_pct:.2f}% ({_sign}{_chg:.2f})</div></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#FF4444;font-size:11px;font-family:monospace">Quotes unavailable. Rate limits or network error.</div>', unsafe_allow_html=True)
            
    render_morning_brief_header()

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
    L, R = st.columns([3,2])

    with L:
        st.markdown('<div class="bb-ph">⚡ MARKET SENTIMENT</div>', unsafe_allow_html=True)
        s1,s2,s3 = st.columns(3)
        
        vix_info = get_vix_full()
        v = vix_info[0] if vix_info else None
        
        vix_q = yahoo_quote("^VIX")
        with s1:
            if v:
                lbl = "LOW FEAR" if v<15 else ("MODERATE" if v<25 else ("HIGH FEAR" if v<35 else "PANIC"))
                vix_chg = f"{vix_q['pct']:+.2f}%" if vix_q else ""
                vix_chg_c = pct_color(vix_q['pct']) if vix_q else "#888"
                # VIX help tooltip added via markdown (can't use st.metric help here due to custom HTML)
                st.markdown(f'<div class="fg-gauge"><div class="fg-num">{v:.2f}</div><div class="fg-lbl" style="color:#FF8C00">{lbl}</div><div style="color:{vix_chg_c};font-size:13px;font-weight:700;margin-top:4px">{vix_chg}</div><div style="color:#555;font-size:8px;margin-top:2px">VIX</div></div>', unsafe_allow_html=True)
        sfg_val, sfg_lbl = calc_stock_fear_greed()
        with s2:
            if sfg_val:
                sfg_c = "#00CC44" if sfg_val>=55 else ("#FF4444" if sfg_val<35 else "#FF8C00")
                st.markdown(f'<div class="fg-gauge"><div class="fg-num" style="color:{sfg_c}">{sfg_val}</div><div class="fg-lbl" style="color:{sfg_c}">{sfg_lbl}</div><div style="color:#555;font-size:8px;margin-top:2px">STOCK MARKET F&G</div></div>', unsafe_allow_html=True)
        with s3:
            vix_val, vix_pct, posture = vix_info if vix_info else (None, None, None)
            if vix_val:
                pc = {"RISK-ON": "#00CC44", "NEUTRAL": "#FF8C00", "RISK-OFF": "#FF4444"}.get(posture[:8] if posture else "NEUTRAL", "#FF8C00")
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
                    f'font-size:13px;padding:5px 0">{_esc(q["ticker"])}</div>',
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
                if st.button("✕", key=f"rm_{q['ticker']}", help=f"Remove {q['ticker']}"):
                    st.session_state.watchlist = [x for x in st.session_state.watchlist if x!=q["ticker"]]
                    _save_watchlist(st.session_state.watchlist)
                    st.rerun()

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
            query = st.session_state.geo_watch if st.session_state.geo_watch else "geopolitical conflict oil market"
            geo_arts = gdelt_news(query, 8)
        if geo_arts:
            seen_titles = set()
            for art in geo_arts[:8]:
                t=art.get("title","")[:90]; u=art.get("url","#"); dom=art.get("domain","GDELT"); sd=art.get("seendate","")
                if not is_market_relevant(t, dom): continue  # filter fluff
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
        # Stable key prevents widget recreation when master_ticker changes (double-type bug)
        def _on_flash_change():
            val = st.session_state.get("flash_main_ticker", "").upper().strip()
            if val:
                st.session_state.master_ticker = val

        flash_ticker = st.text_input(
            "⚡ TICKER LOOKUP",
            placeholder="NVDA, AAPL, TSLA, SPY, GLD…", key="flash_main_ticker",
            on_change=_on_flash_change,
            help="Type a ticker symbol to see price, chart, options, insider trades, and short data. This ticker persists across tabs.")

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


            # --- START: Financials & Market Data ---
            st.markdown('<div class="bb-ph" style="margin-top:12px">🏦 FINANCIALS & COMPANY OVERVIEW</div>', unsafe_allow_html=True)
            with st.spinner("Loading financials..."):
                try:
                    yf_tk = get_yf_ticker(tkr)
                    _q = yahoo_quote(tkr) or {}
                    
                    # Try to fetch extended info, but default to empty dict if Yahoo 401 blocks it
                    info = {}
                    try:
                        if yf_tk:
                            info = yf_tk.info
                            if not isinstance(info, dict): info = {}
                    except Exception:
                        pass
                    
                    # Fallback: populate from fast_info when .info is empty/blocked
                    fi = None
                    if yf_tk:
                        try:
                            fi = yf_tk.fast_info
                        except Exception:
                            fi = None
                    
                    if fi and not info.get('marketCap'):
                        info.setdefault('marketCap', getattr(fi, 'market_cap', None))
                    if fi and not info.get('trailingPE'):
                        # Compute from price & EPS if available
                        _fi_price = getattr(fi, 'last_price', None)
                        _fi_eps = getattr(fi, 'earnings_per_share', None) or info.get('trailingEps')
                        if _fi_price and _fi_eps and _fi_eps != 0:
                            info.setdefault('trailingPE', round(_fi_price / _fi_eps, 2))
                    if fi:
                        info.setdefault('fiftyTwoWeekHigh', getattr(fi, 'year_high', None))
                        info.setdefault('fiftyTwoWeekLow', getattr(fi, 'year_low', None))
                        info.setdefault('averageVolume', getattr(fi, 'three_month_average_volume', None))
                        info.setdefault('currentPrice', getattr(fi, 'last_price', None))
                        info.setdefault('previousClose', getattr(fi, 'previous_close', None))
                    
                    _mc = info.get('marketCap') or _q.get('cap')
                    _mc_str = (f"${_mc/1e12:.2f}T" if _mc and _mc >= 1e12 else f"${_mc/1e9:.2f}B" if _mc and _mc > 0 else "N/A")
                    
                    _pe = info.get('trailingPE') or _q.get('pe') or 'N/A'
                    _pe_str = f"{_pe:.2f}" if isinstance(_pe, (int, float)) and _pe > 0 else str(_pe)
                    
                    _div = info.get('dividendYield') or _q.get('div') or 'N/A'
                    _div_str = f"{_div*100:.2f}%" if isinstance(_div, (int, float)) and _div > 0 else "N/A" if _div == 'N/A' else str(_div)
                    
                    _beta = info.get('beta', 'N/A')
                    _beta_str = f"{_beta:.2f}" if isinstance(_beta, (int, float)) else str(_beta)
                    
                    _margin = info.get('profitMargins', 'N/A')
                    _margin_str = f"{_margin*100:.2f}%" if isinstance(_margin, (int, float)) else str(_margin)
                    
                    _sector   = info.get('sector', 'N/A')
                    _industry = info.get('industry', 'N/A')
                    _desc     = info.get('longBusinessSummary', '')
                    _52wh     = info.get('fiftyTwoWeekHigh')
                    _52wl     = info.get('fiftyTwoWeekLow')
                    _avg_vol  = info.get('averageVolume')
                    _fwd_pe   = info.get('forwardPE')
                    _ps       = info.get('priceToSalesTrailing12Months')
                    _ev_ebitda= info.get('enterpriseToEbitda')
                    _rev      = info.get('totalRevenue')
                    _eps      = info.get('trailingEps')

                    # ── Company description ABOVE metrics ──
                    if _desc:
                        import re as _re
                        _sents = _re.split(r'(?<=[.!?])\s+', _desc.strip())
                        _short_desc = ' '.join(_sents[:4])
                        st.markdown(
                            f'<div style="color:#AAA;font-size:11px;margin-bottom:10px;line-height:1.55;font-family:monospace;'
                            f'background:#050505;border-left:3px solid #FF6600;padding:8px 12px">{_esc(_short_desc)}</div>',
                            unsafe_allow_html=True)

                    if _sector != 'N/A' or _industry != 'N/A':
                        st.markdown(f'<div style="color:#888;font-size:10px;font-family:monospace;margin-bottom:6px">Sector: <span style="color:#FF8C00">{_sector}</span> &nbsp;|&nbsp; Industry: <span style="color:#CCC">{_industry}</span></div>', unsafe_allow_html=True)

                    # Row 1: core metrics
                    f1, f2, f3, f4, f5 = st.columns(5)
                    f1.metric("Market Cap", _mc_str)
                    f2.metric("P/E (Trail)", _pe_str)
                    f3.metric("P/E (Fwd)", f"{_fwd_pe:.2f}" if isinstance(_fwd_pe,(int,float)) and _fwd_pe>0 else "N/A")
                    f4.metric("EPS", f"${_eps:.2f}" if isinstance(_eps,(int,float)) else "N/A")
                    f5.metric("Beta", _beta_str)

                    # Row 2: extended
                    f6, f7, f8, f9, f10 = st.columns(5)
                    f6.metric("Div Yield", _div_str)
                    f7.metric("Profit Margin", _margin_str)
                    f8.metric("EV/EBITDA", f"{_ev_ebitda:.1f}x" if isinstance(_ev_ebitda,(int,float)) and _ev_ebitda>0 else "N/A")
                    f9.metric("P/S Ratio", f"{_ps:.2f}" if isinstance(_ps,(int,float)) and _ps>0 else "N/A")
                    def _auto_scale_rev(v):
                        if not v: return "N/A"
                        if v >= 1e12: return f"${v/1e12:.2f}T"
                        if v >= 1e9:  return f"${v/1e9:.2f}B"
                        if v >= 1e6:  return f"${v/1e6:.0f}M"
                        return f"${v:,.0f}"
                    f10.metric("Revenue (TTM)", _auto_scale_rev(_rev))

                    # Row 3: 52w range + volume
                    f11, f12, f13 = st.columns(3)
                    f11.metric("52W High", f"${_52wh:,.2f}" if isinstance(_52wh,(int,float)) else "N/A")
                    f12.metric("52W Low",  f"${_52wl:,.2f}" if isinstance(_52wl,(int,float)) else "N/A")
                    _avg_vol_str = (f"{_avg_vol/1e6:.1f}M" if _avg_vol and _avg_vol>=1e6 else f"{_avg_vol/1e3:.0f}K" if _avg_vol else "N/A")
                    f13.metric("Avg Volume", _avg_vol_str)

                    if _sector != 'N/A' or _industry != 'N/A':
                        pass  # sector/industry already shown above metrics
                except Exception as e:
                    st.markdown('<div style="color:#555;font-size:11px">Financials temporarily unavailable.</div>', unsafe_allow_html=True)
            # --- END: Financials ---

            # ── PROFITABILITY PANEL ─────────────────────────────────────────
            st.markdown('<div class="bb-ph" style="margin-top:12px">📊 PROFITABILITY</div>', unsafe_allow_html=True)
            with st.spinner("Loading profitability metrics…"):
                _prof = get_profitability_metrics(tkr)
            if _prof:
                def _fmt_margin(v, label=""):
                    if v is None:
                        return '<span style="color:#333">—</span>'
                    pct = v * 100
                    c = "#00CC44" if pct > 0 else "#FF4444"
                    return f'<span style="color:{c};font-weight:700">{pct:.1f}%</span>'

                _prof_html = (
                    '<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #00AAFF;'
                    'padding:14px 16px;margin:4px 0;font-family:monospace">'
                    '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;text-align:center">'
                )
                _prof_items = [
                    ("GROSS MARGIN",    _prof.get("gross_margin")),
                    ("OPERATING MARGIN", _prof.get("op_margin")),
                    ("EBITDA MARGIN",   _prof.get("ebitda_margin")),
                    ("NET MARGIN",      _prof.get("net_margin")),
                    ("ROA",             _prof.get("roa")),
                    ("ROE",             _prof.get("roe")),
                ]
                for plbl, pval in _prof_items:
                    _prof_html += (
                        f'<div>'
                        f'<div style="color:#555;font-size:8px;letter-spacing:1px;margin-bottom:6px">{plbl}</div>'
                        f'<div style="font-size:16px;font-weight:700">{_fmt_margin(pval)}</div>'
                        f'</div>'
                    )
                _prof_html += '</div></div>'
                st.markdown(_prof_html, unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#555;font-size:11px;font-family:monospace">Profitability data unavailable.</div>', unsafe_allow_html=True)

            # ── BALANCE SHEET PANEL ─────────────────────────────────────────
            st.markdown('<div class="bb-ph" style="margin-top:12px">🏦 BALANCE SHEET</div>', unsafe_allow_html=True)
            with st.spinner("Loading balance sheet…"):
                _bs = get_balance_sheet_metrics(tkr)
            if _bs:
                def _fmt_bs_val(v, label=""):
                    if v is None:
                        return '<span style="color:#333">—</span>'
                    if label in ("CURRENT RATIO", "QUICK RATIO"):
                        c = "#00CC44" if v >= 1.5 else "#FF8C00" if v >= 1.0 else "#FF4444"
                        return f'<span style="color:{c};font-weight:700">{v:.2f}x</span>'
                    if label == "DEBT/EQUITY":
                        c = "#00CC44" if v < 100 else "#FF8C00" if v < 200 else "#FF4444"
                        return f'<span style="color:{c};font-weight:700">{v:.1f}%</span>'
                    # Money values
                    abs_v = abs(v)
                    if abs_v >= 1e12:
                        s = f"${v/1e12:.2f}T"
                    elif abs_v >= 1e9:
                        s = f"${v/1e9:.2f}B"
                    elif abs_v >= 1e6:
                        s = f"${v/1e6:.0f}M"
                    else:
                        s = f"${v:,.0f}"
                    c = "#00CC44" if v >= 0 else "#FF4444"
                    return f'<span style="color:{c};font-weight:700">{s}</span>'

                _bs_html = (
                    '<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #FF8C00;'
                    'padding:14px 16px;margin:4px 0;font-family:monospace">'
                    '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;text-align:center">'
                )
                _bs_items = [
                    ("TOTAL CASH",    _bs.get("total_cash"),    "TOTAL CASH"),
                    ("TOTAL DEBT",    _bs.get("total_debt"),    "TOTAL DEBT"),
                    ("NET CASH/DEBT", _bs.get("net_cash_debt"), "NET CASH/DEBT"),
                    ("DEBT/EQUITY",   _bs.get("de_ratio"),      "DEBT/EQUITY"),
                    ("CURRENT RATIO", _bs.get("current_ratio"), "CURRENT RATIO"),
                    ("QUICK RATIO",   _bs.get("quick_ratio"),   "QUICK RATIO"),
                ]
                for blbl, bval, bkey in _bs_items:
                    _bs_html += (
                        f'<div>'
                        f'<div style="color:#555;font-size:8px;letter-spacing:1px;margin-bottom:6px">{blbl}</div>'
                        f'<div style="font-size:16px;font-weight:700">{_fmt_bs_val(bval, bkey)}</div>'
                        f'</div>'
                    )
                _bs_html += '</div></div>'
                st.markdown(_bs_html, unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#555;font-size:11px;font-family:monospace">Balance sheet data unavailable.</div>', unsafe_allow_html=True)

            # ── QUARTERLY FINANCIALS (Markets Tab) ─────────────────────────
            st.markdown('<div class="bb-ph" style="margin-top:12px">📊 QUARTERLY FINANCIALS</div>', unsafe_allow_html=True)
            try:
                with st.spinner("Loading quarterly financials…"):
                    _mkt_fin_data = get_full_financials(tkr)
                if _mkt_fin_data:
                    _mkt_qs = sorted(_mkt_fin_data.keys(), reverse=True)
                    def _mkt_fmt_val(v, unit="auto"):
                        if v is None: return '<span style="color:#333">—</span>'
                        if unit == "%": return f'<span style="color:#CCC">{v:.1f}%</span>'
                        if unit == "raw": return f'<span style="color:#CCC">{v:.2f}</span>'
                        abs_v = abs(v)
                        if abs_v >= 1e12:   v_d, sfx = v/1e12, "T"
                        elif abs_v >= 1e9:  v_d, sfx = v/1e9,  "B"
                        elif abs_v >= 1e6:  v_d, sfx = v/1e6,  "M"
                        elif abs_v >= 1e3:  v_d, sfx = v/1e3,  "K"
                        else:               v_d, sfx = v,       ""
                        c = "#00CC44" if v >= 0 else "#FF4444"
                        return f'<span style="color:{c};font-weight:600">{v_d:,.1f}{sfx}</span>'
                    _MKT_METRICS = [
                        ("Revenue",      "revenue",       "auto"),
                        ("Gross Profit", "gross_profit",  "auto"),
                        ("Op. Income",   "op_income",     "auto"),
                        ("Net Income",   "net_income",    "auto"),
                        ("EBITDA",       "ebitda",        "auto"),
                        ("Free CF",      "free_cashflow", "auto"),
                        ("Op. CF",       "op_cashflow",   "auto"),
                        ("Gross Margin", "gross_margin",  "%"),
                        ("Op. Margin",   "op_margin",     "%"),
                        ("Net Margin",   "net_margin",    "%"),
                        ("Total Debt",   "total_debt",    "auto"),
                        ("Cash",         "cash",          "auto"),
                        ("EPS (Dil.)",   "eps",           "raw"),
                    ]
                    _qf_hdr = "".join(f'<span style="color:#FF6600;font-weight:700;text-align:right;font-family:monospace;font-size:10px">{q}</span>' for q in _mkt_qs)
                    _qf_html = (
                        f'<div style="background:#080808;border:1px solid #1A1A1A;border-radius:4px;padding:12px;margin:6px 0">'
                        f'<div style="display:grid;grid-template-columns:130px repeat({len(_mkt_qs)},1fr);gap:6px;'
                        f'padding:5px 8px;border-bottom:1px solid #FF6600;margin-bottom:4px">'
                        f'<span style="color:#FF6600;font-family:monospace;font-size:10px;font-weight:700;letter-spacing:1px">METRIC</span>{_qf_hdr}</div>'
                    )
                    for _i, (_lbl, _key, _unit) in enumerate(_MKT_METRICS):
                        _row_bg = "background:#050505;" if _i % 2 == 0 else ""
                        _cells = "".join(
                            f'<span style="text-align:right;font-family:monospace;font-size:11px">{_mkt_fmt_val(_mkt_fin_data.get(q, {}).get(_key), _unit)}</span>'
                            for q in _mkt_qs
                        )
                        _qf_html += (
                            f'<div style="display:grid;grid-template-columns:130px repeat({len(_mkt_qs)},1fr);gap:6px;'
                            f'padding:5px 8px;border-bottom:1px solid #0D0D0D;{_row_bg}">'
                            f'<span style="color:#888;font-family:monospace;font-size:11px">{_lbl}</span>{_cells}</div>'
                        )
                    _qf_html += '</div>'
                    st.markdown(_qf_html, unsafe_allow_html=True)
                else:
                    st.markdown('<div style="color:#555;font-size:11px;font-family:monospace">Quarterly financials unavailable.</div>', unsafe_allow_html=True)
            except Exception:
                pass
            # ── END QUARTERLY FINANCIALS ────────────────────────────────────

            # ── EARNINGS MATRIX (Markets Tab) ──────────────────────────────
            st.markdown('<div class="bb-ph" style="margin-top:14px">📈 EARNINGS MATRIX</div>', unsafe_allow_html=True)
            with st.spinner(f"Building Earnings Matrix for {tkr}…"):
                _mkt_em_data = get_earnings_matrix(tkr)
            if _mkt_em_data:
                _me_years     = _mkt_em_data["years"]
                _me_qlabels   = _mkt_em_data["q_labels"]
                _me_quarterly = _mkt_em_data["quarterly"]
                _me_estimates = _mkt_em_data.get("estimates", {})
                _me_beats     = _mkt_em_data.get("beats", {})
                _me_surprise  = _mkt_em_data.get("surprise_pct", {})
                _me_revenue_q = _mkt_em_data.get("revenue_q", {})
                _me_annual    = _mkt_em_data["annual"]
                _me_annual_rev = _mkt_em_data.get("annual_revenue", {})
                _me_yoy       = _mkt_em_data["yoy_growth"]
                _me_ann_growth = _mkt_em_data.get("annual_growth", {})
                _me_rev_growth = _mkt_em_data.get("rev_growth", {})
                _me_ann_rev_growth = _mkt_em_data.get("annual_rev_growth", {})
                _me_streak    = _mkt_em_data.get("streak", 0)
                _me_beat_rate = _mkt_em_data.get("beat_rate", 0)
                _me_company   = _mkt_em_data.get("company", tkr)
                _me_currency  = _mkt_em_data.get("currency", "USD")
                _me_vals      = _mkt_em_data.get("valuations", {})
                _me_ratings   = _mkt_em_data.get("analyst_ratings", {})
                _me_streak_c  = "#00CC44" if _me_streak > 0 else ("#FF4444" if _me_streak < 0 else "#888")
                _me_br_c      = "#00CC44" if _me_beat_rate >= 75 else "#FF8C00" if _me_beat_rate >= 50 else "#FF4444"
                _me_streak_txt = (f"🔥 {_me_streak}Q BEAT" if _me_streak > 0 else (f"⚠️ {abs(_me_streak)}Q MISS" if _me_streak < 0 else "—"))

                # ── Build EPS table HTML ──
                _me_yr_hdr = "".join(f"<th>{yr}</th>" for yr in _me_years)
                _me_eps_html = (
                    f'<div style="color:#555;font-family:monospace;font-size:9px;margin-bottom:6px;letter-spacing:1px">'
                    f'EPS ACTUAL vs ESTIMATE — {_me_currency} ($)</div>'
                    f'<table class="em-table"><thead><tr><th></th>{_me_yr_hdr}</tr></thead><tbody>'
                )
                for ql in _me_qlabels:
                    _me_eps_html += f"<tr><td>{ql}</td>"
                    for yr in _me_years:
                        val  = _me_quarterly.get(yr, {}).get(ql)
                        est  = _me_estimates.get(yr, {}).get(ql)
                        beat = _me_beats.get(yr, {}).get(ql)
                        surp = _me_surprise.get(yr, {}).get(ql)
                        if val is not None:
                            _ec = "#00CC44" if val >= 0 else "#FF4444"
                            _icon = (' <span style="color:#00CC44;font-size:8px">✓</span>' if beat is True
                                     else (' <span style="color:#FF4444;font-size:8px">✗</span>' if beat is False else ""))
                            _surp_s = (f'<br><span style="color:{"#00CC44" if (surp or 0)>=0 else "#FF4444"};font-size:8px">{surp:+.1f}%</span>'
                                       if surp is not None else "")
                            _est_s  = (f'<br><span style="color:#555;font-size:8px">est {est:.2f}</span>'
                                       if est is not None else "")
                            _me_eps_html += f'<td style="color:{_ec}">{val:.2f}{_icon}{_est_s}{_surp_s}</td>'
                        else:
                            _me_eps_html += '<td style="color:#333">—</td>'
                    _me_eps_html += "</tr>"
                _me_eps_html += '<tr class="em-annual"><td>Annual</td>'
                for yr in _me_years:
                    val = _me_annual.get(yr)
                    _me_eps_html += (f'<td style="color:{"#00CC44" if val>=0 else "#FF4444"};font-weight:700">{val:.2f}</td>'
                                     if val is not None else '<td style="color:#333">—</td>')
                _me_eps_html += "</tr></tbody></table>"

                # ── Build YoY growth table HTML ──
                _me_g_hdr  = "".join(f"<th>{yr}</th>" for yr in _me_years)
                _me_g_html = (
                    '<div style="color:#555;font-family:monospace;font-size:9px;margin-bottom:6px;letter-spacing:1px">YoY EPS GROWTH</div>'
                    f'<table class="em-table"><thead><tr><th></th>{_me_g_hdr}</tr></thead><tbody>'
                )
                for ql in _me_qlabels:
                    _me_g_html += f"<tr><td>{ql}</td>"
                    for yr in _me_years:
                        val = _me_yoy.get(yr, {}).get(ql)
                        _me_g_html += (f'<td style="color:{"#00CC44" if val>=0 else "#FF4444"}">{val:+.1f}%</td>'
                                       if val is not None else '<td style="color:#333">—</td>')
                    _me_g_html += "</tr>"
                _me_g_html += '<tr class="em-annual"><td>Annual</td>'
                for yr in _me_years:
                    val = _me_ann_growth.get(yr)
                    _me_g_html += (f'<td style="color:{"#00CC44" if val>=0 else "#FF4444"};font-weight:700">{val:+.1f}%</td>'
                                   if val is not None else '<td style="color:#333">—</td>')
                _me_g_html += "</tr></tbody></table>"

                # ── Build Revenue table HTML ──
                _me_rev_html = ""
                if _me_revenue_q:
                    _me_rev_hdr  = "".join(f"<th>{yr}</th>" for yr in _me_years)
                    _me_rev_html = (
                        '<div style="color:#555;font-family:monospace;font-size:9px;margin:10px 0 4px;letter-spacing:1px">QUARTERLY REVENUE</div>'
                        f'<table class="em-table"><thead><tr><th></th>{_me_rev_hdr}</tr></thead><tbody>'
                    )
                    for ql in _me_qlabels:
                        _me_rev_html += f"<tr><td>{ql}</td>"
                        for yr in _me_years:
                            val = _me_revenue_q.get(yr, {}).get(ql)
                            if val is not None:
                                rv_s = (f"${val/1e12:.2f}T" if abs(val)>=1e12
                                        else f"${val/1e9:.1f}B" if abs(val)>=1e9
                                        else f"${val/1e6:.0f}M" if abs(val)>=1e6
                                        else f"${val:,.0f}")
                                _me_rev_html += f'<td style="color:#CCC">{rv_s}</td>'
                            else:
                                _me_rev_html += '<td style="color:#333">—</td>'
                        _me_rev_html += "</tr>"
                    _me_rev_html += '<tr class="em-annual"><td>Annual</td>'
                    for yr in _me_years:
                        val = _me_annual_rev.get(yr)
                        if val is not None:
                            rv_a = (f"${val/1e12:.2f}T" if abs(val)>=1e12
                                    else f"${val/1e9:.1f}B" if abs(val)>=1e9
                                    else f"${val/1e6:.0f}M")
                            _me_rev_html += f'<td style="color:#FF8C00;font-weight:700">{rv_a}</td>'
                        else:
                            _me_rev_html += '<td style="color:#333">—</td>'
                    _me_rev_html += "</tr></tbody></table>"

                    # Revenue YoY growth
                    _me_rg_hdr  = "".join(f"<th>{yr}</th>" for yr in _me_years)
                    _me_rev_html += (
                        '<div style="color:#555;font-family:monospace;font-size:9px;margin:10px 0 4px;letter-spacing:1px">REVENUE YoY %</div>'
                        f'<table class="em-table"><thead><tr><th></th>{_me_rg_hdr}</tr></thead><tbody>'
                    )
                    for ql in _me_qlabels:
                        _me_rev_html += f"<tr><td>{ql}</td>"
                        for yr in _me_years:
                            val = _me_rev_growth.get(yr, {}).get(ql)
                            _me_rev_html += (f'<td style="color:{"#00CC44" if val>=0 else "#FF4444"}">{val:+.1f}%</td>'
                                             if val is not None else '<td style="color:#333">—</td>')
                        _me_rev_html += "</tr>"
                    _me_rev_html += '<tr class="em-annual"><td>Annual</td>'
                    for yr in _me_years:
                        val = _me_ann_rev_growth.get(yr)
                        _me_rev_html += (f'<td style="color:{"#00CC44" if val>=0 else "#FF4444"};font-weight:700">{val:+.1f}%</td>'
                                         if val is not None else '<td style="color:#333">—</td>')
                    _me_rev_html += "</tr></tbody></table>"

                # ── Build Valuation multiples HTML ──
                _me_val_html = ""
                if _me_vals:
                    _me_val_html = (
                        '<div style="color:#FF6600;font-size:10px;letter-spacing:1px;font-family:monospace;font-weight:700;margin:12px 0 6px">VALUATION MULTIPLES</div>'
                        '<table class="em-val-table"><thead><tr><th></th><th>Last 4Q</th><th>Forward</th></tr></thead><tbody>'
                    )
                    for _mn, _mp in _me_vals.items():
                        def _vc(v_str):
                            try:
                                v = float(v_str.replace("x",""))
                                return "#00CC44" if v < 15 else ("#FF8C00" if v < 25 else "#FF6600")
                            except: return "#888"
                        _lq = _mp.get("Last 4Q","—"); _fw = _mp.get("Forward","—")
                        _me_val_html += f'<tr><td>{_mn}</td><td style="color:{_vc(_lq)}">{_lq}</td><td style="color:{_vc(_fw)}">{_fw}</td></tr>'
                    _me_val_html += "</tbody></table>"

                # ── Build Analyst Ratings HTML ──
                _me_rat_html = ""
                if _me_ratings:
                    _cons = _me_ratings.get("consensus","—")
                    _nana = _me_ratings.get("num_analysts", 0)
                    _sb   = _me_ratings.get("strong_buy",  0)
                    _b    = _me_ratings.get("buy",         0)
                    _h    = _me_ratings.get("hold",        0)
                    _s    = _me_ratings.get("sell",        0)
                    _ss   = _me_ratings.get("strong_sell", 0)
                    _tot  = _me_ratings.get("total_rated", _sb+_b+_h+_s+_ss) or 1
                    _tmean = _me_ratings.get("target_mean",   0)
                    _tmed  = _me_ratings.get("target_median", 0)
                    _tlow  = _me_ratings.get("target_low",    0)
                    _thi   = _me_ratings.get("target_high",   0)
                    _cur_p = _mkt_em_data.get("price", 0)
                    _cons_c = ("#00CC44" if _cons.lower() in ("buy","strong buy","strongbuy","outperform","overweight")
                               else "#FF4444" if _cons.lower() in ("sell","strong sell","underperform","underweight")
                               else "#FF8C00")
                    def _pbar(n, total, color):
                        pct = min(round(n / total * 100), 100) if total > 0 else 0
                        return (f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                                f'<span style="width:70px;color:#888;font-size:9px">{n}</span>'
                                f'<div style="flex:1;background:#111;height:6px;border-radius:2px">'
                                f'<div style="width:{pct}%;background:{color};height:6px;border-radius:2px"></div></div>'
                                f'<span style="color:{color};font-size:9px;width:32px;text-align:right">{pct}%</span></div>')
                    _me_rat_html = (
                        f'<div style="color:#00AAFF;font-size:10px;letter-spacing:1px;font-family:monospace;font-weight:700;margin:12px 0 6px">'
                        f'ANALYST RATINGS <span style="color:#555;font-weight:400;font-size:8px">({_nana} analysts)</span></div>'
                        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">'
                        f'<span style="color:{_cons_c};font-size:16px;font-weight:900;font-family:monospace">{_cons}</span>'
                        f'</div>'
                        f'<div style="font-family:monospace;font-size:10px;color:#555;margin-bottom:4px;letter-spacing:1px">BREAKDOWN</div>'
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:70px;color:#00CC44;font-size:9px;font-weight:700">Strong Buy</span>'
                        f'<div style="flex:1;background:#111;height:6px;border-radius:2px"><div style="width:{min(round(_sb/_tot*100),100)}%;background:#00CC44;height:6px;border-radius:2px"></div></div>'
                        f'<span style="color:#00CC44;font-size:9px;width:26px;text-align:right">{_sb}</span></div>'
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:70px;color:#00AA33;font-size:9px;font-weight:700">Buy</span>'
                        f'<div style="flex:1;background:#111;height:6px;border-radius:2px"><div style="width:{min(round(_b/_tot*100),100)}%;background:#00AA33;height:6px;border-radius:2px"></div></div>'
                        f'<span style="color:#00AA33;font-size:9px;width:26px;text-align:right">{_b}</span></div>'
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:70px;color:#FF8C00;font-size:9px;font-weight:700">Hold</span>'
                        f'<div style="flex:1;background:#111;height:6px;border-radius:2px"><div style="width:{min(round(_h/_tot*100),100)}%;background:#FF8C00;height:6px;border-radius:2px"></div></div>'
                        f'<span style="color:#FF8C00;font-size:9px;width:26px;text-align:right">{_h}</span></div>'
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:70px;color:#FF6655;font-size:9px;font-weight:700">Sell</span>'
                        f'<div style="flex:1;background:#111;height:6px;border-radius:2px"><div style="width:{min(round(_s/_tot*100),100)}%;background:#FF6655;height:6px;border-radius:2px"></div></div>'
                        f'<span style="color:#FF6655;font-size:9px;width:26px;text-align:right">{_s}</span></div>'
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:70px;color:#FF4444;font-size:9px;font-weight:700">Strong Sell</span>'
                        f'<div style="flex:1;background:#111;height:6px;border-radius:2px"><div style="width:{min(round(_ss/_tot*100),100)}%;background:#FF4444;height:6px;border-radius:2px"></div></div>'
                        f'<span style="color:#FF4444;font-size:9px;width:26px;text-align:right">{_ss}</span></div>'
                    )
                    if _tmean > 0 or _tlow > 0 or _thi > 0:
                        _up_dn = (f'+{((_tmean-_cur_p)/_cur_p*100):.1f}%' if _cur_p > 0 and _tmean > 0
                                  else "")
                        _pt_c  = "#00CC44" if _tmean > _cur_p else "#FF4444"
                        _me_rat_html += (
                            f'<div style="margin-top:8px;padding-top:6px;border-top:1px solid #1A1A1A;font-family:monospace;font-size:10px">'
                            f'<div style="color:#555;font-size:8px;letter-spacing:1px;margin-bottom:4px">PRICE TARGETS</div>'
                            f'<div style="display:flex;justify-content:space-between">'
                            f'<span style="color:#888">Low: <span style="color:#CCC">${_tlow:,.2f}</span></span>'
                            f'<span style="color:#888">Mean: <span style="color:{_pt_c};font-weight:700">${_tmean:,.2f}</span>'
                            f'{"&nbsp;<span style=color:"+_pt_c+";font-size:9px>"+_up_dn+"</span>" if _up_dn else ""}</span>'
                            f'<span style="color:#888">High: <span style="color:#CCC">${_thi:,.2f}</span></span>'
                            f'</div>'
                            f'</div>'
                        )

                # ── Render all panels as single HTML block ──
                _em_full_html = (
                    f'<div class="em-container">'
                    f'<div class="em-header">'
                    f'<span class="em-badge">Earnings Matrix</span>'
                    f'<span class="em-ticker-label">● {tkr}</span>'
                    f'<span class="em-metric-label">EPS (GAAP) · {_me_currency}</span>'
                    f'<span style="margin-left:auto;font-family:monospace;font-size:10px;color:{_me_streak_c};font-weight:700">{_me_streak_txt}</span>'
                    f'<span style="margin-left:12px;font-family:monospace;font-size:10px;color:{_me_br_c}">Beat Rate: {_me_beat_rate:.0f}%</span>'
                    f'</div>'
                    # Two-column EPS + YoY tables
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:8px">'
                    f'<div>{_me_eps_html}</div>'
                    f'<div>{_me_g_html}</div>'
                    f'</div>'
                    # Revenue tables (full width)
                    f'{_me_rev_html}'
                    # Valuation + Analyst side by side
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:4px">'
                    f'<div>{_me_val_html}</div>'
                    f'<div>{_me_rat_html}</div>'
                    f'</div>'
                    f'</div>'
                )
                st.markdown(_em_full_html, unsafe_allow_html=True)

                # ── Quarterly Revenue Trend Chart ──
                if _me_revenue_q:
                    _rev_chart_labels, _rev_chart_vals = [], []
                    for yr in _me_years:
                        for ql in _me_qlabels:
                            val = _me_revenue_q.get(yr, {}).get(ql)
                            if val is not None:
                                _rev_chart_labels.append(f"{ql[:2]} {yr}")
                                _rev_chart_vals.append(val / 1e9)
                    if len(_rev_chart_labels) >= 2:
                        st.markdown('<div class="bb-ph" style="margin-top:12px">📉 QUARTERLY REVENUE TREND</div>', unsafe_allow_html=True)
                        _fig_rev = dark_fig(220)
                        # Scale y-axis properly based on actual data range
                        _rev_min = min(_rev_chart_vals) if _rev_chart_vals else 0
                        _rev_max = max(_rev_chart_vals) if _rev_chart_vals else 1
                        _rev_pad = (_rev_max - _rev_min) * 0.15 if _rev_max > _rev_min else _rev_max * 0.1
                        _rev_ymin = max(0, _rev_min - _rev_pad)
                        _rev_ymax = _rev_max + _rev_pad
                        _fig_rev.add_trace(go.Bar(
                            x=_rev_chart_labels, y=_rev_chart_vals,
                            marker=dict(color="rgba(255,102,0,0.25)", line=dict(color="#FF6600", width=1)),
                            hovertext=[f"${v:.2f}B" for v in _rev_chart_vals], hoverinfo="text",
                            name="Revenue ($B)",
                        ))
                        _fig_rev.add_trace(go.Scatter(
                            x=_rev_chart_labels, y=_rev_chart_vals,
                            mode="lines+markers",
                            line=dict(color="#FF6600", width=2),
                            marker=dict(size=6, color="#FF6600", line=dict(width=1, color="#000")),
                            text=[f"${v:.2f}B" for v in _rev_chart_vals],
                            textposition="top center", textfont=dict(size=7, color="#FF8C00"),
                            hoverinfo="skip", showlegend=False,
                        ))
                        _fig_rev.update_layout(
                            margin=dict(l=40, r=10, t=28, b=40), height=220,
                            title=dict(text="QUARTERLY REVENUE ($B)", font=dict(size=10, color="#FF6600"), x=0),
                            xaxis=dict(color="#555", tickfont=dict(size=7, color="#666"), tickangle=-45, showgrid=False),
                            yaxis=dict(color="#555", tickfont=dict(size=9), gridcolor="#111", tickprefix="$", ticksuffix="B",
                                       range=[_rev_ymin, _rev_ymax]),
                            legend=dict(font=dict(size=8, color="#888"), bgcolor="rgba(0,0,0,0)"),
                            showlegend=False,
                        )
                        st.plotly_chart(_fig_rev, use_container_width=True, config={"displayModeBar": False})
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Earnings matrix data unavailable.</p>', unsafe_allow_html=True)
            # ── END EARNINGS MATRIX ──────────────────────────────────────────

            if st.session_state.finnhub_key.get_secret_value():
                with st.status("Loading insider intelligence…", expanded=False) as _ins_status:
                    st.write("Fetching insider transactions…")
                    ins = finnhub_insider(tkr, st.session_state.finnhub_key.get_secret_value())
                    st.write("Resolving officer roles…")
                    officer_roles = finnhub_officers(tkr, st.session_state.finnhub_key.get_secret_value())
                    _ins_status.update(label="Insider data loaded", state="complete", expanded=False)
                if ins:
                    st.markdown(render_insider_cards(ins[:10], tkr, role_map=officer_roles), unsafe_allow_html=True)

                    # ── SMART MONEY CONVICTION BUY LIST ────────────────────
                    conviction = smart_money_conviction_buys(ins, officer_roles=officer_roles)
                    if conviction:
                        st.markdown(
                            '<div class="bb-ph" style="margin-top:12px">💰 SMART MONEY — CONVICTION BUY LIST</div>',
                            unsafe_allow_html=True)
                        st.markdown(
                            '<div style="color:#555;font-family:monospace;font-size:9px;margin-bottom:6px">'
                            'Open market purchases only (Code: P). Noise filtered: exercises, tax withholding, gifts, awards excluded. '
                            'Score = dollar value tier + C-suite seniority bonus.</div>',
                            unsafe_allow_html=True)
                        # Header
                        st.markdown(
                            '<div style="display:grid;grid-template-columns:1fr 90px 80px 100px 55px;gap:6px;'
                            'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                            'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                            '<span>INSIDER</span><span>ROLE</span><span>SHARES</span>'
                            '<span>$ VALUE</span><span>SCORE</span></div>',
                            unsafe_allow_html=True)
                        for cb in conviction[:8]:
                            _dv = cb["dollar_value"]
                            _dv_str = f"${_dv / 1e6:.2f}M" if _dv >= 1e6 else (f"${_dv / 1e3:.0f}K" if _dv >= 1e3 else f"${_dv:,.0f}")
                            _sc = cb["score"]
                            _sc_c = "#00CC44" if _sc >= 6 else "#FF8C00" if _sc >= 3 else "#888"
                            _role_c = "#FF6600" if cb["is_csuite"] else "#888"
                            _role_str = cb["role"][:18] if len(cb["role"]) > 18 else cb["role"]
                            _cs_badge = ' <span style="color:#00CC44;font-size:7px;font-weight:700">C-SUITE</span>' if cb["is_csuite"] else ""
                            st.markdown(
                                f'<div style="display:grid;grid-template-columns:1fr 90px 80px 100px 55px;gap:6px;'
                                f'padding:5px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px;'
                                f'border-left:3px solid #00CC44;background:rgba(0,204,68,0.03)">'
                                f'<div><span style="color:#FFF;font-weight:700">{_esc(cb["name"][:20])}</span>'
                                f'{_cs_badge}<br><span style="color:#555;font-size:9px">{cb["date"]}</span></div>'
                                f'<span style="color:{_role_c};font-size:9px">{_esc(_role_str)}</span>'
                                f'<span style="color:#00CC44;font-weight:600">{cb["shares"]:,}</span>'
                                f'<span style="color:#00CC44;font-weight:700">{_dv_str}</span>'
                                f'<span style="color:{_sc_c};font-weight:700;font-size:13px">{_sc}</span></div>',
                                unsafe_allow_html=True)
                        # Summary insight
                        _total_buys = sum(c["dollar_value"] for c in conviction)
                        _csuite_count = sum(1 for c in conviction if c["is_csuite"])
                        _total_str = f"${_total_buys / 1e6:.2f}M" if _total_buys >= 1e6 else f"${_total_buys / 1e3:.0f}K"
                        _signal = "🔥 STRONG" if _csuite_count >= 2 and _total_buys >= 500_000 else ("📊 MODERATE" if _csuite_count >= 1 or _total_buys >= 100_000 else "📋 WEAK")
                        _sig_c = "#00CC44" if "STRONG" in _signal else "#FF8C00" if "MODERATE" in _signal else "#888"
                        st.markdown(
                            f'<div style="background:#001A00;border:1px solid #00CC44;border-left:4px solid #00CC44;'
                            f'padding:10px 14px;margin:8px 0;font-family:monospace;font-size:11px">'
                            f'<span style="color:{_sig_c};font-weight:700">{_signal} CONVICTION SIGNAL</span>'
                            f'<br><span style="color:#888">Total Open Market Buys: '
                            f'<span style="color:#00CC44;font-weight:700">{_total_str}</span>'
                            f' &nbsp;|&nbsp; C-Suite Buyers: '
                            f'<span style="color:#FFF;font-weight:700">{_csuite_count}</span>'
                            f' &nbsp;|&nbsp; Total Transactions: {len(conviction)}</span></div>',
                            unsafe_allow_html=True)
                    else:
                        st.markdown(
                            '<div style="color:#555;font-family:monospace;font-size:10px;margin-top:6px">'
                            '💰 No open market purchases (Code: P) found. All insider activity is exercises, '
                            'awards, or tax withholding — low signal value.</div>',
                            unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No recent insider transactions found.</p>', unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Add Finnhub key in sidebar.</p>', unsafe_allow_html=True)

            st.markdown('<div class="bb-ph" style="margin-top:12px">📉 SHORT VOLUME & DARK POOL PROXY (FINRA/YF)</div>', unsafe_allow_html=True)
            finra = get_finra_short_volume(tkr)
            if finra:
                c1, c2, c3 = st.columns(3)
                c1.metric("Short % of Float", f"{finra['short_pct_float']}%", help="Percentage of freely tradable shares currently sold short. >20% is considered very high.")
                c2.metric("Short Shares", f"{finra['short_shares']:,}", help="Total number of shares currently held short by market participants.")
                c3.metric("Days to Cover", f"{finra['days_to_cover']}", help="Short ratio — days to cover all shorts at average daily volume. >5 days = potential squeeze setup.")
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
                _pct_val = row["% Chg"]
                _c = "#00CC44" if _pct_val >= 0 else "#FF4444"
                _arr = "▲" if _pct_val >= 0 else "▼"
                st.markdown(
                    f'<div class="wei-row">'
                    f'<span style="font-size:20px">{row["Flag"]}</span>'
                    f'<span style="color:#FFF;font-size:14px;font-weight:700">{row["Index"]}</span>'
                    f'<span style="color:{_c};font-weight:600">{row["Value"]:.3f}</span>'
                    f'<span style="color:{_c}">{row["Change"]:.3f}</span>'
                    f'<span style="color:{_c};font-weight:700">{_arr} {_pct_val:.2f}%</span>'
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
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTOR RELATIVE ROTATION GRAPH — under % change
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="bb-ph">🔄 SECTOR RELATIVE ROTATION GRAPH — RRG</div>', unsafe_allow_html=True)

    with st.status("Computing sector rotation…", expanded=False) as _rrg_status:
        st.write("Calculating RS-Ratio and RS-Momentum…")
        _rrg_data = get_sector_rrg()
        _rrg_status.update(label="Sector rotation computed", state="complete", expanded=False)

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
    # RISK-NEUTRAL EXPECTED MOVE (3D PROBABILITY SURFACE)
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="bb-ph">🔮 3D RISK-NEUTRAL PROBABILITY SURFACE</div>', unsafe_allow_html=True)
    with st.spinner("Computing 3D probability surface…"):
        spy_q = yahoo_quote("SPY")
        vix_q = yahoo_quote("^VIX")
        if spy_q and vix_q:
            spy_price = spy_q["price"]
            vix_iv = vix_q["price"] / 100.0
            
            # Days to Expiry (Y axis) and Strikes (X axis)
            days = np.linspace(1, 90, 30) # 1 to 90 days
            strike_pct = np.linspace(0.85, 1.15, 30) # 85% to 115% moneyness
            strikes = spy_price * strike_pct
            
            # Fully vectorized 3D Risk-Neutral PDF using np.meshgrid
            # Replaces nested Python for-loop (30x30 = 900 iterations)
            T = days / 365.0
            X_mesh, Y_mesh = np.meshgrid(strikes, T)
            sigma = vix_iv
            
            d1 = (np.log(X_mesh / spy_price) + (0.5 * sigma**2) * Y_mesh) / (sigma * np.sqrt(Y_mesh))
            Z = np.exp(-0.5 * d1**2) / (np.sqrt(2 * np.pi) * X_mesh * sigma * np.sqrt(Y_mesh))
            
            # Normalize Z
            Z_norm = Z / np.max(Z)
            
            colorscale = [
                [0, 'rgb(255,40,40)'],       # Low probability (Red)
                [0.5, 'rgb(255,255,255)'],   # Mid probability (White)
                [1, 'rgb(40,255,40)']        # High probability (Green)
            ]
            
            fig_3d = go.Figure(data=[go.Surface(
                z=Z_norm, x=strikes, y=days,
                colorscale=colorscale,
                showscale=False,
                contours=dict(
                    x=dict(show=True, color="white", width=1),
                    y=dict(show=True, color="white", width=1),
                    z=dict(show=True, usecolormap=True, highlightcolor="limegreen", project_z=True)
                )
            )])
            
            fig_3d.update_layout(
                title=dict(
                    text=f"SPY 3D PROBABILITY SURFACE (BASED ON VIX: {vix_q['price']:.2f})",
                    font=dict(size=12, color="#FF6600", family="monospace"),
                    x=0.5
                ),
                scene=dict(
                    xaxis_title='Strike Price ($)',
                    yaxis_title='Days to Expiry',
                    zaxis_title='Relative Probability Density',
                    xaxis=dict(gridcolor="#333", backgroundcolor="#080808", showbackground=True, tickfont=dict(color="#888")),
                    yaxis=dict(gridcolor="#333", backgroundcolor="#080808", showbackground=True, tickfont=dict(color="#888")),
                    zaxis=dict(gridcolor="#333", backgroundcolor="#080808", showbackground=True, tickfont=dict(color="#888"), range=[0, 1.2]),
                    camera=dict(
                        eye=dict(x=-1.5, y=-1.5, z=0.5)
                    )
                ),
                margin=dict(l=0, r=0, b=0, t=40),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=500
            )
            
            st.plotly_chart(fig_3d, use_container_width=True)
            
            st.markdown(
                '<div style="color:#888;font-size:10px;text-align:center;font-family:monospace;margin-top:-10px">'
                'Interactive 3D Risk-Neutral Probability Surface mapped across Strikes and Expirations based on current implied volatility.'
                '</div>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">SPY or VIX data unavailable for 3D expected move.</p>', unsafe_allow_html=True)

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
        _iv_ticker = st.text_input("IV Ticker", value=st.session_state.master_ticker or "SPY", key="iv_ts_tkr", placeholder="SPY, QQQ, AAPL…",
                                    help="Enter ticker for IV term structure analysis. Shows ATM implied volatility across multiple expiration dates.")
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
        _rv_iv = get_rv_iv_spread(_iv_ticker.upper().strip() if '_iv_ticker' in locals() else "SPY")
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
        _skew_data = get_iv_skew(_iv_ticker.upper().strip() if '_iv_ticker' in locals() else "SPY")
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
    with st.status("Building heatmap (scanning ~120 stocks)…", expanded=False) as _hm_status:
        st.write("Downloading sector stock data…")
        hm_data = get_heatmap_data()
        _hm_status.update(label="Heatmap ready", state="complete", expanded=False)
    if hm_data:
        hm_df = pd.DataFrame(hm_data)
        hm_df["pct_capped"] = hm_df["pct"].clip(-5, 5)
        hm_df["label"] = hm_df.apply(lambda r: f"{r['ticker']}<br>${r['price']:.2f}<br>{r['pct']:+.2f}%", axis=1)

        sectors = hm_df["sector"].unique().tolist()
        sec_rows = pd.DataFrame({
            "label": sectors, "sector": [""] * len(sectors),
            "pct_capped": [0]*len(sectors), "values": [0]*len(sectors),
            "ticker": sectors, "price": [0]*len(sectors),
            "pct": [0]*len(sectors), "change": [0]*len(sectors),
        })
        stock_rows = hm_df.copy()
        stock_rows["values"] = stock_rows["market_cap"].clip(lower=1e9)

        all_labels    = list(sec_rows["label"]) + list(stock_rows["label"])
        all_parents   = list(sec_rows["sector"]) + list(stock_rows["sector"])
        sec_rows["values"] = stock_rows.groupby("sector")["values"].sum().reindex(sectors).fillna(1e9).values
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
                    [0.0,  "#FF4444"],
                    [0.46, "#441111"],
                    [0.49, "#111111"],
                    [0.51, "#111111"],
                    [0.54, "#114411"],
                    [1.0,  "#00CC44"],
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
        st.plotly_chart(fig_hm, use_container_width=True)
    else:
        st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Heatmap data loading…</p>', unsafe_allow_html=True)

    if st.session_state.finnhub_key.get_secret_value():
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">📰 MARKET NEWS — FINNHUB LIVE</div>', unsafe_allow_html=True)
        with st.spinner("Loading news…"):
            fn = finnhub_news(st.session_state.finnhub_key.get_secret_value())
        for art in fn[:12]:  # scan more to compensate for filter
            title=art.get("headline","")[:100]; url=art.get("url","#"); src=art.get("source","")
            if not is_market_relevant(title, src): continue  # filter fluff
            ts=art.get("datetime",0)
            d=datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
            st.markdown(render_news_card(title,url,src,d,"bb-news bb-news-macro"), unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 2 — OPTIONS (Payoff Builder + Options Chain + 0DTE GEX)
# ════════════════════════════════════════════════════════════════════
with tabs[2]:

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ────────────────────────────────────────────────────────────────
    # OPTIONS CHAIN — MIGRATED FROM MARKETS TAB
    # ────────────────────────────────────────────────────────────────
    st.markdown('<div class="bb-ph">📋 OPTIONS INTELLIGENCE — ADAPTIVE SCORING ENGINE</div>', unsafe_allow_html=True)

    _opt_fc, _ = st.columns([2,3])
    with _opt_fc:
        def _on_opt_flash_change():
            val = st.session_state.get("opt_flash", "").upper().strip()
            if val:
                st.session_state.master_ticker = val
        _opt_default = st.session_state.master_ticker if st.session_state.master_ticker else ""
        _opt_ticker = st.text_input(
            "⚡ TICKER LOOKUP", value=_opt_default,
            placeholder="SPY, NVDA, AAPL, TSLA…", key="opt_flash",
            on_change=_on_opt_flash_change,
            help="Type a ticker to view options chain, scoring, and Greeks. Syncs with MARKETS tab.")

    if _opt_ticker:
        _ot = _opt_ticker.upper().strip()
        _oq = yahoo_quote(_ot)
        if _oq:
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:10px">'
                f'<span style="color:#FF6600;font-size:16px;font-weight:700;font-family:monospace">{_ot}</span>'
                f'<span style="color:#FFF;font-size:24px;font-weight:700;font-family:monospace">{fmt_p(_oq["price"])}</span>'
                f'<span style="color:{pct_color(_oq["pct"])};font-size:14px;font-weight:600;font-family:monospace">'
                f'{"+" if _oq["pct"]>=0 else ""}{_oq["pct"]:.2f}%</span></div>', unsafe_allow_html=True)

            _opt_expiries = options_expiries(_ot)
            _opt_sel_exp = None
            if not _opt_expiries:
                options_expiries.clear(_ot)
            else:
                def _of_fmt(d):
                    try: return datetime.strptime(str(d), "%Y-%m-%d").strftime("%B %-d, %Y")
                    except: return str(d)
                _opt_sel_exp = st.selectbox("EXPIRY DATE", _opt_expiries, index=0, key=f"opt_exp_{_ot}", format_func=_of_fmt)

            with st.spinner("Loading options…"):
                _oc, _op, _oe = options_chain(_ot, _opt_sel_exp)

            if _oc is not None:
                _oexp_dt = None
                try:
                    _oexp_dt = datetime.strptime(str(_oe), "%Y-%m-%d")
                    _oexp_fmt = _oexp_dt.strftime("%B %-d, %Y")
                except:
                    _oexp_fmt = str(_oe)

                try:
                    _ov_info = get_vix_full()
                    _o_vix = _ov_info[0] if _ov_info else 20.0
                except:
                    _o_vix = 20.0


                # ════════════════════════════════════════════════════════════
                # INTEGRATED PAYOFF BUILDER — live options data
                # ════════════════════════════════════════════════════════════
                st.markdown('<div class="bb-ph" style="margin-top:12px">📐 OPTIONS PAYOFF — STRATEGY ENGINE</div>', unsafe_allow_html=True)
                _LIVE_STRATS = {
                    "Long Call":             [("call",  1, 1)],
                    "Long Put":              [("put",   1, 1)],
                    "Short Call":            [("call", -1, 1)],
                    "Short Put":             [("put",  -1, 1)],
                    "Covered Call":          [("stock", 1, 1), ("call", -1, 1)],
                    "Protective Put":        [("stock", 1, 1), ("put",   1, 1)],
                    "Bull Call Spread":      [("call",  1, 1), ("call", -1, 2)],
                    "Bear Put Spread":       [("put",   1, 2), ("put",  -1, 1)],
                    "Bull Put Spread":       [("put",  -1, 1), ("put",   1, 2)],
                    "Bear Call Spread":      [("call", -1, 1), ("call",  1, 2)],
                    "Iron Condor":           [("put",   1, 1), ("put",  -1, 2), ("call", -1, 3), ("call", 1, 4)],
                    "Iron Butterfly":        [("put",   1, 1), ("put",  -1, 2), ("call", -1, 2), ("call", 1, 3)],
                    "Straddle":              [("call",  1, 1), ("put",   1, 1)],
                    "Strangle":              [("call",  1, 2), ("put",   1, 1)],
                    "Collar":                [("stock", 1, 1), ("put",   1, 1), ("call", -1, 2)],
                    "Call Ratio Backspread": [("call", -1, 1), ("call",  2, 2)],
                    "Put Ratio Backspread":  [("put",  -1, 2), ("put",   2, 1)],
                }
                _lv_dte_default = max((_oexp_dt.date()-datetime.today().date()).days,1) if _oexp_dt else 30
                _lv_spot = float(_oq["price"])
                _lv_c1, _lv_c2, _lv_c3, _lv_c4 = st.columns([2, 1, 1, 1])
                with _lv_c1:
                    _lv_strat = st.selectbox("Strategy", list(_LIVE_STRATS.keys()), key=f"lv_strat_{_ot}")
                with _lv_c2:
                    _lv_qty = st.number_input("Qty", value=1, min_value=1, max_value=500, key=f"lv_qty_{_ot}")
                with _lv_c3:
                    _lv_iv_override = st.slider("IV %", min_value=5.0, max_value=200.0, value=float(_o_vix) if _o_vix else 20.0, step=0.5, key=f"lv_iv_{_ot}")
                with _lv_c4:
                    _lv_dte_override = st.slider("DTE", min_value=1, max_value=365, value=int(_lv_dte_default), step=1, key=f"lv_dte_{_ot}")
                _lv_legs          = _LIVE_STRATS[_lv_strat]
                _lv_strike_indices = sorted(set(leg[2] for leg in _lv_legs if leg[0] != "stock"))
                # Strike selectors
                _lv_strike_vals = {}
                _strikes_fc = []
                if _oc is not None and not _oc.empty and "strike" in _oc.columns:
                    _strikes_fc = sorted(_oc["strike"].dropna().unique().tolist())
                elif _op is not None and not _op.empty and "strike" in _op.columns:
                    _strikes_fc = sorted(_op["strike"].dropna().unique().tolist())
                if _strikes_fc and _lv_strike_indices:
                    _lv_atm = min(range(len(_strikes_fc)), key=lambda i: abs(_strikes_fc[i]-_lv_spot))
                    _lv_sk_cols = st.columns(min(len(_lv_strike_indices), 4))
                    for i, si in enumerate(_lv_strike_indices):
                        _di = min(_lv_atm+i*2, len(_strikes_fc)-1)
                        with _lv_sk_cols[i % len(_lv_sk_cols)]:
                            _lv_strike_vals[si] = st.select_slider(f"K{i+1}", options=_strikes_fc, value=_strikes_fc[_di], key=f"lv_k_{si}_{_ot}")
                elif _lv_strike_indices:
                    _lv_sk_cols2 = st.columns(min(len(_lv_strike_indices), 4))
                    for i, si in enumerate(_lv_strike_indices):
                        with _lv_sk_cols2[i%len(_lv_sk_cols2)]:
                            _lv_strike_vals[si] = st.number_input(f"Strike {i+1} ($)", value=round(_lv_spot*(1+i*0.02),2), format="%.2f", key=f"lv_kn_{si}_{_ot}")
                def _lv_get_prem(cdf, strike):
                    if cdf is None or cdf.empty: return 0.0
                    col = "lastPrice" if "lastPrice" in cdf.columns else ("last" if "last" in cdf.columns else None)
                    if col is None: return 0.0
                    row = cdf[cdf["strike"]==strike]
                    if row.empty: row = cdf.iloc[(cdf["strike"]-strike).abs().argsort()[:1]]
                    if row.empty: return 0.0
                    v = float(row[col].iloc[0])
                    if v<=0 and "bid" in row.columns and "ask" in row.columns: v=(float(row["bid"].iloc[0])+float(row["ask"].iloc[0]))/2
                    return max(v,0.0)
                _lv_S = np.linspace(_lv_spot*0.85, _lv_spot*1.15, 600)
                _lv_total = np.zeros(len(_lv_S))
                _lv_nc=_lv_nd=_lv_ng=_lv_nt=_lv_nv=0.0
                _lv_T = max(_lv_dte_override/365.0, 1/365.0)
                _lv_sigma = _lv_iv_override/100.0
                for _ll_type,_ll_dir,_ll_si in _lv_legs:
                    _ll_K=_lv_strike_vals.get(_ll_si,_lv_spot); _ll_abs=abs(_ll_dir)*_lv_qty; _ll_sgn=1 if _ll_dir>0 else -1
                    if _ll_type=="stock":
                        _lv_total+=_ll_sgn*_ll_abs*100*(_lv_S-_lv_spot); _lv_nd+=_ll_sgn*_ll_abs*100
                    else:
                        _pm=_lv_get_prem(_oc if _ll_type=="call" else _op,_ll_K)
                        if _pm==0:
                            _bsv=bs_greeks_engine(_lv_spot,_ll_K,_lv_T,0.045,_lv_sigma,_ll_type); _pm=_bsv.get("price",0.0)
                        _intr=np.maximum(_lv_S-_ll_K,0) if _ll_type=="call" else np.maximum(_ll_K-_lv_S,0)
                        _lv_total+=_ll_sgn*_ll_abs*100*(_intr-_pm); _lv_nc+=_ll_sgn*_pm*_ll_abs*100
                        _g=bs_greeks_engine(_lv_spot,_ll_K,_lv_T,0.045,_lv_sigma,_ll_type)
                        _lv_nd+=_ll_sgn*_ll_abs*100*_g["delta"]; _lv_ng+=_ll_sgn*_ll_abs*100*_g["gamma"]
                        _lv_nt+=_ll_sgn*_ll_abs*100*_g["theta"]; _lv_nv+=_ll_sgn*_ll_abs*100*_g.get("vega",0)
                _lv_net_debit=-_lv_nc; _lv_mp=float(np.max(_lv_total)); _lv_ml=float(np.min(_lv_total))
                _lv_be=[]
                for _bi in range(len(_lv_total)-1):
                    if (_lv_total[_bi]<=0<_lv_total[_bi+1]) or (_lv_total[_bi]>=0>_lv_total[_bi+1]):
                        _lv_be.append(round(float(np.interp(0,[_lv_total[_bi],_lv_total[_bi+1]],[_lv_S[_bi],_lv_S[_bi+1]])),2))
                _lv_pop=None
                if _lv_be and _lv_sigma>0:
                    try:
                        _d1=(np.log(_lv_spot/_lv_be[0])+0.5*_lv_sigma**2*_lv_T)/(_lv_sigma*np.sqrt(_lv_T))
                        _lv_pop=float(_norm_dist.cdf(_d1) if _lv_total[-1]>0 else _norm_dist.cdf(-_d1))*100
                    except: pass
                _lv_nd_lbl="NET DEBIT" if _lv_net_debit>=0 else "NET CREDIT"
                _lv_ml_s=f"${abs(_lv_net_debit):,.0f}" if abs(_lv_net_debit)<1e7 else "Unlimited"
                _lv_mp_s=f"${_lv_mp:,.0f}" if _lv_mp<1e7 else "Infinite"
                _lv_be_d=("Above $"+f"{_lv_be[0]:,.2f} (+{(_lv_be[0]-_lv_spot)/_lv_spot*100:.1f}%)" if len(_lv_be)==1 else " / ".join(f"${b:,.2f}" for b in _lv_be) if _lv_be else "—")
                _lv_pop_s=f"{_lv_pop:.0f}%" if _lv_pop else "--%"
                st.markdown(f'''<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;background:#050505;border:1px solid #1A1A1A;border-top:2px solid #FF6600;padding:14px 20px;margin:10px 0 8px;font-family:monospace">
<div style="text-align:center;min-width:80px"><div style="color:#888;font-size:9px;letter-spacing:1px;margin-bottom:4px">{_lv_nd_lbl}</div><div style="color:#FFCC00;font-size:20px;font-weight:700">${abs(_lv_net_debit):,.0f}</div></div>
<div style="text-align:center;min-width:80px"><div style="color:#888;font-size:9px;letter-spacing:1px;margin-bottom:4px">MAX LOSS</div><div style="color:#FF4444;font-size:20px;font-weight:700">{_lv_ml_s}</div></div>
<div style="text-align:center;min-width:80px"><div style="color:#888;font-size:9px;letter-spacing:1px;margin-bottom:4px">MAX PROFIT</div><div style="color:#00CC44;font-size:20px;font-weight:700">{_lv_mp_s}</div></div>
<div style="text-align:center;min-width:80px"><div style="color:#888;font-size:9px;letter-spacing:1px;margin-bottom:4px">CHANCE OF PROFIT</div><div style="color:#FFF;font-size:20px;font-weight:700">{_lv_pop_s}</div></div>
<div style="text-align:center;min-width:120px"><div style="color:#888;font-size:9px;letter-spacing:1px;margin-bottom:4px">BREAKEVEN</div><div style="color:#00AAFF;font-size:14px;font-weight:700;line-height:1.4">{_lv_be_d}</div></div>
</div>''',unsafe_allow_html=True)
                _lv_fig=go.Figure()
                _lv_bm=_lv_be[0] if _lv_be else None
                if _lv_bm:
                    _ml2=_lv_S<=_lv_bm; _mp3=_lv_S>=_lv_bm
                    _Sl=np.append(_lv_S[_ml2],_lv_bm); _Pl=np.append(_lv_total[_ml2],float(np.interp(_lv_bm,_lv_S,_lv_total)))
                    _Sp=np.insert(_lv_S[_mp3],0,_lv_bm); _Pp=np.insert(_lv_total[_mp3],0,float(np.interp(_lv_bm,_lv_S,_lv_total)))
                    _lv_fig.add_trace(go.Scatter(x=_Sl,y=_Pl,mode="lines",line=dict(color="#FF2B43",width=3),fill="tozeroy",fillcolor="rgba(255,43,67,0.22)",showlegend=False,hovertemplate="$%{x:,.2f}<br>P&L: $%{y:,.0f}<extra></extra>"))
                    _lv_fig.add_trace(go.Scatter(x=_Sp,y=_Pp,mode="lines",line=dict(color="#00CC44",width=3),fill="tozeroy",fillcolor="rgba(0,204,68,0.18)",showlegend=False,hovertemplate="$%{x:,.2f}<br>P&L: $%{y:,.0f}<extra></extra>"))
                else:
                    _lv_fig.add_trace(go.Scatter(x=_lv_S,y=_lv_total,mode="lines",line=dict(color="#FF6600",width=3),fill="tozeroy",fillcolor="rgba(255,102,0,0.18)",showlegend=False))
                _lv_fig.add_hline(y=0,line_color="#2A2A2A",line_width=1)
                _lv_fig.add_vline(x=_lv_spot,line_color="#555",line_dash="dot",line_width=1,annotation_text=f"Spot ${_lv_spot:,.2f}",annotation_font=dict(size=9,color="#888",family="IBM Plex Mono"),annotation_position="top right")
                for _bv in _lv_be:
                    _lv_fig.add_vline(x=_bv,line_color="#00AAFF",line_width=1.5)
                    _lv_fig.add_annotation(x=_bv,y=max(_lv_total)*0.7 if max(_lv_total)>0 else 0,text=f"${_bv:,.2f}",showarrow=False,font=dict(color="#00AAFF",size=11,family="IBM Plex Mono"),xanchor="left",xshift=6)
                _lv_fig.update_layout(height=320,margin=dict(l=60,r=20,t=16,b=42),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(showgrid=True,gridcolor="#0D0D0D",zeroline=False,color="#888",tickprefix="$",tickfont=dict(size=9,family="IBM Plex Mono")),
                    yaxis=dict(showgrid=True,gridcolor="#0D0D0D",zeroline=False,color="#888",tickprefix="$",tickfont=dict(size=9,family="IBM Plex Mono")),hovermode="x unified")
                st.plotly_chart(_lv_fig,use_container_width=True,config={"displayModeBar":False})
                _lv_gc=st.columns(4)
                _lv_gc[0].markdown(f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #AA44FF;padding:8px;font-family:monospace;text-align:center"><div style="color:#555;font-size:8px">DELTA</div><div style="color:#BB88FF;font-size:14px;font-weight:700">{_lv_nd:+.2f}</div></div>',unsafe_allow_html=True)
                _lv_gc[1].markdown(f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #FF8C00;padding:8px;font-family:monospace;text-align:center"><div style="color:#555;font-size:8px">THETA</div><div style="color:#FF8C00;font-size:14px;font-weight:700">{_lv_nt:+.4f}</div></div>',unsafe_allow_html=True)
                _lv_gc[2].markdown(f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #00CC44;padding:8px;font-family:monospace;text-align:center"><div style="color:#555;font-size:8px">GAMMA</div><div style="color:#00CC44;font-size:14px;font-weight:700">{_lv_ng:+.5f}</div></div>',unsafe_allow_html=True)
                _lv_gc[3].markdown(f'<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #00AAFF;padding:8px;font-family:monospace;text-align:center"><div style="color:#555;font-size:8px">VEGA</div><div style="color:#00AAFF;font-size:14px;font-weight:700">{_lv_nv:+.4f}</div></div>',unsafe_allow_html=True)
                st.markdown(f'<div style="color:#555;font-size:9px;font-family:monospace;margin-top:4px">DTE: {_lv_dte_override}d &nbsp;|&nbsp; IV: {_lv_iv_override:.1f}% &nbsp;|&nbsp; SPOT: ${_lv_spot:,.2f} &nbsp;|&nbsp; {_lv_strat}</div>',unsafe_allow_html=True)
                st.markdown('<hr class="bb-divider">',unsafe_allow_html=True)
                # ── END PAYOFF BUILDER ──
                _oscored = score_options_chain(_oc, _op, _oq["price"], vix=_o_vix, expiry_date=_opt_sel_exp)

                _ovix_str = f"{_o_vix:.1f}" if _o_vix else "N/A"
                if _o_vix and _o_vix > 25:
                    _oregime = f'<span style="color:#FF4444;font-weight:700">HIGH VOL (VIX {_ovix_str})</span> — Δ-weighted'
                elif _o_vix and _o_vix < 15:
                    _oregime = f'<span style="color:#00CC44;font-weight:700">LOW VOL (VIX {_ovix_str})</span> — Flow-weighted'
                else:
                    _oregime = f'<span style="color:#FF8C00;font-weight:700">NEUTRAL (VIX {_ovix_str})</span> — Balanced'

                st.markdown(f'<div style="color:#888;font-size:11px;font-family:monospace;margin-bottom:6px">EXPIRY: {_oexp_fmt} | CURRENT: {fmt_p(_oq["price"])} | REGIME: {_oregime}</div>', unsafe_allow_html=True)

                _occ, _opc = st.columns(2)
                with _occ:
                    st.markdown('<div style="color:#00CC44;font-size:10px;font-weight:700;letter-spacing:2px">▲ TOP CALLS (by score)</div>', unsafe_allow_html=True)
                    st.markdown(render_scored_options(_oscored["top_calls"], side="calls"), unsafe_allow_html=True)
                with _opc:
                    st.markdown('<div style="color:#FF4444;font-size:10px;font-weight:700;letter-spacing:2px">▼ TOP PUTS (by score)</div>', unsafe_allow_html=True)
                    st.markdown(render_scored_options(_oscored["top_puts"], side="puts"), unsafe_allow_html=True)

                if _oscored.get("unusual"):
                    st.markdown(render_unusual_trade(_oscored["unusual"], ticker=_ot, expiry=_oexp_fmt), unsafe_allow_html=True)

                with st.expander("🔧 TRUE BLACK-SCHOLES ENGINE (WHAT-IF)", expanded=False):
                    st.markdown('<div style="color:#888;font-size:10px;margin-bottom:8px">Calculate Delta, Gamma, Theta locally bypassing Alpaca endpoint limits.</div>', unsafe_allow_html=True)
                    _bsc1, _bsc2, _bsc3, _bsc4, _bsc5 = st.columns(5)
                    with _bsc1: _bs_s = st.number_input("Spot Price", value=float(_oq["price"]), format="%.2f", key=f"obs_s_{_ot}")
                    with _bsc2: _bs_k = st.number_input("Strike", value=float(_oq["price"]), format="%.2f", key=f"obs_k_{_ot}")
                    with _bsc3:
                        _odt_exp = max((_oexp_dt.date() - datetime.today().date()).days, 1) if _oexp_dt else 14
                        _bs_t = st.number_input("Days to Expire", value=float(_odt_exp), format="%.1f", key=f"obs_t_{_ot}")
                    with _bsc4:
                        _bs_v = st.number_input("Implied Vol (%)", value=float(_o_vix) if _o_vix else 20.0, format="%.1f", key=f"obs_v_{_ot}")
                    with _bsc5: _bs_side = st.selectbox("Type", ["call", "put"], key=f"obs_side_{_ot}")

                    _bs_res = bs_greeks_engine(_bs_s, _bs_k, _bs_t / 365.0, 0.045, _bs_v / 100.0, _bs_side)
                    _brc1, _brc2, _brc3, _brc4, _brc5 = st.columns(5)
                    _brc1.metric("Delta", f"{_bs_res['delta']:.4f}", help="Rate of change of option price per $1 move in underlying. Calls: 0 to 1, Puts: -1 to 0.")
                    _brc2.metric("Gamma", f"{_bs_res['gamma']:.6f}", help="Rate of change of Delta per $1 move. High gamma = delta shifts fast (near ATM, short-dated).")
                    _brc3.metric("Theta (Daily)", f"{_bs_res['theta']:.4f}", help="Time decay — how much option value erodes per day. Accelerates near expiry.")
                    _brc4.metric("Vega (1%)", f"{_bs_res.get('vega', 0):.4f}", help="Sensitivity to a 1% change in implied volatility. Higher for longer-dated options.")
                    _brc5.metric("Rho (1%)", f"{_bs_res.get('rho', 0):.4f}", help="Sensitivity to a 1% change in interest rates. Matters more for LEAPS.")

                with st.expander("📊 **FULL OPTIONS CHAIN**", expanded=False):
                    _ofc, _ofp = st.columns(2)
                    with _ofc:
                        st.markdown('<div style="color:#00CC44;font-size:9px;font-weight:700;letter-spacing:2px">▲ ALL CALLS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(_oc, "calls", _oq["price"]), unsafe_allow_html=True)
                    with _ofp:
                        st.markdown('<div style="color:#FF4444;font-size:9px;font-weight:700;letter-spacing:2px">▼ ALL PUTS</div>', unsafe_allow_html=True)
                        st.markdown(render_options_table(_op, "puts", _oq["price"]), unsafe_allow_html=True)
            else:
                st.warning(f"Options data failed to load for {_ot}")
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Options unavailable for this ticker.</p>', unsafe_allow_html=True)
        else:
            st.error(f"No data for '{_ot}'. Check ticker symbol.")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ────────────────────────────────────────────────────────────────
    # 0DTE GEX & TRADE ENGINE (kept from original SPX 0DTE tab)
    # ────────────────────────────────────────────────────────────────
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
                with _m1: st.metric("SPX SPOT", f"${_spot:,.2f}", help="Current SPX spot price from Alpaca real-time feed.")
                with _m2: st.metric("EXPECTED MOVE", f"±{_em:.1f}", help="Options-implied expected daily range in SPX points. Derived from high-low spread.")
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
                    st.metric("VIX", f"{_vix_val:.2f}", delta=_vl, help="Expected 30-day annualized volatility of SPX. <15=calm, 15-25=normal, >30=high fear, >40=panic.")
                else: st.metric("VIX", "—")
            with _v2:
                _v9d = _vix_data.get("vix9d")
                st.metric("VIX9D", f"{_v9d:.2f}" if _v9d else "—")
            with _v3:
                _ctg = _vix_data.get("contango")
                if _ctg is not None:
                    st.metric("TERM STRUCTURE", "✅ Contango" if _ctg else "⚠️ Backwardation",
                            delta_color="normal" if _ctg else "inverse",
                            help="Contango = front VIX < back VIX (normal, markets calm). Backwardation = inverted — signals acute fear/hedging demand.")
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
            # Use CBOE data as fallback for direction predictor if no Alpaca chain
            _dir_chain_src = _0dte_chain
            _dir_spx_src   = _spx
            if not _dir_chain_src or not _dir_spx_src:
                try:
                    _fb_spot, _fb_opts = fetch_cboe_gex("SPX")
                    if _fb_spot and _fb_opts:
                        _dir_spx_src = {"spot": _fb_spot, "vwap": _fb_spot, "high": _fb_spot*1.005, "low": _fb_spot*0.995}
                        # Build minimal chain from CBOE opts
                        _dir_chain_src = [{"strike": float(r.get("strike",0)), "option_type": r.get("option_type","call").lower(),
                                           "open_interest": int(r.get("open_interest",0) or 0),
                                           "gamma": float(r.get("gamma",0) or 0), "expiration_date": r.get("expiration_date","")}
                                          for r in (_fb_opts or []) if r.get("strike")]
                except Exception:
                    pass
            _dir_result = compute_spx_direction(_dir_chain_src, _dir_spx_src, _vix_data)
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

                _gex_col, _ovw_col = st.columns([3, 2])
                with _gex_col:
                    _fig = render_0dte_gex_chart(_gex, _gf_spy, _mp_spy,
                                                spot_spx=_spot_for_chart,
                                                display_pct=_chart_pct)
                    if _fig:
                        st.plotly_chart(_fig, use_container_width=True, config={'displayModeBar': False})
                    else:
                        st.markdown('<div style="color:#555;font-family:monospace;font-size:11px">GEX data unavailable.</div>', unsafe_allow_html=True)
                with _ovw_col:
                    # ── TODAY OVERVIEW panel ──
                    st.markdown('<div style="color:#FF6600;font-weight:700;font-size:12px;letter-spacing:1px;'
                                'margin-bottom:8px;font-family:monospace">📋 TODAY OVERVIEW</div>', unsafe_allow_html=True)
                    _ovw_spot = _spot_for_chart or (_spx["spot"] if _spx else None)
                    _ovw_vwap = _spx["vwap"] if _spx else None
                    _ovw_high = _spx["high"] if _spx else None
                    _ovw_low = _spx["low"] if _spx else None
                    _ovw_em = round(_ovw_high - _ovw_low, 1) if _ovw_high and _ovw_low else None
                    _ovw_vix = _vix_data.get("vix") if _vix_data else None
                    _ovw_pcr = compute_pcr(_0dte_chain) if _0dte_chain else None
                    if _ovw_pcr is None and _use_cboe:
                        _ovw_pcr = compute_cboe_pcr(_cboe_opts)
                    _ovw_total_gex = _total_gex_bn
                    _ovw_gf_spx = _gf_spy * 10 if _gf_spy else None
                    _ovw_mp_spx = _mp_spy * 10 if _mp_spy else None

                    # Gamma regime
                    if _ovw_spot and _ovw_gf_spx:
                        _gamma_regime = "POSITIVE γ" if _ovw_spot > _ovw_gf_spx else "NEGATIVE γ"
                        _gamma_color = "#00CC44" if _ovw_spot > _ovw_gf_spx else "#FF4444"
                        _gamma_desc = "Dealer dampening" if _ovw_spot > _ovw_gf_spx else "Dealer amplifying"
                    else:
                        _gamma_regime, _gamma_color, _gamma_desc = "—", "#888", ""

                    def _ovw_row(label, value, color="#CCC", sub=""):
                        sub_html = f'<span style="color:#555;font-size:9px;margin-left:6px">{sub}</span>' if sub else ""
                        return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
                                f'padding:5px 8px;border-bottom:1px solid #111;font-family:monospace;font-size:11px">'
                                f'<span style="color:#888">{label}</span>'
                                f'<span style="color:{color};font-weight:600">{value}{sub_html}</span></div>')

                    _ovw_html = '<div style="background:#080808;border:1px solid #1A1A1A;border-top:2px solid #FF6600;padding:2px 0">'
                    _ovw_html += _ovw_row("SPX SPOT", f"${_ovw_spot:,.2f}" if _ovw_spot else "—", "#FFF")
                    _ovw_html += _ovw_row("VWAP", f"${_ovw_vwap:,.2f}" if _ovw_vwap else "—",
                                          "#00CC44" if _ovw_spot and _ovw_vwap and _ovw_spot > _ovw_vwap else "#FF4444")
                    _ovw_html += _ovw_row("HIGH / LOW",
                                          f"${_ovw_high:,.2f} / ${_ovw_low:,.2f}" if _ovw_high and _ovw_low else "—",
                                          "#CCC")
                    _ovw_html += _ovw_row("DAY RANGE", f"±{_ovw_em:.1f} pts" if _ovw_em else "—", "#FF8C00")
                    _ovw_html += _ovw_row("VIX", f"{_ovw_vix:.2f}" if _ovw_vix else "—",
                                          "#FF4444" if _ovw_vix and _ovw_vix > 25 else "#FF8C00" if _ovw_vix and _ovw_vix > 18 else "#00CC44")
                    _ovw_html += _ovw_row("PCR", f"{_ovw_pcr:.2f}" if _ovw_pcr else "—",
                                          "#FF4444" if _ovw_pcr and _ovw_pcr > 1.0 else "#00CC44" if _ovw_pcr and _ovw_pcr < 0.7 else "#FF8C00")
                    _ovw_html += _ovw_row("NET GEX",
                                          f"${_ovw_total_gex:+.2f}Bn" if _ovw_total_gex is not None else "—",
                                          "#00CC44" if _ovw_total_gex and _ovw_total_gex >= 0 else "#FF4444")
                    _ovw_html += _ovw_row("γ FLIP", f"${_ovw_gf_spx:,.0f}" if _ovw_gf_spx else "—", "#FFCC00")
                    _ovw_html += _ovw_row("MAX PAIN", f"${_ovw_mp_spx:,.0f}" if _ovw_mp_spx else "—", "#AA44FF")
                    _ovw_html += _ovw_row("γ REGIME", _gamma_regime, _gamma_color, _gamma_desc)
                    _ovw_html += '</div>'
                    st.markdown(_ovw_html, unsafe_allow_html=True)

                # ── GEX DECODER (full width below) ──
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

    if not st.session_state.fred_key.get_secret_value():
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
            macro_ov = get_macro_overview(st.session_state.fred_key.get_secret_value())

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
            macro_cal = get_macro_calendar(st.session_state.fred_key.get_secret_value())

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
                fig_yc = yield_curve_chart(st.session_state.fred_key.get_secret_value(), 260)
            if fig_yc:
                st.plotly_chart(fig_yc, use_container_width=True)
                df_2y = fred_series("DGS2", st.session_state.fred_key.get_secret_value(), 3)
                df_10y = fred_series("DGS10", st.session_state.fred_key.get_secret_value(), 3)
                if df_2y is not None and df_10y is not None and not df_2y.empty and not df_10y.empty:
                    sp = round(df_10y["value"].iloc[-1] - df_2y["value"].iloc[-1], 2)
                    if sp < 0:
                        st.markdown(f'<div style="background:#1A0000;border-left:3px solid #FF0000;padding:8px 12px;font-family:monospace;font-size:11px;color:#FF8C00">⚠️ INVERTED: 10Y-2Y = {sp:.2f}%. Recession lead: 12-18 months avg.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="background:#001A00;border-left:3px solid #00CC44;padding:8px 12px;font-family:monospace;font-size:11px;color:#CCC">✅ NORMAL: 10Y-2Y = +{sp:.2f}%</div>', unsafe_allow_html=True)

                st.markdown('<div class="bb-ph" style="margin-top:8px">📊 CPI vs FED FUNDS vs CORE PCE</div>', unsafe_allow_html=True)
                with st.spinner("Loading inflation data…"):
                    fig_cpi = cpi_vs_rates_chart(st.session_state.fred_key.get_secret_value(), 250)
                if fig_cpi:
                    st.plotly_chart(fig_cpi, use_container_width=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace">Yield data loading…</p>', unsafe_allow_html=True)

        with mc2:
            st.markdown('<div class="bb-ph">📊 KEY MACRO INDICATORS</div>', unsafe_allow_html=True)
            MACRO = {"CPI":"CPIAUCSL","Core PCE":"PCEPILFE","Fed Funds":"FEDFUNDS",
                    "Unemployment":"UNRATE","U6 Rate":"U6RATE","M2 Supply":"M2SL",
                    "HY Spread":"BAMLH0A0HYM2"}
            for name, code in MACRO.items():
                df = fred_series(code, st.session_state.fred_key.get_secret_value(), 3)
                if df is not None and not df.empty:
                    val = round(df["value"].iloc[-1], 2)
                    prev = round(df["value"].iloc[-2], 2) if len(df)>1 else val
                    chg = round(val-prev, 2)
                    st.metric(name, f"{val:.2f}", delta=f"{chg:+.2f}",
                              help={
                                  "CPI": "Consumer Price Index — headline inflation measure. YoY change drives Fed policy.",
                                  "Core PCE": "Personal Consumption Expenditures excluding food & energy. The Fed's preferred inflation gauge.",
                                  "Fed Funds": "Federal Funds effective rate. The primary tool for monetary policy. Floor for all short-term rates.",
                                  "Unemployment": "U3 unemployment rate. Below 4% is considered full employment (tightens labor market).",
                                  "U6 Rate": "Broad unemployment including discouraged workers and underemployed. More comprehensive than U3.",
                                  "M2 Supply": "M2 money supply in trillions. Rapid growth is inflationary; contraction signals tightening.",
                                  "HY Spread": "High-yield (junk) bond spread over Treasuries. Widening = rising credit risk / fear.",
                              }.get(name))

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

        st.markdown('<div class="bb-ph">📈 MULTI-MATURITY YIELD HISTORY — 3 YEARS (LIVE FRED)</div>', unsafe_allow_html=True)
        with st.spinner("Loading yield history…"):
            fig_hist = yield_history_chart(st.session_state.fred_key.get_secret_value(), 240)
        if fig_hist:
            st.plotly_chart(fig_hist, use_container_width=True)
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
        # SOVEREIGN 10Y BOND YIELDS BY COUNTRY
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        _sov_left, _sov_right = st.columns([1, 1])

        with _sov_left:
            st.markdown('<div class="bb-ph">🏛️ GLOBAL SOVEREIGN 10Y YIELDS — HIGHEST FIRST</div>', unsafe_allow_html=True)
            with st.spinner("Loading sovereign yields…"):
                _sov_yields = get_sovereign_10y_yields()
            if _sov_yields:
                # Header
                st.markdown(
                    '<div style="display:grid;grid-template-columns:30px 1fr 80px 70px;gap:8px;'
                    'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                    'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                    '<span></span><span>COUNTRY</span><span>YIELD</span><span>CHG</span></div>',
                    unsafe_allow_html=True)
                for sy in _sov_yields:
                    _yld_c = "#FF4444" if sy["yield_pct"] > 5.0 else "#FF8C00" if sy["yield_pct"] > 3.5 else "#FFCC00" if sy["yield_pct"] > 2.0 else "#00CC44"
                    _chg_c = "#00CC44" if sy["change"] <= 0 else "#FF4444"
                    _chg_sign = "+" if sy["change"] > 0 else ""
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:30px 1fr 80px 70px;gap:8px;'
                        f'padding:5px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:12px">'
                        f'<span style="font-size:16px">{sy["flag"]}</span>'
                        f'<span style="color:#FFF;font-weight:600">{sy["country"]}</span>'
                        f'<span style="color:{_yld_c};font-weight:700">{sy["yield_pct"]:.3f}%</span>'
                        f'<span style="color:{_chg_c}">{_chg_sign}{sy["change"]:.3f}</span></div>',
                        unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Sovereign yield data loading…</p>', unsafe_allow_html=True)

        with _sov_right:
            st.markdown('<div class="bb-ph">⚠️ SOVEREIGN CREDIT RISK — ETF PROXY</div>', unsafe_allow_html=True)
            with st.spinner("Loading sovereign CDS…"):
                _sov_cds = get_sovereign_cds_proxy()
            if _sov_cds:
                # Header
                st.markdown(
                    '<div style="display:grid;grid-template-columns:30px 1fr 70px 70px 80px;gap:8px;'
                    'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                    'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                    '<span></span><span>COUNTRY/ETF</span><span>PRICE</span><span>%CHG</span><span>RISK</span></div>',
                    unsafe_allow_html=True)
                for sc in _sov_cds:
                    _pct_c = "#00CC44" if sc["pct"] >= 0 else "#FF4444"
                    _pct_sign = "+" if sc["pct"] >= 0 else ""
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:30px 1fr 70px 70px 80px;gap:8px;'
                        f'padding:5px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px;'
                        f'border-left:3px solid {sc["risk_color"]}">'
                        f'<span style="font-size:14px">{sc["flag"]}</span>'
                        f'<span style="color:#CCC;font-weight:600">{sc["label"]}</span>'
                        f'<span style="color:#888">${sc["price"]:.2f}</span>'
                        f'<span style="color:{_pct_c};font-weight:600">{_pct_sign}{sc["pct"]:.2f}%</span>'
                        f'<span style="color:{sc["risk_color"]};font-weight:700;font-size:9px">{sc["risk_signal"]}</span></div>',
                        unsafe_allow_html=True)
                st.markdown(
                    '<div style="color:#444;font-size:8px;font-family:monospace;margin-top:4px">'
                    'Proxy: ETF performance as CDS proxy. Negative returns signal higher sovereign stress. '
                    'Real CDS spreads require Bloomberg terminal.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Sovereign CDS proxy data loading…</p>', unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════════
        # CENTRAL BANK RATES + YIELD CURVE INVERSIONS
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        _cb_left, _cb_right = st.columns([1, 1])

        with _cb_left:
            st.markdown('<div class="bb-ph">🏦 CENTRAL BANK POLICY RATES — GLOBAL</div>', unsafe_allow_html=True)
            with st.spinner("Loading central bank rates…"):
                _cb_rates = get_central_bank_rates(st.session_state.fred_key.get_secret_value())
            if _cb_rates:
                # Header
                st.markdown(
                    '<div style="display:grid;grid-template-columns:30px 1fr 70px 60px 80px;gap:8px;'
                    'padding:5px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                    'font-size:9px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                    '<span></span><span>CENTRAL BANK</span><span>RATE</span><span>CHG</span><span>STANCE</span></div>',
                    unsafe_allow_html=True)
                for cb in _cb_rates:
                    _rate_c = "#FF4444" if cb["rate"] > 4.0 else "#FF8C00" if cb["rate"] > 2.0 else "#00CC44"
                    _chg_c = "#FF4444" if cb["change"] > 0 else "#00CC44" if cb["change"] < 0 else "#888"
                    _chg_sign = "+" if cb["change"] > 0 else ""
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:30px 1fr 70px 60px 80px;gap:8px;'
                        f'padding:6px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:12px;'
                        f'border-left:3px solid {cb["stance_color"]}">'
                        f'<span style="font-size:16px">{cb["flag"]}</span>'
                        f'<span style="color:#FFF;font-weight:600;font-size:11px">{cb["name"]}</span>'
                        f'<span style="color:{_rate_c};font-weight:700">{cb["rate"]:.2f}%</span>'
                        f'<span style="color:{_chg_c};font-size:10px">{_chg_sign}{cb["change"]:.2f}</span>'
                        f'<span style="color:{cb["stance_color"]};font-weight:700;font-size:9px">{cb["stance"]}</span></div>',
                        unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Central bank rate data unavailable.</p>', unsafe_allow_html=True)

        with _cb_right:
            st.markdown('<div class="bb-ph">📐 YIELD CURVE INVERSIONS MONITOR</div>', unsafe_allow_html=True)
            _fk = st.session_state.fred_key.get_secret_value()
            if _fk:
                with st.spinner("Checking yield curve inversions…"):
                    _yc_inv = get_yield_curve_inversions(_fk)
                if _yc_inv:
                    # Count inversions
                    _n_inv = sum(1 for y in _yc_inv if y["inverted"])
                    _inv_banner_c = "#FF4444" if _n_inv >= 2 else "#FF8C00" if _n_inv >= 1 else "#00CC44"
                    _inv_label = f"⚠️ {_n_inv} INVERSION{'S' if _n_inv != 1 else ''} DETECTED" if _n_inv > 0 else "✅ NO INVERSIONS — CURVE NORMAL"
                    st.markdown(
                        f'<div style="background:#0A0A0A;border:1px solid {_inv_banner_c};border-left:4px solid {_inv_banner_c};'
                        f'padding:8px 14px;margin-bottom:8px;font-family:monospace;font-size:12px;color:{_inv_banner_c};font-weight:700">'
                        f'{_inv_label}</div>', unsafe_allow_html=True)
                    # Header
                    st.markdown(
                        '<div style="display:grid;grid-template-columns:90px 70px 70px 70px 90px;gap:6px;'
                        'padding:4px 10px;border-bottom:1px solid #FF6600;font-family:monospace;'
                        'font-size:8px;color:#FF6600;letter-spacing:1px;margin-bottom:2px">'
                        '<span>SPREAD</span><span>LONG</span><span>SHORT</span><span>DIFF</span><span>STATUS</span></div>',
                        unsafe_allow_html=True)
                    for yi in _yc_inv:
                        _sp_c = "#FF4444" if yi["inverted"] else ("#FF8C00" if abs(yi["spread"]) < 0.10 else "#00CC44")
                        _sp_sign = "+" if yi["spread"] > 0 else ""
                        _row_bg = "background:rgba(255,68,68,0.06);" if yi["inverted"] else ""
                        st.markdown(
                            f'<div style="display:grid;grid-template-columns:90px 70px 70px 70px 90px;gap:6px;'
                            f'padding:5px 10px;border-bottom:1px solid #0D0D0D;font-family:monospace;font-size:11px;{_row_bg}'
                            f'border-left:3px solid {_sp_c}">'
                            f'<span style="color:#FFF;font-weight:600">{yi["label"]}</span>'
                            f'<span style="color:#888">{yi["long_rate"]:.3f}%</span>'
                            f'<span style="color:#888">{yi["short_rate"]:.3f}%</span>'
                            f'<span style="color:{_sp_c};font-weight:700">{_sp_sign}{yi["spread"]:.3f}</span>'
                            f'<span style="color:{yi["status_color"]};font-weight:700;font-size:9px">{yi["status"]}</span></div>',
                            unsafe_allow_html=True)
                    # Descriptions
                    with st.expander("Spread Descriptions", expanded=False):
                        for yi in _yc_inv:
                            st.markdown(
                                f'<div style="font-family:monospace;font-size:9px;color:#888;padding:2px 0">'
                                f'<span style="color:#FF8C00">{yi["label"]}</span> — {yi["description"]}</div>',
                                unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Yield curve inversion data requires FRED API key.</p>', unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">Add FRED API key to monitor yield curve inversions.</p>', unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════════
        # NET LIQUIDITY INDICATOR (Feature 2)
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">💧 NET LIQUIDITY INDICATOR — WALCL − TGA − RRP</div>', unsafe_allow_html=True)

        with st.spinner("Computing net liquidity…"):
            _nl_data = get_net_liquidity(st.session_state.fred_key.get_secret_value())

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
            _yc3d_data = get_yield_curve_history(st.session_state.fred_key.get_secret_value(), lookback_weeks=52)

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
            _esi = get_economic_surprise_index(st.session_state.fred_key.get_secret_value())
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
            if _esi and _esi.get("_no_key"):
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">ESI requires a FRED API key. Add FRED_API_KEY to secrets.</p>', unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">ESI unavailable — add FRED_API_KEY for macro calendar data.</p>', unsafe_allow_html=True)

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
    # ── Institutional BTC ETF Flows ───────────────────────────────────

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
                st.plotly_chart(fig_mis, use_container_width=True)

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
            st.plotly_chart(fig_prob, use_container_width=True)

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
            st.plotly_chart(fig_vol, use_container_width=True)

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
        earn_tkr = st.text_input("Ticker for chart & matrix", value=st.session_state.master_ticker or "", placeholder="NVDA, AAPL…", key="ec",
                                  help="Enter a ticker to view earnings history, revenue matrix, expected move, and AI guidance.")

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

                    def _fmt_val(v, unit="auto", decimals=1):
                        if v is None: return '<span style="color:#444">—</span>'
                        if unit == "%": return f'<span style="color:#CCC">{v:.1f}%</span>'
                        if unit == "raw": return f'<span style="color:#CCC">{v:.2f}</span>'
                        # Auto-scale: detect T/B/M from magnitude
                        abs_v = abs(v)
                        if abs_v >= 1e12:   v_disp, suffix = v / 1e12, "T"
                        elif abs_v >= 1e9:  v_disp, suffix = v / 1e9,  "B"
                        elif abs_v >= 1e6:  v_disp, suffix = v / 1e6,  "M"
                        elif abs_v >= 1e3:  v_disp, suffix = v / 1e3,  "K"
                        else:               v_disp, suffix = v,         ""
                        color = "#00CC44" if v >= 0 else "#FF4444"
                        return f'<span style="color:{color};font-weight:600">{v_disp:,.{decimals}f}{suffix}</span>'

                    METRICS = [
                        ("Revenue",      "revenue",       "auto"),
                        ("Gross Profit", "gross_profit",  "auto"),
                        ("Op. Income",   "op_income",     "auto"),
                        ("Net Income",   "net_income",    "auto"),
                        ("EBITDA",       "ebitda",        "auto"),
                        ("Free CF",      "free_cashflow", "auto"),
                        ("Op. CF",       "op_cashflow",   "auto"),
                        ("Gross Margin", "gross_margin",  "%"),
                        ("Op. Margin",   "op_margin",     "%"),
                        ("Net Margin",   "net_margin",    "%"),
                        ("Total Debt",   "total_debt",    "auto"),
                        ("Cash",         "cash",          "auto"),
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
                    _et_ratings = _em_data.get("analyst_ratings", {})

                    # ── Analyst Ratings Block (Earnings Tab) ──
                    if _et_ratings:
                        _et_cons  = _et_ratings.get("consensus","—")
                        _et_nana  = _et_ratings.get("num_analysts", 0)
                        _et_sb    = _et_ratings.get("strong_buy",  0)
                        _et_b     = _et_ratings.get("buy",         0)
                        _et_h     = _et_ratings.get("hold",        0)
                        _et_s     = _et_ratings.get("sell",        0)
                        _et_ss    = _et_ratings.get("strong_sell", 0)
                        _et_tot   = max(_et_ratings.get("total_rated", _et_sb+_et_b+_et_h+_et_s+_et_ss), 1)
                        _et_tmean = _et_ratings.get("target_mean",   0)
                        _et_tmed  = _et_ratings.get("target_median", 0)
                        _et_tlow  = _et_ratings.get("target_low",    0)
                        _et_thi   = _et_ratings.get("target_high",   0)
                        _et_cur   = _em_data.get("price", 0)
                        _et_cc    = ("#00CC44" if _et_cons.lower() in ("buy","strong buy","strongbuy","outperform","overweight")
                                     else "#FF4444" if _et_cons.lower() in ("sell","strong sell","underperform","underweight")
                                     else "#FF8C00")
                        _et_up_dn = (f'+{((_et_tmean-_et_cur)/_et_cur*100):.1f}%' if _et_cur > 0 and _et_tmean > 0 else "")
                        _et_pt_c  = "#00CC44" if _et_tmean > _et_cur else "#FF4444"
                        def _et_bar(lbl, n, tot, col):
                            p = min(round(n / tot * 100), 100) if tot > 0 else 0
                            return (f'<div style="display:flex;align-items:center;gap:5px;margin:2px 0">'
                                    f'<span style="width:58px;color:{col};font-size:8px">{lbl}</span>'
                                    f'<div style="flex:1;background:#111;height:5px;border-radius:2px">'
                                    f'<div style="width:{p}%;background:{col};height:5px;border-radius:2px"></div></div>'
                                    f'<span style="color:{col};font-size:8px;width:22px;text-align:right">{n}</span></div>')
                        _rat_html = (
                            f'<div style="margin-top:14px;padding:10px;background:#0A0A0A;border:1px solid #1A1A1A;'
                            f'border-radius:3px;font-family:monospace;font-size:10px">'
                            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">'
                            f'<span style="color:#00AAFF;font-weight:700;letter-spacing:1px">ANALYST RATINGS</span>'
                            f'<span style="color:#555;font-size:8px">{_et_nana} analysts</span></div>'
                            f'<span style="color:{_et_cc};font-size:15px;font-weight:900;display:block;margin-bottom:7px">{_et_cons}</span>'
                            + _et_bar("Strong Buy", _et_sb, _et_tot, "#00CC44")
                            + _et_bar("Buy",         _et_b,  _et_tot, "#00AA33")
                            + _et_bar("Hold",        _et_h,  _et_tot, "#FF8C00")
                            + _et_bar("Sell",        _et_s,  _et_tot, "#FF6655")
                            + _et_bar("Str. Sell",   _et_ss, _et_tot, "#FF4444")
                        )
                        if _et_tmean > 0 or _et_tlow > 0 or _et_thi > 0:
                            _rat_html += (
                                f'<div style="margin-top:7px;padding-top:5px;border-top:1px solid #1A1A1A">'
                                f'<div style="color:#555;font-size:8px;letter-spacing:1px;margin-bottom:3px">PRICE TARGETS</div>'
                                f'<div style="display:flex;justify-content:space-between">'
                                f'<span style="color:#888;font-size:9px">Low <b style="color:#CCC">${_et_tlow:,.2f}</b></span>'
                                f'<span style="color:#888;font-size:9px">Mean <b style="color:{_et_pt_c}">${_et_tmean:,.2f}</b>'
                                + (f' <b style="color:{_et_pt_c};font-size:8px">{_et_up_dn}</b>' if _et_up_dn else "")
                                + f'</span><span style="color:#888;font-size:9px">High <b style="color:#CCC">${_et_thi:,.2f}</b></span>'
                                f'</div></div>'
                            )
                        _rat_html += '</div>'
                        st.markdown(_rat_html, unsafe_allow_html=True)

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
                        gemini_api_key=st.session_state.gemini_key.get_secret_value(),
                        finnhub_key=st.session_state.get("finnhub_key"),
                        newsapi_key=st.session_state.get("newsapi_key"),
                    )
                if _ai_summary:
                    if "error" in _ai_summary:
                        err = _ai_summary["error"]
                        if err == "NO_KEY":
                            msg = "AI summary unavailable. Check Gemini key."
                        elif err == "FUTURE_EVENT":
                            msg = f"Earnings event for {et} has not happened yet (Expected: {_ai_summary.get('date', 'Future')})."
                        elif err == "NO_NEWS":
                            msg = f"No recent news found for {et} to generate an earnings summary."
                        else:
                            msg = "AI summary generation failed."
                        st.markdown(f'<p style="color:#555;font-family:monospace;font-size:11px">{msg}</p>', unsafe_allow_html=True)
                    else:
                        _summary_text = _ai_summary["summary"].replace("\n", "<br>")
                        st.markdown(
                            f'<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;'
                            f'padding:14px 16px;font-family:monospace;font-size:11px;color:#CCC;line-height:1.8">'
                            f'<div style="color:#FF6600;font-size:10px;letter-spacing:1px;margin-bottom:8px">'
                            f'⚡ SENTINEL AI ({_ai_summary["news_count"]} news sources analyzed)</div>'
                            f'{_summary_text}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">AI summary generation failed.</p>', unsafe_allow_html=True)

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
                stock_news = filter_market_news(stock_news, key_title="title", key_source="source")
                for art in stock_news:
                    st.markdown(render_news_card(art["title"], art["url"], art["source"], art["date"], "bb-news"), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#555;font-family:monospace;font-size:11px">No recent news found. Add Finnhub or NewsAPI key for richer coverage.</p>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 8 — SENTINEL AI
# ════════════════════════════════════════════════════════════════════
with tabs[8]:
    st.markdown('<div class="bb-ph">🤖 SENTINEL AI — POWERED BY GOOGLE GEMINI</div>', unsafe_allow_html=True)

    if not st.session_state.gemini_key.get_secret_value():
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
                mlist = list_gemini_models(st.session_state.gemini_key.get_secret_value())
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