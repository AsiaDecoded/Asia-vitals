"""Thailand GDP, annual, from the World Bank's World Development Indicators, as published (nothing calculated):

- real GDP growth, % (NY.GDP.MKTP.KD.ZG), 1961 on;
- GDP in current US$ (NY.GDP.MKTP.CD) and constant 2015 US$ (NY.GDP.MKTP.KD);
- GDP per capita in current US$ (NY.GDP.PCAP.CD) and constant 2015 US$ (NY.GDP.PCAP.KD).

GNI (Atlas method) is not fetched here: GNI per capita comes from the central dataset data/asia/gni/ (source gni_wdi),
and total GNI is to be added there by the main chat.
API: api.worldbank.org/v2 (no key). A few seconds.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long

NAME = "th_gdp_intl"
DESCRIPTION = "Thailand GDP, annual, World Bank WDI (growth, US$ levels, per capita)"
OUT = DATA / "th" / "gdp"
SERIES = {"NY.GDP.MKTP.KD.ZG": ("GDP growth, constant prices", "%", 1961),
          "NY.GDP.MKTP.CD": ("GDP, current US$", "US$", 1960), "NY.GDP.MKTP.KD": ("GDP, constant 2015 US$", "US$", 1960),
          "NY.GDP.PCAP.CD": ("GDP per capita, current US$", "US$", 1960),
          "NY.GDP.PCAP.KD": ("GDP per capita, constant 2015 US$", "US$", 1960)}
URL = "https://api.worldbank.org/v2/country/THA/indicator/{}?format=json&per_page=200"
SRC = "World Bank, World Development Indicators"


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
    vals, upd = {}, ""
    for code in SERIES:
        d = get(URL.format(code))
        upd = max(upd, d[0].get("lastupdated", ""))
        vals[code] = {int(r["date"]): float(r["value"]) for r in (d[1] or []) if r.get("value") is not None}
    nesdc = {}
    p = OUT / "th_gdp.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["span"] == "Y" and r["code"] == "total" and r["measure"] == "yoy" and r["price"] == "cvm_2002":
                nesdc[int(r["period"])] = float(r["rate"])
    errors, warnings = [], []
    last = max(vals["NY.GDP.MKTP.KD.ZG"]) if vals["NY.GDP.MKTP.KD.ZG"] else 0
    for code, (lab, unit, first) in SERIES.items():
        yrs = sorted(vals[code])
        if not yrs or yrs[0] > first or yrs != list(range(yrs[0], yrs[-1] + 1)):
            errors.append(f"{code}: years {yrs[:2]}..{yrs[-2:]} (need every year from {first})")
        if last not in vals[code]:
            errors.append(f"{code}: no figure for {last}")
        if unit == "US$" and any(v <= 0 for v in vals[code].values()):
            errors.append(f"{code}: non-positive values")
    if nesdc and last < max(nesdc) - 1:
        errors.append(f"WDI growth ends {last}, NESDC has {max(nesdc)}")
    for y in sorted(set(nesdc) & set(vals["NY.GDP.MKTP.KD.ZG"])):
        if abs(vals["NY.GDP.MKTP.KD.ZG"][y] - nesdc[y]) > 0.15:
            warnings.append(f"{y}: World Bank {vals['NY.GDP.MKTP.KD.ZG'][y]:.2f} vs NESDC {nesdc[y]:.1f}")
    if errors:
        raise CheckFailed(errors)
    rows = [{"year": y, "source": "wb_wdi", "series": code, "measure": "yoy" if code.endswith("ZG") else "level",
             "unit": SERIES[code][1], "value": round(v, 6) if code.endswith("ZG") else round(v, 2), "release": upd}
            for code in SERIES for y, v in sorted(vals[code].items())]
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    code = f"W{last}-{upd}"
    label = f"WDI to {last} (updated {upd})"
    if state.get("fingerprint") == fp and not force and (OUT / "th_gdp_intl.csv").exists():
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    with open(OUT / "th_gdp_intl.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "year", "source", "series", "label", "measure", "unit", "value", "release",
                                            "source_name"], lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({"date": f"{r['year']}-12-01", **r, "label": SERIES[r["series"]][0], "source_name": SRC})
    nlong = write_long(({"country": "TH", "indicator": "gdp_intl", "series": r["series"], "label": SERIES[r["series"]][0],
                         "measure": r["measure"], "area": "national", "freq": "A", "date": f"{r['year']}-12-01",
                         "value": r["value"], "unit": r["unit"], "source": SRC, "release": code} for r in rows), OUT / "long_intl.csv")
    rec = {"code": code, "label": label, "latest_year": last, "wdi_lastupdated": upd, "fingerprint": fp, "rows": len(rows),
           "long_rows": nlong, "warnings": warnings}
    (OUT / "release_intl.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
