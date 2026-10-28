"""China industrial producer prices: NBS data portal, as published (no key).

Producer price index for industrial products (ex-factory PPI) with means of production and consumer
goods, the purchasing price index for industrial producers with its 9 groups, and ex-factory PPI by
industry (GB/T 4754-2017 divisions); y/y (same month last year = 100), year to date (same period last
year = 100) and m/m (previous month = 100); national, and PPI and purchasing prices by province.
NBS publishes no index levels. The value is stored as published and as a percentage change
(value - 100, the rate in NBS's release); nothing is calculated.
"""
import csv
import gzip
import hashlib
import json

from core import nbs
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "cn_ppi_nbs"
DESCRIPTION = "China industrial producer and purchasing prices (NBS data portal, as published)"
OUT = DATA / "cn" / "ppi"
RAWDIR = RAW / "cn" / "ppi_nbs"
LONGMONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
MEASURES = {"6021702000021": "yoy", "6021702000022": "ytd", "6021702000023": "mom"}
BASE_STARTS = {"2001-01": "2000", "2006-01": "2005", "2011-01": "2010", "2016-01": "2015", "2021-01": "2020",
               "2026-01": "2025"}
# Chinese name (without the index suffix) -> (key, English name as in NBS's English release)
NAMES = {
    "工业生产者出厂价格指数": ("ppi", "PPI (ex-factory prices of industrial products)"),
    "生产资料工业生产者出厂价格指数": ("ppi_production", "Means of production"),
    "生活资料工业生产者出厂价格指数": ("ppi_consumer", "Consumer goods"),
    "采掘业生产资料": ("ppi_mining", "Mining and quarrying"),
    "原料业生产资料": ("ppi_raw", "Raw materials"),
    "加工业生产资料": ("ppi_processing", "Processing"),
    "食品类": ("ppi_food", "Food"),
    "衣着类": ("ppi_clothing", "Clothing"),
    "一般日用品类": ("ppi_daily", "Articles for daily use"),
    "耐用消费品类": ("ppi_durables", "Durable consumer goods"),
    "工业生产者购进价格指数": ("purchasing", "Purchasing prices of industrial producers"),
    "燃料、动力类": ("pur_fuel_power", "Fuel and power"),
    "黑色金属材料类": ("pur_ferrous", "Ferrous metals"),
    "有色金属材料及电线类": ("pur_nonferrous", "Nonferrous metals and cables"),
    "有色金属材料和电线类": ("pur_nonferrous", "Nonferrous metals and cables"),
    "化工原料类": ("pur_chemicals", "Raw chemical materials"),
    "木材及纸浆类": ("pur_timber_pulp", "Timber and paper pulp"),
    "建筑材料及非金属类": ("pur_building", "Building materials and non-metals"),
    "其他工业原材料及半成品类": ("pur_other", "Other industrial raw materials and semi-products"),
    "其它工业原材料及半成品类": ("pur_other", "Other industrial raw materials and semi-products"),
    "农副产品类": ("pur_agri", "Agricultural and sideline products"),
    "纺织原料类": ("pur_textile", "Textile materials"),
    "煤炭开采和洗选业": ("ind_coal", "Mining and washing of coal"),
    "石油和天然气开采业": ("ind_oil_gas", "Extraction of petroleum and natural gas"),
    "黑色金属矿采选业": ("ind_ferrous_ore", "Mining and processing of ferrous metal ores"),
    "有色金属矿采选业": ("ind_nonferrous_ore", "Mining and processing of non-ferrous metal ores"),
    "非金属矿采选业": ("ind_nonmetal_ore", "Mining and processing of non-metal ores"),
    "开采专业及辅助性活动": ("ind_mining_support", "Professional and support activities for mining"),
    "开采辅助活动": ("ind_mining_support", "Support activities for mining"),
    "其他采矿业": ("ind_other_mining", "Other mining"),
    "农副食品加工业": ("ind_agri_food", "Processing of food from agricultural and sideline products"),
    "食品制造业": ("ind_food", "Manufacture of foods"),
    "酒、饮料及精制茶制造业": ("ind_beverages", "Manufacture of liquor, beverages and refined tea"),
    "酒、饮料和精制茶制造业": ("ind_beverages", "Manufacture of liquor, beverages and refined tea"),
    "饮料制造业": ("ind_beverages", "Manufacture of beverages"),
    "烟草制品业": ("ind_tobacco", "Manufacture of tobacco"),
    "纺织业": ("ind_textiles", "Textile industry"),
    "纺织服装、服饰业": ("ind_apparel", "Manufacture of textiles, wearing apparel and accessories"),
    "纺织服装、鞋、帽制造业": ("ind_apparel", "Manufacture of textile wearing apparel, footwear and caps"),
    "皮革、毛皮、羽毛及其制品和制鞋业": ("ind_leather", "Leather, fur, feathers and footwear"),
    "皮革、毛皮、羽毛 (绒) 及其制品业": ("ind_leather", "Leather, fur, feathers and related products"),
    "木材加工和木、竹、藤、棕、草制品业": ("ind_wood", "Processing of timber; wood, bamboo, rattan, palm and straw products"),
    "木材加工及木、竹、藤、棕、草制品业": ("ind_wood", "Processing of timber; wood, bamboo, rattan, palm and straw products"),
    "家具制造业": ("ind_furniture", "Manufacture of furniture"),
    "造纸和纸制品业": ("ind_paper", "Manufacture of paper and paper products"),
    "造纸及纸制品业": ("ind_paper", "Manufacture of paper and paper products"),
    "印刷和记录媒介复制业": ("ind_printing", "Printing and reproduction of recording media"),
    "印刷业和记录媒介的复制": ("ind_printing", "Printing and reproduction of recording media"),
    "文教、工美、体育和娱乐用品制造业": ("ind_culture_sports", "Articles for culture, education, arts and crafts, sport and entertainment"),
    "文教体育用品制造业": ("ind_culture_sports", "Articles for culture, education and sport"),
    "石油、煤炭及其他燃料加工业": ("ind_petroleum", "Processing of petroleum, coal and other fuels"),
    "石油加工、炼焦和核燃料加工业": ("ind_petroleum", "Processing of petroleum, coking and nuclear fuel"),
    "石油加工、炼焦及核燃料加工业": ("ind_petroleum", "Processing of petroleum, coking and nuclear fuel"),
    "化学原料和化学制品制造业": ("ind_chemicals", "Manufacture of raw chemical materials and chemical products"),
    "化学原料及化学制品制造业": ("ind_chemicals", "Manufacture of raw chemical materials and chemical products"),
    "医药制造业": ("ind_medicines", "Manufacture of medicines"),
    "化学纤维制造业": ("ind_chem_fibres", "Manufacture of chemical fibres"),
    "橡胶和塑料制品业": ("ind_rubber_plastics", "Manufacture of rubber and plastic products"),
    "橡胶制品业": ("ind_rubber", "Manufacture of rubber products"),
    "塑料制品业": ("ind_plastics", "Manufacture of plastic products"),
    "非金属矿物制品业": ("ind_nonmetal_products", "Manufacture of non-metallic mineral products"),
    "黑色金属冶炼和压延加工业": ("ind_ferrous", "Smelting and pressing of ferrous metals"),
    "黑色金属冶炼及压延加工业": ("ind_ferrous", "Smelting and pressing of ferrous metals"),
    "有色金属冶炼和压延加工业": ("ind_nonferrous", "Smelting and pressing of non-ferrous metals"),
    "有色金属冶炼及压延加工业": ("ind_nonferrous", "Smelting and pressing of non-ferrous metals"),
    "金属制品业": ("ind_metal_products", "Manufacture of metal products"),
    "通用设备制造业": ("ind_general_machinery", "Manufacture of general-purpose machinery"),
    "专用设备制造业": ("ind_special_machinery", "Manufacture of special-purpose machinery"),
    "汽车制造业": ("ind_autos", "Manufacture of automobiles"),
    "铁路、船舶、航空航天和其他运输设备制造业": ("ind_transport_equip", "Railway, ships, aerospace and other transport equipment"),
    "交通运输设备制造业": ("ind_transport_equip", "Manufacture of transport equipment"),
    "电气机械和器材制造业": ("ind_electrical", "Manufacture of electrical machinery and apparatus"),
    "电气机械及器材制造业": ("ind_electrical", "Manufacture of electrical machinery and apparatus"),
    "计算机、通信和其他电子设备制造业": ("ind_electronics", "Computers, communication equipment and other electronic equipment"),
    "通信设备、计算机及其他电子设备制造业": ("ind_electronics", "Communication equipment, computers and other electronic equipment"),
    "仪器仪表制造业": ("ind_instruments", "Manufacture of measuring instruments"),
    "仪器仪表及文化、办公用机械制造业": ("ind_instruments", "Instruments and office machinery"),
    "其他制造业": ("ind_other_mfg", "Other manufacturing"),
    "工艺品及其他制造业": ("ind_other_mfg", "Handicrafts and other manufacturing"),
    "废弃资源综合利用业": ("ind_waste", "Utilisation of waste resources"),
    "废弃资源和废旧材料回收加工业": ("ind_waste", "Recycling of waste resources and materials"),
    "金属制品、机械和设备修理业": ("ind_repair", "Repair of metal products, machinery and equipment"),
    "电力、热力生产和供应业": ("ind_power_heat", "Production and supply of electricity and heat"),
    "燃气生产和供应业": ("ind_gas", "Production and supply of gas"),
    "水的生产和供应业": ("ind_water", "Production and supply of water"),
}
ORDER = {k: i for i, k in enumerate(dict.fromkeys(v[0] for v in NAMES.values()))}
PROVINCES = {
    "11": "Beijing", "12": "Tianjin", "13": "Hebei", "14": "Shanxi", "15": "Inner Mongolia", "21": "Liaoning",
    "22": "Jilin", "23": "Heilongjiang", "31": "Shanghai", "32": "Jiangsu", "33": "Zhejiang", "34": "Anhui",
    "35": "Fujian", "36": "Jiangxi", "37": "Shandong", "41": "Henan", "42": "Hubei", "43": "Hunan",
    "44": "Guangdong", "45": "Guangxi", "46": "Hainan", "50": "Chongqing", "51": "Sichuan", "52": "Guizhou",
    "53": "Yunnan", "54": "Tibet", "61": "Shaanxi", "62": "Gansu", "63": "Qinghai", "64": "Ningxia",
    "65": "Xinjiang",
}


