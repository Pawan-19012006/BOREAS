"""Per-source connectivity status for satellite tile sources that require
real credentials (Copernicus Data Space Ecosystem for Sentinel-1/2,
Copernicus Marine Toolbox for the Marine tile). NASA Worldview/GIBS is
keyless and always connected -- it isn't part of this check.

Note on exact endpoint syntax (CDSE OAuth2 token URL, OData query shape,
Copernicus Marine Toolbox invocation): this module only checks whether the
relevant credentials are *configured*, not whether they're valid -- actually
fetching real imagery is future work, wired up once real credentials exist.
The env var names below (`CDSE_CLIENT_ID`/`CDSE_CLIENT_SECRET`,
`COPERNICUSMARINE_SERVICE_USERNAME`/`COPERNICUSMARINE_SERVICE_PASSWORD`) are
believed correct per each service's current documentation but not
independently exercised against a live call in this codebase -- verify
against current docs before wiring up a real fetch.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceStatus:
    connected: bool
    reason: str


def _cdse_status() -> SourceStatus:
    if os.environ.get("CDSE_CLIENT_ID") and os.environ.get("CDSE_CLIENT_SECRET"):
        return SourceStatus(connected=True, reason="Copernicus Data Space Ecosystem credentials configured")
    return SourceStatus(
        connected=False,
        reason="CDSE_CLIENT_ID / CDSE_CLIENT_SECRET not configured (see .env.example)",
    )


def _copernicus_marine_status() -> SourceStatus:
    if os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"):
        return SourceStatus(connected=True, reason="Copernicus Marine Toolbox credentials configured")
    return SourceStatus(
        connected=False,
        reason=(
            "COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD "
            "not configured (see .env.example)"
        ),
    )


def get_all_statuses() -> dict[str, SourceStatus]:
    cdse = _cdse_status()
    return {
        "sentinel-1": cdse,
        "sentinel-2": cdse,
        "copernicus-marine": _copernicus_marine_status(),
    }
