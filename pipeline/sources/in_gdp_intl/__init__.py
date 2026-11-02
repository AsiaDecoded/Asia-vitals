"""India GDP from the World Bank's World Development Indicators, annual, as published (nothing calculated).

- NY.GDP.MKTP.KD.ZG: real GDP growth, % (for the MoSPI / World Bank comparison chart).
- NY.GDP.MKTP.CD, NY.GDP.MKTP.KD: GDP, current US$ and constant 2015 US$.
- NY.GDP.PCAP.CD, NY.GDP.PCAP.KD: GDP per capita, current US$ and constant 2015 US$.
GNI (Atlas method) is not fetched here: it comes from the central dataset (data/asia/gni/, source gni_wdi).

WDI reports India's national accounts by fiscal year (April to March), labelled by the year the fiscal year begins
(WDI 2025 = 2025-26); the file keeps WDI's year and adds the fiscal-year label. Checked against MoSPI's published
annual growth (data/in/gdp/in_gdp.csv) as warnings. api.worldbank.org/v2, no key, a few seconds.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long

NAME = "in_gdp_intl"
DESCRIPTION = "India GDP, GDP per capita (US$) and real GDP growth, annual, World Bank WDI, as published"
OUT = DATA / "in" / "gdp"
URL = "https://api.worldbank.org/v2/country/IND/indicator/{}?format=json&per_page=200"
SERIES = {"NY.GDP.MKTP.KD.ZG": ("Real GDP growth", "%"),
          "NY.GDP.MKTP.CD": ("GDP, current US$", "US$"), "NY.GDP.MKTP.KD": ("GDP, constant 2015 US$", "US$"),
          "NY.GDP.PCAP.CD": ("GDP per capita, current US$", "US$"),
          "NY.GDP.PCAP.KD": ("GDP per capita, constant 2015 US$", "US$")}
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
    vals, upd, errors, warnings = {}, "", [], []
    for code in SERIES:
        d = get(URL.format(code))
        upd = d[0].get("lastupdated", upd)
        vals[code] = {int(r["date"]): float(r["value"]) for r in (d[1] or []) if r.get("value") is not None}
    for code, v in vals.items():
        yrs = sorted(v)
        if not yrs or yrs[0] > 1961 or yrs != list(range(yrs[0], yrs[-1] + 1)) or yrs[-1] < 2024:
            errors.append(f"{code}: years {yrs[:2]}..{yrs[-2:]} (need every year from 1961 to at least 2024)")
        if code.endswith("ZG"):
            if any(not -30 < x < 40 for x in v.values()):
                errors.append(f"{code}: value out of range")
        elif any(x <= 0 for x in v.values()):
            errors.append(f"{code}: non-positive values")
    if errors:
        raise CheckFailed(errors)
    p = OUT / "in_gdp.csv"
    if p.exists():
        mospi = {int(r["fy"][:4]): float(r["value"]) for r in csv.DictReader(open(p, encoding="utf-8"))
                 if r["freq"] == "A" and r["code"] == "gdp" and r["measure"] == "yoy" and r["price"] == "constant"}
        for y in sorted(set(mospi) & set(vals["NY.GDP.MKTP.KD.ZG"])):
            w = vals["NY.GDP.MKTP.KD.ZG"][y]
            if abs(round(w, 1) - mospi[y]) > 0.05:
                warnings.append(f"{y}-{(y + 1) % 100:02d}: World Bank {w:.2f} vs MoSPI {mospi[y]:.1f}")
    rows = [{"date": f"{y}-04-01", "year": y, "fy": f"{y}-{(y + 1) % 100:02d}", "series": code, "label": SERIES[code][0],
             "measure": "yoy" if code.endswith("ZG") else "level", "unit": SERIES[code][1],
             "value": round(x, 6) if code.endswith("ZG") else round(x, 2), "release": upd}
            for code, v in vals.items() for y, x in sorted(v.items())]
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    with open(OUT / "in_gdp_intl.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) + ["source"], lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "source": SOURCE})
    last = max(vals["NY.GDP.MKTP.CD"])
    code = f"W-{upd}"
    label = f"WDI updated {upd}, to {last} ({last}-{(last + 1) % 100:02d})"
    nlong = write_long(({"country": "IN", "indicator": "gdp_intl", "series": r["series"], "label": r["label"],
                         "measure": r["measure"], "area": "national", "freq": "A", "date": r["date"], "value": r["value"],
                         "unit": r["unit"], "source": SOURCE, "release": code} for r in rows), OUT / "long_intl.csv")
    (OUT / "release_intl.json").write_text(json.dumps({"code": code, "label": label, "wdi_lastupdated": upd, "fingerprint": fp,
                                                       "rows": len(rows), "long_rows": nlong, "warnings": warnings},
                                                      ensure_ascii=False, indent=1) + "\n")
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
