"""Fetch MoSPI's IIP press release (2022-23 base) and extract its text and tables, to read the NIC 2-digit weights.
Usage: python -I pipeline/tools/mospi_iip_weights_probe.py discovery/mospi_iip_weights
"""
import os
import ssl
import sys
import urllib.request

import pdfplumber

OUT = sys.argv[1] if len(sys.argv) > 1 else "discovery/mospi_iip_weights"
os.makedirs(OUT, exist_ok=True)
CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
URLS = {
    "first_release_2022_23": "https://www.mospi.gov.in/uploads/latestReleases/latest_release_1780371708887_52b83604-666c-443a-82c6-4411103e2ede_Press_Release_IIP_2022-23f.pdf",
    "aug2026": "https://www.mospi.gov.in/uploads/latestReleases/latest_release_1790590696008_1b346687-0a5f-445a-83a2-28283c586094_IIP_Press_Release_August_2026.pdf",
    "jul2026": "https://www.mospi.gov.in/uploads/latestReleases/latest_release_1787912132242_3d2fc197-d8a9-48a0-840f-d0cdc12c6835_IIP_Press_Release_July_2026.pdf",
}
log = []
for k, u in URLS.items():
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)"})
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            b = r.read()
        p = os.path.join(OUT, k + ".pdf")
        open(p, "wb").write(b)
        with pdfplumber.open(p) as pdf, open(os.path.join(OUT, k + ".txt"), "w") as t:
            for i, page in enumerate(pdf.pages):
                t.write(f"\n===== page {i + 1}\n" + (page.extract_text() or ""))
                for j, tab in enumerate(page.extract_tables()):
                    t.write(f"\n--- table {j + 1}\n" + "\n".join(" | ".join(str(c) for c in row) for row in tab))
        log.append(f"ok {k} {len(b)} bytes")
    except Exception as e:  # noqa: BLE001
        log.append(f"FAIL {k} {e!r}")
open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
