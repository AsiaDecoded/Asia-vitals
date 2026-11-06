"""Benchmark stock indices for the 12 Asia-dashboard economies, daily close, from Yahoo Finance via yfinance (cookie and
crumb; GitHub's runners only, the workspace cannot reach Yahoo). Asked for 2 Nov 2026: a bar chart of year-to-date
returns on the Asia Financial tab, "use Yahoo Finance". Not an official source.
Thailand (SET), the Philippines (PSEi) and Vietnam (VN-Index): Yahoo returns no history, so CNBC's daily bars
(ts-api.cnbc.com, symbols .SETI, .PSI, .VNI; not an official source either) are used instead (asked for 6 Nov 2026:
"try other sites like yahoo finance for set and psei"). Ticker column "cnbc:<symbol>".

For each economy the first ticker that returns data is used (a list of candidates where Yahoo's symbol is uncertain).
Writes data/asia/eq/:
  asia_eq_daily.csv  economy, ticker, date, close (local-currency index points, from 1990 where Yahoo has it; completed sessions only)
  asia_eq_ytd.csv    economy, name, index, ticker, base_date, base_close, latest_date, latest_close, ytd_pct
                     ytd_pct = (latest close / last close on or before 31 Dec of the previous year - 1) x 100 (calculated):
                     price index, local currency, dividends not included
  long.csv, release.json, release_row.json (code E<latest date>-<hash>)
An economy whose tickers all fail, or whose series fails its checks, is left out and reported; the others still update.
"""
import csv
import hashlib
import json

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "eq_yahoo"
DESCRIPTION = "Benchmark stock indices, 12 Asian economies, daily close, Yahoo Finance"
OUT = DATA / "asia" / "eq"
SOURCE = "Yahoo Finance (CNBC for Thailand, the Philippines, Vietnam), not an official source"
START = "1990-01-01"
# economy: (name, index name, candidate tickers)
INDICES = {
    "JP": ("Japan", "Nikkei 225", ["^N225"]),
    "KR": ("South Korea", "KOSPI", ["^KS11"]),
    "TW": ("Taiwan", "TAIEX", ["^TWII"]),
    "HK": ("Hong Kong", "Hang Seng", ["^HSI"]),
    "CN": ("China", "Shanghai Composite", ["000001.SS"]),
    "IN": ("India", "Nifty 50", ["^NSEI"]),
    "ID": ("Indonesia", "Jakarta Composite", ["^JKSE"]),
    "TH": ("Thailand", "SET", ["cnbc:.SETI"]),
    "MY": ("Malaysia", "FTSE Bursa Malaysia KLCI", ["^KLSE"]),
    "SG": ("Singapore", "Straits Times Index", ["^STI"]),
    "PH": ("Philippines", "PSEi", ["cnbc:.PSI"]),
    "VN": ("Vietnam", "VN-Index", ["cnbc:.VNI"]),
}


def fetch_cnbc(symbol):
    """CNBC daily bars (close) from START, completed sessions only (today's bar dropped: Singapore date)."""
    import datetime as dt  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)
    today = now.date().isoformat()
    end = (now + dt.timedelta(days=2)).strftime("%Y%m%d000000")
    url = f"https://ts-api.cnbc.com/harmony/app/bars/{symbol}/1D/{START.replace('-', '')}000000/{end}/adjusted/EST5EDT.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=60) as r:
        bars = (json.loads(r.read()).get("barData") or {}).get("priceBars") or []
    out = {}
    for b in bars:
        d, v = str(b.get("tradeTime", ""))[:8], float(b.get("close") or 0)
        if len(d) == 8 and v > 0:
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            if START <= d < today:
                out[d] = v
    return out


