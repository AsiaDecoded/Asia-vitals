"""Singapore CPI: Department of Statistics (SingStat), 2024 base, via the Table Builder API (no key).

Writes data/sg/cpi/:
  sg_cpi.csv            headline, MAS core and its components, food, divisions, additional indicators;
                        index, m/m and y/y as published; seasonally adjusted index and m/m where SingStat
                        publishes them (no SA series exists for MAS core or its services, retail and
                        electricity & gas components, so none is made here)
  sg_cpi_contrib.csv    contributions (pp) of food, services, retail & other goods, electricity & gas,
                        accommodation and private transport to all-items y/y, Jan 2015 on (calculated);
                        rows with series "core_*": contributions of the first four to MAS core y/y
  sg_cpi_diffusion.csv  share of items with prices up / down on a year earlier, Jan 2016 on
  sg_cpi_items.csv      every item, latest 12 months: 2024 weight, index, m/m, y/y (published),
                        contribution to all-items y/y (calculated)
  sg_cpi_series_weights.csv  2024 basket weight (per 10,000) of all items, CPI less imputed rentals, CPI less
                        accommodation, MAS core, energy (calculated), food, divisions and groups in sg_cpi.csv
  sg_cpi_weights.json   the effective basket weights recovered from the published indices, and fit residuals
                        Also in sg_cpi.csv (calculated, series "fuel"): fuel CPI = electricity, gas, petrol and other
                        fuel & lubricants for personal transport, weighted by their 2024 basket weights, Jan 2024 on
                        (2024 = 100); m/m and y/y from that index

Weights: SingStat publishes no weights table. Within each basket (2014, 2019 and 2024 bases) the published
all-items index is exactly a fixed linear combination of its components; the coefficients are recovered by
least squares over that basket's months and accepted only if they reproduce the published parent index
within 0.01 index points in every month (checked below). On the 2024 base the coefficients are the 2024
weights. Item weights come from the same identity applied down the classification tree.
"""
import csv
import gzip
import hashlib
import json

import numpy as np

from core import singstat
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "sg_cpi_singstat"
DESCRIPTION = "Singapore CPI, MAS core, contributions and diffusion (SingStat, 2024 base)"
OUT = DATA / "sg" / "cpi"
RAWDIR = RAW / "sg" / "cpi_singstat"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON = {m: i + 1 for i, m in enumerate(MONTHS)}

T = {"index": "M213751", "index_sa": "M213752", "yoy": "M213781", "mom": "M213771",
     "mom_sa": "M213792", "mas": "M213891"}

# key, label, group, CPI seriesNo (tables M213751/M213771/M213781 and, if SA, M213752/M213792)
CPI = [
    ("all", "All items", "headline", "1"),
    ("less_accom", "All items less accommodation", "headline", "2"),
    ("less_imputed", "All items less imputed rentals for housing", "headline", "3"),
    ("food", "Food", "drivers", "1.0"),
    ("food_ex_fbss", "Food excl. food and beverage serving services", "drivers", "1.01"),
    ("fbss", "Food and beverage serving services", "drivers", "1.11"),
    ("accommodation", "Accommodation", "drivers", "1.03.1"),
    ("imputed_rentals", "Imputed rentals for housing", "drivers", "1.03.1.2"),
    ("private_transport", "Private transport", "drivers", "1.06.1"),
    ("petrol", "Petrol", "drivers", "1.06.1.5"),
    ("electricity", "Electricity", "drivers", "1.03.2.3"),
    ("gas", "Gas", "drivers", "1.03.2.4"),
    ("other_fuels", "Other fuel and lubricants for personal transport", "drivers", "1.06.1.6"),
    ("clothing", "Clothing and footwear", "groups", "1.02"),
    ("housing", "Housing and utilities", "groups", "1.03"),
    ("household", "Household durables and services", "groups", "1.04"),
    ("health", "Health", "groups", "1.05"),
    ("transport", "Transport", "groups", "1.06"),
    ("info_comm", "Information and communication", "groups", "1.07"),
    ("recreation", "Recreation, sport and culture", "groups", "1.08"),
    ("education", "Education", "groups", "1.09"),
    ("misc", "Miscellaneous goods and services", "groups", "1.10"),
]
# MAS measures (table M213891): index row, m/m row, y/y row. NSA only.
MAS = [
    ("core", "MAS core inflation measure", "headline", "1", "1.1", "1.2"),
    ("services", "Services", "core_parts", "2", "2.1", "2.2"),
    ("retail_goods", "Retail and other goods", "core_parts", "3", "3.1", "3.2"),
    ("elec_gas", "Electricity and gas", "core_parts", "4", "4.1", "4.2"),
]
# Baskets: (first month, last month or None). Each is a fixed-weight segment of the published index.
BASKETS = [("2014-01-01", "2018-12-01"), ("2019-01-01", "2023-12-01"), ("2024-01-01", None)]
CONTRIB_PARTS = [("food", "Food"), ("services", "Services"), ("retail_goods", "Retail and other goods"),
                 ("elec_gas", "Electricity and gas"), ("accommodation", "Accommodation"),
                 ("private_transport", "Private transport")]
