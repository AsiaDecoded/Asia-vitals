"""Singapore CPI by household income group: SingStat, 2024 base, half-yearly, via the Table Builder API (no key).

SingStat's published y/y (change over the same half a year earlier) for all items, all items less accommodation and
all items less imputed rentals for housing, for the lowest 20%, middle 60% and highest 20% of households by income
(tables M214001, M214011, M214021; all items from 1H 1994, the two exclusion measures from 1H 2016). Released twice a
year, in January (July-December) and July (January-June). Dates: 1H is stored as June, 2H as December.
"""
import csv
import hashlib
import json

from core import singstat
from core.common import DATA, CheckFailed, read_json, write_release

NAME = "sg_cpi_hh_singstat"
DESCRIPTION = "Singapore CPI by household income group, half-yearly y/y (SingStat, 2024 base)"
OUT = DATA / "sg" / "cpi_hh"
GROUPS = [("l20", "Lowest 20%", "M214001"), ("m60", "Middle 60%", "M214011"), ("h20", "Highest 20%", "M214021")]
ROWS = [("all", "All items", "1"), ("less_accom", "All items less accommodation", "2"),
        ("less_imputed", "All items less imputed rentals for housing", "3")]


def _date(key):
    y, h = key.split()
    return f"{y}-{'06' if h == '1H' else '12'}-01"


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    metas = {t: singstat.metadata(t) for _, _, t in GROUPS}
    stamp = json.dumps({t: [m.get("dataLastUpdated"), m.get("endPeriod")] for t, m in metas.items()}, sort_keys=True)
    fingerprint = hashlib.sha256(stamp.encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    rows, errors, ends = [], [], set()
    for g, glab, t in GROUPS:
        tbl = singstat.table(t)
        by = {r["seriesNo"]: r for r in tbl["rows"]}
        for k, lab, no in ROWS:
            r = by.get(no)
            if not r:
                errors.append(f"{t}: row {no} ({lab}) missing")
                continue
            for c in r["columns"]:
                try:
                    v = float(c["value"])
                except (TypeError, ValueError):
                    continue
                if not -50 < v < 50:
                    errors.append(f"{t} {lab} {c['key']}: {v} out of range")
                rows.append({"date": _date(c["key"]), "period": c["key"], "group": g, "group_label": glab,
                             "series": k, "label": lab, "yoy": v})
            if k == "all":
                ends.add(max(c["key"] for c in r["columns"]))
    if len(ends) != 1:
        errors.append(f"income groups end in different periods: {sorted(ends)}")
    if errors:
        raise CheckFailed(errors)
    end = ends.pop()
    if state.get("latest_month") and _date(end) < state["latest_month"]:
        raise CheckFailed([f"latest period {end} is before the one already stored ({state['label']})"])
    rows.sort(key=lambda r: (r["date"], r["series"], r["group"]))
    with (OUT / "sg_cpi_hh.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "period", "group", "group_label", "series", "label", "yoy"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    y, h = end.split()
    release = {"code": f"H{y}-{h[0]}", "label": f"{h} {y}", "latest_month": _date(end),
               "table": "SingStat Table Builder M214001, M214011, M214021 (2024 base)"}
    write_release(OUT, release, [], len(rows), {"fingerprint": fingerprint})
    return {"updated": True, "code": release["code"], "summary": f"{h} {y}: {len(rows)} rows"}
