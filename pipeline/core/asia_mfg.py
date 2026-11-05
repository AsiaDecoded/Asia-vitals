"""Asia Manufacturing tab: one comparable table of manufacturing production and GVA for the Asia dashboard
(asked for 4 Nov 2026; definitions and decisions in the project doc claude/asia-mfg-definitions.md).

Reads files already in the repo, calculates the same rates the same way for every economy, fetches nothing:
  - data/asia/mfg/src_iip.csv, src_gva.csv (source mfg_asia: Japan, Korea, Taiwan, Malaysia, Singapore, Hong Kong)
  - India      data/in/iip/in_iip.csv (2022-23 base), in_iip_contrib_items.csv (weights); data/in/gdp/in_gdp.csv
  - Thailand   data/th/mpi/th_mpi.csv (2021 base, OIE weights); data/th/gdp/th_gdp.csv
  - Vietnam    data/vn/gdp/vn_iip.csv (quarterly y/y as published); data/vn/gdp/vn_gdp.csv
  - Philippines data/ph/mfg/ph_vopi.csv (2018 base); data/ph/gdp/ph_gdp.csv
  - Indonesia  data/id/gdp/id_gdp_industry.csv (GVA only; its production index has no source yet)

Industries (ISIC Rev. 4): mfg, 19 refined petroleum, 20 chemicals, 21 pharmaceuticals, 23 non-metallic minerals,
24 basic metals, 26, 27, elec, nonelec. Electronics = ISIC 26, computer, electronic and optical products, the usual
international definition (decision 5 Nov 2026; electrical equipment, 27, is not electronics): division 26 as published
(Japan: 電子部品・デバイス + 情報通信機械 at METI's weights; Singapore: EDB's Electronics cluster). Non-electronics =
manufacturing less 26, at the agency's published weights (India: MoSPI's; Thailand: OIE's; Japan: METI's); blank where
no weights are published.

Calculated (all flagged): y/y = index / index a year earlier - 1 where not published; m3 = plain average of the latest
three monthly y/y (latest quarter's y/y for quarterly economies); ytd = calendar year to date, average index January to
the latest month / the same months a year earlier - 1; electronics groups; GVA shares where only levels are published.

Writes data/asia/mfg_tab/:
  asia_mfg_iip.csv     economy, name, freq, date, industry, index, yoy, yoy_calculated
  asia_mfg_latest.csv  economy, name, industry, freq, date, yoy, yoy_prev, m3, ytd, ytd_months, note
  asia_mfg_gva.csv     economy, name, freq, period, real_yoy, share, share_4q (average of the latest four quarters)
  asia_mfg_gva_annual.csv  economy, name, year, quarters, ytd, real_yoy, basis: calendar-year real growth of
                       manufacturing GVA, sum of the year's real quarterly levels / the same quarters a year earlier - 1
                       (calculated; asked for 5 Nov 2026), within one price base only; the latest year with fewer than four
                       quarters is year to date (ytd = y, quarters e.g. Q1-Q3). Vietnam: NSO's annual and cumulative
                       y/y as published (its real levels are not one consistent series; basis published). China: NBS's
                       cumulative y/y as published (no real levels published).
  release.json, release_row.json (code T<hash>)
"""
import csv
import hashlib
import json

from core.common import DATA, read_json, write_release

OUT = DATA / "asia" / "mfg_tab"
NAMES = {"JP": "Japan", "KR": "South Korea", "TW": "Taiwan", "CN": "China", "HK": "Hong Kong", "IN": "India",
         "ID": "Indonesia", "TH": "Thailand", "MY": "Malaysia", "SG": "Singapore", "PH": "Philippines", "VN": "Vietnam"}
INDS = ["mfg", "elec", "nonelec", "19", "20", "21", "23", "24", "26", "27"]


def f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def rd(path):
    p = DATA / path
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def r(eco, freq, date, ind, index, yoy=None, calc=""):
    return {"economy": eco, "freq": freq, "date": date, "industry": ind, "index": index, "yoy": yoy, "yoy_calculated": calc}


