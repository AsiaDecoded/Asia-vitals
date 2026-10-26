"""Japan CPI: contributions to the y/y change in all items, Statistics Bureau, as published.

Source: Table 5 of each monthly CPI report on e-Stat ("品目別価格指数・寄与度（全国・東京都区部）月次"),
one Excel file per month, July 2016 onward. Each month's figures are taken from that month's own
report, on the base in use then (2015, 2020, 2025). The file catalogue is read through the e-Stat API
(needs ESTAT_APP_ID); the files themselves are public downloads. Each file is kept, gzipped, under
raw/jp/cpi_contrib/ and only new months are downloaded.

Series (national, percentage points): all items, fresh food, energy, goods, services, and
goods less fresh food and energy = goods - fresh food - energy (all three published).

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
            and state.get("items_months") == min(12, len(table)):
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
    items_by_month = {d: parse_items(gzip.decompress(have[d[:7]].read_bytes())) for d in item_months}
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
    with open(OUT / "jp_cpi_items.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "code", "name", "name_ja", "weight", "index", "mom", "yoy", "contrib_mom", "contrib_yoy"])
        for d in item_months:
            for i in items_by_month[d]:
                w.writerow([d, i["code"], names.get(i["code"], i["name_ja"]), i["name_ja"]] +
                           ["" if i[k] is None else i[k] for k in ("weight", "index", "mom", "yoy", "contrib_mom", "contrib_yoy")])
    write_release(OUT, release, warnings, len(out), {"long_rows": nlong, "new_months": new, "items": len(items),
                                                 "items_months": len(item_months)})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(table)} months, {len(new)} new",
            "warnings": warnings}
