"""Probe (9 Nov 2026): what TPSO's Open API has for October 2026 vs September (th_cpi_tpso check failing).

  python -I pipeline/tools/tpso_probe.py discovery/tpso
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "pipeline")
from core import tpso  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/tpso")
OUT.mkdir(parents=True, exist_ok=True)
log = []
for fam in ("Cpig", "Cpil"):
    m = tpso.master(fam)
    (OUT / f"master_{fam}.json").write_text(json.dumps(m, ensure_ascii=False, indent=1)[:200000])
    log.append(f"{fam} latest: {tpso.latest_period(m, 2566)}")
for fam, typ in (("Cpig", "TG"), ("Cpil", "TL"), ("Cpig", "10")):
    rows = {mo: tpso.month(fam, typ, 2566, 2026, mo) for mo in (9, 10)}
    for mo, r in rows.items():
        (OUT / f"{fam}_{typ}_2026_{mo}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    sep = {x["commodityCode"]: x for x in rows[9]}
    octo = {x["commodityCode"]: x for x in rows[10]}
    log.append(f"{fam} {typ}: Sep {len(sep)} rows, Oct {len(octo)} rows")
    miss = sorted(set(sep) - set(octo))
    log.append(f"  missing in Oct: {[(c, sep[c].get('commodityName')) for c in miss]}")
    if "00000" in octo:
        log.append(f"  Oct all-items row: {octo['00000']}")
    nulls = [c for c, x in octo.items() if not any(v not in (None, '') for k, v in x.items() if k.lower().startswith(('change', 'yoy', 'pct')))]
    log.append(f"  Oct rows with keys {sorted(next(iter(octo.values())).keys()) if octo else []}")
(OUT / "summary.txt").write_text("\n".join(log))
print("\n".join(log))
