"""Run Indonesia sources by name, including ones not yet in pipeline/sources/__init__.py (id-test.yml).

  BPS_KEY=... python -I pipeline/tools/id_run.py id_gdp_bps id_trade_bps
"""
import importlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.common import CheckFailed  # noqa: E402


def main(names):
    failed = []
    for name in names:
        if not name.startswith("id_"):
            raise SystemExit(f"{name}: Indonesia sources only")
        print(f"== {name}", flush=True)
        try:
            res = importlib.import_module(f"sources.{name}").update(force=True)
            print(f"   {res.get('summary')}")
            for w in res.get("warnings") or []:
                print(f"   warning: {w}")
        except CheckFailed as e:
            failed.append(name)
            print(f"   CHECKS FAILED ({len(e.errors)}); nothing written:")
            for err in e.errors[:40]:
                print(f"   - {err}")
        except Exception:  # noqa: BLE001
            failed.append(name)
            traceback.print_exc(file=sys.stdout)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
