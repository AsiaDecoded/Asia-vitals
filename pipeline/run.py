"""Check ESRI for a new GDP release and, if there is one, rebuild the data.

  python -I pipeline/run.py                          # look for the release after data/release.json
  python -I pipeline/run.py --code qe262_2 --from-dir raw/esri/qe262_2   # rebuild from saved files

Exit codes: 0 = nothing new or rebuilt successfully; 1 = a check failed (nothing written).
Writes `updated=true|false` and `code=` to $GITHUB_OUTPUT when run in GitHub Actions.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import checks  # noqa: E402
import esri  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "raw" / "esri"
STATE = DATA / "release.json"


def gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def download(code, dest):
    dest.mkdir(parents=True, exist_ok=True)
    for stem in esri.TABLES:
        url = esri.table_url(code, stem)
        body = esri.fetch(url)
        if body is None:
            raise SystemExit(f"{code}: {stem} not found at {url} (release only partly published?)")
        (dest / f"{stem}{esri.suffix(code)}.csv").write_bytes(body)
        print(f"  {stem}: {len(body):,} bytes")


def load(code, folder):
    tables = {}
    for stem, key in esri.TABLES.items():
        f = folder / f"{stem}{esri.suffix(code)}.csv"
        tables[key] = esri.parse_table(f.read_bytes())
    return tables


def find_new_release(current):
    """Try the next two releases after `current`; return the latest one that is published."""
    found = None
    code = current
    for _ in range(2):
        code = esri.next_code(code)
        if esri.fetch(esri.table_url(code, "gaku-jk")) is not None:
            found = code
        else:
            break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="release code, e.g. qe262_2")
    ap.add_argument("--from-dir", help="folder holding that release's CSVs (skips downloading)")
    args = ap.parse_args()

    state = json.loads(STATE.read_text()) if STATE.exists() else {"code": None, "history": []}

    if args.code:
        code = args.code
    else:
        if not state.get("code"):
            raise SystemExit("data/release.json has no current release; run once with --code")
        code = find_new_release(state["code"])
        if not code:
            print(f"No release after {state['code']} yet ({esri.next_code(state['code'])} not published).")
            gh_output(updated="false")
            return 0
        print(f"New release found: {code} ({esri.label(code)})")

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(args.from_dir) if args.from_dir else Path(tmp) / code
        if not args.from_dir:
            download(code, folder)
        tables = load(code, folder)
        errors, warnings = checks.run(tables, code, esri.ref_date(code), DATA / "jp_gdp.csv")
        for w in warnings:
            print("WARNING:", w)
        if errors:
            print(f"{len(errors)} check(s) failed; nothing written:")
            for e in errors[:40]:
                print("  ERROR:", e)
            gh_output(updated="false")
            return 1

        # All checks passed: keep the raw files and write the outputs.
        dest = RAW / code
        if folder.resolve() != dest.resolve():
            dest.mkdir(parents=True, exist_ok=True)
            for f in folder.glob("*.csv"):
                shutil.copy2(f, dest / f.name)

    release = {"code": code, "label": esri.label(code), "ref_quarter": esri.ref_date(code),
               "menu_url": esri.menu_url(code)}
    rows = build.write_combined(tables, DATA / "jp_gdp.csv")
    slugs = build.write_json(tables, release, DATA / "json")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    history = [h for h in state.get("history", []) if h.get("code") != code]
    history.append({"code": code, "processed_at": now})
    STATE.write_text(json.dumps({**release, "processed_at": now, "rows": rows,
                                 "warnings": warnings, "history": history},
                                ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote data/jp_gdp.csv ({rows} rows), {len(slugs)} JSON files, data/release.json")
    gh_output(updated="true", code=code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
