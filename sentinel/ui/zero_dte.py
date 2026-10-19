"""0DTE panels: GEX read-out, recommendation card, trade log (all values in SPX points)."""
from __future__ import annotations

from sentinel.core.formatting import _esc
from sentinel.ui.palette import DOWN, FLAT, TEXT, TEXT_DIM, UP


def render_0dte_gex_decoder(gamma_flip, max_pain, wall_strike, wall_gex_m, spot):
    """Plain-language read of the gamma map. Inputs are SPX levels (or None)."""
    lines = []
    if gamma_flip and spot:
        if spot > gamma_flip:
            lines.append(f'<span style="color:{UP}">Spot {spot:,.0f} is above the gamma flip ({gamma_flip:,.0f})</span> — '
                         "dealers are net long gamma: they sell rallies and buy dips, which dampens moves.")
        else:
            lines.append(f'<span style="color:{DOWN}">Spot {spot:,.0f} is below the gamma flip ({gamma_flip:,.0f})</span> — '
                         "dealers are net short gamma: hedging chases price, which amplifies moves.")
    else:
        lines.append(f'<span style="color:{FLAT}">No gamma flip inside the displayed strike window.</span>')
    if wall_strike:
        side = "call" if (wall_gex_m or 0) >= 0 else "put"
        rel = f" ({abs(wall_strike - spot):,.0f} pts {'above' if wall_strike > spot else 'below'} spot)" if spot else ""
        if side == "call":
            lines.append(f"Largest wall: <b>call wall {wall_strike:,.0f}</b>{rel}, ${abs(wall_gex_m or 0):,.0f}M per 1%. "
                         "Positive gamma concentration tends to act as resistance / a pin into expiry.")
        else:
            lines.append(f"Largest wall: <b>put wall {wall_strike:,.0f}</b>{rel}, ${abs(wall_gex_m or 0):,.0f}M per 1%. "
                         "Negative gamma here can accelerate a sell-off rather than stop it.")
    if max_pain:
        lines.append(f"Max pain (front expiry): <b>{max_pain:,.0f}</b> — where option holders' payout is smallest.")
    body = "".join(f'<div style="margin:4px 0">{ln}</div>' for ln in lines)
    return (f'<div class="s-panel" style="font-size:13px;line-height:1.6"><div class="s-card-lbl" '
            f'style="margin-bottom:6px">Gamma read-out</div>{body}</div>')


def render_0dte_recommendation(rec):
    no_trade = "NO TRADE" in rec.get("recommendation", "")
    color = FLAT if no_trade else (UP if rec.get("opt_type") == "CALL" else DOWN)
    met = "".join(f'<li style="color:{UP}">{_esc(m)}</li>' for m in rec.get("conditions_met") or [])
    failed = "".join(f'<li style="color:{DOWN}">{_esc(m)}</li>' for m in rec.get("conditions_failed") or [])
    stats = _esc(rec.get("stats", "")).replace("\n", "<br>")
    mid = rec.get("mid_price") or 0
    return f"""
<div class="s-panel" style="border-left:3px solid {color};font-size:13px;line-height:1.6">
  <div style="color:{color};font-weight:700;font-size:15px">{_esc(rec.get('recommendation', ''))}</div>
  <div style="color:{TEXT};margin-top:6px">{_esc(rec.get('rationale', ''))}</div>
  {f'<div class="num" style="color:{TEXT_DIM};font-size:12px;margin-top:8px">{stats}</div>' if stats else ''}
  {f'<div style="margin-top:8px">{_esc(rec.get("action", ""))}</div>' if rec.get("action") else ''}
  <ul style="margin:8px 0 0 18px;padding:0;font-size:12px">{met}{failed}</ul>
  <div style="color:{TEXT_DIM};font-size:11px;margin-top:8px">Confidence {_esc(rec.get('confidence', ''))}
  {f' · option mid ${mid:.2f} (SPY contract)' if mid else ''} · research only, not advice</div>
</div>"""


def render_0dte_trade_log(entries):
    if not entries:
        return ""
    chips = "".join(
        f'<span class="s-pill" style="color:{UP if "CALL" in e else DOWN if "PUT" in e else FLAT}">{_esc(e)}</span>'
        for e in entries
    )
    return f'<div class="s-panel"><div class="s-card-lbl" style="margin-bottom:8px">Signal log</div>' \
           f'<div style="display:flex;flex-wrap:wrap;gap:6px">{chips}</div></div>'
