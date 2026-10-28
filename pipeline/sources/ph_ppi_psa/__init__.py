"""Philippines producer prices: PSA Producer Price Index for manufacturing (2018 = 100), OpenSTAT.

As published, nothing calculated: index and y/y for total manufacturing and its 2-digit PSIC divisions,
Jan 2018 on (table 0012M4CPPI2; y/y from Jan 2019), and PSA's backcast for total manufacturing,
Jan 2001-Dec 2017 (0022M4CPPI1; its division backcasts are not used: some are on other levels, e.g. furniture ~1,600). PSA publishes no y/y for 2018: left blank.
The PPI comes from the Monthly Integrated Survey of Selected Industries, about two months after the month.
New data is detected from the folder listing's last-updated dates.
"""
import csv
import gzip
import json

from core import psa
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "ph_ppi_psa"
DESCRIPTION = "Philippines producer prices (PSA PPI for manufacturing, 2018 = 100)"
OUT = DATA / "ph" / "ppi"
RAWDIR = RAW / "ph" / "ppi_psa"
FOLDER = "2M/PI/PPI/PPIM"
CUR, BACK = FOLDER + "/0012M4CPPI2.px", FOLDER + "/0022M4CPPI1.px"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YOY_TOL = 0.1


def _key(txt):
    t = txt.strip(". ")
    code = t.split(" ")[0].rstrip(",")
    return ("manufacturing" if code == "C" else code.lower()), t


def _label(t):
    if t.startswith("C ") or t == "C MANUFACTURING":
        return "Manufacturing"
    parts = t.split(" ", 1)
    rest = parts[1] if len(parts) > 1 else t
    while rest[:1] == "C" and rest.split(" ")[0].rstrip(",").startswith("C"):  # "C29, C30 Manufacture..."
        rest = rest.split(" ", 1)[1]
    return rest.replace("Manufacture of ", "").replace("Other Manufacturing", "Other manufacturing").strip().capitalize()


def tidy(cur, back):
    out = {}
    for rows, dimname, src in ((back, "PSIC/Industry", "back"), (cur, "Industry Group/Division", "current")):
        for r in rows:
            txt = r[dimname]
            if txt.startswith(".."):  # 3-digit groups: not used
                continue
            if src == "back" and not txt.startswith("C "):  # backcast: total manufacturing only
                continue
            if r["Month"] not in MONTHS or r["value"] is None:
                continue
            key, t = _key(txt)
            d = f"{r['Year']}-{MONTHS.index(r['Month']) + 1:02d}-01"
            rec = out.setdefault((d, key), {"date": d, "series": key, "label": _label(t), "source": src})
            rec["index" if r["Item"] == "Index" else "yoy"] = r["value"]
            rec["source"] = src
    keys = []
    for (d, k) in sorted(out):
        if k not in keys:
            keys.append(k)
    keys.sort(key=lambda k: (k != "manufacturing", k))
    rows = sorted(out.values(), key=lambda r: (r["date"], keys.index(r["series"])))
    for r in rows:
        r["order"] = keys.index(r["series"])
    return rows


def update(from_dir=None, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    if from_dir:
        from pathlib import Path
        src = Path(from_dir)
        cur = json.load(gzip.open(src / "ppim.json.gz", "rt"))
        back = json.load(gzip.open(src / "ppim_back.json.gz", "rt"))
        cur, back = cur.get("rows", cur) if isinstance(cur, dict) else cur, back.get("rows", back) if isinstance(back, dict) else back
        st = state.get("stamps", {})
    else:
        st = {f"{FOLDER}/{it['id']}": it.get("updated") for it in psa._request(f"{psa.BASE}/{FOLDER}")}
        if st == state.get("stamps"):
            return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
        cur, back = psa.get(CUR), psa.get(BACK)
    rows = tidy(cur, back)
    errors, warnings = [], []
    man = [r for r in rows if r["series"] == "manufacturing" and r.get("index") is not None]
    latest = max(r["date"] for r in man)
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    lm = next(r for r in man if r["date"] == latest)
    if lm.get("yoy") is None:
        errors.append(f"manufacturing y/y missing for {latest}")
    idx = {(r["series"], r["date"]): r.get("index") for r in rows if r["source"] == "current"}
    bad = []
    for r in rows:
        if r["source"] != "current" or r.get("yoy") is None or r["date"] < "2019-01-01":
            continue
        p, n = idx.get((r["series"], f"{int(r['date'][:4]) - 1}{r['date'][4:]}")), r.get("index")
        if p and n and abs((n / p - 1) * 100 - r["yoy"]) > YOY_TOL + 0.05:
            bad.append(f"{r['series']} {r['date'][:7]}: {r['yoy']} vs {(n / p - 1) * 100:.2f}")
    if len(bad) > 10:
        errors.append(f"{len(bad)} published y/y rates differ from the index, e.g. {bad[:3]}")
    elif bad:
        warnings.append("y/y vs index: " + "; ".join(bad[:10]))
    for r in rows:
        if r.get("index") is not None and not 0 < r["index"] < 1000:
            errors.append(f"{r['series']} {r['date']} index {r['index']} out of range")
            break
    if errors:
        raise CheckFailed(errors)
    code = f"P{latest[:7]}"
    if not from_dir:
        dest = RAWDIR / latest[:7]
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in (("ppim", cur), ("ppim_back", back)):
            with gzip.open(dest / f"{name}.json.gz", "wt", encoding="utf-8") as f:
                json.dump({"rows": data}, f, ensure_ascii=False)
    cols = ["date", "series", "label", "order", "index", "yoy"]
    with open(OUT / "ph_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])
    label = f"{SHORT[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2018 = 100"), ("yoy", "%")):
                yield {"country": "PH", "indicator": "ppi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r.get(meas), "unit": unit,
                       "source": "Philippine Statistics Authority", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    if state.get("code") == code:
        warnings.append("same month re-published (revision or table refresh)")
    release = {"code": code, "label": label, "latest_month": latest,
               "table": "PSA OpenSTAT 0012M4CPPI2, 0022M4CPPI1 (PPI for manufacturing, 2018 = 100)"}
    write_release(OUT, release, warnings, len(rows), {"long_rows": nlong, "stamps": st})
    return {"updated": True, "code": code, "summary": f"{label}: {len(rows)} rows", "warnings": warnings}
