"""Number/HTML formatting helpers shared by data and UI layers."""
from __future__ import annotations

import html
import math

from sentinel.ui.palette import DOWN, FLAT, UP


def _safe_float(v, default=0):
    """float(v), or *default* for None/NaN/inf/garbage."""
    if v is None:
        return default
    try:
        f = float(v)
    except (ValueError, TypeError, OverflowError):
        return default
    return default if (math.isnan(f) or math.isinf(f)) else f


def _safe_int(v, default: int = 0) -> int:
    f = _safe_float(v, None)
    return default if f is None else int(f)


def _esc(t) -> str:
    """HTML-escape any value (None → '')."""
    if t is None:
        return ""
    return html.escape(str(t), quote=True)


def _finite(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(p) or math.isinf(p)) else p


def _is_index_ticker(ticker=None) -> bool:
    if not ticker:
        return False
    t = str(ticker).upper().strip()
    # Indices, futures (=F, quoted in points/cents) and FX (=X) carry no "$".
    return t.startswith("^") or t.endswith(("=F", "=X")) or t in {"000001.SS", "DX-Y.NYB"}


def fmt_p(p, ticker=None) -> str:
    """Price: indices/yields without '$', micro-prices with more decimals."""
    p = _finite(p)
    if p is None:
        return "—"
    if _is_index_ticker(ticker):
        return f"{p:,.2f}" if abs(p) >= 10 else f"{p:.3f}"
    if p != 0 and abs(p) < 0.01:
        return f"${p:.6f}"
    if abs(p) < 1:
        return f"${p:.4f}"
    return f"${p:,.2f}"


def fmt_num(p, decimals: int = 2) -> str:
    p = _finite(p)
    return "—" if p is None else f"{p:,.{decimals}f}"


def fmt_vol(v) -> str:
    """Compact count: 1.20B / 45.3M / 120.5K."""
    v = _finite(v)
    if v is None or v < 0:
        return "—"
    if v >= 1e9:
        return f"{v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.1f}K"
    return f"{int(v)}"


def fmt_usd(v, decimals: int = 2) -> str:
    """Compact signed dollars: $1.23T / -$4.5B / $12.3M / $950K / $12."""
    v = _finite(v)
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    a = abs(v)
    for size, sfx in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= size:
            return f"{sign}${a / size:,.{decimals}f}{sfx}"
    return f"{sign}${a:,.0f}"


def fmt_pct(p, decimals: int = 2) -> str:
    p = _finite(p)
    return "—" if p is None else f"{p:+.{decimals}f}%"


def fmt_signed(p, decimals: int = 2) -> str:
    p = _finite(p)
    return "—" if p is None else f"{p:+,.{decimals}f}"


def pct_color(v) -> str:
    v = _finite(v)
    if v is None or v == 0:
        return FLAT
    return UP if v > 0 else DOWN


def _is_english(text: str) -> bool:
    """Heuristic: reject text where >15% of characters are non-ASCII."""
    if not text:
        return False
    return sum(1 for c in text if ord(c) < 128) / len(text) > 0.85
