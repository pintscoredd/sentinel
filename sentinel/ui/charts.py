"""Plotly figure builders (all styled by sentinel.ui.theme)."""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from sentinel.config import ETF_TICKERS
from sentinel.core.http import _yf_semaphore, yf
from sentinel.data.macro import fred_series
from sentinel.ui.palette import BORDER_STRONG, DOWN, SERIES, TEXT, TEXT_DIM, TEXT_MUTED, UP
from sentinel.ui.theme import chart_layout, dark_fig, go

logger = logging.getLogger("sentinel.ui")


def candlestick_chart(df, title="", height=420, ma_windows=(20, 50), show_volume=True):
    """OHLC candles + moving averages + volume pane.

    *df*: DatetimeIndex and open/high/low/close[/volume] columns (any case).
    """
    if go is None or df is None or getattr(df, "empty", True):
        return None
    cols = {str(c).lower(): c for c in df.columns}
    if not all(k in cols for k in ("open", "high", "low", "close")):
        return None
    o, h, l, c = (df[cols[k]] for k in ("open", "high", "low", "close"))
    from plotly.subplots import make_subplots

    with_vol = show_volume and "volume" in cols
    fig = make_subplots(rows=2 if with_vol else 1, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.76, 0.24] if with_vol else [1.0])
    fig.add_trace(go.Candlestick(
        x=df.index, open=o, high=h, low=l, close=c, name="Price",
        increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
        decreasing=dict(line=dict(color=DOWN, width=1), fillcolor=DOWN),
        whiskerwidth=0.3,
    ), row=1, col=1)
    for i, w in enumerate(ma_windows):
        if len(c) >= w:
            fig.add_trace(go.Scatter(x=df.index, y=c.rolling(w).mean(), mode="lines", name=f"MA{w}",
                                     line=dict(width=1.2, color=SERIES[min(i + 1, len(SERIES) - 1)])), row=1, col=1)
    if with_vol:
        vol_colors = ["rgba(63,207,142,0.45)" if float(cc) >= float(oo) else "rgba(242,85,90,0.45)" for oo, cc in zip(o, c)]
        fig.add_trace(go.Bar(x=df.index, y=df[cols["volume"]], name="Volume", marker_color=vol_colors,
                             marker_line_width=0, showlegend=False), row=2, col=1)
    layout = chart_layout(height=height, title=dict(text=title), showlegend=True, hovermode="x unified")
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor="#161616", color=TEXT_DIM, showgrid=False, rangeslider_visible=False,
                     linecolor="#1F1F1F")
    fig.update_yaxes(gridcolor="#161616", color=TEXT_DIM, side="right", zeroline=False)
    return fig


