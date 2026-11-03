"""India Index of Industrial Production, MoSPI (api.mospi.gov.in/api/iip/getIipData), monthly, as published, plus a
linked general and manufacturing index and its y/y, calculated (user, 3 Nov 2026).

As published (in_iip.csv): 2011-12 base, April 2012 - March 2026 and 2022-23 base, April 2023 on; General, Sectoral
(mining, manufacturing and its NIC divisions, electricity; on the new base also water supply, sewerage and waste) and
use-based categories; index and MoSPI's growth rate. On the 2022-23 base MoSPI's growth rate for April 2023 - March 2024
is the index less 100 (growth on the 2022-23 average, there being no monthly 2022-23 index), not y/y.

Linked (in_iip_linked.csv), calculated: 2011-12-base index / MoSPI's linking factor (geometric-mean method, first
release of the 2022-23 series, 1 Jun 2026: general 1.3834, manufacturing 1.3700) to March 2023, the 2022-23-base index
from April 2023. Monthly y/y from the linked index; quarterly: the linked index averaged over each quarter (Apr-Jun,
Jul-Sep, Oct-Dec, Jan-Mar), y/y from the averages. Rates rounded to one decimal, as MoSPI publishes. MoSPI says it
prescribes no linking method and growth rates across the two series are not strictly comparable.

Divisions (in_iip_divisions.csv): see divisions().\nChecks (errors stop it): every month present on each base; linked y/y equals MoSPI's published y/y within 0.15pp
wherever both indices are on one base (to March 2023 on the old base, from April 2024 on the new base).
Dates: first day of the month; quarters at their first month (Apr-Jun 2026 = 2026-04-01). About 80 calls, ~1 minute.
"""
import csv
import hashlib
import json

from core import mospi
from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "in_iip_mospi"
DESCRIPTION = "India IIP, MoSPI, monthly (2011-12 and 2022-23 bases, as published) and linked general and manufacturing index, y/y"
OUT = DATA / "in" / "iip"
PATH = "/api/iip/getIipData"
FACTORS = {"general": 1.3834, "manufacturing": 1.3700}   # MoSPI, linking 2011-12 to 2022-23 (geometric mean)
SPLICE = "2023-04-01"
BASES = ("2011-12", "2022-23")
TYPES = ("General", "Sectoral", "Use-based category")
COLS = ["date", "base_year", "type", "category", "sub_category", "index", "growth_rate"]


def fetch():
    out = []
    for by in BASES:
        for t in TYPES:
            rows, total = mospi.paged(PATH, {"base_year": by, "frequency": "Monthly", "type": t}, max_pages=80)
            if not rows or (total is not None and len(rows) != int(total)):
                raise CheckFailed([f"IIP {by} {t}: {len(rows)} rows of {total}"])
            for r in rows:
                out.append({"date": f"{int(r['year'])}-{mospi.month_number(r['month']):02d}-01", "base_year": by,
                            "type": r["type"], "category": r["category"], "sub_category": r.get("sub_category") or "",
                            "index": float(r["index"]) if r.get("index") not in (None, "") else None,
                            "growth_rate": float(r["growth_rate"]) if r.get("growth_rate") not in (None, "") else None})
    return out


def pick(rows, by, key):
    cat = {"general": "General", "manufacturing": "Manufacturing"}[key]
    return {r["date"]: r for r in rows if r["base_year"] == by and r["category"] == cat and r["sub_category"] == ""
            and r["index"] is not None}


def months(a, b):
    y, m = int(a[:4]), int(a[5:7])
    while f"{y}-{m:02d}-01" <= b:
        yield f"{y}-{m:02d}-01"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def prev_year(d):
    return f"{int(d[:4]) - 1}{d[4:]}"


