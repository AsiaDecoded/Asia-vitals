"""Japan CPI: contributions to the y/y change in all items, Statistics Bureau, as published.

Source: Table 5 of each monthly CPI report on e-Stat ("品目別価格指数・寄与度（全国・東京都区部）月次"),
one Excel file per month, July 2016 onward. Each month's figures are taken from that month's own
report, on the base in use then (2015, 2020, 2025). The file catalogue is read through the e-Stat API
(needs ESTAT_APP_ID); the files themselves are public downloads. Each file is kept, gzipped, under
raw/jp/cpi_contrib/ and only new months are downloaded.

Series (national, percentage points): all items, fresh food, energy, goods, services, and
goods less fresh food and energy = goods - fresh food - energy (all three published).

Also writes jp_cpi_groups.csv: weight, y/y and contribution to the all-items y/y for the headline and core
measures, food and energy with the energy items, the 10 major groups with selected subgroups, and goods and
services (national, every month), as published in Table 5.

Also writes jp_cpi_items.csv: every individual item (not categories) in each of the last 12 months' Table 5,
national, with its weight, y/y, m/m and published contribution to the all-items y/y. English item
names come from the e-Stat API's English metadata for the 2025-base CPI table.
"""
import csv
import gzip
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_contrib_estat"
DESCRIPTION = "Japan CPI contributions to y/y (Statistics Bureau, Table 5)"
OUT = DATA / "jp" / "cpi_contrib"
RAWDIR = RAW / "jp" / "cpi_contrib"
API = "https://api.e-stat.go.jp/rest/3.0/app/json"
TITLE = "統計表_5_品目別価格指数・寄与度（全国・東京都区部）_月次"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# key, label, name in the table
ROWS = [("all", "All items", "総合"), ("fresh_food", "Fresh food", "生鮮食品"),
        ("energy", "Energy", "エネルギー"), ("goods", "Goods", "財"), ("services", "Services", "サービス")]
DERIVED = ("goods_core", "Goods less fresh food and energy")
ORDER = {"all": 0, "services": 1, "goods_core": 2, "energy": 3, "fresh_food": 4, "goods": 5}


def _call(method, params):
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        raise RuntimeError("ESTAT_APP_ID is not set (GitHub secret missing?)")
    url = f"{API}/{method}?{urllib.parse.urlencode({**params, 'appId': app_id})}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))


def _as_list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def _text(x):
    return x.get("$", "") if isinstance(x, dict) else (x or "")


def catalogue():
    """{YYYY-MM: statInfId} for every monthly Table 5 Excel file."""
    out, start = {}, 1
    while True:
        res = _call("getDataCatalog", {"statsCode": "00200573", "searchWord": "寄与度", "limit": 100,
                                       "startPosition": start})
        body = res["GET_DATA_CATALOG"]
        st = body["RESULT"]["STATUS"]
        if st == 1:
            break
        if st != 0:
            raise RuntimeError(f"e-Stat catalogue error {st}: {body['RESULT'].get('ERROR_MSG')}")
        dl = body.get("DATA_CATALOG_LIST_INF", {})
        for d in _as_list(dl.get("DATA_CATALOG_INF")):
            ds = d.get("DATASET", {})
            dname = _text(ds.get("TITLE", {}).get("NAME") if isinstance(ds.get("TITLE"), dict) else ds.get("TITLE"))
            m = re.search(r"月報_月次_(\d{4})年(\d{1,2})月$", dname)
            if not m:
                continue
            for r in _as_list(d.get("RESOURCES", {}).get("RESOURCE")):
                t = r.get("TITLE", {})
                if (t.get("NAME") if isinstance(t, dict) else t) != TITLE or r.get("FORMAT") != "XLS":
                    continue
                sid = re.search(r"statInfId=(\d+)", r.get("URL", ""))
                if sid:
                    out[f"{m.group(1)}-{int(m.group(2)):02d}"] = sid.group(1)
        nxt = dl.get("RESULT_INF", {}).get("NEXT_KEY")
        if not nxt:
            break
        start = int(nxt)
    return out


def download(sid):
    url = f"https://www.e-stat.go.jp/stat-search/file-download?statInfId={sid}&fileKind=0"
    req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))


def _sheet_rows(data):
    if data[:4] == b"PK\x03\x04":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    import xlrd
    s = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
    return [s.row_values(i) for i in range(s.nrows)]


