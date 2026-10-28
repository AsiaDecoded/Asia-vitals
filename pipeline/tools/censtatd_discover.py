"""Probe Hong Kong price data sources from GitHub Actions and save every response.

Usage: python -I pipeline/tools/censtatd_discover.py discovery/censtatd

Probes, in order: C&SD web-table API (get.php), the data.gov.hk catalogue (CKAN) for
C&SD price tables, C&SD subject and calendar pages, the government press releases (GIA)
for October 2026, HKMA's API, and the headline-only fallbacks (IMF, OECD, DBnomics).
Writes raw responses (gzipped), a log of every call (status, bytes, error) and a
summary of each C&SD table found (dimensions, series, first and last period).
"""
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)",
      "Accept": "application/json, text/html, */*"}
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/censtatd")
OUT.mkdir(parents=True, exist_ok=True)
LOG = []


def fetch(name, url, ext=".json", data=None, keep=True, timeout=90):
    t0 = time.time()
    rec = {"name": name, "url": url}
    try:
        req = urllib.request.Request(url, headers=UA, data=data)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            rec.update(status=r.status, bytes=len(body), ctype=r.headers.get("Content-Type"))
    except urllib.error.HTTPError as e:
        body = e.read() or b""
        rec.update(status=e.code, bytes=len(body), error=f"HTTPError {e.code} {e.reason}",
                   head=body[:400].decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        body = b""
        rec.update(status=None, error=repr(e))
    rec["secs"] = round(time.time() - t0, 1)
    LOG.append(rec)
    print(json.dumps({k: rec.get(k) for k in ("name", "status", "bytes", "error", "secs")}), flush=True)
    if keep and body:
        (OUT / f"{name}{ext}.gz").write_bytes(gzip.compress(body))
    return rec.get("status"), body


def as_json(body):
    try:
        return json.loads(body.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


CSD = "https://www.censtatd.gov.hk"


def summarise_table(tid, obj):
    """Generic summary of a get.php response: top-level keys, dimension names and values, periods."""
    s = {"id": tid, "top_keys": list(obj.keys()) if isinstance(obj, dict) else type(obj).__name__}
    rows = None
    if isinstance(obj, dict):
        for k in ("dataSet", "dataset", "data", "records"):
            if isinstance(obj.get(k), list):
                rows = obj[k]
                s["rows_key"] = k
                break
        hdr = obj.get("header")
        if hdr is not None:
            s["header"] = json.dumps(hdr, ensure_ascii=False)[:3000]
    if rows:
        s["n_rows"] = len(rows)
        s["row_keys"] = sorted({k for r in rows[:500] if isinstance(r, dict) for k in r})
        vals = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if k.lower() in ("figure", "value", "obs_value"):
                    continue
                vals.setdefault(k, set()).add(str(v))
        s["distinct"] = {k: (sorted(v)[:80] if len(v) <= 80 else sorted(v)[:40] + [f"... {len(v)} values"])
                         for k, v in vals.items()}
        s["sample_rows"] = rows[:5]
    return s


def main():
    tables = {}

    # 1. data.gov.hk catalogue (CKAN): list C&SD table datasets, keep price ones
    ck = []
    for q in ("hk-censtatd-tablechart-510", "consumer price index censtatd", "price index censtatd"):
        for base in ("https://data.gov.hk/en-data/api/3/action/package_search",
                     "https://data.gov.hk/tc-data/api/3/action/package_search"):
            st, body = fetch(f"ckan_{re.sub(r'[^a-z0-9]+', '_', q)}_{base.split('/')[3]}",
                             f"{base}?{urllib.parse.urlencode({'q': q, 'rows': 1000})}")
            o = as_json(body) if st == 200 else None
            if o and o.get("success"):
                ck += (o.get("result") or {}).get("results") or []
                break
    st, body = fetch("ckan_package_list", "https://data.gov.hk/en-data/api/3/action/package_list")
    pkgs = (as_json(body) or {}).get("result") or [] if st == 200 else []
    ids = set()
    for p in pkgs:
        m = re.match(r"hk-censtatd-tablechart-(\d{3}-\d{5})$", p)
        if m:
            ids.add(m.group(1))
    cat = {}
    for p in ck:
        m = re.match(r"hk-censtatd-tablechart-(\d{3}-\d{5})$", p.get("name", ""))
        if m:
            ids.add(m.group(1))
            cat[m.group(1)] = {"title": p.get("title"), "notes": (p.get("notes") or "")[:300],
                               "resources": [{"name": r.get("name"), "url": r.get("url"), "format": r.get("format")}
                                             for r in p.get("resources") or []][:6]}
    (OUT / "ckan_censtatd_tables.json").write_text(json.dumps(
        {"all_censtatd_table_ids": sorted(ids), "price_search_hits": cat}, ensure_ascii=False, indent=1))
    print(f"catalogue: {len(ids)} C&SD table ids, {len(cat)} search hits", flush=True)

    # 2. C&SD get.php: CPI range plus any catalogue id in 510-* (prices) or with 'price' in the title
    cand = {f"510-600{n:02d}" for n in range(1, 31)}
    cand |= {i for i in ids if i.startswith("510-")}
    cand |= {i for i, c in cat.items() if "price" in (c.get("title") or "").lower()}
    for tid in sorted(cand):
        url = f"{CSD}/api/get.php?{urllib.parse.urlencode({'id': tid, 'lang': 'en', 'full_series': 1})}"
        st, body = fetch(f"csd_{tid}", url, timeout=150)
        o = as_json(body) if st == 200 and body else None
        if o is not None:
            tables[tid] = summarise_table(tid, o)
            if tid in cat:
                tables[tid]["catalogue_title"] = cat[tid]["title"]
        time.sleep(0.5)
    (OUT / "csd_tables_summary.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1, default=str))

    # 3. C&SD pages: CPI subject page, monthly report page, release calendar candidates
    for name, url in [
        ("csd_scode270", f"{CSD}/en/scode270.html"),
        ("csd_monthly_report_page", f"{CSD}/en/EIndexbySubject.html?pcode=B1060001&scode=270"),
        ("csd_home", f"{CSD}/en/"),
        ("csd_calendar_1", f"{CSD}/en/press_release_calendar.html"),
        ("csd_calendar_2", f"{CSD}/en/ReleaseCalendar.html"),
        ("csd_web_table_510_60001", f"{CSD}/en/web_table.html?id=510-60001"),
    ]:
        fetch(name, url, ext=".html")

    # 4. Government press releases (GIA): daily index pages for 15-31 Oct 2026, find the CPI release
    found = []
    for d in range(15, 32):
        st, body = fetch(f"gia_index_202610{d:02d}", f"https://www.info.gov.hk/gia/general/202610/{d:02d}.htm",
                         ext=".html", keep=False)
        txt = body.decode("utf-8", "replace") if body else ""
        for m in re.finditer(r'href="([^"]+P2026\d+\.htm)"[^>]*>([^<]*Consumer Price Ind[^<]*)<', txt):
            found.append({"day": d, "href": m.group(1), "title": m.group(2).strip()})
    for i, f in enumerate(found):
        href = urllib.parse.urljoin("https://www.info.gov.hk/gia/general/202610/01.htm", f["href"])
        f["url"] = href
        st, body = fetch(f"gia_cpi_release_{i}", href, ext=".html")
        txt = body.decode("utf-8", "replace") if body else ""
        f["pdfs"] = sorted(set(re.findall(r'https?://gia\.info\.gov\.hk/[^"\']+\.pdf', txt)))
    (OUT / "gia_cpi_releases_oct2026.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))

    # 5. HKMA API: documentation pages and the public API root
    fetch("hkma_apidocs", "https://apidocs.hkma.gov.hk/documentation/", ext=".html")
    fetch("hkma_msb_list", "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin")

    # 6. Headline-only fallbacks
    imf = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI"
    fetch("imf_cpi_index_m", f"{imf}/HKG.CPI._T.IX.M?startPeriod=1970", ext=".xml")
    fetch("imf_cpi_yoy_m", f"{imf}/HKG.CPI._T.YOY_PCH_PA_PT.M?startPeriod=1970", ext=".xml")
    o = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
    fetch("oecd_cpi_hkg", f"{o}/HKG.M......?startPeriod=2024-01&format=csvfilewithlabels", ext=".csv")
    d = "https://api.db.nomics.world/v22"
    fetch("dbnomics_search", f"{d}/search?{urllib.parse.urlencode({'q': 'Hong Kong consumer price', 'limit': 50})}")
    fetch("dbnomics_imf_cpi_hkg", f"{d}/series/IMF/CPI?{urllib.parse.urlencode({'dimensions': json.dumps({'REF_AREA': ['HK']}), 'observations': 1, 'limit': 20})}")

    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def round2():
    """Section-level tables, the monthly report's Excel/CSV/XML files, catalogue entries for
    reports and trade price indices, and the C&SD release schedules."""
    for tid in ("510-60001A", "510-60002A"):
        fetch(f"csd_{tid}", f"{CSD}/api/get.php?{urllib.parse.urlencode({'id': tid, 'lang': 'en', 'full_series': 1})}",
              timeout=150)
    for ym in ("2026MM09", "2026MM08"):
        code = f"B1060001{ym}"
        for fmt, ext in (("excel", ".xlsx"), ("csv", ".csv"), ("xml", ".xml")):
            if ym != "2026MM09" and fmt != "excel":
                continue
            fetch(f"report_{code}_{fmt}", f"{CSD}/en/wbr.html?ecode={code}&download_{fmt}=1", ext=ext, timeout=150)
        fetch(f"report_{code}_page", f"{CSD}/en/wbr.html?ecode={code}", ext=".html")
    ck = "https://data.gov.hk/en-data/api/3/action"
    for pk in ("b1060001", "b1060003", "b1070003", "d5600001", "fa100117", "fa100024", "510-60001a", "520-62001"):
        fetch(f"ckan_show_{pk}", f"{ck}/package_show?id=hk-censtatd-tablechart-{pk}")
    hits = {}
    for q in ("unit value index", "trade index numbers", "import price", "export price",
              "Consumer Price Index weights", "Household Expenditure Survey"):
        st, body = fetch(f"ckan_q_{re.sub(r'[^a-z0-9]+', '_', q.lower())}",
                         f"{ck}/package_search?{urllib.parse.urlencode({'q': q, 'fq': 'organization:hk-censtatd', 'rows': 200})}")
        o = as_json(body) if st == 200 else None
        for p in ((o or {}).get("result") or {}).get("results") or []:
            hits[p["name"]] = {"title": p.get("title"),
                               "resources": [r.get("url") for r in p.get("resources") or []][:4]}
        if not ((o or {}).get("result") or {}).get("results"):
            st, body = fetch(f"ckan_q2_{re.sub(r'[^a-z0-9]+', '_', q.lower())}",
                             f"{ck}/package_search?{urllib.parse.urlencode({'q': q + ' censtatd', 'rows': 200})}")
            o = as_json(body) if st == 200 else None
            for p in ((o or {}).get("result") or {}).get("results") or []:
                if "censtatd" in p["name"]:
                    hits[p["name"]] = {"title": p.get("title"),
                                       "resources": [r.get("url") for r in p.get("resources") or []][:4]}
    (OUT / "ckan_hits_round2.json").write_text(json.dumps(hits, ensure_ascii=False, indent=1))
    # Release schedules: 2026 (announced Sep 2025) and 2027 (announced around mid-Sep 2026)
    fetch("gia_schedule_2026", "https://www.info.gov.hk/gia/general/202509/15/P2025091200738.htm", ext=".html")
    found = []
    for d in range(8, 31):
        st, body = fetch(f"gia_index_202609{d:02d}", f"https://www.info.gov.hk/gia/general/202609/{d:02d}.htm",
                         ext=".html", keep=False)
        txt = body.decode("utf-8", "replace") if body else ""
        for m in re.finditer(r'href="([^"]+P20\d+\.htm)"[^>]*>([^<]*(?:schedule|Schedule)[^<]*)<', txt):
            found.append({"day": d, "href": m.group(1), "title": m.group(2).strip()})
    for i, f in enumerate(found):
        f["url"] = urllib.parse.urljoin("https://www.info.gov.hk/gia/general/202609/01.htm", f["href"])
        fetch(f"gia_schedule_2027_{i}", f["url"], ext=".html")
    (OUT / "gia_schedule_2027.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def round3():
    """The page scripts, to find the endpoints behind the report and release-schedule pages."""
    for js in ("web_report_init.js", "cnds_cdm.js", "subject_common.js", "common.js", "search_ajax.js",
               "press_release.js", "press_release_calendar.js"):
        fetch(f"js_{js}", f"{CSD}/js/{js}", ext=".js")
    for name, url in [("csd_press_release_page", f"{CSD}/en/press_release.html"),
                      ("csd_page_CPI_lang", f"{CSD}/en/page_CPI_lang.json"),
                      ("csd_page_CPI_lang_2", f"{CSD}/page_CPI_lang.json"),
                      ("csd_hes_report_page", f"{CSD}/en/EIndexbySubject.html?pcode=B1060003&scode=290")]:
        fetch(name, url, ext=".html")
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def round4():
    """Web-report data files (monthly CPI report, HES report, PPI report, trade index report),
    table E501, trade index tables, and the release-schedule data behind press_release.html."""
    for pc in ("B1060001", "B1060003", "B1070003", "B1020006", "D5600001"):
        st, body = fetch(f"elidx_{pc}", f"{CSD}/en/data/stat_report/product/{pc}/report_element_index.json")
        fetch(f"el_{pc}", f"{CSD}/en/data/stat_report/product/{pc}/report_element.json")
        o = as_json(body) if st == 200 else None
        for k in ((o or {}).get("elementindex") or [])[:2]:
            fetch(f"el_{pc}_{k}", f"{CSD}/en/data/stat_report/product/{pc}/report_element_{k}.json")
    for pc, ec in (("B1060001", "B10600012026MM09"), ("B1060003", "B10600032025XXXX"),
                   ("B1070003", "B10700032026QQ02")):
        d = f"{CSD}/wbr/{pc}/{ec}/data/"
        st, body = fetch(f"wbr_{ec}", f"{d}en/wbr.json")
        o = as_json(body) if st == 200 else None
        ids = (o or {}).get("tb_code_list") or []
        if isinstance(ids, str):
            ids = [i for i in re.split(r"[,; ]+", ids) if i]
        ids = [i if isinstance(i, str) else (i.get("table_id") or i.get("id") or json.dumps(i)) for i in ids]
        for tid in ids[:60]:
            fetch(f"wbr_{ec}_table_{tid}_comp", f"{d}table_{tid}_comp.json")
            fetch(f"wbr_{ec}_table_{tid}_lang", f"{d}en/table_{tid}_lang.json")
            time.sleep(0.2)
    fetch("e501_xlsx", f"{CSD}/en/data/stat_report/product/D5600001/att/D5600001B2026MM09B.xlsx", ext=".xlsx")
    fetch("e501_zip", f"{CSD}/en/data/stat_report/product/D5600001/att/D5600001B2026MM09B.zip", ext=".zip")
    for tid in ("410-51001", "410-51002", "410-51003"):
        fetch(f"csd_{tid}", f"{CSD}/api/get.php?{urllib.parse.urlencode({'id': tid, 'lang': 'en', 'full_series': 1})}",
              timeout=150)
    st, body = fetch("js_press_release_list", f"{CSD}/js/press_release_list.js", ext=".js")
    txt = body.decode("utf-8", "replace") if body else ""
    names = sorted(set(re.findall(r"[\w./-]*\.json", txt)))
    (OUT / "press_release_json_names.json").write_text(json.dumps(names, indent=1))
    for n in names[:20]:
        base = n.split("/")[-1]
        fetch(f"pr_{base}", f"{CSD}/data/en/press_release/{base}")
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "round4":
        round4()
    elif len(sys.argv) > 2 and sys.argv[2] == "round3":
        round3()
    elif len(sys.argv) > 2 and sys.argv[2] == "round2":
        round2()
    else:
        main()
