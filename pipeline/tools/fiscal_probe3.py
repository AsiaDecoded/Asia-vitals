"""Indonesia fiscal discovery, round 3: DJPPR (debt office) OData API at api-djppr.kemenkeu.go.id: entity sets,
the data-file service (LayananDataFileDTO and related sets, first pages), and the media files they point to.

  python -I pipeline/tools/fiscal_probe3.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36", "Accept": "application/json,*/*"}
BASES = ["https://api-djppr.kemenkeu.go.id/subscriber/api/v1", "https://api-djppr.kemenkeu.go.id/web/api/v1"]


def fetch(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:3000]
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode()


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = []

    def save(name, url):
        st, ct, b = fetch(url)
        ext = "json" if ct and "json" in ct else "xml" if ct and "xml" in ct else "bin"
        if b[:2] == b"PK":
            ext = "xlsx"
        (out / f"{name}.{ext}").write_bytes(b[:5_000_000])
        log.append({"name": name, "url": url, "status": st, "type": ct, "bytes": len(b)})
        (out / "log.json").write_text(json.dumps(log, indent=1))
        print(name, st, ct, len(b), flush=True)
        try:
            return json.loads(b)
        except Exception:  # noqa: BLE001
            return None

    sets = {}
    for i, base in enumerate(BASES):
        d = save(f"root{i}", base)
        save(f"metadata{i}", base + "/$metadata")
        if isinstance(d, dict):
            sets[base] = [v["url"] for v in d.get("value", [])]
    (out / "sets.json").write_text(json.dumps(sets, indent=1))
    # data-file and content sets: first 200 rows of each set whose name suggests data, files, statistics, debt
    for base, names in sets.items():
        for n in names:
            if re.search(r"(?i)data|file|statist|utang|debt|konten|content|layanan|publikasi|dokumen|menu|page", n):
                save(f"set_{n}", f"{base}/{n}?$top=200")
    # every media id seen in those answers: download the first 25
    ids = set()
    for p in out.glob("set_*.json"):
        ids |= set(re.findall(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", p.read_text(errors="replace")))
    for j, mid in enumerate(sorted(ids)[:25]):
        save(f"media_{mid}", f"https://api-djppr.kemenkeu.go.id/web/api/v1/media/{mid}")
    save("media_known", "https://api-djppr.kemenkeu.go.id/web/api/v1/media/0E5C1AFE-0B80-48AC-9F8C-423492188394")


if __name__ == "__main__":
    main(sys.argv[1])
