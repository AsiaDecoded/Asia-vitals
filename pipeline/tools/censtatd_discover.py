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


if __name__ == "__main__":
    main()