CORE_PARTS = CONTRIB_PARTS[:4]  # food, services, retail & other goods, electricity & gas
DIVISIONS = ["1.01", "1.02", "1.03", "1.04", "1.05", "1.06", "1.07", "1.08", "1.09", "1.10", "1.11"]
DIFFUSION_START = "2016-01-01"
FUEL_ITEMS = ["1.03.2.3", "1.03.2.4", "1.06.1.5", "1.06.1.6"]  # electricity, gas, petrol, other fuel & lubricants
TOL = 0.01
VERSION = 9  # bump when the outputs change, so the next run rebuilds them


def _date(key):
    y, m = key.split()
    return f"{y}-{MON[m]:02d}-01"


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _series(tbl):
    """{seriesNo: {date: value}} and {seriesNo: name}"""
    out, names = {}, {}
    for r in tbl["rows"]:
        names[r["seriesNo"]] = r["rowText"]
        out[r["seriesNo"]] = {_date(c["key"]): _num(c["value"]) for c in r["columns"] if _num(c["value"]) is not None}
    return out, names


def _lstsq(parent, kids, months):
    X = np.array([[k[d] for k in kids] for d in months])
    y = np.array([parent[d] for d in months])
    c, *_ = np.linalg.lstsq(X, y, rcond=None)
    return c, float(np.abs(X @ c - y).max())


def _contrib(idx, mas, errors, core=False):
    """Contributions to y/y. All items (core=False): parts are MAS core (food, services, retail & other goods,
    electricity & gas) + accommodation + private transport. MAS core (core=True): its four parts.
    Core rows carry series names prefixed "core_"."""
    parts = {"food": idx["1.0"], "services": mas["2"], "retail_goods": mas["3"], "elec_gas": mas["4"],
             "accommodation": idx["1.03.1"], "private_transport": idx["1.06.1"]}
    spec = CORE_PARTS if core else CONTRIB_PARTS
    keys = [k for k, _ in spec]
    A = mas["1"] if core else idx["1"]
    pre = "core_" if core else ""
    latest = max(A)
    segs = []
    for a, b in BASKETS:
        b = b or latest
        months = sorted(d for d in A if a <= d <= b and all(d in parts[k] for k in keys))
        c, res = _lstsq(A, [parts[k] for k in keys], months)
        if res > TOL or (c < 0).any():
            errors.append(f"{pre}contributions: basket from {a} not reproduced (max residual {res:.4f}, coefs {np.round(c, 4).tolist()})")
        segs.append((a, b, dict(zip(keys, c)), res))
    seg_of = lambda d: next((s for s in segs if s[0] <= d <= s[1]), None)  # noqa: E731
    rows, out = [], []
    for t in sorted(A):
        s = _shift(t, -12)
        St, Ss = seg_of(t), seg_of(s)
        if not St or not Ss or s not in A:
            continue
        I = {k: parts[k] for k in keys}
        if St is Ss:
            C = {k: St[2][k] * (I[k][t] - I[k][s]) / A[s] * 100 for k in keys}
        else:
            J = St[0]
            L = _shift(J, -1)
            old, new = Ss[2], St[2]
            step = A[J] - A[L]
            newstep = sum(new[k] * (I[k][J] - I[k][L]) for k in keys)
            gap = step - newstep  # linking residual at the basket change, spread by weight
            C = {}
            for k in keys:
                b = new[k] * (I[k][J] - I[k][L]) + gap * new[k] * I[k][J] / A[J]
                C[k] = (old[k] * (I[k][L] - I[k][s]) + b + new[k] * (I[k][t] - I[k][J])) / A[s] * 100
        tot = (A[t] / A[s] - 1) * 100
        if abs(sum(C.values()) - tot) > 0.01:  # indices are published to 3 decimals
            errors.append(f"{pre}contributions {t}: parts sum {sum(C.values()):.4f}, all items {tot:.4f}")
        out.append((t, round(tot, 2), {k: round(v, 2) for k, v in C.items()}))
    for t, tot, C in out:
        rows.append({"date": t, "series": pre + "all", "label": "MAS core" if core else "All items", "order": 10 if core else 0, "contrib_yoy": tot})
        for i, (k, lab) in enumerate(spec, 1):
            rows.append({"date": t, "series": pre + k, "label": lab, "order": (10 if core else 0) + i, "contrib_yoy": C[k]})
    weights = [{"from": a, "to": b, "max_residual": round(res, 5), "weights_per_10000": {k: round(v * 1e4, 1) for k, v in c.items()}}
               for a, b, c, res in segs]
    return rows, weights


