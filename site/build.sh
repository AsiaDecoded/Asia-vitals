#!/usr/bin/env bash
# Builds the public site into public/: the page files plus the latest data the pipeline committed.
# Cloudflare Pages: build command "bash site/build.sh", output directory "public".
set -euo pipefail
rm -rf public && mkdir -p public/sg/data
cp site/sg/index.html site/sg/cpi.js site/sg/export.js site/sg/shim.js public/sg/
cp data/sg/cpi/sg_cpi.csv data/sg/cpi/sg_cpi_series_weights.csv data/sg/cpi/sg_cpi_contrib.csv data/sg/cpi/sg_cpi_diffusion.csv data/sg/cpi/sg_cpi_items.csv public/sg/data/
cp data/sg/ppi/sg_ppi.csv public/sg/data/
cp data/sg/cpi/release_row.json public/sg/data/cpi_release.json
cp data/sg/ppi/release_row.json public/sg/data/ppi_release.json
# root goes to the Singapore page for now
cat > public/index.html <<'HTML'
<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=sg/"><title>Asia Decoded</title><a href="sg/">Singapore</a>
HTML
cat > public/_headers <<'HDR'
/sg/data/*
  Cache-Control: public, max-age=600
HDR
echo "built public/"
