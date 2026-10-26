"""Download PPAC's retail selling prices of petrol and diesel in the four metros (daily, since 16 June 2017).

  python -I pipeline/tools/ppac_rsp.py <out dir>

Fetches the PPAC page, saves it, and downloads every .xls/.xlsx/.csv/.pdf file it links under /uploads/.
"""
import re
import sys
import urllib.request
from pathlib import Path

PAGE = "https://ppac.gov.in/retail-selling-price-rsp-of-petrol-diesel-and-domestic-lpg/rsp-of-petrol-and-diesel-in-metro-cities-since-16-6-2017"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline)"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    html = get(PAGE).decode("utf-8", "replace")
    (out / "ppac_metro_page.html").write_text(html)
    links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|pdf))"', html, re.I)))
    print(links)
    for href in links:
        url = href if href.startswith("http") else "https://ppac.gov.in/" + href.lstrip("/")
        if "uploads" not in url:
            continue
        try:
            (out / url.rsplit("/", 1)[-1]).write_bytes(get(url))
            print("saved", url)
        except Exception as e:  # noqa: BLE001
            print("failed", url, e)


if __name__ == "__main__":
    main(*sys.argv[1:])
