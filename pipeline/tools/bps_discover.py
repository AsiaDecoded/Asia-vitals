"""Probe Indonesian price data sources (BPS, Bank Indonesia SEKI, Satu Data), round 1.

  python -I pipeline/tools/bps_discover.py OUTDIR

Saves every response (status, headers, body) under OUTDIR and a summary.json.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9,id;q=0.8"}


def get(url, timeout=60, headers=None):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={**UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read(), round(time.time() - t0, 2)
    except Exception as e:  # noqa: BLE001
        return None, {}, repr(e).encode(), round(time.time() - t0, 2)


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    s = []

    def probe(name, url, **kw):
        st, hd, b, secs = get(url, **kw)
        ext = ".bin"
        ct = (hd.get("Content-Type") or hd.get("content-type") or "").lower()
        if "html" in ct: ext = ".html"
        elif "json" in ct: ext = ".json"
        elif "pdf" in ct: ext = ".pdf"
        elif "excel" in ct or "spreadsheet" in ct or url.endswith((".xls", ".xlsx")): ext = ".xls" if url.endswith(".xls") else ".xlsx"
        (out / (name + ext)).write_bytes(b)
        info = {"name": name, "url": url, "status": st, "secs": secs, "bytes": len(b), "type": ct,
                "head": b[:300].decode("utf-8", "replace")}
        s.append(info)
        print(name, st, secs, len(b), ct, flush=True)
        (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
        return st, b

    # BPS WebAPI without a key: what does it say?
    probe("webapi_nokey", "https://webapi.bps.go.id/v1/api/list/model/var/domain/0000/subject/3/lang/eng")
    probe("webapi_dev", "https://webapi.bps.go.id/developer/")
    # BPS website: inflation subject pages and static/dynamic tables
    for nm, u in [
        ("bps_subject_inflasi", "https://www.bps.go.id/en/subject/3/inflation.html"),
        ("bps_st_ihk_2006_2023", "https://www.bps.go.id/en/statistics-table/1/OTA3IzE=/indeks-harga-konsumen-dan-inflasi-bulanan-indonesia--2006-2023.html"),
        ("bps_query_builder", "https://www.bps.go.id/en/query-builder"),
        ("bps_statistics_table_list", "https://www.bps.go.id/en/statistics-table?subject=3"),
        ("bps_home", "https://www.bps.go.id/en"),
    ]:
        st, b = probe(nm, u)
        if st == 200 and nm != "bps_home":
            # follow statistics-table links and any JS chunks that may name an API
            txt = b.decode("utf-8", "replace")
            links = sorted(set(re.findall(r'/(?:en|id)/statistics-table/[0-9]/[A-Za-z0-9=%]+/[a-z0-9\-]+\.html', txt)))
            (out / (nm + "_links.txt")).write_text("\n".join(links))
            apis = sorted(set(re.findall(r'https?://[a-z0-9.\-]*bps\.go\.id/[A-Za-z0-9_/\-\.]*api[A-Za-z0-9_/\-\.]*', txt)))
            (out / (nm + "_apis.txt")).write_text("\n".join(apis))
            js = sorted(set(re.findall(r'/_next/static/[A-Za-z0-9_/\-\.]+\.js', txt)))
            (out / (nm + "_js.txt")).write_text("\n".join(js))
    # Bank Indonesia SEKI, chapter VIII (prices)
    for i in range(1, 11):
        for ext in ("xls", "xlsx", "pdf"):
            probe(f"seki_8_{i}_{ext}", f"https://www.bi.go.id/seki/tabel/TABEL8_{i}.{ext}")
    probe("seki_index", "https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/default.aspx")
    probe("bi_data_inflasi_id", "https://www.bi.go.id/id/statistik/indikator/data-inflasi.aspx")
    probe("bi_data_inflasi_en", "https://www.bi.go.id/en/statistik/indikator/data-inflasi.aspx")
    # Satu Data Indonesia (CKAN)
    probe("satudata_search", "https://data.go.id/api/3/action/package_search?q=indeks%20harga%20konsumen&rows=50")
    probe("satudata_search2", "https://katalog.data.go.id/api/3/action/package_search?q=inflasi&rows=50")


if __name__ == "__main__":
    main(sys.argv[1])
