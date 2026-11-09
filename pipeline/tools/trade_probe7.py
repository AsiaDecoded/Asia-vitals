"""Trade probe round 7 (9 Nov 2026): Philippines OpenSTAT query shapes and Malaysia METS classification queries.

  python -I pipeline/tools/trade_probe7.py discovery/trade7
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade7")
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


# --- Philippines: formats ---
fob = PX + "FOB/0012L4DXVD5.px"
months = {"code": "Period", "selection": {"filter": "all", "values": ["*"]}}
small = [{"code": "Commodity Code", "selection": {"filter": "item", "values": [str(i) for i in range(3000, 3010)]}},
         {"code": "Country", "selection": {"filter": "item", "values": ["860", "164"]}}, months]
for fmt in ("json-stat2", "json-stat", "json", "csv", "xlsx"):
    call(f"ph_fmt_{fmt}", fob, {"query": small, "response": {"format": fmt}})
call("ph_fmt_json_all1country", fob, {"query": [{"code": "Commodity Code", "selection": {"filter": "all", "values": ["*"]}},
     {"code": "Country", "selection": {"filter": "item", "values": ["860"]}}, months], "response": {"format": "json"}})
call("ph_fmt_csv_all1country", fob, {"query": [{"code": "Commodity Code", "selection": {"filter": "all", "values": ["*"]}},
     {"code": "Country", "selection": {"filter": "item", "values": ["860"]}}, months], "response": {"format": "csv"}})
call("ph_fmt_csv_all40country", fob, {"query": [{"code": "Commodity Code", "selection": {"filter": "all", "values": ["*"]}},
     {"code": "Country", "selection": {"filter": "item", "values": ["860", "164", "168", "392", "410", "344", "702", "458", "764", "704", "360", "699", "276", "528"]}},
     months], "response": {"format": "csv"}})
for tid in ("0012L4DFTS0.px", "0012L4DFTS1.px"):
    for fmt in ("json-stat2", "csv"):
        call(f"ph_sum_{tid[:-3]}_{fmt}", PX + "SUM/" + tid, {"query": [], "response": {"format": fmt}})
# --- Malaysia METS: partner dimension ---
q = {"tradeClass": "classification", "hsType": "HS2_digit", "flowTypes": ["Exports"], "frequencyType": "MONTHLY",
     "years": ["2026"], "months": ["08"], "products": [{"codeValue": "85", "codeName": ""}]}
variants = {
    "pc_list": dict(q, PGEGrouping="PARTNERCOUNTRY", partnerCountries=["CHINA", "SINGAPORE"], isAllPartner=False),
    "pc_objs": dict(q, PGEGrouping="PARTNERCOUNTRY", partnerCountries=[{"codeValue": "CHINA", "codeName": "CHINA"}], isAllPartner=False),
    "pge_list": dict(q, PGEGrouping="PARTNERCOUNTRY", PGE=["CHINA", "SINGAPORE"]),
    "pge_values": dict(q, PGEGrouping="PARTNERCOUNTRY", pgeValues=["CHINA", "SINGAPORE"]),
    "country_all": dict(q, PGEGrouping="PARTNERCOUNTRY", isAllPGE=True),
    "region": dict(q, PGEGrouping="REGION", isAllPGE=True),
}
for k, b in variants.items():
    call(f"my_q_{k}", METS + "Trade/classification-query", b)
for path in ("", "Trade/get-advanced-search-list/Region", "Trade/get-advanced-search-list/EconomicGrouping",
             "Trade/get-advanced-search-list/Port"):
    call("my_get_" + (path.replace("/", "_") or "root"), METS + path)
try:
    h = urllib.request.urlopen(urllib.request.Request("https://metsonline.dosm.gov.my/", headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
    (OUT / "my_index.html").write_text(h)
    import re
    for i, js in enumerate(re.findall(r'src="([^"]+\.js)"', h)[:12]):
        u = js if js.startswith("http") else "https://metsonline.dosm.gov.my/" + js.lstrip("/")
        try:
            t = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
            hits = [t[max(0, m.start() - 600): m.start() + 900] for m in re.finditer(r"classification-query|PGEGrouping|partnerCountr", t)][:12]
            (OUT / f"my_js_{i}.txt").write_text(u + "\n\n" + "\n=====\n".join(hits))
        except Exception as e:  # noqa: BLE001
            LOG.append({"name": f"js{i}", "url": u, "err": repr(e)})
except Exception as e:  # noqa: BLE001
    LOG.append({"name": "my_index", "err": repr(e)})
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
