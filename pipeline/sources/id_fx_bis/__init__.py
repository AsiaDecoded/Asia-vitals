"""Indonesia rupiah per US dollar, as published by the BIS (bilateral exchange rates, WS_XRU, from national sources):
daily from January 1988 and monthly (average and end of period) from January 1967. Asked for 31 Oct 2026 (Financial
tab, longest USD/IDR series covering the Asian financial crisis). The IMF's IFS monthly series (ER dataflow) covers the
same span (1967-) and is not used. Bank Indonesia's own reference rate (JISDOR) starts only in 2013.

API: BIS SDMX v2 (stats.bis.org), CSV; no key.
"""
import csv
import hashlib
import io
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_fx_bis"
DESCRIPTION = "Indonesia rupiah per US dollar, BIS, daily from 1988 and monthly from 1967"
OUT = DATA / "id" / "fx"
SOURCE = "BIS, bilateral exchange rates (WS_XRU), from national sources"
URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/{key}?format=csv"


def get(key, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(URL.format(key=key), headers={"User-Agent": "asia-vitals", "Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    daily = {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in get("D.ID.IDR.A") if r["OBS_VALUE"] not in ("", "NaN")}
    mon = {}
    for r in get("M.ID.IDR.*"):
        if r["OBS_VALUE"] in ("", "NaN"):
            continue
        k = {"A": "avg", "E": "eop"}.get(r["COLLECTION"])
        if k:
            mon.setdefault(r["TIME_PERIOD"], {})[k] = float(r["OBS_VALUE"])
    errors, warnings = [], []
    ds, ms = sorted(daily), sorted(mon)
    if not ds or ds[0] > "1988-12-31":
        errors.append(f"daily series starts {ds[:1]}")
    if not ms or ms[0] > "1970-01":
        errors.append(f"monthly series starts {ms[:1]}")
    if any(v <= 0 for v in daily.values()):
        errors.append("non-positive daily rate")
    if ds and not (10000 < daily.get(max(d for d in ds if d <= "1998-06-30"), 0) < 20000):
        errors.append("June 1998 rate outside 10,000-20,000 (units?)")
    jumps = [b for a, b in zip(ds, ds[1:]) if b >= "1999" and not 0.85 < daily[b] / daily[a] < 1.15]
    if jumps:
        warnings.append(f"daily moves beyond 15% after 1998: {jumps[:5]}")
    gaps = [m for m in ms if set(mon[m]) != {"avg", "eop"}]
    if gaps:
        warnings.append(f"months without both average and end of period: {gaps[:5]}")
    if errors:
        raise CheckFailed(errors)
    fp = hashlib.sha256(json.dumps([daily, mon], sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    with open(OUT / "id_fx_daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "usd_idr"])
        for d in ds:
            w.writerow([d, round(daily[d], 4)])
    with open(OUT / "id_fx_monthly.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "avg", "eop"])
        for m in ms:
            w.writerow([f"{m}-01", round(mon[m].get("avg", 0), 4) or "", round(mon[m].get("eop", 0), 4) or ""])
    last = ds[-1]
    prev_y = max((d for d in ds if d <= f"{int(last[:4]) - 1}{last[4:]}"), default=None)
    end_y = max((d for d in ds if d < f"{last[:4]}-01-01"), default=None)
    row = {"date": last, "usd_idr": round(daily[last], 2),
           "yoy_pct": round((daily[last] / daily[prev_y] - 1) * 100, 2) if prev_y else "",
           "ytd_pct": round((daily[last] / daily[end_y] - 1) * 100, 2) if end_y else "",
           "label": f"BIS daily to {last}"}
    with open(OUT / "id_fx_latest.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(list(row))
        w.writerow(list(row.values()))
    code = f"X{last}"

    def long_rows():
        for m in ms:
            for k in ("avg", "eop"):
                if k in mon[m]:
                    yield {"country": "ID", "indicator": "fx", "series": f"usd_idr_{k}", "label": f"Rupiah per US dollar, monthly {k}",
                           "measure": k, "area": "", "freq": "M", "date": f"{m}-01", "value": round(mon[m][k], 4), "unit": "IDR per USD",
                           "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": row["label"], "latest_date": last, "table": URL.format(key="D.ID.IDR.A")},
                  warnings, len(ds) + len(ms), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{ds[0]}..{last} daily, {ms[0]}..{ms[-1]} monthly; latest {daily[last]:,.0f}",
            "warnings": warnings}
