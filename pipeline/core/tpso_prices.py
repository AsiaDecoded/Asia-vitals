"""Shared update for TPSO price indices with one row set per type and month (PPI, export/import prices).

A source module gives: family, the types with their base year (BE) and first month, the codes to keep with English
labels, the output folder and file stem. Everything is as published (index, y/y, m/m); nothing is calculated.
New data is detected from MasterData's latest month per type; a new month re-fetches the latest three months
(TPSO may revise them); a missing type is backfilled. Store: raw/th/<stem>_tpso/store.json.gz; each run's new
responses: raw/th/<stem>_tpso/<YYYY-MM>/.
"""
import csv
import gzip
import hashlib
import json

from core import tpso
from core.common import CheckFailed, read_json, write_long, write_release

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YOY_TOL = 0.25  # published y/y vs the published index (TPSO rounds indices to one decimal, rates come from unrounded ones)


def _shift(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def run(spec, force=False):
    """spec: dict(family, types={type: (base_be, first 'YYYY-MM' or '')}, codes={type: [(code, key, label)]},
    out, rawdir, stem, indicator, base_label, need=[(type, code)], table)."""
    out, rawdir = spec["out"], spec["rawdir"]
    out.mkdir(parents=True, exist_ok=True)
    state = read_json(out / "release.json", {}) or {}
    m = tpso.master(spec["family"])
    latest = {t: tpso.latest_period(m, b, t) for t, (b, _f) in spec["types"].items()}
    if None in latest.values():
        raise CheckFailed([f"MasterData lists no months for {latest}"])
    top = max(latest.values())
    store_path = rawdir / "store.json.gz"
    store = json.load(gzip.open(store_path, "rt", encoding="utf-8")) if store_path.exists() else {}
    if state.get("latest") == latest and all(t in store for t in spec["types"]) and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    new = {}
    for t, (base, first) in spec["types"].items():
        have = store.get(t, {})
        want = tpso.month_range(first or tpso.first_period(m, base, t), latest[t])
        recent = set(tpso.month_range(_shift(latest[t], 2), latest[t]))
        todo = [ym for ym in want if ym not in have or ym in recent or force]
        if todo:
            got = tpso.months(spec["family"], t, base, todo)
            new[t] = got
            have.update(got)
        store[t] = {ym: have[ym] for ym in sorted(have) if ym in set(want)}

    rows, errors, warnings = [], [], []
    order = 0
    published = {}
    for t, codes in spec["codes"].items():
        months = store.get(t, {})
        for code, key, label in codes:
            for ym in sorted(months):
                r = next((x for x in months[ym] if x["commodityCode"] == code), None)
                if not r or (r.get("index") is None and r.get("changeYear") is None):
                    continue
                rows.append({"date": ym + "-01", "type": t, "series": key, "code": code, "label": label,
                             "order": order, "index": r.get("index"), "yoy": r.get("changeYear"),
                             "mom": r.get("change")})
                if ym == latest[t]:
                    published[t] = r.get("createdAt")
            order += 1
    rawdir.mkdir(parents=True, exist_ok=True)
    with gzip.open(store_path, "wt", encoding="utf-8") as f:  # kept even if the checks fail
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    # checks
    for t, code in spec["need"]:
        if not any(r["type"] == t and r["code"] == code and r["date"] == latest[t] + "-01" and r["yoy"] is not None
                   for r in rows):
            errors.append(f"{t} {code}: no y/y for {latest[t]}")
    for t, ym in latest.items():
        old = (state.get("latest") or {}).get(t)
        if old and ym < old:
            errors.append(f"{t}: latest month {ym} is before the one already stored ({old})")
    idx = {(r["type"], r["code"], r["date"][:7]): r for r in rows}
    bad = []
    for (t, c, ym), r in idx.items():
        p = idx.get((t, c, f"{int(ym[:4]) - 1}{ym[4:]}"))
        if r["yoy"] is None or not p or not p["index"] or r["index"] is None or ym < spec.get("check_from", "0000"):
            continue
        calc = (r["index"] / p["index"] - 1) * 100
        tol = YOY_TOL * max(1, 100 / p["index"])  # one-decimal indices far below 100 round more
        if abs(calc - r["yoy"]) > tol:
            bad.append(f"{t} {c} {ym}: published {r['yoy']}, index gives {calc:.2f}")
    if len(bad) > 5:
        errors.append(f"{len(bad)} published y/y rates differ from the index, e.g. {bad[:3]}")
    elif bad:
        warnings.append("y/y vs index: " + "; ".join(bad))
    for t in spec["types"]:
        dates = sorted({r["date"][:7] for r in rows if r["type"] == t and r["order"] == min(
            x["order"] for x in rows if x["type"] == t)})
        gaps = [ym for ym in tpso.month_range(dates[0], latest[t]) if ym not in set(dates)] if dates else ["all"]
        if gaps:
            errors.append(f"{t}: months missing, e.g. {gaps[:5]}")
    if errors:
        raise CheckFailed(errors)

    dest = rawdir / top
    dest.mkdir(parents=True, exist_ok=True)
    for t, months in new.items():
        recent = {ym: v for ym, v in months.items() if ym >= _shift(latest[t], 2)}
        if recent:
            with gzip.open(dest / f"{t}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(recent, f, ensure_ascii=False)
    with gzip.open(store_path, "wt", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "type", "series", "code", "label", "order", "index", "yoy", "mom"]
    with open(out / f"{spec['stem']}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])
    code = "P" + top
    label = f"{MONTHS[int(top[5:7]) - 1]} {top[:4]}"

    def long_rows():
        for r in rows:
            for meas, unit in (("index", spec["base_label"]), ("yoy", "%"), ("mom", "% m/m")):
                yield {"country": "TH", "indicator": spec["indicator"], "series": r["series"], "label": r["label"],
                       "measure": meas, "area": "national", "freq": "M", "date": r["date"], "value": r[meas],
                       "unit": unit, "source": "Trade Policy and Strategy Office, Ministry of Commerce", "release": code}
    nlong = write_long(long_rows(), out / "long.csv")
    fp = hashlib.sha256(json.dumps(rows[-400:], sort_keys=True).encode()).hexdigest()[:16]
    release = {"code": code, "label": label, "latest_month": top + "-01", "latest": latest,
               "published_at": published, "table": spec["table"]}
    write_release(out, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: {len(rows)} rows, "
            f"{sum(len(v) for v in new.values())} months fetched", "warnings": warnings}
