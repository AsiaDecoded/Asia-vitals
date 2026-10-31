"""Indonesia official government debt: Bank Indonesia / Ministry of Finance public sector debt statistics (SUSPI),
the debt office (DJPPR) without www, and the Ministry's APBN KiTa monthly reports (2019-2024, debt section).

  python -I pipeline/tools/debt_probe2.py OUTDIR
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/json,*/*;q=0.8"}
URLS = [
    "https://www.bi.go.id/id/statistik/ekonomi-keuangan/suspi/default.aspx",
    "https://www.bi.go.id/en/statistik/ekonomi-keuangan/suspi/default.aspx",
    "https://www.bi.go.id/id/statistik/ekonomi-keuangan/suspi/Pages/SUSPI-Terkini.aspx",
    "https://www.bi.go.id/id/publikasi/laporan/Default.aspx?Topik=Statistik%20Utang%20Sektor%20Publik%20Indonesia",
    "https://djppr.kemenkeu.go.id/",
    "https://djppr.kemenkeu.go.id/profilutang",
    "https://djppr.kemenkeu.go.id/page/load/2820",
    "https://djppr.kemenkeu.go.id/data-statistik",
    "https://www.kemenkeu.go.id/informasi-publik/publikasi/apbn-kita",
]
LIST = "https://media.kemenkeu.go.id/SinglePage/Filter?path=/Pages/Home/Informasi-Terbaru/APBN-Kita&lang=id-id&hassubcategory=true&param1={}"


def fetch(url, data=None, timeout=90):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=UA, data=data, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000], round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode(), round(time.time() - t0, 1)


def main(out):
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    log = []
    for i, u in enumerate(URLS):
        st, ct, b, s = fetch(u)
        (out / "pages" / f"{i:02d}.txt").write_bytes(b[:3_000_000])
        t = b.decode("utf-8", "replace")
        links = sorted(set(re.findall(r'href="([^"#]+)"', t)))
        log.append({"i": i, "url": u, "status": st, "type": ct, "bytes": len(b), "secs": s,
                    "links": [l for l in links if re.search(r"(?i)suspi|utang|debt|xls|pdf|profil", l)][:200]})
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), s, u, flush=True)
    # APBN KiTa list, 2019-2024: titles and files (monthly reports carry a debt section)
    lists = {}
    for y in range(2019, 2025):
        st, ct, b, s = fetch(LIST.format(y), data=b"")
        try:
            items = json.loads(b)
        except Exception:  # noqa: BLE001
            items = {"raw": b[:2000].decode("utf-8", "replace")}
        lists[y] = items
        print("list", y, st, len(b), flush=True)
    (out / "apbnkita_lists.json").write_text(json.dumps(lists, ensure_ascii=False)[:5_000_000])


if __name__ == "__main__":
    main(sys.argv[1])
