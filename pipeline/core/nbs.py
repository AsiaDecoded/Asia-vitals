"""China National Bureau of Statistics (NBS) data portal client, no key.

The portal at data.stats.gov.cn was rebuilt in 2025-26; the old easyquery.htm interface returns
HTTP 403 (WAF "UrlACL"). The new site (data.stats.gov.cn/dg/website/) is a single-page app over a
JSON API under /dg/website/publicrelease/web/external/:

  GET  new/queryIndexTreeAsync?pid=&code=   indicator catalog tree (code 1 = monthly national,
                                            4 = monthly by province); leaves are catalogs (cid)
  GET  new/queryIndicatorsByCid?cid=        indicators in a catalog (_id, ek, i_showname, ...)
  GET  new/queryDtByCid?cid=&rootId=        latest period in a catalog
  GET  getDaCatalogTreeByIndicatorCid?indicatorCid=   area catalogs for a catalog (provinces)
  POST stream/esData                        table: {cid, indicatorIds, daCatalogId, das, showType,
                                            dts: ["198301MM-202609MM"], rootId} -> [{code: "202609MM",
                                            values: [{ek, i_showname, value, da, da_name, ...}]}]

Values are as published: indices with the comparison period = 100 (same month last year = 100,
same period last year = 100, previous month = 100), one decimal.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://data.stats.gov.cn/dg/website/publicrelease/web/external"
HDR = {
    "User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://data.stats.gov.cn/dg/website/page.html",
    "Origin": "https://data.stats.gov.cn",
}
NATIONAL = "000000000000"
ROOT_MONTHLY = "fc982599aa684be7969d7b90b1bd0e84"      # 月度数据 (tree code 1)
ROOT_PROVINCE = "f4c6cd795fea436c807163397dd36b98"     # 分省月度数据 (tree code 4)


class NBSError(RuntimeError):
    pass


# The portal's firewall answers bursts of requests with a redirect that sets a cookie; keep cookies
# so the redirect resolves, and keep concurrency low.
import http.cookiejar as _cj
_JAR = _cj.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))


def _call(path, params=None, body=None, tries=6, timeout=120):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = dict(HDR)
    if data is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with _OPENER.open(req, timeout=timeout) as r:
                raw = r.read()
            try:
                out = json.loads(raw.decode("utf-8"))
            except ValueError:
                # The portal answers bad parameters with an HTML error page (HTTP 200)
                raise NBSError(f"non-JSON answer from {path}: {raw[:120]!r}")
            if not out.get("success"):
                raise NBSError(f"{path}: {out.get('state')} {out.get('message')}")
            return out.get("data")
        except (urllib.error.URLError, TimeoutError, NBSError, ConnectionError) as e:
            err = e
            time.sleep(10 * (i + 1))
    raise NBSError(f"NBS request failed: {url}: {err!r}")


def tree(code, pid=""):
    return _call("new/queryIndexTreeAsync", {"pid": pid, "code": code}) or []


def indicators(cid):
    return ((_call("new/queryIndicatorsByCid", {"cid": cid, "dt": "", "name": ""}) or {}).get("list")) or []


def latest(cid, root=ROOT_MONTHLY):
    """Latest period in a catalog, e.g. '202609'."""
    d = _call("new/queryDtByCid", {"cid": cid, "rootId": root}) or {}
    return (d.get("dt_all") or "").replace("MM", "") or None


def area_catalogs(cid):
    return _call("getDaCatalogTreeByIndicatorCid", {"indicatorCid": cid}) or []


def table(cid, ids, start="198301", end="203012", root=ROOT_MONTHLY, das=None, da_catalog=""):
    """Rows {period 'YYYY-MM', ek, name, value (str), area, area_name} for indicators `ids` of catalog `cid`."""
    body = {"cid": cid, "indicatorIds": list(ids), "daCatalogId": da_catalog,
            "das": das if das is not None else [{"text": "全国", "value": NATIONAL}],
            "showType": 1, "dts": [f"{start}MM-{end}MM"], "rootId": root}
    if da_catalog:
        body["das"] = []
    data = _call("stream/esData", body=body) or []
    rows = []
    for per in data:
        code = per.get("code") or ""
        if not code.endswith("MM"):
            continue
        p = f"{code[:4]}-{code[4:6]}"
        for v in per.get("values") or []:
            val = v.get("value")
            if val in (None, "", "null"):
                continue
            rows.append({"period": p, "ek": v.get("ek"), "id": v.get("_id"),
                         "name": (v.get("i_showname") or "").strip(), "value": str(val).strip(),
                         "area": v.get("da"), "area_name": v.get("da_name")})
    return rows, data


def catalogs(code, root, keep):
    """Leaf catalogs under `root` whose path or name passes keep(path, name): {cid: {name, path, sdate, edate}}.

    Only branches whose name mentions prices (价格) are walked below the root.
    """
    out, queue = {}, [(root, "")]
    while queue:
        pid, path = queue.pop(0)
        for n in tree(code, pid):
            nm = (n.get("_name") or n.get("name") or "").strip()
            if pid == root and "价格" not in nm:
                continue
            if n.get("isLeaf"):
                if keep(path, nm):
                    out[n["_id"]] = {"name": nm, "path": path, "sdate": n.get("sdate"), "edate": n.get("edate")}
            else:
                queue.append((n["_id"], (path + " > " + nm).strip(" >")))
        time.sleep(0.2)
    return out


def provinces():
    """[{text, value}] for the 31 provinces (value '110000000000' ...)."""
    return _call("getAllProvince") or []


def parallel(fn, items, workers=3):
    """[fn(x) for x in items] on a few threads (the portal answers one table in a few seconds)."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def province_rows(cid, ids, start="198301", end="203012"):
    """Rows for every province, one call per province: a call with several areas (das) or with the
    area catalog ('全部地区') as daCatalogId returns only the first province."""
    def one(p):
        return p, table(cid, ids, start, end, root=ROOT_PROVINCE, das=[{"text": p.get("text"), "value": p.get("value")}])
    rows, data = [], []
    for p, (r, d) in parallel(one, provinces(), workers=3):
        rows += r
        data.append({"area": p.get("value"), "data": d})
    if not rows:
        raise NBSError(f"no provincial rows for catalog {cid}")
    return rows, data


