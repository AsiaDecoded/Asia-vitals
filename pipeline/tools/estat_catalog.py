"""Search e-Stat's data catalogue (files: Excel, CSV, PDF) for a statistics code and keywords.

  ESTAT_APP_ID=... python -I pipeline/tools/estat_catalog.py 00200573 discovery/catalog 寄与度

Writes <out>/catalog.json: every matching dataset and its resources (title, format, URL, dates).
The app ID is never written to the output.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.e-stat.go.jp/rest/3.0/app/json"


def call(method, **params):
    params["appId"] = os.environ["ESTAT_APP_ID"]
    url = f"{API}/{method}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def as_list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def text(x):
    return x.get("$", "") if isinstance(x, dict) else (x or "")


def main(stats_code, out, *words):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    found = []
    for w in words or [""]:
        start = 1
        while True:
            params = {"statsCode": stats_code, "limit": 1000, "startPosition": start}
            if w:
                params["searchWord"] = w
            res = call("getDataCatalog", **params)
            body = res["GET_DATA_CATALOG"]
            st = body["RESULT"]["STATUS"]
            if st == 1:
                break
            if st != 0:
                raise SystemExit(f"getDataCatalog error {st}: {body['RESULT'].get('ERROR_MSG')}")
            dl = body.get("DATA_CATALOG_LIST_INF", {})
            for d in as_list(dl.get("DATA_CATALOG_INF")):
                ds = d.get("DATASET", {})
                for r in as_list(d.get("RESOURCES", {}).get("RESOURCE")):
                    found.append({
                        "word": w,
                        "dataset": text(ds.get("TITLE", {}).get("NAME") if isinstance(ds.get("TITLE"), dict) else ds.get("TITLE")),
                        "id": r.get("@id"),
                        "title": text(r.get("TITLE", {}).get("NAME") if isinstance(r.get("TITLE"), dict) else r.get("TITLE")),
                        "table": r.get("TITLE", {}).get("TABLE_NAME") if isinstance(r.get("TITLE"), dict) else None,
                        "format": r.get("FORMAT"),
                        "url": r.get("URL"),
                        "release": r.get("RELEASE_DATE"),
                        "last_modified": r.get("LAST_MODIFIED_DATE"),
                        "raw_title": r.get("TITLE"),
                    })
            nxt = dl.get("RESULT_INF", {}).get("NEXT_KEY")
            if not nxt:
                break
            start = int(nxt)
    (out / "catalog.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    print(f"{len(found)} resources")


if __name__ == "__main__":
    main(*sys.argv[1:])
