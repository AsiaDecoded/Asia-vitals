"""Fetch a list of URLs and save each response, for checking external data sources.

  python -I pipeline/tools/probe_urls.py urls.txt discovery/probe

urls.txt: one "name url" pair per line. Saves <out>/<name>.<ext> and summary.json.
"""
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)  # some Indian government servers need this
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)", "Accept": "*/*"}


def main(listfile, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for line in Path(listfile).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, url = line.split(None, 1)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120, context=CTX) as r:
                status, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, body, ctype = e.code, e.read(), e.headers.get("Content-Type", "")
        except Exception as e:  # noqa: BLE001
            status, body, ctype = None, str(e).encode(), "error"
        ext = "json" if "json" in ctype else "xml" if "xml" in ctype else "txt"
        (out / f"{name}.{ext}").write_bytes(body[:60_000_000])
        summary.append({"name": name, "url": url, "status": status, "type": ctype, "bytes": len(body)})
        print(name, status, ctype, len(body))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
