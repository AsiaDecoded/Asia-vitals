"""Probe: daily history for the SET (Thailand) and PSEi (Philippines) from sites other than Yahoo Finance.
Writes discovery/eq_probe/report.txt and the first bytes of each response."""
import json, urllib.request, urllib.error, ssl, time
from pathlib import Path

OUT = Path("discovery/eq_probe"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "text/csv,application/json,text/html;q=0.9,*/*;q=0.8"}
C = [
  ("cnbc_bars_set", "https://ts-api.cnbc.com/harmony/app/bars/.SETI/1D/19900101000000/20261106000000/adjusted/EST5EDT.json"),
  ("cnbc_bars_psei", "https://ts-api.cnbc.com/harmony/app/bars/.PSI/1D/19900101000000/20261106000000/adjusted/EST5EDT.json"),
  ("cnbc_bars_vni", "https://ts-api.cnbc.com/harmony/app/bars/.VNI/1D/19900101000000/20261106000000/adjusted/EST5EDT.json"),
  ("cnbc_5y_set", "https://ts-api.cnbc.com/harmony/app/charts/5Y.json?symbol=.SETI"),
]
lines = []
for name, url in C:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
            lines.append(f"{name}: HTTP {r.status} {len(body)} bytes {r.headers.get('Content-Type')}")
            (OUT / f"{name}.txt").write_bytes(body[:4000])
    except urllib.error.HTTPError as e:
        lines.append(f"{name}: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"{name}: {type(e).__name__}: {str(e)[:150]}")
    time.sleep(1)
(OUT / "report.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
