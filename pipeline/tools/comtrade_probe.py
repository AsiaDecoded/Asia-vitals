"""UN Comtrade survey probe (10 Nov 2026): what Comtrade holds for one reporter, monthly and annual, with a comparison
sample (totals, the dump's partners and HS lines). Writes to discovery/comtrade/<iso>/; nothing goes into data/.

  COMTRADE_KEY=... python -I pipeline/tools/comtrade_probe.py CN discovery/comtrade/cn
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

M49 = {"CN": 156, "WLD": 0, "US": 842, "HK": 344, "JP": 392, "KR": 410, "TW": 490, "IN": 699, "ID": 360, "MY": 458,
       "PH": 608, "SG": 702, "TH": 764, "VN": 704, "EU": 97}
CMDS = "TOTAL,85,8419,8470,8471,8472,8473,2709,2710"
ISO = sys.argv[1] if len(sys.argv) > 1 else "CN"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else f"discovery/comtrade/{ISO.lower()}")
OUT.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("COMTRADE_KEY", "").strip()
BASE = "https://comtradeapi.un.org/data/v1/"
LOG = []


def get(name, path, **params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    t = time.time()
    for i in range(4):
        try:
            rq = urllib.request.Request(url, headers={"Ocp-Apim-Subscription-Key": KEY, "User-Agent": "asia-vitals survey"})
            with urllib.request.urlopen(rq, timeout=180) as r:
                b, st = r.read(), r.status
            break
        except urllib.error.HTTPError as e:
            b, st = e.read(), e.code
            if st != 429:
                break
        except Exception as e:  # noqa: BLE001
            b, st = repr(e).encode(), -1
        time.sleep(10 * (i + 1))
    (OUT / f"{name}.json").write_bytes(b)
    try:
        js = json.loads(b)
    except Exception:  # noqa: BLE001
        js = None
    n = len(js.get("data") or []) if isinstance(js, dict) else None
    LOG.append({"name": name, "path": path, "params": params, "status": st, "bytes": len(b), "rows": n,
                "secs": round(time.time() - t, 1), "error": (js or {}).get("error") if isinstance(js, dict) else b[:200].decode("utf-8", "replace")})
    time.sleep(1.5)
    return js


rep = M49[ISO]
LOG.append({"key_present": bool(KEY), "key_len": len(KEY)})
# what exists
for freq in ("A", "M"):
    get(f"da_{freq}", f"getDA/C/{freq}/HS", reporterCode=rep)
# annual sample: all years in one call per flow
partners = ",".join(str(v) for k, v in M49.items() if k != ISO)
for y0 in range(1992, 2026, 12):
    years = ",".join(str(y) for y in range(y0, min(y0 + 12, 2026)))
    get(f"A_{y0}", "get/C/A/HS", reporterCode=rep, period=years, partnerCode=partners, cmdCode=CMDS,
        flowCode="X,M", partner2Code=0, customsCode="C00", motCode=0, includeDesc="true")
# monthly sample: 12 periods per call
for y in ([] if os.environ.get("ANNUAL_ONLY") else range(2000, 2027)):
    per = ",".join(f"{y}{m:02d}" for m in range(1, 13))
    get(f"M_{y}", "get/C/M/HS", reporterCode=rep, period=per, partnerCode=partners, cmdCode=CMDS, flowCode="X,M",
        partner2Code=0, customsCode="C00", motCode=0, includeDesc="true")
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
print(json.dumps(LOG[:4], indent=1))
