# Market Daily routine

Paste everything below the line into the prompt field at claude.ai/code/routines.
Repo: ArnavHP18/market-daily. Schedule: daily 02:15 UTC (07:45 IST, after US close and before India open). Connectors: none required (web search is built in). Remove Slack/Gmail etc. from the routine's connector list.

---

You maintain the Market Daily dashboard in this repository. Produce today's edition and push it. Work autonomously; do not stop to ask questions. Done means: `data/prices.json` and `data/brief.json` are updated, committed and pushed to `main`.

## 1. Refresh prices
```
pip install -q -U yfinance
python3 scripts/fetch_prices.py
```
Read the stderr log. If more than half the assets errored, retry once after 60 seconds. If it still fails, commit whatever succeeded, and put the failure in `brief.json` under `"headline"` so it is visible on the dashboard. Never fabricate prices or returns.

## 2. Research
Read `data/prices.json`. Cover (a) every asset with `"news": true` and (b) the 3 largest absolute `chg_1d_pct` movers in each group that are not already covered. For each, run web searches and collect 2 to 3 stories from the last 48 hours, preferring Reuters, Bloomberg, FT, WSJ, CNBC, Economic Times, Mint, Moneycontrol, Business Standard, Kitco (metals), CoinDesk (crypto). Each story needs a real URL that you actually saw in search results. Skip an asset rather than invent a source.

Also search for: yesterday's US close and driver; Nifty and Bank Nifty close, FII/DII net flows, USD/INR; Asia and Europe close; any scheduled macro events in the next 7 days (Fed, RBI, CPI, earnings of watchlist stocks, SEBI or RBI circulars affecting markets).

## 3. Outlook rules
For `outlook_1y` and `outlook_lt`, quote only named third-party views: sell-side consensus targets (already in `prices.json` as `target_mean`), bank house forecasts for gold, silver, oil, copper, rare earths (Goldman, UBS, Citi, JPM, ICICI Securities, Motilal Oswal, etc.), or the fund house's own commentary for mutual funds. Name the house and date. If you cannot find a cited view, write "No cited forecast found this run." Never produce your own number. Never use the words guaranteed, will, or should about future prices.

## 3b. IPOs
Search for IPOs opening in the next 14 days: India (NSE, BSE, SME excluded; sources Chittorgarh, Moneycontrol, Economic Times, SEBI DRHP list) and US (Nasdaq IPO calendar, Renaissance Capital). Write up to 10 into `ipos[]` with name, market, sector, open, close, price_band, lot, size, source, source_url, drhp_url (empty string if none). Only list issues with a confirmed open date.

## 3c. Saturdays only
If today is Saturday (UTC), also write `weekly.week_ending` and `weekly.narrative` (3 to 5 sentences on the week across US, India, metals, crypto, plus next week's setup). Do not list winners or losers; the page computes them. On other days keep the previous `weekly` object unchanged if it is less than 8 days old, else omit it.

## 4. Write `data/brief.json`
Match the schema in `data/brief.sample.json` exactly: `date`, `generated_at`, `headline` (one sentence, the single most important cross-market fact today), `summary.us`, `summary.india`, `summary.global` (2 sentences each, drivers not adjectives), `calendar` (next 7 days), `ipos`, `weekly` (per 3b and 3c), and `assets` keyed by watchlist `id` with `outlook_1y`, `outlook_lt`, `news[]` (`title`, `source`, `url`, `date`). Plain language, no markdown inside strings, no em dashes anywhere.

Validate: `python3 -c "import json; json.load(open('data/brief.json'))"`.

## 5. Publish
```
git add data/prices.json data/brief.json data/series
git commit -m "edition $(date -u +%F)"
git push origin main
```
If push is rejected, `git pull --rebase origin main` and push again.

## Guardrails
Do not edit `index.html`, `scripts/`, or `watchlist.json`. Do not add files. Do not exceed 70 web searches in one run; if the budget runs out, drop movers first, never the `news: true` assets. If a tool errors twice in a row, move on and note it in `headline`.
