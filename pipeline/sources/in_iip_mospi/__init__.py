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


# MoSPI's IIP weights, 2022-23 base, NIC 2-digit manufacturing divisions (Statement II A of the monthly IIP release,
# e.g. August 2026, released 28 Sep 2026; manufacturing 76.062 of the general index). They reproduce the published
# manufacturing index within 0.05 points every month from April 2023 (checked in groups()).
WEIGHTS = {"10": 5.679, "11": 1.113, "12": 0.774, "13": 3.275, "14": 1.970, "15": 0.607, "16": 0.239, "17": 1.375,
           "18": 0.506, "19": 7.721, "20": 7.813, "21": 5.833, "22": 3.384, "23": 3.519, "24": 9.198, "25": 2.481,
           "26": 2.085, "27": 3.175, "28": 5.020, "29": 6.417, "30": 2.089, "31": 0.283, "32": 1.509}
# Electronics groups (user, 3 Nov 2026): electronics and electrical (NIC 26 + 27) and the rest of manufacturing.
GROUPS = {"E2627": ("Electronics and electrical (26, 27)", {"26", "27"}), "X2627": ("Non-electronics (ex 26, 27)", None)}
GROUP_START = "2023-04-01"   # 2022-23 base only (user: from April 2024 for y/y)


def groups(rows):
    """Electronics and non-electronics manufacturing IIP, 2022-23 base, calculated: weighted average of the published
    NIC 2-digit indices at MoSPI's weights (WEIGHTS) over each group's divisions; y/y from the group index (from April
    2024). Returns monthly rows {date, code, name, index, yoy}."""
    code = {k: v[0] for k, v in NIC.items()}
    by = {}
    for r in rows:
        if r["base_year"] == "2022-23" and r["category"] == "Manufacturing" and r["index"] is not None and r["date"] >= GROUP_START:
            by.setdefault(r["date"], {})[code.get(r["sub_category"], "C")] = r["index"]
    errors, out, idx = [], [], {}
    for d, v in sorted(by.items()):
        miss = [c for c in WEIGHTS if c not in v]
        if miss or "C" not in v:
            errors.append(f"IIP groups {d[:7]}: divisions missing {miss[:4]}"); continue
        calc = sum(WEIGHTS[c] * v[c] for c in WEIGHTS) / sum(WEIGHTS.values())
        if abs(calc - v["C"]) > 0.15:
            errors.append(f"IIP weights {d[:7]}: weighted divisions {calc:.2f} vs published manufacturing {v['C']}")
        for g, (name, members) in GROUPS.items():
            mem = members if members is not None else set(WEIGHTS) - GROUPS["E" + g[1:]][1]
            idx[(g, d)] = sum(WEIGHTS[c] * v[c] for c in mem) / sum(WEIGHTS[c] for c in mem)
    if errors:
        raise CheckFailed(errors[:20])
    for (g, d), x in sorted(idx.items(), key=lambda t: (t[0][0], t[0][1])):
        p = idx.get((g, f"{int(d[:4]) - 1}{d[4:]}"))
        out.append({"date": d, "code": g, "name": GROUPS[g][0], "index": round(x, 3),
                    "yoy": round((x / p - 1) * 100, 1) if p else None, "calculated": "y"})
    return out


_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def divisions(rows):
    """Manufacturing by NIC 2-digit division, 2022-23 base, latest month: MoSPI's y/y as published, and the calendar
    year to date (January to the latest month) against the same months a year earlier, calculated as the ratio of the
    summed indices (MoSPI's method for its cumulative growth, on calendar rather than fiscal months; user, 3 Nov 2026);
    and the three months to the latest against the same three months a year earlier (m3, "3mma y/y"), same method."""
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
        # three months to the latest, against the same three months a year earlier (3mma y/y; user, 3 Nov 2026)
        last3 = [d for d in sorted(s) if d <= last][-3:]
        p3 = [s.get(f"{int(d[:4]) - 1}{d[4:]}") for d in last3]
        if len(last3) < 3 or any(x is None for x in p3):
            errors.append(f"IIP division {sub or 'Manufacturing'}: no 3-month comparison"); continue
        m3 = round((sum(s[d]["index"] for d in last3) / sum(x["index"] for x in p3) - 1) * 100, 1)
        one = round((s[last]["index"] / s[f"{y - 1}{last[4:]}"]["index"] - 1) * 100, 1)
        pub = s[last]["growth_rate"]
        if pub is None or abs(one - pub) > 0.15:
            errors.append(f"IIP division {sub or 'Manufacturing'} {last[:7]}: index ratio {one} vs MoSPI y/y {pub}")
        code, short = NIC.get(sub, ("C", "Manufacturing"))
        out.append({"date": last, "nic": code, "name": short, "industry": sub or "Manufacturing", "yoy": pub,
                    "m3": m3, "m3_months": f"{_MON[int(last3[0][5:7]) - 1]}-{_MON[int(last3[-1][5:7]) - 1]} {last3[-1][:4]}", "ytd": ytd,
                    "ytd_months": f"Jan-{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} {y}",
                    "ytd_calculated": "y"})
    # electronics groups: same 3mma and YTD method, on the group indices
    gi = {}
    for r in groups(rows):
        gi.setdefault(r["code"], {})[r["date"]] = r["index"]
    for g, (name, _) in GROUPS.items():
        s = gi.get(g, {})
        cur = [s.get(f"{y}-{k:02d}-01") for k in range(1, m + 1)]
        prev = [s.get(f"{y - 1}-{k:02d}-01") for k in range(1, m + 1)]
        last3 = [d for d in sorted(s) if d <= last][-3:]
        p3 = [s.get(f"{int(d[:4]) - 1}{d[4:]}") for d in last3]
        if any(x is None for x in cur + prev + p3) or len(last3) < 3:
            errors.append(f"IIP group {g}: months missing"); continue
        out.append({"date": last, "nic": g, "name": name, "industry": name,
                    "yoy": round((s[last] / s[f"{y - 1}{last[4:]}"] - 1) * 100, 1),
                    "m3": round((sum(s[d] for d in last3) / sum(p3) - 1) * 100, 1),
                    "m3_months": f"{_MON[int(last3[0][5:7]) - 1]}-{_MON[int(last3[-1][5:7]) - 1]} {last3[-1][:4]}",
                    "ytd": round((sum(cur) / sum(prev) - 1) * 100, 1), "ytd_months": out[0]["ytd_months"], "ytd_calculated": "y"})
    missing = [k for k in NIC if k not in {r["sub_category"] for r in new}]
    if missing or len(out) != 26:
        errors.append(f"IIP divisions: {len(out)} of 26 rows; not in the data: {missing[:3]}")
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
    gr = groups(rows)
    with open(OUT / "in_iip_groups.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(gr[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(gr)
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
