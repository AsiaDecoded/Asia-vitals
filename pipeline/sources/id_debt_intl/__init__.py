"""Indonesia government debt, long-run series from international compilers, as published (asked for 31 Oct 2026,
alongside the official SUSPI series in chart 2 of the Fiscal tab):

  IMF Global Debt Database (GDD), central government debt, % of GDP, annual from 1972 (FL_S1311MIXED_POGDP_PT; the
    IMF's sources: an academic dataset, "JP", 1972-1985; IMF IFS and IDS 1986-1999; national source from 2000).
  BIS credit to the general government from all sectors at nominal value, adjusted for breaks, quarterly from Q4 2001:
    Rp billion, US$ billion and % of GDP (WS_TC, Q.ID.G.A.N.{XDC,USD,770}.A).

APIs: IMF SDMX 3.0 (api.imf.org), BIS SDMX v2 (stats.bis.org); no key.
"""
import csv
import hashlib
import io
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_debt_intl"
DESCRIPTION = "Indonesia government debt, IMF Global Debt Database (central government, % of GDP) and BIS credit to government"
OUT = DATA / "id" / "debt_intl"
GDD = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.FAD/GDD/+/IDN.FL_S1311MIXED_POGDP_PT.A"
BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_TC/2.0/Q.ID.G.A.N.*.A?format=csv"
SRC = {"gdd": "IMF, Global Debt Database (central government debt)", "bis": "BIS, credit to the general government (nominal value)"}


def get(url, accept="application/json", tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals", "Accept": accept})
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


def bis():
    rows = list(csv.DictReader(io.StringIO(get(BIS, "text/csv").decode("utf-8"))))
    out = {}
    for r in rows:
        if r["OBS_VALUE"] in ("", "NaN"):
            continue
        k = {"XDC": "bis_rp", "USD": "bis_usd", "770": "bis_pct"}.get(r["UNIT_TYPE"])
        if not k:
            continue
        mult = 10 ** int(r["UNIT_MULT"] or 0)
        v = float(r["OBS_VALUE"]) * mult
        v = v / 1e9 if k in ("bis_rp", "bis_usd") else v      # Rp billion, US$ billion
        out.setdefault(k, {})[r["TIME_PERIOD"]] = v
    return out


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    g, gnote = gdd()
    b = bis()
    errors, warnings = [], []
    gy = sorted(g)
    if not gy or gy[0] > 1980 or gy != list(range(gy[0], gy[-1] + 1)):
        errors.append(f"GDD: years {gy[:2]}..{gy[-2:]}")
    if any(not 3 < v < 150 for v in g.values()):
        errors.append("GDD: a ratio outside 3-150% of GDP")
    for k in ("bis_rp", "bis_usd", "bis_pct"):
        if not b.get(k):
            errors.append(f"BIS: {k} missing")
    if not errors:
        qs = sorted(b["bis_rp"])
        odd = [q for q in qs if q in b["bis_usd"] and not 8000 < b["bis_rp"][q] / b["bis_usd"][q] < 25000]
        if odd:
            errors.append(f"BIS: implied Rp/US$ outside 8,000-25,000 in {odd[:4]}")
        if any(not 3 < v < 150 for v in b["bis_pct"].values()):
            errors.append("BIS: a ratio outside 3-150% of GDP")
    if errors:
        raise CheckFailed(errors)
    rows = [{"series": "gdd_cg_pct", "period": str(y), "value": round(g[y], 3), "unit": "% of GDP", "note": gnote} for y in gy]
    for k, unit in (("bis_rp", "Rp billion"), ("bis_usd", "US$ billion"), ("bis_pct", "% of GDP")):
        for q in sorted(b[k]):
            rows.append({"series": k, "period": q, "value": round(b[k][q], 3), "unit": unit, "note": ""})
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["series", "period", "value", "unit", "note"]
    with open(OUT / "id_debt_intl.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    lq = max(b["bis_rp"])
    code = f"G{gy[-1]}-B{lq}"
    label = f"GDD {gy[0]}-{gy[-1]}; BIS {min(b['bis_rp'])}..{lq}"

    def long_rows():
        for r in rows:
            q = r["period"]
            date = f"{q[:4]}-{int(q[-1]) * 3:02d}-01" if "Q" in q else f"{q}-01-01"
            yield {"country": "ID", "indicator": "debt_intl", "series": r["series"], "label": r["series"], "measure": "level",
                   "area": "central government" if r["series"].startswith("gdd") else "general government",
                   "freq": "Q" if "Q" in q else "A", "date": date, "value": r["value"], "unit": r["unit"],
                   "source": SRC["gdd" if r["series"].startswith("gdd") else "bis"], "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "table": f"{GDD}; {BIS}"}, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
