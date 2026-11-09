"""Trade probe round 6 (9 Nov 2026): Philippines OpenSTAT query shapes and Malaysia METS classification queries.

  python -I pipeline/tools/trade_probe6.py discovery/trade6
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade6")
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


# --- Philippines ---
for folder in ("SUM", "PCG", "PMG", "AVE", "AVI", "SAV"):
    lst = call(f"ph_list_{folder}", PX + folder + "/") or []
    for t in lst[:6]:
        if t.get("type") == "t":
            m = call(f"ph_meta_{folder}_{t['id']}", PX + folder + "/" + t["id"])
            if m:
                small = {"title": m.get("title"), "variables": [{"code": v["code"], "n": len(v.get("values", [])),
                         "values": v.get("values", [])[:40], "texts": v.get("valueTexts", [])[:40], "elim": v.get("elimination")}
                         for v in m.get("variables", [])]}
                (OUT / f"ph_meta_{folder}_{t['id']}.small.json").write_text(json.dumps(small, indent=1))
fob = PX + "FOB/0012L4DXVD5.px"
cif_list = call("ph_list_CIF", PX + "CIF/") or []
months = {"code": "Period", "selection": {"filter": "all", "values": ["*"]}}
allc = {"code": "Commodity Code", "selection": {"filter": "all", "values": ["*"]}}
# country eliminated (omitted) with all commodities
call("ph_q_allcom_nocountry", fob, {"query": [allc, months], "response": {"format": "json-stat2"}})
# commodity omitted, all countries
call("ph_q_nocom_allcountry", fob, {"query": [{"code": "Country", "selection": {"filter": "all", "values": ["*"]}}, months],
                                    "response": {"format": "json-stat2"}})
# 200 commodities x all countries x all months (cell-limit test)
call("ph_q_200com_allcountry", fob, {"query": [{"code": "Commodity Code", "selection": {"filter": "item", "values": [str(i) for i in range(200)]}},
                                     {"code": "Country", "selection": {"filter": "all", "values": ["*"]}}, months],
                                     "response": {"format": "json-stat2"}})
call("ph_q_50com_allcountry", fob, {"query": [{"code": "Commodity Code", "selection": {"filter": "item", "values": [str(i) for i in range(50)]}},
                                    {"code": "Country", "selection": {"filter": "all", "values": ["*"]}}, months],
                                    "response": {"format": "json-stat2"}})
# old year table, one country, all commodities
fl = call("ph_list_FOB", PX + "FOB/") or []
for t in fl:
    if "1995" in t.get("text", "") or "2005" in t.get("text", ""):
        call(f"ph_q_old_{t['id']}", PX + "FOB/" + t["id"], {"query": [allc, {"code": "Country", "selection": {"filter": "item", "values": ["860"]}}, months],
                                                          "response": {"format": "json-stat2"}})

# --- Malaysia METS ---
call("my_hstypes", METS + "Trade/get-all-hstypes")
call("my_partners", METS + "Trade/get-advanced-search-list/PartnerCountry")
for name, hs, prods in (("my_hs2_85", "HS2_digit", [{"codeValue": "85", "codeName": ""}]),
                        ("my_hs4_2709", "HS4_digit", [{"codeValue": "2709", "codeName": ""}, {"codeValue": "2710", "codeName": ""}])):
    for flow in ("Exports", "Imports"):
        call(f"{name}_{flow}", METS + "Trade/classification-query",
             {"tradeClass": "classification", "hsType": hs, "flowTypes": [flow], "frequencyType": "MONTHLY",
              "years": ["2025", "2026"], "months": [f"{m:02d}" for m in range(1, 13)], "products": prods,
              "PGEGrouping": "PARTNERCOUNTRY", "partnerCountries": [], "isAllPartner": True})
call("my_partner_total", METS + "Trade/classification-query",
     {"tradeClass": "classification", "hsType": "HS2_digit", "flowTypes": ["Exports"], "frequencyType": "MONTHLY",
      "years": ["2026"], "months": ["01", "02"], "products": [], "isAllProduct": True, "PGEGrouping": "PARTNERCOUNTRY",
      "partnerCountries": [], "isAllPartner": True})
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
