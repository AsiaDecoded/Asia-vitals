"""Indonesia: original budget laws (UU APBN) 2001-2025, full text from the Ministry of Finance legal database (JDIH)
and pasal.id; saves each response and the sentences that state revenue, expenditure and the deficit.

  python -I pipeline/tools/apbn_law_probe.py OUTDIR
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
# budget year: (law number, year enacted)
LAWS = {2001: (35, 2000), 2002: (19, 2001), 2003: (29, 2002), 2004: (28, 2003), 2005: (36, 2004), 2006: (13, 2005),
        2007: (18, 2006), 2008: (45, 2007), 2009: (41, 2008), 2010: (47, 2009), 2011: (10, 2010), 2012: (22, 2011),
        2013: (19, 2012), 2014: (23, 2013), 2015: (27, 2014), 2016: (14, 2015), 2017: (18, 2016), 2018: (15, 2017),
        2019: (12, 2018), 2020: (20, 2019), 2021: (9, 2020), 2022: (6, 2021), 2023: (28, 2022), 2024: (19, 2023),
        2025: (62, 2024)}


def fetch(url, timeout=60):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:5000], round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode(), round(time.time() - t0, 1)


def text_of(b):
    t = b.decode("utf-8", "replace")
    t = re.sub(r"(?s)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;", " ", t)
    return re.sub(r"\s+", " ", t)


def main(out):
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    log = []
    for by, (n, y) in LAWS.items():
        for tag, url in (("jdih", f"https://jdih.kemenkeu.go.id/api/download/fullText/{y}/{n}TAHUN{y}UU.htm"),
                         ("pasal", f"https://pasal.id/peraturan/uu/uu-no-{n}-tahun-{y}")):
            st, b, s = fetch(url)
            (out / "pages" / f"{by}_{tag}.html").write_bytes(b[:4_000_000])
            t = text_of(b)
            hits = [m.group(0) for m in re.finditer(r"(?i).{0,160}(defisit anggaran|pendapatan negara dan hibah|belanja negara)[^.]{0,260}", t)][:12]
            log.append({"budget_year": by, "law": f"UU {n}/{y}", "src": tag, "url": url, "status": st, "bytes": len(b), "secs": s,
                        "title": (re.search(r"(?i)tentang anggaran pendapatan dan belanja negara tahun anggaran \d{4}", t) or [None])[0] if t else None,
                        "hits": hits})
            (out / "laws.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
            print(by, tag, st, len(b), s, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
