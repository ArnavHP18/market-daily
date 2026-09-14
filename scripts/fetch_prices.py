#!/usr/bin/env python3
"""
Pulls 5y daily closes for every asset in data/watchlist.json.

Writes
  data/prices.json          summary for the list view (price, 1d, returns, 52w range, 30d sparkline, consensus)
  data/series/<id>.json     full 5y daily [[date, close], ...], loaded by the page only when an asset is opened

Sources
  yahoo (default)  yfinance batch download, per-ticker fallback, then stooq.com CSV (US only)
  mfapi            api.mfapi.in AMFI NAV history (Indian mutual funds, end of day)
"""
import json, math, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST = ROOT / "data" / "watchlist.json"
OUT = ROOT / "data" / "prices.json"
SERIES_DIR = ROOT / "data" / "series"
YEARS = 5
TARGET_TIME_BUDGET = 240  # seconds spent on analyst targets before giving up

def log(msg): print(msg, file=sys.stderr, flush=True)

def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "market-daily/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def clean(closes):
    return [[d.strftime("%Y-%m-%d"), round(float(c), 4)] for d, c in closes.items() if c is not None and not math.isnan(c)]

# ---------- sources ----------
def yahoo_batch(symbols):
    import yfinance as yf
    out = {}
    for i in range(0, len(symbols), 60):
        chunk = symbols[i:i+60]
        try:
            df = yf.download(chunk, period=f"{YEARS}y", interval="1d", auto_adjust=False,
                             group_by="ticker", threads=True, progress=False)
        except Exception as e:
            log(f"  batch download failed: {e}"); continue
        for s in chunk:
            try:
                col = df[s]["Close"] if len(chunk) > 1 else df["Close"]
                ser = clean(col.dropna())
                if ser: out[s] = ser
            except Exception:
                pass
        time.sleep(1)
    return out

def yahoo_single(symbol):
    import yfinance as yf
    h = yf.Ticker(symbol).history(period=f"{YEARS}y", interval="1d", auto_adjust=False)
    if h is None or h.empty: raise RuntimeError("empty history")
    return clean(h["Close"])

def yahoo_target(symbol):
    import yfinance as yf
    info = yf.Ticker(symbol).info or {}
    return info.get("targetMeanPrice"), info.get("numberOfAnalystOpinions")

def from_stooq(symbol):
    s = symbol.lower()
    if any(s.endswith(x) for x in (".ns", "=f", "=x", ".ax", ".ks", ".ss")) or s.startswith("^"):
        raise RuntimeError("stooq unsupported")
    csv = http_get(f"https://stooq.com/q/d/l/?s={s}.us&i=d")
    cutoff = (date.today() - timedelta(days=365 * YEARS)).isoformat()
    ser = []
    for line in csv.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 5 and p[0] >= cutoff:
            try: ser.append([p[0], float(p[4])])
            except ValueError: pass
    if not ser: raise RuntimeError("stooq empty")
    return ser

def from_mfapi(code):
    js = json.loads(http_get(f"https://api.mfapi.in/mf/{code}"))
    cutoff = date.today() - timedelta(days=365 * YEARS)
    ser = []
    for r in js.get("data") or []:
        d = datetime.strptime(r["date"], "%d-%m-%Y").date()
        if d >= cutoff: ser.append([d.isoformat(), float(r["nav"])])
    ser.sort()
    if not ser: raise RuntimeError("mfapi empty")
    return ser

# ---------- maths ----------
def close_on_or_before(series, target):
    best = None
    for d, c in series:
        if d <= target: best = c
        else: break
    return best

def pct(a, b): return None if (a is None or b in (None, 0)) else round((a / b - 1) * 100, 2)

def enrich(series):
    if len(series) < 2: return {}
    last_d, last = series[-1]; prev = series[-2][1]
    ld = date.fromisoformat(last_d)
    back = lambda days: close_on_or_before(series, (ld - timedelta(days=days)).isoformat())
    yr = [c for d, c in series if d >= (ld - timedelta(days=365)).isoformat()]
    spark = [c for d, c in series if d >= (ld - timedelta(days=30)).isoformat()]
    return {"price": round(last, 4), "as_of": last_d, "chg_1d_pct": pct(last, prev),
            "ret_1w": pct(last, back(7)), "ret_1m": pct(last, back(30)), "ret_3m": pct(last, back(91)), "ret_6m": pct(last, back(182)),
            "ret_1y": pct(last, back(365)), "ret_5y": pct(last, back(365 * 5)),
            "hi_52w": round(max(yr), 4), "lo_52w": round(min(yr), 4), "spark": spark}

# ---------- main ----------
def main():
    wl = json.loads(WATCHLIST.read_text())
    assets = [(g, a) for g in wl["groups"] for a in g["assets"]]
    yahoo_syms = [a["symbol"] for g, a in assets if a.get("source", "yahoo") == "yahoo"]
    log(f"{len(assets)} assets, {len(yahoo_syms)} via Yahoo")
    series_by_sym = yahoo_batch(yahoo_syms)
    log(f"batch returned {len(series_by_sym)}")

    SERIES_DIR.mkdir(exist_ok=True)
    keep = set()
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "groups": [{"id": g["id"], "label": g["label"]} for g in wl["groups"]], "assets": []}
    for g, a in assets:
        rec = {"id": a["id"], "symbol": a["symbol"], "name": a["name"], "group": g["id"],
               "type": a.get("type", "stock"), "currency": a.get("currency", g.get("currency", "USD")),
               "news": bool(a.get("news")), "error": None, "target_mean": None, "target_n": None}
        src = a.get("source", "yahoo")
        try:
            if src == "mfapi":
                ser = from_mfapi(a["symbol"])
            else:
                ser = series_by_sym.get(a["symbol"])
                if not ser:
                    try: ser = yahoo_single(a["symbol"])
                    except Exception as e:
                        log(f"  single fetch failed {a['symbol']}: {e}; trying stooq"); ser = from_stooq(a["symbol"])
            rec.update(enrich(ser))
            (SERIES_DIR / f"{a['id']}.json").write_text(json.dumps(ser, separators=(",", ":")))
            keep.add(f"{a['id']}.json")
        except Exception as e:
            rec["error"] = str(e)[:160]; log(f"ERR {a['symbol']:<16} {e}")
        out["assets"].append(rec)

    # analyst consensus, stocks only, time-boxed
    t0 = time.time(); n = 0
    for rec in out["assets"]:
        if rec["type"] != "stock" or rec["error"] or time.time() - t0 > TARGET_TIME_BUDGET: continue
        try:
            rec["target_mean"], rec["target_n"] = yahoo_target(rec["symbol"]); n += 1
        except Exception: pass
        time.sleep(0.3)
    log(f"targets fetched for {n} stocks in {int(time.time()-t0)}s")

    for f in SERIES_DIR.glob("*.json"):
        if f.name not in keep: f.unlink()
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    n_err = sum(1 for x in out["assets"] if x["error"])
    log(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB), {len(keep)} series files, {n_err} errors")
    for x in out["assets"]:
        if x["error"]: log(f"  {x['symbol']}: {x['error']}")
    return 1 if n_err > len(out["assets"]) // 2 else 0

if __name__ == "__main__":
    sys.exit(main())
