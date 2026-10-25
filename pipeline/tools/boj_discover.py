"""Save a BoJ database's series list (metadata) and a sample of values, for building fetchers.

  python -I pipeline/tools/boj_discover.py PR01 discovery/boj [CODE ...]

Writes <out>/<db>_metadata.json (the raw getMetadata response) and, if codes are given,
<out>/<db>_sample.json (getDataCode for those codes, from 2024 on).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import boj  # noqa: E402


def main(db, out, *codes):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = boj.metadata(db)
    (out / f"{db}_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    rs = meta.get("RESULTSET") or []
    print(f"{db}: {len(rs)} metadata rows; keys: {sorted(rs[0].keys()) if rs else '-'}")
    if codes:
        data = boj.series(db, list(codes), start="202401")
        (out / f"{db}_sample.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(f"sample: {len(data)} series")


if __name__ == "__main__":
    main(*sys.argv[1:])
