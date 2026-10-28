"""DOSM open data client (OpenDOSM / data.gov.my, no key): the CSV files behind the data catalogue,
and each dataset's catalogue metadata (last and next update).

Set DOSM_FROM_DIR to a folder of saved CSVs (named as on storage, e.g. cpi__cpi_2d.csv) to run offline.
"""
import csv
import io
import json
import os
import re
import time
import urllib.request

STORAGE = "https://storage.dosm.gov.my"
CATALOGUE = "https://open.dosm.gov.my/data-catalogue"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}


def _get(url, tries=4):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"DOSM request failed: {url}: {err!r}")


def raw_csv(path):
    """path like 'cpi/cpi_2d.csv' -> bytes."""
    local = os.environ.get("DOSM_FROM_DIR")
    if local:
        with open(os.path.join(local, path.replace("/", "__")), "rb") as f:
            return f.read()
    return _get(f"{STORAGE}/{path}")


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def meta(dataset_id):
    """Catalogue page metadata: {'last_updated', 'next_update', 'data_as_of'} (strings, Malaysia time), or {} offline."""
    if os.environ.get("DOSM_FROM_DIR"):
        return {}
    try:
        html = _get(f"{CATALOGUE}/{dataset_id}", tries=2)
    except RuntimeError:
        return {}
    m = re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    txt = json.dumps(json.loads(m.group(1)))
    out = {}
    for k in ("last_updated", "next_update", "data_as_of"):
        mm = re.search(r'"%s": "([^"]*)"' % k, txt)
        if mm:
            out[k] = mm.group(1)
    return out
