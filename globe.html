#!/usr/bin/env python3
"""SENTINEL — Bloomberg Intelligence Terminal"""
import streamlit as st, streamlit.components.v1 as components
try:
    import yfinance as yf
except ImportError:
    st.error("yfinance missing. Check requirements.txt in repo root."); st.stop()
import requests, pandas as pd, json, pathlib
from datetime import datetime
import pytz

st.set_page_config(page_title="SENTINEL",page_icon="⚡",layout="wide",initial_sidebar_state="expanded")
PST=pytz.timezone("US/Pacific")
def now_pst(): return datetime.now(PST).strftime("%Y-%m-%d %H:%M:%S")
def date_pst(): return datetime.now(PST).strftime("%A, %B %d %Y")

# ── BLOOMBERG CSS ─────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{--bg:#070809;--bg2:#0d0e10;--bg3:#111316;--border:#1e2025;--amber:#f5a623;
  --red:#ff3b3b;--green:#00e676;--blue:#4fc3f7;--text:#d0d3d8;--text2:#8a8f99;
  --text3:#444851;--white:#f0f2f5;}
*{font-family:'IBM Plex Mono','Courier New',monospace!important;}
.stApp,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;}
[data-testid="stHeader"]{background:var(--bg)!important;}
[data-testid="stSidebar"]{background:var(--bg2)!important;border-right:1px solid var(--border)!important;}
[data-testid="stSidebar"] *{font-size:11px!important;}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{color:var(--amber)!important;font-size:10px!important;letter-spacing:2px;}
.stTabs [data-baseweb="tab-list"]{background:var(--bg2)!important;border-bottom:1px solid var(--amber)!important;gap:0!important;padding:0!important;}
.stTabs [data-baseweb="tab"]{color:var(--text2)!important;font-size:11px!important;letter-spacing:1px!important;padding:6px 16px!important;border-right:1px solid var(--border)!important;border-radius:0!important;background:transparent!important;}
.stTabs [aria-selected="true"]{color:var(--bg)!important;background:var(--amber)!important;font-weight:600!important;}
[data-testid="stMetric"]{background:var(--bg2)!important;border:1px solid var(--border)!important;border-top:2px solid var(--amber)!important;border-radius:0!important;padding:8px!important;}
[data-testid="stMetricLabel"]{color:var(--text2)!important;font-size:9px!important;letter-spacing:1px;}
[data-testid="stMetricValue"]{color:var(--white)!important;font-size:17px!important;font-weight:600!important;}
.stTextInput>div>div>input,.stTextArea>div>div>textarea,.stSelectbox>div>div{background:var(--bg2)!important;color:var(--text)!important;border:1px solid #2a2d33!important;border-radius:0!important;font-size:11px!important;}
.stButton>button{background:var(--bg2)!important;color:var(--amber)!important;border:1px solid var(--amber)!important;border-radius:0!important;font-size:10px!important;letter-spacing:1px!important;padding:4px 12px!important;}
.stButton>button:hover{background:var(--amber)!important;color:var(--bg)!important;}
hr{border-color:var(--border)!important;margin:8px 0!important;}
.streamlit-expanderHeader{background:var(--bg2)!important;border:1px solid var(--border)!important;border-radius:0!important;color:var(--amber)!important;font-size:10px!important;}
#MainMenu,footer,[data-testid="stDecoration"],[data-testid="stToolbar"]{display:none!important;}
h1,h2,h3,h4{color:var(--amber)!important;font-size:11px!important;letter-spacing:2px!important;font-weight:600!important;}
p,li{font-size:11px!important;}
.bb-sec{border:1px solid var(--border);background:var(--bg2);margin-bottom:8px;}
.bb-sec-t{background:var(--bg3);border-bottom:1px solid var(--border);padding:4px 10px;font-size:9px;letter-spacing:2px;color:var(--amber);text-transform:uppercase;}
.bb-sec-b{padding:8px 10px;}
.bb-ni{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid var(--border);align-items:flex-start;}
.bb-ni:last-child{border-bottom:none;}
.bb-nn{color:var(--text3);font-size:9px;min-width:16px;}
.bb-nd{color:var(--amber);font-size:9px;min-width:55px;}
.bb-nl{color:var(--text);font-size:11px;text-decoration:none;line-height:1.4;}
.bb-nl:hover{color:var(--amber);}
.bb-ns{color:var(--text3);font-size:9px;margin-top:2px;}
.bb-tbl{width:100%;border-collapse:collapse;font-size:11px;}
.bb-tbl th{color:var(--amber);font-size:9px;letter-spacing:1px;padding:4px 8px;border-bottom:1px solid var(--border);text-align:left;}
.bb-tbl td{padding:4px 8px;border-bottom:1px solid var(--border);}
.bb-tbl tr:hover td{background:rgba(245,166,35,0.04);}
.bb-tbl td.up{color:var(--green);}.bb-tbl td.dn{color:var(--red);}.bb-tbl td.kk{color:var(--amber);}.bb-tbl td.dm{color:var(--text2);}
.bb-mr{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);font-size:11px;}
.bb-mr:last-child{border-bottom:none;}
.bb-poly{padding:7px 0;border-bottom:1px solid var(--border);}
.bb-poly:last-child{border-bottom:none;}
.bb-pty{font-size:10px;color:var(--text);margin-bottom:4px;}
.bb-pla{text-decoration:none;color:inherit;}
.bb-pla:hover .bb-pty{color:var(--amber);}
.bb-pm{display:flex;justify-content:space-between;font-size:9px;color:var(--text2);}
.yp{color:var(--green);font-weight:600;}.np{color:var(--red);font-weight:600;}
.bb-ac{border-left:3px solid var(--red);background:rgba(255,59,59,0.06);padding:8px 10px;margin:4px 0;font-size:10px;}
.bb-ae{border-left:3px solid var(--amber);background:rgba(245,166,35,0.06);padding:8px 10px;margin:4px 0;font-size:10px;}
.bb-ai{border-left:3px solid var(--blue);background:rgba(79,195,247,0.06);padding:8px 10px;margin:4px 0;font-size:10px;}
.bb-ag{border-left:3px solid var(--green);background:rgba(0,230,118,0.06);padding:8px 10px;margin:4px 0;font-size:10px;}
.bb-og{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border);border:1px solid var(--border);}
.bb-oc{background:var(--bg2);}
.bb-oh{background:var(--bg3);padding:4px 8px;font-size:9px;letter-spacing:2px;text-align:center;border-bottom:1px solid var(--border);}
.bb-ch{color:var(--green);}.bb-ph{color:var(--red);}
.bb-or{display:grid;grid-template-columns:1.2fr 0.8fr 0.8fr 1fr;padding:3px 8px;border-bottom:1px solid var(--border);font-size:10px;}
.bb-or:hover{background:rgba(245,166,35,0.05);}
.bb-ol{color:var(--text2);font-size:9px;}.bb-os{color:var(--amber);font-weight:600;}.bb-oo{color:var(--white);}.bb-ov{color:var(--text2);}.bb-oiv{color:var(--blue);}
.bb-in{display:grid;grid-template-columns:2fr 1fr 0.7fr 0.9fr;padding:5px 8px;border-bottom:1px solid var(--border);font-size:10px;align-items:center;}
.bb-in:hover{background:rgba(245,166,35,0.04);}
.bb-inb{color:var(--green);font-weight:600;}.bb-ins{color:var(--red);font-weight:600;}
.bb-cu{background:var(--bg3);border-left:2px solid var(--amber);padding:8px 12px;margin:6px 0;font-size:11px;}
.bb-ca{background:var(--bg2);border-left:2px solid var(--green);padding:10px 12px;margin:6px 0;font-size:11px;white-space:pre-wrap;line-height:1.7;}
.bb-cl{font-size:9px;letter-spacing:1px;margin-bottom:4px;}
.bb-sr{display:flex;align-items:center;gap:8px;padding:3px 0;border-bottom:1px solid var(--border);font-size:10px;}
.bb-sn{min-width:115px;color:var(--text);}
.bb-sbw{flex:1;height:9px;background:var(--bg3);}
.bb-sbf{height:9px;}
.bb-sv{min-width:52px;text-align:right;}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px;}
.dot-g{background:var(--green);box-shadow:0 0 5px var(--green);}
.dot-a{background:var(--amber);box-shadow:0 0 5px var(--amber);}
.dot-r{background:var(--red);box-shadow:0 0 5px var(--red);animation:bk 1s infinite;}
.dot-x{background:var(--text3);}
@keyframes bk{0%,100%{opacity:1}50%{opacity:0.2}}
.tc{color:var(--red);font-weight:600;font-size:9px;}
.te{color:var(--amber);font-weight:600;font-size:9px;}
.tw{color:var(--blue);font-weight:600;font-size:9px;}
</style>"""
st.markdown(CSS, unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────────────────────────────────────────────
DEFS = {
    "gemini_key":"", "fred_key":"", "finnhub_key":"",
    "newsapi_key":"", "coingecko_key":"", "chat_history":[],
    "watchlist":["SPY","QQQ","NVDA","AAPL","GLD","TLT","BTC-USD"],
    "macro_theses":"", "geo_watch":""
}
for k,v in DEFS.items():
    if k not in st.session_state: st.session_state[k]=v

# ── TRADINGVIEW HELPERS ───────────────────────────────────────────────────────
def tv_chart(symbol="NASDAQ:SPY", height=460):
    sid = symbol.replace(":","_").replace("-","_").replace("!","x")
    components.html(f"""<div id="tv_{sid}" style="height:{height}px;background:#070809"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({{"autosize":true,"symbol":"{symbol}","interval":"D",
"timezone":"America/Los_Angeles","theme":"dark","style":"1","locale":"en",
"toolbar_bg":"#0d0e10","backgroundColor":"rgba(7,8,9,1)",
"gridColor":"rgba(30,32,37,0.8)","enable_publishing":false,"withdateranges":true,
"allow_symbol_change":true,"container_id":"tv_{sid}",
"studies":["RSI@tv-basicstudies","MACD@tv-basicstudies","Volume@tv-basicstudies"]}});
</script>""", height=height+10, scrolling=False)

def tv_mini(symbol, height=180):
    components.html(f"""<iframe scrolling="no" allowtransparency="true" frameborder="0"
