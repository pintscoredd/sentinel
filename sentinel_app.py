#!/usr/bin/env python3
"""
⚡ SENTINEL — Free Bloomberg/PLTR Terminal
Built with Streamlit | Powered by free APIs + Google Gemini
"""

import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import plotly.graph_objects as go
import json
from datetime import datetime
import pytz
import pathlib
import streamlit.components.v1 as components

# ── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="⚡ SENTINEL",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

PST = pytz.timezone("US/Pacific")

def now_pst():
    return datetime.now(PST).strftime("%Y-%m-%d %H:%M PST")

# ── DARK TERMINAL CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp,[data-testid="stAppViewContainer"]{background:#060810!important;color:#c9d1d9!important}
  [data-testid="stSidebar"]{background:#0d1117!important;border-right:1px solid #1f2937!important}
  h1,h2,h3{color:#58a6ff!important}
  [data-testid="stMetric"]{background:#0d1117;border:1px solid #1f2937;border-radius:6px;padding:10px}
  .stTabs [data-baseweb="tab-list"]{background:#0d1117;border-bottom:1px solid #1f2937}
  .stTabs [data-baseweb="tab"]{color:#8b949e}
  .stTabs [aria-selected="true"]{color:#58a6ff!important;border-bottom:2px solid #58a6ff}
  .stButton>button{background:#1f2937;color:#58a6ff;border:1px solid #374151;border-radius:4px}
  .stButton>button:hover{background:#374151;border-color:#58a6ff}
  .stTextInput>div>div>input,.stTextArea>div>div>textarea{background:#0d1117!important;color:#c9d1d9!important;border:1px solid #374151!important}
  .stSelectbox>div>div{background:#0d1117!important;color:#c9d1d9!important}
  .sentinel-alert{background:#1a1f2e;border-left:3px solid #f85149;padding:12px 16px;margin:6px 0;border-radius:0 4px 4px 0;font-family:'Courier New',monospace;font-size:13px}
  .sentinel-signal{background:#0d1f2d;border-left:3px solid #58a6ff;padding:12px 16px;margin:6px 0;border-radius:0 4px 4px 0;font-family:'Courier New',monospace;font-size:13px}
  .sentinel-geo{background:#1a1a0d;border-left:3px solid #e3b341;padding:12px 16px;margin:6px 0;border-radius:0 4px 4px 0;font-family:'Courier New',monospace;font-size:13px}
  .sentinel-poly{background:#1a0d1f;border-left:3px solid #bc8cff;padding:12px 16px;margin:6px 0;border-radius:0 4px 4px 0;font-family:'Courier New',monospace;font-size:13px}
  .sentinel-green{background:#0d1f0d;border-left:3px solid #3fb950;padding:12px 16px;margin:6px 0;border-radius:0 4px 4px 0;font-family:'Courier New',monospace;font-size:13px}
  .term-header{font-family:'Courier New',monospace;color:#58a6ff;font-size:11px;letter-spacing:2px;text-transform:uppercase;border-bottom:1px solid #1f2937;padding-bottom:6px;margin-bottom:14px}
  .chat-user{background:#1f2937;border-radius:8px;padding:10px 14px;margin:6px 0;border-left:3px solid #58a6ff}
  .chat-ai{background:#0d1f0d;border-radius:8px;padding:10px 14px;margin:6px 0;border-left:3px solid #3fb950;font-family:'Courier New',monospace;font-size:13px;white-space:pre-wrap}
  .stDataFrame{background:#0d1117!important}
  div[data-testid="stDecoration"]{display:none}
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
    st.markdown("## ⚡ SENTINEL")
    st.markdown(f"`{now_pst()}`")
    st.divider()

    st.markdown("### 🔑 API KEYS")
    st.caption("All free. Click links to register.")

    with st.expander("🤖 Gemini (Required for AI Chat)", expanded=not st.session_state.gemini_key):
        st.caption("[Get free key → aistudio.google.com](https://aistudio.google.com/app/apikey)")
        st.session_state.gemini_key = st.text_input("Gemini API Key", value=st.session_state.gemini_key, type="password", key="gin")

    with st.expander("📊 Market — Finnhub + Alpha Vantage"):
        st.caption("[Finnhub free key → finnhub.io](https://finnhub.io/register)")
        st.session_state.finnhub_key = st.text_input("Finnhub Key", value=st.session_state.finnhub_key, type="password", key="fh")
        st.caption("[Alpha Vantage → alphavantage.co](https://www.alphavantage.co/support/#api-key)")
        st.session_state.alphavantage_key = st.text_input("Alpha Vantage Key", value=st.session_state.alphavantage_key, type="password", key="av")

    with st.expander("📈 Macro — FRED"):
        st.caption("[FRED free key → fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)")
        st.session_state.fred_key = st.text_input("FRED Key", value=st.session_state.fred_key, type="password", key="fr")

    with st.expander("📰 News — NewsAPI"):
        st.caption("[NewsAPI free → newsapi.org](https://newsapi.org/register)")
        st.session_state.newsapi_key = st.text_input("NewsAPI Key", value=st.session_state.newsapi_key, type="password", key="na")

    with st.expander("💰 Crypto — CoinGecko"):
        st.caption("[CoinGecko Demo (optional) → coingecko.com](https://www.coingecko.com/en/api/pricing)")
        st.session_state.coingecko_key = st.text_input("CoinGecko Demo Key", value=st.session_state.coingecko_key, type="password", key="cg")

    st.divider()
    st.markdown("### 📡 CONNECTION STATUS")
    STATUS = {
        "Yahoo Finance": True,
        "Polymarket": True,
        "GDELT": True,
        "Fear & Greed": True,
        "FRED": bool(st.session_state.fred_key),
        "Finnhub": bool(st.session_state.finnhub_key),
        "Alpha Vantage": bool(st.session_state.alphavantage_key),
        "NewsAPI": bool(st.session_state.newsapi_key),
        "CoinGecko": True,
        "Gemini AI": bool(st.session_state.gemini_key),
    }
    for api, ok in STATUS.items():
        st.markdown(f"{'🟢' if ok else '🔴'} `{api}`")

    st.divider()
    st.markdown("### 🧠 MY CONTEXT")
    st.session_state.macro_theses = st.text_area("Active macro theses", value=st.session_state.macro_theses, placeholder="e.g. Watching Fed pivot, cautious on tech...", height=70)
    st.session_state.geo_watch = st.text_area("Geo situations watching", value=st.session_state.geo_watch, placeholder="e.g. Red Sea, Taiwan strait...", height=55)
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
        df = pd.DataFrame(obs)
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
        return r.json().get("data", [])[:8]
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
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps: return None, None
        chain = t.option_chain(exps[0])
        cols = ["strike", "lastPrice", "volume", "openInterest", "impliedVolatility"]
        return chain.calls[cols].head(10), chain.puts[cols].head(10)
    except Exception:
        return None, None

@st.cache_data(ttl=600)
def sector_etfs():
    SECTORS = {"Technology": "XLK", "Financials": "XLF", "Energy": "XLE",
                "Healthcare": "XLV", "Consumer Staples": "XLP", "Utilities": "XLU",
                "Consumer Disc.": "XLY", "Materials": "XLB", "Comm. Services": "XLC",
                "Real Estate": "XLRE", "Industrials": "XLI"}
    rows = []
    for name, tkr in SECTORS.items():
        q = yahoo_quote(tkr)
        if q: rows.append({"Sector": name, "ETF": tkr, "Price": q["price"], "Change %": q["pct"]})
    return pd.DataFrame(rows)

def detect_unusual_poly(markets):
    out = []
    for m in markets:
        try:
            v24 = float(m.get("volume24hr", 0) or 0)
            vtot = float(m.get("volume", 0) or 0)
            if vtot > 0 and v24 / vtot > 0.38 and v24 > 5000:
                out.append(m)
        except Exception:
            pass
    return out[:6]

def market_snapshot_str():
    try:
        qs = multi_quotes(["SPY", "QQQ", "DXY", "GLD", "TLT", "BTC-USD"])
        parts = [f"{q['ticker']}: ${q['price']:,.2f} ({q['pct']:+.2f}%)" for q in qs]
        v = vix_price()
        if v: parts.append(f"VIX: {v}")
        fv, fl = fear_greed()
        if fv: parts.append(f"Crypto F&G: {fv} ({fl})")
        return " | ".join(parts)
    except Exception:
        return ""

# ── GEMINI SYSTEM PROMPT ─────────────────────────────────────────────────────
SENTINEL_PROMPT = """
You are SENTINEL — a personal financial and geopolitical intelligence terminal for a retail power investor in PST timezone.

PERSONA: Adaptive — match the user's tone. Simple language, deep analysis. Define jargon on first use. Data-first, narrative-second.

CAPABILITIES:
- Macro analysis: CPI, PCE, Fed rates, GDP, yield curve, M2, credit spreads (FRED data)
- Equity analysis: sectors, ETFs, options flow interpretation, rotation signals
- Crypto: BTC dominance, ETH/BTC ratio, Fear & Greed, macro correlations
- Geopolitical intelligence: Middle East, China/Taiwan, Russia/Ukraine, Sub-Saharan Africa, shipping routes
- Polymarket: prediction market analysis, unusual flow detection, convergence signals
- Cross-asset correlation detection and second/third-order effect chains
- Historical analog matching
- Scenario trees (Bull/Base/Bear with probabilities)
- Narrative vs. positioning divergence detection

RULES:
1. Never fabricate data. If unknown, say so and say where to find it.
2. Always include a bear case with any bullish idea.
3. Label confidence: HIGH / MEDIUM / LOW / UNCONFIRMED
4. Separate facts from interpretation — label clearly.
5. Polymarket = crowd odds, not guaranteed outcomes.
6. Everything = research, not financial advice.
7. Trace ripple chains: never stop at first-order effects.
8. When asked about a ticker: price context, catalyst, cross-asset implications.
9. When asked about a macro event: second and third-order effects.
10. Geopolitical events: confidence level, competing accounts, market exposure.

OUTPUT FORMATS:
/brief → Full morning briefing (macro, geo, Polymarket, markets, sector rotation, SENTINEL signal)
/flash [ticker] → Quick snapshot: price, catalyst, options pulse, SENTINEL read
/geo [region] → Geopolitical dashboard: status, confidence, market exposure, second-order chain
/scenario [asset] → Bull/base/bear scenario tree with probabilities
/poly [topic] → Polymarket analysis with unusual activity scan
/rotate → Sector rotation read with cycle position
/sentiment → Market sentiment dashboard

Always timestamp in PST. Always end trade ideas with: ⚠️ Research only, not financial advice.
""".strip()

def gemini_response(user_msg, history, context=""):
    if not st.session_state.gemini_key:
        return "⚠️ Please add your Gemini API key in the sidebar to activate SENTINEL AI."
    try:
        import google.generativeai as genai
        genai.configure(api_key=st.session_state.gemini_key)
        model = genai.GenerativeModel(model_name="gemini-2.0-flash-exp",
                                      system_instruction=SENTINEL_PROMPT)
        ctx = ""
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
    except ImportError:
        return "⚠️ google-generativeai not installed. Run: pip install google-generativeai"
    except Exception as e:
        return f"⚠️ Gemini error: {e}"

# ── CHART THEME ──────────────────────────────────────────────────────────────
CHART = dict(paper_bgcolor="#060810", plot_bgcolor="#0d1117",
             font=dict(color="#c9d1d9"),
             xaxis=dict(gridcolor="#1f2937"),
             yaxis=dict(gridcolor="#1f2937"),
             margin=dict(l=0, r=10, t=24, b=0))

def dark_fig(height=300):
    fig = go.Figure()
    fig.update_layout(**CHART, height=height, showlegend=False)
    return fig

# ════════════════════════════════════════════════════════════════════════════
# ── MAIN APP ────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:4px">
  <h1 style="margin:0;font-family:'Courier New',monospace;letter-spacing:4px;color:#58a6ff">⚡ SENTINEL</h1>
  <span style="color:#8b949e;font-family:'Courier New',monospace;font-size:11px">FREE BLOOMBERG / PLTR TERMINAL</span>
</div>
""", unsafe_allow_html=True)
st.markdown(f'<p style="color:#374151;font-family:Courier New;font-size:10px;margin-top:-8px">'
            f'{now_pst()} | Yahoo Finance • FRED • Polymarket • GDELT • CoinGecko • Finnhub • NewsAPI</p>',
            unsafe_allow_html=True)

tabs = st.tabs(["🌅 Brief", "📊 Markets", "📈 Macro", "💰 Crypto", "🎲 Polymarket", "🌍 Geo", "🤖 SENTINEL AI"])

# ════════════════════════════════════════
# TAB 1 — MORNING BRIEF
# ════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="term-header">⚡ SENTINEL MORNING BRIEF</div>', unsafe_allow_html=True)

    if st.button("🔄 Refresh All Data"):
        st.cache_data.clear()
        st.rerun()

    # ── Market Snapshot ──
    st.markdown("### 📊 MARKET SNAPSHOT")
    KEY_TICKERS = {
        "SPY": "S&P 500", "QQQ": "Nasdaq", "DIA": "Dow",
        "IWM": "Russell 2K", "^TNX": "10Y Yield", "DXY": "USD Index",
        "GLD": "Gold ETF", "CL=F": "WTI Crude", "BTC-USD": "Bitcoin"
    }
    qs = multi_quotes(list(KEY_TICKERS.keys()))
    cols = st.columns(len(qs))
    for col, q in zip(cols, qs):
        label = KEY_TICKERS.get(q["ticker"], q["ticker"])
        with col:
            st.metric(label, f"${q['price']:,.2f}", delta=f"{q['pct']:+.2f}%")

    st.divider()

    col_l, col_r = st.columns([3, 2])

    with col_l:
        # ── Sentiment Pulse ──
        st.markdown("### ⚡ SENTIMENT PULSE")
        s1, s2, s3 = st.columns(3)
        v = vix_price()
        with s1:
            if v:
                lbl = "LOW FEAR" if v < 15 else ("MODERATE" if v < 25 else ("HIGH FEAR" if v < 35 else "PANIC"))
                st.metric("VIX", f"{v:.2f}", delta=lbl)
        fg_val, fg_lbl = fear_greed()
        with s2:
            if fg_val: st.metric("Crypto Fear & Greed", f"{fg_val}/100", delta=fg_lbl)
        with s3:
            if v:
                posture = "🟢 RISK-ON" if v < 18 else ("🟡 NEUTRAL" if v < 25 else "🔴 RISK-OFF")
                st.metric("SENTINEL Posture", posture)

        st.divider()

        # ── Watchlist ──
        st.markdown("### 👁 WATCHLIST")
        wl_qs = multi_quotes(st.session_state.watchlist)
        if wl_qs:
            wl_df = pd.DataFrame([{
                "Ticker": q["ticker"],
                "Price": f"${q['price']:,.4f}" if q["price"] < 5 else f"${q['price']:,.2f}",
                "Change": f"${q['change']:+.2f}",
                "% Chg": f"{q['pct']:+.2f}%",
            } for q in wl_qs])
            st.dataframe(wl_df, use_container_width=True, hide_index=True)

        st.divider()

        # ── Sector Leaders / Laggards ──
        st.markdown("### 🔄 SECTOR PULSE")
        sec_df = sector_etfs()
        if not sec_df.empty:
            top = sec_df.nlargest(3, "Change %")[["Sector", "ETF", "Change %"]]
            bot = sec_df.nsmallest(3, "Change %")[["Sector", "ETF", "Change %"]]
            tc, bc = st.columns(2)
            with tc:
                st.markdown("**🟢 Leading**")
                st.dataframe(top, use_container_width=True, hide_index=True)
            with bc:
                st.markdown("**🔴 Lagging**")
                st.dataframe(bot, use_container_width=True, hide_index=True)

    with col_r:
        # ── Polymarket Top ──
        st.markdown("### 🎲 POLYMARKET TOP")
        poly = polymarket_markets(20)
        for m in poly[:6]:
            title = m.get("question", m.get("title", ""))[:65]
            v24 = float(m.get("volume24hr", 0) or 0)
            st.markdown(f'<div class="sentinel-poly"><strong>{title}…</strong><br>'
                        f'<span style="color:#8b949e;font-size:11px">24h Vol: ${v24:,.0f}</span></div>',
                        unsafe_allow_html=True)

        st.divider()

        # ── GDELT Geo Headlines ──
        st.markdown("### 🌍 GEO WATCH")
        geo_arts = gdelt_news("geopolitical conflict oil market", max_rec=5)
        for art in geo_arts[:4]:
            t = art.get("title", "")[:70]
            u = art.get("url", "#")
            st.markdown(f'<div class="sentinel-geo"><a href="{u}" target="_blank" '
                        f'style="color:#e3b341;text-decoration:none">{t}…</a></div>',
                        unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 2 — MARKETS
# ════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="term-header">📊 MARKETS — EQUITIES, OPTIONS & ROTATION</div>', unsafe_allow_html=True)

    # Flash lookup
    fc, _ = st.columns([2, 2])
    with fc:
        flash_ticker = st.text_input("⚡ Flash Lookup — Ticker", placeholder="NVDA, AAPL, TSLA, SPY…", key="flash")

    if flash_ticker:
        tkr = flash_ticker.upper().strip()
        q = yahoo_quote(tkr)
        if q:
            st.markdown(f"#### ⚡ FLASH: {tkr}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Price",  f"${q['price']:,.2f}", delta=f"{q['pct']:+.2f}%")
            m2.metric("Change", f"${q['change']:+.4f}")
            m3.metric("Volume", f"{q['volume']:,}")

            # Candlestick chart
            try:
                hist = yf.Ticker(tkr).history(period="3mo")
                if not hist.empty:
                    fig = dark_fig(height=300)
                    fig.add_trace(go.Candlestick(
                        x=hist.index, open=hist["Open"], high=hist["High"],
                        low=hist["Low"], close=hist["Close"],
                        increasing_line_color="#3fb950", decreasing_line_color="#f85149",
                        name=tkr
                    ))
                    fig.update_layout(xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

            # Insider transactions
            if st.session_state.finnhub_key:
                ins = finnhub_insider(tkr, st.session_state.finnhub_key)
                if ins:
                    st.markdown("##### 🔍 Insider Transactions (Finnhub)")
                    ins_df = pd.DataFrame(ins)
                    show_cols = [c for c in ["name", "change", "share", "transactionDate", "transactionCode"] if c in ins_df.columns]
                    if show_cols:
                        st.dataframe(ins_df[show_cols].rename(columns={
                            "name": "Name", "change": "Chg Shares", "share": "Total Shares",
                            "transactionDate": "Date", "transactionCode": "Type"
                        }), use_container_width=True, hide_index=True)

            # Options chain
            st.markdown("##### 📋 Options Chain (Nearest Expiry)")
            calls, puts = options_chain(tkr)
            if calls is not None:
                oc1, oc2 = st.columns(2)
                with oc1:
                    st.markdown("**CALLS**")
                    c2 = calls.copy()
                    c2["impliedVolatility"] = c2["impliedVolatility"].apply(lambda x: f"{x:.1%}")
                    st.dataframe(c2, use_container_width=True, hide_index=True)
                with oc2:
                    st.markdown("**PUTS**")
                    p2 = puts.copy()
                    p2["impliedVolatility"] = p2["impliedVolatility"].apply(lambda x: f"{x:.1%}")
                    st.dataframe(p2, use_container_width=True, hide_index=True)
        else:
            st.error(f"Could not fetch data for {tkr}. Check the ticker symbol.")

    st.divider()

    # Sector Heatmap
    st.markdown("### 🔄 SECTOR ROTATION HEATMAP")
    sec_df = sector_etfs()
    if not sec_df.empty:
        sec_sorted = sec_df.sort_values("Change %")
        colors = ["#3fb950" if x >= 0 else "#f85149" for x in sec_sorted["Change %"]]
        fig2 = go.Figure(go.Bar(
            x=sec_sorted["Change %"], y=sec_sorted["Sector"], orientation="h",
            marker=dict(color=colors),
            text=sec_sorted["Change %"].apply(lambda x: f"{x:+.2f}%"),
            textposition="outside"
        ))
        fig2.update_layout(**CHART, height=380)
        fig2.update_layout(xaxis_title="% Change", margin=dict(l=0, r=60, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)

        # Rotation signal
        top_sec = sec_df.nlargest(1, "Change %")["Sector"].values[0]
        DEFENSIVE = {"Utilities", "Consumer Staples", "Healthcare"}
        OFFENSIVE = {"Technology", "Consumer Disc.", "Comm. Services"}
        if top_sec in DEFENSIVE:
            sig = "🔴 DEFENSIVE ROTATION — Late-cycle signal. Consider de-risking."
            cls = "sentinel-alert"
        elif top_sec in OFFENSIVE:
            sig = "🟢 OFFENSIVE ROTATION — Early/mid-cycle. Risk appetite intact."
            cls = "sentinel-green"
        elif top_sec == "Energy":
            sig = "🟠 ENERGY LEADING — Inflation regime. Watch CPI. Oil stocks may outperform."
            cls = "sentinel-geo"
        else:
            sig = f"🟡 MIXED — {top_sec} leading. No clear rotation signal yet."
            cls = "sentinel-signal"
        st.markdown(f'<div class="{cls}">🔄 ROTATION SIGNAL: {sig}</div>', unsafe_allow_html=True)

    # Finnhub Market News
    if st.session_state.finnhub_key:
        st.divider()
        st.markdown("### 📰 MARKET NEWS (Finnhub)")
        fh_news = finnhub_news(st.session_state.finnhub_key, "general")
        for art in fh_news[:5]:
            title = art.get("headline", "")[:90]
            url   = art.get("url", "#")
            src   = art.get("source", "")
            st.markdown(f'<div class="sentinel-signal"><a href="{url}" target="_blank" '
                        f'style="color:#58a6ff;text-decoration:none">{title}</a><br>'
                        f'<span style="color:#8b949e;font-size:10px">{src}</span></div>',
                        unsafe_allow_html=True)

# ════════════════════════════════════════
# TAB 3 — MACRO (FRED)
# ════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="term-header">📈 MACRO — FRED DATA DASHBOARD</div>', unsafe_allow_html=True)

    if not st.session_state.fred_key:
        st.warning("⚠️ Add your FRED API key in the sidebar to unlock this dashboard.")
        st.info("[Get your free FRED key in 30 seconds → fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)")
    else:
        # Yield Curve
        st.markdown("### 📉 YIELD CURVE")
        YC = {"3M": "DTB3", "2Y": "DGS2", "5Y": "DGS5", "10Y": "DGS10", "30Y": "DGS30"}
        yc_vals = {}
        for lbl, code in YC.items():
            df = fred_series(code, st.session_state.fred_key, 5)
            if df is not None and not df.empty:
                yc_vals[lbl] = df["value"].iloc[-1]

        if yc_vals:
            fig_yc = dark_fig(280)
            fig_yc.add_trace(go.Scatter(
                x=list(yc_vals.keys()), y=list(yc_vals.values()),
                mode="lines+markers", line=dict(color="#58a6ff", width=2.5),
                marker=dict(size=9, color="#58a6ff")
            ))
            fig_yc.add_hline(y=0, line_dash="dash", line_color="#f85149", opacity=0.6,
                             annotation_text="0% (inversion line)")
            fig_yc.update_layout(yaxis_title="Yield (%)", xaxis_title="Maturity")
            st.plotly_chart(fig_yc, use_container_width=True)

            if "2Y" in yc_vals and "10Y" in yc_vals:
                spread = yc_vals["10Y"] - yc_vals["2Y"]
                if spread < 0:
                    st.markdown(f'<div class="sentinel-alert">⚠️ YIELD CURVE INVERTED: 10Y-2Y = {spread:.2f}%. '
                                f'Historical recession signal. Avg lead time: 12-18 months.</div>',
                                unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="sentinel-green">✅ Yield curve normal: 10Y-2Y = +{spread:.2f}%.'
                                f' No inversion signal.</div>', unsafe_allow_html=True)

        st.divider()

        # Key metrics
        st.markdown("### 📊 KEY MACRO INDICATORS")
        MACRO = {
            "CPI (All Urban)": "CPIAUCSL",
            "Core PCE (%)": "PCEPILFE",
            "Fed Funds Rate": "FEDFUNDS",
            "Unemployment U3": "UNRATE",
            "Unemployment U6": "U6RATE",
            "M2 Money Supply": "M2SL",
            "HY Credit Spread": "BAMLH0A0HYM2",
            "IG Credit Spread": "BAMLC0A0CM",
        }
        mc = st.columns(4)
        for i, (name, code) in enumerate(MACRO.items()):
            df = fred_series(code, st.session_state.fred_key, 5)
            with mc[i % 4]:
                if df is not None and not df.empty:
                    cur  = df["value"].iloc[-1]
                    prev = df["value"].iloc[-2] if len(df) > 1 else cur
                    st.metric(name, f"{cur:.2f}", delta=f"{cur-prev:+.2f}")
                else:
                    st.metric(name, "N/A")

        st.divider()

        # CPI Trend
        st.markdown("### 📈 CPI TREND — YEAR-OVER-YEAR")
        cpi_df = fred_series("CPIAUCSL", st.session_state.fred_key, 30)
        if cpi_df is not None and len(cpi_df) > 13:
            cpi_df["yoy"] = cpi_df["value"].pct_change(12) * 100
            recent = cpi_df.dropna(subset=["yoy"]).tail(18)
            fig_cpi = dark_fig(260)
            fig_cpi.add_trace(go.Scatter(
                x=recent["date"], y=recent["yoy"], fill="tozeroy",
                line=dict(color="#f85149", width=2),
                fillcolor="rgba(248,81,73,0.12)"
            ))
            fig_cpi.add_hline(y=2.0, line_dash="dash", line_color="#3fb950",
                             annotation_text="Fed 2% target", annotation_font_color="#3fb950")
            fig_cpi.update_layout(yaxis_title="YoY %")
            st.plotly_chart(fig_cpi, use_container_width=True)

        # 10Y Treasury
        st.markdown("### 📈 10Y TREASURY YIELD TREND")
        ty_df = fred_series("DGS10", st.session_state.fred_key, 36)
        if ty_df is not None and not ty_df.empty:
            recent_ty = ty_df.tail(24)
            fig_ty = dark_fig(240)
            fig_ty.add_trace(go.Scatter(
                x=recent_ty["date"], y=recent_ty["value"], fill="tozeroy",
                line=dict(color="#58a6ff", width=2),
                fillcolor="rgba(88,166,255,0.10)"
            ))
            fig_ty.update_layout(yaxis_title="Yield (%)")
            st.plotly_chart(fig_ty, use_container_width=True)

# ════════════════════════════════════════
# TAB 4 — CRYPTO
# ════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="term-header">💰 CRYPTO DASHBOARD — COINGECKO + YAHOO FINANCE</div>', unsafe_allow_html=True)

    # Global stats
    gdata = crypto_global(st.session_state.coingecko_key)
    if gdata:
        g1, g2, g3, g4 = st.columns(4)
        total_cap = gdata.get("total_market_cap", {}).get("usd", 0)
        g1.metric("Total Market Cap", f"${total_cap/1e12:.2f}T")
        btc_dom = gdata.get("market_cap_percentage", {}).get("btc", 0)
        g2.metric("BTC Dominance", f"{btc_dom:.1f}%")
        eth_dom = gdata.get("market_cap_percentage", {}).get("eth", 0)
        g3.metric("ETH Dominance", f"{eth_dom:.1f}%")
        fv, fl = fear_greed()
        if fv: g4.metric("Fear & Greed", f"{fv}/100", delta=fl)

        # BTC dominance signal
        if btc_dom > 55:
            st.markdown('<div class="sentinel-alert">⚠️ BTC Dominance >55% — Altcoins under pressure. Risk-off within crypto.</div>', unsafe_allow_html=True)
        elif btc_dom < 45:
            st.markdown('<div class="sentinel-green">✅ BTC Dominance <45% — Altcoin season conditions.</div>', unsafe_allow_html=True)

    st.divider()

    # Crypto price table
    st.markdown("### 💹 TOP 15 BY MARKET CAP")
    cdata = crypto_markets(st.session_state.coingecko_key)
    if cdata:
        rows = []
        for c in cdata:
            if not c.get("current_price"): continue
            pct = c.get("price_change_percentage_24h", 0) or 0
            rows.append({
                "Coin": f"{c['name']} ({c['symbol'].upper()})",
                "Price": f"${c['current_price']:,.4f}" if c["current_price"] < 1 else f"${c['current_price']:,.2f}",
                "24h %": f"{pct:+.2f}%",
                "Market Cap": f"${c['market_cap']/1e9:.1f}B",
                "24h Volume": f"${c['total_volume']/1e9:.1f}B",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # BTC Chart
    st.markdown("### 📈 BITCOIN — 3 MONTHS")
    try:
        bh = yf.Ticker("BTC-USD").history(period="3mo")
        if not bh.empty:
            fig_btc = dark_fig(320)
            fig_btc.add_trace(go.Candlestick(
                x=bh.index, open=bh["Open"], high=bh["High"], low=bh["Low"], close=bh["Close"],
                increasing_line_color="#3fb950", decreasing_line_color="#f85149"
            ))
            fig_btc.update_layout(xaxis_rangeslider_visible=False)
            st.plotly_chart(fig_btc, use_container_width=True)
    except Exception:
        st.info("BTC chart unavailable right now.")

    # ETH Chart
    st.markdown("### 📈 ETHEREUM — 3 MONTHS")
    try:
        eh = yf.Ticker("ETH-USD").history(period="3mo")
        if not eh.empty:
            fig_eth = dark_fig(280)
            fig_eth.add_trace(go.Candlestick(
                x=eh.index, open=eh["Open"], high=eh["High"], low=eh["Low"], close=eh["Close"],
                increasing_line_color="#3fb950", decreasing_line_color="#f85149"
            ))
            fig_eth.update_layout(xaxis_rangeslider_visible=False)
            st.plotly_chart(fig_eth, use_container_width=True)
    except Exception:
        pass

# ════════════════════════════════════════
# TAB 5 — POLYMARKET
# ════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="term-header">🎲 POLYMARKET — PREDICTION INTELLIGENCE & UNUSUAL FLOW</div>', unsafe_allow_html=True)
    st.caption("Polymarket is a public prediction market. Crowd probabilities + unusual volume may signal informed positioning.")

    poly_search = st.text_input("🔍 Filter markets by keyword", placeholder="Fed rate, oil, Taiwan, gold, recession…")

    all_poly = polymarket_markets(60)
    filtered_poly = [m for m in all_poly if not poly_search or
                     poly_search.lower() in str(m.get("question","")).lower() or
                     poly_search.lower() in str(m.get("title","")).lower()] if poly_search else all_poly

    # Unusual activity
    unusual = detect_unusual_poly(all_poly)
    if unusual:
        st.markdown("### 🚨 UNUSUAL ACTIVITY DETECTED")
        st.caption("Markets where 24h volume is ≥38% of total — signals recent surge in positioning.")
        for m in unusual:
            title = m.get("question", m.get("title", ""))[:80]
            v24  = float(m.get("volume24hr", 0) or 0)
            vtot = float(m.get("volume", 0) or 0)
            ratio = v24 / vtot * 100 if vtot > 0 else 0
            st.markdown(f'<div class="sentinel-alert">🚨 <strong>UNUSUAL:</strong> {title}…<br>'
                        f'24h Vol: <strong>${v24:,.0f}</strong> ({ratio:.0f}% of total) | Total: ${vtot:,.0f}</div>',
                        unsafe_allow_html=True)
        st.divider()

    # All markets
    col_pm, col_guide = st.columns([3, 1])
    with col_pm:
        st.markdown(f"### 📋 ACTIVE MARKETS BY 24H VOLUME")
        for m in filtered_poly[:25]:
            title  = m.get("question", m.get("title", "Unknown"))[:90]
            v24    = float(m.get("volume24hr", 0) or 0)
            vtot   = float(m.get("volume", 0) or 0)
            outcomes   = m.get("outcomes", [])
            out_prices = m.get("outcomePrices", [])

            prob_html = ""
            if outcomes and out_prices:
                try:
                    prices = json.loads(out_prices) if isinstance(out_prices, str) else out_prices
                    parts  = []
                    for i, outcome in enumerate(outcomes[:2]):
                        if i < len(prices):
                            p = float(prices[i]) * 100
                            col_str = "#3fb950" if p > 50 else "#f85149"
                            parts.append(f'<span style="color:{col_str}">{outcome}: {p:.0f}%</span>')
                    prob_html = " &nbsp;|&nbsp; ".join(parts) + "<br>"
                except Exception:
                    pass

            st.markdown(f'<div class="sentinel-poly"><strong>{title}</strong><br>'
                        f'{prob_html}'
                        f'<span style="color:#8b949e;font-size:11px">24h: ${v24:,.0f} | Total: ${vtot:,.0f}</span></div>',
                        unsafe_allow_html=True)

    with col_guide:
        st.markdown("### 📖 HOW TO READ")
        st.markdown("""
<div class="sentinel-signal" style="font-size:11px">
<strong>Unusual Activity Triggers:</strong><br><br>
• 24h vol ≥38% of total vol<br>
• Sudden probability shift<br>
• New market with big instant liquidity<br>
• Heavy pre-event positioning<br><br>
<strong>Convergence Signal:</strong><br>
When Polymarket + FRED data point the same direction → strongest free signal available<br><br>
<strong>⚠️ Remember:</strong><br>
Prediction markets = crowd odds. Not guaranteed. Use alongside macro + geo data.
</div>
""", unsafe_allow_html=True)



# ════════════════════════════════════════
# TAB 6 — GEO (with Interactive Globe)
# ════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="term-header">🌍 GEOPOLITICAL INTELLIGENCE — INTERACTIVE GLOBE + GDELT + NEWSAPI</div>', unsafe_allow_html=True)
    st.markdown("### 🌐 SENTINEL GEOPOLITICAL GLOBE")
    st.caption("Drag to rotate · Scroll to zoom · Click markers for intel · Use left panel to filter by category")
    globe_path = pathlib.Path(__file__).parent / "globe.html"
    if globe_path.exists():
        globe_html = globe_path.read_text(encoding="utf-8")
        components.html(globe_html, height=620, scrolling=False)
    else:
        st.error("globe.html not found. Make sure it's in the same folder as sentinel_app.py")
    st.divider()
    THEATERS = {
        "Middle East + Oil + Hormuz": "Middle East Iran oil Hormuz",
        "China + Taiwan + Semiconductors": "China Taiwan semiconductor chips trade",
        "Russia + Ukraine + Energy + Grain": "Russia Ukraine energy grain wheat NATO",
        "Africa + Cobalt + Lithium + Coup": "Africa cobalt lithium coup mining Sahel",
        "Red Sea + Suez + Shipping": "Red Sea Suez shipping Houthi container",
        "South China Sea + Trade": "South China Sea shipping trade dispute",
    }
    geo_col1, geo_col2 = st.columns([3, 1])
    with geo_col1:
        theater_sel = st.selectbox("📡 Select Theater for News Feed", list(THEATERS.keys()) + ["Custom search…"])
        custom_q = ""
        if theater_sel == "Custom search…":
            custom_q = st.text_input("Custom GDELT query")
        query = custom_q if custom_q else THEATERS.get(theater_sel, "")
        if query:
            st.markdown(f"#### GDELT FEED — `{query}`")
            arts = gdelt_news(query, max_rec=12)
            if arts:
                for art in arts:
                    t = art.get("title", "")[:100]
                    u = art.get("url", "#")
                    dom = art.get("domain", "")
                    sd = art.get("seendate", "")
                    date_str = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
                    st.markdown(f'<div class="sentinel-geo"><a href="{u}" target="_blank" style="color:#e3b341;text-decoration:none;font-weight:bold">{t}</a><br><span style="color:#8b949e;font-size:10px">{dom} | {date_str}</span></div>', unsafe_allow_html=True)
            if st.session_state.newsapi_key:
                st.divider()
                st.markdown("#### NEWSAPI LAYER")
                for art in newsapi_headlines(st.session_state.newsapi_key, query)[:5]:
                    title = art.get("title", "")
                    if not title or "[Removed]" in title: continue
                    u = art.get("url", "#"); src = art.get("source", {}).get("name", ""); pub = art.get("publishedAt", "")[:10]
                    st.markdown(f'<div class="sentinel-signal"><a href="{u}" target="_blank" style="color:#58a6ff;text-decoration:none">{title[:100]}</a><br><span style="color:#8b949e;font-size:10px">{src} | {pub}</span></div>', unsafe_allow_html=True)
    with geo_col2:
        st.markdown("### ⚠️ THEATERS")
        for name, status in {"🔴 Middle East":"CRITICAL","🔴 Ukraine":"ACTIVE","🔴 Red Sea":"DISRUPTED","🟠 Sahel":"ELEVATED","🟠 Hormuz":"ELEVATED","🟡 Taiwan":"MONITORING","🟡 S.China Sea":"MONITORING"}.items():
            color = "#f85149" if status in ("ACTIVE","CRITICAL","DISRUPTED") else ("#e3b341" if status=="ELEVATED" else "#8b949e")
            st.markdown(f'<div style="background:#0d1117;border:1px solid #1f2937;border-radius:4px;padding:6px 10px;margin:3px 0;display:flex;justify-content:space-between"><span style="font-size:11px">{name}</span><span style="color:{color};font-size:9px;font-weight:bold">{status}</span></div>', unsafe_allow_html=True)
        st.divider()
        st.markdown("### 📖 CONFIDENCE")
        st.markdown("`HIGH` Multiple confirmed  \n`MEDIUM` Limited sources  \n`LOW` Single source  \n`UNCONFIRMED` Unverified")

# ════════════════════════════════════════
# TAB 7 — SENTINEL AI CHAT
# ════════════════════════════════════════
with tabs[6]:
    st.markdown('<div class="term-header">🤖 SENTINEL AI — POWERED BY GOOGLE GEMINI</div>', unsafe_allow_html=True)

    if not st.session_state.gemini_key:
        st.warning("⚠️ Add your **free Gemini API key** in the sidebar to activate SENTINEL AI.")
        st.info("[Get a free key at Google AI Studio in 60 seconds →](https://aistudio.google.com/app/apikey)")
        st.markdown("""
**Once activated, you can ask things like:**
- `/brief` — Full morning briefing
- `/flash NVDA` — Quick stock snapshot
- `/geo Red Sea` — Geopolitical dashboard with market impact
- `/scenario Gold` — Bull / base / bear scenario tree
- `/poly Fed rate` — Polymarket analysis with unusual flow
- `/rotate` — Sector rotation read
- `What does a yield curve inversion mean for my portfolio?`
- `BTC just dumped 10%. Walk me through the second-order effects.`
- `What's happening in the Middle East and how does it affect oil?`
        """)
    else:
        # Chat display
        if not st.session_state.chat_history:
            st.markdown("""
<div class="sentinel-green">
⚡ SENTINEL AI ONLINE — Gemini connected. Live market data injected into every response.<br><br>
Try: &nbsp;<code>/brief</code> &nbsp; <code>/flash NVDA</code> &nbsp; <code>/scenario Gold</code> &nbsp; <code>/geo Red Sea</code> &nbsp; <code>/poly Fed</code><br>
Or just ask anything in plain English.
</div>
""", unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">👤 &nbsp;{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                content = msg["content"].replace("<", "&lt;").replace(">", "&gt;")
                st.markdown(f'<div class="chat-ai">⚡ SENTINEL<br><br>{content}</div>', unsafe_allow_html=True)

        # Input row
        st.divider()
        inp_col, btn_col = st.columns([5, 1])
        with inp_col:
            user_input = st.text_input("Ask SENTINEL…",
                placeholder="/brief  |  /flash TSLA  |  /scenario Gold  |  or any question",
                key="chat_inp", label_visibility="collapsed")
        with btn_col:
            send = st.button("⚡ Send", use_container_width=True)

        # Quick buttons
        st.markdown("**Quick commands:**")
        qb = st.columns(6)
        QUICK = {
            "🌅 Brief": "/brief",
            "🔄 Rotate": "/rotate",
            "📰 Sentiment": "/sentiment",
            "🎲 Poly Fed": "/poly Fed rate cut",
            "🌍 Red Sea": "/geo Red Sea",
            "📊 Scenario BTC": "/scenario Bitcoin",
        }
        for col, (label, cmd) in zip(qb, QUICK.items()):
            with col:
                if st.button(label, use_container_width=True, key=f"qb_{label}"):
                    st.session_state.chat_history.append({"role": "user", "content": cmd})
                    with st.spinner("⚡ SENTINEL processing…"):
                        resp = gemini_response(cmd, st.session_state.chat_history[:-1], market_snapshot_str())
                    st.session_state.chat_history.append({"role": "assistant", "content": resp})
                    st.rerun()

        # Clear
        if st.button("🗑 Clear Chat"):
            st.session_state.chat_history = []
            st.rerun()

        # Handle send
        if (send or user_input) and user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.spinner("⚡ SENTINEL processing…"):
                resp = gemini_response(user_input, st.session_state.chat_history[:-1], market_snapshot_str())
            st.session_state.chat_history.append({"role": "assistant", "content": resp})
            st.rerun()

# ── FOOTER ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(f'<p style="color:#1f2937;font-family:Courier New;font-size:10px;text-align:center">'
            f'⚡ SENTINEL | {now_pst()} | Yahoo Finance • FRED • Polymarket • GDELT • CoinGecko • Finnhub • NewsAPI<br>'
            f'Research only — not financial advice. Built for the retail power investor who refuses to pay for a Bloomberg terminal.</p>',
            unsafe_allow_html=True)