def _norm(x):
    s = re.sub(r"\s+", "", str(x if x is not None else ""))
    return re.sub(r"\([a-z]\)$|（[a-z]）$", "", s)


def parse(data):
    """{key: national contribution to y/y, pp} from one Table 5 file."""
    rows = _sheet_rows(data)
    col = None
    for r in rows[:20]:
        for j, c in enumerate(r):
            if "前年同月比に対する寄与度" in _norm(c):
                col = j
                break
        if col is not None:
            break
    if col is None:
        raise ValueError("no 'contribution to y/y' column found")
    found = {}
    for r in rows:
        if len(r) <= col:
            continue
        names = {_norm(c) for c in r[:col - 5] if isinstance(c, str)}
        for key, _, name in ROWS:
            if key not in found and name in names:
                v = r[col]
                try:
                    found[key] = float(v)
                except (TypeError, ValueError):
                    found[key] = None
    return found


# Table 5 categories kept for the heat and contribution tables: name in the table, key, English label,
# block (top: headline and core measures with food and energy; div: the 10 major groups; gs: goods and
# services), parent key (for rows shown under another row). The first row with that name is used.
GROUPS = [
    ("総合", "all", "All items", "top", None),
    ("生鮮食品を除く総合", "core", "Core (less fresh food)", "top", None),
    ("生鮮食品及びエネルギーを除く総合", "core1", "Core 1 (less fresh food and energy)", "top", None),
    ("生鮮食品", "fresh_food", "Fresh food", "top", None),
    ("生鮮食品を除く食料", "food_ex_fresh", "Food less fresh food", "top", None),
    ("エネルギー", "energy", "Energy", "top", None),
    ("電気代", "electricity", "Electricity", "top", "energy"),
    ("都市ガス代", "city_gas", "City gas", "top", "energy"),
    ("プロパンガス", "lp_gas", "LP gas", "top", "energy"),
    ("灯油", "kerosene", "Kerosene", "top", "energy"),
    ("ガソリン", "gasoline", "Gasoline", "top", "energy"),
    ("食料", "d_food", "Food", "div", None),
    ("外食", "d_eating_out", "Eating out", "div", "d_food"),
    ("住居", "d_housing", "Housing", "div", None),
    ("家賃", "d_rent", "Rent (incl. imputed rent)", "div", "d_housing"),
    ("持家の帰属家賃", "d_imputed_rent", "Imputed rent", "div", "d_housing"),
    ("設備修繕・維持", "d_repairs", "Repairs and maintenance", "div", "d_housing"),
    ("光熱・水道", "d_fuel", "Fuel, light and water", "div", None),
    ("家具・家事用品", "d_furniture", "Furniture and household goods", "div", None),
    ("被服及び履物", "d_clothing", "Clothing and footwear", "div", None),
    ("保健医療", "d_medical", "Medical care", "div", None),
    ("保健医療サービス", "d_medical_services", "Medical services", "div", "d_medical"),
    ("交通・通信", "d_transport", "Transport and communication", "div", None),
    ("交通", "d_public_transport", "Public transport", "div", "d_transport"),
    ("自動車等関係費", "d_motoring", "Motoring costs", "div", "d_transport"),
    ("通信", "d_communication", "Communication", "div", "d_transport"),
    ("教育", "d_education", "Education", "div", None),
    ("授業料等", "d_tuition", "Tuition fees", "div", "d_education"),
    ("教養娯楽", "d_culture", "Culture and recreation", "div", None),
    ("教養娯楽サービス", "d_rec_services", "Recreational services", "div", "d_culture"),
    ("諸雑費", "d_misc", "Miscellaneous", "div", None),
    ("財", "d_goods", "Goods", "gs", None),
    ("サービス", "d_services", "Services", "gs", None),
    ("持家の帰属家賃を除くサービス", "d_services_ex_rent", "Services less imputed rent", "gs", None),
]
GROUPS_VERSION = 1


