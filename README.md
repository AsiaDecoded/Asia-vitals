# Asia Vitals

Data pipeline for Asia Decoded's macro dashboards: GDP, inflation and trade for 12 Asian economies. Currently: Japan GDP, CPI, CPI contributions and PPI.

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
| `raw/<country>/<source>/` | Original files for every release processed, unchanged (CPI: compressed API response) |
| `data/<country>/<indicator>/` | `<country>_<indicator>.csv` (dashboard format), `long.csv` (common format), `json/` (per chart), `release.json`, `release_row.json` |
| `data/all_long.csv` | Every source's long file stacked: the input for cross-country views |

**Common long format:** `country, indicator, series, label, measure, area, freq, date, value, unit, source, release`.

## Checks (errors stop that source)

- **GDP:** all tables and columns present; latest quarter matches the release; q/q, annualised q/q and y/y match the levels; contributions sum to GDP; deflator matches nominal ÷ real. Warning if past levels are revised by more than 2%.
- **CPI:** required series present for the latest national and Tokyo months; months never go backwards; published m/m and y/y match the index where both months are on the 2025 base (earlier rates are the officially published ones from older bases); index levels plausible.
- **PPI:** PPI, export and import (yen) index and y/y present for the latest month; months never go backwards; published y/y matches the index where both months are on the 2020 base; index levels plausible. A revision without a new month is noted as a warning.
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
