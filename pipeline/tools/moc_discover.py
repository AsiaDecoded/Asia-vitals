"""Probe Thailand's Ministry of Commerce price data (TPSO), round 2.

  python -I pipeline/tools/moc_discover.py OUTDIR

- data.moc.go.th code lists (CPIIndex.csv and the others)
- dataapi.moc.go.th: headline CPI over every base, core, PPI, export/import prices, with long timeouts,
  calls in parallel, each timed
- index.tpso.go.th (Next.js): the JS bundles, searched for the API it uses, and that API's document page
"""
import concurrent.futures as cf
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
CTX = ssl.create_default_context()


def fetch(url, timeout=150, tries=2):
    last = None
    for a in range(tries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=CTX) as r:
                return r.status, r.read(), round(time.time() - t0, 1)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), round(time.time() - t0, 1)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5)
    return None, repr(last).encode(), None


def save(out, name, body):
    p = out / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if len(body) > 300_000:
        with gzip.open(str(p) + ".gz", "wb") as f:
            f.write(body)
    else:
        p.write_bytes(body)


def api_job(out, name, ep, q):
    url = f"{API}/{ep}?{urllib.parse.urlencode(q)}"
    st, body, secs = fetch(url)
    save(out, f"api/{name}.json", body)
    info = {"url": url, "status": st, "secs": secs, "bytes": len(body)}
    try:
        d = json.loads(body.decode("utf-8-sig"))
        if isinstance(d, list):
            info.update(n=len(d), bases=sorted({r.get("base_year") for r in d}),
                        first=d[:1], last=d[-1:],
                        ids=sorted({(r.get("index_id"), r.get("index_description")) for r in d})[:40])
        else:
            info["json"] = str(d)[:300]
    except Exception:  # noqa: BLE001
        info["text"] = body[:300].decode("utf-8", "replace")
    print(name, st, secs, info.get("n"), flush=True)
    return name, info


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"codelists": {}, "api": {}, "tpso": {}}
    for n in ("CPIIndex", "CPIG", "CPIL", "CPIU", "CPIP", "PPICPA", "PPISOP", "EXI", "IMI", "CSI", "RFT"):
        st, body, secs = fetch(f"https://data.moc.go.th/Download/{n}.csv", timeout=60, tries=1)
        summary["codelists"][n] = {"status": st, "bytes": len(body)}
        if st == 200:
            save(out, f"codes/{n}.csv", body)
    core_ids = []
    p = out / "codes" / "CPIIndex.csv"
    if p.exists():
        txt = p.read_bytes().decode("utf-8-sig", "replace")
        summary["codelists"]["CPIIndex_head"] = txt[:3000]
        core_ids = [ln.split(",")[0].strip('"') for ln in txt.splitlines() if re.search(r"พื้นฐาน|core", ln, re.I)]
    summary["core_ids"] = core_ids
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))

    H = "0000000000000000"
    jobs = [
        ("cpig_h_2024_2026", "cpig-indexes", {"region_id": 5, "index_id": H, "from_year": 2024, "to_year": 2026}),
        ("cpig_h_2026", "cpig-indexes", {"region_id": 5, "index_id": H, "from_year": 2026, "to_year": 2026}),
        ("cpig_h_2005_2014", "cpig-indexes", {"region_id": 5, "index_id": H, "from_year": 2005, "to_year": 2014}),
        ("cpig_h_1976_2004", "cpig-indexes", {"region_id": 5, "index_id": H, "from_year": 1976, "to_year": 2004}),
        ("cpig_bkk_2026", "cpig-indexes", {"region_id": 0, "index_id": H, "from_year": 2026, "to_year": 2026}),
        ("cpil_h_2024_2026", "cpil-indexes", {"region_id": 5, "index_id": H, "from_year": 2024, "to_year": 2026}),
        ("cpiu_h_2024_2026", "cpiu-indexes", {"region_id": 5, "index_id": H, "from_year": 2024, "to_year": 2026}),
        ("ppicpa_h_2010_2026", "ppi-cpa-indexes", {"index_id": H, "from_year": 2010, "to_year": 2026}),
        ("ppisop_h_2024_2026", "ppi-sop-indexes", {"index_id": H, "from_year": 2024, "to_year": 2026}),
        ("exi_h_2024_2026", "exi-indexes", {"index_id": H, "from_year": 2024, "to_year": 2026}),
        ("imi_h_2024_2026", "imi-indexes", {"index_id": H, "from_year": 2024, "to_year": 2026}),
    ] + [(f"cpig_core_{i}", "cpig-indexes", {"region_id": 5, "index_id": c, "from_year": 2024, "to_year": 2026})
         for i, c in enumerate(core_ids[:4])]
    with cf.ThreadPoolExecutor(6) as ex:
        for name, info in ex.map(lambda j: api_job(out, *j), jobs):
            summary["api"][name] = info
            (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))

    # index.tpso.go.th: bundles -> API urls
    st, body, _ = fetch("https://index.tpso.go.th/", timeout=60)
    page = body.decode("utf-8", "replace")
    chunks = sorted(set(re.findall(r'/_next/static/[^"\']+\.js', page)))
    found = set()
    for c in chunks:
        st, b, _ = fetch("https://index.tpso.go.th" + c, timeout=60, tries=1)
        t = b.decode("utf-8", "replace")
        for u in re.findall(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./{}$]*)?', t):
            if "tpso" in u or "moc" in u or "api" in u.lower():
                found.add(u)
        for u in re.findall(r'["\'`](/api/[A-Za-z0-9_\-./]*)', t):
            found.add(u)
        if "pages/" in c or "_app" in c:
            save(out, "tpso_js/" + c.rsplit("/", 1)[-1], b)
    summary["tpso"]["urls"] = sorted(found)
    for path in ("/document", "/api-document", "/apiDocument", "/api/document", "/cpi", "/api"):
        st, b, _ = fetch("https://index.tpso.go.th" + path, timeout=60, tries=1)
        save(out, "tpso_pages" + path.replace("/", "_") + ".html", b)
        summary["tpso"][path] = {"status": st, "bytes": len(b)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
