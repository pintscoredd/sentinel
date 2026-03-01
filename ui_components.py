#!/usr/bin/env python3
"""SENTINEL — UI Components Module
All render_* functions, chart helpers, Polymarket URL/status helpers, and Gemini AI.
"""

import streamlit as st
import re
import json
from datetime import datetime
import pytz

try:
    import plotly.graph_objects as go
    import plotly.express as px
except ImportError:
    go = None
    px = None

from data_fetchers import (
    _safe_float, _safe_int, _esc, fmt_p, fmt_pct, pct_color,
    fred_series, finnhub_officers, _parse_poly_field,
    multi_quotes, vix_price, market_snapshot_str,
    GEO_FINANCIAL_NETWORKS, GEO_WEBCAM_FEEDS,
    GEO_THEATERS, GEO_IMPACT_TICKERS, GEO_SHIPPING_LANES,
    gdelt_news, newsapi_headlines,
    fetch_conflict_events_json, fetch_military_aircraft_json,
    fetch_satellite_positions_json, fetch_ais_vessels,
    fetch_btc_etf_flows, fetch_btc_etf_flows_fallback,
    _ETF_TICKERS, _ETF_COLORS,
)

try:
    import numpy as _np
except ImportError:
    _np = None

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
    fig.update_layout(**CHART_LAYOUT, height=height, margin=dict(l=0, r=10, t=24, b=0))
    return fig