def _path_coef(idx, names, no, months):
    """Coefficient of series `no` in all items over `months`, multiplying parent->child shares down the tree."""
    parts = no.split(".")
    chain = [".".join(parts[:i]) for i in range(2, len(parts) + 1)]
    c, worst, parent = 1.0, 0.0, "1"
    for node in chain:
        if parent == "1":
            kids = DIVISIONS
        else:
            depth = parent.count(".") + 1
            kids = [n for n in names if n.startswith(parent + ".") and n.count(".") == depth
                    and all(t in idx.get(n, {}) for t in months)]
        k, r = _lstsq(idx[parent], [idx[x] for x in kids], months)
        worst = max(worst, r)
        c *= dict(zip(kids, k))[node]
        parent = node
    return c, worst


PETROL_W2019 = 194  # per 10,000, 2019-based CPI (SingStat IP-E48, Appendix I)


def _ex_food_energy(idx, names, errors):
    latest = max(idx["1"])
    segs = []
    for a, b in (("2019-01-01", "2023-12-01"), ("2024-01-01", latest)):
        months = sorted(d for d in idx["1"] if a <= d <= b)
        cd, worst = _lstsq(idx["1"], [idx[x] for x in DIVISIONS], months)
        ck = {}
        for n in ["1.01", "1.03.2.3", "1.03.2.4"] + (["1.06.1.5", "1.06.1.6"] if a >= "2024" else []):
            c, r = _path_coef(idx, names, n, months)
            ck[n], worst = c, max(worst, r)
        if a < "2024":
            ref = lambda s: sum(s[f"2019-{m:02d}-01"] for m in range(1, 13)) / 12  # noqa: E731
            ck["1.06.1.5"] = PETROL_W2019 / 1e4 * ref(idx["1"]) / ref(idx["1.06.1.5"])
        if worst > TOL or any(v < 0 for v in ck.values()):
            errors.append(f"CPI less food and energy: basket from {a} not reproduced (residual {worst:.4f})")
        segs.append((months, cd, ck))

    def level(cd, ck, t):
        return sum(c * idx[x][t] for c, x in zip(cd, DIVISIONS)) - sum(c * idx[n][t] for n, c in ck.items())
    out = {}
    for i, (months, cd, ck) in enumerate(segs):
        seg = {t: level(cd, ck, t) for t in months}
        if i:
            L = _shift(months[0], -1)
            f = out[L] / level(cd, ck, L)
            seg = {t: v * f for t, v in seg.items()}
        out.update(seg)
    # express on 2024 = 100
    base = sum(out[f"2024-{m:02d}-01"] for m in range(1, 13)) / 12
    return {t: v / base * 100 for t, v in out.items()}


