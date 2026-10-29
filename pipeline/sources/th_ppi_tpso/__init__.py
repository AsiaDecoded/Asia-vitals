"""Thailand producer prices: TPSO Producer Price Index, 2021 = 100 (base year BE 2564), Open API family Ppi.

As published, nothing calculated: index, y/y and m/m for
  - CPA (by product of economic activity): all items, agriculture and fishery, mining, manufacturing and the
    manufacturing groups, January 2015 on (TPSO's 2021-base series starts there; y/y from January 2016);
  - SOP (by stage of processing): finished goods, intermediate (processed) goods, raw materials and their
    subgroups, January 1995 on (TPSO's 2021-base series linked back).
Released with the CPI, around the 5th-7th of the following month.
"""
from core import tpso_prices
from core.common import DATA, RAW

NAME = "th_ppi_tpso"
DESCRIPTION = "Thailand producer prices (TPSO PPI, 2021 = 100): CPA and stage of processing"
CPA = [
    ("0000", "ppi", "PPI, all items"), ("1000", "agri", "Agriculture and fishery products"),
    ("1010", "agri_crops", "Agricultural products"), ("1030", "fishery", "Fishery products"),
    ("2000", "mining", "Mining products"), ("2050", "coal", "Coal and lignite"),
    ("2060", "crude_gas", "Crude petroleum and natural gas"), ("2070", "metal_ores", "Metal ores"),
    ("2080", "other_mining", "Other mining products"),
    ("3000", "manufacturing", "Manufactured products"), ("3100", "m_food", "Food products"),
    ("3110", "m_beverages", "Beverages"), ("3120", "m_tobacco", "Tobacco products"), ("3130", "m_textiles", "Textiles"),
    ("3140", "m_apparel", "Wearing apparel"), ("3150", "m_leather", "Leather and related products"),
    ("3160", "m_wood", "Wood and wood products"), ("3170", "m_paper", "Paper and paper products"),
    ("3180", "m_printing", "Printing and recorded media"), ("3190", "m_refined", "Refined petroleum products"),
    ("3200", "m_chemicals", "Chemicals and chemical products"), ("3210", "m_pharma", "Pharmaceutical products"),
    ("3220", "m_rubber_plastic", "Rubber and plastic products"),
    ("3230", "m_nonmetallic", "Other non-metallic mineral products"), ("3240", "m_basic_metals", "Basic metals"),
    ("3250", "m_fabricated_metal", "Fabricated metal products"),
    ("3260", "m_electronics", "Computer and electronic products"), ("3270", "m_electrical", "Electrical equipment"),
    ("3280", "m_machinery", "Machinery and equipment"), ("3290", "m_vehicles", "Motor vehicles, parts and accessories"),
    ("3300", "m_motorcycles", "Motorcycles, bicycles and parts"), ("3310", "m_furniture", "Furniture"),
    ("3320", "m_other", "Other manufactured products"),
]
SOP = [
    ("1000", "finished", "Finished goods"), ("1100", "consumer", "Consumer goods"), ("1200", "capital", "Capital goods"),
    ("2000", "intermediate", "Intermediate (processed) goods"),
    ("2100", "intermediate_industry", "Intermediate goods for industry"),
    ("2200", "intermediate_construction", "Intermediate goods for construction"),
    ("3000", "raw", "Raw materials"), ("3100", "raw_food", "Raw materials for food"),
    ("3200", "raw_nonfood", "Raw materials, non-food"),
]
SPEC = {
    "family": "Ppi",
    "types": {"CPA": (2564, "2015-01"), "SOP": (2564, "1995-01")},
    "codes": {"CPA": CPA, "SOP": SOP},
    "out": DATA / "th" / "ppi", "rawdir": RAW / "th" / "ppi_tpso", "stem": "th_ppi", "indicator": "ppi",
    "base_label": "index, 2021 = 100",
    "need": [("CPA", "0000"), ("CPA", "1000"), ("CPA", "2000"), ("CPA", "3000"),
             ("SOP", "1000"), ("SOP", "2000"), ("SOP", "3000")],
    "check_from": "2022-01",
    "table": "TPSO Open API: Ppi, types CPA and SOP, base 2021 (BE 2564)",
}


def update(force=False, **_):
    return tpso_prices.run(SPEC, force=force)
