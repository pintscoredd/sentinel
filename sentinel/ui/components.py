"""HTML building blocks shared by all pages.

Every renderer escapes external text. Multi-row data is emitted as a single
``<table>`` per section so columns align and wide tables scroll horizontally
instead of overflowing the page.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote, urlsplit

import pytz
import streamlit as st

from sentinel.core.formatting import _esc, _safe_float, _safe_int, fmt_vol
from sentinel.data.polymarket import _parse_poly_field, live_markets
from sentinel.ui.palette import DOWN, FLAT, TEXT, TEXT_DIM, UP, signed_color


# ── Section chrome ──────────────────────────────────────────────────────────
def section(title: str, sub: str = "") -> None:
    """Section header (+ optional one-line description)."""
    html = f'<div class="bb-ph">{_esc(title)}</div>'
    if sub:
        html += f'<div class="bb-sub">{_esc(sub)}</div>'
    st.markdown(html, unsafe_allow_html=True)


def divider() -> None:
    st.markdown('<hr class="bb-divider">', unsafe_allow_html=True)


def note(text: str, kind: str = "", html: bool = False) -> None:
    """Callout box. kind: '' | 'warn' | 'up' | 'dn'."""
    body = text if html else _esc(text)
    st.markdown(f'<div class="s-note {kind}">{body}</div>', unsafe_allow_html=True)


def empty(text: str) -> None:
    st.markdown(f'<div class="s-empty">{_esc(text)}</div>', unsafe_allow_html=True)


def colored(text, color: str, bold: bool = False) -> str:
    w = "font-weight:600;" if bold else ""
    return f'<span style="color:{color};{w}">{_esc(text)}</span>'


def signed(v, fmt: str = "{:+.2f}", suffix: str = "", bold: bool = False) -> str:
    """Value colored by sign (escaped)."""
    try:
        s = fmt.format(float(v)) + suffix
    except (TypeError, ValueError):
        return '<span class="dim">—</span>'
    return colored(s, signed_color(v), bold)


# ── Cards ───────────────────────────────────────────────────────────────────
def card_html(label: str, value: str, sub: str = "", sub_color: str = TEXT_DIM,
              value_color: str = TEXT) -> str:
    sub_html = f'<div class="s-card-sub" style="color:{sub_color}">{_esc(sub)}</div>' if sub else ""
    return (
        f'<div class="s-card"><div class="s-card-lbl">{_esc(label)}</div>'
        f'<div class="s-card-val" style="color:{value_color}">{_esc(value)}</div>{sub_html}</div>'
    )


def cards(items: list[tuple], min_width: int = 150) -> None:
    """Responsive grid of cards: items are (label, value[, sub[, sub_color[, value_color]]])."""
    if not items:
        return
    inner = "".join(card_html(*it) for it in items)
    st.markdown(
        f'<div class="s-cards" style="grid-template-columns:repeat(auto-fit,minmax({min_width}px,1fr))">{inner}</div>',
        unsafe_allow_html=True,
    )


# Back-compat helpers used by a few panels
def metric_card(label: str, value: str, color: str = TEXT, size: str = "16px", border_color: str = "") -> str:
    return card_html(label, value, value_color=color)


def metric_card_with_delta(label: str, value: str, delta: str, delta_color: str,
                           color: str = TEXT, border_color: str = "") -> str:
    return card_html(label, value, delta, delta_color, color)


def sentinel_grid(columns: str, children_html: str, gap: str = "10px", extra_style: str = "") -> str:
    return f'<div style="display:grid;grid-template-columns:{columns};gap:{gap};{extra_style}">{children_html}</div>'


# ── Tables ──────────────────────────────────────────────────────────────────
def table_html(headers: list[str], rows: list[list], align: str | None = None,
               row_classes: list[str] | None = None, max_height: int | None = None) -> str:
    """One aligned table. Cell values are trusted HTML (callers escape external text).

    *align*: string of 'l'/'r' per column (default: first column left, rest right).
    *row_classes*: optional per-row CSS class ('hl', 'sec', …).
    """
    n = len(headers)
    align = (align or ("l" + "r" * (n - 1)))[:n].ljust(n, "r")
    cls = {"l": "l", "c": "c", "w": "l"}
    th = "".join(f'<th class="{cls.get(a, "")}">{_esc(h)}</th>' for h, a in zip(headers, align))
    body = []
    for i, row in enumerate(rows):
        rcls = row_classes[i] if row_classes and i < len(row_classes) else ""
        if rcls == "sec":
            body.append(f'<tr class="sec"><td class="l" colspan="{n}">{row[0]}</td></tr>')
            continue
        tds = "".join(
            f'<td class="{cls.get(a, "")}{" wrap" if a == "w" else ""}">{"" if v is None else v}</td>'
            for v, a in zip(row, align)
        )
        body.append(f'<tr class="{rcls}">{tds}</tr>')
    style = f' style="max-height:{max_height}px;overflow-y:auto"' if max_height else ""
    return (f'<div class="s-tbl-wrap"{style}><table class="s-tbl"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def table(headers, rows, align=None, row_classes=None, max_height=None, empty_text="No data.") -> None:
    if not rows:
        empty(empty_text)
        return
    st.markdown(table_html(headers, rows, align, row_classes, max_height), unsafe_allow_html=True)


def bar_html(pct: float, color: str = "#8A8A8A") -> str:
    pct = max(0.0, min(100.0, _safe_float(pct, 0.0)))
    return f'<div class="s-bar"><div style="width:{pct:.0f}%;background:{color}"></div></div>'


def tkr(t) -> str:
    return f'<span class="s-tkr">{_esc(t)}</span>'


# ── TradingView ─────────────────────────────────────────────────────────────
def tv_chart(symbol, height=450, interval="60", range_="3M"):
    """TradingView advanced chart (values JSON-encoded so symbols cannot inject JS)."""
    cid = re.sub(r"[^A-Za-z0-9_]", "_", str(symbol))[:80] or "chart"
    height = max(200, min(1200, _safe_int(height, 450)))
    cfg = {
        "width": "100%", "height": height, "symbol": str(symbol), "interval": str(interval),
        "range": str(range_), "timezone": "America/New_York", "theme": "dark", "style": "1",
        "locale": "en", "toolbar_bg": "#000000", "enable_publishing": False,
        "hide_side_toolbar": False, "allow_symbol_change": True, "save_image": False,
        "withdateranges": True, "container_id": f"tv_c_{cid}",
        "backgroundColor": "rgba(0,0,0,1)", "gridColor": "rgba(24,24,24,1)",
        "studies": [],
        "overrides": {
            "paneProperties.background": "#000000",
            "paneProperties.vertGridProperties.color": "#181818",
            "paneProperties.horzGridProperties.color": "#181818",
            "mainSeriesProperties.candleStyle.upColor": UP,
            "mainSeriesProperties.candleStyle.downColor": DOWN,
            "mainSeriesProperties.candleStyle.borderUpColor": UP,
            "mainSeriesProperties.candleStyle.borderDownColor": DOWN,
            "mainSeriesProperties.candleStyle.wickUpColor": UP,
            "mainSeriesProperties.candleStyle.wickDownColor": DOWN,
        },
    }
    cfg_js = json.dumps(cfg).replace("</", "<\\/")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;background:#000;overflow:hidden}}#tv_c_{cid}{{width:100%;height:{height}px}}</style></head>
<body><div id="tv_c_{cid}"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({cfg_js});</script></body></html>"""


