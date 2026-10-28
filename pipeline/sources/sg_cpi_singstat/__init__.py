"""Singapore CPI: Department of Statistics (SingStat), 2024 base, via the Table Builder API (no key).

Writes data/sg/cpi/:
  sg_cpi.csv            headline, MAS core and its components, food, divisions, additional indicators;
                        index, m/m and y/y as published; seasonally adjusted index and m/m where SingStat
                        publishes them (no SA series exists for MAS core or its services, retail and
                        electricity & gas components, so none is made here)
  sg_cpi_contrib.csv    contributions (pp) of MAS core, accommodation and private transport to all-items y/y at
                        published weights, Jan 2015 on (calculated);
                        rows with series "core_*": contributions of food excl. serving services, food & beverage
                        serving services, services, retail & other goods and electricity & gas to MAS core y/y at MAS's published weights, Jan 2015 on
                        (2014 basket: services / retail & other goods split estimated)
  sg_cpi_diffusion.csv  share of items with prices up / down on a year earlier, Jan 2016 on
  sg_cpi_items.csv      every item, latest 12 months: published 2024 weight, index, m/m, y/y (published),
                        contribution to all-items y/y (calculated)
  sg_cpi_series_weights.csv  published 2024 basket weight (per 10,000) of all items, CPI less imputed rentals, CPI less
                        accommodation, MAS core, energy (calculated), food, divisions and groups in sg_cpi.csv
  sg_cpi_weights.json   published contribution weights by basket, published item weights
                        beside the index-implied ones, and fit residuals
                        Also in sg_cpi.csv (calculated, series "fuel"): fuel CPI = electricity, gas, petrol and other
                        fuel & lubricants for personal transport, weighted by their published 2024 weights, Jan 2024 on
                        (2024 = 100); m/m and y/y from that index

Weights: item, group, division and series weights are SingStat's published 2024 weights (Information Paper
IP-E61, kept in weights_2024.csv), summed up the tree; CPI less food and energy uses the published 2014, 2019 and
2024 weights. Contributions use published weights: SingStat's for accommodation and private transport, MAS's for MAS core and
its parts. The CPI tree identity below is used only to check the published item weights: within each basket (2014, 2019 and 2024 bases) the published
all-items index is exactly a fixed linear combination of its components; the coefficients are recovered by
least squares over that basket's months and accepted only if they reproduce the published parent index
within 0.01 index points in every month (checked below). On the 2024 base the coefficients are the 2024
weights. Item weights come from the same identity applied down the classification tree.
"""
import csv
import gzip
import hashlib
import json

from pathlib import Path

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
    ("actual_rentals", "Actual rentals for housing", "drivers", "1.03.1.1"),
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
CORE_PARTS = [("food_ex_fbss", "Food excl. food and beverage serving services"),
              ("fbss", "Food and beverage serving services"), ("services", "Services"),
              ("retail_goods", "Retail and other goods"), ("elec_gas", "Electricity and gas")]
DIVISIONS = ["1.01", "1.02", "1.03", "1.04", "1.05", "1.06", "1.07", "1.08", "1.09", "1.10", "1.11"]
DIFFUSION_START = "2016-01-01"
FUEL_ITEMS = ["1.03.2.3", "1.03.2.4", "1.06.1.5", "1.06.1.6"]  # electricity, gas, petrol, other fuel & lubricants
TOL = 0.01
VERSION = 16  # bump when the outputs change, so the next run rebuilds them


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


# Published weights per 10,000 of accommodation and private transport (2014 basket: IP-E48; 2019, restated, and 2024:
# IP-E61); MAS core (all items less both) is the remainder.
HEADLINE_WEIGHTS = {"2014": {"accommodation": 2287, "private_transport": 1149},
                    "2019": {"accommodation": 2198, "private_transport": 1221},
                    "2024": {"accommodation": 2656, "private_transport": 906}}
HEADLINE_PARTS = [("core", "MAS core"), ("accommodation", "Accommodation"), ("private_transport", "Private transport")]


