"""IMF data portal client (api.imf.org, SDMX 2.1). No key needed.

series(flow, key) returns ({series attributes}, [(period, value or None), ...]) per series.
"""
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://api.imf.org/external/sdmx/2.1/data"
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)"}


def fetch(flow, key, start="1900", tries=4):
    url = f"{BASE}/{flow}/{key}?startPeriod={start}"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                raise RuntimeError(f"IMF {e.code} for {url}") from e
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def parse(xml_bytes):
    """[(series attributes, [(TIME_PERIOD, OBS_VALUE or None, obs attributes)])] from structure-specific XML."""
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if re.sub(r"\{.*\}", "", el.tag) != "Series":
            continue
        obs = []
        for o in el:
            if re.sub(r"\{.*\}", "", o.tag) != "Obs":
                continue
            v = o.attrib.get("OBS_VALUE")
            obs.append((o.attrib["TIME_PERIOD"], float(v) if v not in (None, "", "NaN") else None, dict(o.attrib)))
        out.append((dict(el.attrib), obs))
    return out
