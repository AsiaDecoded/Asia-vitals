"""Benchmark stock indices for the 12 Asia-dashboard economies, daily close, from Yahoo Finance via yfinance (cookie and
crumb; GitHub's runners only, the workspace cannot reach Yahoo). Asked for 2 Nov 2026: a bar chart of year-to-date
returns on the Asia Financial tab, "use Yahoo Finance". Not an official source.

For each economy the first ticker that returns data is used (a list of candidates where Yahoo's symbol is uncertain).
Writes data/asia/eq/:
  asia_eq_daily.csv  economy, ticker, date, close (local-currency index points, from 2015)
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
SOURCE = "Yahoo Finance, not an official source"
START = "2015-01-01"
# economy: (name, index name, candidate tickers)
INDICES = {
    "JP": ("Japan", "Nikkei 225", ["^N225"]),
    "KR": ("South Korea", "KOSPI", ["^KS11"]),
    "TW": ("Taiwan", "TAIEX", ["^TWII"]),
    "HK": ("Hong Kong", "Hang Seng", ["^HSI"]),
    "CN": ("China", "Shanghai Composite", ["000001.SS"]),
    "IN": ("India", "Nifty 50", ["^NSEI"]),
    "ID": ("Indonesia", "Jakarta Composite", ["^JKSE"]),
    "TH": ("Thailand", "SET", ["^SET.BK"]),
    "MY": ("Malaysia", "FTSE Bursa Malaysia KLCI", ["^KLSE"]),
    "SG": ("Singapore", "Straits Times Index", ["^STI"]),
    "PH": ("Philippines", "PSEi", ["PSEI.PS", "^PSEI"]),
    "VN": ("Vietnam", "VN-Index", ["^VNINDEX.VN", "^VNINDEX", "VNINDEX.VN", "E1VFVN30.VN"]),
}


def fetch(ticker):
    import yfinance as yf  # noqa: PLC0415
    df = yf.Ticker(ticker).history(start=START, interval="1d", auto_adjust=False)
    if df is None or df.empty:
        return {}
    return {ix.strftime("%Y-%m-%d"): float(v) for ix, v in df["Close"].items() if v == v and v > 0}


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
    write_release(OUT, {"code": code, "label": f"Yahoo Finance daily closes to {latest}", "latest_date": latest,
                        "economies": " ".join(r["economy"] for r in rows)},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong, "tickers": {e: t for e, (t, s) in series.items()}})
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": "; ".join(f"{r['economy']} {r['ticker']} {r['ytd_pct']:+.1f}%" for r in rows)}
