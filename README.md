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

## Smoke test

Before pushing, check that every data feed still answers (needs network, no keys):

```bash
.venv/bin/python tests/smoke_data.py
```

It calls each public fetcher in `sentinel/data/` once and prints the time, result size or
exception. It exits non-zero on any exception, or when a core feed (quotes, screener,
Treasury curve, earnings week) is empty. Keyed feeds report `empty` without keys; that
is expected. Pass a name filter to run a subset (`tests/smoke_data.py macro`), or run it
under pytest with `.venv/bin/python -m pytest tests/smoke_data.py` if pytest is installed.

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
| `SEC_CONTACT` | Contact email sent to SEC EDGAR for the 13F tracker (SEC asks automated clients to identify themselves) |

Everything else is keyless: Yahoo Finance, Nasdaq (earnings calendar and stock screener for
the heatmap/breadth), Treasury.gov yield curve, BLS (CPI, jobs), NY Fed (fed funds), Hyperliquid,
CoinGecko, Polymarket, CBOE delayed options, CFTC COT, Google News RSS, GDELT, USGS,
NASA EONET, adsb.lol, CelesTrak, Digitraffic (Finnish AIS), Wikidata, Wikipedia,
World Bank. In the browser the globe also calls Planespotters (aircraft photos) and
CelesTrak (TLEs propagated live with satellite.js); earnings logos come from
Financial Modeling Prep's public image endpoint.

## Highlights

- **Options → Exposure (GEX):** dealer gamma, delta and vanna by strike and by strike × expiry, the gamma-flip
  level (Black-Scholes re-priced profile) and call/put walls for SPX, NDX, RUT or any optionable stock (CBOE delayed).
- **Markets → Heatmap:** market-cap treemap, breadth, sector participation, % of the 500 largest stocks above
  their 50/200-day averages and 52-week highs vs lows.
- **Markets → Funds (13F):** latest holdings and quarter-over-quarter changes for 18 well-known managers, plus
  the most-bought / most-sold stocks across all of them.
- **Perps:** Hyperliquid crowding board, regime map and funding vs Binance/Bybit.
- **Polymarket:** price history, largest holders, live trades and the trader leaderboard.
- **Geo:** 3D globe with live satellites, military aircraft (with photos), AIS ships and a country-risk
  choropleth (US travel advisories, conflict/unrest headlines, GDACS disasters, local market stress).

Ideas for several of these came from open-source projects: World Monitor (country instability index),
gammagrid and EzOptions (exposure views), rishisidhu/hyperliquid-dashboard (crowding), humanplane/terminal
(Polymarket depth), GreekSoup (13F) and xang1234/stock-screener (breadth). The code here is written for Sentinel.

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
