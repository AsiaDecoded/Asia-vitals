"""Vietnam real GDP growth, annual, from the IMF World Economic Outlook (NGDP_RPCH) and the World Bank's World
Development Indicators (NY.GDP.MKTP.KD.ZG), as published. Both are % change on the previous year at constant prices
(2010 prices, NSO's base until 2025); nothing is calculated here.

- IMF WEO: 1980 on, including the IMF's projections; years after NSO's latest yearbook year are flagged as projections.
- World Bank WDI: 1985 on. From 2006 the World Bank's rates equal NSO's yearbook (checked as warnings).
- World Bank WDI, GDP in US dollars (asked for 2 Nov 2026): current US$ (NY.GDP.MKTP.CD, the World Bank's conversion at
  annual average exchange rates) and constant 2015 US$ (NY.GDP.MKTP.KD), as published, in US$.
- World Bank WDI, GDP per capita in US dollars (asked for 2 Nov 2026): current US$ (NY.GDP.PCAP.CD) and constant 2015 US$
  (NY.GDP.PCAP.KD), as published, in US$ per person.
- World Bank WDI, GNI per capita, Atlas method (NY.GNP.PCAP.CD; the series the World Bank's income classification uses),
  as published, in US$ per person (asked for 2 Nov 2026).

APIs: IMF SDMX 3.0 (api.imf.org, no key) and api.worldbank.org/v2 (no key). A few seconds.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long

NAME = "vn_gdp_intl"
DESCRIPTION = "Vietnam real GDP growth, annual, IMF WEO (NGDP_RPCH) and World Bank WDI (NY.GDP.MKTP.KD.ZG)"
OUT = DATA / "vn" / "gdp"
WEO = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/VNM.NGDP_RPCH.A"
WDI = "https://api.worldbank.org/v2/country/VNM/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=200"
WDI_USD = {"NY.GDP.MKTP.CD": "GDP, current US$", "NY.GDP.MKTP.KD": "GDP, constant 2015 US$",
           "NY.GDP.PCAP.CD": "GDP per capita, current US$", "NY.GDP.PCAP.KD": "GDP per capita, constant 2015 US$",
           "NY.GNP.PCAP.CD": "GNI per capita, Atlas method, current US$"}
WDI_URL = "https://api.worldbank.org/v2/country/VNM/indicator/{}?format=json&per_page=200"
SRC = {"imf_weo": "IMF, World Economic Outlook (NGDP_RPCH)", "wb_wdi": "World Bank, World Development Indicators (NY.GDP.MKTP.KD.ZG)",
       "wb_wdi_usd": "World Bank, World Development Indicators"}


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


def weo(d):
    st = d["data"]["structures"][0]
    times = [int(v["value"]) for v in st["dimensions"]["observation"][0]["values"]]
    series = d["data"]["dataSets"][0]["series"]
    if len(series) != 1:
        raise CheckFailed([f"IMF WEO: {len(series)} series returned, expected 1"])
    s = next(iter(series.values()))
    vals = {times[int(i)]: float(o[0]) for i, o in s["observations"].items() if o and o[0] not in (None, "")}
    attrs = {}
    for k, a in zip(st.get("attributes", {}).get("series", []), s.get("attributes", [])):
        if isinstance(a, str):
            attrs[k["id"]] = a
        elif a is not None and k.get("values"):
            v = k["values"][a]
            attrs[k["id"]] = v.get("value", v.get("id", v.get("name")))
    return vals, attrs


def wdi(d):
    meta, rows = d[0], d[1] or []
    return {int(r["date"]): float(r["value"]) for r in rows if r.get("value") is not None}, meta.get("lastupdated", "")


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release_intl.json", {}) or {}
    w, attrs = weo(get(WEO))
    b, wb_upd = wdi(get(WDI))
    usd = {code: wdi(get(WDI_URL.format(code)))[0] for code in WDI_USD}   # US$, as published (units)
    nso = {}
    p = OUT / "vn_gdp_annual.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["table"] == "sector" and r["code"] == "total" and r["price"] == "constant_2010" and r["measure"] == "yoy":
                nso[int(r["year"])] = float(r["rate"])
    last_nso = max(nso) if nso else max(b)
    errors, warnings = [], []
    for name, vals, first in (("IMF WEO", w, 1980), ("World Bank WDI", b, 1985)):
        yrs = sorted(vals)
        if not yrs or yrs[0] > first or yrs != list(range(yrs[0], yrs[-1] + 1)):
            errors.append(f"{name}: years {yrs[:2]}..{yrs[-2:]} (need every year from {first})")
        if last_nso not in vals:
            errors.append(f"{name}: no figure for {last_nso}, NSO's latest year")
        for y, v in vals.items():
            if not -30 < v < 40:
                errors.append(f"{name} {y}: {v} out of range")
    for code, vals in usd.items():
        yrs = sorted(vals)
        if not yrs or yrs[0] > 1985 or yrs != list(range(yrs[0], yrs[-1] + 1)) or last_nso not in vals:
            errors.append(f"World Bank {code}: years {yrs[:2]}..{yrs[-2:]} (need every year from 1985 to {last_nso})")
        if any(v <= 0 for v in vals.values()):
            errors.append(f"World Bank {code}: non-positive values")
    for y in sorted(set(nso) & set(b)):
        if abs(b[y] - nso[y]) > 0.01:
            warnings.append(f"{y}: World Bank {b[y]:.2f} vs NSO yearbook {nso[y]:.2f}")
    for y in sorted(set(nso) & set(w)):
        if abs(w[y] - nso[y]) > 0.05:
            warnings.append(f"{y}: IMF WEO {w[y]:.2f} vs NSO yearbook {nso[y]:.2f}")
    if errors:
        raise CheckFailed(errors)
    rows = [{"year": y, "source": "imf_weo", "series": "NGDP_RPCH", "measure": "yoy", "unit": "%", "value": round(v, 6),
             "projection": "y" if y > last_nso else "", "release": attrs.get("COUNTRY_UPDATE_DATE", "")} for y, v in sorted(w.items())]
    rows += [{"year": y, "source": "wb_wdi", "series": "NY.GDP.MKTP.KD.ZG", "measure": "yoy", "unit": "%", "value": round(v, 6),
              "projection": "", "release": wb_upd} for y, v in sorted(b.items())]
    for code, vals in usd.items():
        rows += [{"year": y, "source": "wb_wdi_usd", "series": code, "measure": "level", "unit": "US$", "value": round(v, 2),
                  "projection": "", "release": wb_upd} for y, v in sorted(vals.items())]
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    with open(OUT / "vn_gdp_intl.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["date", "year", "source", "series", "measure", "unit", "value", "projection", "release",
                                             "source_name"],
                            lineterminator="\n")
        wr.writeheader()
        for r in rows:
            wr.writerow({"date": f"{r['year']}-12-01", **r, "source_name": SRC[r["source"]]})
    upd = attrs.get("COUNTRY_UPDATE_DATE", "")
    code = f"X-{upd}-{wb_upd}"
    label = f"IMF WEO {min(w)}-{max(w)} (update {upd}); WDI {min(b)}-{max(b)} (updated {wb_upd})"
    nlong = write_long(({"country": "VN", "indicator": "gdp_intl", "series": r["series"],
                         "label": WDI_USD.get(r["series"], f"Real GDP growth, {SRC[r['source']]}"),
                         "measure": "projection" if r["projection"] else r["measure"], "area": "national", "freq": "A",
                         "date": f"{r['year']}-12-01", "value": r["value"], "unit": r["unit"], "source": SRC[r["source"]],
                         "release": code} for r in rows), OUT / "long_intl.csv")
    # release_intl.json, so this source's record sits beside vn_gdp_nso's release.json in data/vn/gdp
    rec = {"code": code, "label": label, "latest_nso_year": last_nso, "weo_attributes": attrs, "wdi_lastupdated": wb_upd,
           "fingerprint": fp, "rows": len(rows), "long_rows": nlong, "warnings": warnings}
    (OUT / "release_intl.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