def parse_groups(data):
    """{key: {weight, yoy, contrib}} for the GROUPS rows, national, from one Table 5 file (either layout)."""
    rows = _sheet_rows(data)
    jw = jy = jc = None
    for r in rows[:20]:
        for j, c in enumerate(r):
            k = _norm(c)
            if jw is None and k.startswith("ウエイト"):
                jw = j
            if jy is None and k == "前年同月比":
                jy = j
            if jc is None and "前年同月比に対する寄与度" in k:
                jc = j
    if None in (jw, jy, jc):
        raise ValueError("weight, y/y or contribution column not found")

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    by_name = {g[0]: g for g in GROUPS}
    out = {}
    for r in rows:
        if len(r) <= max(jw, jy, jc):
            continue
        for c in r[:jw]:
            name = _norm(c) if isinstance(c, str) else ""
            g = by_name.get(name)
            if g and g[1] not in out:
                out[g[1]] = {"weight": num(r[jw]), "yoy": num(r[jy]), "contrib": num(r[jc])}
                break
    return out


def parse_items(data):
    """Individual items (codes not starting with 0) with national weight, index, m/m, y/y and contribution."""
    rows = _sheet_rows(data)
    hdr = None
    for i, r in enumerate(rows[:20]):
        if any(_norm(c) == "類・品目符号" for c in r):
            hdr = i
            break
    if hdr is None:
        raise ValueError("no item-code header row")
    cols = {_norm(c): j for j, c in enumerate(rows[hdr]) if c}
    jc, jn = cols["類・品目符号"], cols["類・品目"]
    # the national block: first occurrence of each measure in the 表章項目 row
    meas_row = next(r for r in rows[:20] if any(_norm(c) == "表章項目" for c in r))
    first = {}
    for j, c in enumerate(meas_row):
        k = _norm(c)
        if k and k not in first:
            first[k] = j
    def col(prefix):
        return next(j for k, j in first.items() if k.startswith(prefix))
    jw, ji, jm, jy = col("ウエイト"), col("指数"), col("前月比"), col("前年同月比")
    jcy = col("総合指数の前年同月比に対する寄与度")
    jcm = col("総合指数の前月比に対する寄与度")

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    out = []
    for r in rows[hdr + 1:]:
        if len(r) <= max(jcy, jcm):
            continue
        code = str(r[jc] or "").strip()
        if not re.fullmatch(r"[1-9]\d{3}", code):
            continue
        out.append({"code": code, "name_ja": str(r[jn]).strip(), "weight": num(r[jw]), "index": num(r[ji]),
                    "mom": num(r[jm]), "yoy": num(r[jy]), "contrib_mom": num(r[jcm]), "contrib_yoy": num(r[jcy])})
    return out


def parse_items_old(data):
    """Older Table 5 layout (no item codes): items are the leaf rows of the name hierarchy, up to the
    special aggregates that start at 生鮮食品. Returns [{name_ja, weight, yoy}]."""
    rows = _sheet_rows(data)
    yc = wc = None
    for r in rows[:20]:
        for j, c in enumerate(r):
            k = _norm(c)
            if yc is None and k == "前年同月比":
                yc = j
            if wc is None and k.startswith("ウエイト"):
                wc = j
    if yc is None or wc is None:
        raise ValueError("no weight or y/y column in the older layout")
    recs = []
    for r in rows:
        if len(r) <= yc:
            continue
        lv = name = None
        for j in range(5, wc):
            v = r[j]
            if isinstance(v, str) and v.strip() and not re.fullmatch(r"[\d\s]+", v.strip()):
                lv, name = j, v.strip()
                break
        if lv is None:
            continue
        if _norm(name).startswith("生鮮食品"):
            break
        try:
            w, y = float(r[wc]), float(r[yc])
        except (TypeError, ValueError):
            w = y = None
        recs.append((lv, name, w, y))
    out = []
    for i, (lv, name, w, y) in enumerate(recs):
        nxt = recs[i + 1][0] if i + 1 < len(recs) else -1
        if nxt <= lv and w and _norm(name) != "総合":
            out.append({"name_ja": name, "weight": w, "yoy": y})
    return out


def diffusion(data):
    """Share of CPI items (all individual items, unweighted) with y/y above and below zero."""
    try:
        items = [{"weight": i["weight"], "yoy": i["yoy"]} for i in parse_items(data)]
    except ValueError:
        items = parse_items_old(data)
    ys = [i["yoy"] for i in items if i["weight"] and i["yoy"] is not None]
    n = len(ys)
    if n < 400:
        raise ValueError(f"only {n} items with a y/y")
    up, down = sum(v > 0 for v in ys), sum(v < 0 for v in ys)
    return {"items": n, "rising": up, "falling": down, "unchanged": n - up - down,
            "share_rising": round(up / n * 100, 1), "share_falling": round(down / n * 100, 1),
            "diffusion": round((up - down) / n * 100, 1)}