def tv_chart(symbol, height=450):
    return f"""<!DOCTYPE html><html>
<head><style>body{{margin:0;padding:0;background:#000000;overflow:hidden}}
.tradingview-widget-container{{width:100%;height:{height}px}}</style></head>
<body><div class="tradingview-widget-container">
<div id="tv_c_{symbol.replace(':','_').replace('-','_')}"></div>
<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
<script type="text/javascript">
new TradingView.widget({{
  "width":"100%","height":{height},"symbol":"{symbol}","interval":"60",
  "range":"1M",
  "timezone":"America/Los_Angeles","theme":"dark","style":"1","locale":"en",
  "toolbar_bg":"#000000","enable_publishing":false,"hide_side_toolbar":false,
  "allow_symbol_change":true,"save_image":false,
  "container_id":"tv_c_{symbol.replace(':','_').replace('-','_')}",
  "backgroundColor":"rgba(0,0,0,1)","gridColor":"rgba(20,20,20,1)",
  "studies":["STD;EMA","STD;RSI"],
  "studies_overrides":{{"ema.length":20,"rsi.length":14}},
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
    """Plotly yield curve chart"""
    if not fred_key: return None
    MATURITIES = [("3M", "DTB3"), ("6M", "DTB6"), ("1Y", "DGS1"), ("2Y", "DGS2"),
                  ("3Y", "DGS3"), ("5Y", "DGS5"), ("7Y", "DGS7"), ("10Y", "DGS10"),
                  ("20Y", "DGS20"), ("30Y", "DGS30")]
    labels, vals = [], []
    for lbl, code in MATURITIES:
        df = fred_series(code, fred_key, 3)
        if df is not None and not df.empty:
            labels.append(lbl)
            vals.append(round(df["value"].iloc[-1], 2))
    if not labels: return None
    fig = dark_fig(height)
    fig.add_trace(go.Scatter(x=labels, y=vals, mode="lines+markers+text",
        line=dict(color="#FF6600", width=2.5), marker=dict(size=9, color="#FF6600"),
        text=[f"{v:.2f}%" for v in vals], textposition="top center",
        textfont=dict(size=10, color="#FF8C00"), fill="tozeroy",
        fillcolor="rgba(255,102,0,0.08)"))
    fig.add_hline(y=0, line_dash="dash", line_color="#FF4444", opacity=0.5)
    fig.update_layout(yaxis_title="Yield (%)",
        title=dict(text=f"US TREASURY YIELD CURVE — {datetime.now().strftime('%Y-%m-%d')}",
                   font=dict(size=11, color="#FF6600"), x=0))
    return fig

def yield_history_chart(fred_key, height=220):
    """Multi-maturity yield history chart"""
    if not fred_key: return None
    LINES = [("2Y", "DGS2", "#FF4444"), ("5Y", "DGS5", "#FF8C00"),
             ("10Y", "DGS10", "#FFCC00"), ("30Y", "DGS30", "#00AAFF")]
    fig = dark_fig(height)
    for lbl, code, color in LINES:
        df = fred_series(code, fred_key, 36)
        if df is not None and not df.empty:
            fig.add_trace(go.Scatter(x=df["date"], y=df["value"], mode="lines",
                name=lbl, line=dict(color=color, width=1.8)))
    fig.update_layout(showlegend=True,
        legend=dict(bgcolor="#050505", bordercolor="#333", font=dict(size=10, color="#FF8C00")),
        yaxis_title="Yield (%)", title=dict(text="MULTI-MATURITY YIELD HISTORY (3Y)",
            font=dict(size=11, color="#FF6600"), x=0))
    return fig

def cpi_vs_rates_chart(fred_key, height=250):
    """CPI YoY vs Fed Funds Rate chart"""
    if not fred_key: return None
    LINES = [("CPI YoY %", "CPIAUCSL", "#FF4444"), ("Fed Funds Rate", "FEDFUNDS", "#00AAFF"),
             ("Core PCE", "PCEPILFE", "#FFCC00")]
    fig = dark_fig(height)
    has_data = False
    for lbl, code, color in LINES:
        df = fred_series(code, fred_key, 36)
        if df is not None and not df.empty:
            has_data = True
            fig.add_trace(go.Scatter(x=df["date"], y=df["value"], mode="lines",
                name=lbl, line=dict(color=color, width=2)))
    if not has_data: return None
    fig.update_layout(showlegend=True,
        legend=dict(bgcolor="#050505", bordercolor="#333", font=dict(size=10, color="#FF8C00")),
        yaxis_title="Rate / Index", title=dict(text="CPI vs FED FUNDS vs CORE PCE (3Y)",
            font=dict(size=11, color="#FF6600"), x=0))
    return fig

# ════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ════════════════════════════════════════════════════════════════════

def render_news_card(title, url, source, date_str, card_class="bb-news"):
    t_html = f'<a href="{_esc(url)}" target="_blank">{_esc(title[:100])}</a>' if url and url != "#" else f'<span style="color:#CCC">{_esc(title[:100])}</span>'
    return f'<div class="{card_class}">{t_html}<div class="bb-meta">{_esc(source)} &nbsp;|&nbsp; {date_str}</div></div>'

def render_wl_row(q):
    c = "#00CC44" if q["pct"] >= 0 else "#FF4444"
    arr = "▲" if q["pct"] >= 0 else "▼"
    vol = f"{q['volume']/1e6:.1f}M" if q["volume"] > 1e6 else f"{q['volume']/1e3:.0f}K"
    return (f'<div class="wl-row"><span class="wl-ticker">{q["ticker"]}</span>'
            f'<span class="wl-price">{fmt_p(q["price"])}</span>'
            f'<span style="color:{c};font-weight:600">{arr} {abs(q["pct"]):.2f}%</span>'
            f'<span style="color:{c}">{"+"+fmt_p(q["change"]) if q["change"]>=0 else fmt_p(q["change"])}</span>'
            f'<span class="wl-vol">{vol}</span>'
            f'</div>')

def render_options_table(df, side="calls", current_price=None):
    if df is None or df.empty: return '<p style="color:#555;font-family:monospace;font-size:11px">No data</p>'
    import pandas as pd
    df = df.copy()
    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce").fillna(0)

    if current_price and "strike" in df.columns and len(df) > 13:
        df["_dist"] = (df["strike"] - current_price).abs()
        df = df.nsmallest(len(df) - 13, "_dist").drop(columns=["_dist"])

    strike_color = "#00CC44" if side == "calls" else "#FF4444"
    atm_strike = None
    if current_price and not df.empty:
        strikes = df["strike"].tolist() if "strike" in df.columns else []
        if strikes:
            atm_strike = min(strikes, key=lambda s: abs(float(s) - current_price))
    rows = ""
    for _, row in df.iterrows():
        s = _safe_float(row.get("strike", 0))
        lp = _safe_float(row.get("lastPrice", 0))
        b = _safe_float(row.get("bid", 0))
        a = _safe_float(row.get("ask", 0))
        v = _safe_int(row.get("volume", 0))
        oi = _safe_int(row.get("openInterest", 0))
        iv = _safe_float(row.get("impliedVolatility", 0))
        itm = ""
        if current_price:
            if side == "calls" and s < current_price: itm = " opt-itm"
            if side == "puts" and s > current_price: itm = " opt-itm"
        hv = " opt-hvol" if v > 0 and oi > 0 and v / max(oi, 1) > 0.5 else ""
        atm_style = ""
        if atm_strike is not None and abs(s - atm_strike) < 0.01:
            atm_style = ' style="background:rgba(255,102,0,0.18);border-left:3px solid #FF6600"'
        rows += (f'<tr class="{itm}"{atm_style}><td style="color:{strike_color};font-weight:600;text-align:left">{s:.2f}</td>'
                 f'<td>{lp:.2f}</td><td>{b:.2f}</td><td>{a:.2f}</td>'
                 f'<td class="{hv}">{v:,}</td><td>{oi:,}</td><td>{iv:.1%}</td></tr>')
    return (f'<table class="opt-tbl"><thead><tr>'
            f'<th>Strike</th><th>Last</th><th>Bid</th><th>Ask</th>'
            f'<th>Volume</th><th>OI</th><th>IV</th></tr></thead><tbody>{rows}</tbody></table>')


def render_scored_options(contracts, side="calls"):
    """Render a compact scored options table (top 2 contracts)."""
    if not contracts:
        return '<p style="color:#555;font-family:monospace;font-size:12px">No scored contracts</p>'
    cls = "opt-call" if side == "calls" else "opt-put"
    rows = ""
    for c in contracts:
        s = c.get("strike", 0)
        lp = c.get("lastPrice", 0)
        b = c.get("bid", 0)
        a = c.get("ask", 0)
        v = c.get("volume", 0)
        oi = c.get("openInterest", 0)
        iv = c.get("iv", 0)
        sc = c.get("score", 0)
        voi = c.get("voi", 0)
        sc_color = "#00CC44" if sc >= 0.3 else "#FF8C00" if sc >= 0.15 else "#FF4444"
        rows += (f'<tr><td class="{cls}">{s:.2f}</td>'
                 f'<td>{lp:.2f}</td><td>{b:.2f}</td><td>{a:.2f}</td>'
                 f'<td>{v:,}</td><td>{oi:,}</td><td>{iv:.1%}</td>'
                 f'<td style="font-weight:700;color:#FF8C00">{voi:.2f}</td>'
                 f'<td style="font-weight:700;color:{sc_color}">{sc:.4f}</td></tr>')
    return (f'<table class="opt-tbl"><thead><tr>'
            f'<th>Strike</th><th>Last</th><th>Bid</th><th>Ask</th>'
            f'<th>Vol</th><th>OI</th><th>IV</th><th>V/OI</th><th>Score</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>')


def render_unusual_trade(contract, ticker="", expiry=""):
    """Render a visually distinct 'Unusual Activity' card for the single highest V/OI contract."""
    if not contract:
        return ""
    s = contract.get("strike", 0)
    side = contract.get("side", "call")
    direction = "BULLISH ▲" if side == "call" else "BEARISH ▼"
    dir_color = "#00CC44" if side == "call" else "#FF4444"
    v = contract.get("volume", 0)
    oi = contract.get("openInterest", 0)
    voi = contract.get("voi", 0)
    sc = contract.get("score", 0)
    iv = contract.get("iv", 0)

    return (
        f'<div style="background:#0A0500;border:1px solid #FF6600;border-left:4px solid #FF6600;'
        f'padding:14px 18px;margin:12px 0;font-family:monospace">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'<span style="color:#FF6600;font-size:14px;font-weight:700;letter-spacing:1px">⚡ UNUSUAL OPTIONS ACTIVITY</span>'
        f'<span style="color:{dir_color};font-size:13px;font-weight:700">{direction}</span>'
        f'</div>'
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:12px">'
        f'<div><span style="color:#666">TICKER</span><br><span style="color:#FFF;font-weight:600">{_esc(ticker)}</span></div>'
        f'<div><span style="color:#666">STRIKE</span><br><span style="color:#FFF;font-weight:600">${s:.2f}</span></div>'
        f'<div><span style="color:#666">EXPIRY</span><br><span style="color:#FFF;font-weight:600">{_esc(str(expiry))}</span></div>'
        f'<div><span style="color:#666">VOL / OI</span><br><span style="color:#FF8C00;font-weight:700">{v:,} / {oi:,} ({voi:.2f}x)</span></div>'
        f'<div><span style="color:#666">IV</span><br><span style="color:#FFF;font-weight:600">{iv:.1%}</span></div>'
        f'<div><span style="color:#666">SCORE</span><br><span style="color:#FF8C00;font-weight:700">{sc:.4f}</span></div>'
        f'</div></div>'
    )

# ════════════════════════════════════════════════════════════════════
# INSIDER TRANSACTIONS
# ════════════════════════════════════════════════════════════════════

ROLE_SHORTCUTS = {
    "CEO": "CEO", "C.E.O.": "CEO", "CHIEF EXECUTIVE": "CEO", "PRESIDENT": "President",
    "CFO": "CFO", "CHIEF FINANCIAL": "CFO", "COO": "COO", "CHIEF OPERATING": "COO",
    "CTO": "CTO", "CHIEF TECHNOLOGY": "CTO", "CMO": "CMO", "CHIEF MARKETING": "CMO",
    "GENERAL COUNSEL": "Gen Counsel", "DIRECTOR": "Director", "CHAIRMAN": "Chairman",
    "VP ": "VP", "VICE PRESIDENT": "VP", "SVP": "SVP", "EVP": "EVP", "TREASURER": "Treasurer",
    "SECRETARY": "Secretary", "CONTROLLER": "Controller", "10% OWNER": "10% Owner",
    "BENEFICIAL OWNER": "Beneficial Owner",
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
    CODE = {
        "P": ("PURCHASE", "buy"), "S": ("SALE", "sell"),
        "A": ("AWARD", "buy"), "D": ("DISPOSAL", "sell"),
        "M": ("EXERCISE", "buy"), "X": ("EXERCISE", "buy"),
        "G": ("GIFT", "sell"), "F": ("TAX WITHHOLD", "sell"),
        "C": ("CONVERSION", "buy"), "W": ("INHERITANCE", "buy"),
        "J": ("OTHER ACQ", "buy"), "K": ("EQUITY SWAP", "sell"),
        "I": ("DISCRETIONARY", "buy"), "U": ("TENDER", "sell"),
        "H": ("EXPIRATION", "sell"), "L": ("SMALL ACQ", "buy"),
        "Z": ("TRUST", "buy"), "V": ("TRANSACTION", "buy"),
    }
    html = ""
    for tx in data[:10]:
        name = _esc(str(tx.get("name", "Unknown"))[:24])
        chg = _safe_int(tx.get("change", 0))
        date = str(tx.get("transactionDate", ""))[:10]
        code = str(tx.get("transactionCode", "?") or "?").upper()
        shares_own = _safe_int(tx.get("share", 0))
        lbl, cls = CODE.get(code, (code if code else "UNKNOWN", "buy" if chg >= 0 else "sell"))
        if chg < 0 and cls == "buy" and code not in ("P", "A", "M", "X", "C"):
            cls = "sell"
        if chg > 0 and cls == "sell" and code not in ("S", "D", "G", "F"):
            cls = "buy"

        name_upper = str(tx.get("name", "")).upper().strip()
        filing_name = str(tx.get("filingName", "") or "")
        raw_role = role_map.get(name_upper, "")

        if not raw_role and name_upper:
            name_parts = name_upper.split()
            if len(name_parts) >= 2:
                raw_role = role_map.get(" ".join(name_parts[:2]), "")
            if not raw_role and len(name_parts) >= 2:
                raw_role = role_map.get(name_parts[1] + " " + name_parts[0], "")
            if not raw_role:
                last = name_parts[0] if name_parts else ""
                first = name_parts[1] if len(name_parts) > 1 else ""
                for k, v in role_map.items():
                    if last in k and first in k:
                        raw_role = v
                        break

        if not raw_role and filing_name:
            parts = filing_name.split(" - ")
            if len(parts) > 1:
                raw_role = parts[-1].strip()

        role = classify_role(raw_role) if raw_role else classify_role(filing_name)
        if role == "Insider" and abs(chg) > 100000:
            role = "Beneficial Owner"

        chg_str = f"{abs(chg):,}"
        own_str = f"{shares_own:,} sh owned" if shares_own > 0 else ""
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

# ════════════════════════════════════════════════════════════════════
# POLYMARKET HELPERS
# ════════════════════════════════════════════════════════════════════

_POLY_OUTCOME_SUFFIX = re.compile(
    r'[-/](?:yes|no|above|below|over|under|before|after|true|false|\d+[a-z%]*)$',
    re.IGNORECASE
)

def _clean_poly_slug(slug):
    """Strip outcome suffixes from a Polymarket slug to get the parent event URL.
    e.g. 'will-trump-nominate-scott-bessent-as-fed-chair-yes' → 'will-trump-nominate-scott-bessent-as-fed-chair'
         'who-will-win-2024-election/donald-trump' → 'who-will-win-2024-election'
    """
    if not slug:
        return slug
    slug = slug.strip().strip('/')
    # Remove path component if present (market sub-paths)
    if '/' in slug:
        slug = slug.split('/')[0]
    # Iteratively strip known outcome suffixes
    for _ in range(3):
        cleaned = _POLY_OUTCOME_SUFFIX.sub('', slug)
        if cleaned == slug:
            break
        slug = cleaned
    return slug

def poly_url(evt):
    """Build correct Polymarket PARENT event URL — never a sub-market outcome URL."""
    # Prefer event-level slug directly from the events endpoint
    slug = evt.get("slug", "") or ""
    if slug:
        return f"https://polymarket.com/event/{_clean_poly_slug(slug)}"
    # Fall back to building from title
    title = evt.get("title", "") or evt.get("question", "") or ""
    if title:
        auto_slug = re.sub(r'[^a-z0-9]+', '-', title.lower())[:70].strip('-')
        if auto_slug:
            return f"https://polymarket.com/event/{auto_slug}"
    return "https://polymarket.com"

def poly_status(m):
    """Determine if market is active, resolved, or expired"""
    closed = m.get("closed", False)
    resolved = m.get("resolved", False)
    end_date_iso = m.get("endDate", "") or m.get("end_date_utc", "") or ""
    if resolved: return "RESOLVED", "poly-status-resolved"
    if closed:   return "CLOSED", "poly-status-closed"
    if end_date_iso:
        try:
            end = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
            if end < datetime.now(pytz.utc):
                return "EXPIRED (pending resolve)", "poly-status-closed"
        except:
            pass
    return "ACTIVE", "poly-status-active"

def unusual_side(m):
    """Determine which side unusual volume favors"""
    try:
        outcomes = _parse_poly_field(m.get("outcomes", []))
        out_prices = _parse_poly_field(m.get("outcomePrices", []))
        if not out_prices or not outcomes: return None, None
        yes_p = _safe_float(out_prices[0]) * 100
        yes_name = str(outcomes[0]) if outcomes else "YES"
        no_name = str(outcomes[1]) if len(outcomes) > 1 else "NO"
        if yes_p > 60: return yes_name, "poly-unusual-yes"
        elif yes_p < 40: return no_name, "poly-unusual-no"
        else: return "BOTH SIDES", "poly-unusual-yes"
    except:
        return None, None

def _extract_participants(evt, limit=5):
    """Extract top participants from an event's nested markets array."""
    markets = evt.get("markets", [])
    if not markets:
        return []
    participants = []
    for mk in markets:
        name = mk.get("groupItemTitle") or mk.get("question", "")[:40]
        prices = _parse_poly_field(mk.get("outcomePrices", []))
        p = _safe_float(prices[0]) if prices else 0.0
        participants.append((name, p))
    participants.sort(key=lambda x: x[1], reverse=True)
    return participants[:limit]


