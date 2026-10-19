"""Markets: overview, single-ticker deep dive, sector rotation, volatility.

Sub-sections are lazy (segmented control) so only the visible one fetches data.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import streamlit as st

from sentinel.core.formatting import _esc, fmt_p, fmt_vol
from sentinel.data.cross_asset import get_sector_rrg, stat_arb_screener
from sentinel.data.market import get_futures, get_global_indices, get_vix_full, sector_etfs, top_movers, yahoo_quote
from sentinel.data.news import finnhub_news, is_market_relevant
from sentinel.data.options import get_gamma_squeeze_scanner, get_iv_skew, get_iv_term_structure, get_rv_iv_spread
from sentinel.pages.ticker import render_ticker
from sentinel.state import key
from sentinel.ui.components import (
    cards, divider, empty, note, render_news_card, render_stat_arb_cards, section, signed, table, tkr,
)
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT, TEXT_DIM, UP, signed_color
from sentinel.ui.theme import dark_fig, go, plot

SUBPAGES = ["Overview", "Ticker", "Rotation", "Volatility"]


# ── Overview ────────────────────────────────────────────────────────────────
def _global_indices():
    section("Global equity indices", "Last close · day change · annualised realised volatility")
    df = get_global_indices()
    if df.empty:
        empty("Index data unavailable.")
        return
    rows, classes = [], []
    for region in ("Americas", "EMEA", "APAC"):
        sub = df[df["Region"] == region]
        if sub.empty:
            continue
        rows.append([region]); classes.append("sec")
        for _, r in sub.iterrows():
            v10, v30 = r["10D Vol"], r["30D Vol"]
            rows.append([
                f'<span class="dim" style="font-size:11px;margin-right:8px">{_esc(r["Flag"])}</span>{_esc(r["Index"])}',
                f'{r["Value"]:,.2f}', signed(r["Change"], "{:+,.2f}"), signed(r["% Chg"], "{:+.2f}", "%", True),
                f"{v10:.1f}%" if v10 is not None and v10 == v10 else "—",
                f"{v30:.1f}%" if v30 is not None and v30 == v30 else "—",
                f'<span class="dim">{_esc(r["AsOf"])}</span>',
            ])
            classes.append("")
    table(["Index", "Last", "Change", "Change %", "10D vol", "30D vol", "As of"], rows, row_classes=classes)


@st.fragment(run_every="60s")
def _futures():
    section("Futures", "Front-month continuous contracts · refreshes every 60 s")
    rows = [[tkr(f["ticker"]), _esc(f["name"]), fmt_p(f["price"], f["ticker"]),
             signed(f["change"], "{:+,.2f}"), signed(f["pct"], "{:+.2f}", "%", True)] for f in get_futures()]
    table(["Contract", "Name", "Last", "Change", "Change %"], rows, align="llrrr",
          empty_text="Futures data unavailable.")


def _sectors():
    section("Sector performance", "SPDR sector ETFs · day change")
    df = sector_etfs()
    if df.empty:
        empty("Sector data unavailable.")
        return
    df = df.sort_values("Pct")
    fig = dark_fig(max(300, 28 * len(df)), hovermode="closest")
    fig.add_trace(go.Bar(x=df["Pct"], y=[f"{s} · {e}" for s, e in zip(df["Sector"], df["ETF"])], orientation="h",
                         marker_color=[UP if v >= 0 else DOWN for v in df["Pct"]], marker_line_width=0,
                         text=[f"{v:+.2f}%" for v in df["Pct"]], textposition="outside",
                         textfont=dict(size=10, color=TEXT_DIM), hovertemplate="%{y}: %{x:+.2f}%<extra></extra>"))
    fig.update_layout(xaxis=dict(ticksuffix="%"), yaxis=dict(side="left"), margin=dict(l=8, r=40, t=16, b=8))
    plot(fig, key="sector_bar")


def _movers():
    section("Top movers", "~120 large caps · day change vs prior close")
    gainers, losers = top_movers()
    c1, c2 = st.columns(2)
    for col, data, title in ((c1, gainers, "Gainers"), (c2, losers, "Losers")):
        with col:
            rows = [[tkr(q["ticker"]), fmt_p(q["price"]), signed(q["pct"], "{:+.2f}", "%", True),
                     signed(q["change"], "{:+,.2f}"), fmt_vol(q["volume"])] for q in data]
            table([title, "Last", "Change %", "Change", "Volume"], rows, empty_text=f"No {title.lower()} today.")


def _news():
    fk = key("finnhub_key")
    if not fk:
        return
    divider()
    section("Market news", "Finnhub")
    shown = 0
    for art in finnhub_news(fk):
        title, src = art.get("headline", ""), art.get("source", "")
        if not is_market_relevant(title, src):
            continue
        ts = art.get("datetime", 0)
        d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
        st.markdown(render_news_card(title, art.get("url"), src, d), unsafe_allow_html=True)
        shown += 1
        if shown >= 8:
            break


def _overview():
    _global_indices()
    divider()
    left, right = st.columns([1, 1], gap="large")
    with left:
        _futures()
    with right:
        _sectors()
    divider()
    _movers()
    _news()


# ── Rotation ────────────────────────────────────────────────────────────────
def _rotation():
    section("Relative rotation graph", "Sector ETFs vs SPY · RS-ratio (x) vs RS-momentum (y), 100 = in line with SPY")
    rrg = get_sector_rrg()
    if not rrg:
        empty("RRG data unavailable.")
    else:
        quad_color = {"LEADING": UP, "WEAKENING": SERIES[1], "LAGGING": DOWN, "IMPROVING": SERIES[2]}
        xs, ys = [s["rs_ratio"] for s in rrg], [s["rs_momentum"] for s in rrg]
        xp = max(max(abs(x - 100) for x in xs) * 1.3, 1.0)
        yp = max(max(abs(y - 100) for y in ys) * 1.3, 1.0)
        fig = dark_fig(520, hovermode="closest")
        for x0, y0, x1, y1, lbl, ax, ay in ((100, 100, 100 + xp, 100 + yp, "LEADING", 1, 1),
                                            (100, 100 - yp, 100 + xp, 100, "WEAKENING", 1, -1),
                                            (100 - xp, 100 - yp, 100, 100, "LAGGING", -1, -1),
                                            (100 - xp, 100, 100, 100 + yp, "IMPROVING", -1, 1)):
            fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, line_width=0, layer="below",
                          fillcolor="rgba(255,255,255,0.025)" if lbl in ("LEADING", "LAGGING") else "rgba(0,0,0,0)")
            fig.add_annotation(x=100 + ax * xp * 0.85, y=100 + ay * yp * 0.9, text=lbl, showarrow=False,
                               font=dict(size=10, color=quad_color[lbl]))
        fig.add_hline(y=100, line=dict(color="#333", width=1))
        fig.add_vline(x=100, line=dict(color="#333", width=1))
        for s in rrg:
            c = quad_color.get(s["quadrant"], FLAT)
            if len(s.get("trail_ratio", [])) >= 2:
                fig.add_trace(go.Scatter(x=s["trail_ratio"], y=s["trail_momentum"], mode="lines",
                                         line=dict(color=c, width=1), opacity=0.4, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=[s["rs_ratio"]], y=[s["rs_momentum"]], mode="markers+text", text=[s["etf"]],
                                     textposition="top center", textfont=dict(size=10, color=TEXT),
                                     marker=dict(size=11, color=c, line=dict(width=1, color="#000")),
                                     hovertemplate=f"{s['sector']} ({s['etf']})<br>RS-ratio %{{x:.2f}}<br>"
                                                   f"RS-momentum %{{y:.2f}}<br>{s['quadrant']}<extra></extra>"))
        fig.update_layout(xaxis=dict(title="RS-ratio", range=[100 - xp, 100 + xp]),
                          yaxis=dict(title="RS-momentum", range=[100 - yp, 100 + yp], side="left"),
                          margin=dict(l=8, r=16, t=16, b=8))
        plot(fig, key="rrg")
        rows = [[_esc(s["sector"]), tkr(s["etf"]), f'{s["rs_ratio"]:.2f}', f'{s["rs_momentum"]:.2f}',
                 f'<span style="color:{quad_color.get(s["quadrant"], FLAT)};font-weight:600">{s["quadrant"].title()}</span>']
                for s in sorted(rrg, key=lambda s: -s["rs_ratio"])]
        table(["Sector", "ETF", "RS-ratio", "RS-momentum", "Quadrant"], rows)
    divider()
    section("Statistical arbitrage", "Engle-Granger cointegration on ~1 year of daily closes · z-score of the spread")
    arb = stat_arb_screener()
    st.markdown(render_stat_arb_cards(arb), unsafe_allow_html=True)


# ── Volatility ──────────────────────────────────────────────────────────────
def _vol_surface():
    spy, vix = yahoo_quote("SPY"), get_vix_full()[0]
    if not (spy and vix):
        return
    section("Risk-neutral price distribution", f"SPY lognormal density using VIX {vix:.1f} as a flat volatility "
                                               "(no skew) · darker = less likely")
    s0, sigma = spy["price"], vix / 100
    days = np.linspace(2, 90, 30)
    k = s0 * np.linspace(0.85, 1.15, 40)
    K, D = np.meshgrid(k, days)
    T = D / 365
    d2 = (np.log(s0 / K) - 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    pdf = np.exp(-0.5 * d2 ** 2) / (K * sigma * np.sqrt(2 * np.pi * T))
    pdf = pdf / pdf.max(axis=1, keepdims=True)  # normalise each expiry so all horizons are visible
    fig = go.Figure(go.Heatmap(z=pdf, x=k, y=days, colorscale=[[0, "#000000"], [1, "#FFFFFF"]], showscale=False,
                               hovertemplate="Strike %{x:.0f}<br>%{y:.0f} days<br>Relative density %{z:.2f}<extra></extra>"))
    fig.add_vline(x=s0, line=dict(color=UP, width=1, dash="dot"))
    from sentinel.ui.theme import chart_layout
    fig.update_layout(**chart_layout(height=320, hovermode="closest", margin=dict(l=8, r=48, t=16, b=8)))
    fig.update_layout(xaxis=dict(title="Strike", tickprefix="$"), yaxis=dict(title="Days to expiry", side="left"))
    plot(fig, key="rnd_heat")


def _volatility():
    c1, _ = st.columns([1, 3])
    with c1:
        t = st.text_input("Underlying", value=st.session_state.master_ticker or "SPY", key="iv_ts_tkr").upper().strip() or "SPY"
    term, skew, rv = get_iv_term_structure(t), get_iv_skew(t), get_rv_iv_spread(t)
    if rv:
        cards([
            ("Realised vol (20D)", f"{rv['rv20']:.1f}%"),
            (f"ATM implied ({rv['dte']}D)", f"{rv['front_iv']:.1f}%"),
            ("Realised − implied", f"{rv['spread']:+.1f} pts", "positive = options cheap vs realised",
             TEXT_DIM, signed_color(rv["spread"])),
            ("Read", rv["signal"].title(), "", TEXT_DIM, UP if rv["signal"] == "BUY VOL" else DOWN if rv["signal"] == "SELL VOL" else TEXT),
        ])
    left, right = st.columns(2)
    with left:
        section("IV term structure", "ATM implied volatility by expiry")
        if term:
            fig = dark_fig(300, hovermode="x unified")
            fig.add_trace(go.Scatter(x=[d["dte"] for d in term], y=[d["atm_iv"] for d in term], mode="lines+markers",
                                     line=dict(color=SERIES[0], width=2), marker=dict(size=6),
                                     customdata=[d["expiry"] for d in term],
                                     hovertemplate="%{customdata} · %{x}d<br>ATM IV %{y:.1f}%<extra></extra>"))
            fig.update_layout(xaxis=dict(title="Days to expiry"), yaxis=dict(ticksuffix="%"))
            plot(fig, key=f"ivts_{t}")
        else:
            empty("No listed options data for this symbol.")
    with right:
        section("25-delta skew", "Put IV − call IV at 25Δ; positive = downside protection is bid")
        if skew:
            fig = dark_fig(300, showlegend=True, hovermode="x unified")
            dtes = [d["dte"] for d in skew]
            fig.add_trace(go.Scatter(x=dtes, y=[d["iv_25p"] for d in skew], name="25Δ put", line=dict(color=DOWN, width=1.5)))
            fig.add_trace(go.Scatter(x=dtes, y=[d["iv_atm"] for d in skew], name="ATM", line=dict(color=SERIES[0], width=2)))
            fig.add_trace(go.Scatter(x=dtes, y=[d["iv_25c"] for d in skew], name="25Δ call", line=dict(color=UP, width=1.5)))
            fig.update_layout(xaxis=dict(title="Days to expiry"), yaxis=dict(ticksuffix="%"))
            plot(fig, key=f"skew_{t}")
        else:
            empty("Skew unavailable.")
    divider()
    _vol_surface()
    divider()
    section("Gamma-squeeze scanner", "High short interest + volume spike vs 20-day average (retail-heavy universe)")
    sq = get_gamma_squeeze_scanner()
    rows = [[tkr(s["ticker"]), f'${s["price"]:,.2f}', f'{s["short_pct"]:.1f}%', f'{s["short_ratio"]:.1f}',
             f'{s["vol_ratio"]:.1f}×', f'<b>{s["squeeze_score"]:.0f}</b>',
             _esc(s["signal"].replace("🔴 ", "").replace("🟡 ", "").replace("🟢 ", "").title())] for s in (sq or [])[:12]]
    table(["Ticker", "Last", "Short % float", "Days to cover", "Volume ×", "Score", "Signal"], rows,
          empty_text="No squeeze candidates right now.")


def render():
    sub = st.segmented_control("Section", SUBPAGES, default="Overview", key="mk_sub",
                               label_visibility="collapsed") or "Overview"
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if sub == "Overview":
        _overview()
    elif sub == "Ticker":
        with st.form("ticker_lookup", border=False):
            c1, c2 = st.columns([3, 1])
            t = c1.text_input("Ticker", value=st.session_state.master_ticker, placeholder="NVDA, AAPL, SPY, BTC-USD…",
                              label_visibility="collapsed")
            if c2.form_submit_button("Look up", width="stretch"):
                st.session_state.master_ticker = t.upper().strip()[:16]
        if st.session_state.master_ticker:
            render_ticker(st.session_state.master_ticker)
        else:
            note("Enter a symbol to load quote, chart, fundamentals, earnings, insiders and short interest.")
    elif sub == "Rotation":
        _rotation()
    else:
        _volatility()
