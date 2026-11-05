"""Taiwan industrial production index: access probe (5 Nov 2026), from GitHub Actions.

  python -I pipeline/tools/tw_ipi_probe.py discovery/tw_ipi

data.gov.tw datasets from the Ministry of Economic Affairs (6607 工業生產, 95137 製造業生產量指數, 146531 電子零組件業,
16366, 16367): resource list via the data.gov.tw API, each file downloaded with its URL percent-encoded (the first probe
failed on the Chinese characters), plus the MOEA statistics pages. Saves files and summary.txt.
"""
import csv
import re
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/tw_ipi")
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def enc(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), urllib.parse.quote(p.query, safe="=&"), ""))


def get(u, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(enc(u), headers=UA), timeout=timeout) as r:
        return r.read()


import ssl
sys.path.insert(0, "pipeline")
from core import dgbas  # noqa: E402

for u in ("https://www.stat.gov.tw/cp.aspx?n=2711", "https://www.stat.gov.tw/cp.aspx?n=2674", "https://www.stat.gov.tw/Point.aspx?sid=t.1&n=3581&sms=11480"):
    try:
        b = dgbas.get(u)
        t = b.decode("utf-8", "replace")
        (OUT / ("page_" + re.sub(r"\W", "_", u[-20:]) + ".html")).write_text(t)
        links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|ods|csv)[^"]*)"', t)))
        say(f"== {u}: ok {len(b)}; {len(links)} file links")
        for l in links[:80]:
            say("   ", urllib.parse.unquote(l))
    except Exception as e:  # noqa: BLE001
        say(f"== {u}: failed {e}")

(OUT / "summary.txt").write_text("\n".join(LOG))
