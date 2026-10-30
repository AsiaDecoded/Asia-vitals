"""Indonesia fiscal discovery, round 7: the Ministry of Finance site's content API (media.kemenkeu.go.id).
Reads the Angular runtime for every lazy chunk, downloads them, lists every `${baseUrl}/...` call with its params,
then calls the page API for the APBN KiTa and press-release pages and saves the answers.

  python -I pipeline/tools/fiscal_probe7.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/plain,*/*", "Origin": "https://www.kemenkeu.go.id", "Referer": "https://www.kemenkeu.go.id/"}
SITE = "https://www.kemenkeu.go.id/"
API = "https://media.kemenkeu.go.id"


def fetch(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000]
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode()


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    st, ct, b = fetch(SITE)
    html = b.decode("utf-8", "replace")
    runtime = next((s for s in re.findall(r'src="([^"]+)"', html) if s.startswith("runtime")), None)
    calls = set()
    chunks = []
    if runtime:
        rt = fetch(SITE + runtime)[2].decode("utf-8", "replace")
        # Angular/webpack: chunk id -> hash map, e.g. {37:"a1b2..",686:"..."}[e]+".js"
        for m in re.finditer(r"\{((?:\d+:\"[0-9a-f]{8,}\",?)+)\}\[\w+\]\+\"\.js\"", rt):
            chunks += [f"{cid}.{h}.js" for cid, h in re.findall(r"(\d+):\"([0-9a-f]+)\"", m.group(1))]
        named = re.findall(r"(\d+):\"([A-Za-z0-9_\-]+)\"", rt)
        (out / "runtime.js").write_text(rt)
    for c in chunks:
        js = fetch(SITE + c, 60)[2].decode("utf-8", "replace")
        for m in re.finditer(r"baseUrl\}(/[A-Za-z0-9_/\-]+)`(.{0,300})", js):
            params = re.findall(r"(\w+):([^,}]{1,60})", m.group(2).split("})")[0])
            calls.add((m.group(1), json.dumps(params)[:300]))
        if re.search(r"(?i)apbn|publikasi|siaran", js):
            (out / f"chunk_{c}").write_text(js[:2_000_000])
    calls = sorted(calls)
    (out / "calls.json").write_text(json.dumps(calls, indent=1))
    print(len(chunks), "chunks;", len(calls), "API calls", flush=True)
    for p, prm in calls:
        print(p, prm[:200], flush=True)
    # page API for likely page paths
    tried = []
    for path in ("/Informasi-Publik/Publikasi/APBN-KiTa", "/informasi-publik/publikasi/apbn-kita", "/Informasi-Publik/Publikasi",
                 "/informasi-publik/publikasi/siaran-pers", "/Informasi-Publik/Publikasi/Siaran-Pers", "/Home"):
        for ep in ("/SinglePage/CustomPage", "/singlePage/SectionPage", "/SinglePage/ListPage", "/SinglePage/List"):
            for lang in ("id", "en"):
                url = API + ep + "?" + urllib.parse.urlencode({"p": path, "lang": lang})
                st, ct, b = fetch(url, 40)
                rec = {"url": url, "status": st, "type": ct, "bytes": len(b), "head": b[:300].decode("utf-8", "replace")}
                tried.append(rec)
                if st == 200 and len(b) > 200:
                    (out / ("page_" + re.sub(r"[^A-Za-z0-9]+", "_", ep + path + lang) + ".json")).write_bytes(b[:3_000_000])
    # every call found in the chunks, with params p / lang filled for the APBN KiTa page
    for p, prm in calls:
        url = API + p + "?" + urllib.parse.urlencode({"p": "/Informasi-Publik/Publikasi/APBN-KiTa", "lang": "id", "page": 1, "pageSize": 50})
        st, ct, b = fetch(url, 40)
        tried.append({"url": url, "status": st, "type": ct, "bytes": len(b), "head": b[:300].decode("utf-8", "replace")})
        if st == 200 and len(b) > 200:
            (out / ("call_" + re.sub(r"[^A-Za-z0-9]+", "_", p) + ".json")).write_bytes(b[:3_000_000])
    (out / "tried.json").write_text(json.dumps(tried, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
