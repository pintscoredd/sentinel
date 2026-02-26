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
)

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
    # Ensure strike is numeric
    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce").fillna(0)

    # ── Remove 13 deepest OTM/ITM strikes ──
    if current_price and "strike" in df.columns and len(df) > 13:
        df["_dist"] = (df["strike"] - current_price).abs()
        df = df.nsmallest(len(df) - 13, "_dist").drop(columns=["_dist"])

    strike_color = "#00CC44" if side == "calls" else "#FF4444"
    # Find ATM strike (nearest to current price)
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
    # Complete SEC transaction code mapping
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
        # Determine buy/sell from change direction if code is ambiguous
        if chg < 0 and cls == "buy" and code not in ("P", "A", "M", "X", "C"):
            cls = "sell"
        if chg > 0 and cls == "sell" and code not in ("S", "D", "G", "F"):
            cls = "buy"

        # Role detection: try multiple name formats against executive map
        name_upper = str(tx.get("name", "")).upper().strip()
        filing_name = str(tx.get("filingName", "") or "")

        # Try exact match first
        raw_role = role_map.get(name_upper, "")

        # Try without middle initial/suffix: "KRESS COLETTE M" → "KRESS COLETTE"
        if not raw_role and name_upper:
            name_parts = name_upper.split()
            if len(name_parts) >= 2:
                # Try just first two parts (LAST FIRST)
                raw_role = role_map.get(" ".join(name_parts[:2]), "")
            if not raw_role and len(name_parts) >= 2:
                # Try reversed: "KRESS COLETTE" → check "COLETTE KRESS"
                raw_role = role_map.get(name_parts[1] + " " + name_parts[0], "")
            if not raw_role:
                # Partial match: check if any key in role_map contains the last name
                last = name_parts[0] if name_parts else ""
                first = name_parts[1] if len(name_parts) > 1 else ""
                for k, v in role_map.items():
                    if last in k and first in k:
                        raw_role = v
                        break

        # Fallback: check filingName for role info
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
# POLYMARKET HELPERS — Fix #4: robust slug stripping
# ════════════════════════════════════════════════════════════════════

# Regex to strip outcome suffixes like -yes, -no, -1t, -above, -below, etc.
_POLY_OUTCOME_SUFFIX = re.compile(
    r'-(?:yes|no|above|below|over|under|before|after|\d+[a-z]*)$',
    re.IGNORECASE
)

def poly_url(evt):
    """Build correct Polymarket event URL from an event object."""
    slug = evt.get("slug", "") or ""
    if slug:
        return f"https://polymarket.com/event/{slug.strip().strip('/')}"
    # Fallback: try title
    title = evt.get("title", "") or evt.get("question", "") or ""
    if title:
        auto_slug = re.sub(r'[^a-z0-9]+', '-', title.lower())[:60].strip('-')
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
    """Extract top participants from an event's nested markets array.
    Each market's outcomePrices[0] is the 'Yes' probability for that participant.
    Returns [(name, probability_float), ...] sorted by probability desc, limited to `limit`.
    """
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

    # Extract participants from nested markets
    participants = _extract_participants(evt, limit=5)

    prob_rows = ""
    if participants:
        # Multi-participant event (e.g., "Who will be Fed Chair?")
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
        # Fallback: simple binary Yes/No from the event's own outcomes
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

    vol_str = f"24H: ${v24:,.0f} &nbsp;|&nbsp; TOTAL: ${vtot:,.0f}"
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

SENTINEL_PROMPT = """You are SENTINEL — a professional Bloomberg-grade financial and geopolitical intelligence terminal.
VOICE: Concise, data-first. Define jargon once. Trace 2nd and 3rd-order effects.
RULES: Never fabricate. Always include bear case. Label confidence HIGH/MEDIUM/LOW/UNCONFIRMED.
Timestamp PST. End trade ideas with: ⚠️ Research only, not financial advice.
FORMATS: /brief /flash [ticker] /scenario [asset] /geo [region] /poly [topic] /rotate /sentiment /earnings"""

GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]

