"""India producer prices: Output PPI, trial Input PPI and WPI (Office of the Economic Adviser, DPIIT).

2022-23 base, from the OEA's monthly index files (download_data_2223.asp): Output PPI (goods, basic prices,
Apr 2023 on), trial Input PPI for manufacturing (purchasers' prices without GST, Mar 2026 on) and WPI.
Index levels as published.

Spliced output PPI (Asia Decoded calculation): the Output PPI (All commodities) from Apr 2023, linked to the
WPI 2011-12 series (All commodities, Apr 2012 on, fixed file raw/in/ppi_oea/wpi1112_monthly_index_202606.xls)
by the ratio of geometric means over 2024-25, the year and method the OEA uses for its own WPI linking
factor (published: 1.53 for All commodities). y/y is calculated from the linked index. Before Apr 2023 the
series moves with the WPI, which differs in concept (taxes included, traded-value weights).

Linked WPI, manufactured products (in_wpi_mfg_linked.csv): WPI 2011-12 manufactured products divided by the OEA's
published linking factor, 1.44, to Mar 2023, the 2022-23 index from Apr 2023; y/y calculated.

The OEA publishes on the 14th of each month; the source checks only once a new month is due.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import re
import ssl
import urllib.request

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "in_ppi_oea"
DESCRIPTION = "India Output PPI, trial Input PPI and WPI (2022-23 base), and output PPI spliced with WPI 2011-12"
OUT = DATA / "in" / "ppi"
RAWDIR = RAW / "in" / "ppi_oea"
OLD_WPI = RAWDIR / "wpi1112_monthly_index_202606.xls"
BASE = "https://eaindustry.nic.in/"
PAGE = BASE + "download_data_2223.asp"
FILES = {"wpi": r"indx_download_2223/wpi_monthly_index_\d{6}\.xlsx",
         "oppi": r"indx_download_2223/oppi_monthly_index_\d{6}\.xlsx",
         "ippi": r"indx_download_2223/trial_ippi_monthly_index_\d{6}\.xlsx"}
LINK_FY = 2024  # financial year 2024-25 (Apr 2024 - Mar 2025), as the OEA's WPI linking factor
OEA_WPI_LINK = 1.53
OEA_WPI_MFG_LINK = 1.44   # OEA, linking factor 2011-12 to 2022-23, manufactured products (linking_factor2223.asp)
# Short names for the output PPI groups of manufactured products (NIC 2-digit divisions), as on the IIP charts
PPI_SHORT = {"1300000000": "Manufacturing", "1301000000": "Food products", "1302000000": "Beverages",
             "1303000000": "Tobacco products", "1304000000": "Textiles", "1305000000": "Wearing apparel",
             "1306000000": "Leather", "1307000000": "Wood and wood products", "1308000000": "Paper",
             "1309000000": "Printing and recorded media", "1310000000": "Coke and refined petroleum",
             "1311000000": "Chemicals", "1312000000": "Pharmaceuticals", "1313000000": "Rubber and plastics",
             "1314000000": "Non-metallic minerals", "1315000000": "Basic metals", "1316000000": "Fabricated metal products",
             "1317000000": "Computer, electronic and optical", "1318000000": "Electrical equipment",
             "1319000000": "Machinery and equipment n.e.c.", "1320000000": "Motor vehicles", "1321000000": "Other transport equipment",
             "1322000000": "Furniture", "1323000000": "Other manufacturing"}
RELEASE_DAY = 14
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)"}


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120, context=CTX).read()


def _fetch():
    html = _get(PAGE).decode("utf-8", "replace")
    out = {}
    for key, pat in FILES.items():
        found = sorted(set(re.findall(pat, html)))
        if not found:
            raise CheckFailed([f"no {key} file link on {PAGE}"])
        out[key] = {"name": found[-1], "bytes": _get(BASE + found[-1])}
    return out


def _month(h):
    if isinstance(h, dt.datetime):
        return f"{h.year}-{h.month:02d}-01"
    m = re.fullmatch(r"([A-Za-z]{3})-(\d{2})", str(h).strip())
    if m:
        return f"20{m.group(2)}-{MON.index(m.group(1).title()) + 1:02d}-01"
    return None


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _sheet(xbytes):
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(xbytes), read_only=True, data_only=True).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _tidy(raw):
    """{series key: {"label", "weight", "values": {YYYY-MM-01: index}}}."""
    out = {}
    # Output PPI: All commodities, the four major groups, and the 23 groups and 74 product categories of manufactured
    # products (Manufacturing tab: PPI excluding refined petroleum, bar chart by group, contributors table; user,
    # 4 Nov 2026).
    rows = _sheet(raw["oppi"]["bytes"])
    hdr = rows[0]
    for r in rows[1:]:
        # plus coke and refined petroleum products (group 1310000000), for the output PPI for manufactured products
        # excluding refined petroleum on the Manufacturing tab (user, 4 Nov 2026)
        if r[0] in ("All", "Major Group") or (r[0] in ("Group", "SUT Product Category") and str(r[1]).strip().startswith("13")):
            key = "oppi" if r[0] == "All" else f"oppi_{int(r[1])}"
            out[key] = {"label": str(r[2]).strip().capitalize(), "weight": _num(r[3]),
                        "values": {_month(h): _num(v) for h, v in zip(hdr[4:], r[4:]) if _month(h) and _num(v) is not None}}
    # WPI 2022-23: All commodities and major groups.
    rows = _sheet(raw["wpi"]["bytes"])
    hdr = rows[0]
    for r in rows[1:]:
        if r[0] in ("ALL", "Major Group"):
            key = "wpi" if r[0] == "ALL" else f"wpi_{r[2]}"
            out[key] = {"label": str(r[1]).strip(), "weight": _num(r[3]),
                        "values": {_month(h): _num(v) for h, v in zip(hdr[4:], r[4:]) if _month(h) and _num(v) is not None}}
    # Trial Input PPI: manufacturing and its industry groups.
    rows = _sheet(raw["ippi"]["bytes"])
    hdr = rows[0]
    for i, r in enumerate(rows[1:]):
        if not r[0]:
            continue
        key = "ippi" if str(r[0]).strip() == "Manufacturing Sector" else f"ippi_{i:02d}"
        out[key] = {"label": str(r[0]).strip(), "weight": _num(r[1]),
                    "values": {_month(h): _num(v) for h, v in zip(hdr[2:], r[2:]) if _month(h) and _num(v) is not None}}
    return out


def _old_wpi(comm="1000000000"):
    import xlrd
    sh = xlrd.open_workbook(file_contents=OLD_WPI.read_bytes()).sheet_by_index(0)
    hdr = sh.row_values(0)
    for i in range(1, sh.nrows):
        r = sh.row_values(i)
        if str(r[1]).strip() == comm:
            vals = {}
            for h, v in zip(hdr[3:], r[3:]):
                m = re.fullmatch(r"INDX(\d{2})(\d{4})", str(h))
                if m and _num(v) is not None:
                    vals[f"{m.group(2)}-{m.group(1)}-01"] = float(v)
            return vals
    raise CheckFailed([f"WPI 2011-12 file: no row {comm}"])


def _gm(vals):
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _fy(year):
    return [f"{year + (m < 4)}-{m:02d}-01" for m in (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3)]


def _prev_year(d):
    return f"{int(d[:4]) - 1}{d[4:]}"


def _due():
    t = dt.date.today()
    back = 1 if t.day >= RELEASE_DAY else 2
    y, m = t.year, t.month - back
    if m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}-01"


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if not from_file and state.get("latest_month", "") >= _due():
        return {"updated": False, "code": state.get("code"),
                "summary": f"not due (have {state.get('latest_month')}; next release on the {RELEASE_DAY}th)"}
    if from_file:
        raw = {k: {"name": v["name"], "bytes": bytes.fromhex(v["hex"])}
               for k, v in json.loads(gzip.decompress(open(from_file, "rb").read())).items()}
    else:
        raw = _fetch()
    tidy = _tidy(raw)
    fingerprint = hashlib.sha256(json.dumps({k: v["values"] for k, v in tidy.items()}, sort_keys=True).encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint") and not from_file:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    errors, warnings = [], []
    for key in ("oppi", "wpi", "ippi"):
        if key not in tidy or len(tidy[key]["values"]) < 6:
            errors.append(f"{key}: missing or too short")
    if errors:
        raise CheckFailed(errors)
    latest = max(tidy["oppi"]["values"])
    if state.get("latest_month") and latest < state["latest_month"]:
        raise CheckFailed([f"latest month {latest} is before the one already stored ({state['latest_month']})"])
    for k in ("oppi", "wpi"):
        if abs(tidy[k]["weight"] - 100) > 0.01:
            errors.append(f"{k}: All commodities weight {tidy[k]['weight']}")

    # Splice: output PPI linked to WPI 2011-12 over FY 2024-25; check the same method on the WPI reproduces
    # the OEA's published linking factor.
    old = _old_wpi()
    fy = _fy(LINK_FY)
    if not all(m in old and m in tidy["oppi"]["values"] and m in tidy["wpi"]["values"] for m in fy):
        raise CheckFailed([f"no full overlap in FY {LINK_FY}-{LINK_FY - 1999}"])
    wpi_link = _gm([old[m] for m in fy]) / _gm([tidy["wpi"]["values"][m] for m in fy])
    if abs(wpi_link - OEA_WPI_LINK) > 0.006:
        errors.append(f"WPI linking factor {wpi_link:.4f}, OEA published {OEA_WPI_LINK}")
    factor = _gm([tidy["oppi"]["values"][m] for m in fy]) / _gm([old[m] for m in fy])
    # Linked WPI, manufactured products (user, 4 Nov 2026): WPI 2011-12 manufactured products divided by the OEA's
    # published linking factor (1.44) to Mar 2023, WPI 2022-23 manufactured products from Apr 2023; y/y calculated.
    # Check: the geometric-mean ratio over 2024-25 reproduces the published factor.
    old_m, new_m = _old_wpi("1300000000"), tidy.get("wpi_1300000000", {}).get("values", {})
    if not all(m in old_m and m in new_m for m in fy):
        errors.append("WPI manufactured products: no full overlap in the link year")
    else:
        mfg_link = _gm([old_m[m] for m in fy]) / _gm([new_m[m] for m in fy])
        if abs(mfg_link - OEA_WPI_MFG_LINK) > 0.006:
            errors.append(f"WPI manufactured products linking factor {mfg_link:.4f}, OEA published {OEA_WPI_MFG_LINK}")
    if errors:
        raise CheckFailed(errors)
    first_new = min(tidy["oppi"]["values"])
    mfg_first = min(new_m)
    wpi_mfg = {m: v / OEA_WPI_MFG_LINK for m, v in old_m.items() if m < mfg_first}
    wpi_mfg.update(new_m)
    spliced = {m: v * factor for m, v in old.items() if m < first_new}
    spliced.update(tidy["oppi"]["values"])

    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent months revised (no new month)")
    release = {"code": code, "label": f"{MON[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "files": {k: v["name"] for k, v in raw.items()},
               "splice": {"link_fy": f"{LINK_FY}-{LINK_FY - 1999}", "oppi_per_old_wpi": round(factor, 6),
                          "wpi_link_check": round(wpi_link, 4), "first_new_month": first_new}}

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "in_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series", "label", "weight", "index"])
        for key, s in tidy.items():
            for m in sorted(s["values"]):
                w.writerow([m, key, s["label"], "" if s["weight"] is None else round(s["weight"], 4), s["values"][m]])
    with open(OUT / "in_ppi_spliced.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "index", "yoy", "basis"])
        for m in sorted(spliced):
            p = _prev_year(m)
            yoy = "" if p not in spliced else round((spliced[m] / spliced[p] - 1) * 100, 2)
            w.writerow([m, round(spliced[m], 3), yoy, "Output PPI 2022-23" if m >= first_new else "WPI 2011-12, linked"])

    with open(OUT / "in_wpi_mfg_linked.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "index", "yoy", "basis"])
        for m in sorted(wpi_mfg):
            p = _prev_year(m)
            yoy = "" if p not in wpi_mfg else round((wpi_mfg[m] / wpi_mfg[p] - 1) * 100, 1)
            w.writerow([m, round(wpi_mfg[m], 3), yoy, "WPI 2022-23" if m >= mfg_first else "WPI 2011-12 / 1.44"])

    # Output PPI, manufactured products by group (user, 4 Nov 2026), as the IIP bar charts: 3mma = plain average of
    # the latest three months' y/y (calculated from the published indices; the OEA publishes no PPI growth rates),
    # YTD = average index January to the latest month against the same months a year earlier.
    ppi_groups = []
    y0, m0 = int(latest[:4]), int(latest[5:7])
    for key, s_ in tidy.items():
        if not re.fullmatch(r"oppi_13\d\d000000", key):
            continue
        v = s_["values"]
        yy = lambda d: (v[d] / v[_prev_year(d)] - 1) * 100 if d in v and _prev_year(d) in v else None
        last3 = [d for d in sorted(v) if d <= latest][-3:]
        y3 = [yy(d) for d in last3]
        cur = [v.get(f"{y0}-{k:02d}-01") for k in range(1, m0 + 1)]
        prev = [v.get(f"{y0 - 1}-{k:02d}-01") for k in range(1, m0 + 1)]
        if len(last3) < 3 or None in y3 or None in cur or None in prev:
            errors.append(f"output PPI {key}: months missing"); continue
        gcode = key.replace("oppi_", "")
        ppi_groups.append({"date": latest, "code": gcode, "name": PPI_SHORT.get(gcode, s_["label"]),
                           "weight": s_["weight"], "yoy": round(yy(latest), 1), "m3": round(sum(y3) / 3, 1),
                           "ytd": round((sum(cur) / sum(prev) - 1) * 100, 1), "calculated": "y"})
    # PPI excluding refined petroleum: manufactured products less coke and refined petroleum, at the published weights
    mp, ck = tidy.get("oppi_1300000000"), tidy.get("oppi_1310000000")
    if mp and ck:
        W, Wc = mp["weight"], ck["weight"]
        v = {d: (W * mp["values"][d] - Wc * ck["values"][d]) / (W - Wc) for d in mp["values"] if d in ck["values"]}
        yy = lambda d: (v[d] / v[_prev_year(d)] - 1) * 100 if d in v and _prev_year(d) in v else None
        last3 = [d for d in sorted(v) if d <= latest][-3:]
        cur = [v.get(f"{y0}-{k:02d}-01") for k in range(1, m0 + 1)]
        prev = [v.get(f"{y0 - 1}-{k:02d}-01") for k in range(1, m0 + 1)]
        if len(last3) == 3 and None not in [yy(d) for d in last3] + cur + prev:
            ppi_groups.insert(1, {"date": latest, "code": "XPET", "name": "Excluding refined petroleum", "weight": round(W - Wc, 5),
                                  "yoy": round(yy(latest), 1), "m3": round(sum(yy(d) for d in last3) / 3, 1),
                                  "ytd": round((sum(cur) / sum(prev) - 1) * 100, 1), "calculated": "y"})
    if errors:
        raise CheckFailed(errors)
    # Contributions of the 74 product categories of manufactured products to its y/y, pp (user, 4 Nov 2026):
    # weight x (index - index a year earlier) / (manufactured products weight x its index a year earlier) x 100;
    # weight shown as a share of manufactured products (%). Check: the categories add up to the y/y within 0.15pp (they do within 0.11pp).
    ppi_items = []
    if mp:
        Wm, vm = mp["weight"], mp["values"]
        cats = {k: v for k, v in tidy.items() if re.fullmatch(r"oppi_13\d{8}", k) and not k.endswith("000000")}
        if len(cats) < 70:
            errors.append(f"output PPI: {len(cats)} product categories of manufactured products, expected 74")
        for d in sorted(vm):
            p_ = _prev_year(d)
            if p_ not in vm or d < "2024-04-01":
                continue
            tot = 0.0
            for k, c in cats.items():
                if d not in c["values"] or p_ not in c["values"]:
                    continue
                con = c["weight"] * (c["values"][d] - c["values"][p_]) / (Wm * vm[p_]) * 100
                tot += con
                ppi_items.append({"date": d, "code": k.replace("oppi_", ""), "name": c["label"], "weight": round(c["weight"] / Wm * 100, 3),
                                  "yoy": round((c["values"][d] / c["values"][p_] - 1) * 100, 1), "contribution": round(con, 3), "calculated": "y"})
            if abs(tot - (vm[d] / vm[p_] - 1) * 100) > 0.15:   # indices published to one decimal
                errors.append(f"output PPI contributions {d[:7]}: categories sum to {tot:.2f}, manufactured products y/y {(vm[d] / vm[p_] - 1) * 100:.2f}")
    if errors:
        raise CheckFailed(errors)
    with open(OUT / "in_ppi_contrib_items.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ppi_items[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(ppi_items)
    with open(OUT / "in_ppi_mfg_groups.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ppi_groups[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(ppi_groups)

    def long_rows():
        for key, s in tidy.items():
            for m, v in s["values"].items():
                yield {"country": "IN", "indicator": "ppi", "series": key, "label": s["label"], "measure": "index",
                       "area": "all-India", "freq": "M", "date": m, "value": v, "unit": "index, 2022-23 = 100",
                       "source": "Office of the Economic Adviser, DPIIT", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(
        {k: {"name": v["name"], "hex": v["bytes"].hex()} for k, v in raw.items()}).encode()))
    write_release(OUT, release, warnings, sum(len(s["values"]) for s in tidy.values()),
                  {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: output PPI {tidy['oppi']['values'][latest]}, "
            f"input PPI {tidy['ippi']['values'].get(latest)}; splice factor {factor:.4f}", "warnings": warnings}
