#!/usr/bin/env python3
"""
Pulls 5y daily closes for every asset in data/watchlist.json and writes data/prices.json.

Sources
  yahoo  : yfinance (unofficial Yahoo Finance client, no key). Fallback: stooq.com CSV.
  mfapi  : api.mfapi.in (AMFI NAV history, free, no key). NAVs are end-of-day only.

Output schema (data/prices.json)
  generated_at, groups[], assets[]  where each asset has:
    id, symbol, name, group, type, currency, price, as_of,
    chg_1d_pct, ret_1m, ret_3m, ret_6m, ret_1y, ret_5y (all % or null),
    target_mean, target_n (analyst consensus, Yahoo, usually null outside US equities),
    series: [[YYYY-MM-DD, close], ...]   (5y daily, used for the chart)
    error: string|null
"""
import io, json, math, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST = ROOT / "data" / "watchlist.json"
OUT = ROOT / "data" / "prices.json"
YEARS = 5

def log(msg): print(msg, file=sys.stderr, flush=True)

def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "market-daily/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

# ---------- sources ----------
def from_yahoo(symbol):
    import yfinance as yf
    t = yf.Ticker(symbol)
    hist = t.history(period=f"{YEARS}y", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        raise RuntimeError("empty history")
    series = [[d.strftime("%Y-%m-%d"), float(c)] for d, c in hist["Close"].items() if not math.isnan(c)]
    target_mean = target_n = None
    try:
        info = t.info or {}
        target_mean = info.get("targetMeanPrice")
        target_n = info.get("numberOfAnalystOpinions")
    except Exception:
        pass
    return series, target_mean, target_n

def from_stooq(symbol):
    # Stooq symbol style: aapl.us, ^spx, xauusd. Only covers a subset; best effort.
    s = symbol.lower()
    if s.endswith(".ns") or s.endswith("=f") or s.endswith("=x"):
        raise RuntimeError("stooq unsupported symbol")
    if not s.startswith("^") and "." not in s and "-" not in s:
        s = f"{s}.us"
    csv = http_get(f"https://stooq.com/q/d/l/?s={s}&i=d")
    series = []
    cutoff = (date.today() - timedelta(days=365 * YEARS)).isoformat()
    for line in csv.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 5 and p[0] >= cutoff:
            try: series.append([p[0], float(p[4])])
            except ValueError: pass
    if not series: raise RuntimeError("stooq empty")
    return series, None, None

def from_mfapi(scheme_code):
    js = json.loads(http_get(f"https://api.mfapi.in/mf/{scheme_code}"))
    rows = js.get("data") or []
    cutoff = date.today() - timedelta(days=365 * YEARS)
    series = []
    for r in rows:  # newest first, dd-mm-yyyy
        d = datetime.strptime(r["date"], "%d-%m-%Y").date()
        if d >= cutoff:
            series.append([d.isoformat(), float(r["nav"])])
    series.sort()
    if not series: raise RuntimeError("mfapi empty")
    return series, None, None

# ---------- maths ----------
def close_on_or_before(series, target):
    """Binary-ish search for the last close on or before target date (ISO string)."""
    best = None
    for d, c in series:
        if d <= target: best = c
        else: break
    return best

def pct(a, b):
    return None if (a is None or b in (None, 0)) else round((a / b - 1) * 100, 2)

def enrich(series):
    if len(series) < 2:
        return {}
    last_d, last = series[-1]
    prev = series[-2][1]
    ld = date.fromisoformat(last_d)
    def back(days): return close_on_or_before(series, (ld - timedelta(days=days)).isoformat())
    return {
        "price": round(last, 4), "as_of": last_d,
        "chg_1d_pct": pct(last, prev),
        "ret_1m": pct(last, back(30)), "ret_3m": pct(last, back(91)),
        "ret_6m": pct(last, back(182)), "ret_1y": pct(last, back(365)),
        "ret_5y": pct(last, back(365 * 5)),
    }

# ---------- main ----------
def main():
    wl = json.loads(WATCHLIST.read_text())
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "groups": [{"id": g["id"], "label": g["label"]} for g in wl["groups"]],
           "assets": []}
    for g in wl["groups"]:
        for a in g["assets"]:
            rec = {"id": a["id"], "symbol": a["symbol"], "name": a["name"], "group": g["id"],
                   "type": a.get("type", "stock"), "currency": a.get("currency", g.get("currency", "USD")),
                   "news": bool(a.get("news")), "error": None,
                   "target_mean": None, "target_n": None, "series": []}
            src = a.get("source", "yahoo")
            try:
                if src == "mfapi":
                    series, tm, tn = from_mfapi(a["symbol"])
                else:
                    try:
                        series, tm, tn = from_yahoo(a["symbol"])
                    except Exception as e:
                        log(f"  yahoo failed for {a['symbol']}: {e}; trying stooq")
                        series, tm, tn = from_stooq(a["symbol"])
                rec.update(enrich(series))
                rec["series"] = [[d, round(c, 4)] for d, c in series]
                rec["target_mean"], rec["target_n"] = tm, tn
                log(f"ok  {a['symbol']:<14} {rec.get('price')}  1m {rec.get('ret_1m')}%  1y {rec.get('ret_1y')}%")
            except Exception as e:
                rec["error"] = str(e)[:200]
                log(f"ERR {a['symbol']:<14} {e}")
            out["assets"].append(rec)
            time.sleep(0.4)  # be polite to Yahoo
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    n_err = sum(1 for x in out["assets"] if x["error"])
    log(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB), {n_err} errors")
    return 1 if n_err > len(out["assets"]) // 2 else 0

if __name__ == "__main__":
    sys.exit(main())