def fetch(ticker):
    """Daily closes from START, completed sessions only (today's bar, which Yahoo fills with the live price during the
    session, is dropped: Singapore date). Some symbols return only the latest quote for a dated range; then period=max.
    A "cnbc:" ticker is read from CNBC instead."""
    if ticker.startswith("cnbc:"):
        return fetch_cnbc(ticker[5:])
    import datetime as dt  # noqa: PLC0415
    import yfinance as yf  # noqa: PLC0415
    today = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)).date().isoformat()
    out = {}
    for kw in ({"start": START}, {"period": "max"}):
        df = yf.Ticker(ticker).history(interval="1d", auto_adjust=False, **kw)
        if df is not None and not df.empty:
            out = {ix.strftime("%Y-%m-%d"): float(v) for ix, v in df["Close"].items() if v == v and v > 0}
            out = {d: v for d, v in out.items() if START <= d < today}
        if len(out) >= 500:
            break
    return out


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    series, warnings, errors = {}, [], []
    for econ, (name, idx, tickers) in INDICES.items():
        got = None
        for t in tickers:
            try:
                s = fetch(t)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{econ} {t}: {type(e).__name__}: {str(e)[:120]}")
                continue
            if len(s) >= 500:
                got = (t, s)
                break
            warnings.append(f"{econ} {t}: {len(s)} days")
        if not got:
            errors.append(f"{econ}: no ticker returned data ({', '.join(tickers)})")
            continue
        t, s = got
        ds = sorted(s)
        jumps = [b for a, b in zip(ds, ds[1:]) if not 0.7 < s[b] / s[a] < 1.4]
        if jumps:
            errors.append(f"{econ} {t}: daily moves beyond -30%/+40%: {jumps[:5]}")
            continue
        series[econ] = (t, s)
    if not series:
        raise CheckFailed(errors)
    warnings += [f"left out: {e}" for e in errors]
    rows = []
    for econ, (t, s) in series.items():
        ds = sorted(s)
        last = ds[-1]
        cut = f"{int(last[:4]) - 1}-12-31"
        base = max((d for d in ds if d <= cut), default=None)
        if not base:
            warnings.append(f"{econ}: no close on or before {cut}")
            continue
        name, idx, _ = INDICES[econ]
        rows.append({"economy": econ, "name": name, "index": idx, "ticker": t, "base_date": base, "base_close": round(s[base], 2),
                     "latest_date": last, "latest_close": round(s[last], 2), "ytd_pct": round((s[last] / s[base] - 1) * 100, 2)})
    latest = max(r["latest_date"] for r in rows)
    stale = [f"{r['economy']} {r['latest_date']}" for r in rows if r["latest_date"] < latest]
    if stale:
        warnings.append(f"latest dates differ: {', '.join(stale)}")
    fp = hashlib.sha256(json.dumps({e: s for e, (t, s) in series.items()}, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {latest})", "warnings": warnings}
    with open(OUT / "asia_eq_daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["economy", "ticker", "date", "close"])
        for econ, (t, s) in series.items():
            for d in sorted(s):
                w.writerow([econ, t, d, round(s[d], 2)])
    cols = ["economy", "name", "index", "ticker", "base_date", "base_close", "latest_date", "latest_close", "ytd_pct"]
    with open(OUT / "asia_eq_ytd.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    code = f"E{latest}-{fp[:6]}"
    nlong = write_long(({"country": econ, "indicator": "equity", "series": t, "label": f"{INDICES[econ][1]}, daily close",
                         "measure": "level", "area": "", "freq": "D", "date": d, "value": round(s[d], 2), "unit": "index points",
                         "source": SOURCE, "release": code}
                        for econ, (t, s) in series.items() for d in sorted(s)), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": f"Yahoo Finance and CNBC daily closes to {latest}", "latest_date": latest,
                        "economies": " ".join(r["economy"] for r in rows)},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong, "tickers": {e: t for e, (t, s) in series.items()}})
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": "; ".join(f"{r['economy']} {r['ticker']} {r['ytd_pct']:+.1f}%" for r in rows)}
