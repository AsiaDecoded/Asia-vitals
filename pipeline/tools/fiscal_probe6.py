"""Indonesia fiscal discovery, round 6: where the Ministry of Finance lists its monthly APBN KiTa publications and
outturn press releases, so a source can find each month's PDF. Reads every script of www.kemenkeu.go.id for API
hosts and paths, tries the listing endpoints that mention publications, press releases or APBN KiTa, and downloads
one known APBN KiTa PDF from media.kemenkeu.go.id to check it is reachable and readable.

  python -I pipeline/tools/fiscal_probe6.py OUTDIR
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/html,*/*", "Accept-Language": "id,en;q=0.8"}
KNOWN_PDF = "https://media.kemenkeu.go.id/getmedia/e37def30-1fc9-4756-95cb-05b4b2c156aa/Bulletin_APBN_KITA_Triwulan_I_tahun_2026.pdf?ext=.pdf"


def fetch(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000], url
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode(), url


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rep = {"pages": [], "hosts": [], "paths": [], "tried": []}
    hosts, paths = set(), set()
    for page in ("https://www.kemenkeu.go.id/", "https://www.kemenkeu.go.id/informasi-publik/publikasi/apbn-kita",
                 "https://www.kemenkeu.go.id/informasi-publik/publikasi/siaran-pers"):
        st, ct, b, final = fetch(page)
        html = b.decode("utf-8", "replace")
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        rep["pages"].append({"url": page, "status": st, "scripts": scripts})
        for s in scripts:
            u = s if s.startswith("http") else "https://www.kemenkeu.go.id/" + s.lstrip("/")
            st2, ct2, b2, _ = fetch(u, 90)
            js = b2.decode("utf-8", "replace")
            (out / re.sub(r"[^A-Za-z0-9]+", "_", s)[-80:]).write_text(js[:4_000_000])
            hosts |= set(re.findall(r"https?://[A-Za-z0-9.\-]+\.(?:go\.id|kemenkeu\.go\.id)(?:/[A-Za-z0-9_\-./]*)?", js))
            paths |= set(re.findall(r"[\"'`](/?(?:api|API|v\d|content|publikasi|siaran)[A-Za-z0-9_\-./{}$]*)[\"'`]", js))
    rep["hosts"], rep["paths"] = sorted(hosts), sorted(paths)
    # try listing endpoints that look like publication or press-release lists
    cands = [h for h in hosts if re.search(r"(?i)api|content|cms|publik|media", h)]
    for p in paths:
        if re.search(r"(?i)publik|siaran|apbn|konten|content|news|berita|list", p):
            for h in [h for h in hosts if re.search(r"(?i)api|cms|media", h)][:4]:
                cands.append(h.rstrip("/") + "/" + p.lstrip("/"))
    for c in sorted(set(cands))[:80]:
        st, ct, b, final = fetch(c, 40)
        rep["tried"].append({"url": c, "status": st, "type": ct, "bytes": len(b), "head": b[:400].decode("utf-8", "replace")})
        if st == 200 and ct and "json" in ct:
            (out / ("ep_" + re.sub(r"[^A-Za-z0-9]+", "_", c)[-90:] + ".json")).write_bytes(b[:3_000_000])
    # the known PDF: reachable, and its text
    st, ct, b, final = fetch(KNOWN_PDF, 180)
    rep["known_pdf"] = {"status": st, "type": ct, "bytes": len(b), "is_pdf": b[:4] == b"%PDF"}
    if b[:4] == b"%PDF":
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(b)
            f.flush()
            txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True).stdout.decode("utf-8", "replace")
        (out / "known_pdf.txt").write_text(txt)
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({k: (v if k != "tried" else len(v)) for k, v in rep.items() if k != "pages"}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1])