def yield_curve_chart(fred_key, height=280):
    """Current Treasury curve with the curve from ~1 month and ~1 year ago."""
    mats = [("1M", "DGS1MO"), ("3M", "DGS3MO"), ("6M", "DGS6MO"), ("1Y", "DGS1"), ("2Y", "DGS2"),
            ("3Y", "DGS3"), ("5Y", "DGS5"), ("7Y", "DGS7"), ("10Y", "DGS10"), ("20Y", "DGS20"), ("30Y", "DGS30")]
    start = (pd.Timestamp.today() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    series = {lbl: fred_series(code, fred_key, start=start) for lbl, code in mats}
    series = {k: v for k, v in series.items() if v is not None and not v.empty}
    if not series:
        return None
    labels = list(series)
    last_date = max(v["date"].iloc[-1] for v in series.values())

    def _curve(at):
        out = []
        for lbl in labels:
            d = series[lbl]
            sub = d[d["date"] <= at]
            out.append(float(sub["value"].iloc[-1]) if not sub.empty else None)
        return out

    fig = dark_fig(height, showlegend=True, hovermode="x unified",
                   title=dict(text=f"US Treasury curve · {last_date:%Y-%m-%d}"))
    for name, at, color, width, dash in (
        ("1Y ago", last_date - pd.Timedelta(days=365), SERIES[4], 1.2, "dot"),
        ("1M ago", last_date - pd.Timedelta(days=30), SERIES[2], 1.4, "dash"),
        ("Latest", last_date, SERIES[0], 2.4, "solid"),
    ):
        fig.add_trace(go.Scatter(x=labels, y=_curve(at), mode="lines+markers", name=name,
                                 line=dict(color=color, width=width, dash=dash), marker=dict(size=5)))
    fig.update_layout(yaxis=dict(ticksuffix="%"))
    return fig


def yield_history_chart(fred_key, height=260):
    """3-year history of the 2Y/5Y/10Y/30Y yields."""
    start = (pd.Timestamp.today() - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
    fig = dark_fig(height, showlegend=True, title=dict(text="Treasury yields · 3 years"))
    added = False
    for i, (lbl, code) in enumerate((("2Y", "DGS2"), ("5Y", "DGS5"), ("10Y", "DGS10"), ("30Y", "DGS30"))):
        df = fred_series(code, fred_key, start=start)
        if df is not None and not df.empty:
            added = True
            fig.add_trace(go.Scatter(x=df["date"], y=df["value"], mode="lines", name=lbl,
                                     line=dict(color=SERIES[i], width=1.6)))
    if not added:
        return None
    fig.update_layout(yaxis=dict(ticksuffix="%"))
    return fig


def cpi_vs_rates_chart(fred_key, height=260):
    """CPI and core PCE year-over-year vs the effective fed funds rate (5 years)."""
    start = (pd.Timestamp.today() - pd.DateOffset(years=6)).strftime("%Y-%m-%d")
    fig = dark_fig(height, showlegend=True, title=dict(text="Inflation (YoY) vs fed funds"))
    added = False
    for i, (lbl, code, yoy) in enumerate((("CPI YoY", "CPIAUCSL", True), ("Core PCE YoY", "PCEPILFE", True),
                                          ("Fed funds", "FEDFUNDS", False))):
        df = fred_series(code, fred_key, start=start)
        if df is None or len(df) < 13:
            continue
        y = df["value"].pct_change(12) * 100 if yoy else df["value"]
        mask = y.notna()
        added = True
        fig.add_trace(go.Scatter(x=df["date"][mask], y=y[mask], mode="lines", name=lbl,
                                 line=dict(color=SERIES[i], width=1.8, dash="solid" if i < 2 else "dash")))
    if not added:
        return None
    fig.add_hline(y=2, line=dict(color=BORDER_STRONG, dash="dot", width=1),
                  annotation_text="2% target", annotation_font=dict(color=TEXT_DIM, size=10))
    fig.update_layout(yaxis=dict(ticksuffix="%"))
    return fig


def render_crypto_etf_chart(df, height=380, is_estimated=True):
    """Stacked daily flow-proxy bars per ETF (grayscale) + cumulative total line."""
    if df is None or df.empty or go is None:
        return None
    fig = dark_fig(height, showlegend=True, hovermode="x unified", barmode="relative",
                   title=dict(text="Spot BTC ETFs · directional dollar-volume proxy ($B)"))
    etfs = [c for c in df.columns if c in ETF_TICKERS]
    order = sorted(etfs, key=lambda t: df[t].abs().sum(), reverse=True)
    for i, t in enumerate(order):
        fig.add_trace(go.Bar(x=df.index, y=df[t], name=t, marker_color=SERIES[min(i, len(SERIES) - 1)],
                             marker_line_width=0, hovertemplate=f"{t}: %{{y:+.2f}}B<extra></extra>"))
    if "Total" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["Total"].cumsum(), name="Cumulative", mode="lines",
                                 yaxis="y2", line=dict(color=UP, width=2),
                                 hovertemplate="Cumulative: %{y:+.2f}B<extra></extra>"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="left", showgrid=False, color=TEXT_DIM,
                                      tickfont=dict(size=10)))
    return fig


@st.cache_data(ttl=60, show_spinner=False)
def _spx_intraday():
    """Today's 5-minute SPX candles (cached so the 30s fragment does not re-download)."""
    if yf is None:
        return pd.DataFrame()
    try:
        with _yf_semaphore:
            df = yf.Ticker("^GSPC").history(period="1d", interval="5m")
        return df.dropna() if df is not None else pd.DataFrame()
    except Exception as e:
        logger.debug("SPX intraday: %s", e)
        return pd.DataFrame()


