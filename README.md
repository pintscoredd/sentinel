# Sentinel

Streamlit market and global-intelligence terminal: equities, options and SPX gamma,
macro, crypto, Hyperliquid perpetuals, Polymarket, a 3D geo monitor and a Gemini
assistant. Black-and-white UI; green/red is used only for signed values.

## Run

Python 3.12 or 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run sentinel_app.py
```

## API keys (all optional)

Put them in `.streamlit/secrets.toml` (never commit it) or environment variables.
Keys entered in the sidebar apply to that browser session only.

| Key | Unlocks |
| --- | --- |
| `FRED_API_KEY` | Macro regime score, PCE, credit spreads, net liquidity, central banks, sovereign yields (yields, CPI, jobs and fed funds work without it) |
| `FINNHUB_API_KEY` | Insider transactions, market news, economic calendar actual vs consensus |
| `GEMINI_API_KEY` | Sentinel AI |
| `NEWSAPI_KEY` | Extra headlines on the Geo page |
| `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` | Live SPY 0DTE chain, VWAP, direction model |
| `MARINESIA_API_KEY` | Extra AIS vessels at chokepoints |

Everything else is keyless: Yahoo Finance, Nasdaq (earnings calendar and stock screener for
the heatmap/breadth), Treasury.gov yield curve, BLS (CPI, jobs), NY Fed (fed funds), Hyperliquid,
CoinGecko, Polymarket, CBOE delayed options, CFTC COT, Google News RSS, GDELT, USGS,
NASA EONET, adsb.lol, CelesTrak, Digitraffic (Finnish AIS), Wikidata, Wikipedia,
World Bank. In the browser the globe also calls Planespotters (aircraft photos) and
CelesTrak (TLEs propagated live with satellite.js); earnings logos come from
Financial Modeling Prep's public image endpoint.

## Layout

```
sentinel_app.py            entry point: page config, theme, sidebar, navigation
sentinel/
  config.py                constants, rate limits, ticker lists
  state.py                 per-session state, API-key slots, watchlist persistence
  core/                    HTTP client (rate limit, circuit breaker, secret redaction),
                           formatting, secrets, stale-while-error cache
  analytics/               Black-Scholes / IV / Greeks, strategy payoff + probability of profit
  data/                    one module per domain: market, macro, options, zero_dte,
                           fundamentals, cross_asset, crypto, hyperliquid, polymarket, news, geo
  ui/                      palette + theme CSS, components, charts, globe (assets/globe.html)
  pages/                   one module per tab, each exposing render()
  ai/                      Gemini assistant + system prompt
```

Only the active tab (and the active sub-section on Markets / Options / Macro) runs, and
every data call is cached, so switching pages stays fast.

## Privacy

- Watchlist and AI memory are written to disk (`~/.sentinel/`) only when the app is
  opened from `localhost`. On a shared deployment they stay in the visitor's session,
  so one user's data is never shown to another. Override with `SENTINEL_PERSIST=1|0`.
- Error messages and logs are scrubbed of API keys/tokens; tracebacks are not shown
  in the browser (`.streamlit/config.toml`).

## Data notes

- Public feeds can be delayed, rate-limited or incomplete. Panels show as-of dates and
  never fabricate missing values.
- Hyperliquid funding is hourly; APR = hourly rate × 8,760. OI is converted at mark.
- The BTC ETF chart is a directional dollar-volume proxy, not creation/redemption flow.
- Polymarket "liquidity view" flags thin markets; it is not a trading signal. Placeholder
  outcomes (inactive, zero-volume "Team H" / "Other") are hidden.
- Conflict markers group the last 48 h of headlines by region; they mark a region, not
  an exact event location.

## Third-party code

Portions adapted from God's Eye View and OSIRIS (MIT); see `THIRD_PARTY_NOTICES.md`.
The globe uses [globe.gl](https://github.com/vasturiano/globe.gl) (MIT),
[satellite.js](https://github.com/shashwatak/satellite-js) (MIT) and the Esri Dark Gray
Canvas basemap. Aircraft photos are © their photographers via Planespotters.net; ship
silhouettes are illustrative, with a link to VesselFinder for real photos.
