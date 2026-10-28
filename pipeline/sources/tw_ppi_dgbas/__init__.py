"""Taiwan producer, import and export prices: DGBAS Macro Database, as published (no key).

PPI (producer price index, replaced the WPI): 2021 = 100, Jan 2021- (y/y from Jan 2022), 2024 weights;
index, m/m, y/y for all items, the four sections, the manufacturing divisions and their subgroups.
Domestic sales price index (國產內銷, part of the WPI to Dec 2022, continued since), 1981-.
Import and export price indices in NTD and USD, by HS section and by end use, 1981- in the database
(DGBAS's linked file starts in 1976), 2021 = 100 reference with 2024 weights from Jan 2026; DGBAS's
seasonally adjusted import and export indices. Nothing is calculated.
"""
import csv
import gzip
import hashlib
import json

from core import dgbas
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "tw_ppi_dgbas"
DESCRIPTION = "Taiwan producer, domestic sales, import and export prices (DGBAS, as published)"
OUT = DATA / "tw" / "ppi"
RAWDIR = RAW / "tw" / "ppi_dgbas"
LONGMONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
# table, first month, prefix, group
TABLES = [
    ("A030701015", "2021-01", "ppi", "ppi"),
    ("A030702015", "1981-01", "dsp", "domestic_sales"),
    ("A030302015", "1981-01", "ipi_ntd", "import_hs"),
    ("A030301015", "1981-01", "ipi_usd", "import_hs"),
    ("A030402015", "1981-01", "epi_ntd", "export_hs"),
    ("A030401015", "1981-01", "epi_usd", "export_hs"),
    ("A030303015", "1981-01", "ipi_ntd", "import_use"),
    ("A030306015", "1981-01", "ipi_usd", "import_use"),
    ("A030405015", "1981-01", "epi_ntd", "export_use"),
    ("A030408015", "1981-01", "epi_usd", "export_use"),
]
SA = {"進口物價總指數_新臺幣計價_經季節調整": "ipi_ntd_all", "進口物價總指數_美元計價_經季節調整": "ipi_usd_all",
      "出口物價總指數_新臺幣計價_經季節調整": "epi_ntd_all", "出口物價總指數_美元計價_經季節調整": "epi_usd_all"}
EN = {
    "總指數": ("all", "All items"),
    "一.農林漁牧業產品": ("agriculture", "Agriculture, forestry, fishing and animal husbandry products"),
    "1.農產品": ("farm", "Farm products"), "2.畜禽產品": ("livestock", "Livestock and poultry products"),
    "3.林產品": ("forest", "Forest products"), "4.水產品": ("fishery", "Fishery products"),
    "二.土石及礦產品": ("mining", "Quarrying and mining products"),
    "1.石油及天然氣": ("oil_gas", "Crude petroleum and natural gas"),
    "2.土石採取及其他礦產品": ("quarrying", "Quarrying and other mining products"),
    "三.製造業產品": ("manufacturing", "Manufacturing products"),
    "1.食品及飼品": ("food", "Food products and prepared animal feeds"), "2.飲料": ("beverages", "Beverages"),
    "3.菸類": ("tobacco", "Tobacco"), "4.紡織品": ("textiles", "Textile products"),
    "5.成衣及服飾品": ("apparel", "Wearing apparel and clothing accessories"),
    "6.皮革及其製品": ("leather", "Leather, fur and related products"), "7.木竹製品": ("wood", "Wood and bamboo products"),
    "8.紙漿、紙、紙製品及印刷品": ("paper", "Pulp, paper, paper products and printing"),
    "9.石油及煤製品": ("petroleum", "Petroleum and coal products"),
    "10.化學材料及其製品與藥品": ("chemicals", "Chemical materials, other chemical products and medicines"),
    "11.橡膠及塑膠製品": ("rubber_plastic", "Rubber and plastic products"),
    "12.非金屬礦物製品": ("non_metallic", "Non-metallic mineral products"), "13.基本金屬": ("basic_metals", "Basic metals"),
    "14.金屬製品": ("fabricated_metal", "Fabricated metal products"),
    "15.電子零組件": ("electronic_parts", "Electronic parts and components"),
    "16.電腦、電子產品及光學製品": ("computers", "Computers, electronic and optical products"),
    "17.電力設備及配備": ("electrical", "Electrical equipment"), "18.機械設備": ("machinery", "Machinery and equipment"),
    "19.運輸工具及零件": ("transport_equipment", "Transport equipment and parts"),
    "20.家具及裝設品": ("furniture", "Furniture and fixtures"), "21.雜項工業製品": ("misc_manufacturing", "Miscellaneous products"),
    "四.水電燃氣": ("utilities", "Water, electricity and gas supply"), "1.水": ("water", "Water supply"),
    "2.電": ("electricity", "Electricity supply"), "3.燃氣": ("gas", "Gas supply"),
    "(1)半導體": ("semiconductors", "Semiconductors"),
    "第1類 動物產品": ("hs01", "Animal products"), "第2類 植物產品": ("hs02", "Vegetable products"),
    "第4類 調製食品、飲料、酒及菸類": ("hs04", "Prepared foodstuffs, beverages and tobacco"),
    "第5類 礦產品": ("hs05", "Mineral products"), "27 能源礦產品": ("hs27", "Mineral fuels"), "原油": ("crude_oil", "Crude oil"),
    "第6類 化學或有關工業產品": ("hs06", "Chemical products"), "第7類 塑、橡膠及其製品": ("hs07", "Plastics and rubber"),
    "第8類 皮革及其製品": ("hs08", "Leather products"), "第9類 木及木製品": ("hs09", "Wood and wood products"),
    "第10類 木漿、紙及其製品": ("hs10", "Pulp, paper and products"), "第11類 紡織及其製品": ("hs11", "Textiles and products"),
    "第13類 石料製品、玻璃及玻璃器": ("hs13", "Stone, ceramic and glass products"),
    "第15類 基本金屬及其製品": ("hs15", "Base metals and products"),
    "第16類 機器、電機及電視影像等設備及其零件": ("hs16", "Machinery and electrical equipment"),
    "8542 積體電路": ("hs8542", "Integrated circuits"), "第17類 運輸工具": ("hs17", "Transport equipment"),
    "第18類 光學、計量、醫療儀器、樂器及其零件": ("hs18", "Optical, measuring and medical instruments"),
    "第20類 雜項製品": ("hs20", "Miscellaneous manufactured articles"),
    "農工業原料": ("raw_materials", "Agricultural and industrial raw materials"),
    "農工業原料-農業原料": ("raw_agri", "Agricultural raw materials"),
    "農工業原料-工業原料": ("raw_industrial", "Industrial raw materials"), "農工業原料-能源": ("raw_energy", "Energy"),
    "資本用品": ("capital", "Capital goods"), "消費用品": ("consumer", "Consumer goods"),
    "消費用品-非耐久": ("consumer_nondurable", "Non-durable consumer goods"),
    "消費用品-耐久": ("consumer_durable", "Durable consumer goods"),
}
PREFIX_LABEL = {"ppi": "PPI", "dsp": "Domestic sales prices", "ipi_ntd": "Import prices (NTD)",
                "ipi_usd": "Import prices (USD)", "epi_ntd": "Export prices (NTD)", "epi_usd": "Export prices (USD)"}