def _contrib_headline(idx, mas, errors):
    """Contributions of MAS core, accommodation and private transport to all-items y/y, Jan 2015 on, at published
    weights. In each basket every index is rebased to the link month (Dec of the year before the basket starts);
    a part's contribution is weight x change in its rebased index x all items at the link month / all items a year
    earlier. Across a basket change the year is split at the link month, old weights before and new after."""
    A = idx["1"]
    P = {"core": mas["1"], "accommodation": idx["1.03.1"], "private_transport": idx["1.06.1"]}
    segs = [("2014", "2014-01-01", "2018-12-01", "2013-12-01"),
            ("2019", "2019-01-01", "2023-12-01", "2018-12-01"),
            ("2024", "2024-01-01", max(A), "2023-12-01")]
    W = {}
    for b, w in HEADLINE_WEIGHTS.items():
        W[b] = {"core": 1 - sum(w.values()) / 1e4, **{k: v / 1e4 for k, v in w.items()}}
    seg_of = lambda d: next((x for x in segs if x[1] <= d <= x[2]), None)  # noqa: E731

    def part(seg, k, x, y):
        b, _, _, L = seg
        return A[L] * W[b][k] * (P[k][y] - P[k][x]) / P[k][L]
    rows = []
    for t in sorted(A):
        s = _shift(t, -12)
        St, Ss = seg_of(t), seg_of(s)
        if t < "2015-01-01" or not St or not Ss:
            continue
        if St is Ss:
            C = {k: part(St, k, s, t) for k in P}
        else:
            C = {k: part(Ss, k, s, St[3]) + part(St, k, St[3], t) for k in P}
        C = {k: v / A[s] * 100 for k, v in C.items()}
        tot = (A[t] / A[s] - 1) * 100
        if abs(sum(C.values()) - tot) > 0.25:
            errors.append(f"contributions {t}: parts sum {sum(C.values()):.3f}, all items {tot:.3f}")
        rows.append({"date": t, "series": "all", "label": "All items", "order": 0, "contrib_yoy": round(tot, 2)})
        for i, (k, lab) in enumerate(HEADLINE_PARTS, 1):
            rows.append({"date": t, "series": k, "label": lab, "order": i, "contrib_yoy": round(C[k], 2)})
    weights = [{"from": a, "to": b, "published_weights_per_10000": {k: round(v * 1e4) for k, v in W[n].items()}}
               for n, a, b, _ in segs]
    return rows, weights


# MAS core weights per 10,000 of all items. 2019 and 2024: as published by MAS/MTI (Consumer Price Developments,
# Table A.1). 2014: MAS published none. Food (2,167) and electricity & gas (215 + 34) are SingStat's published
# weights (IP-E48); MAS core is 10,000 less accommodation (2,287) and private transport (1,149); the remaining 4,148
# is split between services and retail & other goods in the ratio implied by the published MAS core indices over
# 2014-18 (expressed at 2014 prices). The same calculation reproduces MAS's published 2019 and 2024 splits; summing
# SingStat's 2014 item weights by MAS's classification gives 2,922 and 1,226, within about 20 of these.
CORE_WEIGHTS = {"2014": {"food_ex_fbss": 774, "fbss": 1393, "services": 2939, "retail_goods": 1209, "elec_gas": 249},
                "2019": {"food_ex_fbss": 682, "fbss": 1428, "services": 3173, "retail_goods": 1111, "elec_gas": 188},
                "2024": {"food_ex_fbss": 651, "fbss": 1391, "services": 3173, "retail_goods": 1025, "elec_gas": 198}}
# Food is split into its two parts at SingStat's published weights (2014 and 2019: IP-E48, on the classification
# MAS's 2019 food weight of 2,110 uses; 2024: IP-E61); each pair sums to MAS's food weight.


def _contrib_core(idx, mas, errors):
    """Contributions of food (groceries and serving services), services, retail & other goods and electricity & gas
    to MAS core y/y, Jan 2015 on,
    at MAS's published weights (estimated split for the 2014 basket, see CORE_WEIGHTS); same method as _contrib_headline, with MAS core in place of all items."""
    A = mas["1"]
    P = {"food_ex_fbss": idx["1.01"], "fbss": idx["1.11"], "services": mas["2"], "retail_goods": mas["3"], "elec_gas": mas["4"]}
    # the services, retail & other goods and electricity & gas indices start in Jan 2014, so the 2014 basket is
    # anchored there rather than at Dec 2013
    segs = [("2014", "2014-01-01", "2018-12-01", "2014-01-01"),
            ("2019", "2019-01-01", "2023-12-01", "2018-12-01"), ("2024", "2024-01-01", max(A), "2023-12-01")]
    W = {b: {k: v / sum(w.values()) for k, v in w.items()} for b, w in CORE_WEIGHTS.items()}
    seg_of = lambda d: next((x for x in segs if x[1] <= d <= x[2]), None)  # noqa: E731

    def part(seg, k, x, y):
        b, _, _, L = seg
        return A[L] * W[b][k] * (P[k][y] - P[k][x]) / P[k][L]
    rows = []
    for t in sorted(A):
        s = _shift(t, -12)
        St, Ss = seg_of(t), seg_of(s)
        if t < "2015-01-01" or not St or not Ss:
            continue
        if St is Ss:
            C = {k: part(St, k, s, t) for k in P}
        else:
            C = {k: part(Ss, k, s, St[3]) + part(St, k, St[3], t) for k in P}
        C = {k: v / A[s] * 100 for k, v in C.items()}
        tot = (A[t] / A[s] - 1) * 100
        if abs(sum(C.values()) - tot) > 0.25:
            errors.append(f"core contributions {t}: parts sum {sum(C.values()):.3f}, MAS core {tot:.3f}")
        rows.append({"date": t, "series": "core_all", "label": "MAS core", "order": 10, "contrib_yoy": round(tot, 2)})
        for i, (k, lab) in enumerate(CORE_PARTS, 1):
            rows.append({"date": t, "series": "core_" + k, "label": lab, "order": 10 + i, "contrib_yoy": round(C[k], 2)})
    weights = [{"from": a, "to": b, "published_weights_per_10000": CORE_WEIGHTS[n]} for n, a, b, _ in segs]
    return rows, weights