# ── News ────────────────────────────────────────────────────────────────────
def _safe_external_url(url) -> str:
    """Allow only absolute HTTP(S) links from external feeds."""
    if not url or url == "#":
        return ""
    try:
        parsed = urlsplit(str(url).strip())
    except (TypeError, ValueError):
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return str(url).strip()


def render_news_card(title, url, source, date_str, card_class="bb-news"):
    safe_url = _safe_external_url(url)
    title_s = _esc(str(title)[:140])
    t_html = (f'<a href="{_esc(safe_url)}" target="_blank" rel="noopener noreferrer">{title_s}</a>'
              if safe_url else f'<span class="t">{title_s}</span>')
    meta = " · ".join(_esc(x) for x in (source, date_str) if x)
    return f'<div class="{_esc(card_class)}">{t_html}<div class="bb-meta">{meta}</div></div>'


def gdelt_date(seendate: str) -> str:
    sd = str(seendate or "")
    return f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) >= 8 else ""


# ── Options tables ──────────────────────────────────────────────────────────
def render_options_table(df, side="calls", current_price=None):
    if df is None or getattr(df, "empty", True):
        return '<div class="s-empty">No contracts.</div>'
    import pandas as pd
    df = df.copy()
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df.dropna(subset=["strike"])
    if current_price and len(df) > 24:
        df = df.loc[(df["strike"] - current_price).abs().nsmallest(24).index].sort_values("strike")
    atm = None
    if current_price and not df.empty:
        atm = float(df.loc[(df["strike"] - current_price).abs().idxmin(), "strike"])
    rows = []
    for _, row in df.iterrows():
        s = _safe_float(row.get("strike"))
        lp = _safe_float(row.get("lastPrice"))
        b, a = _safe_float(row.get("bid")), _safe_float(row.get("ask"))
        mid = (b + a) / 2.0 if b > 0 and a > 0 else lp
        v, oi = _safe_int(row.get("volume")), _safe_int(row.get("openInterest"))
        iv = _safe_float(row.get("impliedVolatility"))
        voi = v / oi if oi > 0 else 0.0
        itm = current_price and ((side == "calls" and s < current_price) or (side == "puts" and s > current_price))
        cls = "opt-atm" if atm is not None and abs(s - atm) < 1e-9 else ("opt-itm" if itm else "")
        hv = ' class="opt-hvol"' if voi >= 1.0 else ""
        rows.append(
            f'<tr class="{cls}"><td>{s:,.2f}</td><td>{lp:.2f}</td><td>{b:.2f}</td><td>{a:.2f}</td>'
            f'<td>{mid:.2f}</td><td{hv}>{v:,}</td><td>{oi:,}</td><td>{voi:.2f}</td><td>{iv:.1%}</td></tr>'
        )
    return (
        '<div class="s-tbl-wrap"><table class="opt-tbl"><thead><tr><th>Strike</th><th>Last</th><th>Bid</th>'
        '<th>Ask</th><th>Mid</th><th>Vol</th><th>OI</th><th>V/OI</th><th>IV</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def render_scored_options(contracts, side="calls"):
    if not contracts:
        return '<div class="s-empty">No scored contracts.</div>'
    rows = []
    for c in contracts:
        rows.append([
            f'<span style="color:{UP if side == "calls" else DOWN};font-weight:600">{_safe_float(c.get("strike")):,.2f}</span>',
            f'{_safe_float(c.get("lastPrice")):.2f}',
            f'{_safe_float(c.get("bid")):.2f} / {_safe_float(c.get("ask")):.2f}',
            f'{_safe_int(c.get("volume")):,}', f'{_safe_int(c.get("openInterest")):,}',
            f'{_safe_float(c.get("iv")):.1%}', f'{_safe_float(c.get("delta")):+.2f}',
            f'{_safe_float(c.get("voi")):.2f}', f'<b>{_safe_float(c.get("score")):.3f}</b>',
        ])
    return table_html(["Strike", "Last", "Bid / Ask", "Vol", "OI", "IV", "Δ", "V/OI", "Score"], rows)


def render_unusual_trade(contract, ticker="", expiry=""):
    if not contract:
        return ""
    side = contract.get("side", "call")
    direction = colored("CALLS · BULLISH", UP, True) if side == "call" else colored("PUTS · BEARISH", DOWN, True)
    items = [
        ("Ticker", _esc(ticker)), ("Strike", f'{_safe_float(contract.get("strike")):,.2f}'),
        ("Expiry", _esc(expiry)),
        ("Vol / OI", f'{_safe_int(contract.get("volume")):,} / {_safe_int(contract.get("openInterest")):,} '
                     f'({_safe_float(contract.get("voi")):.1f}×)'),
        ("IV", f'{_safe_float(contract.get("iv")):.1%}'), ("Score", f'{_safe_float(contract.get("score")):.3f}'),
    ]
    cells = "".join(f'<div><div class="s-card-lbl">{k}</div><div class="num" style="margin-top:3px">{v}</div></div>'
                    for k, v in items)
    return (f'<div class="s-panel" style="margin:10px 0"><div style="display:flex;justify-content:space-between;'
            f'flex-wrap:wrap;gap:8px;margin-bottom:10px"><b>Unusual options activity</b>{direction}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px">{cells}</div></div>')


def render_stat_arb_cards(data):
    if not data:
        return '<div class="s-empty">Stat-arb data unavailable.</div>'
    rows = []
    for r in data:
        z, thr = r["zscore"], r.get("entry_thresh", 2.0)
        sig = r["signal"]
        sig_c = UP if sig.startswith("Long") else DOWN if sig.startswith("Short") else FLAT
        rows.append([
            f'<b>{_esc(r["t1"])} / {_esc(r["t2"])}</b><span class="em-sub">{_esc(r.get("direction", ""))}</span>',
            colored(f"{z:+.2f}", UP if z < -thr else DOWN if z > thr else TEXT, True),
            f"±{thr:.2f}σ", f'{r["beta"]:.3f}',
            f'{r["half_life"]:.1f}d' if r["half_life"] < 999 else "∞",
            f'{"yes" if r["coint"] else "no"} (p={r["pvalue"]:.3f})',
            colored(sig, sig_c, True),
        ])
    return table_html(["Pair", "Z-score", "Entry", "Hedge β", "Half-life", "Cointegrated", "Signal"], rows)


# ── Insiders ────────────────────────────────────────────────────────────────
_TX_CODES = {
    "P": ("PURCHASE", "buy"), "S": ("SALE", "sell"), "A": ("AWARD", "buy"), "D": ("DISPOSAL", "sell"),
    "M": ("OPTION EXERCISE", "buy"), "X": ("OPTION EXERCISE", "buy"), "G": ("GIFT", "sell"),
    "F": ("TAX WITHHOLDING", "sell"), "C": ("CONVERSION", "buy"), "W": ("INHERITANCE", "buy"),
    "J": ("OTHER", "buy"), "K": ("EQUITY SWAP", "sell"), "I": ("DISCRETIONARY", "buy"),
    "U": ("TENDER", "sell"), "H": ("EXPIRATION", "sell"), "L": ("SMALL ACQUISITION", "buy"),
    "Z": ("TRUST", "buy"), "V": ("VOLUNTARY", "buy"),
}


def insider_tx_label(tx) -> tuple[str, str]:
    """(label, 'buy'|'sell') from a Finnhub insider transaction (code + signed change)."""
    code = str(tx.get("transactionCode") or "").upper()
    chg = _safe_int(tx.get("change"))
    lbl, cls = _TX_CODES.get(code, (code or "TRANSACTION", "buy" if chg >= 0 else "sell"))
    if chg < 0:
        cls = "sell"
    elif chg > 0 and code not in ("S", "D", "G", "F", "K", "U", "H"):
        cls = "buy"
    return lbl, cls


def _lookup_role(name: str, role_map: dict) -> str:
    name_u = str(name or "").upper().strip()
    if not name_u or not role_map:
        return ""
    if name_u in role_map:
        return role_map[name_u]
    parts = name_u.replace(",", "").replace(".", "").split()
    if len(parts) >= 2:
        for k in (" ".join(parts[:2]), f"{parts[1]} {parts[0]}", f"{parts[-1]} {parts[0]}"):
            if k in role_map:
                return role_map[k]
        for k, v in role_map.items():
            if parts[0] in k and parts[-1] in k:
                return v
    return ""


def render_insider_cards(data, ticker="", role_map=None):
    if not data:
        return '<div class="s-empty">No insider transactions.</div>'
    role_map = role_map or {}
    out = []
    for tx in data[:10]:
        name = str(tx.get("name", "Unknown"))
        chg = _safe_int(tx.get("change"))
        lbl, cls = insider_tx_label(tx)
        role = _lookup_role(name, role_map) or "Insider"
        if role == "Insider" and any(k in name.upper() for k in ("LLC", " LP", "FUND", "CAPITAL", "MANAGEMENT", "TRUST", "PARTNERS", "HOLDINGS")):
            role = "Institutional holder"
        price = _safe_float(tx.get("transactionPrice"))
        value = f" · ${abs(chg) * price:,.0f}" if price > 0 and chg else ""
        own = _safe_int(tx.get("share"))
        out.append(
            f'<div class="ins-card {cls}"><div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">'
            f'<span class="ins-name">{_esc(name[:32])}</span><span class="ins-{cls}">{"▲" if cls == "buy" else "▼"} {lbl}</span></div>'
            f'<div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-top:3px">'
            f'<span class="ins-role">{_esc(role[:60])}</span>'
            f'<span class="ins-meta">{abs(chg):,} sh{value} · {_esc(str(tx.get("transactionDate", ""))[:10])}</span></div>'
            + (f'<div class="ins-meta" style="margin-top:2px">{own:,} sh held after</div>' if own > 0 else "")
            + "</div>"
        )
    return "".join(out)


# ── Polymarket ──────────────────────────────────────────────────────────────
_POLY_OUTCOME_SUFFIX = re.compile(
    r"[-/](?:yes|no|above|below|over|under|before|after|true|false|\d+[a-z%]*)$", re.IGNORECASE
)


def _clean_poly_slug(slug):
    if not slug:
        return slug
    slug = str(slug).strip().strip("/").split("/")[0]
    for _ in range(3):
        cleaned = _POLY_OUTCOME_SUFFIX.sub("", slug)
        if cleaned == slug:
            break
        slug = cleaned
    return slug


def poly_url(evt):
    """Parent event URL (slug is URL-quoted so it cannot break out of the href)."""
    slug = _clean_poly_slug(evt.get("slug", "") or "")
    if slug:
        return f"https://polymarket.com/event/{quote(slug, safe='-_')}"
    title = evt.get("title", "") or evt.get("question", "") or ""
    auto = re.sub(r"[^a-z0-9]+", "-", title.lower())[:70].strip("-")
    return f"https://polymarket.com/event/{auto}" if auto else "https://polymarket.com"


def poly_status(m):
    if m.get("resolved"):
        return "RESOLVED", ""
    if m.get("closed"):
        return "CLOSED", ""
    end = m.get("endDate", "") or m.get("end_date_utc", "") or ""
    if end:
        try:
            if datetime.fromisoformat(end.replace("Z", "+00:00")) < datetime.now(pytz.utc):
                return "PENDING RESOLUTION", ""
        except Exception:
            pass
    return "ACTIVE", "active"


def _extract_participants(evt, limit=5):
    out = []
    for mk in live_markets(evt):
        name = mk.get("groupItemTitle") or mk.get("question", "")[:40]
        prices = _parse_poly_field(mk.get("outcomePrices", []))
        out.append((name, _safe_float(prices[0]) if prices else 0.0))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:limit]


