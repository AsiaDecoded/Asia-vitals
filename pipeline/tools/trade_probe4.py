"""Trade probe round 4 (9 Nov 2026): follow-ups on round 1: tests national trade endpoints for the 12 economies from GitHub Actions.

  python -I pipeline/tools/trade_probe4.py discovery/trade4

Each test: GET (or POST) a URL, record status, size, content type and the first bytes; save the body (capped).
Keys come from the environment (BPS_KEY, ECOS_KEY, ESTAT_APP_ID) and are never written out.
"""
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade4")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KEYS = {k: os.environ.get(k, "") for k in ("BPS_KEY", "ECOS_KEY", "ESTAT_APP_ID")}
LOG = []


def enc(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path, safe="/%:@()"),
                                    urllib.parse.quote(p.query, safe="=&%,:+/"), ""))


def hide(s):
    for v in KEYS.values():
        if v:
            s = s.replace(v, "<key>")
    return s


def test(name, url, data=None, headers=None, opener=None, cap=3_000_000):
    for k, v in KEYS.items():
        url = url.replace("{" + k + "}", v)
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    t0 = time.time()
    try:
        req = urllib.request.Request(enc(url), data=data, headers=h)
        with (opener or urllib.request.build_opener()).open(req, timeout=90) as r:
            b = r.read(cap)
            ct = r.headers.get("Content-Type", "")
            st = r.status
    except Exception as e:  # noqa: BLE001
        LOG.append(f"FAIL {name}: {hide(str(e))[:200]} ({time.time() - t0:.0f}s) {hide(url)[:160]}")
        return None
    ext = "json" if "json" in ct else "html" if "html" in ct else "xlsx" if "sheet" in ct else "pdf" if "pdf" in ct else "csv" if "csv" in ct else "bin"
    (OUT / f"{name}.{ext}").write_bytes(b)
    head = re.sub(r"\s+", " ", b[:300].decode("utf-8", "replace"))
    LOG.append(f"OK   {name}: {st} {len(b)} bytes {ct[:40]} ({time.time() - t0:.0f}s) | {hide(head)[:220]}")
    return b




B = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/"
for n, u in [("ph_db", ""), ("ph_2L", "2L"), ("ph_imt", "2L/IMT")]:
    test(n, B + u)
P = B + "2L/IMT/FOB/0012L4DXVD5.px"
m = json.loads(test("ph_meta", P) or b"{}")
cv = [v for v in m.get("variables", []) if v["code"] == "Country"][0]["values"] if m else []
def q(com, country, period):
    return json.dumps({"query": [{"code": "Commodity Code", "selection": com}, {"code": "Country", "selection": country},
                                 {"code": "Period", "selection": period}], "response": {"format": "json-stat2"}}).encode()
H = {"Content-Type": "application/json"}
test("ph_q_2digit", P, data=q({"filter": "all", "values": ["??"]}, {"filter": "all", "values": ["*"]}, {"filter": "all", "values": ["*"]}), headers=H)
test("ph_q_all_onecountry", P, data=q({"filter": "all", "values": ["*"]}, {"filter": "item", "values": cv[:1]}, {"filter": "all", "values": ["*"]}), headers=H)
test("ph_q_85_world", P, data=json.dumps({"query": [{"code": "Commodity Code", "selection": {"filter": "all", "values": ["85*"]}},
                                                    {"code": "Period", "selection": {"filter": "all", "values": ["*"]}}],
                                          "response": {"format": "json-stat2"}}).encode(), headers=H)
test("ph_q_noncommodity", P, data=json.dumps({"query": [{"code": "Country", "selection": {"filter": "all", "values": ["*"]}},
                                                       {"code": "Period", "selection": {"filter": "all", "values": ["*"]}}],
                                             "response": {"format": "json-stat2"}}).encode(), headers=H)
(OUT / "summary.txt").write_text("\n".join(LOG))
print("\n".join(LOG))
