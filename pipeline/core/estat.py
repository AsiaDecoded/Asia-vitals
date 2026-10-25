"""Minimal e-Stat API client (https://www.e-stat.go.jp/api/). Needs ESTAT_APP_ID in the environment."""
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://api.e-stat.go.jp/rest/3.0/app/json"


def _call(method, params, retries=3):
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        raise RuntimeError("ESTAT_APP_ID is not set (GitHub secret missing?)")
    url = f"{API}/{method}?{urllib.parse.urlencode({**params, 'appId': app_id})}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))


def _as_list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def get_values(stats_data_id, **filters):
    """All values for a table and filters, following pagination.

    Returns a list of dicts {tab, cat01, area, time, value(str)} with the dimension codes as keys
    (whatever dimensions the table has, minus the '@').
    """
    out, start = [], 1
    while True:
        res = _call("getStatsData", {"statsDataId": stats_data_id, "limit": 100000,
                                     "startPosition": start, "metaGetFlg": "N", "cntGetFlg": "N",
                                     **filters})
        body = res["GET_STATS_DATA"]
        status = body["RESULT"]["STATUS"]
        if status == 1:  # no data matching the filters
            break
        if status != 0:
            raise RuntimeError(f"e-Stat error {status}: {body['RESULT'].get('ERROR_MSG')}")
        sd = body["STATISTICAL_DATA"]
        for v in _as_list(sd.get("DATA_INF", {}).get("VALUE")):
            rec = {k[1:]: val for k, val in v.items() if k.startswith("@")}
            rec["value"] = v.get("$")
            out.append(rec)
        nxt = sd.get("RESULT_INF", {}).get("NEXT_KEY")
        if not nxt:
            break
        start = int(nxt)
    return out
