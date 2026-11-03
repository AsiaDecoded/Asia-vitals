"""Probe MoSPI's IIP API (api.mospi.gov.in/api/iip/...) for India's Manufacturing tab: base years, filters, and the
first pages of monthly General and Sectoral data on each base. Saves raw responses under <out>/ and a summary.txt.
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
            body = r.read(); status = r.status
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
        d = res.get("data"); m = res.get("meta_data") or {}
        n = f"rows={len(d) if isinstance(d, list) else type(d).__name__} total={m.get('totalRecords')} pages={m.get('totalPages')} msg={str(res.get('msg'))[:60]}"
    summary.append(f"{status}\t{name}\t{n}\t{url}")
    time.sleep(0.6)
    return res


save("base_years", "/api/iip/getIipBaseYear")
BASES = ["2022-23", "2011-12", "2004-05", "1993-94"]
for by in BASES:
    for fr in ("Monthly", "Annually"):
        save(f"filter_{by}_{fr}", "/api/iip/getIipFilter", base_year=by, frequency=fr)
for by in BASES:
    for typ in ("General", "Sectoral"):
        for yr in ("2012", "2013", "2022", "2023", "2025", "2026", "1995", "2006"):
            save(f"data_{by}_{typ}_{yr}", "/api/iip/getIipData", base_year=by, frequency="Monthly", type=typ, year=yr,
                 limit="100", page="1", Format="JSON")
        save(f"data_{by}_{typ}_all_p1", "/api/iip/getIipData", base_year=by, frequency="Monthly", type=typ,
             limit="100", page="1", Format="JSON")
        save(f"data_{by}_{typ}_annual", "/api/iip/getIipData", base_year=by, frequency="Annually", type=typ,
             limit="100", page="1", Format="JSON")
# 2-digit manufacturing (NIC divisions) on the new base, one year
save("data_2022-23_All_2026", "/api/iip/getIipData", base_year="2022-23", frequency="Monthly", type="All", year="2026",
     limit="100", page="1", Format="JSON")
with open(os.path.join(OUT, "summary.txt"), "w") as f:
    f.write("\n".join(summary) + "\n")
print("\n".join(summary))