def render_poly_card(evt):
    title = _esc((evt.get("title") or evt.get("question") or "Untitled")[:120])
    url = _esc(poly_url(evt))
    status, cls = poly_status(evt)
    participants = _extract_participants(evt)
    if not participants:
        outcomes = _parse_poly_field(evt.get("outcomes", []))
        prices = _parse_poly_field(evt.get("outcomePrices", []))
        participants = [(o, _safe_float(p)) for o, p in zip(outcomes[:2], prices[:2])]
    settled = status in ("RESOLVED", "CLOSED")
    rows = ""
    for name, p in participants:
        pct = max(0.0, min(100.0, p * 100))
        win = ' <span class="poly-status active">WINNER</span>' if settled and p >= 0.95 else ""
        rows += (
            f'<div style="display:grid;grid-template-columns:52px 1fr minmax(80px,160px);gap:10px;align-items:center;margin-top:6px">'
            f'<span class="num" style="font-weight:600">{pct:.0f}%</span>'
            f'<span class="muted" style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc(str(name)[:60])}{win}</span>'
            f'{bar_html(pct, "#FFFFFF" if pct >= 50 else "#6E6E6E")}</div>'
        )
    v24, vtot = _safe_float(evt.get("volume24hr")), _safe_float(evt.get("volume"))
    n = len(live_markets(evt))
    meta = f"24h ${fmt_vol(v24)} · total ${fmt_vol(vtot)}" + (f" · {n} markets" if n > 1 else "")
    return (
        f'<div class="poly-card"><div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">'
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
        f'<span class="poly-status {cls}">{status}</span></div>{rows}'
        f'<div class="bb-meta">{meta}</div></div>'
    )


def quote_cards(quotes: list[dict], labels: dict | None = None, min_width: int = 140) -> None:
    """Price strip: one card per quote with signed day change."""
    from sentinel.core.formatting import fmt_p
    labels = labels or {}
    items = []
    for q in quotes:
        t = q["ticker"]
        sub = f"{q['pct']:+.2f}%  {q['change']:+,.2f}" if q.get("pct") is not None else ""
        items.append((labels.get(t, t), fmt_p(q["price"], t), sub, signed_color(q.get("pct"))))
    cards(items, min_width)
