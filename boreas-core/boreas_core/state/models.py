"""Pydantic models for BOREAS Unified Current State X(t)."""

from typing import Literal
from pydantic import BaseModel, Field

from boreas_core.observe.models import ObservedIceberg, ObservedVessel

ProvenanceTag = Literal["REAL", "DERIVED", "PROTOTYPE", "SIMULATED", "PLANNED"]


class DataQualityState(BaseModel):
    overall_quality: float = Field(..., ge=0.0, le=1.0, description="Normalized data quality score")
    ais_provenance: ProvenanceTag = Field("PROTOTYPE", description="AIS feed provenance")
    iceberg_provenance: ProvenanceTag = Field("DERIVED", description="Iceberg tracking provenance")
    satellite_provenance: ProvenanceTag = Field("REAL", description="CDSE Earth observation status")
    sea_ice_provenance: ProvenanceTag = Field("DERIVED", description="Sea ice analysis provenance")
    ocean_provenance: ProvenanceTag = Field("SIMULATED", description="Ocean current forcing provenance")
    weather_provenance: ProvenanceTag = Field("SIMULATED", description="Atmospheric forcing provenance")
    bathymetry_provenance: ProvenanceTag = Field("PLANNED", description="Bathymetry grid provenance")


class SeaIceCurrentState(BaseModel):
    mean_concentration_pct: float = Field(..., ge=0.0, le=100.0, description="Regional mean concentration")
    max_concentration_pct: float = Field(..., ge=0.0, le=100.0, description="Maximum observed concentration")
    regional_status: str = Field(..., description="Operational sea-ice regime label")
    fast_ice_extent_km2: float = Field(..., ge=0.0, description="Estimated fast-ice surface area in km²")
    provenance: str = Field(
        default="DERIVED — OSI-SAF / SYNTHETIC ENSEMBLE COMPOSITE",
        description="Data provenance statement",
    )


class OceanCurrentState(BaseModel):
    surface_current_speed_ms: float = Field(..., ge=0.0, description="Mean surface current speed in m/s")
    surface_current_heading_deg: float = Field(..., ge=0.0, le=360.0, description="Current flow direction")
    sea_surface_temp_c: float = Field(..., description="Mean polar sea surface temperature in Celsius")
    provenance: str = Field(
        default="SIMULATED — SOUTHERN OCEAN CLIMATOLOGICAL BASELINE",
        description="Data provenance statement",
    )


class WeatherCurrentState(BaseModel):
    wind_speed_kt: float = Field(..., ge=0.0, description="10m wind speed in knots")
    wind_direction_deg: float = Field(..., ge=0.0, le=360.0, description="10m wind direction in degrees")
    air_temp_c: float = Field(..., description="2m air temperature in Celsius")
    wave_height_m: float = Field(..., ge=0.0, description="Significant wave height in meters")
    pressure_hpa: float = Field(..., description="Mean sea level atmospheric pressure in hPa")
    visibility_nm: float = Field(..., ge=0.0, description="Surface visibility in nautical miles")
    provenance: str = Field(
        default="SIMULATED — POLAR SYNOPTIC METEOROLOGY",
        description="Data provenance statement",
    )


class BathymetryState(BaseModel):
    status: str = Field(..., description="Bathymetric service status")
    min_depth_m: float = Field(..., description="Minimum regional depth in meters")
    soundings_available: bool = Field(..., description="Whether sounding contours are loaded")
    provenance: str = Field(
        default="PLANNED — IBCSO 500M SEABED TOPOGRAPHY",
        description="Data provenance statement",
    )


class CurrentState(BaseModel):
    timestamp: str = Field(..., description="Current UTC timestamp of the state snapshot")
    vessels: list[ObservedVessel] = Field(..., description="All observed Antarctic vessels")
    icebergs: list[ObservedIceberg] = Field(..., description="All tracked iceberg hazards")
    sea_ice: SeaIceCurrentState = Field(..., description="Current sea ice condition")
    ocean: OceanCurrentState = Field(..., description="Current ocean hydrodynamic state")
    weather: WeatherCurrentState = Field(..., description="Current atmospheric meteorological state")
    bathymetry: BathymetryState = Field(..., description="Current bathymetric terrain state")
    quality: DataQualityState = Field(..., description="Multi-sensor quality telemetry")
    uncertainty_score: float = Field(..., ge=0.0, le=1.0, description="Overall current-state epistemic uncertainty")
    provenance: dict[str, str] = Field(..., description="Component-level provenance disclosures")
