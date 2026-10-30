"""Indonesia nominal GDP, annual, from the IMF World Economic Outlook (indicator NGDP, GDP at current prices, national
currency), as published. Asked for 30 Oct 2026, as the denominator for budget ratios before 2010, in place of WDI.

The IMF's series equals BPS's 2010-base nominal GDP from 2010; before 2010 the IMF has linked BPS's earlier bases to
the 2010 level (published that way; the ratio to the unlinked figures varies by period, e.g. 1.088 in 2001-2007).
Includes the IMF's projections for later years, flagged here as such (year after the latest BPS year).

API: IMF SDMX 3.0 (api.imf.org, no key; the DataMapper API refuses GitHub's runners). Rp billion.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_gdp_imf"
DESCRIPTION = "Indonesia nominal GDP, annual, IMF World Economic Outlook (NGDP)"
OUT = DATA / "id" / "gdp_imf"
SOURCE = "IMF, World Economic Outlook (NGDP)"
URL = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.NGDP.A"


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


def parse(d):
    """{year: value in Rp} and the series attributes, from an SDMX-JSON 2.0 response with one series."""
    st = d["data"]["structures"][0]
    times = [int(v["value"]) for v in st["dimensions"]["observation"][0]["values"]]
    series = d["data"]["dataSets"][0]["series"]
    if len(series) != 1:
        raise CheckFailed([f"IMF: {len(series)} series returned, expected 1"])
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


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    vals, attrs = parse(get(URL))
    bps = {}
    p = DATA / "id" / "gdp" / "id_gdp_annual.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["code"] == "800" and r["nominal_level"]:
                bps[int(r["date"][:4])] = float(r["nominal_level"])
    # values come in Rp; the BPS overlap fixes the unit (Rp billion)
    rows = [{"year": y, "gdp": v / 1e9} for y, v in sorted(vals.items())]
    errors, warnings = [], []
    yrs = [r["year"] for r in rows]
    if not rows or yrs[0] > 2001 or yrs != list(range(yrs[0], yrs[-1] + 1)):
        errors.append(f"IMF: years {yrs[:2]}..{yrs[-2:]} (need every year from 2001)")
    over = [r for r in rows if r["year"] in bps]
    if not over:
        errors.append("IMF: no year overlaps BPS annual GDP")
    for r in over:
        if abs(r["gdp"] / bps[r["year"]] - 1) > 0.005:
            warnings.append(f"{r['year']}: IMF {r['gdp']:,.0f} vs BPS {bps[r['year']]:,.0f} Rp bn")
    if over and sum(abs(r["gdp"] / bps[r["year"]] - 1) > 0.05 for r in over) > 0:
        errors.append("IMF and BPS differ by more than 5% in an overlapping year (unit or definition change?)")
    if errors:
        raise CheckFailed(errors)
    last_bps = max(bps) if bps else None
    fp = hashlib.sha256(json.dumps([rows, attrs], sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    with open(OUT / "id_gdp_imf.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["year", "gdp_nominal_rp_bn", "imf_projection", "source"])
        for r in rows:
            w.writerow([r["year"], round(r["gdp"], 3), "y" if last_bps and r["year"] > last_bps else "", SOURCE])
    upd = attrs.get("COUNTRY_UPDATE_DATE", "")
    code = f"I-{upd}" if upd else f"I{rows[-1]['year']}"
    label = f"{rows[0]['year']}-{rows[-1]['year']} (IMF update {upd})"
    nlong = write_long(({"country": "ID", "indicator": "gdp_imf", "series": "NGDP", "label": "GDP, current prices",
                         "measure": "projection" if last_bps and r["year"] > last_bps else "level", "area": "", "freq": "A",
                         "date": f"{r['year']}-01-01", "value": round(r["gdp"], 3), "unit": "Rp billion", "source": SOURCE,
                         "release": code} for r in rows), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_year": rows[-1]["year"], "table": URL, "attributes": attrs},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
