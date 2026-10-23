"""Options → Exposure: dealer gamma / delta / vanna by strike and expiry (CBOE delayed chains)."""
from __future__ import annotations

import numpy as np
import streamlit as st

from sentinel.core.formatting import _esc
from sentinel.data.exposure import by_strike, exposure_chain, gamma_profile, heatmap, key_levels
from sentinel.ui.components import cards, divider, empty, note, section
from sentinel.ui.palette import BORDER_STRONG, DOWN, FLAT, TEXT, TEXT_DIM, UP
from sentinel.ui.theme import dark_fig, go, plot

_METRICS = {
    "GEX": ("gex", "$ per 1% move", "Dealer gamma: positive = hedging dampens moves, negative = amplifies."),
    "DEX": ("dex", "$ notional delta", "Open-interest delta: where directional exposure sits."),
    "VEX": ("vex", "$ delta per +1 vol pt", "How dealer delta shifts when implied vol moves (vol crush ⇒ hedging flows)."),
}
_HORIZONS = {"Next": 0, "7d": 7, "30d": 30, "90d": 90, "All": None}
_NAMES = {"GEX": "Gamma (GEX)", "DEX": "Delta (DEX)", "VEX": "Vanna (VEX)"}


def _fmt_bn(v):
    if v is None:
        return "—"
    a = abs(v)
    return f"{v:+.2f}B" if a >= 1 else f"{v * 1000:+.0f}M"


