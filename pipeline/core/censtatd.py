"""Hong Kong Census and Statistics Department (C&SD): clients for the open data it publishes (no key).

- table(id): web-table API (api/get.php), a whole table as JSON rows.
- issues(product): the issues of a statistical product (report_element_index.json + report_element_<id>.json).
- e501(code): Table E501 (CPI by section and group), the CSV zip published with each release.
- report(code): one issue of the web Monthly Report on the CPI: wbr.json, and per table its component
  definition, labels and data files (the CSVs the report page reads).
- annex_weights(code): Annex 1 to the monthly report (XLSX), CPI expenditure weights.
- schedule(): C&SD's release schedule (the JSON behind press_release.html).

All C&SD hosts are blocked from the Claude sandbox; run from GitHub Actions.
"""
import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

BASE = "https://www.censtatd.gov.hk"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)", "Accept": "*/*"}


def get(url, tries=4, timeout=150):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(f"C&SD 404: {url}") from e
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(4 * (i + 1))
    raise RuntimeError(f"C&SD request failed: {url}: {err!r}")


def get_json(url):
    return json.loads(get(url).decode("utf-8-sig"))


def table(tid):
    """(header, rows) of a web table; rows are dicts with sv, svDesc, period, figure, sd_value and the table's
    classification fields (e.g. GROUP/GROUPDesc, COICOP/COICOPDesc, IND/INDDesc)."""
    o = get_json(f"{BASE}/api/get.php?{urllib.parse.urlencode({'id': tid, 'lang': 'en', 'full_series': 1})}")
    st = (o.get("header") or {}).get("status") or {}
    if st.get("code") not in (0, "0"):
        raise RuntimeError(f"C&SD table {tid}: {st}")
    rows = o.get("dataSet") or []
    for r in rows:
        # "[§3]", "[φ3]", "[§34]": change of less than 0.05%, published as 0.0 (some tables leave the figure blank)
        if r.get("figure") in ("", None) and re.fullmatch(r"\[[§φ]3\d?\]", (r.get("sd_value") or "").strip()):
            r["figure"] = 0.0
    return o["header"], rows


def issues(product, n=60):
    """Latest n issues of a product, newest first: [{id, code, issue, eff, file, att}]."""
    idx = get_json(f"{BASE}/en/data/stat_report/product/{product}/report_element_index.json").get("elementindex") or []
    out = []
    for k in idx[:n]:
        o = get_json(f"{BASE}/en/data/stat_report/product/{product}/report_element_{k}.json")
        e = (o.get("elementlist") or [{}])[0]
        out.append({"id": k, "code": e.get("Element_Code"), "issue": e.get("Issue"), "eff": e.get("Eff_Date"),
                    "web": e.get("Is_Web_Rpt") == "1", "file": e.get("en_file"),
                    "att": [a.get("File_Name") for a in o.get("att") or []]})
    return out


def _num(s):
    s = (s or "").strip().replace(",", "")
    if s in ("", "n.a.", "N.A.", "-", "*"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_e501_csv(text):
    """One E501 sheet: {"codes": [...], "names": {code: name}, "rows": [(date, code, index, yoy, mom)]}.

    Layout: row 2 group codes (three columns each), row 4 English names, row 6 measure names, then annual rows
    (year, blank month) and monthly rows (year, month); notes follow."""
    rows = list(csv.reader(io.StringIO(text)))
    codes_row, names_row = rows[2], rows[4]
    cols = []
    for j in range(2, len(codes_row), 3):
        c = codes_row[j].strip()
        if not c:
            continue
        cols.append((j, c, names_row[j].strip()))
    out = []
    for r in rows[7:]:
        if len(r) < 3 or not re.fullmatch(r"\d{4}", (r[0] or "").strip()) or not re.fullmatch(r"\d{1,2}", (r[1] or "").strip()):
            continue
        d = f"{int(r[0]):04d}-{int(r[1]):02d}-01"
        for j, c, _ in cols:
            vals = [_num(r[j + k]) if j + k < len(r) else None for k in range(3)]
            if any(v is not None for v in vals):
                out.append((d, c, *vals))
    return {"codes": [c for _, c, _ in cols], "names": {c: n for _, c, n in cols}, "rows": out}


def e501(code):
    """Table E501 for an issue code (D5600001<yyyy>MM<mm>): {sheet: parsed} for E501-1 … E501-8, and the raw zip."""
    name = f"D5600001B{code[8:]}B.zip"
    raw = get(f"{BASE}/en/data/stat_report/product/D5600001/att/{name}")
    z = zipfile.ZipFile(io.BytesIO(raw))
    out = {}
    for n in z.namelist():
        m = re.search(r"-(E501-\d)\.CSV$", n, re.I)
        if m:
            out[m.group(1)] = parse_e501_csv(z.read(n).decode("utf-8-sig"))
    return out, raw


def report(code, tables=None):
    """One web issue of the Monthly Report on the CPI (B1060001<yyyy>MM<mm>).

    Returns {"wbr": wbr.json, "tables": {tid: {"comp", "lang", "data": {(stat_var, stat_pres): csv text}}}}.
    tables: only these table ids (default: all in tb_code_list)."""
    d = f"{BASE}/wbr/B1060001/{code}/data/"
    wbr = get_json(f"{d}en/wbr.json")
    out = {"wbr": wbr, "tables": {}}
    for tid in wbr.get("tb_code_list") or []:
        if tables and tid not in tables:
            continue
        comp = get_json(f"{d}table_{tid}_comp.json")
        lang = get_json(f"{d}en/table_{tid}_lang.json")
        data = {}
        for c in comp.get("table_component_list") or []:
            fn = f"MDT_{comp.get('theme_id')}_{tid}_{c['stat_var']}_{c['stat_pres']}.csv".replace("%", "percent").replace("$", "dollar")
            data[(c["stat_var"], c["stat_pres"])] = get(d + urllib.parse.quote(fn)).decode("utf-8-sig")
        out["tables"][tid] = {"comp": comp, "lang": lang, "data": data}
    return out


def class_labels(lang, cv="GROUP"):
    """{class code: label} for a classification variable in a table's _lang.json."""
    out = {}
    for g in (((lang.get("cv_list") or {}).get(cv) or {}).get("ccg_list") or {}).values():
        for c, v in (g.get("cc_list") or {}).items():
            out[c] = v.get("def_class_code_desc")
    return out


def annex_links(wbr):
    """Links in the report's explanatory notes: {title: absolute URL} (Annex 1 holds the weights)."""
    s = json.dumps(wbr, ensure_ascii=False)
    out = {}
    for m in re.finditer(r'href=\\"(/wbr/[^"\\]+)\\"[^>]*>([^<]+)<', s):
        out[re.sub(r"\s+", " ", m.group(2)).strip()] = BASE + m.group(1).replace(" ", "%20")
    return out


def schedule():
    """C&SD's release schedule: [{date, title, series_code}] from press_release_index.json (past and future)."""
    o = get_json(f"{BASE}/data/en/press_release/press_release_index.json")
    return [{"date": (r.get("startTime") or "")[:10], "title": r.get("title"), "series_code": r.get("Series_Code")}
            for r in o.get("press_release") or []]