style="width:100%;height:{height}px;border:1px solid #1e2025"
src="https://s.tradingview.com/embed-widget/mini-symbol-overview/?locale=en#%7B%22symbol%22%3A%22{symbol}%22%2C%22dateRange%22%3A%221M%22%2C%22colorTheme%22%3A%22dark%22%2C%22trendLineColor%22%3A%22%23f5a623%22%2C%22underLineColor%22%3A%22rgba(245%2C166%2C35%2C0.08)%22%2C%22isTransparent%22%3Atrue%2C%22width%22%3A%22100%25%22%2C%22height%22%3A{height}%7D">
</iframe>""", height=height+4, scrolling=False)

def tv_tape():
    components.html("""<iframe scrolling="no" allowtransparency="true" frameborder="0"
style="width:100%;height:46px;border:none;background:#0d0e10"
src="https://s.tradingview.com/embed-widget/ticker-tape/?locale=en#%7B%22symbols%22%3A%5B%7B%22proName%22%3A%22FOREXCOM%3ASPXUSD%22%2C%22title%22%3A%22S%26P+500%22%7D%2C%7B%22proName%22%3A%22FOREXCOM%3ANSXUSD%22%2C%22title%22%3A%22Nasdaq%22%7D%2C%7B%22proName%22%3A%22BITSTAMP%3ABTCUSD%22%7D%2C%7B%22proName%22%3A%22BITSTAMP%3AETHUSD%22%7D%2C%7B%22description%22%3A%22Gold%22%2C%22proName%22%3A%22OANDA%3AXAUUSD%22%7D%2C%7B%22description%22%3A%22Oil%22%2C%22proName%22%3A%22NYMEX%3ACL1%21%22%7D%2C%7B%22description%22%3A%22DXY%22%2C%22proName%22%3A%22TVC%3ADXY%22%7D%5D%2C%22colorTheme%22%3A%22dark%22%2C%22isTransparent%22%3Atrue%2C%22showSymbolLogo%22%3Atrue%2C%22displayMode%22%3A%22compact%22%2C%22locale%22%3A%22en%22%7D">
</iframe>""", height=48, scrolling=False)

def tv_forex(height=280):
    components.html(f"""<iframe scrolling="no" allowtransparency="true" frameborder="0"
