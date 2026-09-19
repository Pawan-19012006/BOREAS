"""Typed Pydantic models for BOREAS Level 01 OBSERVE intelligence."""

from typing import Literal
from pydantic import BaseModel, Field


class ObservedVessel(BaseModel):
    id: str = Field(..., description="Unique vessel identifier, e.g. 'vasiliy_golovnin'")
    name: str = Field(..., description="Display vessel name, e.g. 'MV Vasiliy Golovnin'")
    imo: str | None = Field(None, description="International Maritime Organization number")
    mmsi: str | None = Field(None, description="Maritime Mobile Service Identity number")
    vessel_type: str = Field(..., description="Vessel hull / service classification")
    ice_class: str = Field(..., description="Polar ice class rating (e.g. Arc7, PC3, PC5)")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Current latitude in degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Current longitude in degrees")
    heading_deg: float = Field(..., ge=0.0, le=360.0, description="Current true heading in degrees")
    speed_kt: float = Field(..., ge=0.0, description="Current speed through water or SOG in knots")
    destination: str = Field(..., description="Destination station, port, or survey area")
    eta: str = Field(..., description="Estimated time of arrival or status indicator")
    status: Literal["LIVE_AIS", "DEAD_RECKONING", "MOORED", "ICE_BOUND"] = Field(
        ..., description="Current operational tracking state"
    )
    callsign: str | None = Field(None, description="Radio callsign")
    flag: str = Field(..., description="Flag state of registration")
    track_history: list[list[float]] = Field(
        ..., description="Historical observed track points [lon, lat] ordered oldest to newest"
    )
    source: str = Field(
        ..., description="Data provenance label, e.g. 'PROTOTYPE AIS — ESTIMATED TRANSIT'"
    )


class VesselsObserveResponse(BaseModel):
    vessels: list[ObservedVessel] = Field(..., description="List of observed Antarctic vessels")
    total_count: int = Field(..., description="Total vessels in observation picture")
    active_count: int = Field(..., description="Number of currently underway/active vessels")
    provenance: str = Field(
        default="PROTOTYPE AIS — DETERMINISTIC ANTARCTIC FLEET",
        description="Truthful disclosure of data source and simulation level",
    )
    updated_at: str = Field(..., description="ISO 8601 timestamp of data snapshot")


class ObservedIceberg(BaseModel):
    id: str = Field(..., description="Target identifier (e.g. 'A-23A', 'D-28', 'B-17')")
    name: str = Field(..., description="Full descriptive name")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Estimated centroid latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Estimated centroid longitude")
    drift_speed_kt: float = Field(..., ge=0.0, description="Current drift velocity in knots")
    heading_deg: float = Field(..., ge=0.0, le=360.0, description="Drift heading vector in degrees")
    length_m: float = Field(..., gt=0.0, description="Major axis length in meters")
    width_m: float = Field(..., gt=0.0, description="Minor axis width in meters")
    thickness_m: float = Field(..., gt=0.0, description="Total iceberg thickness (draft + freeboard)")
    area_km2: float = Field(..., gt=0.0, description="Surface area in square kilometers")
    risk_level: Literal["low", "guarded", "high", "critical"] = Field(
        ..., description="Navigation threat level"
    )
    origin: str = Field(..., description="Calving origin ice shelf or glacier tongue")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Tracking confidence index based on sensor age & resolution"
    )
    track_history: list[list[float]] = Field(
        ..., description="Historical drift trajectory points [lon, lat] oldest to newest"
    )
    detection_source: Literal["Sentinel-1", "Sentinel-2", "NIC Radar"] = Field(
        ..., description="Primary sensor used for detection and boundary extraction"
    )
    source: str = Field(
        ..., description="Data provenance label, e.g. 'SYNTHETIC RADAR TRACK — CDSE GROUNDED'"
    )


class IcebergsObserveResponse(BaseModel):
    icebergs: list[ObservedIceberg] = Field(..., description="Tracked iceberg targets")
    total_count: int = Field(..., description="Total tracked iceberg targets")
    provenance: str = Field(
        default="SYNTHETIC RADAR/OPTICAL TRACKS — DETERMINISTIC RECON",
        description="Truthful disclosure of data source and simulation level",
    )
    updated_at: str = Field(..., description="ISO 8601 timestamp of data snapshot")