def linked(rows):
    out, errors = [], []
    for key, f in FACTORS.items():
        old, new = pick(rows, "2011-12", key), pick(rows, "2022-23", key)
        for name, s in (("2011-12", old), ("2022-23", new)):
            ds = sorted(s)
            if not ds or ds != list(months(ds[0], ds[-1])):
                errors.append(f"{key} {name}: months missing between {ds[:1]} and {ds[-1:]}")
        idx = {d: (r["index"] / f, "2011-12") for d, r in old.items() if d < SPLICE}
        idx.update({d: (r["index"], "2022-23") for d, r in new.items() if d >= SPLICE})
        for d in sorted(idx):
            p = idx.get(prev_year(d))
            yoy = round((idx[d][0] / p[0] - 1) * 100, 1) if p else None
            out.append({"date": d, "freq": "M", "series": key, "index_linked": round(idx[d][0], 3), "yoy": yoy,
                        "base_year": idx[d][1], "calculated": "y"})
            # published y/y on one base: the old base before the splice, the new base a year after it
            new_yoy_from = f"{int(SPLICE[:4]) + 1}{SPLICE[4:]}"   # MoSPI's new-base y/y is genuine from April 2024
            pub = old.get(d) if d < SPLICE else (new.get(d) if d >= new_yoy_from else None)
            if yoy is not None and pub is not None and pub["growth_rate"] is not None and p[1] == idx[d][1]:
                if abs(yoy - pub["growth_rate"]) > 0.15:
                    errors.append(f"{key} {d}: linked y/y {yoy} vs MoSPI {pub['growth_rate']} ({idx[d][1]} base)")
        # quarterly averages (complete quarters only)
        qs = {}
        for d, (v, _) in idx.items():
            m = int(d[5:7]); qm = (m - 1) // 3 * 3 + 1
            qs.setdefault(f"{d[:4]}-{qm:02d}-01", []).append(v)
        qa = {d: sum(v) / 3 for d, v in qs.items() if len(v) == 3}
        for d in sorted(qa):
            p = qa.get(prev_year(d))
            out.append({"date": d, "freq": "Q", "series": key, "index_linked": round(qa[d], 3),
                        "yoy": round((qa[d] / p - 1) * 100, 1) if p else None,
                        "base_year": "2011-12" if d < SPLICE else "2022-23", "calculated": "y"})
    if errors:
        raise CheckFailed(errors[:40])
    return out


NIC = {"Manufacture of Food Products": ("10", "Food products"), "Manufacture of Beverages": ("11", "Beverages"),
       "Manufacture of Tobacco Products": ("12", "Tobacco products"), "Manufacture of Textiles": ("13", "Textiles"),
       "Manufacture of Wearing Apparel": ("14", "Wearing apparel"), "Manufacture of Leather and Related Products": ("15", "Leather"),
       "Manufacture of Wood and Products of Wood and Cork, Except Furniture; Manufacture of Articles of Straw and Plaiting Materials": ("16", "Wood and wood products"),
       "Manufacture of Paper and Paper Products": ("17", "Paper"), "Printing and Reproduction of Recorded Media": ("18", "Printing and recorded media"),
       "Manufacture of Coke and Refined Petroleum Products": ("19", "Coke and refined petroleum"),
       "Manufacture of Chemicals and Chemical Products": ("20", "Chemicals"),
       "Manufacture of basic pharmaceutical products and pharmaceutical preparations": ("21", "Pharmaceuticals"),
       "Manufacture of Rubber and Plastics Products": ("22", "Rubber and plastics"),
       "Manufacture of Other Non-metallic Mineral Products": ("23", "Non-metallic minerals"),
       "Manufacture of Basic Metals": ("24", "Basic metals"),
       "Manufacture of Fabricated Metal Products, Except Machinery and Equipment": ("25", "Fabricated metal products"),
       "Manufacture of Computer, Electronic and Optical Products": ("26", "Computer, electronic and optical"),
       "Manufacture of Electrical Equipment": ("27", "Electrical equipment"),
       "Manufacture of Machinery and Equipment n.e.c.": ("28", "Machinery and equipment n.e.c."),
       "Manufacture of Motor Vehicles, Trailers and Semi-trailers": ("29", "Motor vehicles"),
       "Manufacture of Other Transport Equipment": ("30", "Other transport equipment"),
       "Manufacture of Furniture": ("31", "Furniture"), "Other Manufacturing": ("32", "Other manufacturing")}


