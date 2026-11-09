"""Trade probe round 8 (9 Nov 2026): Philippines OpenSTAT query shapes and Malaysia METS classification queries.

  python -I pipeline/tools/trade_probe8.py discovery/trade8
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade8")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LOG = []
PX = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2L/IMT/"
METS = "https://metsonline.dosm.gov.my/api/"


def call(name, url, body=None, cap=2_000_000):
    t = time.time()
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=120) as r:
            b = r.read()
            st = r.status
    except urllib.error.HTTPError as e:
        b, st = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        b, st = repr(e).encode(), -1
    (OUT / f"{name}.json").write_bytes(b[:cap])
    LOG.append({"name": name, "url": url, "body": body, "status": st, "bytes": len(b), "secs": round(time.time() - t, 1),
                "head": b[:300].decode("utf-8", "replace")})
    try:
        return json.loads(b)
    except Exception:  # noqa: BLE001
        return None


q = {"tradeClass": "classification", "hsType": "HS2_digit", "flowTypes": ["Exports"], "frequencyType": "MONTHLY",
     "years": ["2026"], "months": ["07", "08"], "products": [{"codeValue": "85", "codeName": ""}]}
V = {
    "pc_str": dict(q, partnerCountry=["CHINA", "SINGAPORE", "UNITED STATES"]),
    "pc_obj": dict(q, partnerCountry=[{"codeValue": "CHINA", "codeName": "CHINA"}, {"codeValue": "SINGAPORE", "codeName": "SINGAPORE"}]),
    "pc_str_grp": dict(q, partnerCountry=["CHINA", "SINGAPORE"], PGEGrouping="PARTNERCOUNTRY"),
    "pc_eu": dict(q, partnerCountry=["EU"], PGEGrouping="ECONOMICGROUPING"),
    "pc_eu2": dict(q, economicGrouping=["EU"]),
    "allprod_pc": dict(q, products=[], partnerCountry=["CHINA", "SINGAPORE"]),
}
for k, b in V.items():
    call(f"my_{k}", METS + "Trade/classification-query", b)
call("my_region_q", METS + "Trade/region-query", {"frequencyType": "MONTHLY", "flowTypes": ["Exports"], "years": ["2026"],
     "months": ["07", "08"], "partnerCountry": ["CHINA", "SINGAPORE"]})
call("my_partners", METS + "Trade/get-advanced-search-list/PartnerCountry")
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