def base_of(p):
    b = ""
    for start, base in sorted(BASE_STARTS.items()):
        if p >= start:
            b = base
    return b


def _clean(name):
    """'煤炭开采和洗选业工业生产者出厂价格指数 (上年同月=100)' -> '煤炭开采和洗选业'."""
    n = name.split("(")[0].split("（")[0].strip()
    for suf in ("工业生产者出厂价格指数", "工业生产者购进价格指数"):
        if n.endswith(suf) and n != suf and n not in NAMES:
            n = n[: -len(suf)].strip()
    if n in NAMES:
        return n
    return n.replace("购进价格指数", "").strip() or name


def _keep(path, name):
    return "工业生产者" in (path + name) and "中类" not in (path + name) and "按工业部门" not in name


def _tidy(rows, prov, warnings):
    out, unknown = {}, set()
    for r in rows:
        codes = (r["ek"] or "").split("|")[0].split("-")
        meas = next((MEASURES[c] for c in codes if c in MEASURES), None)
        if meas is None:
            continue
        nm = _clean(r["name"])
        if nm not in NAMES:
            unknown.add(nm)
            continue
        key, label = NAMES[nm]
        if prov:
            pc = (r["area"] or "")[:2]
            if pc not in PROVINCES:
                continue
            area, area_name = pc, PROVINCES[pc]
        else:
            area, area_name = "national", "China"
        v = float(r["value"])
        k = (r["period"], area, key, meas)
        if k in out and abs(out[k]["value"] - v) > 1e-9:
            warnings.append(f"{key} {meas} {area} {r['period']}: catalogs disagree ({out[k]['value']} vs {v})")
            continue
        out[k] = {"date": r["period"] + "-01", "area": area, "area_name": area_name, "series": key, "label": label,
                  "group": "industry" if key.startswith("ind_") else ("purchasing" if key.startswith("pur") else "ppi"),
                  "order": ORDER[key], "measure": meas, "value": v, "pct": round(v - 100, 1),
                  "base": base_of(r["period"]), "ek": (r["ek"] or "").split("|")[0]}
    if unknown:
        warnings.append("PPI series not mapped (left out): " + "; ".join(sorted(unknown))[:500])
    return out