def list_gemini_models(key):
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        return [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
    except Exception as e:
        return [f"Error: {e}"]

def gemini_response(user_msg, history, context=""):
    if not st.session_state.gemini_key:
        return "⚠️ Add your Gemini API key in .streamlit/secrets.toml."
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
                gh = [{"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]} for m in history[-12:]]
                chat = model.start_chat(history=gh)
                return chat.send_message(f"{ctx}\n\nQuery: {user_msg}" if ctx else user_msg).text
            except Exception as e:
                last_err = str(e)
                if "not found" in last_err.lower() or "404" in last_err: continue
                return f"⚠️ Gemini error: {e}"
        return f"⚠️ All models failed. Last error: {last_err}"
    except ImportError:
        return "⚠️ google-generativeai not installed."
    except Exception as e:
        return f"⚠️ Error: {e}"

# ════════════════════════════════════════════════════════════════════
# 0DTE TAB HELPERS
# ════════════════════════════════════════════════════════════════════

def render_0dte_gex_chart(gex, gf_spy, mp_spy):
    """Renders the Gamma Exposure (GEX) Plotly bar chart."""
    if not gex or go is None: return None
    strikes_spx = [k * 10 for k in sorted(gex.keys())]
    gex_vals = [gex[k / 10] for k in strikes_spx]
    colors = ["#00CC44" if v >= 0 else "#FF4444" for v in gex_vals]
    
    fig = go.Figure(go.Bar(
        x=strikes_spx, y=gex_vals,
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"${v:.1f}M" for v in gex_vals], textposition="outside",
        textfont=dict(color="#FF8C00", size=9),
        hovertemplate="Strike: %{x}<br>GEX: $%{y:.2f}M<extra></extra>",
    ))
    
    fig.update_layout(**CHART_LAYOUT, height=350, xaxis_title="SPX Strike",
                      yaxis_title="GEX ($M)",
                      title=dict(text="Dealer Gamma Exposure by Strike",
                                 font=dict(color="#FF6600", size=12)))
    if gf_spy:
        fig.add_vline(x=gf_spy * 10, line=dict(color="#FFCC00", dash="dash", width=1),
                      annotation_text=f"Gamma Flip: {gf_spy * 10:.0f}",
                      annotation_font=dict(color="#FFCC00", size=10))
    if mp_spy:
        fig.add_vline(x=mp_spy * 10, line=dict(color="#AA44FF", dash="dot", width=1),
                      annotation_text=f"Max Pain: {mp_spy * 10:.0f}",
                      annotation_font=dict(color="#AA44FF", size=10),
                      annotation_position="bottom right")
    return fig

def render_0dte_gex_decoder(gf_spy, mp_spy, wall_spx, wall_dir):
    """Renders the GEX Decoder informational block."""
    gf_str = f"${gf_spy * 10:,.0f}" if gf_spy else "—"
    mp_str = f"${mp_spy * 10:,.0f}" if mp_spy else "—"
    return f"""
<div style="background:#0A0A0A;border:1px solid #222;border-left:3px solid #FF6600;
padding:14px 16px;font-family:monospace;font-size:11px;line-height:1.8">
<div style="color:#FF6600;font-weight:700;font-size:12px;letter-spacing:1px;margin-bottom:8px">
GEX DECODER</div>
<div style="color:#CCCCCC">
<span style="color:#FFCC00">▸ Gamma Flip:</span> {gf_str}<br>
<span style="color:#AA44FF">▸ Max Pain:</span> {mp_str}<br>
<span style="color:#FF8C00">▸ Biggest Wall:</span> {wall_spx} ({wall_dir})<br>
<hr style="border-color:#222;margin:8px 0">
<span style="color:#00CC44">Green bars</span> = Call GEX (dealers sell strength → resistance)<br>
<span style="color:#FF4444">Red bars</span> = Put GEX (dealers buy weakness → support)<br>
<hr style="border-color:#222;margin:8px 0">
<span style="color:#888">Wall hit → dealers hedge aggressively → price pins or reverses at the wall.</span><br>
<span style="color:#888">Above Gamma Flip = dealers dampen moves (mean-revert).<br>
Below Gamma Flip = dealers amplify moves (trend).</span>
</div></div>"""

def render_0dte_recommendation(rec):
    """Renders the 0DTE Trade Analyzer recommendation output with Greeks breakdown."""
    conf_c = {"HIGH": "#00CC44", "MODERATE": "#FF8C00", "LOW": "#FF4444"}.get(rec["confidence"], "#888888")
    if "NO TRADE" in rec['recommendation']:
        conf_c = "#555555"
        
    met_str = ', '.join(rec['conditions_met']) if rec['conditions_met'] else 'None'
    failed_str = ', '.join(rec['conditions_failed']) if rec['conditions_failed'] else 'None'

    # Handle multi-line stats (Greeks breakdown)
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