def english_names():
    """{item code: English name} from the e-Stat English metadata of the 2025-base CPI table."""
    res = _call("getMetaInfo", {"statsDataId": "0004052037", "lang": "E"})
    meta = res["GET_META_INFO"].get("METADATA_INF", {})
    for c in _as_list(meta.get("CLASS_INF", {}).get("CLASS_OBJ")):
        if c.get("@id") == "cat01":
            return {i["@code"]: re.sub(r"^\d{4}\s*", "", i.get("@name", "")).strip()
                    for i in _as_list(c.get("CLASS"))}
    return {}


def _full_names(names):
    """e-Stat lists sub-items under a parent as '(elementary school)'; prefix the parent's name."""
    out, base = {}, ""
    for code, name in names.items():
        if name.startswith("(") and base:
            out[code] = f"{base} {name}"
        else:
            out[code] = name
            base = name
    return out


def _mlabel(d):
    return f"{MONTHS[int(d[5:7]) - 1]} {d[:4]}"


def _checks(table):
    errors, warnings = [], []
    for month, v in sorted(table.items()):
        miss = [k for k, _, _ in ROWS if v.get(k) is None]
        if miss:
            errors.append(f"{month}: missing {', '.join(miss)}")
            continue
        gap = v["goods"] + v["services"] - v["all"]
        if abs(gap) > 0.1:
            errors.append(f"{month}: goods + services = {v['goods'] + v['services']:.2f} vs all items {v['all']:.2f}")
        if not -15 < v["all"] < 15:
            errors.append(f"{month}: all items {v['all']} out of range")
    return errors, warnings


