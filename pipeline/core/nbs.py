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


def _call(path, params=None, body=None, tries=4, timeout=120):
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
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
            time.sleep(4 * (i + 1))
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
