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


# --- Round 4: PX-Web web export (the PxWeb API does not publish the price databases), post texts, report tables

import http.cookiejar
import html as _html

PXWEB = "https://pxweb.nso.gov.vn/pxweb"
PX_TABLES = [("en", "E 11. CPI", "E 11. CPI__Px_E_11", f"E11.{i:02d}.px") for i in range(1, 29)]


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _post_form(op, url, fields, name):
    data = urllib.parse.urlencode(fields, doseq=True).encode()
    req = urllib.request.Request(q(url), data=data, headers={**UA, "Content-Type": "application/x-www-form-urlencoded",
                                                             "Referer": q(url)})
    t = time.time()
    try:
        with op.open(req, timeout=240) as r:
            st, hd, body, err = r.status, dict(r.headers), r.read(), None
    except urllib.error.HTTPError as e:
        st, hd, body, err = e.code, dict(e.headers), e.read(), f"HTTPError {e.code}"
    except Exception as e:  # noqa: BLE001
        st, hd, body, err = None, {}, b"", f"{type(e).__name__}: {e}"
    cd = hd.get("Content-Disposition", "")
    ext = "px" if (".px" in cd or body[:8] in (b"CHARSET=", b"AXIS-VER") or body[:5] == b"CHARS") else (
        "json" if body[:1] == b"{" else "html" if body.lstrip()[:1] == b"<" else "bin")
    h = hashlib.md5((url + name).encode()).hexdigest()[:10]
    fn = f"{name}_{h}.{ext}"
    (OUT / "files" / fn).write_bytes(body)
    SUMMARY.append({"name": name, "url": url, "post": "form", "status": st, "error": err, "type": hd.get("Content-Type", ""),
                    "bytes": len(body), "secs": round(time.time() - t, 1), "file": fn,
                    "headers": {k: v for k, v in hd.items() if k.lower() in ("content-type", "content-disposition")}})
    print(len(SUMMARY), st, err or "", ext, len(body), url[-60:], flush=True)
    (OUT / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=1))
    return st, body, ext


def px_export(lang, db, folder, table, fmt="FileTypePX"):
    """Select every value of every variable on a PX-Web (ASP.NET) table page and ask for one file format."""
    op = _opener()
    url = f"{PXWEB}/{lang}/{db}/{folder}/{table}/"
    req = urllib.request.Request(q(url), headers=UA)
    with op.open(req, timeout=120) as r:
        page = r.read().decode("utf-8", "replace")
    fields = []
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', page):
        n = re.search(r'name="([^"]+)"', m.group(0)); v = re.search(r'value="([^"]*)"', m.group(0))
        if n:
            fields.append((_html.unescape(n.group(1)), _html.unescape(v.group(1)) if v else ""))
    nsel = 0
    for m in re.finditer(r'<select[^>]*name="([^"]+ValuesListBox)"[^>]*>(.*?)</select>', page, re.S):
        for v in re.findall(r'<option[^>]*value="([^"]*)"', m.group(2)):
            fields.append((_html.unescape(m.group(1)), _html.unescape(v)))
        nsel += 1
    fmt_name = re.search(r'<select[^>]*name="([^"]+OutputFormatDropDownList)"', page).group(1)
    btn = re.search(r'<input[^>]*type="submit"[^>]*name="([^"]+ButtonViewTable)"[^>]*value="([^"]*)"', page)
    fields += [(_html.unescape(fmt_name), fmt), (_html.unescape(btn.group(1)), btn.group(2))]
    return _post_form(op, url, fields, f"pxweb_{table}_{fmt}")


def step_pxweb():
    for lang, db, folder, table in PX_TABLES:
        try:
            st, body, ext = px_export(lang, db, folder, table, "FileTypePX")
            if ext != "px":
                px_export(lang, db, folder, table, "FileTypeCsvWithHeadingAndComma")
        except Exception as e:  # noqa: BLE001
            SUMMARY.append({"name": "pxweb_" + table, "error": f"{type(e).__name__}: {e}"})
            print("pxweb failed", table, e, flush=True)


POST_IDS = [59623, 2903, 2913, 62508, 59522, 61656]


