"""Exchange rates, national currency per US dollar, daily, as published by the BIS (bilateral exchange rates, WS_XRU,
compiled from national sources), for the eleven economies other than Indonesia (Indonesia's rupiah is id_fx_bis,
with monthly series too). Asked for 2 Nov 2026: a Financial tab on every dashboard with the BIS daily chart only.
Vietnam is not fetched: the BIS has no daily dong series (D.VN.VND.A returns nothing). The source fails only if every
economy fails; one that fails its checks is reported as a warning and left as it was.

API: BIS SDMX v2 (stats.bis.org), CSV, no key; one call per economy (series D.<area>.<currency>.A, full history).
Writes data/<cc>/fx/: <cc>_fx_daily.csv (date, rate), long.csv (daily rows), release.json, release_row.json
(code X<latest date>, label "BIS daily to <date>"). Each economy is checked and written on its own: one that fails its
checks or is missing from the BIS is reported and left as it was, and the others still update.
Nothing is calculated.
"""
import csv
import hashlib
import io
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "fx_bis"
DESCRIPTION = "Currency per US dollar, BIS daily (10 economies; Indonesia is id_fx_bis; no Vietnam)"
SOURCE = "BIS, bilateral exchange rates (WS_XRU), from national sources"
URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/{key}?format=csv"

# country code: (BIS area, currency, name, latest-rate bounds as a units check)
ECONOMIES = {
    "jp": ("JP", "JPY", "Japanese yen", 50, 400),
    "kr": ("KR", "KRW", "Korean won", 500, 3000),
    "tw": ("TW", "TWD", "New Taiwan dollar", 15, 60),
    "cn": ("CN", "CNY", "Chinese renminbi", 3, 12),
    "hk": ("HK", "HKD", "Hong Kong dollar", 7.6, 7.95),
    "in": ("IN", "INR", "Indian rupee", 10, 200),
    "th": ("TH", "THB", "Thai baht", 15, 60),
    "my": ("MY", "MYR", "Malaysian ringgit", 2, 7),
    "sg": ("SG", "SGD", "Singapore dollar", 1, 2.5),
    "ph": ("PH", "PHP", "Philippine peso", 10, 100),
}


def get(key, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(URL.format(key=key), headers={"User-Agent": "asia-vitals", "Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if i == tries - 1:
                raise
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
        time.sleep(5 * (i + 1))


def one(cc, force):
    area, ccy, name, lo, hi = ECONOMIES[cc]
    out = DATA / cc / "fx"
    key = f"D.{area}.{ccy}.A"
    daily = {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in get(key) if r.get("OBS_VALUE") not in (None, "", "NaN")}
    ds = sorted(daily)
    errors, warnings = [], []
    if len(ds) < 1000:
        errors.append(f"{cc}: {len(ds)} daily observations for {key}")
    else:
        if any(v <= 0 for v in daily.values()):
            errors.append(f"{cc}: non-positive rate")
        if not lo <= daily[ds[-1]] <= hi:
            errors.append(f"{cc}: latest rate {daily[ds[-1]]} outside {lo}-{hi} (units?)")
        jumps = [b for a, b in zip(ds, ds[1:]) if b >= "2000" and not 0.8 < daily[b] / daily[a] < 1.25]
        if jumps:
            warnings.append(f"{cc}: daily moves beyond -20%/+25% since 2000: {jumps[:5]}")
    if errors:
        return None, errors, warnings
    state = read_json(out / "release.json", {}) or {}
    fp = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()[:16]
    last = ds[-1]
    if state.get("fingerprint") == fp and not force:
        return False, [], warnings
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{cc}_fx_daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "rate"])
        for d in ds:
            w.writerow([d, round(daily[d], 6)])
    code = f"X{last}"
    rows = ({"country": area, "indicator": "fx", "series": f"{ccy.lower()}_per_usd", "label": f"{name} per US dollar",
             "measure": "level", "area": "", "freq": "D", "date": d, "value": round(daily[d], 6), "unit": f"{ccy} per USD",
             "source": SOURCE, "release": code} for d in ds)
    nlong = write_long(rows, out / "long.csv")
    write_release(out, {"code": code, "label": f"BIS daily to {last}", "latest_date": last, "currency": ccy,
                        "unit": f"{name} per US dollar", "first_date": ds[0], "table": URL.format(key=key)},
                  warnings, len(ds), {"fingerprint": fp, "long_rows": nlong})
    return f"{cc} {ds[0]}..{last} {daily[last]:,.4g}", [], warnings


def update(force=False, **_):
    done, errors, warnings, unchanged = [], [], [], 0
    for cc in ECONOMIES:
        try:
            res, err, warn = one(cc, force)
        except Exception as e:  # noqa: BLE001
            res, err, warn = None, [f"{cc}: {type(e).__name__}: {e}"], []
        warnings += warn
        if err:
            errors += err
        elif res:
            done.append(res)
        else:
            unchanged += 1
    if errors and not done and not unchanged:
        raise CheckFailed(errors)
    warnings += [f"not updated: {e}" for e in errors]
    if not done:
        return {"updated": False, "code": None, "summary": "no change", "warnings": warnings}
    return {"updated": True, "code": None, "summary": "; ".join(done), "warnings": warnings}
