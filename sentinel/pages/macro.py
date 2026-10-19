"""Macro: regime score, calendar, curve, inflation, liquidity, global rates, vol, correlations, COT."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from sentinel.core.formatting import _esc, fmt_usd
from sentinel.data.cross_asset import (
    get_cot_positioning, get_cross_asset_volatility, get_macro_correlation_matrix, get_sovereign_10y_yields,
)
from sentinel.data.macro import (
    fred_series, get_central_bank_rates, get_economic_surprise_index, get_macro_calendar, get_macro_overview,
    get_net_liquidity, get_yield_curve_inversions,
)
from sentinel.data.market import multi_quotes
from sentinel.state import key
from sentinel.ui.charts import cpi_vs_rates_chart, yield_curve_chart, yield_history_chart
from sentinel.ui.components import (
    bar_html, cards, divider, empty, note, section, signed, table,
)
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT, TEXT_DIM, UP, signed_color
from sentinel.ui.theme import chart_layout, dark_fig, go, plot

SUBPAGES = ["Overview", "Rates", "Liquidity & flows"]


def _regime(fk):
    ov = get_macro_overview(fk)
    if not ov:
        empty("Macro overview unavailable.")
        return
    color = {"EXPANSIONARY": UP, "CONTRACTIONARY": DOWN}.get(ov["env_label"], TEXT)
    st.markdown(
        f'<div class="s-panel" style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center">'
        f'<div><div class="s-card-lbl">US macro regime</div><div style="font-size:22px;font-weight:700;color:{color};margin-top:4px">'
        f'{_esc(ov["env_label"].title())}</div><div class="muted" style="font-size:13px;margin-top:4px">{_esc(ov["env_desc"])}</div></div>'
        f'<div style="text-align:right"><div class="num" style="font-size:26px;font-weight:700;color:{color}">{ov["total_score"]:+d}</div>'
        f'<div class="dim" style="font-size:11px">score of ±{ov["max_score"]}</div></div></div>',
        unsafe_allow_html=True)
    rows = []
    for name, sig in ov["signals"].items():
        c = UP if sig["score"] > 0 else DOWN if sig["score"] < 0 else FLAT
        dots = "●" * abs(sig["score"]) + "○" * (2 - abs(sig["score"]))
        rows.append([_esc(name), f'<span style="color:{c}">{_esc(sig["label"])}</span>',
                     f'<span style="color:{c};letter-spacing:2px">{dots}</span>'])
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    table(["Indicator", "Reading", "Signal"], rows, align="llr")


def _key_indicators(fk):
    start = (date.today().replace(year=date.today().year - 2)).isoformat()
    items = []

    def _yoy(code):
        df = fred_series(code, fk, start=start)
        if df is None or len(df) < 14:
            return None, None, None
        yoy = df["value"].pct_change(12) * 100
        return float(yoy.iloc[-1]), float(yoy.iloc[-1] - yoy.iloc[-2]), df["date"].iloc[-1]

    for label, code in (("CPI inflation (YoY)", "CPIAUCSL"), ("Core PCE (YoY)", "PCEPILFE")):
        v, d, dt = _yoy(code)
        if v is not None:
            items.append((label, f"{v:.2f}%", f"{d:+.2f} pts m/m · {dt:%b %Y}", signed_color(-d)))
    for label, code, unit in (("Fed funds (effective)", "DFF", "%"), ("Unemployment", "UNRATE", "%"),
                              ("HY credit spread", "BAMLH0A0HYM2", "%")):
        df = fred_series(code, fk, 40)
        if df is not None and len(df) >= 2:
            v, p = df["value"].iloc[-1], df["value"].iloc[-2]
            items.append((label, f"{v:.2f}{unit}", f"{v - p:+.2f} · {df['date'].iloc[-1]:%b %d, %Y}",
                          signed_color(-(v - p))))
    m2 = fred_series("M2SL", fk, start=start)
    if m2 is not None and len(m2) >= 14:
        yoy = (m2["value"].iloc[-1] / m2["value"].iloc[-13] - 1) * 100
        items.append(("M2 money supply", fmt_usd(m2["value"].iloc[-1] * 1e9), f"{yoy:+.1f}% YoY · {m2['date'].iloc[-1]:%b %Y}"))
    if items:
        cards(items, 170)


def _calendar(fk):
    cal = get_macro_calendar(fk, finnhub_key=key("finnhub_key"))
    if not cal:
        empty("No upcoming releases found.")
        return
    today = date.today()
    src = cal[0].get("source", "")
    rows, classes = [], []
    for ev in cal[:20]:
        days = (ev["date"] - today).days
        when = "Today" if days == 0 else ("Tomorrow" if days == 1 else (f"in {days}d" if days > 0 else f"{-days}d ago"))
        imp = ev.get("importance", "MEDIUM")
        detail = " · ".join(x for x in (f"act {ev['actual']}" if ev.get("actual") else "",
                                        f"est {ev['forecast']}" if ev.get("forecast") else "",
                                        f"prev {ev['previous']}" if ev.get("previous") else "") if x)
        rows.append([f"{ev['date']:%a %b %d}", f'<span class="dim">{when}</span>', _esc(ev["name"]),
                     f'<span style="color:{TEXT if imp == "HIGH" else TEXT_DIM};font-weight:{700 if imp == "HIGH" else 400}">{imp.title()}</span>',
                     f'<span class="dim">{_esc(detail)}</span>'])
        classes.append("hl" if days <= 1 else "")
    table(["Date", "", "Release", "Impact", "Detail"], rows, align="llllr", row_classes=classes)
    if src == "est.":
        st.caption("Estimated schedule (rule-of-thumb dates). Add a FRED or Finnhub key for official release dates.")
    else:
        st.caption(f"Source: {src}")


def _surprise():
    esi = get_economic_surprise_index(key("finnhub_key"))
    if not esi or esi.get("_no_key"):
        note("Data-vs-consensus surprises need a Finnhub key with economic-calendar access.")
        return
    c = signed_color(esi["avg_surprise_pct"])
    cards([("Recent data vs consensus", esi["label"].title(), f"avg {esi['avg_surprise_pct']:+.1f}% · "
            f"{esi['above']}/{esi['count']} above", TEXT_DIM, c)], 200)
    rows = [[f"{it['date']}", _esc(it["name"][:48]), f"{it['actual']:g}", f"{it['forecast']:g}",
             signed(it["surprise_pct"], "{:+.1f}", "%")] for it in esi["items"][:8]]
    table(["Date", "Release", "Actual", "Consensus", "Surprise"], rows, align="llrrr")


def _overview(fk):
    _regime(fk)
    divider()
    section("Key indicators", "Latest FRED observations")
    _key_indicators(fk)
    divider()
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Economic calendar", "Next 45 days")
        _calendar(fk)
    with right:
        section("Data surprises")
        _surprise()
    divider()
    fig = cpi_vs_rates_chart(fk)
    if fig:
        plot(fig, key="cpi_rates")


def _rates(fk):
    tq = multi_quotes(("^IRX", "^FVX", "^TNX", "^TYX"))
    if tq:
        names = {"^IRX": "13-week bill", "^FVX": "5Y", "^TNX": "10Y", "^TYX": "30Y"}
        items = [(names[q["ticker"]], f"{q['price']:.3f}%", f"{q['change'] * 100:+.1f} bp today",
                  signed_color(-q["change"])) for q in tq]
        cards(items, 150)
        st.caption("Intraday Treasury yields (CBOE indices via Yahoo). Change shown in basis points.")
    left, right = st.columns(2, gap="large")
    with left:
        fig = yield_curve_chart(fk)
        if fig:
            plot(fig, key="yc")
    with right:
        section("Curve spreads", "Constant-maturity Treasury yields, latest common date")
        inv = get_yield_curve_inversions(fk)
        rows = [[_esc(i["label"]), f"{i['long_rate']:.2f}%", f"{i['short_rate']:.2f}%",
                 signed(i["spread"] * 100, "{:+.0f}", " bp", True),
                 f'<span style="color:{DOWN if i["inverted"] else TEXT_DIM}">{i["status"].title()}</span>']
                for i in inv]
        table(["Spread", "Long", "Short", "Spread", "Status"], rows, empty_text="Spread data unavailable.")
        if inv:
            st.caption(f"As of {inv[0]['as_of']}")
    fig = yield_history_chart(fk)
    if fig:
        plot(fig, key="yhist")
    divider()
    left, right = st.columns(2, gap="large")
    with left:
        section("Global 10-year yields", "US daily; others OECD monthly averages via FRED")
        sov = get_sovereign_10y_yields(fk)
        rows = [[f'<span class="dim" style="margin-right:8px">{s["flag"]}</span>{_esc(s["country"])}', f"{s['yield_pct']:.2f}%",
                 signed(s["change"] * 100, "{:+.0f}", " bp"), f'<span class="dim">{s["as_of"]}</span>'] for s in sov]
        table(["Country", "10Y yield", "Change", "As of"], rows, empty_text="No sovereign data.")
    with right:
        section("Central bank policy rates", "Change over the last 6 months")
        cb = get_central_bank_rates(fk)
        rows = [[_esc(c["name"]), f"{c['rate']:.2f}%", signed(c["change"] * 100, "{:+.0f}", " bp"),
                 f'<span style="color:{UP if c["stance"] == "EASING" else DOWN if c["stance"] == "TIGHTENING" else TEXT_DIM}">'
                 f'{c["stance"].title()}</span>',
                 f'<span class="dim">{c["as_of"]}{" · stale" if c["stale"] else ""}</span>'] for c in cb]
        table(["Central bank", "Rate", "6M change", "Stance", "As of"], rows, empty_text="Policy-rate data unavailable.")


def _liquidity(fk):
    section("Fed net liquidity", "Fed balance sheet (WALCL) − Treasury General Account − overnight reverse repo")
    nl = get_net_liquidity(fk)
    if nl is None or nl.empty:
        empty("Net liquidity unavailable.")
    else:
        last, prev = nl.iloc[-1], nl.iloc[-2]
        year = nl[nl["Date"] <= last["Date"] - pd.Timedelta(days=365)]
        chg_y = last["Net_Liquidity_T"] - year["Net_Liquidity_T"].iloc[-1] if not year.empty else None
        cards([
            ("Net liquidity", f"${last['Net_Liquidity_T']:.2f}T",
             f"{(last['Net_Liquidity_T'] - prev['Net_Liquidity_T']) * 1000:+.0f}B w/w", signed_color(last["Net_Liquidity_T"] - prev["Net_Liquidity_T"])),
            ("Fed assets", f"${last['WALCL'] / 1e6:.2f}T"),
            ("Treasury account (TGA)", f"${last['TGA'] / 1e6:.2f}T"),
            ("Reverse repo", f"${last['RRP'] / 1e6:.2f}T"),
            ("1-year change", f"{chg_y * 1000:+,.0f}B" if chg_y is not None else "—", "", TEXT_DIM, signed_color(chg_y or 0)),
        ], 150)
        fig = dark_fig(280, title=dict(text=f"Net liquidity ($T) · week of {last['Date']:%b %d, %Y}"))
        fig.add_trace(go.Scatter(x=nl["Date"], y=nl["Net_Liquidity_T"], mode="lines", line=dict(color=SERIES[0], width=2),
                                 fill="tozeroy", fillcolor="rgba(255,255,255,0.05)",
                                 hovertemplate="%{x|%b %d %Y}: $%{y:.2f}T<extra></extra>"))
        y = nl["Net_Liquidity_T"]
        fig.update_layout(yaxis=dict(tickprefix="$", ticksuffix="T", range=[y.min() * 0.97, y.max() * 1.02]))
        plot(fig, key="netliq")
    divider()
    left, right = st.columns([1, 1], gap="large")
    with left:
        section("Implied volatility", "CBOE vol indices · 6-month percentile rank")
        vol = get_cross_asset_volatility()
        rows = [[_esc(v["label"]), f"{v['current']:.2f}", signed(v["change_pct"], "{:+.1f}", "%"),
                 bar_html(v["percentile"], DOWN if v["percentile"] >= 75 else UP if v["percentile"] < 25 else FLAT),
                 f"{v['percentile']:.0f}"] for v in (vol or [])]
        table(["Index", "Level", "Day", "6M rank", ""], rows, align="lrrlr", empty_text="Vol data unavailable.")
    with right:
        corr = get_macro_correlation_matrix()
        section("Cross-asset correlation", f"Daily moves, last {corr['lookback_days']} sessions" if corr else "")
        if corr:
            method = st.radio("Method", ["Pearson", "Spearman"], horizontal=True, key="corr_m", label_visibility="collapsed")
            m = corr["pearson" if method == "Pearson" else "spearman"]
            fig = go.Figure(go.Heatmap(z=m.values, x=list(m.columns), y=list(m.index), zmin=-1, zmax=1,
                                       colorscale=[[0, "#F2555A"], [0.5, "#111111"], [1, "#3FCF8E"]],
                                       text=[[f"{v:.2f}" for v in row] for row in m.values], texttemplate="%{text}",
                                       textfont=dict(size=10, color=TEXT), showscale=False,
                                       hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>"))
            fig.update_layout(**chart_layout(height=360, hovermode="closest", margin=dict(l=8, r=8, t=8, b=8)))
            fig.update_layout(yaxis=dict(autorange="reversed", side="left", showgrid=False), xaxis=dict(showgrid=False))
            plot(fig, key="corr")
        else:
            empty("Correlation data unavailable.")
    divider()
    section("Speculative positioning (CFTC COT)", "Non-commercial net contracts · weekly, as of Tuesday")
    cot = get_cot_positioning()
    rows = [[_esc(c["name"]), f"{c['net_noncomm']:+,}", signed(c["net_change"], "{:+,.0f}"),
             f"{c['pct_oi']:+.1f}%" if c["pct_oi"] is not None else "—",
             f'<span style="color:{signed_color(c["net_noncomm"])}">{c["signal"].title()}</span>',
             f'<span class="dim">{c["date"]}</span>'] for c in (cot or [])]
    table(["Contract", "Net position", "Week change", "% of OI", "Bias", "Report"], rows, empty_text="CFTC data unavailable.")


def render():
    fk = key("fred_key")
    if not fk:
        note('Most macro panels use FRED. Add a free key (<a href="https://fred.stlouisfed.org/docs/api/api_key.html" '
             'target="_blank" rel="noopener">fred.stlouisfed.org</a>) as FRED_API_KEY in secrets or in the sidebar. '
             'Keyless panels are shown below.', "warn", html=True)
    sub = st.segmented_control("Section", SUBPAGES, default="Overview", key="mac_sub",
                               label_visibility="collapsed") or "Overview"
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if sub == "Overview":
        if fk:
            _overview(fk)
        else:
            section("Economic calendar", "Estimated schedule")
            _calendar(None)
    elif sub == "Rates":
        _rates(fk)
    else:
        if fk:
            _liquidity(fk)
        else:
            _liquidity_keyless()


def _liquidity_keyless():
    vol = get_cross_asset_volatility()
    section("Implied volatility", "CBOE vol indices · 6-month percentile rank")
    rows = [[_esc(v["label"]), f"{v['current']:.2f}", signed(v["change_pct"], "{:+.1f}", "%"), f"{v['percentile']:.0f}"]
            for v in (vol or [])]
    table(["Index", "Level", "Day", "6M rank"], rows, empty_text="Vol data unavailable.")
    section("Speculative positioning (CFTC COT)")
    cot = get_cot_positioning()
    rows = [[_esc(c["name"]), f"{c['net_noncomm']:+,}", signed(c["net_change"], "{:+,.0f}"), c["date"]] for c in (cot or [])]
    table(["Contract", "Net position", "Week change", "Report"], rows, empty_text="CFTC data unavailable.")