# ---------- production indices ----------
def india():
    out = []
    names = {"": "mfg", "Manufacture of Coke and Refined Petroleum Products": "19",
             "Manufacture of Chemicals and Chemical Products": "20",
             "Manufacture of basic pharmaceutical products and pharmaceutical preparations": "21",
             "Manufacture of Other Non-metallic Mineral Products": "23", "Manufacture of Basic Metals": "24",
             "Manufacture of Computer, Electronic and Optical Products": "26", "Manufacture of Electrical Equipment": "27"}
    for x in rd("in/iip/in_iip.csv"):
        if x["base_year"] == "2022-23" and x["category"] == "Manufacturing" and x["sub_category"] in names:
            out.append(r("IN", "M", x["date"], names[x["sub_category"]], f(x["index"])))
    # rest = manufacturing less divisions 26 and 27 at MoSPI's 2022-23 weights (% of the general index)
    w = {}
    for x in rd("in/iip/in_iip_contrib_items.csv"):
        w[x["code"]] = f(x["weight"])
    wm = sum(v for k, v in w.items() if k.isdigit() and 10 <= int(k) <= 33)
    ix = {(x["industry"], x["date"]): x["index"] for x in out}
    for (k, d), v in list(ix.items()):
        if k == "mfg" and ix.get(("26", d)) is not None and ix.get(("27", d)) is not None and v is not None:
            out.append(r("IN", "M", d, "nonelec", round((wm * v - w["26"] * ix[("26", d)] - w["27"] * ix[("27", d)]) / (wm - w["26"] - w["27"]), 3)))
    return out


def thailand():
    out, w, ix = [], {}, {}
    for x in rd("th/mpi/th_mpi.csv"):
        if x["base"] != "2021" or x["freq"] != "M" or x["measure"] != "index":
            continue
        ix.setdefault(x["code"], {})[x["date"]] = f(x["value"])
        if x["weight"]:
            w[x["code"]] = f(x["weight"])
    m = {"all": "mfg", "19": "19", "20": "20", "21": "21", "23": "23", "24": "24", "26": "26", "27": "27"}
    for c, k in m.items():
        for d, v in ix.get(c, {}).items():
            out.append(r("TH", "M", d, k, v))
    for d in ix.get("all", {}):
        a, b, t = ix["26"].get(d), ix["27"].get(d), ix["all"][d]
        if None in (a, b, t):
            continue
        out.append(r("TH", "M", d, "nonelec", round((w["all"] * t - w["26"] * a - w["27"] * b) / (w["all"] - w["26"] - w["27"]), 3)))
    return out


def vietnam():
    out = []
    m = {"c": "mfg", "c19": "19", "c20": "20", "c21": "21", "c23": "23", "c24": "24", "c26": "26", "c27": "27"}
    for x in rd("vn/gdp/vn_iip.csv"):
        if x["code"] in m and x["period"].endswith(("Q1", "Q2", "Q3", "Q4")):
            q = int(x["period"][-1])
            out.append(r("VN", "Q", f"{x['period'][:4]}-{3 * q - 2:02d}-01", m[x["code"]], None, f(x["rate"])))
    return out


def philippines():
    out = []
    m = {"C": "mfg", "C19": "19", "C20": "20", "C21": "21", "C23": "23", "C24": "24", "C26": "26", "C27": "27"}
    for x in rd("ph/mfg/ph_vopi.csv"):
        if x["base"] == "2018" and x["code"] in m:
            out.append(r("PH", "M", x["date"], m[x["code"]], f(x["index"]), f(x["yoy"])))
    return out


def from_src():
    out = []
    for x in rd("asia/mfg/src_iip.csv"):
        out.append(r(x["economy"], x["freq"], x["date"], x["industry"], f(x["index"]), f(x["yoy"]), x["yoy_calculated"]))
    return out


def fill_yoy(rows):
    ix = {(x["economy"], x["freq"], x["industry"], x["date"]): x["index"] for x in rows if x["index"] is not None}
    for x in rows:
        if x["yoy"] is None and x["index"] is not None:
            b = ix.get((x["economy"], x["freq"], x["industry"], f"{int(x['date'][:4]) - 1}{x['date'][4:]}"))
            if b:
                x["yoy"], x["yoy_calculated"] = round((x["index"] / b - 1) * 100, 2), "y"
    return rows


