"""Pydantic models for the BOREAS Prediction Subsystem."""

from pydantic import BaseModel, Field

from boreas_core.observe.models import ObservedIceberg, ObservedVessel


class IcebergForecastPoint(BaseModel):
    horizon_hours: int = Field(..., ge=0, description="Lead time from analysis epoch in hours")
    timestamp: str = Field(..., description="Target ISO 8601 UTC timestamp")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Predicted latitude in degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Predicted longitude in degrees")
    drift_speed_kt: float = Field(..., ge=0.0, description="Predicted drift speed in knots")
    heading_deg: float = Field(..., ge=0.0, le=360.0, description="Predicted drift heading vector")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score decaying with horizon")
    uncertainty_radius_km: float = Field(..., ge=0.0, description="Radius of positional uncertainty envelope in km")


class IcebergForecast(BaseModel):
    iceberg_id: str = Field(..., description="Unique target identifier (e.g. 'A-23A', 'B-17')")
    iceberg_name: str = Field(..., description="Descriptive iceberg name")
    current_position: list[float] = Field(..., description="Starting [lon, lat] coordinate")
    forecast_points: list[IcebergForecastPoint] = Field(..., description="Trajectory points at future horizons")
    heading: float = Field(..., description="Current drift heading")
    drift_speed: float = Field(..., description="Current drift speed in knots")
    provenance: str = Field(
        default="DETERMINISTIC_PROTOTYPE — KINEMATIC DRIFT FORECAST",
        description="Truthful statement of model type and simulation basis",
    )


class SeaIceForecastResponse(BaseModel):
    horizon_hours: int = Field(..., ge=0, description="Lead time in hours")
    timestamp: str = Field(..., description="Target forecast ISO 8601 UTC timestamp")
    grid_lat: list[float] = Field(..., description="Grid latitude coordinates")
    grid_lon: list[float] = Field(..., description="Grid longitude coordinates")
    sic_values: list[list[float]] = Field(..., description="2D matrix of sea-ice concentration (0.0 to 1.0)")
    mean_concentration_pct: float = Field(..., description="Mean regional concentration percentage")
    max_concentration_pct: float = Field(..., description="Peak regional concentration percentage")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Forecast confidence score")
    provenance: str = Field(
        default="PROTOTYPE — DETERMINISTIC SPATIAL EVOLUTION",
        description="Truthful disclosure of sea ice forecasting method",
    )


class EnvironmentalForecastPoint(BaseModel):
    horizon_hours: int = Field(..., ge=0, description="Lead time in hours")
    timestamp: str = Field(..., description="Target forecast ISO 8601 UTC timestamp")
    wind_speed_kt: float = Field(..., ge=0.0, description="Surface wind speed in knots")
    wind_direction_deg: float = Field(..., ge=0.0, le=360.0, description="Surface wind direction in degrees")
    wave_height_m: float = Field(..., ge=0.0, description="Significant wave height in meters")
    air_temp_c: float = Field(..., description="2m air temperature in Celsius")
    surface_temp_c: float = Field(..., description="Sea surface temperature in Celsius")
    pressure_hpa: float = Field(..., description="Mean sea level pressure in hPa")
    visibility_nm: float = Field(..., ge=0.0, description="Surface visibility in nautical miles")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Forecast confidence score")
    provenance: str = Field(
        default="SIMULATED SYNOPTIC POLAR FORECAST",
        description="Truthful disclosure of meteorological basis",
    )


class EnvironmentalForecastResponse(BaseModel):
    forecasts: list[EnvironmentalForecastPoint] = Field(..., description="Environmental forecasts across horizons")
    current: EnvironmentalForecastPoint = Field(..., description="Baseline T+0 environmental state")
    provenance: str = Field(default="SIMULATED SYNOPTIC POLAR FORECAST")


class FutureStateResponse(BaseModel):
    horizon_hours: int = Field(..., description="Selected forecast horizon in hours")
    timestamp: str = Field(..., description="Forecast valid timestamp")
    vessels: list[ObservedVessel] = Field(..., description="Projected vessel states at T+h")
    icebergs: list[ObservedIceberg] = Field(..., description="Projected iceberg states at T+h")
    sea_ice: SeaIceForecastResponse = Field(..., description="Projected sea ice grid at T+h")
    environment: EnvironmentalForecastPoint = Field(..., description="Projected environmental state at T+h")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Fused state confidence score")
    provenance: dict[str, str] = Field(..., description="Provenance disclosures across domains")
