"""Single-ticker deep dive (used by the Markets page)."""
from __future__ import annotations

import re

import streamlit as st
import streamlit.components.v1 as components

from sentinel.core.formatting import _esc, _safe_float, fmt_p, fmt_usd, fmt_vol
from sentinel.core.http import get_yf_ticker
from sentinel.data.fundamentals import (
    finnhub_insider, finnhub_officers, get_balance_sheet_metrics, get_earnings_matrix, get_finra_short_volume,
    get_full_financials, get_profitability_metrics, smart_money_conviction_buys,
)
from sentinel.data.market import get_ticker_exchange, yahoo_quote
from sentinel.state import key
from sentinel.ui.components import (
    bar_html, cards, colored, empty, note, render_insider_cards, section, signed, table, tv_chart,
)
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT, UP, signed_color
from sentinel.ui.theme import dark_fig, go, plot

TV_MAP = {
    "SPY": "AMEX:SPY", "QQQ": "NASDAQ:QQQ", "IWM": "AMEX:IWM", "GLD": "AMEX:GLD", "TLT": "NASDAQ:TLT",
    "BTC-USD": "COINBASE:BTCUSD", "ETH-USD": "COINBASE:ETHUSD", "SOL-USD": "COINBASE:SOLUSD",
    "GC=F": "COMEX:GC1!", "CL=F": "NYMEX:CL1!", "ES=F": "CME_MINI:ES1!", "NQ=F": "CME_MINI:NQ1!",
    "^GSPC": "SP:SPX", "^VIX": "TVC:VIX", "^TNX": "TVC:TNX", "DX-Y.NYB": "TVC:DXY", "DXY": "TVC:DXY",
}


@st.cache_data(ttl=1800, show_spinner=False)
def _company_info(t: str) -> dict:
    tk = get_yf_ticker(t)
    try:
        info = tk.info if tk is not None else {}
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _dividend_yield_pct(info: dict, price: float | None):
    """Dividend yield in percent.

    Recent yfinance returns ``dividendYield`` already in percent (0.44 = 0.44%),
    older builds returned a fraction — so derive it from the annual rate when possible.
    """
    rate = _safe_float(info.get("dividendRate") or info.get("trailingAnnualDividendRate"), None)
    if rate and price:
        return rate / price * 100
    # yfinance >= 0.2.54 (pinned in requirements) reports dividendYield in percent.
    return _safe_float(info.get("dividendYield"), None)


def _num(v, fmt="{:.2f}", suffix=""):
    v = _safe_float(v, None)
    return "—" if v is None else fmt.format(v) + suffix


def _overview(t, q, info):
    price = q["price"]
    cards([
        ("Last", fmt_p(price, t), f"{q['pct']:+.2f}%  {q['change']:+,.2f}", signed_color(q["pct"])),
        ("Day range", f"{fmt_p(q.get('low'), t)} – {fmt_p(q.get('high'), t)}" if q.get("low") else "—"),
        ("Volume", fmt_vol(q.get("volume")), f"avg {fmt_vol(info.get('averageVolume'))}" if info.get("averageVolume") else ""),
        ("52-week range", f"{_num(info.get('fiftyTwoWeekLow'))} – {_num(info.get('fiftyTwoWeekHigh'))}"),
        ("Market cap", fmt_usd(info.get("marketCap"))),
    ], 150)
    tv_sym = TV_MAP.get(t) or get_ticker_exchange(t)
    components.html(tv_chart(tv_sym, 460), height=465)

    desc = info.get("longBusinessSummary") or ""
    if desc:
        short = " ".join(re.split(r"(?<=[.!?])\s+", desc.strip())[:3])
        meta = " · ".join(_esc(x) for x in (info.get("sector"), info.get("industry")) if x)
        st.markdown(f'<div class="s-note"><div style="color:{TEXT};margin-bottom:4px">{_esc(info.get("longName") or t)}'
                    f'{" · " + meta if meta else ""}</div>{_esc(short)}</div>', unsafe_allow_html=True)

    dy = _dividend_yield_pct(info, price)
    pe = _safe_float(info.get("trailingPE"), None)
    cards([
        ("P/E trailing", _num(pe, "{:.1f}", "×") if pe and pe > 0 else "—"),
        ("P/E forward", _num(info.get("forwardPE"), "{:.1f}", "×") if _safe_float(info.get("forwardPE"), 0) > 0 else "—"),
        ("EPS (TTM)", _num(info.get("trailingEps"), "${:.2f}")),
        ("EV / EBITDA", _num(info.get("enterpriseToEbitda"), "{:.1f}", "×") if _safe_float(info.get("enterpriseToEbitda"), 0) > 0 else "—"),
        ("P / S", _num(info.get("priceToSalesTrailing12Months"), "{:.2f}", "×")),
        ("Dividend yield", f"{dy:.2f}%" if dy else "—"),
        ("Beta (5Y)", _num(info.get("beta"))),
        ("Revenue (TTM)", fmt_usd(info.get("totalRevenue"))),
    ], 130)


