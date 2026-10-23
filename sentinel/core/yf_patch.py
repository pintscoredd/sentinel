"""yfinance guard: drop bars whose Close is missing.

Yahoo often appends today's daily bar with NaN OHLC before (or after) the session.
Every `history(...)["Close"].iloc[-1]` in the app would then read NaN and the quote
would vanish. Patching once here keeps all call sites correct.
"""
from __future__ import annotations

import functools

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


def install() -> None:
    if yf is None or getattr(yf.Ticker.history, "_sentinel_patched", False):
        return
    original = yf.Ticker.history

    @functools.wraps(original)
    def history(self, *args, **kwargs):
        df = original(self, *args, **kwargs)
        try:
            if df is not None and not df.empty and "Close" in df.columns:
                df = df[df["Close"].notna()]
        except Exception:
            pass
        return df

    history._sentinel_patched = True
    yf.Ticker.history = history