def latest(rows):
    by = {}
    for x in rows:
        by.setdefault((x["economy"], x["industry"], x["freq"]), {})[x["date"]] = x
    out = []
    for (e, ind, fr), s in by.items():
        ds = [d for d in sorted(s) if s[d]["yoy"] is not None]
        if not ds:
            continue
        d = ds[-1]
        prev = s[ds[-2]]["yoy"] if len(ds) > 1 else None
        if fr == "M":
            mi = lambda x: int(x[:4]) * 12 + int(x[5:7])  # noqa: E731
            m3 = round(sum(s[x]["yoy"] for x in ds[-3:]) / 3, 2) if len(ds) >= 3 and mi(d) - mi(ds[-3]) == 2 else None
        else:
            m3 = s[d]["yoy"]
        ytd, n = None, 0
        months = [x for x in s if x[:4] == d[:4] and x <= d]
        if fr == "M":
            cur = [s[x]["index"] for x in months]
            prv = [s.get(f"{int(x[:4]) - 1}{x[4:]}", {}).get("index") for x in months]
            if cur and None not in cur and None not in prv:
                ytd, n = round((sum(cur) / sum(prv) - 1) * 100, 2), len(months)
        out.append({"economy": e, "name": NAMES[e], "industry": ind, "freq": fr, "date": d, "yoy": s[d]["yoy"], "yoy_prev": prev,
                    "m3": m3, "ytd": ytd, "ytd_months": n or "", "note": ""})
    return sorted(out, key=lambda x: (x["economy"], INDS.index(x["industry"]) if x["industry"] in INDS else 99))


# ---------- GVA ----------
def qlabel(date_first_month):
    return f"{date_first_month[:4]}-Q{(int(date_first_month[5:7]) - 1) // 3 + 1}"


def gva():
    out = []
    # India: quarterly, 2022-23 base (dates are the first month of the calendar quarter)
    q = {}
    for x in rd("in/gdp/in_gdp.csv"):
        if x["freq"] == "Q" and x["base_year"] == "2022-23" and x["code"] in ("manufacturing", "gdp"):
            q.setdefault(x["date"], {})[(x["code"], x["measure"], x["price"])] = f(x["value"])
    for d, v in sorted(q.items()):
        sh = v.get(("manufacturing", "level", "current")), v.get(("gdp", "level", "current"))
        out.append({"economy": "IN", "freq": "Q", "period": qlabel(d), "real_yoy": v.get(("manufacturing", "yoy", "constant")),
                    "share": round(sh[0] / sh[1] * 100, 2) if all(sh) else None,
                    "real_level": v.get(("manufacturing", "level", "constant")), "price": "2022-23"})
    # Thailand: quarterly, NESDC (cvm 2002), share as calculated by th_gdp_nesdc
    q = {}
    for x in rd("th/gdp/th_gdp.csv"):
        if x["code"] == "manufacturing" and x["span"] == "Q":
            q.setdefault(x["period"], {})[(x["measure"], x["price"])] = f(x["value"] if x["measure"] == "level" else x["rate"])
    for p, v in sorted(q.items()):
        out.append({"economy": "TH", "freq": "Q", "period": p, "real_yoy": v.get(("yoy", "cvm_2002")), "share": v.get(("share", "current")),
                    "real_level": v.get(("level", "cvm_2002")), "price": "cvm_2002"})
    # Vietnam
    q = {}
    for x in rd("vn/gdp/vn_gdp.csv"):
        if x["code"] == "manufacturing" and x["span"] == "Q":
            q.setdefault(x["period"], {})[(x["measure"], x["price"])] = x
    for p, v in sorted(q.items()):
        ry = v.get(("yoy", "constant_2020"))
        sh = v.get(("share", "current"))
        lv = v.get(("level", "constant_2020")) or v.get(("level", "constant_2010"))
        out.append({"economy": "VN", "freq": "Q", "period": p, "real_yoy": f(ry["rate"]) if ry else None,
                    "share": f(sh["value"]) if sh else None,
                    "real_level": f(lv["value"]) if lv else None, "price": lv["price"] if lv else None})
    # Philippines
    q = {}
    for x in rd("ph/gdp/ph_gdp.csv"):
        if x["code"] == "manufacturing" and x["period"][5:6] == "Q":
            q.setdefault(x["period"], {})[(x["measure"], x["price"])] = f(x["value"])
    for p, v in sorted(q.items()):
        out.append({"economy": "PH", "freq": "Q", "period": p, "real_yoy": v.get(("yoy", "constant_2018")), "share": v.get(("share", "current")),
                    "real_level": v.get(("level", "constant_2018")), "price": "constant_2018"})
    # Indonesia
    for x in rd("id/gdp/id_gdp_industry.csv"):
        if x["code"] == "13000":
            out.append({"economy": "ID", "freq": "Q", "period": qlabel(x["date"]), "real_yoy": f(x["real_yoy"]), "share": f(x["share_nominal"]),
                        "real_level": f(x["real_level"]), "price": "constant_2010"})
    for x in rd("asia/mfg/src_gva.csv"):
        out.append({"economy": x["economy"], "freq": x["freq"], "period": x["period"], "real_yoy": f(x["real_yoy"]), "share": f(x["share"]),
                    "real_level": f(x.get("real_level")), "price": "source", "cum_yoy": f(x.get("cum_yoy"))})
    for x in out:
        x["name"] = NAMES[x["economy"]]
    out.sort(key=lambda x: (x["economy"], x["freq"], x["period"]))
    # Quarterly shares are seasonal (e.g. the Philippines 17.0% in Q1 2026, 13.3% in Q2): share_4q = average of the
    # latest four quarters' shares (calculated), the measure compared across economies. Annual shares (Hong Kong) as is.
    for i, x in enumerate(out):
        x["share_4q"] = x["share"] if x["freq"] == "A" else None
        if x["freq"] == "Q" and i >= 3:
            w = out[i - 3:i + 1]
            if all(y["economy"] == x["economy"] and y["freq"] == "Q" and y["share"] is not None for y in w):
                x["share_4q"] = round(sum(y["share"] for y in w) / 4, 2)
    return out


