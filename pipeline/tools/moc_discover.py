"""Probe Thailand's Ministry of Commerce open data (TPSO price indices) and related pages.

  python -I pipeline/tools/moc_discover.py OUTDIR

Saves: code-list CSVs from data.moc.go.th/Download, API samples from dataapi.moc.go.th for
every index family, headline and core CPI history, and the HTML of TPSO/BOT pages that might
carry seasonally adjusted CPI or weights.
"""
import gzip
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9,th;q=0.8"}
API = "https://dataapi.moc.go.th"
FAMILIES = {  # endpoint: candidate code-list names
    "cpig-indexes": ["CPIG"], "cpil-indexes": ["CPIL"], "cpiu-indexes": ["CPIU"], "cpip-indexes": ["CPIP"],
    "ppi-cpa-indexes": ["PPICPA"], "ppi-sop-indexes": ["PPISOP"], "exi-indexes": ["EXI"], "imi-indexes": ["IMI"],
}
PAGES = [
    "https://data.moc.go.th/OpenData/CPIGIndexes", "https://data.moc.go.th/OpenData/CPILIndexes",
    "https://data.moc.go.th/OpenData/CPIUIndexes", "https://data.moc.go.th/OpenData/PPISOPIndexes",
    "https://data.moc.go.th/OpenData/IMIIndexes", "https://data.moc.go.th/economy?show=index",
    "https://index.tpso.go.th/", "https://www.tpso.go.th/", "https://tpso.go.th/press_conference_trade_index",
    "https://www.tpso.go.th/home", "https://catalog-tpso.moc.go.th/dataset/",
    "https://catalog-tpso.moc.go.th/api/3/action/package_search?rows=200",
    "https://data.go.th/api/3/action/package_search?q=%E0%B8%94%E0%B8%B1%E0%B8%8A%E0%B8%99%E0%B8%B5%E0%B8%A3%E0%B8%B2%E0%B8%84%E0%B8%B2&rows=100",
    "https://www.bot.or.th/en/statistics/prices.html",
    "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=409&language=ENG",
]
CTX = ssl.create_default_context()
LEGACY = ssl.create_default_context()
LEGACY.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
LEGACY.set_ciphers("DEFAULT:@SECLEVEL=1")


def fetch(url, tries=1, timeout=25):
    last = None
    for ctx in (CTX, LEGACY):
        for a in range(tries):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=ctx) as r:
                    return r.status, dict(r.headers), r.read()
            except urllib.error.HTTPError as e:
                return e.code, dict(e.headers), e.read()
            except Exception as e:  # noqa: BLE001
                last = e
    return None, {}, repr(last).encode()


def save(out, name, body):
    p = out / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if len(body) > 200_000:
        with gzip.open(str(p) + ".gz", "wb") as f:
            f.write(body)
    else:
        p.write_bytes(body)


def api(endpoint, **q):
    st, hd, body = fetch(f"{API}/{endpoint}?{urllib.parse.urlencode(q)}")
    try:
        return st, json.loads(body.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        return st, body[:500].decode("utf-8", "replace")


T0 = time.time()
BUDGET = 22 * 60


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"codelists": {}, "api": {}, "pages": {}}
    codes = {}
    for ep, names in FAMILIES.items():
        for n in names:
            for url in (f"https://data.moc.go.th/Download/{n}.csv", f"https://data.moc.go.th/Download/{n.lower()}.csv"):
                st, hd, body = fetch(url)
                summary["codelists"][url] = {"status": st, "bytes": len(body)}
                if st == 200 and body:
                    save(out, f"codes/{n}.csv", body)
                    txt = body.decode("utf-8-sig", "replace")
                    codes[ep] = re.findall(r"\b\d{16}\b", txt)
                    break
        # headline sample, last 3 years and a long range to see the base years returned
        q = {"index_id": "0000000000000000", "from_year": 2024, "to_year": 2026}
        if ep in ("cpig-indexes", "cpil-indexes", "cpiu-indexes"):
            q["region_id"] = 5
        st, data = api(ep, **q)
        summary["api"][ep] = {"status": st, "n": len(data) if isinstance(data, list) else None,
                              "first": data[:2] if isinstance(data, list) else data,
                              "last": data[-2:] if isinstance(data, list) else None,
                              "codes_in_list": len(codes.get(ep, []))}
        save(out, f"api/{ep}_head_2024_2026.json", json.dumps(data, ensure_ascii=False).encode())
        print(ep, st, summary["api"][ep]["n"], len(codes.get(ep, [])))
        time.sleep(1)

    pages(out, summary)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    # CPI headline long history (base years), all regions, and every code for 2025-2026
    for y0, y1 in ((1976, 1999), (2000, 2014), (2015, 2023)):
        st, data = api("cpig-indexes", region_id=5, index_id="0000000000000000", from_year=y0, to_year=y1)
        save(out, f"api/cpig_all_{y0}_{y1}.json", json.dumps(data, ensure_ascii=False).encode())
        summary["api"][f"cpig_all_{y0}_{y1}"] = {"status": st, "n": len(data) if isinstance(data, list) else data,
                                                 "bases": sorted({d.get("base_year") for d in data}) if isinstance(data, list) else None}
    for ep in ("cpig-indexes", "ppi-cpa-indexes", "ppi-sop-indexes", "exi-indexes", "imi-indexes", "cpil-indexes"):
        rows, fails = [], []
        for c in codes.get(ep, []):
            if time.time() - T0 > BUDGET:
                fails.append(['budget', None, 'stopped'])
                break
            q = {"index_id": c, "from_year": 2025, "to_year": 2026}
            if ep.startswith("cpi"):
                q["region_id"] = 5
            st, data = api(ep, **q)
            if isinstance(data, list):
                rows += data
            else:
                fails.append([c, st, str(data)[:100]])
            time.sleep(0.2)
        save(out, f"api/{ep}_allcodes_2025_2026.json", json.dumps(rows, ensure_ascii=False).encode())
        summary["api"][f"{ep}_allcodes"] = {"codes": len(codes.get(ep, [])), "rows": len(rows), "fails": fails[:20],
                                            "nfails": len(fails)}
        print(ep, "allcodes", len(rows), len(fails), flush=True)
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    # Without index_id, and an invalid region, to see defaults
    st, data = api("cpig-indexes", region_id=5, from_year=2026, to_year=2026)
    summary["api"]["cpig_noid"] = {"status": st, "n": len(data) if isinstance(data, list) else data}

    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


def pages(out, summary):
    for url in PAGES:
        st, hd, body = fetch(url)
        name = re.sub(r"[^A-Za-z0-9]+", "_", url)[:120]
        save(out, f"pages/{name}.html", body)
        txt = body.decode("utf-8", "replace")
        summary["pages"][url] = {"status": st, "bytes": len(body),
                                 "seasonal_hits": len(re.findall(r"ปรับฤดูกาล|[Ss]easonal", txt)),
                                 "weight_hits": len(re.findall(r"น้ำหนัก|[Ww]eight", txt)),
                                 "links": sorted(set(re.findall(r"https?://[^\s\"'<>]+\.(?:xlsx?|csv|pdf|json)", txt)))[:60]}


if __name__ == "__main__":
    main(sys.argv[1])
