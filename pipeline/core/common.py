"""Shared pieces for every source: paths, the common long format, release files."""
import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = ROOT / "raw"

# The common long format every source writes (data/<country>/<indicator>/long.csv).
LONG_COLUMNS = ["country", "indicator", "series", "label", "measure", "area", "freq",
                "date", "value", "unit", "source", "release"]


class CheckFailed(Exception):
    """A source's data failed its checks; nothing from that source is written."""

    def __init__(self, errors):
        super().__init__(f"{len(errors)} check(s) failed")
        self.errors = errors


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_long(rows, path):
    """rows: iterable of dicts with LONG_COLUMNS keys. Rows with value None are skipped."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LONG_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            if r.get("value") is None:
                continue
            w.writerow({k: r.get(k, "") for k in LONG_COLUMNS})
            n += 1
    return n


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write_release(folder, release, warnings, rows, extra=None):
    """release.json (full record with history) and release_row.json (one-row table for dashboards)."""
    path = folder / "release.json"
    old = read_json(path, {}) or {}
    stamp = now()
    history = [h for h in old.get("history", []) if h.get("code") != release["code"]]
    history.append({"code": release["code"], "processed_at": stamp})
    record = {**release, "processed_at": stamp, "rows": rows, "warnings": warnings,
              **(extra or {}), "history": history[-60:]}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    (folder / "release_row.json").write_text(
        json.dumps([{**release, "processed_at": stamp}], ensure_ascii=False, indent=1) + "\n")
