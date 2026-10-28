"""MAS's inflation forecasts, from the monthly MAS-MTI release "Consumer Price Developments".

Each release ends with MAS's forecast ranges for MAS core and CPI-All Items inflation for the current year (and,
later in the year, the next). The ranges are published only as text, so this source reads the release PDF for the
latest CPI month already in data/sg/cpi and writes the stated ranges, word for word, to
data/sg/cpi/mas_forecast.csv. It runs on Singapore CPI release days, after sg_cpi_singstat.
"""
import csv
import io
import re
import urllib.request

from core.common import DATA, CheckFailed, read_json

NAME = "sg_mas_forecast"
DESCRIPTION = "MAS forecast ranges for MAS core and CPI-All Items inflation (MAS-MTI monthly release)"
OUT = DATA / "sg" / "cpi"
FILE = OUT / "mas_forecast.csv"
COLUMNS = ["cpi_month", "year", "measure", "forecast", "release_url"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
BASE = "https://www.mas.gov.sg/-/media/mas-media-library/news/consumer-price-developments/{folder}/consumer-price-developments-in-{month}-{year}.pdf"

# "MAS Core Inflation is projected to average 1.5–2.0% in 2026 and 1.5–2.5% in 2027."
# "CPI-All Items inflation is forecast to come in at around 2.0% in 2026 and 1.5–2.5% in 2027."
RANGE = r"((?:around |about |between )?-?\d+(?:\.\d+)?%?(?:\s*(?:–|-|to|and)\s*-?\d+(?:\.\d+)?)?\s*%)"
PATTERNS = {
    "core": re.compile(r"MAS\s+Core\s+Inflation\s+is\s+(?:now\s+)?(?:projected|forecast|expected)\s+to\s+(?:average|come\s+in\s+at)\s+"
                       + RANGE + r"\s+in\s+(\d{4})(?:\s*,?\s*and\s+" + RANGE + r"\s+in\s+(\d{4}))?", re.I),
    "headline": re.compile(r"CPI-All\s+Items\s+inflation\s+is\s+(?:now\s+)?(?:projected|forecast|expected)\s+to\s+(?:average|come\s+in\s+at)\s+"
                           + RANGE + r"\s+in\s+(\d{4})(?:\s*,?\s*and\s+" + RANGE + r"\s+in\s+(\d{4}))?", re.I),
}


def _clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"(\d%?)\s*[-–]\s*(\d)", r"\1–\2", s)


def parse(text):
    """{(measure, year): forecast text} from a release's text."""
    text = re.sub(r"\s+", " ", text)
    out = {}
    for measure, pat in PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        out[(measure, m.group(2))] = _clean(m.group(1))
        if m.group(4):
            out[(measure, m.group(4))] = _clean(m.group(3))
    return out


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _pdf_text(data):
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


def update(**_):
    rel = read_json(OUT / "release.json", {}) or {}
    month = rel.get("latest_month")
    if not month:
        raise CheckFailed(["no Singapore CPI release in data/sg/cpi yet"])
    if FILE.exists():
        rows = list(csv.DictReader(FILE.open()))
        if rows and rows[0]["cpi_month"] == month:
            return {"updated": False, "code": rel.get("code"), "summary": f"no change (forecast for CPI {month[:7]} already read)"}
    y, m = int(month[:4]), int(month[5:7])
    name = MONTHS[m - 1]
    # the release for a December CPI month comes out in January: try both year folders
    urls = [BASE.format(folder=f, month=name, year=y) for f in sorted({y, y + 1 if m == 12 else y})]
    errors = []
    for url in urls:
        try:
            text = _pdf_text(_fetch(url))
        except Exception as e:  # noqa: BLE001 - report every failure
            errors.append(f"{url}: {e}")
            continue
        found = parse(text)
        if not any(k[0] == "core" for k in found) or not any(k[0] == "headline" for k in found):
            errors.append(f"{url}: forecast sentences not found (core {sorted(k for k in found if k[0] == 'core')}, "
                          f"headline {sorted(k for k in found if k[0] == 'headline')})")
            continue
        OUT.mkdir(parents=True, exist_ok=True)
        with FILE.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            w.writeheader()
            for (measure, year), fc in sorted(found.items(), key=lambda kv: (kv[0][1], kv[0][0])):
                w.writerow({"cpi_month": month, "year": year, "measure": measure, "forecast": fc, "release_url": url})
        summary = "; ".join(f"{ms} {yr}: {fc}" for (ms, yr), fc in sorted(found.items()))
        return {"updated": True, "code": rel.get("code"), "summary": f"MAS forecasts read from the {name.title()} {y} release: {summary}"}
    raise CheckFailed(errors)
