"""Probe: daily history for the SET (Thailand) and PSEi (Philippines) from sites other than Yahoo Finance.
Writes discovery/eq_probe/report.txt and the first bytes of each response."""
import json, urllib.request, urllib.error, ssl, time
from pathlib import Path

OUT = Path("discovery/eq_probe"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "text/csv,application/json,text/html;q=0.9,*/*;q=0.8"}
C = [
  ("wsj_set", "https://www.wsj.com/market-data/quotes/index/TH/SET/historical-prices/download?num_rows=100000&range_days=100000&startDate=01/01/1990&endDate=11/05/2026"),
  ("wsj_psei", "https://www.wsj.com/market-data/quotes/index/PH/PSEI/historical-prices/download?num_rows=100000&range_days=100000&startDate=01/01/1990&endDate=11/05/2026"),
  ("mw_set", "https://www.marketwatch.com/investing/index/set/downloaddatapartial?startdate=01/01/2024%2000:00:00&enddate=11/05/2026%2000:00:00&daterange=d30&frequency=p1d&csvdownload=true&downloadpartial=false&newdates=false&countrycode=th"),
  ("mw_psei", "https://www.marketwatch.com/investing/index/psei/downloaddatapartial?startdate=01/01/2024%2000:00:00&enddate=11/05/2026%2000:00:00&daterange=d30&frequency=p1d&csvdownload=true&downloadpartial=false&newdates=false&countrycode=ph"),
  ("stooq_set", "https://stooq.com/q/d/l/?s=^set&i=d"),
  ("stooq_psei", "https://stooq.com/q/d/l/?s=^psei&i=d"),
  ("stooq_set_th", "https://stooq.com/q/d/l/?s=set.th&i=d"),
  ("inv_set", "https://api.investing.com/api/financialdata/historical/38690?start-date=2024-01-01&end-date=2026-11-05&time-frame=Daily&add-missing-rows=false"),
  ("inv_psei", "https://api.investing.com/api/financialdata/historical/38691?start-date=2024-01-01&end-date=2026-11-05&time-frame=Daily&add-missing-rows=false"),
  ("set_or_th", "https://www.set.or.th/api/set/index/SET/chart-quotation?period=5Y&accumulated=false"),
  ("pse_chart", "https://edge.pse.com.ph/common/DisclosureCht.ax"),
  ("yahoo_chart_set", "https://query1.finance.yahoo.com/v8/finance/chart/%5ESET.BK?period1=631152000&period2=1793000000&interval=1d"),
  ("yahoo_chart_psei", "https://query1.finance.yahoo.com/v8/finance/chart/PSEI.PS?period1=631152000&period2=1793000000&interval=1d"),
  ("cnbc_set", "https://ts-api.cnbc.com/harmony/app/charts/ALL.json?symbol=.SETI"),
  ("cnbc_psei", "https://ts-api.cnbc.com/harmony/app/charts/ALL.json?symbol=.PSI"),
  ("ft_set", "https://markets.ft.com/data/indices/tearsheet/historical?s=SET:SET"),
]
lines = []
for name, url in C:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
            lines.append(f"{name}: HTTP {r.status} {len(body)} bytes {r.headers.get('Content-Type')}")
            (OUT / f"{name}.txt").write_bytes(body[:4000])
    except urllib.error.HTTPError as e:
        lines.append(f"{name}: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"{name}: {type(e).__name__}: {str(e)[:150]}")
    time.sleep(1)
(OUT / "report.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
