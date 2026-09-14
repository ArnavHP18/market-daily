# Market Daily

Daily market dashboard, same pattern as ai-daily-signal: a Claude Code cloud routine writes two JSON files into this repo every morning, GitHub Pages serves `index.html`, which renders them.

```
index.html                 dashboard (no build step; loads data/*.json at runtime)
data/watchlist.json        what to track. Edit this, nothing else, to change coverage
data/prices.json           written by scripts/fetch_prices.py (prices, returns, 52w range, sparklines)
data/series/<id>.json      5y daily history per asset, loaded on demand by the page
data/brief.json            written by the routine (news, summaries, cited outlooks)
data/brief.sample.json     schema example; also the fallback until the routine's first run
scripts/fetch_prices.py    yfinance + mfapi.in fetcher
ROUTINE_PROMPT.md          paste into claude.ai/code/routines
```

## Setup (15 minutes)

1. Create a public repo `market-daily`, push these files to `main`.
2. Settings > Pages > Deploy from branch `main`, folder `/ (root)`. URL: `https://arnavhp18.github.io/market-daily/`.
3. Locally, run once to verify tickers and see the real page:
   ```
   pip install yfinance
   python3 scripts/fetch_prices.py
   python3 -m http.server 8000   # open http://localhost:8000
   ```
   Fix any `ERR` lines in the log (wrong ticker, wrong AMFI scheme code) in `watchlist.json`. Verify scheme codes at `https://api.mfapi.in/mf/search?q=parag`.
4. Commit `data/prices.json` and `data/series/` and push. Repeat steps 3 and 4 whenever you edit `watchlist.json`; the routine will also pick the change up on its next run.
5. claude.ai/code/routines > New routine > repo `market-daily`, paste `ROUTINE_PROMPT.md`, schedule daily 02:15 UTC, remove all connectors. Click Run now and watch the first run.
6. Add the Pages URL to the same Apple Shortcut pattern you used for ai-daily-signal.

## Portfolio
Open the Portfolio tab, paste holdings in the shown JSON shape, save. It is stored in your browser's localStorage only and never touches the repo. Ids are shown on each asset page ("id ppfas"). SIPs are expanded into monthly buys at that day's close or NAV, so past SIP units are approximate (actual allotment NAV can differ by a day).

## Cadence and data honesty

- US closes 01:30 IST, India closes 15:30 IST. A 07:45 IST run has both closes. Indian mutual fund NAVs land late evening IST, so they show the previous day's NAV.
- Yahoo data is delayed and unofficial. yfinance breaks a few times a year when Yahoo changes endpoints; the routine will then log errors and the dashboard shows the stale-data warning. Fix: `pip install -U yfinance` in the routine prompt.
- Analyst mean targets come from Yahoo and exist mainly for US-listed stocks. Everything forward-looking in `brief.json` must cite a named house.
