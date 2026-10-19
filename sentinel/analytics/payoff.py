"""Expiry payoff, breakevens, risk metrics and probability of profit for option strategies."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from sentinel.analytics.options_math import bs_greeks_engine


@dataclass
class Leg:
    kind: str          # "call" | "put" | "stock"
    qty: int           # signed contracts (+long / −short); stock in 100-share lots
    strike: float = 0.0
    premium: float = 0.0  # per share, paid (>0) for the option


def pnl_at_expiry(legs: list[Leg], prices: np.ndarray, spot: float) -> np.ndarray:
    """Total P&L in dollars (100 multiplier) at expiry for each underlying price."""
    total = np.zeros_like(prices, dtype=float)
    for lg in legs:
        if lg.kind == "stock":
            total += lg.qty * 100 * (prices - spot)
        else:
            intrinsic = np.maximum(prices - lg.strike, 0) if lg.kind == "call" else np.maximum(lg.strike - prices, 0)
            total += lg.qty * 100 * (intrinsic - lg.premium)
    return total


def _breakevens(x, y):
    out = []
    for i in range(len(y) - 1):
        if y[i] == 0:
            out.append(float(x[i]))
        elif y[i] * y[i + 1] < 0:
            out.append(float(x[i] - y[i] * (x[i + 1] - x[i]) / (y[i + 1] - y[i])))
    return sorted({round(b, 2) for b in out})


def analyze(legs: list[Leg], spot: float, T: float, r: float, sigma: float) -> dict:
    """Risk profile of *legs*.

    Max profit/loss come from a grid spanning 0 … 4× spot; a P&L that is still
    sloping at the top of the grid (net long/short calls or stock) is reported
    as unlimited. Probability of profit integrates the risk-neutral lognormal
    density over every price interval where P&L > 0 (handles 0, 1 or 2+
    breakevens, unlike a single-breakeven N(d)).
    """
    grid = np.concatenate([np.linspace(1e-6, spot * 0.5, 200, endpoint=False),
                           np.linspace(spot * 0.5, spot * 1.5, 2001),
                           np.linspace(spot * 1.5, spot * 4, 300)[1:]])
    pnl = pnl_at_expiry(legs, grid, spot)

    # Slope above the top strike: positive → unlimited upside, negative → unlimited downside.
    net_up_slope = sum(lg.qty * 100 for lg in legs if lg.kind in ("call", "stock"))
    max_profit = math.inf if net_up_slope > 0 else float(pnl.max())
    max_loss = -math.inf if net_up_slope < 0 else float(pnl.min())

    bes = _breakevens(grid, pnl)

    pop = None
    if sigma > 0 and T > 0:
        mu = math.log(spot) + (r - 0.5 * sigma * sigma) * T
        sd = sigma * math.sqrt(T)
        edges = np.concatenate([[0.0], (grid[1:] + grid[:-1]) / 2, [np.inf]])
        with np.errstate(divide="ignore"):
            cdf = norm.cdf((np.log(np.maximum(edges, 1e-300)) - mu) / sd)
        cdf[0], cdf[-1] = 0.0, 1.0
        mass = np.diff(cdf)
        pop = float(mass[pnl > 0].sum() * 100)

    debit = sum(lg.qty * 100 * lg.premium for lg in legs if lg.kind != "stock")
    greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for lg in legs:
        if lg.kind == "stock":
            greeks["delta"] += lg.qty * 100
            continue
        g = bs_greeks_engine(spot, lg.strike, T, r, sigma, lg.kind)
        for k in greeks:
            greeks[k] += lg.qty * 100 * g[k]

    return {"grid": grid, "pnl": pnl, "max_profit": max_profit, "max_loss": max_loss,
            "breakevens": bes, "pop": pop, "net_debit": debit, "greeks": greeks}