def gva_annual(g, warnings):
    """Calendar-year (and year-to-date) real growth from the quarterly real levels in g; see the module docstring."""
    out = []
    for e in sorted({x["economy"] for x in g}):
        q0 = [x for x in g if x["economy"] == e and x["freq"] == "Q"]
        q = [x for x in q0 if x.get("real_level")]
        lv = {}
        for x in q:
            lv.setdefault(x["price"], {}).setdefault(int(x["period"][:4]), {})[int(x["period"][-1])] = x["real_level"]
            # check: level-based y/y against the published (or source) quarterly y/y
            prev = lv[x["price"]].get(int(x["period"][:4]) - 1, {}).get(int(x["period"][-1]))
            if prev and x["real_yoy"] is not None and x["period"] >= "2015":
                d = (x["real_level"] / prev - 1) * 100 - x["real_yoy"]
                if abs(d) > 0.3:
                    warnings.append(f"GVA {e} {x['period']}: y/y from real levels differs from the quarterly y/y by {d:.2f} pp")
        latest = max((y for p in lv.values() for y in p), default=None)
        rows = {}
        for price, by in lv.items():
            for y, qs in by.items():
                pq = by.get(y - 1, {})
                have = sorted(qs)
                if len(have) == 4 or (y == latest and have == list(range(1, len(have) + 1))):
                    if all(k in pq for k in have):
                        g_ = (sum(qs[k] for k in have) / sum(pq[k] for k in have) - 1) * 100
                        ytd = len(have) < 4
                        rows[y] = {"economy": e, "name": NAMES[e], "year": y, "quarters": f"Q1-Q{len(have)}" if ytd else "",
                                   "ytd": "y" if ytd else "", "real_yoy": round(g_, 2), "basis": "calculated"}
        if e == "CN":
            # NBS publishes no real levels: its cumulative (year-to-date) growth as published; Q4 = the full year
            rows = {}
            cq = [x for x in q0 if x.get("cum_yoy") is not None]
            for y in sorted({int(x["period"][:4]) for x in cq}):
                c = max((x for x in cq if int(x["period"][:4]) == y), key=lambda x: x["period"])
                n = int(c["period"][-1])
                if n < 4 and y != max(int(x["period"][:4]) for x in cq):
                    continue
                rows[y] = {"economy": e, "name": NAMES[e], "year": y, "quarters": "" if n == 4 else f"Q1-Q{n}",
                           "ytd": "" if n == 4 else "y", "real_yoy": c["cum_yoy"], "basis": "published"}
        if e == "VN":
            # NSO's real levels are not one consistent series (each quarter and year in its own vintage and units: the
            # level-based growth jumps, e.g. -18% in 2014, +62% in 2021), so Vietnam uses NSO's growth rates as
            # published: annual y/y for full years, the latest cumulative y/y (6, 9 months) for the year to date
            rows = {}
            pub = [x for x in rd("vn/gdp/vn_gdp.csv") if x["code"] == "manufacturing" and x["measure"] == "yoy"
                   and x["span"] in ("6M", "9M", "Y") and x["price"].startswith("constant") and f(x["rate"]) is not None]
            for y in sorted({int(x["period"][:4]) for x in pub}):
                ys = [x for x in pub if int(x["period"][:4]) == y]
                c = max(ys, key=lambda x: (x["date"], x["price"]))
                n = {"6M": 2, "9M": 3, "Y": 4}[c["span"]]
                if n < 4 and y != max(int(x["period"][:4]) for x in pub):
                    continue
                rows[y] = {"economy": e, "name": NAMES[e], "year": y, "quarters": "" if n == 4 else f"Q1-Q{n}",
                           "ytd": "" if n == 4 else "y", "real_yoy": round(f(c["rate"]), 2), "basis": "published"}
        out += [rows[y] for y in sorted(rows) if y >= 2010]
    return out


