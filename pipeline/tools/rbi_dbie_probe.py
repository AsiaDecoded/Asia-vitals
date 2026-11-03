"""Probe RBI DBIE (dbie.rbihub.in, data.rbi.org.in) reachability from Actions: status, content type, first bytes, and
whether a bot challenge is served. Usage: python -I pipeline/tools/rbi_dbie_probe.py discovery/rbi_dbie
"""
import os
import sys
import urllib.error
import urllib.request

OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/rbi_dbie"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
      "Accept": "*/*"}
URLS = {
    "dbie_home": "https://dbie.rbihub.in/",
    "dbie_app": "https://dbie.rbihub.in/DBIE/dbie.rbi?site=home",
    "dbie_api_cat": "https://dbie.rbihub.in/DBIE/api/catalogue",
    "data_rbi_home": "https://data.rbi.org.in/",
    "data_rbi_dbie": "https://data.rbi.org.in/DBIE/",
    "rbi_home": "https://www.rbi.org.in/",
    "rbidocs_obicus": "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/OBICUS07102026FL8CF879A4B9AD4C3A8017451D7A83D8F6.PDF",
}
log = []
for k, u in URLS.items():
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
            b = r.read(); st = r.status; ct = r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        b = e.read(); st = e.code; ct = e.headers.get("Content-Type")
    except Exception as e:  # noqa: BLE001
        log.append(f"FAIL {k} {e!r}"); continue
    open(os.path.join(OUT, k + ".bin"), "wb").write(b[:200000])
    txt = b[:3000].decode("utf-8", "replace")
    challenge = "TSPD" in txt or "bobcmn" in txt or "captcha" in txt.lower()
    log.append(f"{st} {k} {ct} {len(b)} bytes challenge={challenge} | {txt[:120]!r}")
open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
