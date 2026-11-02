"""Probe MoSPI's NAS API (national accounts) and the World Bank WDI for India's GDP page.

Saves raw responses under <out>/ (one JSON file per query) and a summary.txt.
Usage: python -I pipeline/tools/mospi_nas_probe.py discovery/mospi_nas
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
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "application/json"}
CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)

OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/mospi_nas"
os.makedirs(OUT, exist_ok=True)
summary = []


def get(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
            body = r.read()
        try:
            return r.status, json.loads(body)
        except ValueError:
            return r.status, body.decode("utf-8", "replace")[:20000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:2000]
    except Exception as e:  # noqa: BLE001
        return -1, repr(e)


def save(name, url):
    status, res = get(url)
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump({"url": url, "status": status, "response": res}, f, ensure_ascii=False, indent=1)
    n = ""
    if isinstance(res, dict):
        d = res.get("data")
        meta = res.get("meta_data") or {}
        n = f"rows={len(d) if isinstance(d, list) else type(d).__name__} total={meta.get('totalRecords')} pages={meta.get('totalPages')}"
    elif isinstance(res, list):
        n = f"list len={len(res)}"
    summary.append(f"{status}\t{name}\t{n}\t{url}")
    time.sleep(0.6)
    return res


def mospi(name, path, **params):
    return save(name, BASE + path + ("?" + urllib.parse.urlencode(params) if params else ""))


# Indicator lists and filters
for acc in (1, 2):
    mospi(f"nas_indicators_acc{acc}", "/api/nas/getNasIndicatorList", account_code=acc)

for by, series in (("2022-23", "Current"), ("2011-12", "Current"), ("2011-12", "Back")):
    for freq in (1, 2):
        for ind in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
            mospi(f"nas_filter_{by}_{series}_f{freq}_i{ind}", "/api/nas/getNasFilterByIndicatorId",
                  base_year=by, series=series, frequency_code=freq, indicator_code=ind, account_code=1)

# Data: first page of each indicator, both bases, annual and quarterly
for by, series in (("2022-23", "Current"), ("2011-12", "Current"), ("2011-12", "Back")):
    for freq in ("Annually", "Quarterly"):
        for ind in range(1, 23):
            mospi(f"nas_data_{by}_{series}_{freq}_i{ind}", "/api/nas/getNASData",
                  base_year=by, series=series, frequency_code=freq, indicator_code=ind,
                  Format="JSON", limit="100", page="1")

# World Bank WDI, India
WDI = ["NY.GDP.MKTP.CD", "NY.GDP.MKTP.KD", "NY.GDP.MKTP.KD.ZG", "NY.GDP.PCAP.CD", "NY.GDP.PCAP.KD",
       "NY.GNP.ATLS.CD", "NY.GNP.PCAP.CD", "NV.IND.MANF.KD.ZG", "NV.AGR.TOTL.KD.ZG",
       "NV.IND.TOTL.KD.ZG", "NV.SRV.TOTL.KD.ZG"]
for s in WDI:
    save("wdi_" + s, f"https://api.worldbank.org/v2/country/IND/indicator/{s}?format=json&per_page=200")
save("wdi_country_IND", "https://api.worldbank.org/v2/country/IND?format=json")

with open(os.path.join(OUT, "summary.txt"), "w") as f:
    f.write("\n".join(summary) + "\n")
print("\n".join(summary))
