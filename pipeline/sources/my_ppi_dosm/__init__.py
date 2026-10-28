"""Malaysia producer prices: DOSM PPI (local production), 2010 = 100, from OpenDOSM (no key).

As published: the index, y/y and m/m for the total and the five sections (agriculture, mining, manufacturing,
electricity and gas, water supply), and DOSM's seasonally adjusted index and m/m for the total and sections
A, B and E (DOSM publishes no seasonally adjusted y/y, and none for C and D). Nothing is calculated here.
"""
import csv
import gzip
import hashlib
import json

from core import dosm
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "my_ppi_dosm"
DESCRIPTION = "Malaysia producer prices (DOSM PPI, 2010 base), with seasonally adjusted index and m/m, as published"
OUT = DATA / "my" / "ppi"
RAWDIR = RAW / "my" / "ppi_dosm"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FILES = {"total": "ppi/ppi.csv", "sections": "ppi/ppi_1d.csv"}
SECTIONS = {
    "total": "PPI, local production",
    "A": "Agriculture, forestry and fishing",
    "B": "Mining and quarrying",
    "C": "Manufacturing",
    "D": "Electricity, gas, steam and air conditioning supply",
    "E": "Water supply, sewerage, waste management and remediation",
}
SOURCE = "Department of Statistics Malaysia"


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    raw = {k: dosm.raw_csv(p) for k, p in FILES.items()}
    fingerprint = hashlib.sha256(raw["total"] + raw["sections"]).hexdigest()[:16]
    if fingerprint == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}
    ser = {}
    fields = {"abs": ("index", "index_sa"), "growth_yoy": ("yoy", None), "growth_mom": ("mom", "mom_sa")}
    for part, key_of in (("total", lambda r: "total"), ("sections", lambda r: r["section"])):
        for r in dosm.rows(raw[part]):
            f, fsa = fields.get(r["series"], (None, None))
            if not f:
                continue
            s = ser.setdefault(key_of(r), {}).setdefault(r["date"], {})
            s[f] = dosm.num(r["index"])
            if fsa:
                s[fsa] = dosm.num(r.get("index_sa"))
    errors = []
    if "total" not in ser:
        raise CheckFailed(["no total PPI in ppi.csv"])
    latest = max(d for d, v in ser["total"].items() if v.get("index") is not None)
    for k in SECTIONS:
        v = ser.get(k, {}).get(latest, {})
        # DOSM publishes seasonally adjusted series for the total and sections A, B and E only
        for f in ("index", "yoy", "mom") + (("index_sa", "mom_sa") if k in ("total", "A", "B", "E") else ()):
            if v.get(f) is None:
                errors.append(f"{k}: {f} missing for {latest}")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    for k, s in ser.items():
        for d, v in s.items():
            for f in ("index", "index_sa"):
                if v.get(f) is not None and not 10 < v[f] < 1000:
                    errors.append(f"{k} {d} {f} {v[f]} out of range")
            # DOSM's m/m should be its own index's change (published rates use unrounded indices)
            y, m = int(d[:4]), int(d[5:7])
            prev = s.get(f"{y if m > 1 else y - 1}-{(m - 2) % 12 + 1:02d}-01", {})
            for f, fi in (("mom", "index"), ("mom_sa", "index_sa")):
                if v.get(f) is not None and v.get(fi) and prev.get(fi):
                    if abs((v[fi] / prev[fi] - 1) * 100 - v[f]) > 0.2:
                        errors.append(f"{k} {d}: published {f} {v[f]:.2f} vs index {(v[fi] / prev[fi] - 1) * 100:.2f}")
    if errors:
        raise CheckFailed(errors[:20])
    order = {k: i for i, k in enumerate(SECTIONS)}
    cols = ["date", "series", "label", "order", "index", "yoy", "mom", "index_sa", "mom_sa"]
    rows = []
    for k in SECTIONS:
        for d in sorted(ser.get(k, {})):
            v = ser[k][d]
            rows.append({"date": d, "series": k, "label": SECTIONS[k], "order": order[k],
                         **{c: v.get(c) for c in cols[4:]}})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    with open(OUT / "my_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    code = f"P{latest[:7]}"
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    units = {"index": "index, 2010 = 100", "yoy": "%", "mom": "%", "index_sa": "index, 2010 = 100, seasonally adjusted",
             "mom_sa": "%, seasonally adjusted"}

    def long_rows():
        for r in rows:
            for meas, unit in units.items():
                yield {"country": "MY", "indicator": "ppi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(
        gzip.compress(json.dumps({k: v.decode("utf-8-sig") for k, v in raw.items()}, ensure_ascii=False).encode()))
    m = dosm.meta("ppi")
    warnings = ["recent months revised"] if state.get("latest_month") == latest else []
    release = {"code": code, "label": label, "latest_month": latest, "table": "OpenDOSM ppi, ppi_1d (2010 base)",
               "dosm_last_updated": m.get("last_updated"), "dosm_next_update": m.get("next_update")}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fingerprint, "long_rows": nlong})
    v = ser["total"][latest]
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": f"{label}: PPI {v['yoy']:.1f}% y/y, {v['mom_sa']:.1f}% m/m seasonally adjusted; {len(rows)} rows"}
