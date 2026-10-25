"""List e-Stat tables for a statistics code and save their structure, for building fetchers.

  ESTAT_APP_ID=... python -I pipeline/tools/estat_discover.py 00200573 discovery/cpi "中分類" "財・サービス" "季節調整"

Writes <out>/list.json (every table: id, title, cycle, dates) and <out>/meta/<id>.json
(class codes and names) for tables whose title contains any of the keywords.
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


def main(stats_code, out, *keywords):
    out = Path(out)
    (out / "meta").mkdir(parents=True, exist_ok=True)
    tables, start = [], 1
    while True:
        res = call("getStatsList", statsCode=stats_code, limit=1000, startPosition=start)
        body = res["GET_STATS_LIST"]
        status = body["RESULT"]["STATUS"]
        if status not in (0, 1):
            raise SystemExit(f"getStatsList error {status}: {body['RESULT'].get('ERROR_MSG')}")
        dl = body.get("DATALIST_INF", {})
        for t in as_list(dl.get("TABLE_INF")):
            tables.append({
                "id": t["@id"],
                "stat_name": text(t.get("STAT_NAME")),
                "title": text(t.get("TITLE")),
                "statistics_name": t.get("STATISTICS_NAME", ""),
                "cycle": t.get("CYCLE"),
                "survey_date": t.get("SURVEY_DATE"),
                "open_date": t.get("OPEN_DATE"),
                "updated_date": t.get("UPDATED_DATE"),
                "rows": t.get("OVERALL_TOTAL_NUMBER"),
                "main_category": text(t.get("MAIN_CATEGORY")),
                "collect_area": t.get("COLLECT_AREA"),
            })
        nxt = dl.get("RESULT_INF", {}).get("NEXT_KEY")
        if not nxt:
            break
        start = int(nxt)
    (out / "list.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))
    print(f"{len(tables)} tables listed")

    picked = [t for t in tables if any(k in (t["title"] + t["statistics_name"]) for k in keywords)]
    for t in picked[:60]:
        res = call("getMetaInfo", statsDataId=t["id"])
        meta = res["GET_META_INFO"].get("METADATA_INF", {})
        classes = {}
        for c in as_list(meta.get("CLASS_INF", {}).get("CLASS_OBJ")):
            items = as_list(c.get("CLASS"))
            classes[c["@id"]] = {
                "name": c.get("@name"),
                "count": len(items),
                "items": [{"code": i.get("@code"), "name": i.get("@name"), "level": i.get("@level"),
                           "unit": i.get("@unit"), "parent": i.get("@parentCode")} for i in items[:400]],
            }
        (out / "meta" / f"{t['id']}.json").write_text(json.dumps(
            {"table": t, "classes": classes}, ensure_ascii=False, indent=1))
        print("meta", t["id"], t["title"][:60])


if __name__ == "__main__":
    main(*sys.argv[1:])
