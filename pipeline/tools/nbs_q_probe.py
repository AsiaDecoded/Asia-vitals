"""Probe: NBS quarterly tree (code 2): catalogs on GDP / value added by industry, their indicators and data.
Writes discovery/nbs_q/ on the branch it runs on."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import nbs

OUT = Path("discovery/nbs_q"); OUT.mkdir(parents=True, exist_ok=True)
log = []
root = nbs.tree("2")
json.dump(root, open(OUT / "root.json", "w"), ensure_ascii=False, indent=1)
rid = root[0]["_id"]
queue, leaves = [(rid, "")], []
while queue:
    pid, path = queue.pop(0)
    for n in nbs.tree("2", pid):
        nm = (n.get("_name") or n.get("name") or "").strip()
        p = (path + " > " + nm).strip(" >")
        log.append(("LEAF " if n.get("isLeaf") else "NODE ") + p + "  " + n["_id"])
        if n.get("isLeaf"):
            leaves.append({"cid": n["_id"], "path": p})
        elif path == "" or any(k in p for k in ("国民经济核算", "国内生产总值", "增加值", "GDP")):
            queue.append((n["_id"], p))
    time.sleep(0.3)
(OUT / "tree.txt").write_text("\n".join(log), encoding="utf-8")
for lf in leaves:
    if not any(k in lf["path"] for k in ("国内生产总值", "增加值")):
        continue
    try:
        ind = nbs.indicators(lf["cid"])
        ids = [i["_id"] for i in ind]
        rows, _ = nbs.table(lf["cid"], ids, "201901", "202612", root=rid)
        json.dump({"path": lf["path"], "indicators": ind, "rows": rows}, open(OUT / f"cat_{lf['cid']}.json", "w"), ensure_ascii=False, indent=1)
        log.append(f"DATA {lf['path']}: {len(ind)} indicators, {len(rows)} rows")
    except Exception as e:  # noqa: BLE001
        log.append(f"FAIL {lf['path']}: {e}")
    time.sleep(0.5)
(OUT / "tree.txt").write_text("\n".join(log), encoding="utf-8")
print("\n".join(log))