def _quality(t):
    prof, bs = get_profitability_metrics(t), get_balance_sheet_metrics(t)
    left, right = st.columns(2)
    with left:
        section("Profitability")
        if prof:
            rows = [[lbl, signed((v or 0) * 100, "{:+.1f}", "%") if v is not None else "—"]
                    for lbl, v in (("Gross margin", prof.get("gross_margin")), ("Operating margin", prof.get("op_margin")),
                                   ("EBITDA margin", prof.get("ebitda_margin")), ("Net margin", prof.get("net_margin")),
                                   ("Return on assets", prof.get("roa")), ("Return on equity", prof.get("roe")))]
            table(["Metric", "Value"], rows)
        else:
            empty("Profitability data unavailable.")
    with right:
        section("Balance sheet")
        if bs:
            cr, qr, de = bs.get("current_ratio"), bs.get("quick_ratio"), bs.get("de_ratio")
            rows = [
                ["Total cash", fmt_usd(bs.get("total_cash"))],
                ["Total debt", fmt_usd(bs.get("total_debt"))],
                ["Net cash / (debt)", colored(fmt_usd(bs["net_cash_debt"]), signed_color(bs["net_cash_debt"]))
                 if bs.get("net_cash_debt") is not None else "—"],
                ["Debt / equity", f"{de:.0f}%" if de is not None else "—"],
                ["Current ratio", f"{cr:.2f}×" if cr is not None else "—"],
                ["Quick ratio", f"{qr:.2f}×" if qr is not None else "—"],
            ]
            table(["Metric", "Value"], rows)
        else:
            empty("Balance-sheet data unavailable.")

    fin = get_full_financials(t)
    if fin:
        section("Quarterly financials")
        qs = sorted(fin, reverse=True)
        spec = [("Revenue", "revenue", "$"), ("Gross profit", "gross_profit", "$"), ("Operating income", "op_income", "$"),
                ("Net income", "net_income", "$"), ("EBITDA", "ebitda", "$"), ("Operating cash flow", "op_cashflow", "$"),
                ("Free cash flow", "free_cashflow", "$"), ("Gross margin", "gross_margin", "%"),
                ("Operating margin", "op_margin", "%"), ("Net margin", "net_margin", "%"),
                ("Diluted EPS", "eps", "eps"), ("Cash", "cash", "$"), ("Total debt", "total_debt", "$")]
        rows = []
        for lbl, k, unit in spec:
            cells = []
            for qd in qs:
                v = fin[qd].get(k)
                if v is None:
                    cells.append('<span class="dim">—</span>')
                elif unit == "%":
                    cells.append(f"{v:.1f}%")
                elif unit == "eps":
                    cells.append(colored(f"{v:.2f}", signed_color(v)))
                else:
                    cells.append(colored(fmt_usd(v), DOWN) if v < 0 else fmt_usd(v))
            rows.append([lbl] + cells)
        table(["Metric"] + qs, rows)


