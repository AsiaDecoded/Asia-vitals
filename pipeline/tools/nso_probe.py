"""Round-2+ probes for Vietnam NSO from Actions: PX-Web API tree and tables, WordPress REST
listings of the price releases and their attachments.

  python -I pipeline/tools/nso_probe.py <out_dir> [steps]

steps (comma list, default all): px, wp, files
Writes summary.json (every request: url, status, error, bytes, secs, file) plus
px_tables.json (every PX table with metadata), wp_media.json, wp_posts.json.
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
      "Accept": "*/*", "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}
PX = "https://pxweb.nso.gov.vn/api/v1"
WP = "https://www.nso.gov.vn/wp-json/wp/v2"
# Price databases (English and Vietnamese, national and provincial "PL" variants)
PX_DBS = [("en", "E 11. CPI"), ("en", "PLE11CPI"), ("vi", "Chỉ số giá"), ("vi", "PLV11Chỉ số giá"),
          ("en", "E 09. IMEX"), ("vi", "Xuất nhập khẩu")]
OUT = None
SUMMARY = []


def q(url):
    return urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")


def fetch(name, url, data=None, ctype=None, save=True, timeout=90):
    req = urllib.request.Request(q(url), data=data, headers={**UA, **({"Content-Type": ctype} if ctype else {})})
    t = time.time()
    status, headers, body, err = None, {}, b"", None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, headers, body = r.status, dict(r.headers), r.read()
            err = None
            break
        except urllib.error.HTTPError as e:
            status, headers, body, err = e.code, dict(e.headers), e.read(), f"HTTPError {e.code} {e.reason}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001
            status, err = None, f"{type(e).__name__}: {e}"
        time.sleep(3 * (attempt + 1))
    secs = round(time.time() - t, 1)
    ct = headers.get("Content-Type", "")
    fn = None
    if save:
        h = hashlib.md5((url + (data.decode() if data else "")).encode()).hexdigest()[:10]
        low = url.lower().split("?")[0]
        ext = ("xlsx" if low.endswith(".xlsx") or "spreadsheetml" in ct else "xls" if low.endswith(".xls") else
               "pdf" if low.endswith(".pdf") or "pdf" in ct else "json" if "json" in ct else
               "csv" if "csv" in ct else "html" if "html" in ct else "bin")
        fn = f"{name}_{h}.{ext}"
        (OUT / "files" / fn).write_bytes(body[:40_000_000])
    rec = {"name": name, "url": url, "post": data.decode()[:500] if data else None, "status": status, "error": err,
           "type": ct, "bytes": len(body), "secs": secs, "file": fn,
           "headers": {k: v for k, v in headers.items() if k.lower() in ("content-type", "last-modified", "server",
                                                                         "x-wp-total", "x-wp-totalpages", "location")}}
    SUMMARY.append(rec)
    print(len(SUMMARY), status, err or "", ct[:28], len(body), secs, url[:150], flush=True)
    (OUT / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=1))
    return status, headers, body


def jget(name, url, **kw):
    s, h, b = fetch(name, url, **kw)
    try:
        return json.loads(b.decode("utf-8-sig")) if s == 200 else None, h
    except Exception:  # noqa: BLE001
        return None, h


def px_walk(lang, path, depth=0, out=None):
    out = [] if out is None else out
    url = f"{PX}/{lang}/{path}"
    items, _ = jget("pxlist", url + ("/" if not url.endswith("/") else ""))
    if not isinstance(items, list):
        return out
    for it in items:
        sub = f"{path}/{it['id']}"
        if it.get("type") == "l" and depth < 4:
            px_walk(lang, sub, depth + 1, out)
        elif it.get("type") == "t":
            out.append({"lang": lang, "path": sub, "text": it.get("text"), "updated": it.get("updated")})
    return out


def step_px():
    tables = []
    for lang, db in PX_DBS:
        tables += px_walk(lang, db)
    print("PX tables:", len(tables), flush=True)
    for t in tables:
        meta, _ = jget("pxmeta", f"{PX}/{t['lang']}/{t['path']}")
        t["meta"] = meta
        if not meta or "variables" not in meta:
            continue
        cells = 1
        for v in meta["variables"]:
            cells *= max(1, len(v.get("values", [])))
        t["cells"] = cells
        body = {"query": [{"code": v["code"], "selection": {"filter": "all", "values": ["*"]}}
                          for v in meta["variables"]], "response": {"format": "json-stat2"}}
        s, h, b = fetch("pxdata", f"{PX}/{t['lang']}/{t['path']}", data=json.dumps(body).encode(),
                        ctype="application/json", timeout=180)
        t["data_status"] = s
        t["data_bytes"] = len(b)
        t["data_file"] = SUMMARY[-1]["file"]
        if s != 200:  # try csv, then the plain json format
            for fmt in ("csv", "json"):
                body["response"]["format"] = fmt
                s2, _, b2 = fetch("pxdata_" + fmt, f"{PX}/{t['lang']}/{t['path']}", data=json.dumps(body).encode(),
                                  ctype="application/json", timeout=180)
                if s2 == 200:
                    t["data_status"], t["data_file"], t["data_format"] = s2, SUMMARY[-1]["file"], fmt
                    break
        (OUT / "px_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))
    (OUT / "px_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))


PRICE = re.compile(r"CPI|PPI|gia|Gia|price|Price|lam-phat|inflation", re.I)


def step_wp():
    media = {}
    for term in ["CPI", "chi so gia", "Price Index", "PPI", "gia san xuat", "san xuat", "xuat khau", "nhap khau",
                 "lam phat", "nien giam", "yearbook", "kinh te xa hoi", "socio-economic"]:
        for page in range(1, 40):
            items, h = jget("wpmedia", f"{WP}/media?search={urllib.parse.quote(term)}&per_page=100&page={page}"
                            "&_fields=id,date,modified,slug,title,mime_type,source_url,post", save=False)
            if not items:
                break
            for x in items:
                media[x["id"]] = {**x, "title": (x.get("title") or {}).get("rendered"), "term": term}
            if page >= int(h.get("X-WP-TotalPages", h.get("x-wp-totalpages", 1)) or 1):
                break
    (OUT / "wp_media.json").write_text(json.dumps(sorted(media.values(), key=lambda x: x["date"]),
                                                  ensure_ascii=False, indent=1))
    posts = {}
    for cat in (32, 94):  # Prices (en), Thống kê giá (vi)
        for page in range(1, 40):
            items, h = jget("wpposts", f"{WP}/posts?categories={cat}&per_page=100&page={page}"
                            "&_fields=id,date,modified,slug,link,title,categories,tags", save=False)
            if not items:
                break
            for x in items:
                posts[x["id"]] = {**x, "title": (x.get("title") or {}).get("rendered")}
            if page >= int(h.get("X-WP-TotalPages", h.get("x-wp-totalpages", 1)) or 1):
                break
    (OUT / "wp_posts.json").write_text(json.dumps(sorted(posts.values(), key=lambda x: x["date"]),
                                                  ensure_ascii=False, indent=1))


def step_files():
    """Download every spreadsheet attachment in wp_media.json (price-related), plus a sample of others."""
    media = json.loads((OUT / "wp_media.json").read_text())
    n = 0
    for x in media:
        u = x["source_url"]
        if u.lower().endswith((".xlsx", ".xls")) and PRICE.search(u):
            fetch("xls", u)
            n += 1
    print("spreadsheets fetched:", n, flush=True)


def main(out, steps="px,wp,files"):
    global OUT
    OUT = Path(out)
    (OUT / "files").mkdir(parents=True, exist_ok=True)
    for s in steps.split(","):
        try:
            {"px": step_px, "wp": step_wp, "files": step_files}[s]()
        except Exception as e:  # noqa: BLE001
            SUMMARY.append({"name": f"step_{s}", "error": f"{type(e).__name__}: {e}"})
            print("step failed", s, e, flush=True)
    (OUT / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
