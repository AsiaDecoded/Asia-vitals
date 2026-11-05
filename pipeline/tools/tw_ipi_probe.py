"""Taiwan industrial production index: access probe (5 Nov 2026), from GitHub Actions.

  python -I pipeline/tools/tw_ipi_probe.py discovery/tw_ipi

data.gov.tw datasets from the Ministry of Economic Affairs (6607 工業生產, 95137 製造業生產量指數, 146531 電子零組件業,
16366, 16367): resource list via the data.gov.tw API, each file downloaded with its URL percent-encoded (the first probe
failed on the Chinese characters), plus the MOEA statistics pages. Saves files and summary.txt.
"""
import csv
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


for ds in ("6607", "95137", "146531", "16366", "16367"):
    try:
        d = json.loads(get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}"))
        res = (d.get("result") or {})
        say(f"== data.gov.tw {ds}: {res.get('title')} | {res.get('updateFrequency') or res.get('updateFreq')} | {len(res.get('distribution') or [])} files")
        (OUT / f"ds_{ds}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
        for i, r in enumerate((res.get("distribution") or [])[:6]):
            u = r.get("resourceDownloadUrl")
            say(f"   {r.get('resourceDescription')} | {r.get('resourceFormat')} | {u}")
            try:
                b = get(u)
                (OUT / f"ds_{ds}_{i}.{(r.get('resourceFormat') or 'bin').lower()}").write_bytes(b)
                txt = b.decode("utf-8-sig", "replace")
                rows = list(csv.reader(io.StringIO(txt)))
                say(f"     ok {len(b)} bytes, {len(rows)} rows; header {rows[0] if rows else ''}")
                for row in rows[1:4] + rows[-3:]:
                    say(f"       {row}")
                if rows and len(rows[0]) >= 3:
                    for j, h in enumerate(rows[0]):
                        vals = sorted({x[j] for x in rows[1:] if len(x) > j})
                        if len(vals) < 120:
                            say(f"     col {h}: {len(vals)} values, e.g. {vals[:60]}")
            except Exception as e:  # noqa: BLE001
                say(f"     failed {e}")
    except Exception as e:  # noqa: BLE001
        say(f"== data.gov.tw {ds} failed {e}")

for u in ("https://www.moea.gov.tw/MNS/dos/content/ContentDesc.aspx?menu_id=23004",
          "https://www.moea.gov.tw/Mns/dos/content/Content.aspx?menu_id=6730",
          "https://service.moea.gov.tw/EE520/opendata/"):
    try:
        b = get(u)
        (OUT / ("moea_" + str(abs(hash(u)))[:8] + ".html")).write_bytes(b)
        say(f"== {u}: ok {len(b)}")
    except Exception as e:  # noqa: BLE001
        say(f"== {u}: failed {e}")

(OUT / "summary.txt").write_text("\n".join(LOG))