style="width:100%;height:{height}px;border:1px solid #1e2025"
src="https://s.tradingview.com/embed-widget/forex-cross-rates/?locale=en#%7B%22currencies%22%3A%5B%22EUR%22%2C%22USD%22%2C%22JPY%22%2C%22GBP%22%2C%22CHF%22%2C%22AUD%22%2C%22CAD%22%2C%22CNY%22%5D%2C%22colorTheme%22%3A%22dark%22%2C%22width%22%3A%22100%25%22%2C%22height%22%3A{height}%7D">
</iframe>""", height=height+4, scrolling=False)

# ── DATA FETCHERS ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def yquote(t):
    try:
        h = yf.Ticker(t).history(period="2d")
        if h.empty: return None
        p = h["Close"].iloc[-1]; prev = h["Close"].iloc[-2] if len(h)>1 else p
        return {"ticker":t, "price":round(p,4), "change":round(p-prev,4),
                "pct":round((p-prev)/prev*100,2), "volume":int(h["Volume"].iloc[-1]) if "Volume" in h.columns else 0}
    except: return None

@st.cache_data(ttl=300)
def multi_q(tickers): return [q for t in tickers if (q:=yquote(t))]

@st.cache_data(ttl=600)
def fred_fetch(sid, key, lim=36):
    if not key: return None
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id":sid,"api_key":key,"sort_order":"desc","limit":lim,"file_type":"json"},timeout=10)
        df = pd.DataFrame(r.json().get("observations",[]))
        df["value"] = pd.to_numeric(df["value"],errors="coerce")
        df["date"]  = pd.to_datetime(df["date"])
        return df.dropna(subset=["value"]).sort_values("date")
    except: return None

@st.cache_data(ttl=300)
def poly_mkt(lim=80):
    try:
        return requests.get("https://gamma-api.polymarket.com/markets",
            params={"limit":lim,"order":"volume24hr","ascending":"false","active":"true"},timeout=10).json()
    except: return []

@st.cache_data(ttl=300)
def fear_greed():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1",timeout=8).json()
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except: return None, None

@st.cache_data(ttl=600)
def cg_markets(key=""):
    try:
        h = {"x-cg-demo-api-key":key} if key else {}
        return requests.get("https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency":"usd","order":"market_cap_desc","per_page":20,"page":1,"price_change_percentage":"24h"},
            headers=h, timeout=10).json()
    except: return []

@st.cache_data(ttl=600)
def cg_global(key=""):
    try:
        h = {"x-cg-demo-api-key":key} if key else {}
        return requests.get("https://api.coingecko.com/api/v3/global",headers=h,timeout=8).json().get("data",{})
    except: return {}

@st.cache_data(ttl=600)
def gdelt_news(q, n=12):
    try:
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query":q,"mode":"artlist","maxrecords":n,"format":"json","timespan":"24h"},timeout=12)
        return r.json().get("articles",[])
    except: return []

@st.cache_data(ttl=300)
def newsapi_fetch(key, q="finance"):
    if not key: return []
    try:
        return requests.get("https://newsapi.org/v2/everything",
            params={"q":q,"language":"en","sortBy":"publishedAt","pageSize":10,"apiKey":key},timeout=10).json().get("articles",[])
    except: return []

@st.cache_data(ttl=300)
def fh_news(key):
    if not key: return []
    try:
        return requests.get("https://finnhub.io/api/v1/news",
            params={"category":"general","token":key},timeout=10).json()[:15]
    except: return []

@st.cache_data(ttl=600)
def fh_insider(ticker, key):
    if not key: return []
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol":ticker,"token":key},timeout=10)
        return r.json().get("data",[])[:10]
    except: return []

@st.cache_data(ttl=300)
def get_vix():
    try:
        h = yf.Ticker("^VIX").history(period="2d")
        return round(h["Close"].iloc[-1],2) if not h.empty else None
    except: return None

@st.cache_data(ttl=600)
def opt_chain(ticker):
    try:
        t = yf.Ticker(ticker); exps = t.options
        if not exps: return None, None
        ch = t.option_chain(exps[0])
        cols = ["strike","lastPrice","volume","openInterest","impliedVolatility"]
        return ch.calls[cols].head(8), ch.puts[cols].head(8)
    except: return None, None

@st.cache_data(ttl=600)
def sector_data():
    S = {"Tech":"XLK","Fins":"XLF","Energy":"XLE","Health":"XLV","Staples":"XLP",
         "Utils":"XLU","C.Disc":"XLY","Matls":"XLB","Comm":"XLC","R.Est":"XLRE","Indust":"XLI"}
    rows = []
    for name,tkr in S.items():
        q = yquote(tkr)
        if q: rows.append({"Sector":name,"ETF":tkr,"Price":q["price"],"Pct":q["pct"]})
    return pd.DataFrame(rows)

def unusual_poly(mks):
    out = []
    for m in mks:
        try:
            v24=float(m.get("volume24hr",0) or 0); vtot=float(m.get("volume",0) or 0)
            if vtot>0 and v24/vtot>0.38 and v24>5000: out.append(m)
        except: pass
    return out[:8]

def poly_pct(m):
    try:
        pp = m.get("outcomePrices",[])
        p = json.loads(pp) if isinstance(pp,str) else pp
        return float(p[0])*100 if p else 50
    except: return 50

def msnap():
    try:
        parts = [f"{q['ticker']} {q['price']:,.2f}({q['pct']:+.2f}%)" for q in multi_q(["SPY","QQQ","GLD","CL=F","BTC-USD"])]
        v = get_vix()
        if v: parts.append(f"VIX {v}")
        return " | ".join(parts)
    except: return ""

def quotecard(label, price, pct, amber_top=True):
    c = "#00e676" if pct>=0 else "#ff3b3b"
    s = "+" if pct>=0 else ""
    border_color = "#f5a623" if amber_top else c
    return f"""<div style="background:#0d0e10;border:1px solid #1e2025;border-top:2px solid {border_color};padding:7px;text-align:center">
  <div style="color:#8a8f99;font-size:8px;letter-spacing:1px">{label}</div>
  <div style="color:#f0f2f5;font-size:15px;font-weight:600">{price}</div>
  <div style="color:{c};font-size:10px">{s}{pct:.2f}%</div></div>"""

# ── GEMINI — AUTO MODEL SELECTION ─────────────────────────────────────────────
SYS = """You are SENTINEL — a Bloomberg-grade financial and geopolitical intelligence terminal for a retail power investor in PST.
VOICE: Adaptive. Simple language, deep analysis. Define jargon on first use. Trace second and third-order effects always.
DATA: Yahoo Finance, FRED (CPI/PCE/rates/GDP/M2/spreads), Polymarket, GDELT, CoinGecko, Finnhub, NewsAPI, CBOE, Fear & Greed.
ASSETS: US Equities/ETFs, Options, Crypto (BTC/ETH/alts/dominance), Commodities (WTI/Gold/Silver/Copper/Wheat), Fixed Income, Forex.
GEO: Middle East/Iran/Houthi, China/Taiwan/TSMC, Russia/Ukraine, Sub-Saharan Africa/minerals, Red Sea/Suez shipping.
RULES: Never fabricate. Always bear case. Label confidence HIGH/MEDIUM/LOW/UNCONFIRMED. Timestamp PST. Full ripple chains. Polymarket=crowd odds. Trade ideas=research only.
FORMATS: /brief /flash [ticker] /scenario [asset] /geo [region] /poly [topic] /rotate /sentiment /idea [theme]"""

def gemini_chat(msg, history, ctx=""):
    if not st.session_state.gemini_key:
        return "Add Gemini API key in sidebar.\nFree: https://aistudio.google.com/app/apikey"
    try:
        import google.generativeai as genai
        genai.configure(api_key=st.session_state.gemini_key)
        model = None
        for mn in ["gemini-2.0-flash","gemini-1.5-flash","gemini-1.5-pro","gemini-pro"]:
            try: model = genai.GenerativeModel(model_name=mn, system_instruction=SYS); break
            except: continue
        if not model:
            return ("No Gemini model available. List your models:\n"
                    "curl \"https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY\"\n\n"
                    "Or Python:\nimport google.generativeai as genai\n"
                    "genai.configure(api_key='YOUR_KEY')\n"
                    "for m in genai.list_models():\n"
                    "  if 'generateContent' in m.supported_generation_methods:\n"
                    "    print(m.name)")
        full_ctx = ""
        if st.session_state.macro_theses: full_ctx += f"\nMacro theses: {st.session_state.macro_theses}"
        if st.session_state.geo_watch:    full_ctx += f"\nGeo watch: {st.session_state.geo_watch}"
        if st.session_state.watchlist:    full_ctx += f"\nWatchlist: {', '.join(st.session_state.watchlist)}"
        if ctx: full_ctx += f"\nLive market: {ctx}"
        gh = []
        for m in history[-12:]:
            role = "user" if m["role"]=="user" else "model"
            gh.append({"role":role,"parts":[m["content"]]})
        chat = model.start_chat(history=gh)
        return chat.send_message(f"{full_ctx}\n\n{msg}" if full_ctx else msg).text
    except ImportError:
        return "google-generativeai not in requirements.txt"
    except Exception as e:
        err = str(e)
        if "404" in err or "not found" in err.lower():
            return (f"Model not found (404). To list YOUR available models:\n\n"
                    f"curl \"https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY\"\n\n"
                    f"Python:\nimport google.generativeai as genai\n"
                    f"genai.configure(api_key='YOUR_KEY')\n"
                    f"for m in genai.list_models():\n"
                    f"  if 'generateContent' in m.supported_generation_methods:\n"
                    f"    print(m.name)\n\n"
                    f"SENTINEL auto-tries: gemini-2.0-flash → gemini-1.5-flash → gemini-1.5-pro\n"
                    f"Original: {err}")
        return f"Gemini error: {err}"

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""<div style="background:#0d0e10;border-bottom:2px solid #f5a623;padding:8px 4px;margin-bottom:12px">
      <div style="color:#f5a623;font-size:16px;font-weight:700;letter-spacing:4px">⚡ SENTINEL</div>
      <div style="color:#444851;font-size:9px;letter-spacing:1px">{date_pst()}</div>
      <div style="color:#f5a623;font-size:10px;margin-top:2px">{now_pst()}</div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div style="color:#f5a623;font-size:9px;letter-spacing:2px;margin-bottom:8px">▶ API KEYS</div>', unsafe_allow_html=True)
    with st.expander("🤖 Gemini AI — Required"):
        st.caption("[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)")
        st.session_state.gemini_key = st.text_input("Key",value=st.session_state.gemini_key,type="password",key="gk")
    with st.expander("📊 Finnhub"):
        st.caption("[finnhub.io/register](https://finnhub.io/register)")
        st.session_state.finnhub_key = st.text_input("Key",value=st.session_state.finnhub_key,type="password",key="fhk")
    with st.expander("📈 FRED Macro"):
        st.caption("[fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)")
        st.session_state.fred_key = st.text_input("Key",value=st.session_state.fred_key,type="password",key="frk")
    with st.expander("📰 NewsAPI"):
        st.caption("[newsapi.org/register](https://newsapi.org/register)")
        st.session_state.newsapi_key = st.text_input("Key",value=st.session_state.newsapi_key,type="password",key="nak")
    with st.expander("💰 CoinGecko (optional)"):
        st.caption("[coingecko.com](https://www.coingecko.com/en/api/pricing)")
        st.session_state.coingecko_key = st.text_input("Key",value=st.session_state.coingecko_key,type="password",key="cgk")

    st.divider()
    st.markdown('<div style="color:#f5a623;font-size:9px;letter-spacing:2px;margin-bottom:8px">▶ CONNECTION STATUS</div>', unsafe_allow_html=True)
    STATUS = [
        ("Yahoo Finance", True), ("Polymarket", True), ("GDELT", True), ("TradingView", True),
        ("FRED", bool(st.session_state.fred_key)),
        ("Finnhub", bool(st.session_state.finnhub_key)),
        ("NewsAPI", bool(st.session_state.newsapi_key)),
        ("Gemini AI", bool(st.session_state.gemini_key)),
    ]
    for api, ok in STATUS:
        d = "dot-g" if ok else "dot-x"
        st.markdown(f'<div style="font-size:10px;padding:2px 0"><span class="dot {d}"></span>{api}</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown('<div style="color:#f5a623;font-size:9px;letter-spacing:2px;margin-bottom:8px">▶ SESSION CONTEXT</div>', unsafe_allow_html=True)
    st.session_state.macro_theses = st.text_area("Macro theses",value=st.session_state.macro_theses,placeholder="e.g. Watching Fed pivot...",height=60,key="mth")
    st.session_state.geo_watch = st.text_area("Geo watch",value=st.session_state.geo_watch,placeholder="e.g. Red Sea, Taiwan...",height=50,key="gww")
    wl = st.text_input("Watchlist (comma-separated)",value=",".join(st.session_state.watchlist),key="wlin")
    st.session_state.watchlist = [t.strip().upper() for t in wl.split(",") if t.strip()]

# ── TICKER TAPE + HEADER ──────────────────────────────────────────────────────
tv_tape()
st.markdown(f"""<div style="background:#0d0e10;border-bottom:1px solid #f5a623;padding:5px 16px;display:flex;justify-content:space-between;align-items:center">
  <div style="display:flex;align-items:center;gap:16px">
    <span style="color:#f5a623;font-size:17px;font-weight:700;letter-spacing:5px">⚡ SENTINEL</span>
    <span style="color:#444851">|</span>
    <span style="color:#8a8f99;font-size:9px;letter-spacing:1px">INTELLIGENCE TERMINAL</span>
    <span class="dot dot-g"></span><span style="color:#00e676;font-size:9px">LIVE</span>
  </div>
  <div style="font-size:9px;color:#8a8f99">{now_pst()} PST</div>