def step_posts():
    """Full text of the methodology posts and of every monthly CPI post (Vietnamese category 94)."""
    for pid in POST_IDS:
        fetch("post", f"{WP}/posts/{pid}?_fields=id,date,modified,link,title,content")
    for page in range(1, 6):
        s, h, b = fetch("cpiposts", f"{WP}/posts?categories=94&search={urllib.parse.quote('Chỉ số giá tiêu dùng')}"
                        f"&per_page=100&page={page}&_fields=id,date,link,title,content")
        if s != 200 or page >= int(h.get("X-WP-TotalPages", 1) or 1):
            break


REPORT_FILES = ["https://www.nso.gov.vn/wp-content/uploads/2026/10/02.-Bieu-thang-9.2026.xlsx",
                "https://www.nso.gov.vn/wp-content/uploads/2026/07/2.-Bieu-T6.2026.xlsx"]


def step_files2():
    for u in REPORT_FILES:
        fetch("report", u)
    media, _ = jget("wpmedia_reports", f"{WP}/media?search={urllib.parse.quote('Bieu thang')}&per_page=100"
                    "&_fields=id,date,source_url,post", save=True)



def step_quarters():
    """Socio-economic report workbooks at each quarter end (PPI and trade price tables), 2020-2026."""
    import datetime as _dt
    found = []
    for y in range(2020, 2027):
        for m in (3, 6, 9, 12):
            a = _dt.date(y, m, 20) if m != 12 else _dt.date(y, 12, 20)
            b = (_dt.date(y + (m == 12), (m % 12) + 1, 10))
            items, _ = jget("wpmedia_q", f"{WP}/media?after={a}T00:00:00&before={b}T00:00:00&per_page=100"
                            "&_fields=id,date,source_url,post,mime_type", save=False)
            for x in items or []:
                u = x["source_url"]
                if u.lower().endswith((".xlsx", ".xls")) and re.search(r"Bieu|bieu|So-lieu", u) and not re.search(r"CPI|IIP|Lao-dong|XNK|NK|XK", u):
                    found.append({"quarter": f"{y}Q{m // 3}", **x})
    (OUT / "quarter_workbooks.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    for x in found:
        fetch("qbook_" + x["quarter"], x["source_url"])


def step_misc():
    fetch("infographic_2024", "https://www.nso.gov.vn/wp-content/uploads/2026/01/646f8dc5-8880-4de0-ad98-65a9a60e29d6.jpg")
    for u in ["https://pxweb.nso.gov.vn/pxweb/vi/Ch%e1%bb%89%20s%e1%bb%91%20gi%c3%a1/",
              "https://pxweb.nso.gov.vn/pxweb/vi/Ch%e1%bb%89%20s%e1%bb%91%20gi%c3%a1/Ch%e1%bb%89%20s%e1%bb%91%20gi%c3%a1__Px_V_11/?tablelist=true",
              "https://pxweb.nso.gov.vn/pxweb/vi/Ch%e1%bb%89%20s%e1%bb%91%20gi%c3%a1/?tablelist=true"]:
        fetch("pxvi", u)


# --- GDP round (g1): national accounts on PX-Web, GDP posts and attachments, older report workbooks

NA_KEY = re.compile(r"t[aà]i\s*kho[aả]n\s*qu[oố]c\s*gia|national\s*account|E\s*0?3\b|V\s*0?3\b|GDP|t[oổ]ng\s*s[aả]n\s*ph[aẩ]m", re.I)


def _links(html_text, base):
    out = []
    for m in re.finditer(r"""<a\b[^>]*href=["']([^"'#]+)["'][^>]*>(.*?)</a>""", html_text, re.I | re.S):
        u = urllib.parse.urljoin(base, _html.unescape(m.group(1)))
        out.append((u, re.sub(r"<[^>]+>|\s+", " ", _html.unescape(m.group(2))).strip()))
    return out


def step_gdp_px():
    """List every PX-Web database (web and API, en and vi); for national-accounts ones, list and export every table."""
    found = {}
    for lang in ("en", "vi"):
        jget(f"pxapi_root_{lang}", f"{PX}/{lang}/")
        s, h, b = fetch(f"pxweb_root_{lang}", f"{PXWEB}/{lang}/")
        if s != 200:
            continue
        page = b.decode("utf-8", "replace")
        dbs = sorted({u for u, t in _links(page, f"{PXWEB}/{lang}/") if f"/pxweb/{lang}/" in u})
        (OUT / f"px_databases_{lang}.json").write_text(json.dumps(_links(page, f"{PXWEB}/{lang}/"), ensure_ascii=False, indent=1))
        for u in dbs:
            name = urllib.parse.unquote(u.split(f"/pxweb/{lang}/", 1)[1])
            if not NA_KEY.search(name):
                continue
            s2, _, b2 = fetch(f"pxdb_{lang}", u.rstrip("/") + "/?tablelist=true")
            if s2 != 200:
                continue
            for t_url, text in _links(b2.decode("utf-8", "replace"), u):
                if re.search(r"\.px/?$", t_url, re.I):
                    found[t_url] = {"lang": lang, "db_url": u, "text": text}
    (OUT / "px_na_tables.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    for t_url, info in found.items():
        rest = urllib.parse.unquote(t_url.split(f"/pxweb/{info['lang']}/", 1)[1]).strip("/").split("/")
        if len(rest) < 3:
            continue
        db, folder, table = rest[0], rest[1], rest[-1]
        try:
            st, body, ext = px_export(info["lang"], db, folder, table, "FileTypePX")
            info["export"] = SUMMARY[-1]["file"]
            if ext != "px":
                px_export(info["lang"], db, folder, table, "FileTypeCsvWithHeadingAndComma")
                info["export"] = SUMMARY[-1]["file"]
        except Exception as e:  # noqa: BLE001
            info["error"] = f"{type(e).__name__}: {e}"
        (OUT / "px_na_tables.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))


GDP_SEARCH = ["Tổng sản phẩm trong nước", "giá so sánh 2020", "quy mô GDP", "đánh giá lại quy mô", "GDP quý",
              "gross domestic product", "GDP growth", "2020 constant prices", "revised GDP", "tài khoản quốc gia"]


def step_gdp_wp():
    """GDP posts (titles, dates, text) and GDP spreadsheet attachments."""
    posts = {}
    for term in GDP_SEARCH:
        for page in (1, 2, 3):
            items, h = jget("wpposts_gdp", f"{WP}/posts?search={urllib.parse.quote(term)}&per_page=100&page={page}"
                            "&_fields=id,date,link,title,categories", save=False)
            for x in items or []:
                posts[x["id"]] = {"date": x["date"], "link": x["link"], "title": x["title"]["rendered"], "term": term}
            if not items or page >= int(h.get("X-WP-TotalPages", 1) or 1):
                break
    (OUT / "wp_gdp_posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1))
    media = {}
    for term in ("GDP", "Tong-san-pham", "tai-khoan-quoc-gia", "GDP-gia-so-sanh", "Bieu-GDP", "So-lieu-GDP"):
        for page in (1, 2, 3):
            items, h = jget("wpmedia_gdp", f"{WP}/media?search={urllib.parse.quote(term)}&per_page=100&page={page}"
                            "&_fields=id,date,source_url,post,mime_type,title", save=False)
            for x in items or []:
                media[x["id"]] = {"date": x["date"], "url": x["source_url"], "post": x["post"], "mime": x["mime_type"],
                                  "title": x["title"]["rendered"]}
            if not items or page >= int(h.get("X-WP-TotalPages", 1) or 1):
                break
    (OUT / "wp_gdp_media.json").write_text(json.dumps(media, ensure_ascii=False, indent=1))
    for x in media.values():
        if x["url"].lower().endswith((".xlsx", ".xls", ".csv")):
            fetch("gdpfile", x["url"])
    # Full text of GDP-titled posts since 2025 (press releases: expenditure side, revisions, the 2020 rebase)
    for pid, x in sorted(posts.items(), key=lambda kv: kv[1]["date"], reverse=True):
        if x["date"] >= "2025-01-01" and re.search(r"GDP|tổng sản phẩm|kinh tế - xã hội|socio-economic|quy mô", x["title"], re.I):
            fetch("post_gdp", f"{WP}/posts/{pid}?_fields=id,date,modified,link,title,content")


def step_gdp_old():
    """Report workbooks at quarter ends 2010-2019 (GDP tables before the stored 2020- series)."""
    import datetime as _dt
    found = []
    for y in range(2010, 2020):
        for m in (3, 6, 9, 12):
            a = _dt.date(y, m, 15)
            b = _dt.date(y + (m == 12), (m % 12) + 1, 12)
            items, _ = jget("wpmedia_old", f"{WP}/media?after={a}T00:00:00&before={b}T00:00:00&per_page=100"
                            "&_fields=id,date,source_url,post,mime_type", save=False)
            for x in items or []:
                u = x["source_url"]
                if u.lower().endswith((".xlsx", ".xls")):
                    found.append({"quarter": f"{y}Q{m // 3}", **x})
    (OUT / "old_workbooks.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    for x in found:
        if re.search(r"Bieu|bieu|So-lieu|so-lieu|GDP|KTXH|ktxh", x["source_url"]):
            fetch("oldbook_" + x["quarter"], x["source_url"])


PX_FOLDERS = [("en", "E 03. National Accounts and State budget", "E 03. National Accounts and State budget__Px_E_03"),
              ("en", "E 07. Industry", "E 07. Industry__Px_E_07"),
              ("vi", "Tài khoản quốc gia", "Tài khoản quốc gia__Px_V_03")]


def step_gdp_px2():
    """Table lists of the national accounts and industry folders on PX-Web; export every table (PC-Axis)."""
    found = []
    for lang, db, folder in PX_FOLDERS:
        url = f"{PXWEB}/{lang}/{db}/{folder}/"
        s, h, b = fetch(f"pxfolder_{lang}", url + "?tablelist=true")
        if s != 200:
            continue
        for t_url, text in _links(b.decode("utf-8", "replace"), url):
            m = re.search(r"/([^/]+\.px)/?(?:\?|$)", urllib.parse.unquote(t_url), re.I)
            if m and folder in urllib.parse.unquote(t_url):
                found.append({"lang": lang, "db": db, "folder": folder, "table": m.group(1), "text": text})
    seen, uniq = set(), []
    for x in found:
        k = (x["lang"], x["table"])
        if k not in seen:
            seen.add(k); uniq.append(x)
    (OUT / "px_folder_tables.json").write_text(json.dumps(uniq, ensure_ascii=False, indent=1))
    for x in uniq:
        if x["lang"] == "vi":
            continue
        try:
            st, body, ext = px_export(x["lang"], x["db"], x["folder"], x["table"], "FileTypePX")
            x["export"], x["ext"] = SUMMARY[-1]["file"], ext
        except Exception as e:  # noqa: BLE001
            x["error"] = f"{type(e).__name__}: {e}"
        (OUT / "px_folder_tables.json").write_text(json.dumps(uniq, ensure_ascii=False, indent=1))


def step_gdp_bieu():
    """Every 'Bieu'/'So-lieu' spreadsheet in the media library (listing); fetch the quarter-end ones for 2013-2019."""
    media = {}
    for term in ("Bieu", "So-lieu", "Tong-hop-bieu", "Bieu-TH"):
        for page in range(1, 15):
            items, h = jget("wpmedia_bieu", f"{WP}/media?search={urllib.parse.quote(term)}&per_page=100&page={page}"
                            "&_fields=id,date,source_url,post,mime_type", save=False)
            for x in items or []:
                if x["source_url"].lower().endswith((".xls", ".xlsx")):
                    media[x["id"]] = {"date": x["date"], "url": x["source_url"], "post": x["post"]}
            if not items or page >= int(h.get("X-WP-TotalPages", 1) or 1):
                break
    (OUT / "wp_bieu_media.json").write_text(json.dumps(media, ensure_ascii=False, indent=1))
    for x in media.values():
        u = urllib.parse.unquote(x["url"].rsplit("/", 1)[-1])
        m = re.search(r"(?<!\d)(0?3|0?6|0?9|12)[-._ ]+(201[3-9])", u) or re.search(r"T(0?3|0?6|0?9|12)[-._]?(201[3-9])", u)
        if m:
            fetch(f"bieu_{m.group(2)}_{int(m.group(1)):02d}", x["url"])


def step_gdp_posts():
    """Full text of the Q3 2026 socio-economic releases (Vietnamese and English) and the IIP annual table in full."""
    for pid in (62550, 62589, 62545, 62592, 62505, 62518):
        fetch("post_q3", f"{WP}/posts/{pid}?_fields=id,date,modified,link,title,content")
    items, _ = jget("wpposts_en_q3", f"{WP}/posts?search={urllib.parse.quote('third quarter 2026')}&per_page=20&_fields=id,date,link,title", save=True)
    for x in items or []:
        fetch("post_q3_en", f"{WP}/posts/{x['id']}?_fields=id,date,modified,link,title,content")


REBASE_TERMS = ["năm gốc 2020", "năm cơ sở 2020", "giá so sánh 2020", "giá so sánh năm 2020", "chuyển đổi năm gốc",
                "đổi năm gốc", "đánh giá lại quy mô", "điều chỉnh quy mô", "quy mô GDP", "biên soạn lại", "chuỗi số liệu",
                "số liệu GDP giai đoạn", "GDP giai đoạn 2021", "tổng sản phẩm trong nước giai đoạn", "tài khoản quốc gia",
                "base year 2020", "2020 constant prices", "constant 2020 prices", "rebasing", "rebase", "revised GDP",
                "GDP revision", "GDP series", "back series", "revaluation", "national accounts"]
REBASE_RX = re.compile(r"năm gốc|năm cơ sở|giá so sánh (năm )?2020|đánh giá lại|điều chỉnh quy mô|biên soạn lại|chuỗi số liệu|"
                       r"base year|2020 (constant )?prices|constant 2020|rebas|revis|revaluat|back.?series", re.I)


def step_rebase():
    """Exhaustive look for a 2020-price back series: post searches (titles and full text), every post since
    Jun 2025, every media file since Jun 2025 (spreadsheets fetched, PDFs listed), PX-Web database roots."""
    posts = {}
    for term in REBASE_TERMS:
        for page in range(1, 6):
            items, h = jget("rb_search", f"{WP}/posts?search={urllib.parse.quote(term)}&per_page=100&page={page}"
                            "&_fields=id,date,link,title", save=False)
            for x in items or []:
                posts.setdefault(x["id"], {"date": x["date"], "link": x["link"], "title": x["title"]["rendered"], "terms": []})
                posts[x["id"]]["terms"].append(term)
            if not items or page >= int(h.get("X-WP-TotalPages", 1) or 1):
                break
    # every post since Jun 2025 (titles), all pages
    allp = {}
    for page in range(1, 40):
        items, h = jget("rb_all", f"{WP}/posts?after=2025-06-01T00:00:00&per_page=100&page={page}&_fields=id,date,link,title,content",
                        save=False, timeout=180)
        for x in items or []:
            t = _html.unescape(re.sub(r"<[^>]+>", " ", x["content"]["rendered"]))
            hits = [m.group(0)[:300] for m in re.finditer(r"[^.]{0,200}(" + REBASE_RX.pattern + r")[^.]{0,200}", t, re.I)]
            allp[x["id"]] = {"date": x["date"], "link": x["link"], "title": _html.unescape(x["title"]["rendered"]), "hits": hits[:8],
                             "links": [u for u in re.findall(r'href="([^"]+)"', x["content"]["rendered"]) if "wp-content/uploads" in u]}
        if not items or page >= int(h.get("X-WP-TotalPages", 1) or 1):
            break
    (OUT / "rb_posts_search.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1))
    (OUT / "rb_posts_all.json").write_text(json.dumps(allp, ensure_ascii=False, indent=1))
    # full text of every search hit not already covered
    for pid in posts:
        if pid not in allp:
            fetch("rb_post", f"{WP}/posts/{pid}?_fields=id,date,modified,link,title,content")
    # every media item since Jun 2025
    media = {}
    for page in range(1, 60):
        items, h = jget("rb_media", f"{WP}/media?after=2025-06-01T00:00:00&per_page=100&page={page}"
                        "&_fields=id,date,source_url,post,mime_type,title", save=False, timeout=180)
        for x in items or []:
            media[x["id"]] = {"date": x["date"], "url": x["source_url"], "post": x["post"], "mime": x["mime_type"],
                              "title": _html.unescape(x["title"]["rendered"])}
        if not items or page >= int(h.get("X-WP-TotalPages", 1) or 1):
            break
    (OUT / "rb_media.json").write_text(json.dumps(media, ensure_ascii=False, indent=1))
    skip = re.compile(r"CPI|IIP|Lao-dong|XNK|NK-|XK-|Gia-vang|Bieu-thang|Bieu-T\d|So-lieu-CPI", re.I)
    for x in media.values():
        u = x["url"]
        if u.lower().endswith((".xlsx", ".xls", ".csv", ".zip")) and not skip.search(u):
            fetch("rb_file", u)
        elif u.lower().endswith(".pdf") and REBASE_RX.search(urllib.parse.unquote(u) + " " + x["title"]):
            fetch("rb_pdf", u)
    # PX-Web roots again (any new national-accounts database or 2020-price table)
    for lang in ("en", "vi"):
        fetch(f"rb_pxroot_{lang}", f"{PXWEB}/{lang}/")
        jget(f"rb_pxapi_{lang}", f"{PX}/{lang}/")
    for lang, db, folder in PX_FOLDERS:
        fetch(f"rb_pxfolder_{lang}", f"{PXWEB}/{lang}/{db}/{folder}/?tablelist=true")


def _doc_text(path):
    """Text of a PDF, .docx or .doc saved by fetch(), for grepping on the runner (binaries are not pushed if large)."""
    import subprocess
    p = str(path)
    try:
        if p.endswith(".pdf"):
            from pypdf import PdfReader  # noqa: PLC0415
            return "\n".join(f"[page {i + 1}] " + (pg.extract_text() or "") for i, pg in enumerate(PdfReader(p).pages))
        if p.endswith(".docx") or p.endswith(".bin"):
            import docx  # noqa: PLC0415
            return "\n".join(x.text for x in docx.Document(p).paragraphs) + "\n" + "\n".join(
                " | ".join(c.text for c in r.cells) for t in docx.Document(p).tables for r in t.rows)
        return subprocess.run(["antiword", p], capture_output=True, text=True, timeout=120).stdout
    except Exception as e:  # noqa: BLE001
        return f"(text extraction failed: {e})"


def step_g5():
    """Final round: yearbook 2025 versions, SNA methodology book, national accounts metadata (as text, grepped for
    2020 prices); the 9 Apr 2026 chart post and its images; spreadsheets g4 did not reach; PX-Web roots."""
    rx = re.compile(r"giá so sánh (năm )?2020|năm gốc 2020|năm cơ sở 2020|2020 constant|constant 2020|base year 2020|chuyển đổi năm gốc", re.I)
    urls = [u.strip() for u in Path("pipeline/tools/nso_g5_urls.txt").read_text().splitlines() if u.strip() and not u.startswith("#")]
    found = {}
    for u in urls:
        low = u.lower()
        if low.endswith((".pdf", ".docx", ".doc")):
            st, h, b = fetch("g5_doc", u, timeout=300)
            fn = OUT / "files" / SUMMARY[-1]["file"]
            if low.endswith(".docx"):
                fn = fn.rename(fn.with_suffix(".docx"))
            elif low.endswith(".doc"):
                fn = fn.rename(fn.with_suffix(".doc"))
            txt = _doc_text(fn) if st == 200 else ""
            (OUT / "files" / (fn.stem + ".txt")).write_text(txt)
            found[u] = [m.group(0) for m in re.finditer(r".{0,300}(" + rx.pattern + r").{0,300}", txt, re.I | re.S)][:40]
            if fn.stat().st_size > 15_000_000:
                fn.unlink()
        else:
            fetch("g5_file", u)
        (OUT / "g5_doc_hits.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    st, h, b = fetch("g5_post", f"{WP}/posts/60735?_fields=id,date,link,title,content")
    try:
        raw = json.loads(b)["content"]["rendered"]
        for u in re.findall(r'(?:src|data-src|href)="(https://www\.nso\.gov\.vn/wp-content/uploads/[^"]+\.(?:png|jpe?g|webp))"', raw):
            fetch("g5_img", u)
    except Exception:  # noqa: BLE001
        pass
    for lang in ("en", "vi"):
        fetch(f"g5_pxroot_{lang}", f"{PXWEB}/{lang}/")
    for lang, db, folder in PX_FOLDERS:
        fetch(f"g5_pxfolder_{lang}", f"{PXWEB}/{lang}/{db}/{folder}/?tablelist=true")


def step_intl():
    """International sources for a long Vietnam GDP series: World Bank WDI (series and country notes), IMF WEO,
    IMF quarterly and annual national accounts (structure first, then Vietnam data), UN, DBnomics."""
    WB = "https://api.worldbank.org/v2"
    for ind in ("NY.GDP.MKTP.KN", "NY.GDP.MKTP.KD", "NY.GDP.MKTP.KD.ZG", "NY.GDP.MKTP.CN", "NY.GDP.DEFL.ZS",
                "NV.IND.MANF.KN", "NV.IND.MANF.CN", "NV.IND.MANF.ZS", "NV.IND.MANF.KD.ZG", "NE.CON.PRVT.KN", "NE.GDI.FTOT.KN"):
        fetch("wb_" + ind, f"{WB}/country/VNM/indicator/{ind}?format=json&per_page=200")
        fetch("wbmeta_" + ind, f"{WB}/sources/2/country/VNM/series/{ind}/metadata?format=json")
    fetch("wb_country_meta", f"{WB}/sources/2/country/VNM/metadata?format=json")
    fetch("wb_country", f"{WB}/country/VNM?format=json")
    IMF = "https://api.imf.org/external/sdmx/3.0"
    for ind in ("NGDP_R", "NGDP_RPCH", "NGDP", "NGDP_D"):
        fetch("weo_" + ind, f"{IMF}/data/dataflow/IMF.RES/WEO/+/VNM.{ind}.A")
    fetch("weo_struct", f"{IMF}/structure/dataflow/IMF.RES/WEO/+?detail=full&references=none")
    for flow in ("QNEA", "ANEA", "NEA"):
        fetch(f"imf_{flow}_struct", f"{IMF}/structure/dataflow/IMF.STA/{flow}/+?references=datastructure")
        fetch(f"imf_{flow}_vnm", f"{IMF}/data/dataflow/IMF.STA/{flow}/+/*?c%5BCOUNTRY%5D=VNM&dimensionAtObservation=TIME_PERIOD&detail=serieskeysonly")
        fetch(f"imf_{flow}_vnm_full", f"{IMF}/data/dataflow/IMF.STA/{flow}/+/*?c%5BCOUNTRY%5D=VNM")
    fetch("imf_dataflows", f"{IMF}/structure/dataflow/*/*/+?detail=allstubs")
    DB = "https://api.db.nomics.world/v22"
    for path in ("series/WB/WDI/A-NY.GDP.MKTP.KN-VNM", "series/IMF/WEO:latest/VNM.NGDP_R.national_currency",
                 "search?q=viet%20nam%20gross%20domestic%20product%20quarterly&limit=50",
                 "search?q=vietnam%20GDP%20constant%20prices&limit=50", "providers"):
        fetch("dbn", f"{DB}/{path}{'&' if '?' in path else '?'}observations=1")
    fetch("un_ama", "https://unstats.un.org/unsd/amaapi/api/file/6")
    fetch("un_ama_list", "https://unstats.un.org/unsd/amaapi/api/file")
    fetch("asean", "https://data.aseanstats.org/api/indicators")


def _xlrd_lenient():
    import importlib
    uni = lambda b, enc: b.decode(enc, "replace")  # noqa: E731 - some NSO .xls files carry broken UTF-16 strings
    for m in ("xlrd.biffh", "xlrd.book", "xlrd.sheet"):
        mod = importlib.import_module(m)
        if hasattr(mod, "unicode"):
            mod.unicode = uni


def step_g7():
    """Older socio-economic report books (2006-2019) and NSO's 2014 official series file: keep only the GDP sheets
    (first 60 rows as text), not the binaries."""
    import io
    _xlrd_lenient()
    import xlrd, openpyxl  # noqa: E401
    urls = [u.strip() for u in Path("pipeline/tools/nso_g7_urls.txt").read_text().splitlines() if u.strip()]
    out = {}
    rx = re.compile(r"Tổng sản phẩm trong nước|TỔNG SẢN PHẨM TRONG NƯỚC|Gross domestic product|GROSS DOMESTIC PRODUCT|\bGDP\b")
    for u in urls:
        st, h, b = fetch("g7", u, save=False)
        if st != 200:
            out[u] = {"error": st}
            continue
        try:
            if u.lower().endswith(".xls"):
                wb = xlrd.open_workbook(file_contents=b)
                sheets = [(sh.name, [[str(c) for c in sh.row_values(i)] for i in range(min(sh.nrows, 60))]) for sh in wb.sheets()]
            else:
                wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
                sheets = [(ws.title, [["" if c is None else str(c) for c in r] for _, r in zip(range(60), ws.iter_rows(values_only=True))]) for ws in wb.worksheets]
        except Exception as e:  # noqa: BLE001
            out[u] = {"error": f"{type(e).__name__}: {e}"[:200]}
            continue
        g = {n: rows for n, rows in sheets if rx.search(" ".join(c for r in rows[:4] for c in r))}
        out[u] = {"sheets": [n for n, _ in sheets], "gdp": g}
        if "Day-so-lieu" in u:
            (OUT / "files" / (re.sub(r"[^A-Za-z0-9.-]", "_", u.rsplit("/", 1)[-1]))).write_bytes(b)
        (OUT / "g7_gdp_sheets.json").write_text(json.dumps(out, ensure_ascii=False))


def step_g8():
    """World Bank income classification history for Vietnam: OGHIST (fiscal-year groups and thresholds) and WDI GNI per
    capita, Atlas method (NY.GNP.PCAP.CD), 2005-2012."""
    import io
    import openpyxl
    out = {}
    for u in ["https://datacatalogfiles.worldbank.org/ddh-published/0037712/DR0090754/OGHIST.xlsx",
              "https://ddh-openapi.worldbank.org/resources/DR0090754/download",
              "https://databankfiles.worldbank.org/public/ddpext_download/site-content/OGHIST.xlsx",
              "https://databankfiles.worldbank.org/data/download/site-content/OGHIST.xlsx"]:
        st, h, b = fetch("g8", u, save=False)
        out[u] = {"status": st}
        if st != 200:
            continue
        try:
            wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
            keep = {}
            for ws in wb.worksheets:
                rows = [["" if c is None else str(c) for c in r] for r in ws.iter_rows(values_only=True)]
                keep[ws.title] = [r for r in rows[:15]] + [r for r in rows if any(c in ("VNM", "Vietnam", "Viet Nam") for c in r[:3])]
                keep[ws.title] += [r for r in rows if r and any("threshold" in c.lower() or "Low income" in c for c in r[:2])][:20]
            out[u]["sheets"] = keep
            break
        except Exception as e:  # noqa: BLE001
            out[u]["error"] = f"{type(e).__name__}: {e}"[:200]
    st, h, b = fetch("g8", "https://api.worldbank.org/v2/country/VNM/indicator/NY.GNP.PCAP.CD?format=json&date=2005:2012", save=False)
    out["wdi_gni_pc_atlas"] = {"status": st, "body": b.decode("utf-8", "replace")[:6000] if st == 200 else ""}
    (OUT / "g8_income_class.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("G8JSON " + json.dumps(out, ensure_ascii=False), flush=True)   # also in the log (discovery branch push can collide)


def main(out, steps="px,wp,files"):
    global OUT
    OUT = Path(out)
    (OUT / "files").mkdir(parents=True, exist_ok=True)
    for s in steps.split(","):
        try:
            {"px": step_px, "wp": step_wp, "files": step_files, "pxweb": step_pxweb,
             "posts": step_posts, "files2": step_files2,
             "quarters": step_quarters, "misc": step_misc,
             "gdp_px": step_gdp_px, "gdp_wp": step_gdp_wp, "gdp_old": step_gdp_old,
             "gdp_px2": step_gdp_px2, "gdp_bieu": step_gdp_bieu,
             "gdp_posts": step_gdp_posts, "rebase": step_rebase, "g5": step_g5, "intl": step_intl, "g7": step_g7, "g8": step_g8}[s]()
        except Exception as e:  # noqa: BLE001
            SUMMARY.append({"name": f"step_{s}", "error": f"{type(e).__name__}: {e}"})
            print("step failed", s, e, flush=True)
    (OUT / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
