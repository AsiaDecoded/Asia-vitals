# Asia Vitals

Data pipeline for Asia Decoded's macro dashboards: GDP, inflation and trade for 12 Asian economies. Currently: Japan GDP, CPI, CPI contributions and PPI; India CPI (headline, core 1 and 2, and a long series from the IMF).

## How it updates

1. **GitHub Actions** (`.github/workflows/update.yml`) runs every source twice a day (00:15 and 03:15 UTC). Each source fetches its data, runs its checks and writes only if there is something new that passes. A failing source writes nothing and doesn't block the others.
2. After every run, `run_report.txt` (what each source did, and why any failed) is pushed to the **run-reports** branch.
3. **A scheduled task in Claude** copies new data into the Claude dashboards and reports failures.

## Sources

| Source | Module | Data | New data detected by |
|---|---|---|---|
| Japan GDP, Cabinet Office (ESRI) | `sources/jp_gdp_esri` | Quarterly, 1994–; 15 CSV tables | Next release code (qe262_2 → qe263 → …) appearing on ESRI's site |
| Japan CPI, Statistics Bureau | `sources/jp_cpi_estat` | Monthly, 1970–; national and Tokyo; e-Stat API table 0004052037 (2025 base) | Any change in the data (new month, Tokyo early release, revisions) |
| Japan CPI contributions, Statistics Bureau | `sources/jp_cpi_contrib_estat` | Monthly, Jul 2016–; national contributions to y/y (services, goods, fresh food, energy) from Table 5 of each monthly report (Excel files found through the e-Stat file catalogue), as published on the base then in use | A new month's Table 5 in the catalogue (C2026-09 → C2026-10) |
| Japan PPI, Bank of Japan | `sources/jp_ppi_boj` | Monthly, 1960–; producer, export and import prices (CGPI, 2020 base); BoJ API database PR01, no key | Any change in the data; new month gives a new code (M2026-09 → M2026-10) |
| India CPI, MoSPI | `sources/in_cpi_mospi` | Monthly, spliced index Jan 2011– (2024 = 100) and y/y Jan 2012–, all-India, rural/urban/combined: 2024 base from Jan 2025, MoSPI's 2024-base back series 2013–2024, 2010 base 2011–2012 linked by Asia Decoded (annual geometric-mean ratio, 2013 overlap). y/y calculated from the spliced index; MoSPI's published rates kept as yoy_published; MoSPI API, no key | Checked only once the next month is due (MoSPI releases on the 12th), then daily until it appears; a new month gives a new code (M2026-09 → M2026-10) and refreshes the full history, picking up revisions |
| India CPI, long series, IMF | `sources/in_cpi_imf` | Monthly Jan 1957– and annual 1957–; all items, 2024 = 100, and the IMF's y/y rates, as published in the IMF Consumer Price Index dataset (formerly IFS; IMF.STA:CPI IND.CPI._T.IX.M/A, YOY_PCH_PA_PT.M/A); IMF joins India's indices at overlaps; no key | Any change in the data; new month gives a new code |
| India core CPI (calculated) | `sources/in_cpi_core` | Monthly, linked index Jan 2014–, y/y Jan 2015– (gaps Mar–May 2020 and 2021); all-India combined; RBI definitions. 2024 base (Jan 2025–): weighted average of MoSPI item indices with Annex 5.3d weights (core 1 excl. food and beverages, group 04.5 and class 07.2.2; core 2 also excl. gold and silver jewellery). 2012 base (2014–2025): residual of the published headline after removing food and beverages, fuel and light, petrol, diesel (and gold, silver), MoSPI 2012 weights, fixed inputs in raw/in/cpi_core/core2012_inputs.json (built by `tools/mospi_core2012_inputs.py`). Linked over 2025 (geometric-mean ratio); y/y from the linked index | Runs only when the MoSPI headline data changes (it pages through every item) |
| India CPI contributions (calculated) | `sources/in_cpi_core` (in_cpi_contrib.csv) | Monthly, Jan 2015–: contributions (pp) of food, fuel and CPI excluding food and fuel to CPI y/y, within the 2012 base to Dec 2025 (food = Consumer Food Price Index, weight 39.06; fuel = fuel and light + petrol + diesel) and the 2024 base from Jan 2026 (food = group 01.1 Food; fuel = group 04.5 + class 07.2.2); ex food and fuel is the residual (so it includes beverages, and on the 2012 base prepared meals), so the three sum to CPI y/y on each base | With in_cpi_core |

