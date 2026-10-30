"""Indonesia fiscal discovery: Bank Indonesia SEKI table headers (chapters other than V-VIII), Ministry of Finance
sites (APBN KiTa, budget data portal, DJPb, DJPPR debt), BPS WebAPI annual fiscal variables.

  BPS_KEY=... python -I pipeline/tools/fiscal_probe.py OUTDIR
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bps_api_discover import KEY, get, rows_of  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8"}
URLS = [
    "https://www.kemenkeu.go.id/informasi-publik/publikasi/apbn-kita",
    "https://www.kemenkeu.go.id/en/informasi-publik/publikasi/apbn-kita",
    "https://media.kemenkeu.go.id/",
    "https://data-apbn.kemenkeu.go.id/",
    "https://data-apbn.kemenkeu.go.id/api",
    "https://data-apbn.kemenkeu.go.id/lv2/apbn",
    "https://djpb.kemenkeu.go.id/portal/id/data/",
    "https://djppr.kemenkeu.go.id/",
    "https://djppr.kemenkeu.go.id/data-statistik",
    "https://djppr.kemenkeu.go.id/page/load/2820",
    "https://www.djppr.kemenkeu.go.id/profilutang",
    "https://fiskal.kemenkeu.go.id/",
    "https://fiskal.kemenkeu.go.id/data/",
    "https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/Default.aspx",
    "https://www.bi.go.id/en/statistik/ekonomi-keuangan/seki/Default.aspx",
    "https://satudata.kemenkeu.go.id/",
    "https://satudata.kemenkeu.go.id/api/3/action/package_search?q=apbn&rows=50",
    "https://data.go.id/api/3/action/package_search?q=realisasi%20apbn&rows=50",
    "https://katalog.data.go.id/api/3/action/package_search?q=apbn&rows=50",
    "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/GFSMAB2014/A.ID.S1311B.W0_S1_G1..XDC",
    "https://api.imf.org/external/sdmx/2.1/dataflow/IMF.STA",
]


def fetch(url, timeout=60):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            b = r.read()
            return r.status, r.headers.get("Content-Type"), b, round(time.time() - t0, 1), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000], round(time.time() - t0, 1), url
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode(), round(time.time() - t0, 1), url


def links(html):
    return sorted(set(re.findall(r'href="([^"#]+)"', html)))


def main(out):
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    log = []
    for i, u in enumerate(URLS):
        st, ct, b, s, final = fetch(u)
        txt = b.decode("utf-8", "replace")
        (out / "pages" / f"{i:02d}.txt").write_text(txt[:400000])
        rec = {"i": i, "url": u, "final": final, "status": st, "type": ct, "bytes": len(b), "secs": s,
               "title": (re.search(r"<title>(.*?)</title>", txt, re.S | re.I) or [None, ""])[1].strip()[:150]}
        if ct and "html" in ct:
            ls = links(txt)
            rec["links_fiscal"] = [l for l in ls if re.search(r"(?i)apbn|fiskal|utang|debt|realisasi|xls|csv|pdf|api|data", l)][:150]
        log.append(rec)
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, s, u, flush=True)
    # SEKI: every table header in chapters 1-4, 9-12 (TABEL<c>_<n>.xls), first sheet titles only
    import xlrd  # noqa: PLC0415
    seki = {}
    for c in (1, 2, 3, 4, 9, 10, 11, 12):
        miss = 0
        for n in range(1, 40):
            st, ct, b, s, _ = fetch(f"https://www.bi.go.id/SEKI/tabel/TABEL{c}_{n}.xls", 90)
            if not b.startswith(b"\xd0\xcf\x11\xe0"):
                miss += 1
                if miss >= 3:
                    break
                continue
            miss = 0
            try:
                wb = xlrd.open_workbook(file_contents=b)
                sh = wb.sheet_by_index(wb.nsheets - 1)
                title = " | ".join(str(sh.cell_value(r, cc)).strip() for r in range(min(4, sh.nrows)) for cc in range(min(3, sh.ncols))
                                   if str(sh.cell_value(r, cc)).strip())[:200]
                labels = [" ".join(str(x).strip() for x in sh.row_values(r)[:3] if str(x).strip())[:80] for r in range(min(sh.nrows, 70))]
                seki[f"{c}_{n}"] = {"sheets": wb.sheet_names(), "title": title, "rows": sh.nrows, "cols": sh.ncols,
                                    "labels": [l for l in labels if l], "header": [str(x)[:12] for x in sh.row_values(min(5, sh.nrows - 1))[-8:]]}
                if re.search(r"(?i)pemerintah|government|fiskal|fiscal|anggaran|budget|utang|debt|SBN|pajak", title):
                    (out / "seki").mkdir(exist_ok=True)
                    (out / "seki" / f"TABEL{c}_{n}.xls").write_bytes(b)
            except Exception as e:  # noqa: BLE001
                seki[f"{c}_{n}"] = {"error": repr(e)}
            print("SEKI", c, n, seki[f"{c}_{n}"].get("title", "")[:80], flush=True)
            (out / "seki.json").write_text(json.dumps(seki, ensure_ascii=False, indent=1))
    # BPS WebAPI: annual fiscal variables
    if KEY:
        for vid in (1070, 1082, 1529, 1256, 1587):
            st, d, s = get(f"list/model/th/domain/0000/var/{vid}")
            _, ths = rows_of(d)
            yrs = {int(t["th"]): t["th_id"] for t in ths if str(t.get("th", "")).isdigit()}
            if yrs:
                y = max(yrs)
                st, d, s = get(f"list/model/data/domain/0000/var/{vid}/th/{yrs[y]}")
                (out / f"bps_{vid}_{y}.json").write_text(json.dumps(d, ensure_ascii=False)[:300000].replace(KEY, "***"))
            print("BPS", vid, sorted(yrs)[:1], sorted(yrs)[-1:], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
