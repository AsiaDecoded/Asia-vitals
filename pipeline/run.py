"""Run every registered source (or the ones named), then rebuild the combined long file.

  python -I pipeline/run.py                     # all sources: fetch, check, write what is new
  python -I pipeline/run.py jp_cpi_estat        # one source
  python -I pipeline/run.py jp_gdp_esri --code qe262_2 --from-dir raw/jp/gdp_esri/qe262_2
  python -I pipeline/run.py jp_cpi_estat --from-file raw/jp/cpi_estat/2026-09.json.gz

A source that fails its checks or errors writes nothing; the others still run.
Exit code 1 if any source failed, so GitHub flags the run (successful sources are still committed).
Writes updated=, updated_sources=, failed_sources= to $GITHUB_OUTPUT.
"""
import argparse
import csv
import importlib
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.common import DATA, LONG_COLUMNS, CheckFailed, now  # noqa: E402
from sources import SOURCES  # noqa: E402


def gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def combine_long():
    """data/all_long.csv.gz: every source's long file stacked, for cross-country views. A folder shared by two
    sources holds long.csv for one and long_<name>.csv for the other (e.g. data/id/jci/long_daily.csv), so both
    patterns are read.

    Gzipped: uncompressed it passes GitHub's 100 MB file limit with all 12 economies.
    """
    import gzip
    files = sorted(set(DATA.glob("*/*/long.csv")) | set(DATA.glob("*/*/long_*.csv")))
    out = DATA / "all_long.csv.gz"
    (DATA / "all_long.csv").unlink(missing_ok=True)
    n = 0
    with gzip.open(out, "wt", newline="", compresslevel=9) as f:
        w = csv.DictWriter(f, fieldnames=LONG_COLUMNS, lineterminator="\n")
        w.writeheader()
        for p in files:
            for row in csv.DictReader(open(p)):
                w.writerow(row)
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", help="source names (default: all)")
    ap.add_argument("--code", help="GDP: release code to process")
    ap.add_argument("--from-dir", help="GDP: folder with that release's CSVs")
    ap.add_argument("--from-file", help="CPI: saved API response (.json or .json.gz)")
    args = ap.parse_args()
    names = args.sources or SOURCES
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise SystemExit(f"unknown source(s): {unknown}; known: {SOURCES}")
    # run in registry order, whatever order they were named in (the release calendar lists sources by group;
    # sources that read other sources' files, e.g. id_fiscal_gdp, sit after them in the registry)
    names = [n for n in SOURCES if n in names]

    updated, failed = [], []
    report = [f"run at {now()} UTC; sources: {' '.join(names)}"]

    def say(line):
        print(line)
        report.append(line)

    for name in names:
        say(f"== {name}")
        mod = importlib.import_module(f"sources.{name}")
        try:
            res = mod.update(code=args.code, from_dir=args.from_dir, from_file=args.from_file)
        except CheckFailed as e:
            say(f"   CHECKS FAILED ({len(e.errors)}); nothing written for {name}:")
            for err in e.errors[:40]:
                say(f"   - {err}")
            failed.append(name)
            continue
        except Exception:  # noqa: BLE001 - one source's failure must not stop the others
            say(f"   ERROR in {name}; nothing written:")
            say(traceback.format_exc().rstrip())
            failed.append(name)
            continue
        say(f"   {'UPDATED' if res['updated'] else 'unchanged'}: {res['summary']}")
        for w in res.get("warnings", []):
            say(f"   WARNING: {w}")
        if res["updated"]:
            updated.append(name)

    if updated:
        say(f"== combined long file: {combine_long()} rows")
        try:
            from core.asia import build as build_asia
            res = build_asia()
            say(f"== Asia table: {'UPDATED' if res['updated'] else 'unchanged'}: {res['summary']}")
            for w in res["warnings"]:
                say(f"   WARNING: {w}")
        except Exception:  # noqa: BLE001 - the Asia table must not fail the country sources
            say("   ERROR building the Asia table:")
            say(traceback.format_exc().rstrip())
        try:
            from core.asia_fx import build as build_asia_fx
            res = build_asia_fx()
            say(f"== Asia FX: {'UPDATED' if res['updated'] else 'unchanged'}: {res['summary']}")
            for w in res["warnings"]:
                say(f"   WARNING: {w}")
        except Exception:  # noqa: BLE001 - nor the Asia FX file
            say("   ERROR building the Asia FX file:")
            say(traceback.format_exc().rstrip())
        try:
            from core.asia_mfg import build as build_asia_mfg
            res = build_asia_mfg()
            say(f"== Asia manufacturing: {'UPDATED' if res['updated'] else 'unchanged'}: {res['summary']}")
            for w in res["warnings"]:
                say(f"   WARNING: {w}")
        except Exception:  # noqa: BLE001 - nor the Asia manufacturing files
            say("   ERROR building the Asia manufacturing files:")
            say(traceback.format_exc().rstrip())
    say(f"result: updated={updated or '-'} failed={failed or '-'}")
    (Path(__file__).resolve().parent.parent / "run_report.txt").write_text("\n".join(report) + "\n")
    gh_output(updated=str(bool(updated)).lower(), updated_sources=" ".join(updated),
              failed_sources=" ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