def render_poly_card(evt, show_unusual=False):
    """Render a Polymarket event card with up to 5 participants and their probabilities."""
    raw_title = evt.get("title", evt.get("question", "Unknown")) or "Unknown"
    title_esc = _esc(raw_title[:100])
    url = poly_url(evt)
    v24 = _safe_float(evt.get("volume24hr", 0))
    vtot = _safe_float(evt.get("volume", 0))
    status_lbl, status_cls = poly_status(evt)
    t_html = f'<a href="{url}" target="_blank">{title_esc}</a>'

    is_settled = status_lbl in ("RESOLVED", "CLOSED")

    participants = _extract_participants(evt, limit=5)

    prob_rows = ""
    if participants:
        for name, p_raw in participants:
            p = max(0.0, min(100.0, p_raw * 100))
            bar_c = "#00CC44" if p >= 50 else ("#FF8C00" if p >= 20 else "#FF4444")
            is_winner = is_settled and p_raw >= 0.95
            winner_tag = (f' &nbsp;<span style="background:#00CC44;color:#000;'
                          f'font-size:9px;font-weight:700;padding:1px 5px">✓ WINNER</span>'
                          if is_winner else "")
            outcome_name = _esc(str(name)[:35])
            prob_rows += (
                f'<div style="display:flex;align-items:center;gap:8px;margin-top:5px">'
                f'<span style="color:{bar_c};font-size:11px;min-width:44px;font-weight:700">{p:.0f}%</span>'
                f'<span style="color:#AAA;font-size:10px;flex:1">{outcome_name}{winner_tag}</span>'
                f'<div style="width:160px;height:5px;background:#1A1A1A;border-radius:1px;overflow:hidden">'
                f'<div style="width:{min(p, 100):.0f}%;height:100%;background:{bar_c};border-radius:1px"></div>'
                f'</div></div>')
    else:
        outcomes = _parse_poly_field(evt.get("outcomes", []))
        out_prices = _parse_poly_field(evt.get("outcomePrices", []))
        if outcomes and out_prices:
            for i, outcome in enumerate(outcomes[:2]):
                if i >= len(out_prices): break
                p = max(0.0, min(100.0, _safe_float(out_prices[i]) * 100))
                bar_c = "#00CC44" if p >= 50 else "#FF4444"
                outcome_name = _esc(str(outcome)[:30])
                prob_rows += (
                    f'<div style="display:flex;align-items:center;gap:8px;margin-top:5px">'
                    f'<span style="color:{bar_c};font-size:11px;min-width:44px;font-weight:700">{p:.0f}%</span>'
                    f'<span style="color:#888;font-size:10px;flex:1">{outcome_name}</span>'
                    f'<div style="width:160px;height:5px;background:#1A1A1A;border-radius:1px;overflow:hidden">'
                    f'<div style="width:{p:.0f}%;height:100%;background:{bar_c};border-radius:1px"></div>'
                    f'</div></div>')

    unusual_html = ""
    if show_unusual:
        ratio = v24 / vtot * 100 if vtot > 0 else 0
        unusual_html = (f'<div style="margin-top:5px;padding:3px 6px;background:rgba(255,102,0,0.08);border-left:2px solid #FF6600">'
                        f'⚡ Unusual volume ({ratio:.0f}% of total in 24h)</div>')

    def _fmt_vol(v):
        if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
        if v >= 1_000:     return f"${v/1_000:.1f}K"
        return f"${v:.0f}"

    vol_str = f"24H: {_fmt_vol(v24)} &nbsp;|&nbsp; TOTAL: {_fmt_vol(vtot)}"
    n_markets = len(evt.get("markets", []))
    count_str = f" &nbsp;·&nbsp; {n_markets} markets" if n_markets > 1 else ""

    return (f'<div class="poly-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px">'
            f'<div style="font-size:13px;font-weight:600;flex:1">{t_html}</div>'
            f'<span class="{status_cls}" style="margin-left:8px;white-space:nowrap">{status_lbl}</span>'
            f'</div>'
            f'{prob_rows}{unusual_html}'
            f'<div style="color:#444;font-size:10px;margin-top:6px;letter-spacing:0.5px">{vol_str}{count_str}</div>'
            f'</div>')

