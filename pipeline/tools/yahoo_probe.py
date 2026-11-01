"""Probe: Yahoo Finance chart API for the Jakarta Composite (^JKSE), monthly and daily, max range. Saves raw JSON."""
import json, sys, time, urllib.request, pathlib
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
log = []
for host in ["query1", "query2"]:
    for iv in ["1mo", "1d"]:
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/%5EJKSE?interval={iv}&period1=0&period2={int(time.time())}&events=history"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                b = r.read()
            (out / f"jkse_{host}_{iv}.json").write_bytes(b)
            d = json.loads(b)["chart"]["result"][0]
            ts = d["timestamp"]; q = d["indicators"]["quote"][0]["close"]
            log.append(f"{host} {iv}: {len(ts)} obs {time.strftime('%Y-%m-%d', time.gmtime(ts[0]))}..{time.strftime('%Y-%m-%d', time.gmtime(ts[-1]))}; first {q[0]} last {q[-1]}; nulls {sum(v is None for v in q)}")
        except Exception as e:
            log.append(f"{host} {iv}: {type(e).__name__} {e}")
        time.sleep(2)
(out / "log.txt").write_text("\n".join(log) + "\n"); print("\n".join(log))
