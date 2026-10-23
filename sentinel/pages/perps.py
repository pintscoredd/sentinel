"""Hyperliquid perpetuals: market screener, funding, order book, candles."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sentinel.core.formatting import _esc, fmt_pct, fmt_usd
from sentinel.data.hyperliquid import (
    hl_cross_venue_funding, hl_oi_trend,
    CANDLE_INTERVALS, hl_candles, hl_funding_history, hl_markets, hl_order_book,
    hl_perp_dexs, hl_recent_trades, hl_summary,
)
from sentinel.ui.charts import candlestick_chart
from sentinel.ui.components import cards, colored, divider, empty, note, section, signed, table, tkr
from sentinel.ui.palette import DOWN, FLAT, SERIES, TEXT_DIM, UP, signed_color
from sentinel.ui.theme import dark_fig, go, plot

_SORTS = {
    "24h volume": ("volume_24h_usd", False),
    "Open interest": ("oi_usd", False),
    "24h change ↑": ("chg_24h_pct", False),
    "24h change ↓": ("chg_24h_pct", True),
    "Funding APR ↑": ("funding_apr_pct", False),
    "Funding APR ↓": ("funding_apr_pct", True),
}


def _px(v):
    if v is None:
        return "—"
    v = float(v)
    if v >= 1000:
        return f"{v:,.1f}"
    if v >= 1:
        return f"{v:,.3f}".rstrip("0").rstrip(".") if v < 10 else f"{v:,.2f}"
    return f"{v:.6g}"


def render():
    section("Hyperliquid perpetuals", "Live public data from api.hyperliquid.xyz · funding is paid hourly · "
                                     "APR = hourly rate × 8,760 · OI converted to USD at mark.")

    dexs = hl_perp_dexs()
    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    with c1:
        dex = st.selectbox("Venue", dexs, format_func=lambda d: "Hyperliquid (main)" if d == "" else f"HIP-3 · {d}",
                           key="hl_dex")
    with c2:
        sort_by = st.selectbox("Sort by", list(_SORTS), key="hl_sort")
    with c3:
        query = st.text_input("Filter", placeholder="BTC, ETH, SOL…", key="hl_q").strip().upper()

    @st.fragment(run_every="20s")
    def _overview():
        df = hl_markets(dex)
        if df.empty:
            note("Hyperliquid API unavailable right now — retrying automatically.", "warn")
            return
        s = hl_summary(df)
        cards([
            ("Markets", f"{s['markets']}", f"{s['advancers']} up · {s['decliners']} down"),
            ("Open interest", fmt_usd(s["oi_usd"])),
            ("24h volume", fmt_usd(s["volume_24h_usd"])),
            ("OI-weighted funding", fmt_pct(s["oi_weighted_funding_apr"]) + " APR" if s["oi_weighted_funding_apr"] is not None else "—",
             f"{s['positive_funding_share']:.0f}% of markets longs pay", TEXT_DIM,
             signed_color(s["oi_weighted_funding_apr"] or 0)),
        ])
        view = df
        if query:
            view = view[view["symbol"].str.contains(query, regex=False, na=False)]
        col, asc = _SORTS[sort_by]
        view = view.sort_values(col, ascending=asc, na_position="last").head(60)
        rows = [[
            tkr(r.symbol), _px(r.mark), signed(r.chg_24h_pct, "{:+.2f}", "%"),
            fmt_usd(r.volume_24h_usd), fmt_usd(r.oi_usd),
            signed(r.funding_1h_pct, "{:+.4f}", "%"), signed(r.funding_apr_pct, "{:+.1f}", "%"),
            signed(r.basis_pct, "{:+.3f}", "%"), f"{r.max_leverage}×",
        ] for r in view.itertuples()]
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        table(["Market", "Mark", "24h", "24h volume", "Open interest", "Funding 1h", "Funding APR",
               "Mark vs oracle", "Max lev."], rows, max_height=520, empty_text="No markets match the filter.")

    _overview()

    df = hl_markets(dex)
    if df.empty:
        return

    if dex == "":
        divider()
        _crowding(df)

    divider()
    section("Funding extremes", "Positive funding: longs pay shorts. Annualised from the current hourly rate.")
    liquid = df[df["oi_usd"] >= max(250_000, df["oi_usd"].quantile(0.25))]
    top = liquid.nlargest(8, "funding_apr_pct")
    bot = liquid.nsmallest(8, "funding_apr_pct")
    both = pd.concat([top, bot]).drop_duplicates("coin").sort_values("funding_apr_pct")
    fig = dark_fig(max(260, 26 * len(both)), title=dict(text="Funding APR · liquid markets (OI ≥ $250K)"),
                   hovermode="closest")
    fig.add_trace(go.Bar(
        x=both["funding_apr_pct"], y=both["symbol"], orientation="h",
        marker_color=[UP if v > 0 else DOWN for v in both["funding_apr_pct"]], marker_line_width=0,
        text=[f"{v:+.1f}%" for v in both["funding_apr_pct"]], textposition="outside",
        textfont=dict(size=10, color=TEXT_DIM), hovertemplate="%{y}: %{x:+.2f}% APR<extra></extra>",
    ))
    fig.update_layout(xaxis=dict(ticksuffix="%"), yaxis=dict(side="left"), margin=dict(l=8, r=40, t=36, b=8))
    plot(fig, key="hl_funding_bar")

    divider()
    section("Market detail")
    coins = df["coin"].tolist()
    default = coins.index("BTC") if "BTC" in coins else 0
    d1, d2, d3 = st.columns([1.4, 1, 1])
    with d1:
        coin = st.selectbox("Market", coins, index=default, key=f"hl_coin_{dex}",
                            format_func=lambda c: c.split(":", 1)[-1])
    with d2:
        interval = st.selectbox("Candle interval", list(CANDLE_INTERVALS), index=2, key="hl_iv")
    with d3:
        bars = st.select_slider("Bars", options=[60, 120, 200, 300, 500], value=200, key="hl_bars")

    @st.fragment(run_every="15s")
    def _detail():
        row = df[df["coin"] == coin]
        live = hl_markets(dex)
        lrow = live[live["coin"] == coin] if not live.empty else row
        r = (lrow if not lrow.empty else row).iloc[0]
        book = hl_order_book(coin)
        cards([
            ("Mark", _px(r["mark"]), fmt_pct(r["chg_24h_pct"]) + " 24h", signed_color(r["chg_24h_pct"])),
            ("Oracle", _px(r["oracle"]), f"basis {r['basis_pct']:+.3f}%" if r["basis_pct"] is not None else ""),
            ("Funding", f"{r['funding_1h_pct']:+.4f}%/h", f"{r['funding_apr_pct']:+.1f}% APR",
             signed_color(r["funding_apr_pct"])),
            ("Open interest", fmt_usd(r["oi_usd"]), f"{r['oi_base']:,.2f} {r['symbol']}"),
            ("24h volume", fmt_usd(r["volume_24h_usd"])),
            ("Spread", f"{book['spread_bps']:.2f} bps" if book else "—",
             f"book imbalance {book['imbalance_pct']:+.0f}%" if book else "",
             signed_color(book.get("imbalance_pct", 0)) if book else TEXT_DIM),
        ], min_width=140)

        candles = hl_candles(coin, interval, bars)
        if candles.empty:
            empty("No candle data for this market.")
        else:
            plot(candlestick_chart(candles, title=f"{coin.split(':', 1)[-1]}-PERP · {interval}", height=440),
                 key=f"hl_candles_{coin}_{interval}")

        left, right = st.columns([3, 2])
        with left:
            fh = hl_funding_history(coin, 7)
            if fh.empty:
                empty("No funding history.")
            else:
                f = dark_fig(260, title=dict(text="Funding APR · last 7 days (hourly)"), hovermode="x unified")
                f.add_trace(go.Bar(x=fh.index, y=fh["funding_apr_pct"],
                                   marker_color=[UP if v >= 0 else DOWN for v in fh["funding_apr_pct"]],
                                   marker_line_width=0, hovertemplate="%{y:+.2f}% APR<extra></extra>"))
                avg = fh["funding_apr_pct"].mean()
                f.add_hline(y=avg, line=dict(color=SERIES[1], dash="dot", width=1),
                            annotation_text=f"7d avg {avg:+.1f}%", annotation_font=dict(size=10, color=SERIES[1]))
                f.update_layout(yaxis=dict(ticksuffix="%"))
                plot(f, key=f"hl_fh_{coin}")
        with right:
            if book:
                bids, asks = book["bids"], book["asks"]
                f = dark_fig(260, title=dict(text="Order book depth (top 20 levels, USD)"), hovermode="x unified")
                f.add_trace(go.Scatter(x=bids["px"], y=bids["cum_usd"], fill="tozeroy", mode="lines", name="Bids",
                                       line=dict(color=UP, width=1.5, shape="hv"), fillcolor="rgba(63,207,142,0.15)"))
                f.add_trace(go.Scatter(x=asks["px"], y=asks["cum_usd"], fill="tozeroy", mode="lines", name="Asks",
                                       line=dict(color=DOWN, width=1.5, shape="hv"), fillcolor="rgba(242,85,90,0.15)"))
                f.update_layout(yaxis=dict(tickprefix="$"))
                plot(f, key=f"hl_book_{coin}")
            else:
                empty("Order book unavailable.")

        b1, b2 = st.columns(2)
        with b1:
            if book:
                rows = []
                for (_, b), (_, a) in zip(book["bids"].head(10).iterrows(), book["asks"].head(10).iterrows()):
                    rows.append([colored(_px(b["px"]), UP), f"{b['sz']:,.4g}", f"{a['sz']:,.4g}", colored(_px(a["px"]), DOWN)])
                table(["Bid", "Size", "Size", "Ask"], rows, align="rrrr")
        with b2:
            trades = hl_recent_trades(coin)
            if trades.empty:
                empty("No recent trades.")
            else:
                rows = [[t.time.strftime("%H:%M:%S"),
                         colored(t.side, UP if t.side == "BUY" else DOWN if t.side == "SELL" else FLAT, True),
                         _px(t.px), f"{t.sz:,.4g}", fmt_usd(t.usd)] for t in trades.head(10).itertuples()]
                table(["Time (UTC)", "Side", "Price", "Size", "Notional"], rows)
        st.caption(f"{_esc(coin)} · refreshes every 15 s · data © Hyperliquid public API")

    _detail()


_QUADS = [  # (price up?, funding positive?) → label, colour, meaning
    ((True, True), "Longs chasing", UP, "price up and longs paying: trend with crowded longs"),
    ((False, True), "Longs trapped", DOWN, "price down while longs still pay: long-squeeze risk"),
    ((True, False), "Shorts squeezed", "#8FB8FF", "price up while shorts pay: short-squeeze in progress"),
    ((False, False), "Shorts pressing", FLAT, "price down with shorts paying: bearish consensus"),
]


def _crowding(df):
    section("Crowd positioning", "Who is paying to hold the position. Funding annualised · liquid markets (OI ≥ $5M)")
    liq = df[df["oi_usd"] >= 5e6].copy()
    if liq.empty:
        empty("Not enough liquid markets.")
        return
    oi_chg, mins = hl_oi_trend(df)
    if oi_chg is not None:
        liq["oi_chg"] = liq["coin"].map(oi_chg)
    # Hyperliquid funding = premium + a fixed interest component (0.00125%/h ≈ 10.95% APR), so markets
    # with no premium all sit at the baseline. Crowding is measured relative to it; premium breaks ties.
    base = 0.00125 * 24 * 365
    liq["excess"] = liq["funding_apr_pct"] - base
    ranked = liq.sort_values(["excess", "premium_pct"], ascending=False)
    longs = ranked[ranked["excess"] > 0.5].head(3)
    shorts = ranked[ranked["excess"] < -0.5].iloc[::-1].head(3)

    def head(d):
        if d.empty:
            return "None"
        r = d.iloc[0]
        return f"{r.symbol} {r.funding_apr_pct:+.0f}%"

    def rest(d, what):
        if d.empty:
            return f"no market far from the {base:.1f}% baseline"
        more = ", ".join(f"{r.symbol} {r.funding_apr_pct:+.0f}%" for r in d.iloc[1:].itertuples())
        return (f"then {more} · " if more else "") + what

    above, below = int((liq["excess"] > 0.5).sum()), int((liq["excess"] < -0.5).sum())
    cards([
        ("Most crowded long", head(longs), rest(longs, "APR longs pay"), TEXT_DIM, UP),
        ("Most crowded short", head(shorts), rest(shorts, "APR (negative = shorts pay)"), TEXT_DIM, DOWN),
        ("Crowding balance", f"{above} long · {below} short",
         f"of {len(liq)} liquid markets away from the {base:.2f}% baseline"),
        ("OI trend", f"{mins} min window" if oi_chg is not None else "warming up",
         "change in open interest tracked by this app" if oi_chg is not None
         else "Hyperliquid has no OI history; the app records it (~10 min)"),
    ], 200)

    left, right = st.columns([3, 2], gap="large")
    with left:
        fig = dark_fig(440, hovermode="closest", showlegend=True,
                       title=dict(text="Regime map · 24h price change × funding (bubble = open interest)"))
        for (up, pos), name, color, meaning in _QUADS:
            q = liq[((liq["chg_24h_pct"] >= 0) == up) & ((liq["funding_apr_pct"] >= 0) == pos)]
            if q.empty:
                continue
            size = (q["oi_usd"] / liq["oi_usd"].max()) ** 0.5 * 46 + 6
            label = [s if o >= liq["oi_usd"].quantile(0.8) else "" for s, o in zip(q["symbol"], q["oi_usd"])]
            fig.add_trace(go.Scatter(
                x=q["chg_24h_pct"], y=q["funding_apr_pct"], mode="markers+text", name=name, text=label,
                textposition="top center", textfont=dict(size=10, color="#D4D4D4"),
                marker=dict(size=size, color=color, opacity=0.55, line=dict(width=1, color="#000")),
                customdata=list(zip(q["symbol"], q["oi_usd"] / 1e6)),
                hovertemplate="<b>%{customdata[0]}</b><br>24h %{x:+.2f}%<br>Funding %{y:+.1f}% APR"
                              "<br>OI $%{customdata[1]:,.0f}M<br>" + meaning + "<extra></extra>"))
        fig.add_hline(y=0, line=dict(color="#333", width=1))
        fig.add_vline(x=0, line=dict(color="#333", width=1))
        fig.update_layout(xaxis=dict(ticksuffix="%", title=dict(text="24h price change", font=dict(size=10))),
                          yaxis=dict(ticksuffix="%", title=dict(text="Funding APR", font=dict(size=10))),
                          legend=dict(orientation="h", y=-0.15))
        plot(fig, key="hl_regime")
    with right:
        xv = hl_cross_venue_funding()
        top = liq.nlargest(18, "oi_usd")[["coin", "symbol", "oi_usd"] + (["oi_chg"] if "oi_chg" in liq else [])]
        m = top.merge(xv, on="coin", how="left")
        def apr(v):
            return '<span class="dim">—</span>' if v != v or v is None else signed(v, "{:+.1f}", "%")
        rows = [[tkr(r.symbol), apr(r.Hyperliquid), apr(r.Binance), apr(r.Bybit), apr(r.spread_vs_cex)]
                + ([signed(r.oi_chg, "{:+.1f}", "%")] if "oi_chg" in m else []) for r in m.itertuples()]
        section("Funding across venues", "Predicted next funding, % APR · spread = Hyperliquid minus CEX average")
        table(["Coin", "Hyperliquid", "Binance", "Bybit", "Spread"] + ([f"OI {mins}m"] if "oi_chg" in m else []),
              rows, max_height=440)
        st.caption("A positive spread means longs pay more on Hyperliquid than on Binance/Bybit (basis-trade opportunity, "
                   "before fees). Binance/Bybit rates are as published by Hyperliquid.")
