"""Fetch RBI's OBICUS (capacity utilisation) release PDFs and the publication archive page; save text and tables.
Usage: python -I pipeline/tools/rbi_obicus_probe.py discovery/rbi_obicus
"""
import os
import re
import sys
import urllib.request

import pdfplumber

OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/rbi_obicus"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals; +https://github.com/AsiaDecoded/asia-vitals)"}
log = []


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def pdf(name, url):
    try:
        b = get(url)
        p = os.path.join(OUT, name + ".pdf")
        open(p, "wb").write(b)
        with pdfplumber.open(p) as d, open(os.path.join(OUT, name + ".txt"), "w") as t:
            for i, page in enumerate(d.pages):
                t.write(f"\n===== page {i + 1}\n" + (page.extract_text() or ""))
                for j, tab in enumerate(page.extract_tables()):
                    t.write(f"\n--- table {j + 1}\n" + "\n".join(" | ".join(str(c) for c in row) for row in tab))
        log.append(f"ok {name} {len(b)}")
    except Exception as e:  # noqa: BLE001
        log.append(f"FAIL {name} {url} {e!r}")


pdf("obicus_2026q1", "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/OBICUS07102026FL8CF879A4B9AD4C3A8017451D7A83D8F6.PDF")
# archive pages: list every OBICUS release PDF link
links = set()
for url in ["https://www.rbi.org.in/Scripts/QuarterlyPublications.aspx?head=Quarterly+Order+Books%2C+Inventories+and+Capacity+Utilisation+Survey"]:
    try:
        h = get(url).decode("utf-8", "replace")
        open(os.path.join(OUT, "archive.html"), "w").write(h)
        links |= set(re.findall(r"https?://rbidocs\.rbi\.org\.in/rdocs/Publications/PDFs/[^\"' >]+\.PDF", h, re.I))
        log.append(f"ok archive {len(h)} chars, {len(links)} pdf links")
    except Exception as e:  # noqa: BLE001
        log.append(f"FAIL archive {e!r}")
open(os.path.join(OUT, "links.txt"), "w").write("\n".join(sorted(links)) + "\n")
open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
