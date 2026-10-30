"""Indonesia nominal GDP, annual, from the World Bank's World Development Indicators (NY.GDP.MKTP.CN, GDP at current
prices, local currency), as published. Asked for 30 Oct 2026, as the denominator for budget ratios before 2010.

WDI's figures from 2010 equal BPS's 2010-base nominal GDP; before 2010 they are BPS's earlier bases, not linked to the
2010 base (2010 is 22% above 2009 in WDI, mostly the rebasing). Rp, written in Rp billion to match the BPS files.

API: api.worldbank.org/v2 (no key). About two seconds.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_gdp_wdi"
DESCRIPTION = "Indonesia nominal GDP, annual, World Bank WDI (NY.GDP.MKTP.CN)"
OUT = DATA / "id" / "gdp_wdi"
SOURCE = "World Bank, World Development Indicators (NY.GDP.MKTP.CN)"
URL = "https://api.worldbank.org/v2/country/IDN/indicator/NY.GDP.MKTP.CN?format=json&per_page=200"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "asia-vitals"}), timeout=90) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    d = get(URL)
    meta, recs = d[0], d[1]
    rows = sorted(({"year": int(r["date"]), "gdp": r["value"] / 1e9} for r in recs if r.get("value") is not None), key=lambda r: r["year"])
    errors = []
    if not rows or rows[0]["year"] > 1970:
        errors.append(f"WDI: series starts {rows[0]['year'] if rows else None}")
    yrs = [r["year"] for r in rows]
    if yrs != list(range(yrs[0], yrs[-1] + 1)):
        errors.append("WDI: gaps in the annual series")
    bps = {}
    p = DATA / "id" / "gdp" / "id_gdp_annual.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["code"] == "800" and r["nominal_level"]:
                bps[int(r["date"][:4])] = float(r["nominal_level"])
    warnings = [f"{r['year']}: WDI {r['gdp']:,.0f} vs BPS {bps[r['year']]:,.0f} Rp bn"
                for r in rows if r["year"] in bps and abs(r["gdp"] / bps[r["year"]] - 1) > 0.001]
    if errors:
        raise CheckFailed(errors)
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    with open(OUT / "id_gdp_wdi.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["year", "gdp_nominal_rp_bn", "source"])
        for r in rows:
            w.writerow([r["year"], round(r["gdp"], 3), SOURCE])
    code = f"W{rows[-1]['year']}-{meta.get('lastupdated', '')}"
    label = f"{rows[0]['year']}-{rows[-1]['year']} (WDI updated {meta.get('lastupdated', '')})"
    nlong = write_long(({"country": "ID", "indicator": "gdp_wdi", "series": "NY.GDP.MKTP.CN", "label": "GDP, current prices",
                         "measure": "level", "area": "", "freq": "A", "date": f"{r['year']}-01-01", "value": round(r["gdp"], 3),
                         "unit": "Rp billion", "source": SOURCE, "release": code} for r in rows), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_year": rows[-1]["year"], "table": URL},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