def render_0dte_gex_chart(gex, gamma_flip, max_pain, spot_spx=None, display_pct=0.02, spx_spy_ratio=1.0):
    """GEX walls (horizontal lines) over today's SPX 5-minute candles.

    *gex* keys, *gamma_flip* and *max_pain* are in the chain's strike space;
    *spx_spy_ratio* converts them to SPX points (1.0 for an SPX chain).
    """
    if not gex or go is None:
        return None
    ratio = float(spx_spy_ratio) if spx_spy_ratio and spx_spy_ratio > 0 else 1.0
    calls = sorted(((k * ratio, v) for k, v in gex.items() if v > 0), key=lambda x: -x[1])[:3]
    puts = sorted(((k * ratio, v) for k, v in gex.items() if v < 0), key=lambda x: x[1])[:3]

    fig = dark_fig(480, title=dict(text="SPX · gamma levels and price"), hovermode="x unified")
    df = _spx_intraday()
    if not df.empty:
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="SPX",
            increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
            decreasing=dict(line=dict(color=DOWN, width=1), fillcolor=DOWN),
        ))

    levels = []  # (y, label, color, dash, width) — only the primary walls carry text labels

    for i, (k, v) in enumerate(calls):
        levels.append((k, f"Call wall {k:,.0f}" if i == 0 else "", UP, "solid" if i == 0 else "dot", 1.6 if i == 0 else 0.8))
    for i, (k, v) in enumerate(puts):
        levels.append((k, f"Put wall {k:,.0f}" if i == 0 else "", DOWN, "solid" if i == 0 else "dot", 1.6 if i == 0 else 0.8))
    if gamma_flip:
        levels.append((gamma_flip * ratio, f"γ flip {gamma_flip * ratio:,.0f}", TEXT, "dash", 1.2))
    if max_pain:
        levels.append((max_pain * ratio, f"Max pain {max_pain * ratio:,.0f}", TEXT_MUTED, "dashdot", 1.0))
    for y, text, color, dash, width in levels:
        fig.add_hline(y=y, line=dict(color=color, dash=dash, width=width))
    # Labels as annotations on the right edge, nudged apart so they never overlap.
    labelled = sorted([(y, t, c) for y, t, c, _, _ in levels if t], key=lambda x: x[0])
    ys = [y for y, _, _ in labelled]
    span = ys + ([float(df["Low"].min()), float(df["High"].max())] if not df.empty else []) + ([spot_spx] if spot_spx else [])
    if not span:
        return fig
    lo, hi = min(span), max(span)
    if spot_spx:
        lo, hi = max(lo, spot_spx * (1 - display_pct)), min(hi, spot_spx * (1 + display_pct))
    pad = max((hi - lo) * 0.08, (spot_spx or hi) * 0.001)
    lo, hi = lo - pad, hi + pad
    min_gap = (hi - lo) * 0.045
    placed = []
    for y, text, color in labelled:
        if not (lo <= y <= hi):
            continue
        ay = max(y, placed[-1] + min_gap) if placed else y
        placed.append(ay)
        fig.add_annotation(x=1, xref="paper", xanchor="right", y=ay, yanchor="bottom", text=text, showarrow=False,
                           font=dict(size=10, color=color), bgcolor="rgba(0,0,0,0.6)")
    fig.update_layout(yaxis=dict(range=[lo, hi], tickformat=",.0f"), xaxis=dict(rangeslider=dict(visible=False)),
                      uirevision="gex")
    return fig


def market_heatmap(df, height=620, clip=3.0):
    """Finviz-style treemap: sector → stock, area = market cap, colour = day change (±*clip*%)."""
    if go is None or df is None or df.empty:
        return None
    d = df.copy()
    sect = d.groupby("sector").apply(lambda g: (g["pct"] * g["mcap"]).sum() / g["mcap"].sum(), include_groups=False)
    ids = [f"s:{s}" for s in sect.index] + [f"t:{t}" for t in d["symbol"]]
    labels = list(sect.index) + list(d["symbol"])
    parents = [""] * len(sect) + [f"s:{s}" for s in d["sector"]]
    values = [0] * len(sect) + list(d["mcap"])
    pct = list(sect.values) + list(d["pct"])
    names = ["sector, cap-weighted"] * len(sect) + list(d["name"].str.slice(0, 40))
    prices = [None] * len(sect) + list(d["price"])
    caps = [d.loc[d["sector"] == s, "mcap"].sum() for s in sect.index] + list(d["mcap"])

    def _cap(v):
        return f"${v / 1e12:.2f}T" if v >= 1e12 else f"${v / 1e9:.0f}B"

    hover = [f"<b>{lb}</b> · {nm}<br>{p:+.2f}%" + (f" · ${pr:,.2f}" if pr else "") + f"<br>Market cap {_cap(c)}"
             for lb, nm, p, pr, c in zip(labels, names, pct, prices, caps)]
    fig = dark_fig(height, margin=dict(l=0, r=0, t=8, b=0), uniformtext=dict(minsize=9, mode="hide"),
                   xaxis=dict(visible=False), yaxis=dict(visible=False))
    fig.add_trace(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="remainder",
        marker=dict(colors=[max(-clip, min(clip, p)) for p in pct], cmin=-clip, cmid=0, cmax=clip,
                    colorscale=[[0, "#B3262B"], [0.35, "#5A1D20"], [0.5, "#1C1C1C"], [0.65, "#1B4D36"], [1, "#2FA36B"]],
                    line=dict(color="#000000", width=1), pad=dict(t=18, l=2, r=2, b=2),
                    colorbar=dict(thickness=8, len=0.5, ticksuffix="%", tickfont=dict(color=TEXT_DIM, size=10),
                                  outlinewidth=0)),
        text=[f"{p:+.2f}%" for p in pct], texttemplate="<b>%{label}</b><br>%{text}", textposition="middle center",
        textfont=dict(color="#FFFFFF", size=12), hovertext=hover, hoverinfo="text",
        pathbar=dict(visible=True, thickness=20, textfont=dict(size=11)), maxdepth=2, root=dict(color="#000000"), tiling=dict(packing="squarify"),
    ))
    return fig