# ════════════════════════════════════════════════════════════════════
# GEMINI AI
# ════════════════════════════════════════════════════════════════════

SENTINEL_PROMPT = """You are SENTINEL — a Bloomberg-grade financial and geopolitical intelligence terminal.

═══ CORE RULES ═══
• CURRENT DATE/TIME is injected at the top of every message as "CURRENT DATE/TIME: ...". Use this EXACT date in every header. NEVER use your training cutoff date.
• LIVE MARKET DATA is injected with real prices. Anchor ALL analysis to these exact figures.
• LIVE GEOPOLITICAL HEADLINES are injected when available. You MUST reference specific headline events in geo analysis — never substitute generic placeholder events.
• SPX (S&P 500 Index) is the primary market barometer. It must appear in every brief and analysis by name and price.
• Never fabricate prices, events, or data. If data is missing, say so.
• Always trace 2nd and 3rd-order effects.
• Every response MUST include a Bear Case.
• Label confidence: HIGH / MEDIUM / LOW / UNCONFIRMED
• End any trade idea with: ⚠️ Research only, not financial advice.

═══ /brief — SENTINEL INTELLIGENCE BRIEFING ═══
Produce a structured briefing using EXACTLY this format and section order.
Use the injected date, prices, and headlines — do not invent any.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SENTINEL BRIEFING — {EXACT DATE FROM INJECTION} {TIME PST}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▌ MARKET SNAPSHOT
  SPX   [price] [%chg] — [one-line read: trend/tone]
  SPY   [price] [%chg]
  QQQ   [price] [%chg]
  IWM   [price] [%chg]
  DXY   [price] [%chg] — [one-line read]
  VIX   [price]        — [risk tone: calm / elevated / fear]
  GLD   [price] [%chg]
  Oil   [price] [%chg]

▌ GEOPOLITICAL RADAR
  Use the injected LIVE GEOPOLITICAL HEADLINES as your primary source.
  IMPORTANT: If the injected headlines appear incomplete or missing major known events
  (e.g. Israel-Iran strikes, Ukraine escalation, Taiwan tensions, Red Sea Houthi attacks),
  supplement with your most recent training knowledge and clearly label those entries
  as [MODEL KNOWLEDGE] vs [LIVE HEADLINE].
  
  For each event (minimum 2, maximum 4):
  [EVENT NAME] — [Current status in 1-2 sentences]
  → Affected markets: [list specific assets/sectors, e.g. OIL, XLE, defense ETFs, EM FX]
  → Most probable outcome: [state clearly, assign % if possible]
  → Tail risk: [low-probability high-impact scenario]

▌ MACRO THEMES  (3 dominant forces driving today's flows)
  1. [Theme] — [2-sentence explanation with asset implications]
  2. [Theme] — [2-sentence explanation with asset implications]
  3. [Theme] — [2-sentence explanation with asset implications]

▌ SECTOR WATCH
  Leading  : [sector] — [reason in one line]
  Lagging  : [sector] — [reason in one line]
  Watch    : [sector] — [catalyst to monitor]

▌ MACRO TRADE IDEA  ← required every brief
  Use the injected MACRO & RATES DATA to anchor this. Pick the highest-conviction
  macro theme from today's data (rates, DXY, gold, crude, credit spreads, EM, commodities).
  Theme    : [e.g. "Dollar breakdown", "Gold breakout on rate cut expectations", "Oil spike on Middle East risk"]
  Rationale: [2-sentence thesis grounded in injected rates/macro data]
  Instrument: [ETF, futures, or pair trade — e.g. GLD, TLT, UUP short, XLE, EEM]
  Entry    : [price or trigger condition from injected data]
  Target   : [price with reasoning]
  Stop     : [price with reasoning]
  Timeframe: [1 day / 1-2 weeks / 1 month]
  ⚠️ Research only, not financial advice.

▌ BEAR CASE
  [The single biggest risk that invalidates today's consensus — be specific, not generic]

▌ CONFIDENCE: [HIGH / MEDIUM / LOW] — [one sentence explaining the key uncertainty]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

═══ /flash [TICKER] — RAPID STOCK INTELLIGENCE ═══
  ⚡ FLASH: [TICKER] — [date PST]
  Price    : [price] [%chg]  52wk: [position vs high/low]
  Momentum : [breakout / breakdown / consolidation / reversal]
  Catalyst : [recent news, earnings, analyst action]
  Options  : [IV context, notable flow if known]
  Setup    : Entry [x] | Target [x] | Stop [x] — [one-line thesis]
  Bear case: [what kills this trade]
  CONFIDENCE: [level]
  ⚠️ Research only, not financial advice.

═══ /scenario [ASSET] — SCENARIO ANALYSIS ═══
  SCENARIO ANALYSIS: [ASSET] — [date PST]
  Current  : [price, trend, key levels]
  BULL ([%]) : [catalyst → target → timeline]
  BASE ([%]) : [most likely path → signposts]
  BEAR ([%]) : [trigger → downside target]
  Macro sensitivity: [rate/DXY/recession sensitivity]
  Best trade expression: [setup with defined risk]
  CONFIDENCE: [level]

═══ /geo [REGION or EVENT] — GEOPOLITICAL INTEL ═══
  GEO INTEL: [REGION/EVENT] — [date PST]
  Situation   : [3-5 sentences on current status, referencing injected headlines]
  Stakeholders: [key actors and incentives]
  Market impact:
    Immediate  — [assets already pricing this]
    Near-term  — [1-4 week spillover]
    Tail risk  — [low-prob, high-impact]
  Most probable outcome: [clear statement + confidence %]
  Hedge/Trade : [specific positioning idea]
  CONFIDENCE  : [HIGH / MEDIUM / LOW / UNCONFIRMED]

═══ /poly [TOPIC] — POLYMARKET ANALYSIS ═══
  POLY: [TOPIC] — [date PST]
  Market odds   : [YES/NO prices if known]
  Crowd vs base rate: [is market over/underpriced?]
  Key variables : [2-3 factors determining outcome]
  If YES wins   : [what moves]
  If NO wins    : [what moves]
  Edge          : [mispricing direction + rationale]
  CONFIDENCE    : [level]

═══ /rotate — SECTOR ROTATION ═══
  SECTOR ROTATION — [date PST]
  Cycle position: [Early/Mid/Late expansion or contraction]
  Inflows  : [sectors gaining]  Outflows: [sectors bleeding]
  OVERWEIGHT  (3): [sector + 1-line thesis each]
  UNDERWEIGHT (3): [sector + 1-line thesis each]
  Factor watch: [value/growth/momentum/defensive performance]
  CONFIDENCE: [level]

═══ /sentiment — SENTIMENT ANALYSIS ═══
  SENTIMENT — [date PST]
  Fear/Greed  : [VIX read + put/call + positioning]
  Breadth     : [broad-based or mega-cap concentrated]
  Retail/Inst : [notable divergence if any]
  Contrarian  : [is sentiment extreme enough to fade?]
  Positioning : [allocation recommendation given sentiment]
  CONFIDENCE  : [level]

═══ /earnings — EARNINGS INTEL ═══
  EARNINGS INTEL — [date PST]
  This week's prints: [top 5 by market impact]
  For each: consensus vs. options-implied move | sector read-through | surprise risk
  Setups: [pre-earnings plays with defined risk]
  CONFIDENCE: per name

═══ OUTPUT RULES ═══
• Use the exact section headers and dividers shown above.
• Numbers and prices before narrative. Every sentence must add information — no padding.
• Plain-English questions get the same analytical rigor without the slash-command structure."""