The e-Stat API needs the repository secret `ESTAT_APP_ID`. The Excel readers (openpyxl, xlrd) are installed by the workflow.

## Layout

| Path | Contents |
|---|---|
| `pipeline/run.py` | Runs all sources (or those named), writes the run report and `data/all_long.csv` |
| `pipeline/sources/` | One module per source; registry in `sources/__init__.py` |
| `pipeline/core/` | Shared: long format, release files, e-Stat and BoJ clients |
| `pipeline/tools/estat_discover.py` | Lists e-Stat tables and their codes (manual workflow `estat-discover.yml`) |
| `pipeline/tools/estat_catalog.py`, `estat_files.py` | Search e-Stat's file catalogue and download sample files (manual workflow `estat-discover.yml`) |
| `pipeline/tools/boj_discover.py` | Lists BoJ series codes (manual workflow `boj-discover.yml`) |
| `pipeline/tools/mospi_discover.py` | Probes MoSPI's CPI and WPI API (workflow `mospi-discover.yml`) |
| `raw/<country>/<source>/` | Original files for every release processed, unchanged (CPI: compressed API response) |
| `data/<country>/<indicator>/` | `<country>_<indicator>.csv` (dashboard format), `long.csv` (common format), `json/` (per chart), `release.json`, `release_row.json` |
| `data/all_long.csv` | Every source's long file stacked: the input for cross-country views |

**Common long format:** `country, indicator, series, label, measure, area, freq, date, value, unit, source, release`.

## Checks (errors stop that source)

- **GDP:** all tables and columns present; latest quarter matches the release; q/q, annualised q/q and y/y match the levels; contributions sum to GDP; deflator matches nominal ÷ real. Warning if past levels are revised by more than 2%.
- **CPI:** required series present for the latest national and Tokyo months; months never go backwards; published m/m and y/y match the index where both months are on the 2025 base (earlier rates are the officially published ones from older bases); index levels plausible.
- **PPI:** PPI, export and import (yen) index and y/y present for the latest month; months never go backwards; published y/y matches the index where both months are on the 2020 base; index levels plausible. A revision without a new month is noted as a warning.
- **India CPI:** spliced index present every month from Jan 2011, y/y from Jan 2012, for all three sectors; 2010-base link factor in range; each part where it should be; calculated y/y within 0.15pp of MoSPI's published rate from Jan 2026, and never more than 1.5pp from it before.
- **India CPI, IMF:** one monthly and one annual series, reference period 2024 = 100; no gaps from the first month or year to the latest; months never go backwards; 2024 annual within 1 of 100; IMF y/y within 0.05pp of its own index; warning if any month from Jan 2025 differs from MoSPI's combined CPI by more than 0.02.
- **India core CPI:** 2012-base y/y for 2025 within 0.06pp of the RBI's published Table IV.1 (MPR April 2026); full 2025 overlap for the link; all 358 items present for every month and matching the weights file; weights sum to 100; weighted items reproduce MoSPI's published general index within 0.02 every month.
- **CPI contributions:** all items, fresh food, energy, goods and services found in every month's file; goods + services within 0.1pp of all items; all items within ±15.

## Adding a source

Add a module under `pipeline/sources/` with `update(**opts)` returning `{"updated", "code", "summary", "warnings"}` (raise `CheckFailed` on bad data), write `data/<country>/<indicator>/` including `long.csv`, and add its name to `SOURCES`.

## Running by hand

```
python -I pipeline/run.py                         # all sources
python -I pipeline/run.py jp_cpi_estat            # one source (needs ESTAT_APP_ID)
python -I pipeline/run.py jp_gdp_esri --code qe262_2 --from-dir raw/jp/gdp_esri/qe262_2
```

Or from the Actions tab: "Update data" → Run workflow (optionally push to a test branch).
