"""Probe DOSM's open data (OpenDOSM / data.gov.my) for Malaysian price datasets.

Saves, under the output folder:
- catalogue_<term>.html / .json: catalogue search pages and their embedded page data
- meta_<id>.json: each dataset page's embedded metadata (variables, download links, update dates)
- files/<name>.csv: each CSV the metadata links to (and a list of guessed names), first 2 MB
- summary.txt: what was found
"""
import json
import os
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/dosm"
os.makedirs(os.path.join(OUT, "files"), exist_ok=True)
log = []


def get(url, limit=None):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                data = r.read(limit) if limit else r.read()
                return r.status, data
        except urllib.error.HTTPError as e:
            return e.code, b""
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3)
    return f"ERR {err!r}", b""


def next_data(html):
    m = re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


ids = set()
for term in ["cpi", "ppi", "price", "inflation", "import", "export"]:
    st, html = get(f"https://open.dosm.gov.my/data-catalogue?search={term}")
    log.append(f"catalogue {term}: {st} {len(html)} bytes")
    nd = next_data(html) if html else None
    if nd:
        json.dump(nd, open(os.path.join(OUT, f"catalogue_{term}.json"), "w"), indent=1)
        txt = json.dumps(nd)
        found = set(re.findall(r'"id":\s*"([a-z0-9_]+)"', txt))
        ids |= {i for i in found if any(k in i for k in ("cpi", "ppi", "price", "ipi_", "xpi", "mpi", "trade_price", "inflation"))}
    else:
        open(os.path.join(OUT, f"catalogue_{term}.html"), "wb").write(html[:500000])

guess = ["cpi_headline", "cpi_headline_inflation", "cpi_core", "cpi_core_inflation", "cpi_state", "cpi_state_inflation",
         "cpi_strata", "cpi_lowincome", "cpi_3d", "cpi_4d", "cpi_5d", "cpi_weights", "cpi_sa", "cpi_headline_sa", "ppi",
         "ppi_1d", "ppi_2d", "ppi_sector", "ppi_stage", "ppi_construction", "ppi_agriculture", "trade_price",
         "trade_unit_value", "ipi_import", "export_price", "import_price", "mcoicop", "cpi_mcoicop"]
ids |= set(guess)
log.append("dataset ids tried: " + ", ".join(sorted(ids)))

csvs = set()
for i in sorted(ids):
    st, html = get(f"https://open.dosm.gov.my/data-catalogue/{i}")
    nd = next_data(html) if st == 200 and html else None
    if not nd:
        log.append(f"meta {i}: {st}")
        continue
    json.dump(nd, open(os.path.join(OUT, f"meta_{i}.json"), "w"), indent=1)
    txt = json.dumps(nd)
    links = sorted(set(re.findall(r'https://storage\.dosm\.gov\.my/[^"\\ ]+\.csv', txt)))
    csvs |= set(links)
    title = re.search(r'"title":\s*"([^"]+)"', txt)
    log.append(f"meta {i}: 200 {title.group(1) if title else ''} | csv: {', '.join(links)}")

for name in ["cpi_2d", "cpi_2d_core", "cpi_3d", "cpi_4d", "cpi_5d", "cpi_2d_state", "cpi_2d_strata", "cpi_2d_lowincome",
             "cpi_2d_inflation", "cpi_2d_core_inflation", "cpi_weights", "cpi_2d_sa", "cpi_sa"]:
    csvs.add(f"https://storage.dosm.gov.my/cpi/{name}.csv")
csvs |= {"https://storage.dosm.gov.my/ppi/ppi.csv", "https://storage.dosm.gov.my/ppi/ppi_1d.csv",
         "https://storage.dosm.gov.my/ppi/ppi_2d.csv", "https://storage.dosm.gov.my/dictionaries/mcoicop.csv",
         "https://storage.dosm.gov.my/dictionaries/msic.csv"}

for u in sorted(csvs):
    st, data = get(u, limit=2_000_000)
    name = u.split("storage.dosm.gov.my/")[1].replace("/", "__")
    if st == 200 and data:
        open(os.path.join(OUT, "files", name), "wb").write(data)
        lines = data.decode("utf-8", "replace").splitlines()
        log.append(f"file {u}: {len(data)} bytes, {len(lines)} lines | {lines[0] if lines else ''} | {lines[1] if len(lines) > 1 else ''} | last: {lines[-1] if lines else ''}")
    else:
        log.append(f"file {u}: {st}")

# API sample for each id that has metadata
for i in sorted(ids):
    st, data = get(f"https://api.data.gov.my/data-catalogue?id={i}&limit=3")
    if st == 200:
        log.append(f"api {i}: {data[:300].decode('utf-8', 'replace')}")

open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