def write(name, cols, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def build(force=False):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    warnings, iip = [], []
    for fn in (india, thailand, vietnam, philippines, from_src):
        try:
            iip += fn()
        except Exception as e:  # noqa: BLE001 - one economy must not stop the others
            warnings.append(f"{fn.__name__}: {type(e).__name__}: {e}")
    # electronics = division 26 where the economy has no electronics series of its own (Japan and Singapore do)
    have = {x["economy"] for x in iip if x["industry"] == "elec"}
    iip += [{**x, "industry": "elec"} for x in iip if x["industry"] == "26" and x["economy"] not in have]
    iip = fill_yoy([x for x in iip if x["index"] is not None or x["yoy"] is not None])
    for x in iip:
        x["name"] = NAMES[x["economy"]]
    iip.sort(key=lambda x: (x["economy"], x["industry"], x["freq"], x["date"]))
    lat = latest(iip)
    g = gva()
    ga = gva_annual(g, warnings)
    fp = hashlib.sha256(json.dumps([iip, g, ga], sort_keys=True, default=str).encode()).hexdigest()[:16]
    covered = " ".join(sorted({x["economy"] for x in lat}))
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "summary": f"Asia manufacturing unchanged ({covered})", "warnings": warnings}
    write("asia_mfg_iip.csv", ["economy", "name", "freq", "date", "industry", "index", "yoy", "yoy_calculated"],
          [x for x in iip if x["date"] >= "2015-01-01"])
    write("asia_mfg_latest.csv", ["economy", "name", "industry", "freq", "date", "yoy", "yoy_prev", "m3", "ytd", "ytd_months", "note"], lat)
    write("asia_mfg_gva.csv", ["economy", "name", "freq", "period", "real_yoy", "share", "share_4q"], g)
    write("asia_mfg_gva_annual.csv", ["economy", "name", "year", "quarters", "ytd", "real_yoy", "basis"], ga)
    code = f"T{fp[:8]}"
    write_release(OUT, {"code": code, "label": f"Asia manufacturing: production {covered}; GVA {' '.join(sorted({x['economy'] for x in g}))}",
                        "economies": covered}, warnings, len(iip), {"fingerprint": fp})
    return {"updated": True, "summary": f"Asia manufacturing rebuilt ({covered})", "warnings": warnings}