GEMINI_MODELS = [
    "gemini-2.5-flash-preview-05-20",  # latest Gemini 2.5 preview
    "gemini-2.5-flash",                # stable 2.5
    "gemini-2.0-flash",                # stable 2.0
    "gemini-2.0-flash-lite",           # lightweight fallback
]

def list_gemini_models(key):
    """List available Gemini models via the new google-genai SDK."""
    try:
        from google import genai
        client = genai.Client(api_key=key)
        return [m.name for m in client.models.list()]
    except Exception as e:
        return [f"Error: {e}"]

def gemini_response(user_msg, history, context=""):
    """
    Send a message to Gemini using the google-genai SDK.
    `context` is the output of market_snapshot_str() — it already contains
    the current date/time AND live market prices as a structured string.
    These are injected at the very top of the user message so the model
    cannot hallucinate the date from training data.
    """
    if not st.session_state.gemini_key:
        return "⚠️ Add your Gemini API key in .streamlit/secrets.toml."
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=st.session_state.gemini_key)

        # ── Build the enriched user message ──────────────────────────────────
        # context already contains: "CURRENT DATE/TIME: ...\nLIVE MARKET DATA: ..."
        # Append any user-configured session context below that.
        ctx_sections = []
        if context:
            ctx_sections.append(context)                          # date + live prices (always first)
        if getattr(st.session_state, "macro_theses", None):
            ctx_sections.append(f"USER MACRO THESIS: {st.session_state.macro_theses}")
        if getattr(st.session_state, "geo_watch", None):
            ctx_sections.append(f"USER GEO WATCHLIST: {st.session_state.geo_watch}")
        if getattr(st.session_state, "watchlist", None):
            ctx_sections.append(f"USER TICKER WATCHLIST: {', '.join(st.session_state.watchlist)}")

        header = "\n".join(ctx_sections)
        full_user_msg = f"{header}\n\n{user_msg}" if header else user_msg

        # ── Convert chat history to new SDK Content objects ───────────────────
        contents = []
        for m in history[-12:]:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=full_user_msg)]))

        # ── Try each model in priority order ─────────────────────────────────
        errors = []
        for model_name in GEMINI_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SENTINEL_PROMPT,
                        max_output_tokens=4096,
                        temperature=0.35,
                    ),
                )
                return f"*[{model_name}]*\n\n{response.text}"
            except Exception as e:
                err_str = str(e)
                errors.append(f"{model_name}: {err_str[:90]}")
                soft = ["not found", "404", "429", "quota", "resource_exhausted",
                        "unavailable", "deprecated", "invalid argument"]
                if any(x in err_str.lower() for x in soft):
                    continue          # try next model
                return f"⚠️ Gemini error ({model_name}): {e}"   # hard error — stop

        return "⚠️ All models exhausted.\n\nAttempted:\n" + "\n".join(errors)

    except ImportError:
        return "⚠️ google-genai not installed. Run: pip install google-genai"
    except Exception as e:
        return f"⚠️ Error: {e}"

# ════════════════════════════════════════════════════════════════════
# 0DTE TAB HELPERS
# ════════════════════════════════════════════════════════════════════