def divisions(rows):
    """Manufacturing by NIC 2-digit division, 2022-23 base, latest month: MoSPI's y/y as published, and the calendar
    year to date (January to the latest month) against the same months a year earlier, calculated as the ratio of the
    summed indices (MoSPI's method for its cumulative growth, on calendar rather than fiscal months; user, 3 Nov 2026)."""
    new = [r for r in rows if r["base_year"] == "2022-23" and r["category"] == "Manufacturing" and r["index"] is not None]
    last = max(r["date"] for r in new)
    y, m = int(last[:4]), int(last[5:7])
    out, errors = [], []
    for sub in [""] + sorted(NIC, key=lambda k: NIC[k][0]):
        s = {r["date"]: r for r in new if r["sub_category"] == sub}
        if last not in s:
            errors.append(f"IIP division {sub or 'Manufacturing'}: no {last[:7]}"); continue
        cur = [s.get(f"{y}-{k:02d}-01") for k in range(1, m + 1)]
        prev = [s.get(f"{y - 1}-{k:02d}-01") for k in range(1, m + 1)]
        if any(x is None for x in cur + prev):
            errors.append(f"IIP division {sub or 'Manufacturing'}: months missing for the year to date"); continue
        ytd = round((sum(x["index"] for x in cur) / sum(x["index"] for x in prev) - 1) * 100, 1)
        one = round((s[last]["index"] / s[f"{y - 1}{last[4:]}"]["index"] - 1) * 100, 1)
        pub = s[last]["growth_rate"]
        if pub is None or abs(one - pub) > 0.15:
            errors.append(f"IIP division {sub or 'Manufacturing'} {last[:7]}: index ratio {one} vs MoSPI y/y {pub}")
        code, short = NIC.get(sub, ("C", "Manufacturing"))
        out.append({"date": last, "nic": code, "name": short, "industry": sub or "Manufacturing", "yoy": pub, "ytd": ytd,
                    "ytd_months": f"Jan-{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} {y}",
                    "ytd_calculated": "y"})
    missing = [k for k in NIC if k not in {r["sub_category"] for r in new}]
    if missing or len(out) != 24:
        errors.append(f"IIP divisions: {len(out)} of 24 rows; not in the data: {missing[:3]}")
    if errors:
        raise CheckFailed(errors)
    return out


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    rows = fetch()
    lk = linked(rows)
    dv = divisions(rows)
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    with open(OUT / "in_iip.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["base_year"], r["type"], r["category"], r["sub_category"], r["date"])):
            w.writerow(r)
    with open(OUT / "in_iip_linked.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "freq", "series", "index_linked", "yoy", "base_year", "calculated"],
                           lineterminator="\n")
        w.writeheader()
        for r in sorted(lk, key=lambda r: (r["freq"], r["series"], r["date"])):
            w.writerow(r)
    with open(OUT / "in_iip_divisions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(dv[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(dv)
    last = max(r["date"] for r in rows if r["base_year"] == "2022-23")
    g = next(r for r in lk if r["freq"] == "M" and r["series"] == "general" and r["date"] == last)
    m = next(r for r in lk if r["freq"] == "M" and r["series"] == "manufacturing" and r["date"] == last)
    code = f"M{last[:7]}"
    label = f"{last[:7]}: IIP {g['yoy']}%, manufacturing {m['yoy']}% y/y (2022-23 base)"
    nlong = write_long(({"country": "IN", "indicator": "iip", "series": f"{r['series']}_{r['freq']}",
                         "label": f"IIP, {r['series']}, linked, y/y (calculated)", "measure": "yoy", "area": "national",
                         "freq": r["freq"], "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": "MoSPI, Index of Industrial Production (linked by Asia Decoded)", "release": code}
                        for r in lk), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_month": last}, [], len(rows),
                  {"fingerprint": fp, "linked_rows": len(lk), "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label}
