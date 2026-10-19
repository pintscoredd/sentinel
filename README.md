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
| `FRED_API_KEY` | Macro regime, curve, inflation, net liquidity, central banks, sovereign yields |
| `FINNHUB_API_KEY` | Insider transactions, market news, economic calendar actual vs consensus |
| `GEMINI_API_KEY` | Sentinel AI |
| `NEWSAPI_KEY` | Extra headlines on the Geo page |
| `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` | Live SPY 0DTE chain, VWAP, direction model |
| `MARINESIA_API_KEY` | Extra AIS vessels at chokepoints |

Everything else is keyless: Yahoo Finance, Hyperliquid, CoinGecko, Polymarket, CBOE
delayed options, CFTC COT, GDELT, USGS, NASA EONET, adsb.lol, CelesTrak,
Digitraffic, Wikidata, World Bank.

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
- Polymarket "liquidity view" flags thin markets; it is not a trading signal.

## Third-party code

Portions adapted from God's Eye View and OSIRIS (MIT); see `THIRD_PARTY_NOTICES.md`.
The globe uses [globe.gl](https://github.com/vasturiano/globe.gl) (MIT) and the Esri
Dark Gray Canvas basemap.
