"""Indonesia government gross debt, Rp and % of GDP, annual, IMF World Economic Outlook (GGXWDG, GGXWDG_NGDP), as
published. Asked for 30 Oct 2026 (Fiscal tab). General government (central plus regional; Indonesia's regional debt is
small, so it is close to the Ministry of Finance's central government debt), calendar years, from 2000, with the IMF's
projections. The Ministry's own monthly debt profile (DJPPR) is not reachable from GitHub's runners (login, certificate
errors); WDI's central government debt stops in 2009.

Projections: years after the latest year with a central government actual in SEKI (data/id/fiscal/id_fiscal_annual.csv).
API: IMF SDMX 3.0 (api.imf.org, no key).
"""
import csv
import hashlib
import json

from core.common import DATA, CheckFailed, read_json, write_long, write_release
from sources.id_gdp_imf import get, parse

NAME = "id_debt_imf"
DESCRIPTION = "Indonesia general government gross debt, Rp and % of GDP, IMF World Economic Outlook"
OUT = DATA / "id" / "debt_imf"
SOURCE = "IMF, World Economic Outlook (GGXWDG, GGXWDG_NGDP)"
BASE = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.{}.A"


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    lvl, attrs = parse(get(BASE.format("GGXWDG")))
    pct, _ = parse(get(BASE.format("GGXWDG_NGDP")))
    last_act = None
    p = DATA / "id" / "fiscal" / "id_fiscal_annual.csv"
    if p.exists():
        last_act = max((int(r["year"]) for r in csv.DictReader(open(p, encoding="utf-8")) if r["basis"] == "actual"), default=None)
    yrs = sorted(set(lvl) & set(pct))
    errors, warnings = [], []
    if not yrs or yrs[0] > 2005 or yrs != list(range(yrs[0], yrs[-1] + 1)):
        errors.append(f"IMF: years {yrs[:2]}..{yrs[-2:]}")
    if any(not 5 < pct[y] < 150 for y in yrs):
        errors.append("IMF: debt ratio outside 5-150% of GDP (unit change?)")
    # level / ratio gives the IMF's GDP; it should match its NGDP (id_gdp_imf) within rounding
    pg = DATA / "id" / "gdp_imf" / "id_gdp_imf.csv"
    if pg.exists():
        g = {int(r["year"]): float(r["gdp_nominal_rp_bn"]) for r in csv.DictReader(open(pg, encoding="utf-8"))}
        bad = [y for y in yrs if y in g and abs(lvl[y] / 1e9 / (pct[y] / 100) / g[y] - 1) > 0.01]
        if bad:
            warnings.append(f"debt / ratio differs from IMF GDP by more than 1% in {bad[:5]}")
    if errors:
        raise CheckFailed(errors)
    rows = [{"year": y, "debt": round(lvl[y] / 1e9, 3), "debt_pct_gdp": round(pct[y], 3),
             "imf_projection": "y" if last_act and y > last_act else ""} for y in yrs]
    fp = hashlib.sha256(json.dumps([rows, attrs], sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["year", "debt", "debt_pct_gdp", "imf_projection"]
    with open(OUT / "id_debt_imf.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    upd = attrs.get("COUNTRY_UPDATE_DATE", "")
    code = f"D-{upd}" if upd else f"D{yrs[-1]}"
    first_p = next((r["year"] for r in rows if r["imf_projection"]), None)
    label = f"{yrs[0]}-{yrs[-1]}, projections from {first_p} (IMF update {upd})"

    def long_rows():
        for r in rows:
            for k, unit in (("debt", "Rp billion"), ("debt_pct_gdp", "% of GDP")):
                yield {"country": "ID", "indicator": "debt_imf", "series": k, "label": "General government gross debt",
                       "measure": "projection" if r["imf_projection"] else "level", "area": "general government", "freq": "A",
                       "date": f"{r['year']}-01-01", "value": r[k], "unit": unit, "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_year": yrs[-1], "first_projection": first_p,
                        "table": BASE.format("GGXWDG[_NGDP]"), "attributes": attrs}, warnings, len(rows),
                  {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