def _shift(p, months):
    y, m = int(p[:4]), int(p[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def _months(a, b):
    out, p = [], a
    while p <= b:
        out.append(p)
        p = _shift(p, 1)
    return out


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])


def update(**opts):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    warnings = []
    latest = dgbas.latest("A030701015")
    if state.get("latest_month", "")[:7] == latest and not opts.get("force"):
        return {"updated": False, "code": state.get("code"), "summary": f"no new month (latest {latest})"}
    raw, data, meta = {}, {}, {}
    for funid, first, prefix, group in TABLES:
        s, r = dgbas.series(funid, first, latest)
        raw.update(r)
        for j, ((field, meas), vals) in enumerate(sorted(s.items())):
            key, label = EN.get(field, (None, None))
            if key is None:
                key, label = "f_" + hashlib.md5(field.encode()).hexdigest()[:6], field
            if group.endswith("_use") and key == "all":
                continue  # same all-items index as the HS table
            sid = f"{prefix}_{key}"
            data[(sid, meas)] = vals
            meta[sid] = {"label": f"{PREFIX_LABEL[prefix]}: {label}" if key != "all" else PREFIX_LABEL[prefix],
                         "label_zh": field, "group": group, "prefix": prefix}
    s, r = dgbas.series("A030601015", "1981-01", latest, ("00", "1"))
    raw.update(r)
    for (field, meas), vals in s.items():
        if field in SA:
            sid = SA[field]
            data[(sid, "sa_index" if meas == "index" else "sa_mom")] = vals
    # ---- checks
    errors = []
    for sid in ("ppi_all", "ipi_usd_all", "ipi_ntd_all", "epi_usd_all", "epi_ntd_all", "dsp_all"):
        for meas in ("index", "mom", "yoy"):
            if latest not in data.get((sid, meas), {}):
                errors.append(f"latest month {latest}: {sid} {meas} missing")
    if state.get("latest_month") and latest < state["latest_month"][:7]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month'][:7]})")
    for sid, first in (("ppi_all", "2022-01"), ("ipi_usd_all", "1982-01"), ("epi_usd_all", "1982-01")):
        have = set(data.get((sid, "yoy"), {}))
        missing = sorted(set(_months(first, latest)) - have)
        if missing:
            errors.append(f"{sid} y/y has gaps: {missing[:12]}")
    stats = {"tested": 0, "max": 0.0}
    bad, bad_other = [], []
    for (sid, meas), vals in data.items():
        if meas not in ("yoy", "mom"):
            continue
        idx = data.get((sid, "index"), {})
        for p, v in vals.items():
            p0 = _shift(p, -12 if meas == "yoy" else -1)
            if p in idx and p0 in idx and idx[p0] > 0:
                c = (idx[p] / idx[p0] - 1) * 100
                d = abs(c - v)
                stats["tested"] += 1
                stats["max"] = max(stats["max"], d)
                lim = 100 * (0.005 / idx[p0] + 0.005 * idx[p] / idx[p0] ** 2) + 0.0151
                if d > lim:
                    (bad if sid.endswith("_all") else bad_other).append(f"{sid} {meas} {p}: published {v} vs index {c:.3f}")
    if bad:
        errors.append(f"published rate differs from the index beyond rounding ({len(bad)}): {bad[:6]}")
    if bad_other:
        warnings.append(f"rate vs index beyond rounding in {len(bad_other)} of {stats['tested']} cases (components): {bad_other[:4]}")
    for (sid, meas), vals in data.items():
        for p, v in vals.items():
            if meas in ("index", "sa_index") and not 0 < v < 2000:
                errors.append(f"{sid} {meas} {p} = {v} out of range")
    if errors:
        raise CheckFailed(errors)
    # ---- write
    cpi_rel = read_json(DATA / "tw" / "cpi" / "release.json", {}) or {}
    rel_dates = {}
    try:
        idx = json.loads((RAW / "tw" / "cpi_dgbas" / "releases" / "index.json").read_text())
        rel_dates = {m: r.get("date", "") for m, r in idx.items()}  # one release for CPI, PPI, import/export
    except (OSError, ValueError):
        pass
    rows = []
    for (sid, meas), vals in data.items():
        m = meta.get(sid, {"label": sid, "label_zh": "", "group": "seasonally_adjusted"})
        for p, v in vals.items():
            rows.append({"date": p + "-01", "series": sid, "label": m["label"], "label_zh": m["label_zh"],
                         "group": m["group"], "measure": meas, "value": v,
                         "base_break": 1 if (p == "2026-01" and sid.startswith(("ipi", "epi"))) else 0,
                         "release_date": rel_dates.get(p, "")})
    rows.sort(key=lambda r: (r["date"], r["group"], r["series"], r["measure"]))
    cols = ["date", "series", "label", "label_zh", "group", "measure", "value", "base_break", "release_date"]
    _write_csv(OUT / "tw_ppi.csv", cols, rows)
    dash = [r for r in rows if r["series"] in {"ppi_all", "ppi_agriculture", "ppi_mining", "ppi_manufacturing",
                                               "ppi_utilities", "dsp_all", "ipi_usd_all", "ipi_ntd_all", "epi_usd_all",
                                               "epi_ntd_all", "ppi_electronic_parts", "ppi_petroleum", "ppi_chemicals",
                                               "ppi_computers", "ppi_basic_metals"}]
    _write_csv(OUT / "tw_ppi_dash.csv", ["date", "series", "measure", "value"], dash)
    code = f"P{latest}"
    label = f"{LONGMONTHS[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            yield {"country": "TW", "indicator": "ppi", "series": f"{r['series']}_{r['measure']}", "label": r["label"],
                   "measure": r["measure"], "area": "national", "freq": "M", "date": r["date"], "value": r["value"],
                   "unit": "index 2021=100" if "index" in r["measure"] else "%", "source": "DGBAS", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    asia = [{"country": "TW", "concept": "ppi_yoy", "series_id": "tw.ppi.all.yoy", "date": r["date"], "value": r["value"],
             "unit": "% y/y", "basis": "published", "source": "DGBAS", "base_break": r["base_break"],
             "release_date": r["release_date"]} for r in rows if r["series"] == "ppi_all" and r["measure"] == "yoy"]
    _write_csv(OUT / "asia.csv", ["country", "concept", "series_id", "date", "value", "unit", "basis", "source",
                                  "base_break", "release_date"], asia)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(raw, ensure_ascii=False).encode()
    fp = hashlib.sha256(payload).hexdigest()[:12]
    (RAWDIR / f"{code}_{fp}.json.gz").write_bytes(gzip.compress(payload))
    release = {"code": code, "label": label, "latest_month": latest + "-01",
               "release_date": rel_dates.get(latest, "") or cpi_rel.get("release_date", ""),
               "table": "DGBAS Macro Database (nstatdb): PPI, domestic sales, import and export price tables"}
    write_release(OUT, release, warnings, len(rows), {"long_rows": nlong, "rate_checks": stats})
    return {"updated": True, "code": code,
            "summary": f"{label}: {len(rows)} rows; rates vs index {stats['tested']} tested, max {stats['max']:.3f}",
            "warnings": warnings}