def _tree(idx, names, errors):
    """Item weights on the 2024 basket: the identity parent = sum(coef * child) solved node by node."""
    start = BASKETS[-1][0]
    months = sorted(d for d in idx["1"] if d >= start)
    nos = list(names)

    def kids(p):
        if p == "1":
            return DIVISIONS
        depth = p.count(".") + 1
        return [n for n in nos if n.startswith(p + ".") and n.count(".") == depth
                and all(d in idx.get(n, {}) for d in months)]

    coef, worst = {"1": 1.0}, 0.0

    def walk(p):
        nonlocal worst
        ch = kids(p)
        if not ch:
            return
        c, res = _lstsq(idx[p], [idx[k] for k in ch], months)
        worst = max(worst, res)
        if res > TOL or (c < -1e-6).any():
            errors.append(f"item weights: {p} {names.get(p)} not reproduced by its children (residual {res:.4f})")
        for k, v in zip(ch, c):
            coef[k] = coef[p] * float(v)
            walk(k)
    walk("1")
    leaves = {k: v for k, v in coef.items() if k != "1" and not kids(k)}
    if abs(sum(leaves.values()) - 1) > 0.001:
        errors.append(f"item weights sum to {sum(leaves.values()):.4f}, not 1")
    return leaves, worst, coef


def _diffusion(yoy, names):
    cand = [n for n in names if n.startswith("1.") and n != "1.0"]
    desc = {n: [k for k in cand if k != n and k.startswith(n + ".")] for n in cand}
    dates = sorted(d for d in yoy.get("1", {}) if d >= DIFFUSION_START)
    rows = []
    for d in dates:
        have = {n for n in cand if d in yoy.get(n, {})}
        items = [n for n in have if not any(k in have for k in desc[n])]
        up = sum(1 for n in items if yoy[n][d] > 0)
        down = sum(1 for n in items if yoy[n][d] < 0)
        n = len(items)
        rows.append({"date": d, "items": n, "rising": up, "falling": down, "unchanged": n - up - down,
                     "share_rising": round(up / n * 100, 1), "share_falling": round(down / n * 100, 1),
                     "diffusion": round((up - down) / n * 100, 1)})
    return rows


def _checks(S, latest, state):
    errors = []
    idx, yoy, mom = S["index"][0], S["yoy"][0], S["mom"][0]
    for key, lab, grp, no in CPI:
        if latest not in idx.get(no, {}):
            errors.append(f"{key} index missing for {latest}")
    for key, *_ in MAS:
        pass
    mas = S["mas"][0]
    for key, lab, grp, i, m, y in MAS:
        if latest not in mas.get(i, {}) or latest not in mas.get(y, {}):
            errors.append(f"MAS {key} index or y/y missing for {latest}")
    for no in ("1", "1.0", "2", "3"):
        if latest not in S["index_sa"][0].get(no, {}) or latest not in S["mom_sa"][0].get(no, {}):
            errors.append(f"seasonally adjusted {no} missing for {latest}")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    # published y/y and m/m match the index (rates are computed by SingStat from unrounded indices: ±0.15pp)
    for key, lab, grp, no in CPI:
        s = idx.get(no, {})
        for d, v in yoy.get(no, {}).items():
            p = s.get(_shift(d, -12))
            if p and d in s and d >= "2015-01-01" and abs((s[d] / p - 1) * 100 - v) > 0.15:
                errors.append(f"{key} y/y {d}: published {v}, from index {(s[d] / p - 1) * 100:.2f}")
        for d, v in mom.get(no, {}).items():
            p = s.get(_shift(d, -1))
            if p and d in s and d >= "2015-01-01" and abs((s[d] / p - 1) * 100 - v) > 0.15:
                errors.append(f"{key} m/m {d}: published {v}, from index {(s[d] / p - 1) * 100:.2f}")
    for no, s in idx.items():
        for d, v in s.items():
            if not 0 < v < 1000:
                errors.append(f"index {no} {d} = {v} out of range")
    return errors[:60]