def _shift(p, n):
    y, m = int(p[:4]), int(p[5:7]) - 1 + n
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def _write_csv(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])


def update(**opts):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    warnings = []
    cats = nbs.catalogs("1", nbs.ROOT_MONTHLY, _keep)
    if not cats:
        raise CheckFailed(["no PPI catalogs found in the NBS portal's monthly tree (portal changed?)"])
    main = [c for c, m in cats.items() if m["name"].startswith("工业生产者出厂价格指数 (上年同月=100)")]
    lp = nbs.latest(main[0]) if main else None
    if lp and state.get("latest_month") == f"{lp[:4]}-{lp[4:6]}-01" and not opts.get("force"):
        return {"updated": False, "code": state.get("code"), "summary": f"no new month (latest {state['latest_month'][:7]})"}
    raw, rows = {}, []
    for cid, meta in cats.items():
        inds = nbs.indicators(cid)
        if inds:
            r, data = nbs.table(cid, [x["_id"] for x in inds])
            raw[cid] = {"meta": meta, "data": data}
            rows += r
    tidy = _tidy(rows, False, warnings)
    pcats = nbs.catalogs("4", nbs.ROOT_PROVINCE, lambda p, n: "工业生产者" in (p + n))
    prow = []
    for cid, meta in pcats.items():
        inds = nbs.indicators(cid)
        if not inds:
            continue
        try:
            r, data = nbs.province_rows(cid, [x["_id"] for x in inds])
            raw["prov_" + cid] = {"meta": meta, "data": data}
            prow += r
        except nbs.NBSError as e:
            warnings.append(f"provinces, {meta['name']}: {e}")
    ptidy = _tidy(prow, True, warnings)

    errors = []
    nat = [v for v in tidy.values() if v["series"] == "ppi" and v["measure"] == "yoy"]
    if not nat:
        raise CheckFailed(["no national PPI y/y"])
    latest = max(v["date"] for v in nat)
    for key in ("ppi", "ppi_production", "ppi_consumer", "purchasing"):
        for m in ("yoy", "mom", "ytd"):
            if (latest[:7], "national", key, m) not in tidy:
                errors.append(f"latest month {latest[:7]}: {key} {m} missing")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month']})")
    hl = sorted(v["date"][:7] for v in nat)
    p, missing = hl[0], []
    while p <= hl[-1]:
        if (p, "national", "ppi", "yoy") not in tidy:
            missing.append(p)
        p = _shift(p, 1)
    if missing:
        errors.append(f"PPI y/y has gaps: {missing[:12]}")
    for v in list(tidy.values()) + list(ptidy.values()):
        if not 40 < v["value"] < 250:
            errors.append(f"{v['area']} {v['series']} {v['measure']} {v['date'][:7]} = {v['value']} out of range")
    # YTD in January equals y/y; YTD is the average of the year's y/y (within 0.15, NBS averages unrounded rates)
    bad, n = [], 0
    for (p, area, key, meas), v in tidy.items():
        if meas != "ytd":
            continue
        y, m = int(p[:4]), int(p[5:7])
        ys = [tidy.get((f"{y}-{i:02d}", area, key, "yoy")) for i in range(1, m + 1)]
        if any(x is None for x in ys):
            continue
        n += 1
        avg = sum(x["value"] for x in ys) / len(ys)
        if (m == 1 and abs(v["value"] - ys[0]["value"]) > 0.051) or abs(v["value"] - avg) > 0.15:
            bad.append(f"{key} {p}: YTD {v['value']} vs y/y average {avg:.2f}")
    if len(bad) > max(3, n // 100):
        errors.append(f"YTD inconsistent with y/y ({len(bad)} of {n}): {bad[:5]}")
    elif bad:
        warnings.append(f"YTD vs y/y average beyond 0.15 in {len(bad)} of {n}: {bad[:3]}")
    off, n2 = [], 0
    for (p, area, key, meas), v in tidy.items():
        if meas != "yoy" or key not in ("ppi", "purchasing", "ppi_production", "ppi_consumer"):
            continue
        ms = [tidy.get((_shift(p, -i), area, key, "mom")) for i in range(12)]
        if any(x is None for x in ms):
            continue
        n2 += 1
        c = 1.0
        for x in ms:
            c *= x["value"] / 100
        if abs(c * 100 - v["value"]) > 0.4:
            off.append(f"{key} {p}: y/y {v['value']} vs m/m compounded {c * 100:.2f}")
    if off:
        warnings.append(f"m/m compounded over 12 months differs from y/y by more than 0.4pp in {len(off)} of {n2} months: {off[:3]}")
    if errors:
        raise CheckFailed(errors)

    cols = ["date", "area", "area_name", "series", "label", "group", "order", "measure", "value", "pct", "base",
            "base_break", "ek"]
    out = sorted(list(tidy.values()) + list(ptidy.values()),
                 key=lambda r: (r["date"], r["area"] != "national", r["area"], r["order"], r["measure"]))
    for r in out:
        r["base_break"] = 1 if r["date"][:7] in BASE_STARTS else 0
    _write_csv(OUT / "cn_ppi.csv", cols, [r for r in out if r["area"] == "national"])
    _write_csv(OUT / "cn_ppi_provinces.csv", cols, [r for r in out if r["area"] != "national"])
    code = f"P{latest[:7]}"
    label = f"{LONGMONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    rel_date = ""
    cpi_rel = read_json(DATA / "cn" / "cpi" / "release.json", {}) or {}
    if cpi_rel.get("latest_month") == latest:
        rel_date = cpi_rel.get("release_date", "")   # CPI and PPI are released together

    def long_rows():
        for r in out:
            yield {"country": "CN", "indicator": "ppi", "series": f"{r['series']}_{r['measure']}", "label": r["label"],
                   "measure": r["measure"], "area": r["area"], "freq": "M", "date": r["date"], "value": r["pct"],
                   "unit": "%", "source": "National Bureau of Statistics of China", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    asia = [{"country": "CN", "concept": "ppi_yoy", "series_id": "cn.ppi.ppi.yoy", "date": r["date"], "value": r["pct"],
             "unit": "% y/y", "basis": "published", "source": "NBS", "base_break": r["base_break"],
             "release_date": rel_date if r["date"] == latest else ""}
            for r in out if r["area"] == "national" and r["series"] == "ppi" and r["measure"] == "yoy"]
    _write_csv(OUT / "asia.csv", ["country", "concept", "series_id", "date", "value", "unit", "basis", "source",
                                  "base_break", "release_date"], asia)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(raw, ensure_ascii=False).encode()
    (RAWDIR / f"{code}_{hashlib.sha256(blob).hexdigest()[:12]}.json.gz").write_bytes(gzip.compress(blob))
    release = {"code": code, "label": label, "latest_month": latest,
               "table": "NBS data portal (data.stats.gov.cn), monthly industrial producer price catalogs"}
    write_release(OUT, release, warnings, len(out), {"long_rows": nlong, "catalogs": len(cats), "province_catalogs": len(pcats)})
    return {"updated": True, "code": code, "summary": f"{label}: {len(tidy)} national and {len(ptidy)} provincial rows",
            "warnings": warnings}