def render_0dte_gex_chart(gex, gf_spy, mp_spy, spot_spx=None, display_pct=0.05):
    """Renders the Gamma Exposure (GEX) Plotly bar chart.

    FIX: Removed text labels above bars (too small/overlapping).
         Added large, readable hover tooltip via hoverlabel.
         Staggered annotations vertically to prevent overlap.

    Args:
        gex: dict {spy_key: $M}
        gf_spy: gamma flip in SPY scale
        mp_spy: max pain in SPY scale
        spot_spx: SPX spot price for range filtering + spot line
        display_pct: ±% window around spot to display (default 0.05 = ±5%)
    """
    if not gex or go is None: return None

    all_strikes_spx = [k * 10 for k in sorted(gex.keys())]
    all_gex_vals = [gex[k / 10] for k in all_strikes_spx]

    # Filter to ±display_pct around spot for a tight, readable chart
    if spot_spx and spot_spx > 0:
        lo = spot_spx * (1 - display_pct)
        hi = spot_spx * (1 + display_pct)
        pairs = [(s, v) for s, v in zip(all_strikes_spx, all_gex_vals) if lo <= s <= hi]
    else:
        pairs = list(zip(all_strikes_spx, all_gex_vals))

    if not pairs:
        pairs = list(zip(all_strikes_spx, all_gex_vals))

    strikes_spx, gex_vals = zip(*pairs) if pairs else ([], [])
    colors = ["#00CC44" if v >= 0 else "#FF4444" for v in gex_vals]

    fig = go.Figure(go.Bar(
        x=list(strikes_spx), y=list(gex_vals),
        marker=dict(color=colors, line=dict(width=0)),
        # ── FIX: No text labels on bars — they were too small and overlapping
        hovertemplate=(
            "<b style='font-size:15px'>Strike: %{x:,.0f}</b><br>"
            "<b style='font-size:14px'>GEX: $%{y:.2f}M</b>"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        **CHART_LAYOUT,
        height=360,
        xaxis_title="SPX Strike",
        yaxis_title="GEX ($M)",
        title=dict(
            text="Dealer Gamma Exposure by Strike",
            font=dict(color="#FF6600", size=12)
        ),
        bargap=0.15,
        # ── FIX: Larger, more readable hover tooltip
        hoverlabel=dict(
            bgcolor="#0D0D0D",
            bordercolor="#FF6600",
            font=dict(size=14, color="#FF8C00", family="IBM Plex Mono"),
            namelength=0,
        ),
    )

    # ── FIX: Stagger annotation y-positions to prevent overlap
    # Spot line — top right, yref paper so it's always visible
    if spot_spx:
        fig.add_vline(
            x=spot_spx,
            line=dict(color="#FFFFFF", dash="solid", width=1.5),
            annotation_text=f"Spot: {spot_spx:,.0f}",
            annotation_font=dict(color="#FFFFFF", size=11, family="IBM Plex Mono"),
            annotation_position="top right",
            annotation_yshift=0,
        )
    # Gamma flip — top left, shifted down to avoid spot label
    if gf_spy:
        fig.add_vline(
            x=gf_spy * 10,
            line=dict(color="#FFCC00", dash="dash", width=1.2),
            annotation_text=f"γ Flip: {gf_spy * 10:,.0f}",
            annotation_font=dict(color="#FFCC00", size=11, family="IBM Plex Mono"),
            annotation_position="top left",
            annotation_yshift=-22,   # shift down so it doesn't collide with spot
        )
    # Max pain — bottom right, well separated from top labels
    if mp_spy:
        fig.add_vline(
            x=mp_spy * 10,
            line=dict(color="#AA44FF", dash="dot", width=1.2),
            annotation_text=f"Max Pain: {mp_spy * 10:,.0f}",
            annotation_font=dict(color="#AA44FF", size=11, family="IBM Plex Mono"),
            annotation_position="bottom right",
            annotation_yshift=8,
        )
    return fig


def render_0dte_gex_decoder(gf_spy, mp_spy, wall_spx, wall_dir, spot_spx=None, wall_gex_m=None):
    """Renders the GEX Decoder with dynamic wall-hit explanation."""
    gf_str = f"${gf_spy * 10:,.0f}" if gf_spy else "—"
    mp_str = f"${mp_spy * 10:,.0f}" if mp_spy else "—"

    wall_rel = ""
    if spot_spx and wall_spx and wall_spx != "—":
        try:
            wall_val = float(wall_spx.replace("$", "").replace(",", ""))
            dist = wall_val - spot_spx
            direction = "above" if dist > 0 else "below"
            wall_rel = f"<span style='color:#888'>({abs(dist):,.0f} pts {direction} spot)</span>"
        except Exception:
            pass

    if wall_dir == "Call Wall":
        wall_action = (
            "<b style='color:#00CC44'>Call Wall</b> — Dealers are long gamma here. "
            "As price rallies toward this strike, dealers must <b>sell futures/stock</b> to stay delta-neutral, "
            "creating a natural ceiling. Price tends to <b>stall or pin</b> at this level. "
            "A confirmed break above it forces dealers to <b>flip long</b> → can trigger a sharp squeeze."
        )
    elif wall_dir == "Put Wall":
        wall_action = (
            "<b style='color:#FF4444'>Put Wall</b> — Dealers are short gamma here. "
            "As price drops toward this strike, dealers must <b>sell more futures/stock</b> to hedge, "
            "which <b>accelerates the decline</b>. Acts as a momentum amplifier, not a floor. "
            "A bounce above it forces dealers to <b>cover shorts</b> → snap-back risk."
        )
    else:
        wall_action = "<span style='color:#888'>No dominant wall identified.</span>"

    if gf_spy and spot_spx:
        gf_spx = gf_spy * 10
        if spot_spx > gf_spx:
            flip_ctx = (f"<span style='color:#00CC44'>▲ Above Gamma Flip ({gf_str}) — "
                        f"Positive gamma: dealers dampen volatility, mean-reversion bias.</span>")
        else:
            flip_ctx = (f"<span style='color:#FF4444'>▼ Below Gamma Flip ({gf_str}) — "
                        f"Negative gamma: dealers amplify moves, trend-following bias.</span>")
    else:
        flip_ctx = f"<span style='color:#888'>Gamma Flip: {gf_str}</span>"

    wall_size_str = f" (${wall_gex_m:.1f}M notional)" if wall_gex_m is not None else ""

    return f"""
<div style="background:#0A0A0A;border:1px solid #222;border-left:3px solid #FF6600;
padding:14px 16px;font-family:monospace;font-size:11px;line-height:1.9">
<div style="color:#FF6600;font-weight:700;font-size:12px;letter-spacing:1px;margin-bottom:8px">
GEX DECODER</div>
<div style="color:#CCCCCC">
{flip_ctx}<br>
<span style="color:#AA44FF">▸ Max Pain:</span> {mp_str}<br>
<span style="color:#FF8C00">▸ Biggest Wall:</span> {wall_spx} ({wall_dir}){wall_size_str} {wall_rel}<br>
<hr style="border-color:#222;margin:8px 0">
<div style="color:#FF8C00;font-size:10px;font-weight:700;letter-spacing:1px;margin-bottom:4px">
⚡ IF PRICE HITS THE WALL</div>
<div style="color:#CCCCCC;line-height:1.8">{wall_action}</div>
<hr style="border-color:#222;margin:8px 0">
<span style="color:#888;font-size:10px">
<span style="color:#00CC44">Green bars</span> = Call GEX → dealer resistance (sells into strength)<br>
<span style="color:#FF4444">Red bars</span> = Put GEX → dealer acceleration (sells into weakness)
</span>
</div></div>"""

def render_0dte_recommendation(rec):
    """Renders the 0DTE Trade Analyzer recommendation output with Greeks breakdown."""
    conf_c = {"HIGH": "#00CC44", "MODERATE": "#FF8C00", "LOW": "#FF4444"}.get(rec["confidence"], "#888888")
    if "NO TRADE" in rec['recommendation']:
        conf_c = "#555555"
        
    met_str = ', '.join(rec['conditions_met']) if rec['conditions_met'] else 'None'
    failed_str = ', '.join(rec['conditions_failed']) if rec['conditions_failed'] else 'None'

    stats_html = rec['stats'].replace('\n', '<br>') if rec.get('stats') else ''

    return f"""
<div style="background:#0A0A0A;border:1px solid #222;border-left:4px solid {conf_c};
padding:16px 18px;font-family:monospace;font-size:12px;line-height:1.9;margin:8px 0">
<div style="color:{conf_c};font-weight:700;font-size:14px;letter-spacing:1px;margin-bottom:10px">
{rec['recommendation']}</div>
<div style="color:#CCCCCC">{rec['rationale']}</div>
<div style="background:#050505;border:1px solid #1A1A1A;padding:10px 12px;margin:10px 0;
font-size:11px;line-height:1.8;letter-spacing:0.3px">
<div style="color:#FF6600;font-weight:700;font-size:10px;letter-spacing:1px;margin-bottom:4px">
GREEKS ANALYSIS</div>
<div style="color:#FF8C00">{stats_html}</div>
</div>
<div style="color:#CCCCCC;margin-top:6px">{rec['action']}</div>
<hr style="border-color:#222;margin:10px 0">
<div style="font-size:10px">
<span style="color:#00CC44">✅ {met_str}</span><br>
<span style="color:#FF4444">❌ {failed_str}</span><br>
<span style="color:#555">Confidence: {rec['confidence']} | Ask: ${rec.get('mid_price', 0):.2f} (SPY) | 1 contract</span>
</div></div>"""

def render_0dte_trade_log(entries):
    """Renders the compact horizontal trade log for 0DTE."""
    if not entries: return ""
    html = ""
    for entry in entries:
        if "CALL" in entry:
            bc, bg = "#00CC44", "rgba(0,204,68,0.1)"
        elif "PUT" in entry:
            bc, bg = "#FF4444", "rgba(255,68,68,0.1)"
        else:
            bc, bg = "#888", "rgba(136,136,136,0.1)"
        html += (f'<span style="display:inline-block;background:{bg};border:1px solid {bc};'
                 f'color:{bc};padding:3px 8px;margin:2px 4px;font-size:10px;'
                 f'font-family:monospace;font-weight:600;letter-spacing:0.5px">{entry}</span>')
                 
    return f"""
<div style="background:#050505;border:1px solid #222;border-top:2px solid #FF6600;
padding:8px 10px;margin-top:4px">
<div style="color:#FF6600;font-size:9px;font-weight:700;letter-spacing:2px;margin-bottom:6px;
font-family:monospace">TRADE LOG</div>
<div style="display:flex;flex-wrap:wrap;gap:2px">{html}</div>
</div>"""

# ════════════════════════════════════════════════════════════════════
# GEO TAB — RENDER FUNCTION
# ════════════════════════════════════════════════════════════════════


def _geo_network_embed_html(network):
    """HTML block: single financial network live stream with robust fallback."""
    name = network["name"]
    embed_url = network.get("embed_url", "")

    # Build an HTML page with a primary iframe and a JS fallback.
    # If the live_stream?channel= embed fails (shows "unavailable"),
    # the onerror / onload handler swaps to a channel /live page.
    channel_id = network.get("channel_id", "")
    fallback_url = f"https://www.youtube.com/channel/{channel_id}/live" if channel_id else ""

    return f'''
    <div style="background:#030303;padding:10px;border:1px solid #1A1A1A;
                border-top:2px solid #FF6600;margin-bottom:8px">
      <div style="font-family:monospace;font-size:11px;color:#FF6600;
                  letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">
        📡 {name} — LIVE
      </div>
      <div style="position:relative;width:100%;padding-top:56.25%;background:#000">
        <iframe id="net-frame"
                src="{embed_url}"
                style="position:absolute;top:0;left:0;width:100%;height:100%;border:1px solid #1A1A1A"
                frameborder="0"
                allow="autoplay; encrypted-media"
                allowfullscreen>
        </iframe>
      </div>
      <div style="font-family:monospace;font-size:9px;color:#333;margin-top:6px;
                  display:flex;justify-content:space-between">
        <span>Auto-embed via YouTube Live</span>
        <a href="https://www.youtube.com/channel/{channel_id}/live"
           target="_blank"
           style="color:#FF6600;text-decoration:none">
          Open in YouTube ↗
        </a>
      </div>
    </div>
    '''


def _geo_webcam_region_html(region_cams):
    """HTML block: webcam feeds for a specific region in a uniform CSS grid."""
    # Determine column count: 2 columns for <=4 cams, 3 for more
    cols = 2 if len(region_cams) <= 4 else 3
    items = ""
    for cam in region_cams:
        src   = f"https://www.youtube.com/embed/{cam['fallbackVideoId']}?autoplay=1&mute=1"
        label = f"{cam['city']}, {cam['country']}"
        items += (
            f'<div>'
            f'<div style="font-family:monospace;font-size:10px;color:#888;'
            f'letter-spacing:1px;padding:3px 0;margin-bottom:4px">{label}</div>'
            f'<div style="position:relative;width:100%;padding-top:56.25%;background:#000">'
            f'<iframe src="{src}" '
            f'style="position:absolute;top:0;left:0;width:100%;height:100%;border:1px solid #1A1A1A" '
            f'frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>'
            f'</div>'
            f'</div>'
        )
    return (
        f'<div style="background:#030303;padding:8px;border:1px solid #1A1A1A">'
        f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:10px">{items}</div>'
        f'</div>'
    )


# ════════════════════════════════════════════════════════════════════
# CRYPTO ETF FLOWS CHART
# ════════════════════════════════════════════════════════════════════

def render_crypto_etf_chart(df, height=420, is_estimated=False):
    """Render a dark-themed stacked bar chart of daily BTC Spot ETF net flows.

    Args:
        df: DataFrame with date index, columns = ETF tickers + 'Total'
        height: chart height in px
        is_estimated: if True, adds a label that data is estimated (yfinance fallback)

    Returns:
        plotly.graph_objects.Figure or None
    """
    if df is None or df.empty or go is None:
        return None

    fig = go.Figure()

    # Stacked bars — one trace per ETF
    etf_cols = [c for c in df.columns if c in _ETF_TICKERS]
    for ticker in etf_cols:
        color = _ETF_COLORS.get(ticker, "#FF8C00")
        fig.add_trace(go.Bar(
            x=df.index,
            y=df[ticker],
            name=ticker,
            marker_color=color,
            marker_line_width=0,
            opacity=0.9,
            hovertemplate=f"<b>{ticker}</b><br>%{{x|%b %d}}<br>${{y:,.1f}}M<extra></extra>",
        ))

    # Cumulative trendline
    if "Total" in df.columns:
        cumulative = df["Total"].cumsum()
        fig.add_trace(go.Scatter(
            x=df.index,
            y=cumulative,
            name="Cumulative Net Flow",
            mode="lines",
            line=dict(color="#FFFFFF", width=2, dash="solid"),
            yaxis="y2",
            hovertemplate="<b>Cumulative</b><br>%{x|%b %d}<br>$%{y:,.0f}M<extra></extra>",
        ))

    title_text = "INSTITUTIONAL BTC ETF FLOWS — DAILY NET ($M)"
    if is_estimated:
        title_text += "  ⚠ ESTIMATED (yfinance proxy)"

    fig.update_layout(
        barmode="relative",
        paper_bgcolor="#000000",
        plot_bgcolor="#050505",
        font=dict(color="#FF8C00", family="IBM Plex Mono"),
        height=height,
        margin=dict(l=0, r=60, t=40, b=0),
        title=dict(
            text=title_text,
            font=dict(size=11, color="#FF6600"),
            x=0,
        ),
        xaxis=dict(
            gridcolor="#111111",
            color="#555555",
            showgrid=False,
            tickfont=dict(size=9, color="#888"),
        ),
        yaxis=dict(
            title="Daily Net Flow ($M)",
            titlefont=dict(size=9, color="#666"),
            gridcolor="#111111",
            color="#555555",
            showgrid=True,
            tickfont=dict(size=9, color="#888"),
            zeroline=True,
            zerolinecolor="#333333",
            zerolinewidth=1,
        ),
        yaxis2=dict(
            title="Cumulative ($M)",
            titlefont=dict(size=9, color="#888"),
            overlaying="y",
            side="right",
            showgrid=False,
            color="#555555",
            tickfont=dict(size=9, color="#888"),
        ),
        legend=dict(
            font=dict(size=9, color="#888"),
            bgcolor="rgba(0,0,0,0)",
            orientation="h",
            x=0, y=1.08,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#111111",
            font=dict(size=11, color="#FF8C00", family="IBM Plex Mono"),
            bordercolor="#333",
        ),
    )

    return fig


@st.fragment(run_every="10m")
def render_geo_tab():
    """
    Full Geo Tab — @st.fragment so it auto-refreshes every 10 min without
    triggering a full-app rerun.

    Sections:
      1. 3D Globe (globe.html — military air / satellites / conflict events / infra)
      2. Live Network Selector (toggle between news networks)
      3. Live Webcam Grid (toggle by region)
      4. GDELT theater intel feed + commodity/currency impact radar
    """
    import streamlit.components.v1 as _components
    import pathlib as _pathlib

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="bb-ph">🌍 GEOPOLITICAL INTELLIGENCE — LIVE GLOBE + SURVEILLANCE MATRIX</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:#555;font-family:monospace;font-size:10px;margin-bottom:6px">'
        'Auto-refresh every 10 minutes · Toggle networks and webcam regions below'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── 1. 3D Globe ───────────────────────────────────────────────────────────
    st.markdown(
        '<div class="bb-ph">🌐 3D INTELLIGENCE GLOBE — MILITARY AIR · SATELLITES · CONFLICT EVENTS</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:#555;font-family:monospace;font-size:10px;margin-bottom:6px">'
        'Drag to rotate · Scroll to zoom · Click markers for intel · Toggle layers in left sidebar'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Fetch dynamic geo data and inject into globe.html ──────────────
    with st.spinner("Loading geo intelligence feeds…"):
        _geo_events  = fetch_conflict_events_json()
        _geo_planes  = fetch_military_aircraft_json()
        _geo_sats    = fetch_satellite_positions_json()
        _geo_vessels = fetch_ais_vessels()
        _geo_infra   = GEO_SHIPPING_LANES

    # Build JSON injection script
    _sentinel_data = json.dumps({
        "events":  _geo_events,
        "planes":  _geo_planes,
        "sats":    _geo_sats,
        "vessels": _geo_vessels,
        "infra":   _geo_infra,
    }, default=str)
    _inject_script = (
        f'<script>window.__SENTINEL_DATA__ = {_sentinel_data};</script>\n'
    )

    # Read globe.html from disk and prepend injected data
    globe_path = _pathlib.Path(__file__).parent / "globe.html"
    try:
        globe_html = globe_path.read_text(encoding="utf-8")
        # Inject data right after <head> so it's available before globe JS runs
        if '<head>' in globe_html:
            globe_html = globe_html.replace('<head>', '<head>\n' + _inject_script, 1)
        else:
            globe_html = _inject_script + globe_html
        _components.html(globe_html, height=700, scrolling=False)
    except FileNotFoundError:
        st.error("⚠️ globe.html not found — place it in the same directory as ui_components.py.")

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ── 2. Live Network Selector ──────────────────────────────────────────────
    st.markdown(
        '<div class="bb-ph" style="margin-top:4px">📺 LIVE FINANCIAL NETWORK</div>',
        unsafe_allow_html=True,
    )

    network_names = [n["name"] for n in GEO_FINANCIAL_NETWORKS]
    selected_network = st.radio(
        "Select Network",
        network_names,
        horizontal=True,
        key="geo_network_sel",
        label_visibility="collapsed",
    )

    # Find the selected network and embed it
    net_obj = next((n for n in GEO_FINANCIAL_NETWORKS if n["name"] == selected_network), GEO_FINANCIAL_NETWORKS[0])
    _components.html(_geo_network_embed_html(net_obj), height=780, scrolling=False)

    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)

    # ── 3. Live Webcam Grid — Toggle by Region ────────────────────────────────
    st.markdown(
        '<div class="bb-ph">🌍 LIVE GLOBAL CAMS</div>',
        unsafe_allow_html=True,
    )

    # Build unique ordered region list
    seen_regions = []
    for cam in GEO_WEBCAM_FEEDS:
        r = cam.get("region", "Other")
        if r not in seen_regions:
            seen_regions.append(r)

    selected_region = st.radio(
        "Select Region",
        seen_regions,
        horizontal=True,
        key="geo_webcam_region",
        label_visibility="collapsed",
    )

    region_cams = [cam for cam in GEO_WEBCAM_FEEDS if cam.get("region") == selected_region]
    if region_cams:
        _components.html(_geo_webcam_region_html(region_cams), height=780, scrolling=True)
    else:
        st.markdown(
            '<div style="color:#555;font-family:monospace;font-size:11px">'
            'No webcams available for this region.</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="margin:4px 0;border-top:1px solid #111"></div>',
        unsafe_allow_html=True,
    )

    # ── 4. Theater intel feed + commodity radar ────────────────────────────────
    geo_col1, geo_col2 = st.columns([3, 1])

    with geo_col1:
        theater_sel = st.selectbox(
            "📡 THEATER INTEL FEED",
            list(GEO_THEATERS.keys()) + ["Custom query…"],
            key="geo_theater",
        )
        custom_q = ""
        if theater_sel == "Custom query…":
            custom_q = st.text_input("Custom GDELT query", key="geo_cq")
        query = custom_q if custom_q else GEO_THEATERS.get(theater_sel, "")

        if query:
            with st.spinner(f"Fetching GDELT feed for: {query}…"):
                arts = gdelt_news(query, max_rec=12)
            if arts:
                st.markdown(
                    f'<div class="bb-ph">GDELT LIVE FEED — {len(arts)} articles</div>',
                    unsafe_allow_html=True,
                )
                for art in arts:
                    t   = art.get("title", "")[:100]
                    u   = art.get("url", "#")
                    dom = art.get("domain", "GDELT")
                    sd  = art.get("seendate", "")
                    d   = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) >= 8 else ""
                    st.markdown(render_news_card(t, u, dom, d, "bb-news bb-news-geo"), unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div style="background:#0D0D0D;border-left:3px solid #FF6600;'
                    'padding:10px 12px;font-family:monospace;font-size:11px;color:#888">'
                    'No articles found in GDELT for this query.</div>',
                    unsafe_allow_html=True,
                )

            # NewsAPI layer (if key available)
            newsapi_key = st.session_state.get("newsapi_key")
            if newsapi_key:
                with st.spinner("Loading NewsAPI layer…"):
                    na_arts = newsapi_headlines(newsapi_key, query)
                if na_arts:
                    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
                    st.markdown('<div class="bb-ph">NEWSAPI LAYER — 150K+ SOURCES</div>', unsafe_allow_html=True)
                    for art in na_arts[:8]:
                        title = art.get("title", "")
                        if not title or "[Removed]" in title:
                            continue
                        u   = art.get("url", "#")
                        src = art.get("source", {}).get("name", "")
                        pub = art.get("publishedAt", "")[:10]
                        st.markdown(render_news_card(title[:100], u, src, pub, "bb-news bb-news-macro"), unsafe_allow_html=True)

    with geo_col2:
        st.markdown('<div class="bb-ph">📊 COMMODITY & CURRENCY IMPACT RADAR</div>', unsafe_allow_html=True)
        impact_qs = multi_quotes(list(GEO_IMPACT_TICKERS.values()))
        for q in impact_qs:
            name = next((k for k, v in GEO_IMPACT_TICKERS.items() if v == q["ticker"]), q["ticker"])
            c   = pct_color(q["pct"])
            arr = "▲" if q["pct"] >= 0 else "▼"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:4px 0;border-bottom:1px solid #111;'
                f'font-family:monospace;font-size:12px">'
                f'<span style="color:#CCC">{name}</span>'
                f'<span style="color:{c};font-weight:700">{arr} {q["pct"]:+.2f}% &nbsp; {fmt_p(q["price"])}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)
        st.markdown('<div class="bb-ph">📖 CONFIDENCE LEVELS</div>', unsafe_allow_html=True)
        for lbl, c, desc in [
            ("HIGH",        "#00CC44", "Multiple verified sources"),
            ("MEDIUM",      "#FF8C00", "Single source / partial confirm"),
            ("LOW",         "#FFCC00", "Unverified rumor"),
            ("UNCONFIRMED", "#555",    "Raw signal only"),
        ]:
            st.markdown(
                f'<div style="font-family:monospace;font-size:10px;padding:3px 0">'
                f'<span style="color:{c};font-weight:700">{lbl}</span> '
                f'<span style="color:#444">— {desc}</span></div>',
                unsafe_allow_html=True,
            )

