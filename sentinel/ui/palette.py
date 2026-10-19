"""Monochrome palette. Grayscale everywhere; green/red only for signed values."""

BG = "#000000"
PANEL = "#0A0A0A"
PANEL_2 = "#111111"
BORDER = "#1F1F1F"
BORDER_STRONG = "#333333"

TEXT = "#EDEDED"
TEXT_MUTED = "#A3A3A3"
TEXT_DIM = "#6E6E6E"
TEXT_FAINT = "#404040"
ACCENT = "#FFFFFF"

UP = "#3FCF8E"
DOWN = "#F2555A"
FLAT = "#8A8A8A"
UP_BG = "rgba(63,207,142,0.08)"
DOWN_BG = "rgba(242,85,90,0.08)"
HILITE_BG = "rgba(255,255,255,0.05)"

# Ordered grayscale ramp for multi-series charts (brightest = most important).
SERIES = ["#FFFFFF", "#C2C2C2", "#8F8F8F", "#666666", "#474747", "#2E2E2E"]

FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
MONO = "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace"


def signed_color(v, neutral=FLAT):
    """UP for >0, DOWN for <0, *neutral* otherwise."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return neutral
    if v > 0:
        return UP
    if v < 0:
        return DOWN
    return neutral
