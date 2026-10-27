"""Probe ECOS query shapes for Korea (second pass).

  python -I pipeline/tools/ecos_discover.py OUTDIR
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ecos  # noqa: E402


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for name, fn in [
        ("month_all_901Y009_202609", lambda: ecos._get(["StatisticSearch", ecos.KEY, "json", "kr", 1, 10, "901Y009", "M", "202609", "202609"])),
        ("month_all_q_901Y009_202609", lambda: ecos._get(["StatisticSearch", ecos.KEY, "json", "kr", 1, 10, "901Y009", "M", "202609", "202609", "?"])),
        ("items_401Y015", lambda: ecos._get(["StatisticItemList", ecos.KEY, "json", "kr", 1, 10, "401Y015"])),
        ("items_402Y014", lambda: ecos._get(["StatisticItemList", ecos.KEY, "json", "kr", 1, 10, "402Y014"])),
        ("cpi0_recent", lambda: ecos._get(["StatisticSearch", ecos.KEY, "json", "kr", 1, 10, "901Y009", "M", "202601", "202612", "0"])),
    ]:
        try:
            res[name] = fn()
        except Exception as e:  # noqa: BLE001
            res[name] = {"error": repr(e)}
    (out / "probe2.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
