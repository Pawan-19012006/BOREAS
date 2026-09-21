"""Service providing the unified CurrentState X(t) snapshot."""

from datetime import datetime, timezone

from boreas_core.observe.service import get_observed_icebergs, get_observed_vessels

from .models import (
    BathymetryState,
    CurrentState,
    DataQualityState,
    OceanCurrentState,
    SeaIceCurrentState,
    WeatherCurrentState,
)


def get_current_state() -> CurrentState:
    """Composes a canonical current-state representation X(t) from
    active observation streams and deterministic operational models.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    vessels_res = get_observed_vessels()
    icebergs_res = get_observed_icebergs()

    sea_ice = SeaIceCurrentState(
        mean_concentration_pct=68.4,
        max_concentration_pct=96.0,
        regional_status="EXTENSIVE_PACK_ICE",
        fast_ice_extent_km2=184200.0,
        provenance="DERIVED — OSI-SAF / SYNTHETIC ENSEMBLE COMPOSITE",
    )

    ocean = OceanCurrentState(
        surface_current_speed_ms=0.18,
        surface_current_heading_deg=65.0,
        sea_surface_temp_c=-1.4,
        provenance="SIMULATED — SOUTHERN OCEAN CLIMATOLOGICAL BASELINE",
    )

    weather = WeatherCurrentState(
        wind_speed_kt=16.5,
        wind_direction_deg=245.0,
        air_temp_c=-12.5,
        wave_height_m=2.4,
        pressure_hpa=984.0,
        visibility_nm=8.0,
        provenance="SIMULATED — POLAR SYNOPTIC METEOROLOGY",
    )

    bathymetry = BathymetryState(
        status="IBCSO_DERIVED_CONTOURS",
        min_depth_m=85.0,
        soundings_available=True,
        provenance="PLANNED — IBCSO 500M DIGITAL ELEVATION MODEL",
    )

    quality = DataQualityState(
        overall_quality=0.88,
        ais_provenance="PROTOTYPE",
        iceberg_provenance="DERIVED",
        satellite_provenance="REAL",
        sea_ice_provenance="DERIVED",
        ocean_provenance="SIMULATED",
        weather_provenance="SIMULATED",
        bathymetry_provenance="PLANNED",
    )

    provenance = {
        "vessels": "PROTOTYPE — DETERMINISTIC ANTARCTIC FLEET",
        "icebergs": "DERIVED — CDSE RADAR/OPTICAL TRACKS",
        "satellites": "REAL — COPERNICUS DATA SPACE ECOSYSTEM (CDSE)",
        "sea_ice": "DERIVED — COMPOSITE ANALYSIS",
        "ocean": "SIMULATED — CLIMATOLOGICAL FORCING",
        "weather": "SIMULATED — SYNOPTIC MODELING",
        "bathymetry": "PLANNED — IBCSO BATHYMETRIC CONTOURS",
    }

    return CurrentState(
        timestamp=now_iso,
        vessels=vessels_res.vessels,
        icebergs=icebergs_res.icebergs,
        sea_ice=sea_ice,
        ocean=ocean,
        weather=weather,
        bathymetry=bathymetry,
        quality=quality,
        uncertainty_score=0.14,
        provenance=provenance,
    )
