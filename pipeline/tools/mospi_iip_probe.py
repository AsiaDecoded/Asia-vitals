"""Probe MoSPI's IIP and ASI APIs for India's Manufacturing tab. Raw responses under <out>/, summary.txt.
Usage: python -I pipeline/tools/mospi_iip_probe.py discovery/mospi_iip
"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.mospi.gov.in"
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)", "Accept": "application/json"}
CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/mospi_iip"
os.makedirs(OUT, exist_ok=True)
summary = []


def save(name, path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90, context=CTX) as r:
            status, body = r.status, r.read()
        try:
            res = json.loads(body)
        except ValueError:
            res = body.decode("utf-8", "replace")[:20000]
    except urllib.error.HTTPError as e:
        status, res = e.code, e.read().decode("utf-8", "replace")[:2000]
    except Exception as e:  # noqa: BLE001
        status, res = -1, repr(e)
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump({"url": url, "status": status, "response": res}, f, ensure_ascii=False, indent=1)
    n = ""
    if isinstance(res, dict):
        d, meta = res.get("data"), res.get("meta_data") or {}
        n = f"rows={len(d) if isinstance(d, list) else type(d).__name__} total={meta.get('totalRecords')} pages={meta.get('totalPages')}"
    summary.append(f"{status}\t{name}\t{n}\t{url}")
    time.sleep(0.6)


save("iip_base_years", "/api/iip/getIipBaseYear")
for by in ("2022-23", "2011-12", "2004-05"):
    for fr in ("Monthly", "Annually"):
        save(f"iip_filter_{by}_{fr}", "/api/iip/getIipFilter", base_year=by, frequency=fr)
for by in ("2022-23", "2011-12"):
    for t in ("General", "Sectoral", "Use-based category", "All"):
        save(f"iip_m_{by}_{t.replace(' ', '_')}_2026", "/api/iip/getIipData", base_year=by, frequency="Monthly", year="2026",
             type=t, limit="1000", page="1", Format="JSON")
        save(f"iip_a_{by}_{t.replace(' ', '_')}", "/api/iip/getIipData", base_year=by, frequency="Annually", type=t,
             limit="1000", page="1", Format="JSON")
    for path in ("/api/iip/getIIPMonthly", "/api/iip/getIIPAnnual"):
        save(f"iip_alt_{by}_{path.rsplit('/', 1)[1]}", path, base_year=by, type="All", limit="100", page="1", Format="JSON")
save("iip_m_2011-12_All_2012", "/api/iip/getIipData", base_year="2011-12", frequency="Monthly", year="2012", type="All",
     limit="1000", page="1", Format="JSON")
save("iip_m_2004-05_General", "/api/iip/getIipData", base_year="2004-05", frequency="Monthly", type="General",
     limit="1000", page="1", Format="JSON")

save("asi_classification_years", "/api/asi/getNicClassificationYear")
save("asi_filter", "/api/asi/getAsiFilter")
save("asi_filter_2008", "/api/asi/getAsiFilter", classification_year="2008")
save("asi_2digit_allindia", "/api/asi/getASIData", classification_year="2008", sector_code="Combined", state_code="99",
     nic_type="2-digit", limit="1000", page="1", Format="JSON")

with open(os.path.join(OUT, "summary.txt"), "w") as f:
    f.write("\n".join(summary) + "\n")
print("\n".join(summary))
