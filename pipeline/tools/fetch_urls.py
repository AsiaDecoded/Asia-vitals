"""Download public files by URL into a folder, for building parsers (statistics-agency PDFs and spreadsheets).

  python -I pipeline/tools/fetch_urls.py discovery/web https://www.stat.go.jp/data/cpi/2020/kaisetsu/pdf/4-5.pdf ...

Each file is saved under its URL path with "/" replaced by "_". A failed URL is reported and skipped.
"""
import sys
import urllib.request
from pathlib import Path


def main(out, *urls):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for u in urls:
        name = u.split("://", 1)[-1].replace("/", "_")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "asia-vitals"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            (out / name).write_bytes(data)
            print("ok", u, len(data))
        except Exception as e:  # noqa: BLE001
            print("failed", u, e)


if __name__ == "__main__":
    main(*sys.argv[1:])
