"""Registry of data sources. Each module exposes NAME, DESCRIPTION and update(**opts) -> dict.

update() returns {"updated": bool, "code": release code, "summary": str, "warnings": [...]}
and raises core.common.CheckFailed if the new data fails its checks (nothing is written then).
"""
SOURCES = [
    "jp_gdp_esri",
    "jp_cpi_estat",
    "jp_ppi_boj",
    "jp_cpi_contrib_estat",
    "jp_cpi_core3_estat",
    "in_cpi_mospi",
    "in_cpi_imf",
    "in_cpi_core",
    "in_ppi_oea",
    "sg_cpi_singstat",
    "sg_ppi_singstat",
    "kr_cpi_ecos",
    "kr_ppi_ecos",
    "ph_cpi_psa",
    "ph_ppi_psa",
]
