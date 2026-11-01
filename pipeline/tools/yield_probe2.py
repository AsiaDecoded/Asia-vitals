"""Indonesia 10-year yield, round 2: AsianBondsOnline (ADB) data pages and their links, and Bank Indonesia's
government bond yield page. Saves pages and any csv/xls/json links found (first 30).

  python -I pipeline/tools/yield_probe2.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
PAGES = ["https://asianbondsonline.adb.org/xml/get-indicator.php?code=Int_rate_spread_2yrvs10yr",
         "https://asianbondsonline.adb.org/xml/get-indicator.php?code=Yld_volatility",
         "https://asianbondsonline.adb.org/data-portal/get-metadata.php?code=Int_rate_spread_2yrvs10yr"]


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:5000]
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode()


def main(out):
    out = Path(out)
    (out / "files").mkdir(parents=True, exist_ok=True)
    log = []
    got = 0
    for i, u in enumerate(PAGES):
        st, ct, b = fetch(u)
        (out / f"page{i}.html").write_bytes(b)
        t = b.decode("utf-8", "replace")
        links = sorted(set(re.findall(r'(?:href|src|data-url|url)\s*[=:]\s*["\']([^"\']+)["\']', t)))
        data = [l for l in links if re.search(r"(?i)\.(csv|xlsx?|json|php)(\?|$)|download|export|api|data-portal|chart", l)]
        data += sorted(set(re.findall(r"(?:url|href)\s*[:=]\s*['\"]([^'\"]+\.php[^'\"]*)", t)))
        log.append({"url": u, "status": st, "type": ct, "bytes": len(b), "data_links": data[:120],
                    "yield_hits": [t[max(0, m.start() - 100): m.end() + 100] for m in re.finditer(r"(?i)10[- ]?year|yield", t)][:6]})
        for l in data:
            if got >= 30 or not re.search(r"(?i)\.(csv|xlsx?|json)", l):
                continue
            full = urllib.parse.urljoin(u, l)
            st2, ct2, fb = fetch(full)
            name = re.sub(r"[^A-Za-z0-9._-]", "_", full.split("//", 1)[-1])[:120]
            (out / "files" / name).write_bytes(fb[:5_000_000])
            log.append({"file": full, "status": st2, "type": ct2, "bytes": len(fb), "head": fb[:200].decode("utf-8", "replace")})
            got += 1
        for prog in re.findall(r"<(?:table_program|chart_program)[^>]*>\s*(?:<!\[CDATA\[)?\s*([^<\]]+)", t) + re.findall(r'name="(?:table_program|chart_program)"[^>]*value="([^"]+)"', t):
            for q in ("economy=ID&years=2000-2026&frequency=Daily&add_opts=&frequency_switch=0", "economy=ID&years=all&frequency=Daily"):
                full = urllib.parse.urljoin(u, prog.strip()) + ("&" if "?" in prog else "?") + q
                st3, ct3, pb = fetch(full)
                name = re.sub(r"[^A-Za-z0-9._-]", "_", full.split("//", 1)[-1])[:150]
                (out / "files" / name).write_bytes(pb[:10_000_000])
                log.append({"program": full, "status": st3, "type": ct3, "bytes": len(pb), "head": pb[:400].decode("utf-8", "replace")})
        (out / "y2.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), u, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
