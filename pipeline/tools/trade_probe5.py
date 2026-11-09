"""Trade probe round 5 (9 Nov 2026): follow-ups on round 1: tests national trade endpoints for the 12 economies from GitHub Actions.

  python -I pipeline/tools/trade_probe5.py discovery/trade5

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
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade5")
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




B = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2L/IMT/"
for f in ("SUM", "PCG", "PMG", "AVE"):
    test(f"ph_{f}", B + f)
M = "https://metsonline.dosm.gov.my/api/"
H = {"Content-Type": "application/json", "Accept": "application/json", "Referer": "https://metsonline.dosm.gov.my/",
     "Origin": "https://metsonline.dosm.gov.my"}
test("my_codes_hs2", M + "Trade/get-type-by-codes/HS2_digit", headers=H)
test("my_totalby", M + "Trade/get-total-by-values", headers=H)
variants = {
  "a": {"hsType": "HS2_digit", "products": [{"codeValue": "85", "codeName": "85"}], "flowTypes": ["EXPORT"], "frequencyType": "Monthly",
        "months": [7], "years": [2026], "quarters": [], "PGEGrouping": "PARTNER", "partnerCountry": [], "pagination": {"offset": 0, "limit": 150},
        "advancedSearch": {"enabled": False}, "isEmbargo": False, "isDataChecking": False},
  "b": {"hsType": "HS2_digit", "products": ["85"], "flowTypes": ["Export"], "frequencyType": "MONTHLY", "months": ["7"], "years": ["2026"],
        "quarters": [], "PGEGrouping": "Partner", "partnerCountry": ["UNITED STATES"], "pagination": {"offset": 0, "limit": 150},
        "advancedSearch": {"enabled": True, "advancedSearchType": "Partner", "values": ["UNITED STATES"]}, "isEmbargo": False, "isDataChecking": False},
}
for k, body in variants.items():
    b = test(f"my_cq_{k}", M + "Trade/classification-query", data=json.dumps(body).encode(), headers=H)
    if b is None:
        try:
            req = urllib.request.Request(M + "Trade/classification-query", data=json.dumps(body).encode(), headers={**H, "User-Agent": UA})
            urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            LOG.append(f"     my_cq_{k} error body: {e.read()[:600]!r}")
        except Exception as e:  # noqa: BLE001
            LOG.append(f"     my_cq_{k}: {e}")
(OUT / "summary.txt").write_text("\n".join(LOG))
print("\n".join(LOG))
