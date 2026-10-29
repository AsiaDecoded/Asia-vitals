"""Client for the Philippine Statistics Authority's OpenSTAT (PXWeb API v1, no key).

Tables are addressed by their folder path, e.g. "2M/PI/CPI/2018NEW/0012M4ACP22.px".
meta(path) returns the table's variables; get(path, select) returns tidy rows:
[{<variable code>: <value text>, ..., "value": float or None}], from PXWeb's json response.
select maps a variable code to a list of value texts, or to a function text -> bool;
variables not named are fetched in full. OpenSTAT allows up to 100,000 cells per query.
"""
import json
import time
import urllib.error
import urllib.request

BASE = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_CELLS = 100_000


def _request(url, body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {**HEADERS, **({"Content-Type": "application/json"} if data else {})}
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=90) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"OpenSTAT {e.code} for {url}: {e.read()[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"OpenSTAT failed for {url}: {last!r}")


def meta(path):
    time.sleep(0.5)
    return _request(f"{BASE}/{path}")


def get(path, select=None, m=None):
    """Tidy rows for the selection; splits the query along the largest variable if over the cell limit."""
    m = m or meta(path)
    select = select or {}
    chosen = {}
    for v in m["variables"]:
        want = select.get(v["code"])
        pairs = list(zip(v["values"], v["valueTexts"]))
        if want is None:
            keep = pairs
        elif callable(want):
            keep = [p for p in pairs if want(p[1])]
        else:
            want = list(want)
            keep = [p for p in pairs if p[1] in want or p[1].strip(". ") in want]
        if not keep:
            raise RuntimeError(f"{path}: nothing selected for {v['code']}")
        chosen[v["code"]] = keep
    return _fetch(path, chosen, m)


def _fetch(path, chosen, m):
    cells = 1
    for keep in chosen.values():
        cells *= len(keep)
    if cells > MAX_CELLS:
        big = max(chosen, key=lambda k: len(chosen[k]))
        keep = chosen[big]
        half = len(keep) // 2
        return (_fetch(path, {**chosen, big: keep[:half]}, m) +
                _fetch(path, {**chosen, big: keep[half:]}, m))
    body = {"query": [{"code": k, "selection": {"filter": "item", "values": [c for c, _ in keep]}}
                      for k, keep in chosen.items()],
            "response": {"format": "json"}}
    time.sleep(0.5)
    js = _request(f"{BASE}/{path}", body)
    if LAST is not None:
        LAST.append(js)
    return tidy_json(js, m)


LAST = None  # set to a list to keep raw responses (discovery)


def tidy_json(js, m):
    """PXWeb's native json: columns (dimensions 'd'/'t', then content 'c') and data [{key, values}]."""
    texts = {v["code"]: dict(zip(v["values"], v["valueTexts"])) for v in m["variables"]}
    cols = js["columns"]
    dims = [c["code"] for c in cols if c.get("type") in ("d", "t")]
    rows = []
    for rec in js["data"]:
        r = {d: texts.get(d, {}).get(k, k) for d, k in zip(dims, rec["key"])}
        v = rec["values"][0]
        try:
            r["value"] = float(v)
        except (TypeError, ValueError):
            r["value"] = None
        rows.append(r)
    return rows


def tidy(js):
    ids, sizes = js["id"], js["size"]
    labels = []
    for d in ids:
        cat = js["dimension"][d]["category"]
        idx = cat["index"]
        order = sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)
        labels.append([cat.get("label", {}).get(c, c) for c in order])
    vals = js["value"]
    if isinstance(vals, dict):  # sparse form
        dense = [None] * eval_size(sizes)
        for k, v in vals.items():
            dense[int(k)] = v
        vals = dense
    rows = []
    for n, v in enumerate(vals):
        rem, pos = n, []
        for s in reversed(sizes):
            pos.append(rem % s)
            rem //= s
        pos.reverse()
        r = {d: labels[i][pos[i]] for i, d in enumerate(ids)}
        r["value"] = None if v is None else float(v)
        rows.append(r)
    return rows


def eval_size(sizes):
    n = 1
    for s in sizes:
        n *= s
    return n
