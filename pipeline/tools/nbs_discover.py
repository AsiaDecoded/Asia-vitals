"""Probe China's NBS sources (and headline-only fallbacks) from GitHub Actions.

  python -I pipeline/tools/nbs_discover.py discovery/nbs

Order tested:
  1. NBS data portal, easyquery (data.stats.gov.cn), monthly database hgyd (and fsyd, provinces)
  2. NBS press releases (English, and the Chinese originals with NBS's interpretation notes)
  3. Fallbacks for the headline only: DBnomics (provider NBS), OECD SDMX

Every request is logged to <out>/log.json: URL, HTTP status, bytes, error text. Raw responses
are saved as-is. No PDFs are fetched.
"""
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/nbs")
OUT.mkdir(parents=True, exist_ok=True)
LOG = []

CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX),
                                     urllib.request.HTTPCookieProcessor(JAR))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 asia-vitals")


DEAD = {}  # host -> consecutive connection failures; after 3, the host is skipped


def fetch(name, url, data=None, headers=None, timeout=45, save=True, ext=None):
    host = urllib.parse.urlsplit(url).netloc
    if DEAD.get(host, 0) >= 3:
        LOG.append({"name": name, "url": url, "status": None, "error": "skipped: host failed 3 times", "bytes": 0})
        return None
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en,zh-CN;q=0.8"}
    h.update(headers or {})
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    rec = {"name": name, "url": url, "post": data if isinstance(data, dict) else None}
    t0 = time.time()
    raw = None
    try:
        req = urllib.request.Request(url, data=body, headers=h)
        with OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
            rec.update(status=r.status, final_url=r.geturl(), ctype=r.headers.get("Content-Type"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        rec.update(status=e.code, error=f"HTTPError {e.code} {e.reason}")
    except Exception as e:  # noqa: BLE001
        rec.update(status=None, error=f"{type(e).__name__}: {e}")
    rec["bytes"] = len(raw) if raw else 0
    DEAD[host] = DEAD.get(host, 0) + 1 if rec.get("status") is None else 0
    rec["secs"] = round(time.time() - t0, 1)
    if raw:
        rec["head"] = raw[:300].decode("utf-8", "replace")
        if save:
            ext = ext or (".json" if raw[:1] in (b"{", b"[") else ".html")
            (OUT / f"{name}{ext}").write_bytes(raw)
    LOG.append(rec)
    print(f"{rec.get('status')} {rec['bytes']:>8} {rec['secs']:>5}s {name} {rec.get('error', '')}", flush=True)
    return raw


def text(raw):
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def js(raw):
    try:
        return json.loads(text(raw))
    except Exception:  # noqa: BLE001
        return None


def k1():
    return str(int(time.time() * 1000))


# ---------------------------------------------------------------- 1. data portal
def portal():
    res = {}
    for lang, base in (("cn", "https://data.stats.gov.cn"), ("en", "https://data.stats.gov.cn/english")):
        fetch(f"portal_home_{lang}", base + "/")
        fetch(f"portal_home_{lang}_http", base.replace("https:", "http:") + "/")
        ep = base + "/easyquery.htm"
        hdr = {"Referer": base + "/easyquery.htm?cn=A01", "X-Requested-With": "XMLHttpRequest"}
        fetch(f"portal_page_{lang}", base + "/easyquery.htm?cn=A01", save=True)
        tree = {}

        def walk(db, node_id, depth=0):
            raw = fetch(f"tree_{lang}_{db}_{node_id}", ep,
                        data={"id": node_id, "dbcode": db, "wdcode": "zb", "m": "getTree"},
                        headers=hdr, save=False)
            nodes = js(raw)
            if not isinstance(nodes, list):
                return
            for n in nodes:
                tree[n["id"]] = {"name": n.get("name"), "parent": node_id, "isParent": n.get("isParent")}
                if n.get("isParent") and depth < 4 and (node_id != "zb" or n["id"] == "A01"):
                    walk(db, n["id"], depth + 1)
                    time.sleep(0.3)

        walk("hgyd", "zb")
        (OUT / f"tree_{lang}_hgyd.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1))
        res[f"tree_{lang}"] = len(tree)
        # Data: query each parent of leaves under A01 (all CPI/PPI families), full history
        parents = sorted({v["parent"] for k, v in tree.items() if k.startswith("A01") and not v["isParent"]})
        if not parents:
            parents = ["A0101", "A0102", "A0103", "A0104", "A0105", "A0106", "A0107", "A0108", "A0109",
                       "A010A", "A010B", "A010C", "A010D"]
        for p in parents:
            for sj in ("199001-", "LAST13"):
                raw = fetch(f"data_{lang}_hgyd_{p}_{sj.strip('-')}", ep + "?" + urllib.parse.urlencode({
                    "m": "QueryData", "dbcode": "hgyd", "rowcode": "zb", "colcode": "sj", "wds": "[]",
                    "dfwds": json.dumps([{"wdcode": "zb", "valuecode": p}, {"wdcode": "sj", "valuecode": sj}]),
                    "k1": k1()}), headers=hdr)
                d = js(raw)
                if d and d.get("returncode") == 200:
                    break
                time.sleep(0.5)
            time.sleep(0.5)
        if lang == "en":
            continue
        # Provinces: monthly regional database fsyd
        ftree = {}
        raw = fetch("tree_cn_fsyd_zb", ep, data={"id": "zb", "dbcode": "fsyd", "wdcode": "zb", "m": "getTree"},
                    headers=hdr)
        for n in js(raw) or []:
            ftree[n["id"]] = n.get("name")
        raw = fetch("tree_cn_fsyd_A01", ep, data={"id": "A01", "dbcode": "fsyd", "wdcode": "zb", "m": "getTree"},
                    headers=hdr)
        sub = js(raw) or []
        for n in sub[:3]:
            raw = fetch(f"tree_cn_fsyd_{n['id']}", ep, data={"id": n["id"], "dbcode": "fsyd", "wdcode": "zb",
                                                             "m": "getTree"}, headers=hdr)
            leaves = js(raw) or []
            if leaves:
                code = leaves[0]["id"]
                fetch(f"data_cn_fsyd_{code}", ep + "?" + urllib.parse.urlencode({
                    "m": "QueryData", "dbcode": "fsyd", "rowcode": "reg", "colcode": "sj",
                    "wds": json.dumps([{"wdcode": "zb", "valuecode": code}]),
                    "dfwds": json.dumps([{"wdcode": "sj", "valuecode": "LAST13"}]), "k1": k1()}), headers=hdr)
        res["fsyd"] = len(ftree)
    return res


# ---------------------------------------------------------------- 2. press releases
def links(html, base):
    out = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S):
        label = re.sub(r"<[^>]+>", "", label).strip()
        out.append((urllib.parse.urljoin(base, href), label))
    return out


def releases():
    found = {}
    # English
    pages = ["https://www.stats.gov.cn/english/PressRelease/"] + \
            [f"https://www.stats.gov.cn/english/PressRelease/index_{i}.html" for i in range(1, 8)]
    eng = []
    for i, u in enumerate(pages):
        raw = fetch(f"en_list_{i}", u)
        if raw:
            eng += links(text(raw), u)
        time.sleep(0.5)
    pick = [(u, l) for u, l in eng if re.search(r"Consumer Price|Producer Price|CPI|PPI", l, re.I)]
    found["en_links"] = pick[:60]
    for j, (u, l) in enumerate(pick[:24]):
        fetch(f"en_rel_{j:02d}", u)
        time.sleep(0.5)
    # Chinese originals (latest releases and NBS interpretation), same agency
    zh = []
    for sect in ("zxfb", "sjjd"):
        for i in range(0, 12):
            u = f"https://www.stats.gov.cn/sj/{sect}/" + ("" if i == 0 else f"index_{i}.html")
            raw = fetch(f"zh_{sect}_list_{i}", u)
            if raw:
                zh += [(x, l, sect) for x, l in links(text(raw), u)]
            time.sleep(0.4)
    pick = [(u, l, s) for u, l, s in zh if re.search(r"居民消费价格|工业生产者|CPI|PPI|价格", l)]
    seen, uniq = set(), []
    for u, l, s in pick:
        if u not in seen and u.endswith(".html"):
            seen.add(u)
            uniq.append((u, l, s))
    found["zh_links"] = uniq[:120]
    for j, (u, l, s) in enumerate(uniq[:40]):
        fetch(f"zh_rel_{s}_{j:02d}", u)
        time.sleep(0.4)
    # Release calendar
    for name, u in (("zh_calendar", "https://www.stats.gov.cn/sj/fbrc/"),
                    ("en_calendar", "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/")):
        raw = fetch(name, u)
        if raw:
            found[name + "_links"] = [x for x in links(text(raw), u) if re.search(r"20(26|27)", x[1])][:20]
    for j, (u, l) in enumerate((found.get("zh_calendar_links") or [])[:3]):
        if u.endswith(".html"):
            fetch(f"zh_calendar_{j}", u)
    (OUT / "release_links.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- 3. fallbacks
def fallbacks():
    d = "https://api.db.nomics.world/v22"
    fetch("dbn_provider", f"{d}/providers/NBS")
    raw = fetch("dbn_datasets", f"{d}/datasets/NBS?limit=500")
    ds = js(raw) or {}
    codes = [x.get("code") for x in ((ds.get("datasets") or {}).get("docs") or [])]
    price = [c for c, x in zip(codes, (ds.get("datasets") or {}).get("docs") or [])
             if re.search(r"price|CPI|A01", json.dumps(x), re.I)]
    for c in price[:6]:
        fetch(f"dbn_series_{c}", f"{d}/series/NBS/{c}?limit=50&observations=1")
        time.sleep(0.5)
    fetch("dbn_search", f"{d}/search?q=china%20consumer%20price%20index&limit=20")
    o = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
    fetch("oecd_cpi_headline", f"{o}/CHN.M.N.CPI.PA._T.N.GY?startPeriod=2024-01&format=csvfilewithlabels", ext=".csv")
    fetch("oecd_cpi_all", f"{o}/CHN.M......?startPeriod=2026-01&format=csvfilewithlabels", ext=".csv")
    fetch("oecd_ppi", "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_PPI@DF_PRICES_PPI,1.0/"
          "CHN.M.......?startPeriod=2025-01&format=csvfilewithlabels", ext=".csv")


# ---------------------------------------------------------------- stage 2
def stage2():
    """New data portal (single-page app): its scripts, to find the data API; DBnomics full
    history for the monthly price datasets; OECD headline history; NBS's notes on the 2026
    base rotation and the September 2026 interpretation."""
    base = "https://data.stats.gov.cn/"
    for n in ("setting/script", "common/config_project.js", "common/global_project.js",
              "static/js/project/dsf-pc.js", "static/js/project/subPage.js",
              "modules/dataview/js/dsf-dataview.common.js", "modules/dataview/js/dsf-dataview.pc.js",
              "modules/platform/js/dsf-platform.common.js", "modules/core/js/dsf-core.js", "robots.txt"):
        fetch("spa_" + re.sub(r"\W", "_", n), base + n, ext=".txt")
    d = "https://api.db.nomics.world/v22/series/NBS"
    for ds in ("M_A01010J", "M_A01010K", "M_A01010L", "M_A01020J", "M_A01030J", "M_A01010G",
               "M_A010101", "M_A010102", "M_A010801", "M_A010701", "M_A010804", "M_A010807", "M_A010H"):
        fetch(f"dbn_obs_{ds}", f"{d}/{ds}?observations=1&limit=1000")
        time.sleep(0.4)
    o = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
    fetch("oecd_cpi_headline_full", f"{o}/CHN.M.N.CPI.PA._T.N.GY?startPeriod=1985-01&format=csvfilewithlabels", ext=".csv")
    fetch("oecd_cpi_index_full", f"{o}/CHN.M.N.CPI.IX._T.N._Z?startPeriod=1985-01&format=csvfilewithlabels", ext=".csv")
    for name, u in (
            ("zh_sjjd_rotation", "https://www.stats.gov.cn/sj/sjjd/202602/t20260211_1962589.html"),
            ("zh_sjjd_sep2026", "https://www.stats.gov.cn/sj/sjjd/202610/t20261014_1965475.html"),
            ("zh_sjjd_q3_2026", "https://www.stats.gov.cn/sj/sjjd/202610/t20261019_1965630.html"),
            ("zh_sjjd_2025", "https://www.stats.gov.cn/sj/sjjd/202601/t20260119_1962341.html")):
        fetch(name, u)
        time.sleep(0.4)
    for i in (10, 20, 40, 60, 80, 100, 120):
        fetch(f"en_list_{i}", f"https://www.stats.gov.cn/english/PressRelease/index_{i}.html")
    for i in range(12, 40):
        fetch(f"zh_zxfb_list_{i}", f"https://www.stats.gov.cn/sj/zxfb/index_{i}.html")
        time.sleep(0.3)
    fetch("en_calendar_2026", "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/202512/t20251226_1962154.html")
    fetch("runner_ip", "https://ipinfo.io/json")
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def stage3():
    """The new data portal (data.stats.gov.cn/dg/website/): page, scripts and the API paths in them."""
    base = "https://data.stats.gov.cn/dg/website/"
    raw = fetch("p3_page", base + "page.html")
    page = text(raw)
    srcs = re.findall(r'(?:src|href)="([^"]+\.(?:js|json)[^"]*)"', page) + ["setting/script"]
    found = {}
    for i, s in enumerate(srcs):
        u = urllib.parse.urljoin(base + "page.html", s)
        r = fetch(f"p3_js_{i:02d}", u, ext=".txt", timeout=90)
        t = text(r)
        for m in set(re.findall(r'["\'`](/?[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-\.]+){1,8})["\'`]', t)):
            if re.search(r"(?i)api|query|data|search|tree|esdata|indicator|publicrelease|external|cube|index|menu", m) \
                    and not re.search(r"\.(css|png|svg|gif|jpg|woff|ttf|vue)$", m):
                found.setdefault(m, []).append(i)
        time.sleep(0.3)
    (OUT / "api_paths.json").write_text(json.dumps({"scripts": srcs, "paths": found}, ensure_ascii=False, indent=1))
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def stage4():
    """The portal's data-page chunks, the API calls they make, and a bare call to each."""
    base = "https://data.stats.gov.cn/dg/website/"
    hdr = {"Referer": base + "page.html", "Origin": "https://data.stats.gov.cn"}
    fetch("p4_page", base + "page.html")
    chunks = ["DataPage", "DataPage~ReportPage~SearchPage", "project_national_datapage", "project_national_datatree",
              "DataPage~MapPage~ReportPage~project_national_datapage~project_national_home",
              "MapPage~ReportPage~project_national_datapage~project_national_home", "project_national_home",
              "ReportPage", "SearchPage", "project_national_page"]
    paths = {}
    for c in chunks:
        r = fetch("p4_chunk_" + c.replace("~", "-")[:60], base + "static/js/project/" + urllib.parse.quote(c) + ".js",
                  ext=".txt", headers=hdr, timeout=90)
        t = text(r)
        for m in re.findall(r'["\'`]((?:/[A-Za-z0-9_\-]+){2,9})["\'`?]', t):
            if "external" in m or "/api/" in m or "data" in m.lower():
                paths.setdefault(m, []).append(c)
        time.sleep(0.3)
    (OUT / "api_paths.json").write_text(json.dumps(paths, ensure_ascii=False, indent=1))
    for i, m in enumerate(sorted(paths)):
        if m.startswith("/publicrelease/") or m.startswith("/api/"):
            fetch(f"p4_get_{i:03d}", "https://data.stats.gov.cn/dg/website" + m, headers=hdr, ext=".txt")
            time.sleep(0.4)
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def stage5():
    """Call the new portal's data API: indicator tree (monthly national, code 1; monthly by
    province, code 4), indicators under the price nodes, their date range, and data."""
    ext = "https://data.stats.gov.cn/dg/website/publicrelease/web/external"
    hdr = {"Referer": "https://data.stats.gov.cn/dg/website/page.html", "Origin": "https://data.stats.gov.cn",
           "Accept": "application/json, text/plain, */*"}

    def get(name, path, params):
        r = fetch(name, ext + path + "?" + urllib.parse.urlencode(params), headers=hdr, ext=".json")
        return js(r)

    def post(name, path, body):
        r = fetch(name, ext + path, data=json.dumps(body).encode(), ext=".json",
                  headers={**hdr, "Content-Type": "application/json;charset=UTF-8"})
        return js(r)

    report = {}
    for code in ("1", "4"):
        tree = {}
        top = get(f"t5_tree_{code}_root", "/new/queryIndexTreeAsync", {"pid": "", "code": code}) or {}
        level = top.get("data") or []
        for n in level:
            tree[n["_id"]] = {k: n.get(k) for k in ("_name", "name", "show_name", "isLeaf", "treeinfo_level", "treeinfo_pid")}
        # walk only nodes whose name mentions prices
        def pname(n):
            return str(n.get("_name") or n.get("name") or n.get("show_name") or "")
        queue = [n for n in level if not n.get("isLeaf")]
        steps = 0
        while queue and steps < 80:
            n = queue.pop(0)
            nm = pname(n)
            depth = n.get("treeinfo_level") or 0
            if depth and int(depth) >= 2 and "价格" not in nm and "指数" not in nm:
                continue
            steps += 1
            sub = (get(f"t5_tree_{code}_{steps:03d}", "/new/queryIndexTreeAsync", {"pid": n["_id"], "code": code}) or {}).get("data") or []
            for c in sub:
                tree[c["_id"]] = {**{k: c.get(k) for k in ("_name", "name", "show_name", "isLeaf", "treeinfo_level")}, "parent": n["_id"]}
                if not c.get("isLeaf") and ("价格" in pname(c) or int(c.get("treeinfo_level") or 0) <= 2):
                    queue.append(c)
            time.sleep(0.3)
        (OUT / f"tree_{code}.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1))
        leaves = [k for k, v in tree.items() if v.get("isLeaf") and ("居民消费价格" in str(v) or "工业生产者" in str(v))]
        report[f"code{code}_nodes"] = len(tree)
        report[f"code{code}_price_leaves"] = len(leaves)
        root_id = level[0]["_id"] if level else ""
        for j, cid in enumerate(leaves[:12]):
            ind = get(f"t5_ind_{code}_{j:02d}", "/new/queryIndicatorsByCid", {"cid": cid, "dt": "", "name": ""}) or {}
            lst = ((ind.get("data") or {}).get("list")) or []
            dt = get(f"t5_dt_{code}_{j:02d}", "/new/queryDtByCid", {"cid": cid, "rootId": root_id}) or {}
            ids = [x.get("_id") for x in lst][:40]
            if not ids:
                continue
            for k, dts in enumerate((["199001MM-202609MM"], ["199001-202609"], ["202501MM-202609MM"], [""])):
                body = {"cid": cid, "indicatorIds": ids, "daCatalogId": "", "das": [], "showType": 1, "dts": dts,
                        "rootId": root_id}
                if code == "4":
                    body["das"] = [{"text": "北京市", "value": "110000000000"}, {"text": "上海市", "value": "310000000000"}]
                d = post(f"t5_data_{code}_{j:02d}_{k}", "/getEsDataByIndicatorIdAndDa", body) or {}
                if d.get("success") and d.get("data"):
                    break
                time.sleep(0.3)
            time.sleep(0.3)
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


def main():
    if len(sys.argv) > 2 and sys.argv[2] == "stage5":
        return stage5()
    if len(sys.argv) > 2 and sys.argv[2] == "stage4":
        return stage4()
    if len(sys.argv) > 2 and sys.argv[2] == "stage2":
        return stage2()
    if len(sys.argv) > 2 and sys.argv[2] == "stage3":
        return stage3()
    summary = {}
    for name, fn in (("portal", portal), ("releases", releases), ("fallbacks", fallbacks)):
        try:
            summary[name] = fn()
        except Exception as e:  # noqa: BLE001
            summary[name] = f"crashed: {type(e).__name__}: {e}"
            print(summary[name], flush=True)
        (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    # Outbound IP and region of the runner (NBS blocks some non-China IPs)
    fetch("runner_ip", "https://ipinfo.io/json")
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
