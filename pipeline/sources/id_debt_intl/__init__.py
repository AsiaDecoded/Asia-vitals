"""Indonesia central government debt, % of GDP, long run: the IMF Global Debt Database (GDD) from 1972, extended with
the official SUSPI central government series (Bank Indonesia and Ministry of Finance, table 1.1; from id_debt_suspi,
data/id/debt/id_debt.csv) for the years after the GDD ends and for the latest quarter. Asked for 31 Oct 2026.

  GDD: central government debt, % of GDP (FL_S1311MIXED_POGDP_PT), as published; the IMF's sources: an academic
    dataset ("JP") 1972-1985, IMF IFS and IDS 1986-1999, national source from 2000.
  SUSPI: year-end central government gross debt / annual BPS nominal GDP, and the latest quarter / four-quarter GDP
    (calculated in id_debt_suspi).

BIS credit to government, downloaded here until 31 Oct 2026, is no longer fetched (dropped at the user's request).
API: IMF SDMX 3.0 (api.imf.org, no key). Runs after id_debt_suspi.
"""
import csv
import hashlib
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_debt_intl"
DESCRIPTION = "Indonesia central government debt, % of GDP, IMF Global Debt Database from 1972 extended with SUSPI"
OUT = DATA / "id" / "debt_intl"
GDD = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.FAD/GDD/+/IDN.FL_S1311MIXED_POGDP_PT.A"
SRC_GDD = "IMF, Global Debt Database (central government debt)"
SRC_SUSPI = "Bank Indonesia and Ministry of Finance, SUSPI table 1.1; % of GDP calculated with BPS GDP"


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def gdd():
    d = json.loads(get(GDD))
    st = d["data"]["structures"][0]
    times = [int(v["value"]) for v in st["dimensions"]["observation"][0]["values"]]
    ser = d["data"]["dataSets"][0]["series"]
    if len(ser) != 1:
        raise CheckFailed([f"GDD: {len(ser)} series returned"])
    s = next(iter(ser.values()))
    vals = {times[int(i)]: float(o[0]) for i, o in s["observations"].items() if o and o[0] not in (None, "")}
    note = next((a for a in (s.get("attributes") or []) if isinstance(a, str) and "(" in a), "")
    return vals, note


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    g, gnote = gdd()
    errors, warnings = [], []
    gy = sorted(g)
    if not gy or gy[0] > 1980 or gy != list(range(gy[0], gy[-1] + 1)):
        errors.append(f"GDD: years {gy[:2]}..{gy[-2:]}")
    if any(not 3 < v < 150 for v in g.values()):
        errors.append("GDD: a ratio outside 3-150% of GDP")
    sus = []
    ps = DATA / "id" / "debt" / "id_debt.csv"
    if ps.exists():
        sus = [r for r in csv.DictReader(open(ps, encoding="utf-8")) if r["debt_pct_gdp"] != ""]
    else:
        warnings.append("SUSPI file not found; GDD only")
    if errors:
        raise CheckFailed(errors)
    rows = [{"series": "cg_pct", "period": str(y), "value": round(g[y], 3), "unit": "% of GDP", "source": "GDD", "note": gnote} for y in gy]
    ext = [r for r in sus if (r["quarter"].endswith("Q4") and int(r["quarter"][:4]) > gy[-1])]
    if sus and not sus[-1]["quarter"].endswith("Q4") and int(sus[-1]["quarter"][:4]) > gy[-1]:
        ext.append(sus[-1])
    for r in ext:
        q = r["quarter"]
        rows.append({"series": "cg_pct", "period": q[:4] if q.endswith("Q4") else q, "value": float(r["debt_pct_gdp"]),
                     "unit": "% of GDP", "source": "SUSPI", "note": "year-end / annual GDP" if q.endswith("Q4") else "quarter-end / four-quarter GDP"})
    # overlap check: GDD's latest years against SUSPI year-ends
    for r in sus:
        y = int(r["quarter"][:4])
        if r["quarter"].endswith("Q4") and y in g and y >= gy[-1] - 2 and abs(float(r["debt_pct_gdp"]) - g[y]) > 1.5:
            warnings.append(f"{y}: GDD {g[y]:.2f}% vs SUSPI {float(r['debt_pct_gdp']):.2f}%")
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["series", "period", "value", "unit", "source", "note"]
    with open(OUT / "id_debt_intl.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    code = f"G{gy[-1]}-{rows[-1]['period']}"
    label = f"GDD {gy[0]}-{gy[-1]}; SUSPI to {rows[-1]['period']}"

    def long_rows():
        for r in rows:
            q = r["period"]
            date = f"{q[:4]}-{int(q[-1]) * 3:02d}-01" if "Q" in q else f"{q}-12-01"
            yield {"country": "ID", "indicator": "debt_long", "series": "cg_pct", "label": "Central government debt, % of GDP",
                   "measure": "level" if r["source"] == "GDD" else "calculated", "area": "central government",
                   "freq": "Q" if "Q" in q else "A", "date": date, "value": r["value"], "unit": r["unit"],
                   "source": SRC_GDD if r["source"] == "GDD" else SRC_SUSPI, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "table": GDD}, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