# ---------------------------------------------------------------- NBS release pages (HTML, stats.gov.cn)
# The monthly CPI release (最新发布, /sj/zxfb/) and the chief statistician's interpretation (数据解读,
# /sj/sjjd/) state NBS's own "impact on CPI" figures in their text: published contributions, in
# percentage points, for the items NBS chooses to mention each month.
import html as _html
import re as _re

WWW = "https://www.stats.gov.cn"
ZH_NAMES = {
    "食品烟酒及在外餐饮类": ("food_tobacco_liquor", "Food, tobacco, liquor and dining out"),
    "食品烟酒类": ("food_tobacco_liquor", "Food, tobacco and liquor"),
    "食品": ("food", "Food"), "能源": ("energy", "Energy"), "服务": ("services", "Services"),
    "扣除能源的工业消费品": ("goods_ex_energy", "Industrial consumer goods excluding energy"),
    "工业消费品": ("industrial_goods", "Industrial consumer goods"), "消费品": ("goods", "Consumer goods"),
    "鲜菜": ("fresh_vegetables", "Fresh vegetables"), "畜肉类": ("livestock_meat", "Meat of livestock"),
    "猪肉": ("pork", "Pork"), "牛肉": ("beef", "Beef"), "羊肉": ("mutton", "Mutton"), "鲜果": ("fresh_fruit", "Fresh fruits"),
    "蛋类": ("eggs", "Eggs"), "蛋": ("eggs", "Eggs"), "畜肉": ("livestock_meat", "Meat of livestock"), "鸡蛋": ("eggs", "Eggs"), "水产品": ("aquatic", "Aquatic products"), "粮食": ("grain", "Grain"),
    "食用油": ("edible_oil", "Edible oil"), "奶类": ("dairy", "Dairy"), "汽油": ("gasoline", "Gasoline"),
    "黄金饰品": ("gold_jewellery", "Gold jewellery"), "飞机票": ("air_fares", "Air fares"),
    "宾馆住宿": ("hotels", "Hotel accommodation"), "教育服务": ("education_services", "Education services"),
    "服装": ("garments", "Garments"), "医疗服务": ("medical_services", "Medical services"),
    "交通工具用燃料": ("vehicle_fuel", "Fuel for vehicles"), "出行服务": ("travel_services", "Travel services"),
}


def _get_html(url, tries=3):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": HDR["User-Agent"]})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (i + 1))
    raise NBSError(f"{url}: {err!r}")


def _text(page):
    s = _re.sub(r"(?is)<(script|style).*?</\1>", "", page)
    m = _re.search(r'(?is)<div[^>]+class="[^"]*TRS_Editor[^"]*".*', s)
    if m:
        s = m.group(0)
    s = _re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", s)
    s = _re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s).replace("　", "").replace("\xa0", " ")
    return _re.sub(r"[ \t]+", "", s)


