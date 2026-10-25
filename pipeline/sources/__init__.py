"""Registry of data sources. Each module exposes NAME, DESCRIPTION and update(**opts) -> dict.

update() returns {"updated": bool, "code": release code, "summary": str, "warnings": [...]}
and raises core.common.CheckFailed if the new data fails its checks (nothing is written then).
"""
SOURCES = [
    "jp_gdp_esri",
    "jp_cpi_estat",
]
