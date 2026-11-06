"""Probe 3: CNBC daily bars for the other nine benchmark indices: first and last date, number of days."""
import json, urllib.request, time
from pathlib import Path
OUT = Path("discovery/eq_probe"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SYM = {"JP": [".N225"], "KR": [".KS11", ".KOSPI"], "TW": [".TWII"], "HK": [".HSI"], "CN": [".SSEC"], "IN": [".NSEI", ".NIFTY"],
       "ID": [".JKSE"], "MY": [".KLSE"], "SG": [".STI", ".FTSTI"]}
lines = []
for e, syms in SYM.items():
    for s in syms:
        url = f"https://ts-api.cnbc.com/harmony/app/bars/{s}/1D/19700101000000/20261107000000/adjusted/EST5EDT.json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                b = (json.loads(r.read()).get("barData") or {}).get("priceBars") or []
            b = [x for x in b if float(x.get("close") or 0) > 0]
            lines.append(f"{e} {s}: {len(b)} days, {b[0]['tradeTime'][:8] if b else '-'} to {b[-1]['tradeTime'][:8] if b else '-'}, last close {b[-1]['close'] if b else '-'}")
        except Exception as ex:  # noqa: BLE001
            lines.append(f"{e} {s}: {type(ex).__name__} {str(ex)[:100]}")
        time.sleep(1)
(OUT / "report3.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
