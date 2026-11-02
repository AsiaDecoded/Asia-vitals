"""Probe Thailand's NESDC (national accounts) and the Bank of Thailand from Actions; both are blocked from the
Claude sandbox. Crawls the NESDC national-accounts pages, lists WordPress REST content that mentions GDP, and saves
every spreadsheet found.

  python -I pipeline/tools/nesdc_probe.py <out_dir> [max_files]

Writes summary.json (every request: url, status, error, bytes, file), links.json (every link seen on the crawled
pages), wp.json (WordPress REST search results), and the files under files/.
"""
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "*/*", "Accept-Language": "en;q=0.9,th;q=0.8"}
SEEDS = [
    "https://www.nesdc.go.th/en/info/national-accounts/",
    "https://www.nesdc.go.th/en/info/quarterly-gross-domestic-product-qgdp-en/",
    "https://www.nesdc.go.th/en/download/all-tables-qgdp2-2026-download-excel-file/",
    "https://www.nesdc.go.th/en/download/gross-domestic-product-q1-2026-report/",
    "https://www.nesdc.go.th/en/",
    "https://www.nesdc.go.th/",
]
FOLLOW = re.compile(r"nesdc\.go\.th/.*(national-account|gdp|qgdp|gross-domestic|download|wp-content/uploads|"
                    r"%e0%b8%9a%e0%b8%b1%e0%b8%8d%e0%b8%8a%e0%b8%b5|calendar|release)", re.I)
FILE = re.compile(r"\.(xlsx?|zip|csv)(\?|$)", re.I)
WP_TERMS = ["qgdp", "gross domestic product", "national income", "chain volume", "all tables", "GDP time series",
            "release calendar", "ผลิตภัณฑ์มวลรวม", "บัญชีประชาชาติ"]
OUT = None
SUMMARY = []


def fetch(url, save=True, timeout=90):
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~"), headers=UA)
    status, headers, body, err = None, {}, b"", None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, headers, body = r.status, dict(r.headers), r.read()
            err = None
            break
        except urllib.error.HTTPError as e:
            status, headers, body, err = e.code, dict(e.headers), e.read(), f"HTTPError {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        time.sleep(3 * (attempt + 1))
    ct = headers.get("Content-Type", "")
    fn = None
    if save and body:
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.unquote(url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]))[-80:]
        if FILE.search(url) or "spreadsheet" in ct or "excel" in ct or "zip" in ct:
            fn = f"files/{h}_{base}"
        else:
            fn = f"pages/{h}_{base or 'index'}.{'json' if 'json' in ct else 'html'}"
        (OUT / fn).parent.mkdir(parents=True, exist_ok=True)
        (OUT / fn).write_bytes(body)
    SUMMARY.append({"url": url, "status": status, "error": err, "bytes": len(body), "ctype": ct, "file": fn,
                    "disposition": headers.get("Content-Disposition", "")})
    return status, ct, body


def links(html, base):
    out = []
    for m in re.finditer(r"""href\s*=\s*["']([^"'#]+)""", html, re.I):
        u = urllib.parse.urljoin(base, m.group(1).strip())
        if u.startswith("http"):
            out.append(u)
    return out


def main():
    global OUT
    OUT = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    max_files = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    seen, queue, all_links, files = set(), [(s, 0) for s in SEEDS], {}, []
    while queue and len(seen) < 250:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if FILE.search(url):
            files.append(url)
            continue
        st, ct, body = fetch(url)
        if not body or "html" not in ct:
            continue
        html = body.decode("utf-8", "replace")
        ls = links(html, url)
        all_links[url] = ls
        for u in ls:
            if FILE.search(u) and u not in files:
                files.append(u)
            elif depth < 2 and FOLLOW.search(u) and u not in seen:
                queue.append((u, depth + 1))
    # WordPress REST: search, plus the download post type if it exists
    wp = {}
    st, ct, body = fetch("https://www.nesdc.go.th/wp-json/", save=False)
    try:
        root = json.loads(body)
        wp["routes"] = sorted(k for k in root.get("routes", {}) if "/wp/v2/" in k and "(?P" not in k)
    except Exception:  # noqa: BLE001
        wp["routes"] = f"status {st}"
    for term in WP_TERMS:
        u = f"https://www.nesdc.go.th/wp-json/wp/v2/search?search={urllib.parse.quote(term)}&per_page=100"
        st, ct, body = fetch(u)
        try:
            wp[term] = [(r.get("title"), r.get("url"), r.get("subtype")) for r in json.loads(body)]
        except Exception:  # noqa: BLE001
            wp[term] = f"status {st}"
    for pt in ("download", "downloads", "media"):
        u = f"https://www.nesdc.go.th/wp-json/wp/v2/{pt}?search=gdp&per_page=100"
        st, ct, body = fetch(u)
        try:
            items = json.loads(body)
            wp[f"type:{pt}"] = [(i.get("date"), (i.get("title") or {}).get("rendered"), i.get("link"), i.get("source_url"))
                                for i in items]
            for i in items:
                for k in ("source_url",):
                    if i.get(k) and FILE.search(i[k]) and i[k] not in files:
                        files.append(i[k])
        except Exception:  # noqa: BLE001
            wp[f"type:{pt}"] = f"status {st}"
    # download pages found by search: fetch them for their file links
    for term, res in list(wp.items()):
        if isinstance(res, list):
            for r in res:
                u = r[1] if len(r) > 1 else None
                if u and isinstance(u, str) and "/download/" in u and u not in seen:
                    seen.add(u)
                    st, ct, body = fetch(u)
                    if body and "html" in ct:
                        ls = links(body.decode("utf-8", "replace"), u)
                        all_links[u] = ls
                        files += [x for x in ls if (FILE.search(x) or "wpdmdl" in x or "download=" in x) and x not in files]
    # Bank of Thailand statistics downloads (no key) and World Bank, for reach
    for u in ["https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=409&language=ENG",
              "https://app.bot.or.th/BTWS_STAT/statistics/DownloadFile.aspx?file=EC_EI_027_S2_ENG_ALL.XLSX",
              "https://www.bot.or.th/en/statistics/real-sector.html",
              "https://api.worldbank.org/v2/country/THA/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=5"]:
        fetch(u)
    for u in files[:max_files]:
        fetch(u, timeout=180)
    (OUT / "links.json").write_text(json.dumps(all_links, ensure_ascii=False, indent=0))
    (OUT / "wp.json").write_text(json.dumps(wp, ensure_ascii=False, indent=0))
    (OUT / "files.json").write_text(json.dumps(files, ensure_ascii=False, indent=0))
    (OUT / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=0))
    print(f"{len(SUMMARY)} requests, {len(files)} file links, {sum(1 for s in SUMMARY if s['status'] == 200)} ok")


if __name__ == "__main__":
    main()
