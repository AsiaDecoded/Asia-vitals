"""Philippines GDP from the World Bank's World Development Indicators, annual, as published (nothing calculated).

- Real GDP growth, % (NY.GDP.MKTP.KD.ZG), for Chart 5 beside the PSA's annual growth.
- GDP in US dollars: current US$ (NY.GDP.MKTP.CD, the World Bank's conversion at annual average exchange rates) and
  constant 2015 US$ (NY.GDP.MKTP.KD), in US$.
- GDP per capita: current US$ (NY.GDP.PCAP.CD) and constant 2015 US$ (NY.GDP.PCAP.KD), in US$ per person.
- GNI, Atlas method, current US$ (NY.GNP.ATLS.CD), the total behind GNI per capita (asked for 2 Nov 2026).
  GNI per capita (Atlas) is not fetched here: the dashboard reads the central dataset data/asia/gni/asia_gni_pc.csv.

API: api.worldbank.org/v2, no key. A few seconds. Checks against the PSA's annual growth (data/ph/gdp/ph_gdp_annual.csv,
written by ph_gdp_psa) are warnings.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long

NAME = "ph_gdp_intl"
DESCRIPTION = "Philippines GDP, World Bank WDI: real growth, GDP and GDP per capita in US$, GNI (Atlas)"
OUT = DATA / "ph" / "gdp"
SERIES = {
    "NY.GDP.MKTP.KD.ZG": ("Real GDP growth", "yoy", "%"),
    "NY.GDP.MKTP.CD": ("GDP, current US$", "level", "US$"),
    "NY.GDP.MKTP.KD": ("GDP, constant 2015 US$", "level", "US$"),
    "NY.GDP.PCAP.CD": ("GDP per capita, current US$", "level", "US$"),
    "NY.GDP.PCAP.KD": ("GDP per capita, constant 2015 US$", "level", "US$"),
    "NY.GNP.ATLS.CD": ("GNI, Atlas method, current US$", "level", "US$"),
}
FIRST = 1987          # every series must run without gaps from here (charts start at the 1987 classification year)
URL = "https://api.worldbank.org/v2/country/PHL/indicator/{}?format=json&per_page=200"
SOURCE = "World Bank, World Development Indicators"


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release_intl.json", {}) or {}
    data, upd = {}, ""
    for code in SERIES:
        d = get(URL.format(code))
        data[code] = {int(r["date"]): float(r["value"]) for r in (d[1] or []) if r.get("value") is not None}
        upd = max(upd, d[0].get("lastupdated", "") or "")

    errors, warnings = [], []
    last = max(data["NY.GDP.MKTP.CD"]) if data["NY.GDP.MKTP.CD"] else 0
    for code, vals in data.items():
        yrs = sorted(vals)
        if not yrs or yrs[0] > FIRST or yrs != list(range(yrs[0], yrs[-1] + 1)) or yrs[-1] != last:
            errors.append(f"{code}: years {yrs[:2]}..{yrs[-2:]} (need every year from {FIRST} to {last})")
        if SERIES[code][1] == "level" and any(v <= 0 for v in vals.values()):
            errors.append(f"{code}: non-positive values")
        if SERIES[code][1] == "yoy" and any(not -20 < v < 20 for v in vals.values()):
            errors.append(f"{code}: growth out of range")
    # PSA's own annual real growth, where both have a year (warnings: WDI may lag a PSA revision)
    p = OUT / "ph_gdp_annual.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["code"] == "gdp" and r["price"].startswith("constant") and r["measure"] == "yoy" and r["value"]:
                y = int(r["year"])
                wb = data["NY.GDP.MKTP.KD.ZG"].get(y)
                if wb is not None and abs(wb - float(r["value"])) > 0.05:
                    warnings.append(f"{y}: WDI real growth {wb:.2f} vs PSA {float(r['value']):.2f}")
    if errors:
        raise CheckFailed(errors)

    rows = [{"year": y, "series": code, "label": SERIES[code][0], "measure": SERIES[code][1], "unit": SERIES[code][2],
             "value": round(v, 6) if SERIES[code][1] == "yoy" else round(v, 2), "release": upd}
            for code, vals in data.items() for y, v in sorted(vals.items())]
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    with open(OUT / "ph_gdp_intl.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["date", "year", "series", "label", "measure", "unit", "value", "release", "source"],
                            lineterminator="\n")
        wr.writeheader()
        for r in rows:
            wr.writerow({"date": f"{r['year']}-12-01", **r, "source": SOURCE})
    code = f"W-{upd}"
    label = f"WDI {FIRST}-{last} (updated {upd})"
    nlong = write_long(({"country": "PH", "indicator": "gdp_intl", "series": r["series"], "label": r["label"],
                         "measure": r["measure"], "area": "national", "freq": "A", "date": f"{r['year']}-12-01",
                         "value": r["value"], "unit": r["unit"], "source": SOURCE, "release": code} for r in rows),
                       OUT / "long_intl.csv")
    rec = {"code": code, "label": label, "latest_year": last, "wdi_lastupdated": upd, "fingerprint": fp,
           "rows": len(rows), "long_rows": nlong, "warnings": warnings}
    (OUT / "release_intl.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
