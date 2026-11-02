# Philippines dashboard (Claude Dashboard artifact): page source

Copy of the page files published to https://claude.ai/artifact/YS5Qj6cwWmovEVBZokaXxa (documents `files/index.html`, `files/gdp.js`, `files/cpi.js` and `files/export.js` in the artifact's database). The artifact is the live copy; this folder is a backup, refreshed when the page changes. Layout, styles, chart helpers (`window.JG`) and PNG export are the South Korea page's.

Datasets: `ph_cpi`, `ph_cpi_sa`, `ph_cpi_regions`, `ph_cpi_weights`, `ph_cpi_items` (from data/ph/cpi/), `ph_ppi` (data/ph/ppi/ph_ppi.csv), `cpi_release` and `ppi_release` (the release_row.json files). Every figure is as published by the PSA; the page's calcs only pick rows (latest months, tables).

GDP tab (first tab, 2 Nov 2026): `gdp.js`, Charts 1–6. Datasets `ph_gdp` (data/ph/gdp/ph_gdp_dash.csv), `ph_gdp_intl` (data/ph/gdp/ph_gdp_intl.csv), `asia_gni_pc` (central, data/asia/gni/asia_gni_pc.csv) and `gdp_release` (data/ph/gdp/release_row.json). Figures as published except the year-to-date real growth (calculated in ph_gdp_psa, flagged) and the CAGR labels on Charts 1–2 (calculated on the page).