def update(from_dir=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    have = {p.name.split("_")[0]: p for p in RAWDIR.glob("*.gz")}
    new = []
    if not from_dir:
        for month, sid in sorted(catalogue().items()):
            p = RAWDIR / f"{month}_{sid}.gz"
            if month in have and have[month].name == p.name:
                continue
            p.write_bytes(gzip.compress(download(sid)))
            if month in have:
                have[month].unlink()
            have[month] = p
            new.append(month)
            time.sleep(1)
    table = {}
    for month, p in sorted(have.items()):
        table[f"{month}-01"] = parse(gzip.decompress(p.read_bytes()))
    if not table:
        raise CheckFailed(["no Table 5 files found in the e-Stat catalogue"])
    latest = max(table)
    if not new and state.get("latest_month") == latest and not from_dir and (OUT / "jp_cpi_items.csv").exists() \
            and state.get("items_months") == min(12, len(table)) \
            and state.get("diffusion_months") == len(table) \
            and state.get("groups_version") == GROUPS_VERSION:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {latest[:7]})"}

    errors, warnings = _checks(table)
    if errors:
        raise CheckFailed(errors)
    code = f"C{latest[:7]}"
    release = {"code": code, "label": _mlabel(latest), "latest_month": latest, "first_month": min(table),
               "table": "e-Stat CPI monthly report, Table 5"}
    labels = {k: lab for k, lab, _ in ROWS}
    labels[DERIVED[0]] = DERIVED[1]
    out = []
    for d, v in sorted(table.items()):
        v = dict(v)
        v["goods_core"] = round(v["goods"] - v["fresh_food"] - v["energy"], 2)
        for k in ORDER:
            out.append({"date": d, "series": k, "label": labels[k], "order": ORDER[k], "contrib_yoy": v[k]})
    # item detail for the latest month
    # last 12 months, each from its own report (base in use at the time)
    item_months = sorted(table)[-12:]
    items_by_month = {}
    for d in item_months:
        try:
            items_by_month[d] = parse_items(gzip.decompress(have[d[:7]].read_bytes()))
        except Exception as e:  # noqa: BLE001 - an older layout; the latest month is checked below
            warnings.append(f"items not read for {d[:7]}: {e}")
    item_months = [d for d in item_months if d in items_by_month]
    if latest not in items_by_month:
        raise CheckFailed([f"items could not be read from the latest Table 5 ({latest[:7]})"])
    items = items_by_month[latest]
    OUT.mkdir(parents=True, exist_ok=True)
    names_path = OUT / "item_names_en.json"
    names = read_json(names_path, {}) or {}
    if from_dir is None and any(i["code"] not in names for i in items):
        try:
            names = english_names() or names
            names_path.write_text(json.dumps(names, ensure_ascii=False, indent=1) + "\n")
        except Exception as e:  # noqa: BLE001 - English names are a nicety; keep Japanese if the call fails
            warnings.append(f"English item names not refreshed: {e}")
    names = _full_names(names)
    if len(items) < 400:
        raise CheckFailed([f"only {len(items)} items parsed from the latest Table 5"])
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "jp_cpi_contrib.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series", "label", "order", "contrib_yoy"])
        for r in out:
            w.writerow([r["date"], r["series"], r["label"], r["order"], r["contrib_yoy"]])
    nlong = write_long(({"country": "JP", "indicator": "cpi_contrib", "series": r["series"], "label": r["label"],
                         "measure": "contrib_yoy", "area": "national", "freq": "M", "date": r["date"],
                         "value": r["contrib_yoy"], "unit": "pp", "source": "Statistics Bureau of Japan",
                         "release": code} for r in out), OUT / "long.csv")
    diff, diff_errors = {}, []
    for d in sorted(table):
        try:
            diff[d] = diffusion(gzip.decompress(have[d[:7]].read_bytes()))
        except Exception as e:  # noqa: BLE001
            diff_errors.append(f"{d[:7]}: {e}")
    if latest not in diff:
        raise CheckFailed(["diffusion index could not be built for the latest month"] + diff_errors[:5])
    if diff_errors:
        warnings.append(f"diffusion index missing for {len(diff_errors)} month(s): " + "; ".join(diff_errors[:3]))
    with open(OUT / "jp_cpi_diffusion.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        cols = ["items", "rising", "falling", "unchanged", "share_rising", "share_falling", "diffusion"]
        w.writerow(["date"] + cols)
        for d in sorted(diff):
            w.writerow([d] + [diff[d][c] for c in cols])
    groups, group_errors = {}, []
    for d in sorted(table):
        try:
            groups[d] = parse_groups(gzip.decompress(have[d[:7]].read_bytes()))
        except Exception as e:  # noqa: BLE001
            group_errors.append(f"{d[:7]}: {e}")
    if latest not in groups or any(groups[latest].get(k) is None for _, k, *_r in GROUPS):
        raise CheckFailed(["category rows could not all be read from the latest Table 5"] + group_errors[:5])
    if group_errors:
        warnings.append(f"category rows missing for {len(group_errors)} month(s): " + "; ".join(group_errors[:3]))
    lat = groups[latest]
    if abs(lat["d_goods"]["contrib"] + lat["d_services"]["contrib"] - lat["all"]["yoy"]) > 0.1:
        raise CheckFailed([f"{latest[:7]}: goods + services contributions don't add to the all-items y/y"])
    with open(OUT / "jp_cpi_groups.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "series", "label", "order", "block", "parent", "weight", "yoy", "contrib_yoy"])
        for d in sorted(groups):
            for i, (_, k, lab, blk, par) in enumerate(GROUPS):
                v = groups[d].get(k)
                if not v:
                    continue
                w.writerow([d, k, lab, i, blk, par or ""] +
                           ["" if v[m] is None else v[m] for m in ("weight", "yoy", "contrib")])
    with open(OUT / "jp_cpi_items.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "code", "name", "name_ja", "weight", "index", "mom", "yoy", "contrib_mom", "contrib_yoy"])
        for d in item_months:
            for i in items_by_month[d]:
                w.writerow([d, i["code"], names.get(i["code"], i["name_ja"]), i["name_ja"]] +
                           ["" if i[k] is None else i[k] for k in ("weight", "index", "mom", "yoy", "contrib_mom", "contrib_yoy")])
    write_release(OUT, release, warnings, len(out), {"long_rows": nlong, "new_months": new, "items": len(items),
                                                 "items_months": len(item_months),
                                                 "diffusion_months": len(diff),
                                                 "groups_version": GROUPS_VERSION})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(table)} months, {len(new)} new",
            "warnings": warnings}
