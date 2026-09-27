"""BOREAS Prediction Subsystem.

Provides trajectory forecasting, spatial sea-ice evolution, environmental
projections, and the Unified Future State X(t+h).
"""

from .environment import EnvironmentalForecastEngine
from .iceberg import IcebergTrajectoryEngine
from .models import (
    EnvironmentalForecastPoint,
    EnvironmentalForecastResponse,
    FutureStateResponse,
    IcebergForecast,
    IcebergForecastPoint,
    SeaIceForecastResponse,
    WeatherHotspot,
    WeatherHotspotResponse,
)
from .sea_ice import SeaIceForecastEngine
from .service import (
    get_environmental_forecast,
    get_future_state,
    get_iceberg_forecasts,
    get_sea_ice_forecast,
    get_weather_hotspots,
)

__all__ = [
    "EnvironmentalForecastEngine",
    "EnvironmentalForecastPoint",
    "EnvironmentalForecastResponse",
    "FutureStateResponse",
    "IcebergForecast",
    "IcebergForecastPoint",
    "IcebergTrajectoryEngine",
    "SeaIceForecastEngine",
    "SeaIceForecastResponse",
    "WeatherHotspot",
    "WeatherHotspotResponse",
    "get_environmental_forecast",
    "get_future_state",
    "get_iceberg_forecasts",
    "get_sea_ice_forecast",
    "get_weather_hotspots",
]