</div>""", unsafe_allow_html=True)

tabs = st.tabs(["  BRIEF  ","  MARKETS  ","  MACRO  ","  CRYPTO  ","  POLYMARKET  ","  GEO GLOBE  ","  SENTINEL AI  "])

# ════════════ BRIEF TAB ════════════
with tabs[0]:
    if st.button("⟳  REFRESH ALL", key="ref"): st.cache_data.clear(); st.rerun()

    KEY = {"SPY":"S&P 500","QQQ":"NASDAQ","DIA":"DOW","IWM":"RUSS 2K",
           "^TNX":"10Y YLD","DXY":"USD IDX","GLD":"GOLD","CL=F":"WTI","BTC-USD":"BITCOIN"}
    qs = multi_q(list(KEY.keys()))
    cols = st.columns(len(qs))
    for col, q in zip(cols, qs):
        with col:
            st.markdown(quotecard(KEY[q["ticker"]], f"{q['price']:,.2f}", q["pct"]), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    L, R = st.columns([3, 2])

    with L:
        # Watchlist
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">WATCHLIST</div><div class="bb-sec-b">', unsafe_allow_html=True)
        st.markdown('<table class="bb-tbl"><tr><th>TICKER</th><th>PRICE</th><th>CHG</th><th>%</th><th>VOL</th></tr>', unsafe_allow_html=True)
        for q in multi_q(st.session_state.watchlist):
            cls = "up" if q["pct"]>=0 else "dn"; s = "+" if q["pct"]>=0 else ""
            vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
            st.markdown(f'<tr><td class="kk">{q["ticker"]}</td><td>{q["price"]:,.4f}</td><td class="{cls}">{s}{q["change"]:.4f}</td><td class="{cls}">{s}{q["pct"]:.2f}%</td><td class="dm">{vol}</td></tr>', unsafe_allow_html=True)
        st.markdown("</table></div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Sector Rotation
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">SECTOR ROTATION</div><div class="bb-sec-b">', unsafe_allow_html=True)
        sec = sector_data()
        if not sec.empty:
            ss = sec.sort_values("Pct", ascending=False); mx = sec["Pct"].abs().max() or 1
            for _, row in ss.iterrows():
                p = row["Pct"]; c = "#00e676" if p>=0 else "#ff3b3b"; bw = abs(p)/mx*100; s = "+" if p>=0 else ""
                st.markdown(f"""<div class="bb-sr">
                  <span class="bb-sn">{row['Sector']} <span style="color:#444851">({row['ETF']})</span></span>
                  <div class="bb-sbw"><div class="bb-sbf" style="width:{bw}%;background:{c};opacity:0.7"></div></div>
                  <span class="bb-sv" style="color:{c}">{s}{p:.2f}%</span></div>""", unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    with R:
        # Sentiment
        v = get_vix(); fgv, fgl = fear_greed()
        vc = "#00e676" if v and v<15 else ("#f5a623" if v and v<25 else "#ff3b3b")
        pos = "RISK-ON" if v and v<18 else ("NEUTRAL" if v and v<25 else "RISK-OFF")
        pc = {"RISK-ON":"#00e676","NEUTRAL":"#f5a623","RISK-OFF":"#ff3b3b"}[pos]
        st.markdown(f"""<div class="bb-sec"><div class="bb-sec-t">SENTIMENT PULSE</div><div class="bb-sec-b">
          <div class="bb-mr"><span>VIX</span><span style="color:{vc};font-weight:600">{v if v else 'N/A'}</span></div>
          <div class="bb-mr"><span>CRYPTO F&G</span><span>{fgv}/100 — {fgl or ''}</span></div>
          <div class="bb-mr"><span>POSTURE</span><span style="color:{pc};font-weight:700">{pos}</span></div>
          </div></div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Polymarket
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">POLYMARKET — TOP MARKETS</div><div class="bb-sec-b">', unsafe_allow_html=True)
        for m in poly_mkt(8)[:5]:
            title = m.get("question", m.get("title",""))[:65]
            v24 = float(m.get("volume24hr",0) or 0)
            slug = m.get("slug",""); url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
            yp = poly_pct(m); np_ = 100-yp
            st.markdown(f"""<div class="bb-poly"><a href="{url}" target="_blank" class="bb-pla">
              <div class="bb-pty">{title}</div></a>
              <div style="display:flex;height:3px;margin:3px 0"><div style="flex:{yp};background:#00e676"></div><div style="flex:{np_};background:#ff3b3b"></div></div>
              <div class="bb-pm"><span><span class="yp">YES {yp:.0f}%</span> / <span class="np">NO {np_:.0f}%</span></span><span>24h ${v24:,.0f}</span></div></div>""", unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Geo Feed
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">GEO INTELLIGENCE</div><div class="bb-sec-b">', unsafe_allow_html=True)
        for i, a in enumerate(gdelt_news("geopolitical conflict oil market", 6)[:5]):
            t = a.get("title","")[:65]; u = a.get("url","#"); sd = a.get("seendate","")
            ds = f"{sd[4:6]}/{sd[6:8]}" if sd and len(sd)>=8 else "--"
            st.markdown(f'<div class="bb-ni"><span class="bb-nn">{i+1}</span><span class="bb-nd">{ds}</span><div><a href="{u}" target="_blank" class="bb-nl">{t}</a></div></div>', unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

# ════════════ MARKETS TAB ════════════
with tabs[1]:
    TV_MAP = {"SPY":"AMEX:SPY","QQQ":"NASDAQ:QQQ","NVDA":"NASDAQ:NVDA","AAPL":"NASDAQ:AAPL",
              "TSLA":"NASDAQ:TSLA","MSFT":"NASDAQ:MSFT","GOOGL":"NASDAQ:GOOGL","AMZN":"NASDAQ:AMZN",
              "META":"NASDAQ:META","GLD":"AMEX:GLD","TLT":"NASDAQ:TLT","IWM":"AMEX:IWM",
              "BTC-USD":"BITSTAMP:BTCUSD","ETH-USD":"BITSTAMP:ETHUSD","GC=F":"COMEX:GC1!",
              "CL=F":"NYMEX:CL1!","SI=F":"COMEX:SI1!","^TNX":"TVC:TNX","^VIX":"TVC:VIX","DXY":"TVC:DXY"}
    fc, _ = st.columns([2, 2])
    with fc:
        flash = st.text_input("SYMBOL LOOKUP", placeholder="NVDA  AAPL  TSLA  SPY  GLD  BTC-USD  CL=F", key="fl")

    if flash:
        sym = flash.upper().strip()
        tv_sym = TV_MAP.get(sym, f"NASDAQ:{sym}")
        q = yquote(sym)
        if q:
            c = "#00e676" if q["pct"]>=0 else "#ff3b3b"; s = "+" if q["pct"]>=0 else ""
            vol = f"{q['volume']/1e6:.1f}M" if q["volume"]>1e6 else f"{q['volume']/1e3:.0f}K"
            for col, (lbl, val, clr) in zip(st.columns(4), [
                ("LAST PRICE", f"{q['price']:,.4f}", "#f5a623"),
                ("CHANGE",     f"{s}{q['change']:,.4f}", c),
                ("% CHANGE",   f"{s}{q['pct']:.2f}%", c),
                ("VOLUME",     vol, "#8a8f99")]):
                with col:
                    st.markdown(f"""<div style="background:#0d0e10;border:1px solid #1e2025;border-top:2px solid {clr};padding:10px;margin-bottom:8px">
                      <div style="color:#8a8f99;font-size:9px">{lbl}</div>
                      <div style="color:{clr};font-size:22px;font-weight:600">{val}</div></div>""", unsafe_allow_html=True)
        else:
            st.warning(f"No data for {sym}. Check the ticker symbol.")

        st.markdown(f'<div class="bb-sec-t" style="padding:4px 0;margin-bottom:4px">TRADINGVIEW CHART — {sym if flash else "SPY"}</div>', unsafe_allow_html=True)
        tv_chart(tv_sym, height=500)
        st.markdown("<br>", unsafe_allow_html=True)

        cc, ic = st.columns(2)
        with cc:
            st.markdown('<div class="bb-sec-t">OPTIONS CHAIN — NEAREST EXPIRY</div>', unsafe_allow_html=True)
            calls, puts = opt_chain(sym)
            if calls is not None:
                st.markdown("""<div class="bb-og"><div class="bb-oc">
                  <div class="bb-oh bb-ch">▲ CALLS</div>
                  <div class="bb-or" style="background:#111316">
                    <span class="bb-ol">STRIKE</span><span class="bb-ol">LAST</span><span class="bb-ol">VOL</span><span class="bb-ol">IV</span></div>""", unsafe_allow_html=True)
                for _, row in calls.iterrows():
                    iv = f"{row['impliedVolatility']:.0%}" if row['impliedVolatility'] else "-"
                    vo = f"{int(row['volume']):,}" if row['volume'] else "-"
                    st.markdown(f'<div class="bb-or"><span class="bb-os">{row["strike"]:.1f}</span><span class="bb-oo">{row["lastPrice"]:.2f}</span><span class="bb-ov">{vo}</span><span class="bb-oiv">{iv}</span></div>', unsafe_allow_html=True)
                st.markdown("""</div><div class="bb-oc">
                  <div class="bb-oh bb-ph">▼ PUTS</div>
                  <div class="bb-or" style="background:#111316">
                    <span class="bb-ol">STRIKE</span><span class="bb-ol">LAST</span><span class="bb-ol">VOL</span><span class="bb-ol">IV</span></div>""", unsafe_allow_html=True)
                for _, row in puts.iterrows():
                    iv = f"{row['impliedVolatility']:.0%}" if row['impliedVolatility'] else "-"
                    vo = f"{int(row['volume']):,}" if row['volume'] else "-"
                    st.markdown(f'<div class="bb-or"><span class="bb-os" style="color:#ff3b3b">{row["strike"]:.1f}</span><span class="bb-oo">{row["lastPrice"]:.2f}</span><span class="bb-ov">{vo}</span><span class="bb-oiv">{iv}</span></div>', unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)
            else:
                st.info("No options data available for this symbol.")

        with ic:
            st.markdown('<div class="bb-sec-t">INSIDER TRANSACTIONS</div>', unsafe_allow_html=True)
            if st.session_state.finnhub_key:
                ins = fh_insider(sym, st.session_state.finnhub_key)
                if ins:
                    st.markdown('<div style="border:1px solid #1e2025"><div class="bb-in" style="background:#111316"><span style="color:#f5a623;font-size:9px">NAME</span><span style="color:#f5a623;font-size:9px">DATE</span><span style="color:#f5a623;font-size:9px">TYPE</span><span style="color:#f5a623;font-size:9px">SHARES</span></div>', unsafe_allow_html=True)
                    for tx in ins[:8]:
                        name = str(tx.get("name","—"))[:18]; date = tx.get("transactionDate","—")[:10]
                        code = tx.get("transactionCode","—"); chg = tx.get("change",0) or 0
                        is_buy = chg>0 or code in ["P","A"]
                        typ = '<span class="bb-inb">▲ BUY</span>' if is_buy else '<span class="bb-ins">▼ SELL</span>'
                        sh = f"{abs(chg):,.0f}" if chg else "—"
                        st.markdown(f'<div class="bb-in"><span style="color:#d0d3d8">{name}</span><span style="color:#8a8f99;font-size:9px">{date}</span><span>{typ}</span><span style="color:#f0f2f5">{sh}</span></div>', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.info("No recent insider transactions.")
            else:
                st.info("Add Finnhub key in sidebar for insider transaction data.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state.finnhub_key:
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">MARKET NEWS — FINNHUB LIVE</div><div class="bb-sec-b">', unsafe_allow_html=True)
        for i, a in enumerate(fh_news(st.session_state.finnhub_key)[:12]):
            title = a.get("headline","")[:90]; url = a.get("url","#"); src = a.get("source","")
            try: ds = datetime.fromtimestamp(a.get("datetime",0)).strftime("%m/%d")
            except: ds = "--"
            st.markdown(f'<div class="bb-ni"><span class="bb-nn">{i+1}</span><span class="bb-nd">{ds}</span><div><a href="{url}" target="_blank" class="bb-nl">{title}</a><div class="bb-ns">{src}</div></div></div>', unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="bb-sec-t">FOREX CROSS RATES</div>', unsafe_allow_html=True)
    tv_forex(280)

# ════════════ MACRO TAB ════════════
with tabs[2]:
    if not st.session_state.fred_key:
        st.markdown('<div class="bb-ae">⚠ Add FRED API key in sidebar to unlock macro dashboard. Free at fred.stlouisfed.org/docs/api/api_key.html</div>', unsafe_allow_html=True)
    else:
        MSERIES = {"CPI":"CPIAUCSL","Core PCE":"PCEPILFE","Fed Funds":"FEDFUNDS","10Y Yld":"DGS10",
                   "2Y Yld":"DGS2","10Y-2Y":"T10Y2Y","U3 Unemp":"UNRATE","U6 Unemp":"U6RATE",
                   "M2 Money":"M2SL","HY Spread":"BAMLH0A0HYM2"}
        mc = st.columns(5)
        for i, (name, code) in enumerate(MSERIES.items()):
            df = fred_fetch(code, st.session_state.fred_key, 5)
            with mc[i%5]:
                if df is not None and not df.empty:
                    cur = df["value"].iloc[-1]; prev = df["value"].iloc[-2] if len(df)>1 else cur
                    d = cur-prev; c = "#00e676" if d>=0 else "#ff3b3b"; s = "+" if d>=0 else ""
                    st.markdown(f"""<div style="background:#0d0e10;border:1px solid #1e2025;border-top:2px solid #f5a623;padding:8px;margin-bottom:6px">
                      <div style="color:#8a8f99;font-size:9px;letter-spacing:1px">{name}</div>
                      <div style="color:#f0f2f5;font-size:17px;font-weight:600">{cur:.2f}</div>
                      <div style="color:{c};font-size:10px">{s}{d:.3f}</div></div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f'<div style="background:#0d0e10;border:1px solid #1e2025;padding:8px;margin-bottom:6px"><div style="color:#8a8f99;font-size:9px">{name}</div><div style="color:#444851">N/A</div></div>', unsafe_allow_html=True)

        df2 = fred_fetch("T10Y2Y", st.session_state.fred_key, 5)
        if df2 is not None and not df2.empty:
            sp = df2["value"].iloc[-1]
            if sp < 0:
                st.markdown(f'<div class="bb-ac" style="margin:8px 0">⚠ YIELD CURVE INVERTED: 10Y-2Y = {sp:.2f}%. Historical recession signal. Avg lead time 12-18 months.</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bb-ag" style="margin:8px 0">✓ YIELD CURVE NORMAL: 10Y-2Y = +{sp:.2f}%. No inversion signal currently.</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        a, b = st.columns(2)
        with a:
            st.markdown('<div class="bb-sec-t">10Y TREASURY YIELD</div>', unsafe_allow_html=True)
            tv_mini("TVC:TNX", 200)
        with b:
            st.markdown('<div class="bb-sec-t">US DOLLAR INDEX (DXY)</div>', unsafe_allow_html=True)
            tv_mini("TVC:DXY", 200)

        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="bb-sec-t">GOLD (COMEX GC1!)</div>', unsafe_allow_html=True)
            tv_mini("COMEX:GC1!", 200)
        with c2:
            st.markdown('<div class="bb-sec-t">WTI CRUDE OIL (NYMEX CL1!)</div>', unsafe_allow_html=True)
            tv_mini("NYMEX:CL1!", 200)

# ════════════ CRYPTO TAB ════════════
with tabs[3]:
    gd = cg_global(st.session_state.coingecko_key)
    if gd:
        tc = gd.get("total_market_cap",{}).get("usd",0)
        btcd = gd.get("market_cap_percentage",{}).get("btc",0)
        ethd = gd.get("market_cap_percentage",{}).get("eth",0)
        fgv, fgl = fear_greed()
        for col, (lbl, val) in zip(st.columns(4), [
            ("TOTAL MARKET CAP", f"${tc/1e12:.2f}T"),
            ("BTC DOMINANCE", f"{btcd:.1f}%"),
            ("ETH DOMINANCE", f"{ethd:.1f}%"),
            ("FEAR & GREED", f"{fgv}/100 — {fgl}" if fgv else "N/A")]):
            with col:
                st.markdown(f"""<div style="background:#0d0e10;border:1px solid #1e2025;border-top:2px solid #f5a623;padding:8px;text-align:center">
                  <div style="color:#8a8f99;font-size:9px">{lbl}</div>
                  <div style="color:#f0f2f5;font-size:16px;font-weight:600">{val}</div></div>""", unsafe_allow_html=True)
        if btcd > 55:
            st.markdown('<div class="bb-ae" style="margin-top:8px">⚠ BTC Dominance >55% — Altcoin weakness. Risk-off within crypto.</div>', unsafe_allow_html=True)
        elif btcd < 45:
            st.markdown('<div class="bb-ag" style="margin-top:8px">✓ BTC Dominance <45% — Altcoin season conditions may be forming.</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    ca, cb = st.columns(2)
    with ca:
        st.markdown('<div class="bb-sec-t">BITCOIN / USD</div>', unsafe_allow_html=True)
        tv_chart("BITSTAMP:BTCUSD", 360)
    with cb:
        st.markdown('<div class="bb-sec-t">ETHEREUM / USD</div>', unsafe_allow_html=True)
        tv_chart("BITSTAMP:ETHUSD", 360)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="bb-sec-t">CRYPTO MARKET TABLE — TOP 20</div>', unsafe_allow_html=True)
    cd = cg_markets(st.session_state.coingecko_key)
    if cd:
        st.markdown('<table class="bb-tbl"><tr><th>#</th><th>SYM</th><th>NAME</th><th>PRICE</th><th>24H %</th><th>MKT CAP</th><th>24H VOL</th></tr>', unsafe_allow_html=True)
        for i, c in enumerate(cd[:18]):
            p = c.get("price_change_percentage_24h",0) or 0
            cls = "up" if p>=0 else "dn"; s = "+" if p>=0 else ""
            pr = f"${c['current_price']:,.4f}" if c["current_price"]<1 else f"${c['current_price']:,.2f}"
            mc = f"${c['market_cap']/1e9:.1f}B"; vo = f"${c['total_volume']/1e9:.1f}B"
            st.markdown(f'<tr><td class="dm">{i+1}</td><td class="kk">{c["symbol"].upper()}</td><td class="dm">{c["name"]}</td><td>{pr}</td><td class="{cls}">{s}{p:.2f}%</td><td class="dm">{mc}</td><td class="dm">{vo}</td></tr>', unsafe_allow_html=True)
        st.markdown("</table>", unsafe_allow_html=True)

# ════════════ POLYMARKET TAB ════════════
with tabs[4]:
    st.markdown('<div class="bb-sec-t">POLYMARKET — PREDICTION INTELLIGENCE & UNUSUAL FLOW DETECTION</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8a8f99;font-size:9px;margin:6px 0 10px">Click any market title to open on Polymarket.com · Unusual volume may signal informed positioning</div>', unsafe_allow_html=True)

    psrch = st.text_input("FILTER MARKETS", placeholder="Fed rate  oil  Taiwan  election  gold  BTC  recession...", key="ps")
    all_p = poly_mkt(80)
    unusual = unusual_poly(all_p)
    filtered = [m for m in all_p if not psrch or psrch.lower() in str(m.get("question","")).lower()] if psrch else all_p

    if unusual:
        st.markdown('<div style="color:#ff3b3b;font-size:9px;letter-spacing:2px;padding:4px 0;border-bottom:1px solid #ff3b3b;margin-bottom:6px">⚡ UNUSUAL ACTIVITY DETECTED</div>', unsafe_allow_html=True)
        for m in unusual:
            t = m.get("question", m.get("title",""))[:80]
            v24 = float(m.get("volume24hr",0) or 0); vtot = float(m.get("volume",0) or 0)
            ratio = v24/vtot*100 if vtot>0 else 0
            slug = m.get("slug",""); url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
            st.markdown(f'<div class="bb-ac"><a href="{url}" target="_blank" style="color:#ff3b3b;text-decoration:none;font-weight:600">⚡ {t}</a><div style="color:#8a8f99;font-size:9px;margin-top:4px">24h: ${v24:,.0f} ({ratio:.0f}% of total ${vtot:,.0f})</div></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    pa, pb = st.columns([3, 1])
    with pa:
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">ACTIVE MARKETS — RANKED BY 24H VOLUME</div><div class="bb-sec-b">', unsafe_allow_html=True)
        for m in filtered[:30]:
            t = m.get("question", m.get("title","Unknown"))[:88]
            v24 = float(m.get("volume24hr",0) or 0); vtot = float(m.get("volume",0) or 0)
            slug = m.get("slug",""); url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
            yp = poly_pct(m); np_ = 100-yp
            st.markdown(f"""<div class="bb-poly"><a href="{url}" target="_blank" class="bb-pla">
              <div class="bb-pty">{t}</div></a>
              <div style="display:flex;height:3px;margin:4px 0"><div style="flex:{yp};background:#00e676"></div><div style="flex:{np_};background:#ff3b3b"></div></div>
              <div class="bb-pm"><span><span class="yp">YES {yp:.0f}%</span> &nbsp;/&nbsp; <span class="np">NO {np_:.0f}%</span></span><span style="color:#444851">24h ${v24:,.0f} | total ${vtot:,.0f}</span></div></div>""", unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

    with pb:
        st.markdown("""<div class="bb-sec"><div class="bb-sec-t">SIGNAL GUIDE</div><div class="bb-sec-b" style="font-size:10px;color:#8a8f99;line-height:1.9">
          <div style="color:#ff3b3b;margin-bottom:6px">⚡ UNUSUAL TRIGGERS</div>
          24h vol ≥38% of total<br>
          15pt shift in 6h no news<br>
          Large single wallet<br>
          Pre-event surge 12-48h<br>
          New market + instant liquidity<br><br>
          <div style="color:#f5a623;margin-bottom:6px">🔗 CONVERGENCE SIGNAL</div>
          Polymarket + FRED macro<br>pointing same direction =<br>strongest free signal<br><br>
          <div style="color:#444851;font-size:9px">⚠ Crowd odds only.<br>Not guaranteed outcomes.</div>
        </div></div>""", unsafe_allow_html=True)

# ════════════ GEO GLOBE TAB ════════════
with tabs[5]:
    st.markdown('<div class="bb-sec-t">GEOPOLITICAL INTELLIGENCE — SENTINEL GLOBE | CESIUM SATELLITE IMAGERY</div>', unsafe_allow_html=True)
    st.caption("Drag to rotate · Scroll to zoom · Click markers for intel · Hover for preview · Click + ADD EVENT to pin custom events")

    globe_path = pathlib.Path(__file__).parent / "globe.html"
    if globe_path.exists():
        components.html(globe_path.read_text(encoding="utf-8"), height=650, scrolling=False)
    else:
        st.error("globe.html not found. Place it in the same folder as sentinel_app.py")
        st.info("Download globe.html from the SENTINEL files you were given and add it to your GitHub repo root.")

    st.markdown("<br>", unsafe_allow_html=True)

    THMAP = {
        "Middle East + Hormuz + Oil": "Middle East Iran oil Hormuz Houthi",
        "China + Taiwan + Semiconductors": "China Taiwan semiconductor chips TSMC",
        "Russia + Ukraine + Energy": "Russia Ukraine energy grain NATO",
        "Africa + Cobalt + Lithium": "Africa cobalt lithium coup Sahel Mali",
        "Red Sea + Suez + Shipping": "Red Sea Suez shipping Houthi container",
        "South China Sea + Trade": "South China Sea shipping dispute Philippines",
    }
    g1, g2 = st.columns([3, 1])
    with g1:
        th = st.selectbox("NEWS FEED — SELECT THEATER", list(THMAP.keys()) + ["Custom search…"])
        cq = "" if th != "Custom search…" else st.text_input("Custom GDELT query", key="cq")
        q = cq if cq else THMAP.get(th, "")
        if q:
            st.markdown('<div class="bb-sec"><div class="bb-sec-t">GDELT LIVE FEED — 100+ LANGUAGES, UPDATES EVERY 15 MIN</div><div class="bb-sec-b">', unsafe_allow_html=True)
            for i, a in enumerate(gdelt_news(q, 12)):
                t = a.get("title","")[:100]; u = a.get("url","#"); dom = a.get("domain",""); sd = a.get("seendate","")
                ds = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd)>=8 else ""
                st.markdown(f'<div class="bb-ni"><span class="bb-nn">{i+1}</span><span class="bb-nd" style="min-width:70px">{ds}</span><div><a href="{u}" target="_blank" class="bb-nl">{t}</a><div class="bb-ns">{dom}</div></div></div>', unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

            if st.session_state.newsapi_key:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="bb-sec"><div class="bb-sec-t">NEWSAPI — 150,000+ SOURCES</div><div class="bb-sec-b">', unsafe_allow_html=True)
                for i, a in enumerate(newsapi_fetch(st.session_state.newsapi_key, q)[:8]):
                    title = a.get("title","")
                    if not title or "[Removed]" in title: continue
                    u = a.get("url","#"); src = a.get("source",{}).get("name",""); pub = a.get("publishedAt","")[:10]
                    st.markdown(f'<div class="bb-ni"><span class="bb-nn">{i+1}</span><span class="bb-nd" style="min-width:70px">{pub}</span><div><a href="{u}" target="_blank" class="bb-nl">{title[:100]}</a><div class="bb-ns">{src}</div></div></div>', unsafe_allow_html=True)
                st.markdown("</div></div>", unsafe_allow_html=True)

    with g2:
        st.markdown('<div class="bb-sec"><div class="bb-sec-t">THEATER STATUS</div><div class="bb-sec-b">', unsafe_allow_html=True)
        for name, status, css in [
            ("MIDDLE EAST","CRITICAL","tc"), ("UKRAINE","ACTIVE","tc"),
            ("RED SEA","DISRUPTED","tc"), ("HORMUZ","ELEVATED","te"),
            ("SAHEL","ELEVATED","te"), ("TAIWAN","MONITORING","tw"), ("S CHINA SEA","MONITORING","tw")]:
            st.markdown(f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1e2025;font-size:10px"><span style="color:#d0d3d8">{name}</span><span class="{css}">{status}</span></div>', unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""<div class="bb-sec"><div class="bb-sec-t">CONFIDENCE SCALE</div><div class="bb-sec-b" style="font-size:10px;color:#8a8f99;line-height:2">
          <span class="tc">HIGH</span> — Multiple confirmed<br>
          <span class="te">MEDIUM</span> — Limited sources<br>
          <span class="tw">LOW</span> — Single source<br>
          <span style="color:#444851">UNCONFIRMED</span> — Unverified
        </div></div>""", unsafe_allow_html=True)

# ════════════ SENTINEL AI TAB ════════════
with tabs[6]:
    st.markdown("""<div style="background:#0d0e10;border:1px solid #1e2025;border-top:2px solid #f5a623;padding:10px 14px;margin-bottom:10px">
      <div style="color:#f5a623;font-size:11px;letter-spacing:2px;margin-bottom:4px">⚡ SENTINEL AI — GOOGLE GEMINI</div>
      <div style="color:#8a8f99;font-size:9px">Commands: /brief &nbsp; /flash NVDA &nbsp; /scenario Gold &nbsp; /geo "Red Sea" &nbsp; /poly "Fed rate" &nbsp; /rotate &nbsp; /sentiment &nbsp; /idea Energy</div>
    </div>""", unsafe_allow_html=True)

    if not st.session_state.gemini_key:
        st.markdown("""<div class="bb-ae">⚠ Gemini API key required. Add it in the sidebar (free at aistudio.google.com/app/apikey)</div>""", unsafe_allow_html=True)
        st.markdown("""<div class="bb-ai" style="margin-top:8px">
<strong>To fix 404 model errors — list YOUR available models:</strong><br><br>
<strong>CURL (paste in terminal):</strong><br>
<code style="color:#f5a623">curl "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_API_KEY" | python3 -m json.tool</code><br><br>
<strong>PYTHON:</strong><br>
<code style="color:#f5a623">import google.generativeai as genai<br>
genai.configure(api_key="YOUR_KEY")<br>
for m in genai.list_models():<br>
&nbsp;&nbsp;if "generateContent" in m.supported_generation_methods:<br>
&nbsp;&nbsp;&nbsp;&nbsp;print(m.name)</code><br><br>
SENTINEL will auto-try: <span style="color:#f5a623">gemini-2.0-flash → gemini-1.5-flash → gemini-1.5-pro → gemini-pro</span><br>
The first model that works on your account will be used automatically.
</div>""", unsafe_allow_html=True)
    else:
        if not st.session_state.chat_history:
            st.markdown('<div class="bb-ag">⚡ SENTINEL AI ONLINE — Live market data injected. Try: <code>/brief</code> &nbsp; <code>/flash NVDA</code> &nbsp; <code>/scenario Gold</code> &nbsp; <code>/geo Red Sea</code></div>', unsafe_allow_html=True)

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="bb-cu"><div class="bb-cl" style="color:#f5a623">YOU</div>{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                content = msg["content"].replace("<","&lt;").replace(">","&gt;")
                st.markdown(f'<div class="bb-ca"><div class="bb-cl" style="color:#00e676">⚡ SENTINEL</div>{content}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Quick command buttons
        qbc = st.columns(7)
        QUICK = [("BRIEF","/brief"),("ROTATE","/rotate"),("SENTIMENT","/sentiment"),
                 ("BTC SCEN","/scenario Bitcoin"),("RED SEA","/geo Red Sea"),
                 ("POLY FED","/poly Fed rate"),("ENERGY","/idea Energy")]
        for col, (lbl, cmd) in zip(qbc, QUICK):
            with col:
                if st.button(lbl, key=f"qb_{lbl}", use_container_width=True):
                    st.session_state.chat_history.append({"role":"user","content":cmd})
                    with st.spinner("⚡ SENTINEL processing..."):
                        resp = gemini_chat(cmd, st.session_state.chat_history[:-1], msnap())
                    st.session_state.chat_history.append({"role":"assistant","content":resp})
                    st.rerun()

        ic, bc = st.columns([6, 1])
        with ic:
            ui = st.text_input("", placeholder="Ask SENTINEL anything... /brief /flash NVDA /scenario Gold /geo Red Sea /poly Fed",
                               key="ci", label_visibility="collapsed")
        with bc:
            send = st.button("SEND ⚡", use_container_width=True, key="sb")

        if st.button("CLEAR CHAT", key="clr"):
            st.session_state.chat_history = []; st.rerun()

        if (send or ui) and ui:
            st.session_state.chat_history.append({"role":"user","content":ui})
            with st.spinner("⚡ SENTINEL processing..."):
                resp = gemini_chat(ui, st.session_state.chat_history[:-1], msnap())
            st.session_state.chat_history.append({"role":"assistant","content":resp})
            st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""<div style="background:#0d0e10;border-top:1px solid #1e2025;padding:4px 16px;
  display:flex;justify-content:space-between;margin-top:12px;font-size:9px;color:#444851">
  <span>⚡ SENTINEL | {now_pst()} PST</span>
  <span>Yahoo Finance • FRED • Polymarket • GDELT • CoinGecko • Finnhub • NewsAPI • TradingView</span>
  <span>Research only — not financial advice</span></div>""", unsafe_allow_html=True)
