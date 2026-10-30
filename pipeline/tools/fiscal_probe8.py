"""Indonesia fiscal discovery, round 8: the Ministry of Finance's APBN KiTa list (media.kemenkeu.go.id
SinglePage/Filter, POST) by year, and the press-release list; downloads the newest APBN KiTa PDFs and saves their
text, to see whether the series is monthly and how the outturn table reads.

  python -I pipeline/tools/fiscal_probe8.py OUTDIR
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://media.kemenkeu.go.id"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/plain,*/*", "Origin": "https://www.kemenkeu.go.id", "Referer": "https://www.kemenkeu.go.id/"}


def call(path, params, method="POST", timeout=60):
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=b"" if method == "POST" else None, headers=UA, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return url, r.status, r.read()
    except urllib.error.HTTPError as e:
        return url, e.code, e.read()[:5000]
    except Exception as e:  # noqa: BLE001
        return url, None, repr(e).encode()


def pdf_text(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=240) as r:
        b = r.read()
    if b[:4] != b"%PDF":
        return None, len(b)
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True).stdout.decode("utf-8", "replace"), len(b)


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = []
    tries = [("/SinglePage/Filter", {"path": "/Pages/Home/Informasi-Terbaru/APBN-Kita", "lang": "id-id", "hassubcategory": "true"}, "POST")]
    for y in ("2026", "2025", "2024"):
        tries.append(("/SinglePage/Filter", {"path": "/Pages/Home/Informasi-Terbaru/APBN-Kita", "lang": "id-id", "hassubcategory": "true", "param1": y}, "POST"))
        tries.append(("/SinglePage/Filter", {"path": "/Pages/Informasi-Publik/Publikasi/Daftar-Publikasi", "lang": "id", "param1": y, "param2": "APBN KiTa"}, "POST"))
    tries.append(("/SinglePage/Pagination", {"p": "/Pages/Informasi-Publik/Publikasi/Siaran-Pers", "lang": "id", "page": "1"}, "GET"))
    tries.append(("/SinglePage/Filter", {"path": "/Pages/Home/Informasi-Terbaru/Siaran-Pers", "lang": "id-id"}, "POST"))
    pdfs = []
    for i, (p, prm, m) in enumerate(tries):
        url, st, b = call(p, prm, m)
        name = f"list_{i:02d}.json"
        (out / name).write_bytes(b[:5_000_000])
        txt = b.decode("utf-8", "replace")
        found = sorted(set(re.findall(r"https?://media\.kemenkeu\.go\.id/getmedia/[^\"'\s]+?\.pdf[^\"'\s]*", txt)))
        titles = re.findall(r'"(?:Title|title|Judul|Name)"\s*:\s*"([^"]{5,140})"', txt)
        log.append({"i": i, "url": url, "method": m, "status": st, "bytes": len(b), "pdfs": found[:40], "titles": titles[:60]})
        pdfs += found
        print(i, st, len(b), url[:140], len(found), "pdfs", flush=True)
    (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    # newest monthly-looking APBN KiTa PDFs (2026, 2025), text saved
    pick = [u for u in dict.fromkeys(pdfs) if re.search(r"(?i)apbn[-_ ]?kita", u)]
    pick = [u for u in pick if re.search(r"2026|2025", u)][:6]
    for j, u in enumerate(pick):
        try:
            t, n = pdf_text(u)
            (out / f"pdf_{j}.meta.json").write_text(json.dumps({"url": u, "bytes": n}))
            if t:
                (out / f"pdf_{j}.txt").write_text(t)
            print("pdf", j, n, u[:140], flush=True)
        except Exception as e:  # noqa: BLE001
            (out / f"pdf_{j}.error.txt").write_text(repr(e) + " " + u)


if __name__ == "__main__":
    main(sys.argv[1])
