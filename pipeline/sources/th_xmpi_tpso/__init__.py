"""Thailand export and import prices: TPSO Export and Import Price Indices, 2012 = 100 (base year BE 2555),
Open API family Imex (types EXI, IMI).

As published, nothing calculated: index, y/y and m/m for all items and the main groups, January 2000 on.
Released around the 28th of the following month.
"""
from core import tpso_prices
from core.common import DATA, RAW

NAME = "th_xmpi_tpso"
DESCRIPTION = "Thailand export and import prices (TPSO, 2012 = 100)"
EXI = [("000", "export", "Export prices, all items"), ("100", "x_agri", "Agricultural products"),
       ("200", "x_agroindustry", "Agro-industrial products"), ("300", "x_industry", "Manufactured products"),
       ("400", "x_mineral_fuel", "Mineral and fuel products")]
IMI = [("000", "import", "Import prices, all items"), ("100", "m_fuel", "Fuel"), ("200", "m_capital", "Capital goods"),
       ("300", "m_intermediate", "Raw materials and intermediate goods"), ("400", "m_consumer", "Consumer goods"),
       ("500", "m_vehicles", "Vehicles and transport equipment")]
SPEC = {
    "family": "Imex",
    "types": {"EXI": (2555, "2000-01"), "IMI": (2555, "2000-01")},
    "codes": {"EXI": EXI, "IMI": IMI},
    "out": DATA / "th" / "xmpi", "rawdir": RAW / "th" / "xmpi_tpso", "stem": "th_xmpi", "indicator": "xmpi",
    "base_label": "index, 2012 = 100",
    "need": [("EXI", "000"), ("IMI", "000")],
    "check_from": "2013-01",
    "table": "TPSO Open API: Imex, types EXI and IMI, base 2012 (BE 2555)",
}


def update(force=False, **_):
    return tpso_prices.run(SPEC, force=force)
