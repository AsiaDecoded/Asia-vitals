"""Probe RBI DBIE's gateway as the DBIE web app uses it: get a guest session token, then list the report catalogue
and look for capacity utilisation. Usage: python -I pipeline/tools/rbi_dbie_probe.py discovery/rbi_dbie
"""
import json
import os
import sys
import urllib.error
import urllib.request

OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/rbi_dbie"
os.makedirs(OUT, exist_ok=True)
BASE = "https://data.rbi.org.in/CIMS_Gateway_DBIE/GATEWAY/SERVICES"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
log = []


def post(name, svc, body, key, token=None):
    h = {"Content-Type": "application/json", "channelkey": key, "datatype": "application/json", "User-Agent": UA,
         "Origin": "https://data.rbi.org.in", "Referer": "https://data.rbi.org.in/DBIE/"}
    if token:
        h["authorization"] = token
    req = urllib.request.Request(f"{BASE}/{svc}", data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            st, hd, b = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        st, hd, b = e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa: BLE001
        log.append(f"FAIL {name} {e!r}"); return None, {}, b""
    open(os.path.join(OUT, name + ".txt"), "wb").write(b)
    open(os.path.join(OUT, name + ".headers.json"), "w").write(json.dumps(hd, indent=1))
    log.append(f"{st} {name} {len(b)} bytes | {b[:200]!r}")
    return st, hd, b


st, hd, b = post("session", "security_generateSessionToken", {"body": {}}, "key1")
token = None
for k, v in hd.items():
    if k.lower() in ("authorization", "token", "sessionid", "x-auth-token"):
        token = v
if not token and b:
    try:
        j = json.loads(b)
        token = (j.get("body") or {}).get("token") or j.get("token") or (j.get("header") or {}).get("token")
        if not token:
            log.append(f"session json keys: {list(j)} body keys: {list((j.get('body') or {}) if isinstance(j.get('body'), dict) else [])}")
    except Exception as e:  # noqa: BLE001
        log.append(f"session not json: {e!r}")
log.append(f"token found: {bool(token)}")
if token:
    post("all_reports", "dbie_getAllDBIEReports", {"body": {}}, "key2", token)
    post("popular", "dbie_GetPopularReportsPortalNew", {"body": {"portal": "DBIE"}}, "key2", token)
    post("eco_header", "dbie_getEcoHeader", {"body": {}}, "key2", token)
open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