def _write_csv(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    metas = {k: singstat.metadata(t) for k, t in T.items()}
    stamp = json.dumps({"v": VERSION, **{k: [m.get("dataLastUpdated"), m.get("endPeriod")] for k, m in metas.items()}}, sort_keys=True)
    fingerprint = hashlib.sha256(stamp.encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    raw = {k: singstat.table(t) for k, t in T.items()}
    S = {k: _series(v) for k, v in raw.items()}
    latest = max(S["index"][0]["1"])
    errors = _checks(S, latest, state)
    idx, names = S["index"][0], S["index"][1]
    mas = S["mas"][0]
    contrib, seg_weights = _contrib(idx, {k: mas[k] for k in ("1", "2", "3", "4")}, errors)
    core_contrib, core_weights = _contrib(idx, {k: mas[k] for k in ("1", "2", "3", "4")}, errors, core=True)
    contrib = sorted(contrib + core_contrib, key=lambda r: (r["date"], r["order"]))
    item_w, worst, node_w = _tree(idx, names, errors)
    diff = _diffusion(S["yoy"][0], names)
    missing = [no for no in FUEL_ITEMS if no not in item_w]
    if missing:
        errors.append(f"fuel CPI: items {missing} have no 2024 weight")
    if diff and diff[-1]["items"] < 120:
        errors.append(f"diffusion: only {diff[-1]['items']} items in {diff[-1]['date']}")
    if errors:
        raise CheckFailed(errors)

    code = f"C{latest[:7]}"
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(raw, ensure_ascii=False).encode()))

    # main CPI file
    rows = []
    isa, msa = S["index_sa"][0], S["mom_sa"][0]
    order = 0
    for key, lab, grp, no in CPI:
        for d in sorted(idx.get(no, {})):
            rows.append({"date": d, "area": "national", "series": key, "label": lab, "group": grp, "order": order,
                         "index": idx[no][d], "mom": S["mom"][0].get(no, {}).get(d), "yoy": S["yoy"][0].get(no, {}).get(d)})
        order += 1
    for key, lab, grp, i, m, y in MAS:
        for d in sorted(mas.get(i, {})):
            rows.append({"date": d, "area": "national", "series": key, "label": lab, "group": grp, "order": order,
                         "index": mas[i][d], "mom": mas.get(m, {}).get(d), "yoy": mas.get(y, {}).get(d)})
        order += 1
    for key, lab, grp, no in CPI:
        if no not in isa:
            continue
        for d in sorted(isa[no]):
            rows.append({"date": d, "area": "national", "series": key + "_sa", "label": lab + ", seasonally adjusted",
                         "group": "sa", "order": order, "index": isa[no][d], "mom": msa.get(no, {}).get(d), "yoy": None})
        order += 1
    # fuel CPI (calculated) on the 2024 basket
    fw = {no: item_w[no] for no in FUEL_ITEMS}
    fuel = {}
    for d in sorted(idx["1"]):
        if d < BASKETS[-1][0] or any(d not in idx.get(no, {}) for no in FUEL_ITEMS):
            continue
        fuel[d] = sum(w * idx[no][d] for no, w in fw.items()) / sum(fw.values())
    for d in sorted(fuel):
        pm, py = fuel.get(_shift(d, -1)), fuel.get(_shift(d, -12))
        rows.append({"date": d, "area": "national", "series": "fuel",
                     "label": "Fuel (electricity, gas, petrol, other fuels; calculated)", "group": "drivers", "order": order,
                     "index": round(fuel[d], 3), "mom": round((fuel[d] / pm - 1) * 100, 1) if pm else None,
                     "yoy": round((fuel[d] / py - 1) * 100, 1) if py else None})
    order += 1
    # CPI excluding food (other than food and beverage serving services) and energy: Jan 2019 on, the 2019 and
    # 2024 baskets linked at Dec 2023. In each basket: all items (as the weighted divisions) less the weighted
    # groceries and energy indices. Weights come from the index identities, except petrol on the 2019 basket,
    # whose item weight is SingStat's published one (Information Paper IP-E48: 194 per 10,000), because the
    # other private-transport items have no history before 2024 to solve it from. Broadly comparable to Japan's
    # core (less food and energy, plus eating out) and India's core 1 (both keep eating out).
    ex = _ex_food_energy(idx, names, errors)
    for d in sorted(ex):
        pm, py = ex.get(_shift(d, -1)), ex.get(_shift(d, -12))
        rows.append({"date": d, "area": "national", "series": "ex_food_energy",
                     "label": "CPI less food (excl. serving services) and energy (calculated)", "group": "headline", "order": order,
                     "index": round(ex[d], 3), "mom": round((ex[d] / pm - 1) * 100, 1) if pm else None,
                     "yoy": round((ex[d] / py - 1) * 100, 1) if py else None})
    order += 1
    rows.sort(key=lambda r: (r["date"], r["order"]))
    _write_csv(OUT / "sg_cpi.csv", ["date", "area", "series", "label", "group", "order", "index", "mom", "yoy"], rows)

    # 2024 basket weights (per 10,000) of the headline series, divisions and calculated measures
    W = {"all": 1.0, "less_imputed": 1 - node_w["1.03.1.2"], "less_accom": 1 - node_w["1.03.1"],
         "core": 1 - node_w["1.03.1"] - node_w["1.06.1"], "fuel": sum(item_w[no] for no in FUEL_ITEMS),
         "food": node_w["1.01"] + node_w["1.11"],
         "ex_food_energy": 1 - node_w["1.01"] - sum(item_w[no] for no in FUEL_ITEMS)}
    for key, lab, grp, no in CPI:
        if key not in W and no in node_w:
            W[key] = node_w[no]
    labels = {k: lab for k, lab, *_r in CPI}
    labels.update({"core": "MAS core inflation measure", "fuel": "Energy (calculated)", "ex_food_energy": "CPI less food (excl. serving services) and energy (calculated)"})
    _write_csv(OUT / "sg_cpi_series_weights.csv", ["series", "label", "weight"],
               [{"series": k, "label": labels.get(k, k), "weight": round(v * 1e4, 1)} for k, v in W.items()])
    _write_csv(OUT / "sg_cpi_contrib.csv", ["date", "series", "label", "order", "contrib_yoy"], contrib)
    _write_csv(OUT / "sg_cpi_diffusion.csv", ["date", "items", "rising", "falling", "unchanged",
                                              "share_rising", "share_falling", "diffusion"], diff)

    # items, latest 12 months, with contributions on the 2024 basket
    A = idx["1"]
    months = sorted(A)[-12:]
    items = []
    for no, w in sorted(item_w.items()):
        for d in months:
            v, p = idx.get(no, {}).get(d), idx.get(no, {}).get(_shift(d, -12))
            c = w * (v - p) / A[_shift(d, -12)] * 100 if v is not None and p is not None and _shift(d, -12) >= BASKETS[-1][0] else None
            items.append({"date": d, "code": no, "name": names[no], "weight": round(w * 1e4, 1), "index": v,
                          "mom": S["mom"][0].get(no, {}).get(d), "yoy": S["yoy"][0].get(no, {}).get(d),
                          "contrib_yoy": None if c is None else round(c, 3)})
    _write_csv(OUT / "sg_cpi_items.csv", ["date", "code", "name", "weight", "index", "mom", "yoy", "contrib_yoy"], items)
    (OUT / "sg_cpi_weights.json").write_text(json.dumps(
        {"baskets": seg_weights, "core_baskets": core_weights, "items_2024": {no: {"name": names[no], "weight_per_10000": round(w * 1e4, 2)} for no, w in sorted(item_w.items())},
         "item_tree_max_residual": round(worst, 5)}, ensure_ascii=False, indent=1) + "\n")

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2024 = 100"), ("mom", "%"), ("yoy", "%")):
                yield {"country": "SG", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Singapore Department of Statistics", "release": code}
        for r in contrib:
            yield {"country": "SG", "indicator": "cpi_contrib", "series": r["series"], "label": r["label"],
                   "measure": "contrib_yoy", "area": "national", "freq": "M", "date": r["date"], "value": r["contrib_yoy"],
                   "unit": "pp", "source": "Singapore Department of Statistics; Asia Decoded calculation", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    release = {"code": code, "label": label, "latest_month": latest,
               "table": "SingStat Table Builder " + ", ".join(T.values()) + " (2024 base)"}
    write_release(OUT, release, [], len(rows), {"fingerprint": fingerprint, "long_rows": nlong,
                                                "contrib_rows": len(contrib), "diffusion_items": diff[-1]["items"]})
    return {"updated": True, "code": code,
            "summary": f"{label}: {len(rows)} CPI rows, contributions from {contrib[0]['date'][:7]}, {diff[-1]['items']} items"}
