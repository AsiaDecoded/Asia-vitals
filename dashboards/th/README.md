# Thailand dashboard (Claude Dashboard artifact): page source

Copy of the page files published to https://claude.ai/artifact/PW44KETSq6qDxwY13hjkFb (documents `files/index.html`, `files/cpi.js`, `files/gdp.js` and `files/export.js` in the artifact's database). The artifact is the live copy; this folder is a backup, refreshed when the page changes. Layout, styles, chart helpers (`window.JG`) and PNG export are the Philippines page's.

Datasets: `th_cpi`, `th_cpi_items`, `th_cpi_weights`, `th_cpi_regions` (from data/th/cpi/), `th_ppi` (data/th/ppi/th_ppi.csv), `th_xmpi` (data/th/xmpi/th_xmpi.csv), `cpi_release`, `ppi_release` and `xmpi_release` (the release_row.json files). Every figure is as published by TPSO; the page's calcs only pick rows (latest months, tables). TPSO publishes no seasonally adjusted CPI, so the page has no SA m/m.

GDP tab (first tab, added 2 Nov 2026, `gdp.js`): Charts 1–6 as on the Vietnam page; headline tiles are placeholders. Datasets `th_gdp` (data/th/gdp/th_gdp_dash.csv, source th_gdp_nesdc), `th_gdp_intl` (data/th/gdp/th_gdp_intl.csv, source th_gdp_intl) and `asia_gni_pc` (central file data/asia/gni/asia_gni_pc.csv). Calculated: nominal y/y and the latest year to date (pipeline, flagged calculated = y), CAGR from 1987 (page calc `gdp_cagr`).
