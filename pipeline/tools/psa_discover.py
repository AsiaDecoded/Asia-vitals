"""Probe the Philippine Statistics Authority's OpenSTAT (PXWeb) API for price tables.

  python -I pipeline/tools/psa_discover.py OUTDIR

Round 1: the folder tree under DB/2M (prices), every table's metadata, and status of
psa.gov.ph pages (CPI page, advance release calendar).
"""
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
PAGES = [
    "https://psa.gov.ph/price-indices/cpi-ir",
    "https://psa.gov.ph/statistics/price-indices/cpi-ir",
    "https://psa.gov.ph/advance-release-calendar",
    "https://psa.gov.ph/content/summary-inflation-report-consumer-price-index-2018100-september-2026",
]
LOG = []


def get(url, data=None, raw=False):
    req = urllib.request.Request(url, data=data, headers={**HEADERS, **({"Content-Type": "application/json"} if data else {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                LOG.append([url, r.status, len(body)])
                return body if raw else json.loads(body.decode("utf-8-sig"))
        except urllib.error.HTTPError as e:
            LOG.append([url, e.code, 0])
            if e.code in (429, 503):
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except Exception as e:  # noqa: BLE001
            LOG.append([url, repr(e), 0])
            time.sleep(3)
    raise RuntimeError(f"failed {url}")


def walk(path, out, tree):
    items = get(f"{BASE}/{path}")
    time.sleep(0.4)
    for it in items:
        sub = f"{path}/{it['id']}"
        node = {"path": sub, "type": it.get("type"), "text": it.get("text"), "updated": it.get("updated")}
        tree.append(node)
        if it.get("type") == "l":
            walk(sub, out, tree)
        elif it.get("type") == "t":
            try:
                meta = get(f"{BASE}/{sub}")
                node["variables"] = [
                    {"code": v["code"], "text": v["text"], "n": len(v["values"]),
                     "first": v["valueTexts"][:3], "last": v["valueTexts"][-3:]}
                    for v in meta.get("variables", [])]
                fn = sub.replace("/", "__") + ".meta.json"
                (out / "meta" / fn).write_text(json.dumps(meta, ensure_ascii=False, indent=1))
            except Exception as e:  # noqa: BLE001
                node["error"] = repr(e)
            time.sleep(0.4)


def main(out):
    out = Path(out)
    (out / "meta").mkdir(parents=True, exist_ok=True)
    (out / "pages").mkdir(exist_ok=True)
    tree = []
    try:
        top = get(BASE)
        (out / "top.json").write_text(json.dumps(top, ensure_ascii=False, indent=1))
    except Exception as e:  # noqa: BLE001
        (out / "top.error.txt").write_text(repr(e))
    try:
        walk("2M", out, tree)
    except Exception as e:  # noqa: BLE001
        (out / "walk.error.txt").write_text(repr(e))
    (out / "tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1))
    for i, p in enumerate(PAGES):
        try:
            body = get(p, raw=True)
            with gzip.open(out / "pages" / f"page{i}.html.gz", "wb") as f:
                f.write(body)
        except Exception as e:  # noqa: BLE001
            (out / "pages" / f"page{i}.error.txt").write_text(f"{p}\n{e!r}")
    (out / "log.json").write_text(json.dumps(LOG, indent=0))
    print(len(tree), "nodes")


if __name__ == "__main__":
    main(sys.argv[1])
