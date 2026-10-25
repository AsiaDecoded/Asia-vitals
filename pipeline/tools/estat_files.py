"""Download e-Stat file datasets (Excel) by statInfId into a folder, for building parsers.

  python -I pipeline/tools/estat_files.py discovery/files 000040513578 ...

No app ID needed: these are the public file-download links.
"""
import sys
import urllib.request
from pathlib import Path


def main(out, *ids):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for i in ids:
        url = f"https://www.e-stat.go.jp/stat-search/file-download?statInfId={i}&fileKind=0"
        req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals"})
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
            name = r.headers.get_filename() or f"{i}.xls"
        ext = Path(name).suffix or ".xls"
        (out / f"{i}{ext}").write_bytes(data)
        print(i, name, len(data))


if __name__ == "__main__":
    main(*sys.argv[1:])
