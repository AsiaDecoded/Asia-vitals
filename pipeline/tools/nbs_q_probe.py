"""Probe 2: NBS quarterly data format (period codes, dts syntax) for manufacturing value added. Writes discovery/nbs_q/."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import nbs

OUT = Path("discovery/nbs_q"); OUT.mkdir(parents=True, exist_ok=True)
rid = nbs.tree("2")[0]["_id"]
cid = "f9b694c9b79e4ce5958bc88c6410fa67"
ids = ["1a9c5f486ee848138ddf4189b46f1830", "74dc0a5a68a14acd92d332d734d40e88"]
log = []
try:
    log.append("latest: " + json.dumps(nbs._call("new/queryDtByCid", {"cid": cid, "rootId": rid}), ensure_ascii=False))
except Exception as e:  # noqa: BLE001
    log.append(f"latest failed {e}")
for dts in (["2019A-2026D"], ["2019AQ-2026DQ"], ["201901SS-202604SS"], ["2019SS-2026SS"], ["201901QQ-202604QQ"], ["2019Q1-2026Q4"], ["201901MM-202612MM"], ["2019-2026"]):
    body = {"cid": cid, "indicatorIds": ids, "daCatalogId": "", "das": [{"text": "全国", "value": nbs.NATIONAL}],
            "showType": 1, "dts": dts, "rootId": rid}
    try:
        d = nbs._call("stream/esData", body=body, tries=2) or []
        log.append(f"{dts}: {len(d)} periods; codes {[p.get('code') for p in d][:12]}")
        json.dump(d[:6], open(OUT / f"raw_{dts[0].replace('-', '_')}.json", "w"), ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        log.append(f"{dts}: failed {str(e)[:200]}")
(OUT / "probe2.txt").write_text("\n".join(log), encoding="utf-8")
print("\n".join(log))