def render():
    c1, c2, c3, c4 = st.columns([1.1, 1.5, 2.2, 1.8])
    with c1:
        tk = st.text_input("Underlying", value=st.session_state.get("exp_tk", "SPX"), key="exp_tk_in",
                           help="SPX, NDX, RUT (cash indexes) or any optionable stock/ETF").strip().upper()[:8] or "SPX"
        st.session_state["exp_tk"] = tk
    with c2:
        short = st.segmented_control("Metric", list(_METRICS), default="GEX", key="exp_metric",
                                     help="GEX = gamma, DEX = delta, VEX = vanna exposure") or "GEX"
        label = _NAMES[short]
    with c3:
        horizon = st.segmented_control("Expiries within", list(_HORIZONS), default="30d", key="exp_h") or "30d"
    with c4:
        pct = st.select_slider("Strike range", [0.02, 0.03, 0.05, 0.08, 0.12, 0.2], value=0.05, key="exp_pct",
                               format_func=lambda x: f"±{x:.0%}")
    metric, unit, explain = _METRICS[short]

    with st.spinner(f"Loading {tk} chain from CBOE…"):
        spot, df = exposure_chain(tk)
    if spot is None or df is None or df.empty:
        empty(f"No CBOE options data for {tk}. Check the symbol (cash indexes: SPX, NDX, RUT).")
        return
    max_dte = _HORIZONS[horizon]
    sub = df
    if max_dte == 0:
        sub = df[df["expiration"] == df["expiration"].min()]
    elif max_dte is not None:
        sub = df[df["dte"] <= max_dte]

    lv = key_levels(sub, spot, strike_pct=max(pct, 0.10), max_dte=10_000)
    levels, curve, flip = gamma_profile(sub, spot, span=max(pct, 0.05), max_dte=10_000)
    net = float(sub["gex"].sum() / 1e9)
    regime_pos = net >= 0
    items = [
        (f"{tk} spot (delayed)", f"{spot:,.2f}", f"{len(sub):,} contracts · {sub['expiration'].nunique()} expiries"),
        ("Net dealer gamma", _fmt_bn(net), "per 1% move", TEXT_DIM, UP if regime_pos else DOWN),
        ("Regime", "Long gamma" if regime_pos else "Short gamma",
         "moves tend to be dampened / pinned" if regime_pos else "moves tend to be amplified", TEXT_DIM,
         UP if regime_pos else DOWN),
    ]
    if flip:
        items.append(("Gamma flip", f"{flip:,.0f}", f"{(flip / spot - 1) * 100:+.1f}% vs spot · "
                      + ("spot above ⇒ stabilising" if spot >= flip else "spot below ⇒ unstable"), TEXT_DIM, TEXT))
    if lv.get("call_wall"):
        items.append(("Call wall", f"{lv['call_wall']:,.0f}", f"{(lv['call_wall'] / spot - 1) * 100:+.1f}% · largest call gamma",
                      TEXT_DIM, UP))
    if lv.get("put_wall"):
        items.append(("Put wall", f"{lv['put_wall']:,.0f}", f"{(lv['put_wall'] / spot - 1) * 100:+.1f}% · largest put gamma",
                      TEXT_DIM, DOWN))
    cards(items, 160)

    def _vlines(fig, horizontal=False):
        marks = [("Spot", spot, TEXT, "solid")]
        if flip:
            marks.append(("Flip", flip, FLAT, "dash"))
        if lv.get("call_wall"):
            marks.append(("Call wall", lv["call_wall"], UP, "dot"))
        if lv.get("put_wall"):
            marks.append(("Put wall", lv["put_wall"], DOWN, "dot"))
        # Spot/flip labelled at the top, walls at the bottom, alternating sides so labels never stack.
        pos_v = {"Spot": "top left", "Flip": "top right", "Call wall": "bottom right", "Put wall": "bottom left"}
        for name, x, color, dash in marks:
            kw = dict(line=dict(color=color, width=1, dash=dash), annotation_text=f"{name} {x:,.0f}",
                      annotation_font=dict(size=10, color=color))
            if horizontal:
                fig.add_hline(y=x, annotation_position="right", **kw)
            else:
                fig.add_vline(x=x, annotation_position=pos_v[name], **kw)

    left, right = st.columns([3, 2], gap="large")
    with left:
        section(f"{label} by strike", f"{unit} · calls vs puts · expiries: {horizon}")
        bs = by_strike(sub, spot, metric, pct)
        if bs.empty:
            empty("No open interest in this strike range.")
        else:
            fig = dark_fig(min(820, max(420, 8 * len(bs))), hovermode="y unified", barmode="relative", showlegend=True)
            fig.add_trace(go.Bar(y=bs["strike"], x=bs["call"] / 1e6, orientation="h", name="Calls",
                                 marker_color=UP, marker_line_width=0, opacity=0.85,
                                 hovertemplate="%{x:,.1f}M<extra>Calls</extra>"))
            fig.add_trace(go.Bar(y=bs["strike"], x=bs["put"] / 1e6, orientation="h", name="Puts",
                                 marker_color=DOWN, marker_line_width=0, opacity=0.85,
                                 hovertemplate="%{x:,.1f}M<extra>Puts</extra>"))
            fig.add_trace(go.Scatter(y=bs["strike"], x=bs["net"] / 1e6, mode="markers", name="Net",
                                     marker=dict(color="#FFFFFF", size=5, symbol="diamond"),
                                     hovertemplate="%{x:,.1f}M<extra>Net</extra>"))
            fig.update_layout(xaxis=dict(title=dict(text=f"$M ({unit})", font=dict(size=10)), zeroline=True,
                                         zerolinecolor=BORDER_STRONG),
                              yaxis=dict(title=None, side="left", tickformat=",.0f"),
                              margin=dict(l=8, r=80, t=30, b=8), bargap=0.15)
            _vlines(fig, horizontal=True)
            plot(fig, key="exp_bars")
        st.caption(explain)
    with right:
        section("Gamma profile vs price", "Total dealer gamma if the index moved there (Black-Scholes re-priced)")
        if len(levels):
            fig = dark_fig(420, hovermode="x unified")
            pos = np.where(curve >= 0, curve, np.nan)
            neg = np.where(curve < 0, curve, np.nan)
            fig.add_trace(go.Scatter(x=levels, y=pos, mode="lines", line=dict(color=UP, width=2), fill="tozeroy",
                                     fillcolor="rgba(63,207,142,0.10)", name="Long gamma",
                                     hovertemplate="%{y:+.2f}B<extra></extra>"))
            fig.add_trace(go.Scatter(x=levels, y=neg, mode="lines", line=dict(color=DOWN, width=2), fill="tozeroy",
                                     fillcolor="rgba(242,85,90,0.10)", name="Short gamma",
                                     hovertemplate="%{y:+.2f}B<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=BORDER_STRONG, width=1))
            fig.update_layout(showlegend=False, yaxis=dict(ticksuffix="B", title=None), xaxis=dict(tickformat=",.0f"),
                              margin=dict(l=8, r=8, t=30, b=8))
            _vlines(fig)
            plot(fig, key="exp_profile")
            st.caption("Right of the flip, dealer hedging leans against moves; left of it, hedging chases them.")
        else:
            empty("Not enough data for a profile.")

    divider()
    section(f"{label} heatmap · strike × expiry", f"$M ({unit}) · next 10 expiries · strongest strikes in ±{max(pct, 0.03):.0%}")
    hm = heatmap(df, spot, metric, strike_pct=max(pct, 0.03))
    if hm.empty:
        empty("No data for the heatmap.")
    else:
        z = hm.to_numpy()
        lim = float(np.nanpercentile(np.abs(z), 98)) or 1.0
        fig = dark_fig(max(380, 18 * len(hm)), hovermode="closest")
        fig.add_trace(go.Heatmap(
            z=z, x=list(hm.columns), y=[f"{k:,.0f}" for k in hm.index], zmid=0, zmin=-lim, zmax=lim,
            colorscale=[[0, "#B3262B"], [0.4, "#3A1517"], [0.5, "#111111"], [0.6, "#123826"], [1, "#2FA36B"]],
            text=[[f"{v:,.0f}" if abs(v) >= lim * 0.25 else "" for v in row] for row in z], texttemplate="%{text}",
            textfont=dict(size=9, color="#FFFFFF"), xgap=1, ygap=1,
            hovertemplate="Strike %{y} · %{x}<br>%{z:,.1f}M<extra></extra>",
            colorbar=dict(thickness=8, ticksuffix="M", tickfont=dict(size=10, color=TEXT_DIM), outlinewidth=0)))
        spot_row = min(range(len(hm.index)), key=lambda i: abs(hm.index[i] - spot))
        fig.add_hline(y=spot_row, line=dict(color="#FFFFFF", width=1, dash="dot"),
                      annotation_text=f"spot {spot:,.0f}", annotation_position="right",
                      annotation_font=dict(size=10, color=TEXT))
        fig.update_layout(yaxis=dict(type="category", title=None, side="left"), xaxis=dict(type="category", side="top"),
                          margin=dict(l=8, r=8, t=30, b=8))
        plot(fig, key="exp_heat")
    note(f"Estimates from CBOE delayed quotes for {_esc(tk)}, assuming customers are net long options and dealers "
         "hedge the other side. Real positioning is not public; treat levels as zones, not lines.")
