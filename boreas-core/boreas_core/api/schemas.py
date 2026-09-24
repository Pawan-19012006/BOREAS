"""Pydantic request/response schemas for the BOREAS decision-support API."""

from pydantic import BaseModel, Field


class IcebergGeometryIn(BaseModel):
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    thickness_m: float = Field(gt=0)


class DriftForecastRequest(BaseModel):
    lon: float
    lat: float
    velocity_east_ms: float = 0.0
    velocity_north_ms: float = 0.0
    wind_east_ms: float
    wind_north_ms: float
    current_east_ms: float
    current_north_ms: float
    geometry: IcebergGeometryIn
    duration_hours: float = Field(default=72, gt=0, le=240)
    use_residual_correction: bool = True


class DriftForecastResponse(BaseModel):
    track: list[tuple[float, float]]
    final_velocity_ms: tuple[float, float]
    confidence: float
    ood_p_value: float
    degraded: bool
    rationale: str
    top_factors: list[tuple[str, float]]


class RoutePlanRequest(BaseModel):
    start_lon: float
    start_lat: float
    goal_lon: float
    goal_lat: float
    hazard_lon: list[float] = []
    hazard_lat: list[float] = []
    hazard_radius_km: list[float] = []
    # Used for every candidate's ETA and for mapping each leg to the real
    # forecast's lead step (see boreas_core/routing/scoring.py) -- both AI
    # routes have no vessel-performance model of their own, so a single
    # consistent speed assumption is what makes all candidates comparable.
    vessel_speed_kt: float = Field(default=12.0, gt=0)
    # PolarRoute's mesh-build-and-solve pipeline is CPU-bound, GIL-held
    # Python work that takes several seconds per call; useLiveMissionData's
    # 60s background poll (one call per fixed vessel route, just to draw
    # *a* route on the globe) doesn't need it and would otherwise queue
    # behind/ahead of a user's own "Plan Voyage" click, delaying it by tens
    # of seconds under concurrent load. Only the user-triggered voyage
    # planner needs the real dual-engine comparison.
    include_polar_route: bool = True


class RouteLegOut(BaseModel):
    start_lonlat: tuple[float, float]
    end_lonlat: tuple[float, float]
    bearing_deg: float | None
    compass_label: str | None
    distance_km: float


class RouteOptionOut(BaseModel):
    engine: str
    label: str
    recommended: bool
    path: list[tuple[float, float]]
    total_distance_km: float
    estimated_duration_hours: float
    max_risk_on_path: float
    rationale: str
    legs: list[RouteLegOut] = []


class RoutePlanResponse(BaseModel):
    options: list[RouteOptionOut]
    warnings: list[str] = []


class FusionRequest(BaseModel):
    global_model_mean: float = Field(ge=0, le=1)
    global_model_variance: float = Field(gt=0)
    latitude_deg: float
    month: int = Field(ge=1, le=12)
    true_concentration_for_synthetic_obs: float = Field(ge=0, le=1)


class EnsembleSummaryResponse(BaseModel):
    available: bool
    n_members: int = 0
    mean_ensemble_std: float = 0.0
    max_ensemble_std: float = 0.0
    ensemble_mae_vs_truth: float = 0.0
    best_single_member_mae_vs_truth: float = 0.0
    note: str = ""


class EnsembleGridResponse(BaseModel):
    available: bool
    lat: list[float] = []
    lon: list[float] = []
    mean: list[list[float]] = []
    std: list[list[float]] = []
    sample_index: int = 0
    lead_step: int = 0
    note: str = ""


class EdgeReportResponse(BaseModel):
    available: bool
    tiny: dict | None = None
    edge_target: dict | None = None
    note: str = ""


class FusionResponse(BaseModel):
    global_model_mean: float
    global_model_variance: float
    prior_mean: float
    prior_variance: float
    correction_mean: float
    correction_variance: float
    fused_mean: float
    fused_variance: float


class VesselOut(BaseModel):
    id: str
    name: str
    imo: str | None
    mmsi: str | None
    vessel_type: str
    home_port: str
    assigned_station_ids: list[str]
    active: bool
    status: str
    lon: float
    lat: float
    note: str


class VesselRosterResponse(BaseModel):
    vessels: list[VesselOut]


class SatelliteObservation(BaseModel):
    """Provenance for one real satellite observation, as returned by the
    provider. Absent when no real request has succeeded -- never synthesised."""

    product_id: str
    acquired_at: str = Field(..., description="Acquisition time reported by the provider")
    bbox: list[float]
    collection: str
    extra: dict = Field(default_factory=dict)


class SatelliteSourceStatus(BaseModel):
    state: str = Field(
        ..., description="CONNECTED | NOT_CONFIGURED | CONNECTION_ERROR | DEMO"
    )
    reason: str
    provider: str
    credentials_configured: bool
    imagery_available: bool = Field(
        False, description="Whether pixels (not just metadata) can be requested"
    )
    checked_at: str | None = Field(None, description="When this probe actually ran")
    observation: SatelliteObservation | None = None
    connected: bool = Field(
        ..., description="True only when a real provider request succeeded (state == CONNECTED)"
    )


class SatelliteStatusResponse(BaseModel):
    sources: dict[str, SatelliteSourceStatus]