# Published CPI weights per 10,000 for the items taken out of CPI less food and energy:
# 2014 basket from SingStat Information Paper IP-E48 (Appendix I); 2019 and 2024 baskets from IP-E61 (Appendix III),
# where the 2019 weights are restated on the current classification the indices use.
# The 2014 basket lists no separate weight for other fuel and lubricants.
EX_WEIGHTS = {
    "2014": {"1.01": 774, "1.03.2.3": 215, "1.03.2.4": 34, "1.06.1.5": 250},
    "2019": {"1.01": 687, "1.03.2.3": 159, "1.03.2.4": 29, "1.06.1.5": 194, "1.06.1.6": 6},
    "2024": {"1.01": 651, "1.03.2.3": 179, "1.03.2.4": 19, "1.06.1.5": 174, "1.06.1.6": 4},
}


def _ex_food_energy(idx, names, errors):
    """CPI less food (excl. serving services) and energy, Jan 2015 on. In each basket, every index is rebased to
    the link month (Jan 2015 for the first, Dec of the year before for the others) and the excluded items are
    taken out of all items at their published weights; the segments are chained at Dec 2018 and Dec 2023."""
    latest = max(idx["1"])
    segs = [("2014", "2015-01-01", "2018-12-01", "2015-01-01"),
            ("2019", "2019-01-01", "2023-12-01", "2018-12-01"),
            ("2024", "2024-01-01", latest, "2023-12-01")]
    out = {}
    for basket, a, b, link in segs:
        w = {k: v / 1e4 for k, v in EX_WEIGHTS[basket].items()}
        rest = 1 - sum(w.values())
        level = out.get(link, 100.0)
        for t in sorted(d for d in idx["1"] if a <= d <= b):
            if any(t not in idx.get(k, {}) or link not in idx.get(k, {}) for k in w):
                errors.append(f"CPI less food and energy: an excluded item is missing for {t}")
                return {}
            r = idx["1"][t] / idx["1"][link] - sum(s * idx[k][t] / idx[k][link] for k, s in w.items())
            out[t] = level * r / rest
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


WEIGHTS_2024 = Path(__file__).with_name("weights_2024.csv")


def _published_weights(implied, errors):
    """SingStat's published 2024 weights for the items (the most detailed CPI indices), summed up the tree for the
    groups and divisions. Each is checked against the weight implied by the indices: a gap of more than 5 per
    10,000 means the file is out of date (for instance after a rebasing) or mistyped."""
    lines = [l for l in WEIGHTS_2024.read_text().splitlines() if not l.startswith("#")]
    pub = {r["code"]: float(r["weight"]) / 1e4 for r in csv.DictReader(lines)}
    if abs(sum(pub.values()) - 1) > 1e-9:
        errors.append(f"published weights sum to {sum(pub.values()) * 1e4:.0f}, not 10,000")
    if set(pub) != set(implied):
        errors.append(f"published weights: items differ from the CPI tree: {sorted(set(pub) ^ set(implied))}")
    for no, w in pub.items():
        if no in implied and abs(w - implied[no]) > 5e-4:
            errors.append(f"published weight of {no} ({w * 1e4:.0f}) is far from the index-implied {implied[no] * 1e4:.1f}")
    nodes = {}
    for no, w in pub.items():
        parts = no.split(".")
        for i in range(2, len(parts) + 1):
            k = ".".join(parts[:i])
            nodes[k] = nodes.get(k, 0.0) + w
    return pub, nodes


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
    contrib, seg_weights = _contrib_headline(idx, mas, errors)
    core_contrib, core_weights = _contrib_core(idx, mas, errors)
    contrib = sorted(contrib + core_contrib, key=lambda r: (r["date"], r["order"]))
    implied, worst, _ = _tree(idx, names, errors)
    item_w, node_w = _published_weights(implied, errors)
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
    # CPI excluding food (other than food and beverage serving services) and energy, Jan 2015 on: published
    # weights for the 2014, 2019 and 2024 baskets, chained. Broadly comparable to Japan's core (less food and
    # energy, plus eating out) and India's core 1 (both keep eating out).
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
        {"baskets": seg_weights, "core_baskets": core_weights, "items_2024": {no: {"name": names[no], "weight_per_10000": round(w * 1e4), "index_implied": round(implied[no] * 1e4, 1)} for no, w in sorted(item_w.items())},
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