def release_links(section, pages, pattern):
    """[(year, month, release date 'YYYY-MM-DD', url)] from the list pages of /sj/<section>/."""
    out = []
    for i in range(pages):
        url = f"{WWW}/sj/{section}/" + ("" if i == 0 else f"index_{i}.html")
        try:
            page = _get_html(url)
        except NBSError:
            break
        for href, title in _re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, flags=_re.S):
            title = _re.sub(r"<[^>]+>", "", title).strip()
            m = _re.search(pattern, title)
            d = _re.search(r"t(\d{4})(\d{2})(\d{2})_", href)
            if m and d:
                out.append((int(m.group(1)), int(m.group(2)), f"{d.group(1)}-{d.group(2)}-{d.group(3)}",
                            urllib.parse.urljoin(url, href)))
        time.sleep(0.3)
    seen, uniq = set(), []
    for x in out:
        if (x[0], x[1]) not in seen:
            seen.add((x[0], x[1]))
            uniq.append(x)
    return uniq


_IMPACT = _re.compile(
    r"(?P<subj>[一-龥、和及]+?)(?:类)?价格(?:同比|环比)?(?:由[^，；。]*?转为)?(?P<dir>上涨|下降|持平)(?P<rate>\d+(?:\.\d+)?)?%?"
    r"[^；。]*?(?:合计)?(?:影响|上拉|下拉|拉动)(?:CPI|居民消费价格)?(?:（居民消费价格指数）)?(?:同比|环比)?"
    r"(?P<dir2>上涨|下降)?约(?P<pp>\d+\.\d+)个百分点")


def parse_impacts(text, source):
    """Impact statements in one release text: [{source, measure, key, name, rate, pp, text}].

    The pages carry the article twice (desktop and mobile layouts): statements are de-duplicated.
    "由上月上拉约a个百分点转为下拉约b个百分点" gives b (this month). "合计影响" statements cover several
    items together and are kept as one combined entry.
    """
    out, seen = [], set()
    measure = None
    for para in text.split("\n"):
        head = para[:40]
        if source == "interpretation" and ("PPI" in head or "工业生产者" in head):
            measure = None
        if para.startswith("一、") or "从同比看" in head:
            measure = "yoy"
        if para.startswith("二、") or "从环比看" in head:
            measure = "mom"
        if source == "release" and para.startswith("二、"):
            measure = "mom"
        if measure is None:
            continue
        for clause in _re.split(r"[；。]", para):
            for m in _IMPACT.finditer(clause):
                stmt = m.group(0)
                pps = _re.findall(r"(上拉|下拉|上涨|下降)?约(\d+\.\d+)个百分点", clause[m.start():])
                d2, ppv = pps[-1] if "转为" in clause[m.start("dir2") if m.group("dir2") else m.start("pp"):] and pps else (m.group("dir2"), m.group("pp"))
                neg = d2 in ("下降", "下拉") or (not d2 and m.group("dir") == "下降")
                pp = float(ppv) * (-1 if neg else 1)
                subj = m.group("subj").split("，")[-1]
                subj = _re.sub(r"^(其中|食品中|服务中|工业消费品中|其他|带动|国内|受[^，]*影响)", "", subj)
                subj = _re.sub(r"类$", "", subj)
                rate = m.group("rate")
                rate = None if rate is None else float(rate) * (-1 if m.group("dir") == "下降" else 1)
                if "合计" in stmt:
                    names = [_re.sub(r"^(国内|带动)", "", x) for x in _re.findall(r"([\u4e00-\u9fa5]+?)价格", stmt)]
                    key, name = "combined:" + "+".join(ZH_NAMES.get(x, ("zh:" + x,))[0] for x in names), "、".join(names)
                    rate = None
                else:
                    key, name = ZH_NAMES.get(subj, ZH_NAMES.get(subj + "类", ("zh:" + subj, subj)))
                meas = "mom" if "环比" in stmt else ("yoy" if "同比" in stmt else measure)
                k = (source, meas, key, pp)
                if k in seen:
                    continue
                seen.add(k)
                out.append({"source": source, "measure": meas, "key": key, "name": name, "rate": rate,
                            "pp": pp, "text": stmt[:160]})
    return out


def cpi_releases(since="2025-01", pages=40):
    """NBS CPI releases from `since`: [{month 'YYYY-MM', date, url, interp_url, impacts}]."""
    rel = release_links("zxfb", pages, r"(\d{4})年(\d{1,2})月份?居民消费价格")
    interp = {(y, m): u for y, m, _d, u in release_links("sjjd", pages, r"解读(\d{4})年(\d{1,2})月份?CPI和PPI数据")}
    out = []
    for y, m, d, u in rel:
        month = f"{y}-{m:02d}"
        if month < since:
            continue
        imp = parse_impacts(_text(_get_html(u)), "release")
        iu = interp.get((y, m))
        if iu:
            imp += parse_impacts(_text(_get_html(iu)), "interpretation")
        out.append({"month": month, "date": d, "url": u, "interp_url": iu, "impacts": imp})
        time.sleep(0.3)
    return sorted(out, key=lambda r: r["month"])
