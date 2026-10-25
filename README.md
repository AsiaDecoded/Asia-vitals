# Asia Vitals

Data pipeline for Asia Decoded's macro dashboard. Starts with Japan GDP from the Cabinet Office (ESRI) Quarterly Estimates.

## How it updates

1. **GitHub Actions** (`.github/workflows/esri-gdp.yml`) runs in ESRI's release windows. It works out the next release from `data/release.json` (first preliminary → second preliminary → next quarter), downloads ESRI's 15 CSV tables, parses them, runs the checks and commits the result.
2. **A scheduled task in Claude** picks up the commit and uploads `data/jp_gdp.csv` and `data/release.json` to the dashboard.

If any check fails, nothing is committed and GitHub emails the repository owner about the failed run.

## Layout

| Path | Contents |
|---|---|
| `pipeline/esri.py` | Release codes, URLs, CSV parser (CP932, columns matched by English header) |
| `pipeline/checks.py` | Consistency checks run before anything is written |
| `pipeline/build.py` | Combined CSV and per-chart JSON |
| `pipeline/run.py` | Entry point |
| `raw/esri/<release>/` | ESRI's original CSVs for every release processed, unchanged |
| `data/jp_gdp.csv` | One row per quarter per component, all measures (the dashboard's dataset) |
| `data/json/*.json` | One file per chart: metadata, columns, data, latest values |
| `data/release.json` | Current release, processing time, warnings, history |

## Checks

Errors stop the run: missing tables or columns; latest quarter not the release's quarter; q/q, annualised q/q and y/y not matching the levels (±0.06pp); contributions not summing to GDP; deflator index not matching nominal ÷ real.

Warnings are recorded but don't stop it: real GDP levels revised by more than 2% against the previous release (expected with annual and benchmark revisions).

## Running by hand

```
python -I pipeline/run.py                                              # check for a new release
python -I pipeline/run.py --code qe262_2 --from-dir raw/esri/qe262_2   # rebuild from saved files
```

Or run the workflow from the Actions tab ("Run workflow").

## Tables used (Section I, expenditure side)

`gaku-jk/mk` levels SA · `gaku-jg/mg` levels original · `ritu-jk/mk` q/q · `nritu-jk/mk` q/q annualised · `ritu-jg/mg` y/y · `kiyo-jk/jg` contributions · `def-qk` deflator index · `rdef-qk/qg` deflator change.

Source: Cabinet Office of Japan, Economic and Social Research Institute.
