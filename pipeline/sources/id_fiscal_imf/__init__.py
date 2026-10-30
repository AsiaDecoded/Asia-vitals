"""Indonesia general government net lending (+) / borrowing (-), % of GDP, annual, IMF World Economic Outlook
(GGXCNL_NGDP), as published. Asked for 30 Oct 2026 (Fiscal tab, chart 2). General government = central plus regional
governments, IMF definitions (GFSM); calendar years; from 1993, with the IMF's projections.

Projections: the observation attribute DERIVATION_TYPE when the API gives it; otherwise every year after the latest
year with a central government actual in SEKI (data/id/fiscal/id_fiscal_annual.csv) is marked as a projection.

API: IMF SDMX 3.0 (api.imf.org, no key).
"""
import csv
import hashlib
import json

from core.common import DATA, CheckFailed, read_json, write_long, write_release
from sources.id_gdp_imf import get, parse

NAME = "id_fiscal_imf"
DESCRIPTION = "Indonesia general government net lending/borrowing, % of GDP, IMF World Economic Outlook"
OUT = DATA / "id" / "fiscal_imf"
SOURCE = "IMF, World Economic Outlook (GGXCNL_NGDP)"
URL = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.GGXCNL_NGDP.A?attributes=all"


def derivation(d):
    """{year: derivation text} from observation attributes, if the response carries them."""
    try:
        st = d["data"]["structures"][0]
        times = [int(v["value"]) for v in st["dimensions"]["observation"][0]["values"]]
        oattr = st["attributes"].get("observation", [])
        k = next(i for i, a in enumerate(oattr) if a["id"] == "DERIVATION_TYPE")
        vals = oattr[k].get("values", [])
        s = next(iter(d["data"]["dataSets"][0]["series"].values()))
        out = {}
        for i, o in s["observations"].items():
            if len(o) > 1 + k and o[1 + k] is not None:
                a = o[1 + k]
                out[times[int(i)]] = a if isinstance(a, str) else (vals[a].get("name") or vals[a].get("id") or vals[a].get("value"))
        return out
    except Exception:  # noqa: BLE001
        return {}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    d = get(URL)
    vals, attrs = parse(d)
    der = derivation(d)
    last_act = None
    p = DATA / "id" / "fiscal" / "id_fiscal_annual.csv"
    if p.exists():
        last_act = max((int(r["year"]) for r in csv.DictReader(open(p, encoding="utf-8")) if r["basis"] == "actual"), default=None)
    errors, warnings = [], []
    yrs = sorted(vals)
    if not yrs or yrs[0] > 1995 or yrs != list(range(yrs[0], yrs[-1] + 1)):
        errors.append(f"IMF: years {yrs[:2]}..{yrs[-2:]}")
    if any(abs(v) > 20 for v in vals.values()):
        errors.append("IMF: a value beyond ±20% of GDP (unit change?)")
    if errors:
        raise CheckFailed(errors)

    def proj(y):
        if der.get(y):
            return "y" if "forecast" in der[y].lower() or "projection" in der[y].lower() else ""
        return "y" if last_act and y > last_act else ""
    rows = [{"year": y, "value": round(vals[y], 3), "imf_projection": proj(y), "derivation": der.get(y, "")} for y in yrs]
    if not der:
        warnings.append(f"no DERIVATION_TYPE in the response; years after {last_act} marked as projections")
    fp = hashlib.sha256(json.dumps([rows, attrs], sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["year", "value", "imf_projection", "derivation"]
    with open(OUT / "id_fiscal_imf.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    upd = attrs.get("COUNTRY_UPDATE_DATE", "")
    code = f"G-{upd}" if upd else f"G{yrs[-1]}"
    first_p = next((r["year"] for r in rows if r["imf_projection"]), None)
    label = f"{yrs[0]}-{yrs[-1]}, projections from {first_p} (IMF update {upd})"
    nlong = write_long(({"country": "ID", "indicator": "fiscal_imf", "series": "GGXCNL_NGDP",
                         "label": "General government net lending/borrowing, % of GDP",
                         "measure": "projection" if r["imf_projection"] else "level", "area": "general government", "freq": "A",
                         "date": f"{r['year']}-01-01", "value": r["value"], "unit": "% of GDP", "source": SOURCE, "release": code}
                        for r in rows), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_year": yrs[-1], "first_projection": first_p, "table": URL,
                        "attributes": attrs}, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
