# China's import growth, Jan-Sep 2026

Decomposition of China's US$ import growth, Jan-Sep 2026 against Jan-Sep 2025, from GACC's monthly bulletin
(english.customs.gov.cn), cached in raw/trade/cn/store.json.gz. Calculated for this analysis; not part of the pipeline.

- Levels: each year's September page, year-to-date column. Where GACC's 2025 cell overflows (#####), the sum of the
  nine monthly figures (tables 4 and 14) or the 2026 level divided by (1 + GACC's published year-to-date change) (table 2).
- GACC's printed changes: tables (2) and (4) print year-to-date changes; table (14) prints the change for the single
  month, although its header does not say so (beef, Sep 2026: 915.6 vs 1,740.3 US$ mn = -47.4%, the printed figure).
  Growth here is computed from levels; GACC's own year-to-date changes use a revised 2025 base and differ by up to a few
  tenths of a point (Hong Kong 109.3% printed vs 108.2%; ships, HS89, differ more).
- Contribution (pp) = change / total Jan-Sep 2025 imports (US$ 1,904.7 bn) x 100.
- Price and volume (table 14 lines with quantities): volume effect = (Q2026/Q2025 - 1) x V2025; unit-value effect =
  change in value - volume effect. Unit values mix price and composition (chips are counted per piece, computer parts
  per tonne). Quantities converted to one unit where GACC changed the unit between years (noted in unit_note).

Files: products_2026_09.csv (partner, HS section/chapter, table 14 lines), partners_all_2026_09.csv (every partner in
table 2), decomp.py, partners.py (paths are absolute to this clone; run from pipeline/ context).