def _earnings(t):
    em = get_earnings_matrix(t)
    if not em:
        return
    section("Earnings history", "EPS actual vs estimate by fiscal quarter · ✓ beat / ✗ miss")
    years, qls = em["years"][-5:], em["q_labels"]
    rows = []
    for ql in qls:
        cells = [ql]
        for yr in years:
            v = em["quarterly"].get(yr, {}).get(ql)
            if v is None:
                cells.append('<span class="dim">—</span>')
                continue
            beat = em["beats"].get(yr, {}).get(ql)
            est = em["estimates"].get(yr, {}).get(ql)
            mark = colored(" ✓", UP) if beat is True else colored(" ✗", DOWN) if beat is False else ""
            sub = f'<span class="em-sub">est {est:.2f}</span>' if est is not None else ""
            cells.append(f"{v:.2f}{mark}{sub}")
        rows.append(cells)
    rows.append(["Fiscal year"] + [(f"<b>{em['annual'][y]:.2f}</b>" if y in em["annual"] else "—") for y in years])
    table(["Quarter"] + [f"FY{y}" for y in years], rows)
    streak = em.get("streak", 0)
    cards([
        ("Beat rate", f"{em.get('beat_rate', 0):.0f}%", "of reported quarters"),
        ("Streak", f"{abs(streak)} {'beats' if streak > 0 else 'misses' if streak < 0 else ''}".strip() if streak else "—",
         "consecutive", FLAT, UP if streak > 0 else DOWN if streak < 0 else TEXT),
        ("Forward EPS", f"{em['forward_eps']:.2f}" if em.get("forward_eps") else "—"),
    ], 150)

    rev = em.get("revenue_q") or {}
    pts = [(f"{ql[:2]} FY{str(yr)[-2:]}", rev[yr][ql]) for yr in sorted(rev) for ql in qls if ql in rev.get(yr, {})]
    if len(pts) >= 3:
        fig = dark_fig(240, title=dict(text="Quarterly revenue"), hovermode="x unified")
        fig.add_trace(go.Bar(x=[p[0] for p in pts], y=[p[1] for p in pts], marker_color=SERIES[2],
                             marker_line_width=0, hovertemplate="%{x}: $%{y:,.0f}<extra></extra>"))
        plot(fig, key=f"rev_{t}")

    ar = em.get("analyst_ratings") or {}
    if ar.get("total_rated") or ar.get("target_mean"):
        section("Analyst consensus")
        total = max(ar.get("total_rated") or 0, 1)
        rows = [[lbl, f"{n}", bar_html(n / total * 100, c)] for lbl, n, c in (
            ("Strong buy", ar.get("strong_buy", 0), UP), ("Buy", ar.get("buy", 0), UP),
            ("Hold", ar.get("hold", 0), FLAT), ("Sell", ar.get("sell", 0), DOWN),
            ("Strong sell", ar.get("strong_sell", 0), DOWN))]
        c1, c2 = st.columns([3, 2])
        with c1:
            table(["Rating", "Analysts", ""], rows, align="lrl")
        with c2:
            price, tm = em.get("price") or 0, ar.get("target_mean") or 0
            upside = (tm / price - 1) * 100 if price and tm else None
            cards([
                ("Consensus", ar.get("consensus", "—"), f"{ar.get('num_analysts', 0)} analysts"),
                ("Mean target", f"${tm:,.2f}" if tm else "—",
                 f"{upside:+.1f}% vs last" if upside is not None else "", signed_color(upside or 0)),
                ("Target range", f"${ar.get('target_low', 0):,.0f} – ${ar.get('target_high', 0):,.0f}"
                 if ar.get("target_low") else "—"),
            ], 140)


def _insiders(t):
    fk = key("finnhub_key")
    if not fk:
        note("Add a Finnhub key (sidebar) to see insider transactions.")
        return
    ins = finnhub_insider(t, fk)
    roles = finnhub_officers(t, fk)
    section("Insider transactions", "Finnhub · Form 4")
    if not ins:
        empty("No recent insider transactions.")
        return
    st.markdown(render_insider_cards(ins, t, role_map=roles), unsafe_allow_html=True)
    buys = smart_money_conviction_buys(ins, roles)
    if buys:
        section("Open-market purchases (code P)", "Excludes awards, option exercises, tax withholding and gifts.")
        rows = [[_esc(b["name"][:28]), _esc(b["role"][:24]), b["date"], f"{b['shares']:,}", fmt_usd(b["dollar_value"]),
                 f"<b>{b['score']}</b>"] for b in buys[:8]]
        table(["Insider", "Role", "Date", "Shares", "Value", "Score"], rows)


def _short_interest(t):
    si = get_finra_short_volume(t)
    section("Short interest", "Exchange-reported, published twice a month (via Yahoo)")
    if not si:
        empty("Short-interest data unavailable for this symbol.")
        return
    pct = si["short_pct_float"]
    cards([
        ("Short % of float", f"{pct:.2f}%" if pct is not None else "—", "above 20% is very high"),
        ("Shares short", fmt_vol(si["short_shares"]) if si["short_shares"] is not None else "—"),
        ("Days to cover", f"{si['days_to_cover']:.1f}" if si["days_to_cover"] is not None else "—",
         "short interest ÷ avg daily volume"),
    ], 150)


def render_ticker(t: str) -> None:
    q = yahoo_quote(t)
    if not q:
        note(f"No quote found for “{t}”. Check the symbol (Yahoo format, e.g. BRK-B, BTC-USD, ^GSPC).", "warn")
        return
    info = _company_info(t)
    _overview(t, q, info)
    if info.get("quoteType") in ("EQUITY", None, "") and not t.startswith("^") and "=" not in t and "-USD" not in t:
        _quality(t)
        _earnings(t)
        _insiders(t)
        _short_interest(t)
