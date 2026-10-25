"""Minimal client for the Bank of Japan Time-Series Data Search API (no key needed).

Manual: https://www.stat-search.boj.or.jp/info/api_manual_en.pdf
Limits: 250 series per request, 60,000 data points per request; space requests out.
"""
import json
import time
import urllib.parse
import urllib.request

API = "https://www.stat-search.boj.or.jp/api/v1"
HEADERS = {"User-Agent": "asia-vitals/1.0 (+https://github.com/AsiaDecoded/asia-vitals)", "Accept-Encoding": "identity"}


def _call(method, params, retries=3):
    url = f"{API}/{method}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180) as r:
                body = json.loads(r.read().decode("utf-8"))
            status = body.get("STATUS")
            if status not in (200, "200"):
                raise RuntimeError(f"BoJ API {method} status {status}: {body.get('MESSAGE')}")
            return body
        except Exception:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(15 * (attempt + 1))


def metadata(db, lang="EN"):
    return _call("getMetadata", {"db": db, "lang": lang, "format": "json"})


def series(db, codes, start=None, end=None, lang="EN"):
    """Return the RESULTSET list for the given series codes, following NEXTPOSITION paging."""
    out, pos = [], None
    while True:
        params = {"db": db, "code": ",".join(codes), "lang": lang, "format": "json"}
        if start:
            params["startDate"] = start
        if end:
            params["endDate"] = end
        if pos:
            params["startPosition"] = pos
        body = _call("getDataCode", params)
        out.extend(body.get("RESULTSET") or [])
        pos = body.get("NEXTPOSITION")
        if not pos:
            break
        time.sleep(2)
    return out
