"""Request/response schemas for POST /mission/plan."""

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import MISSIONS, VALID_HORIZONS_HOURS


class RouteWeights(BaseModel):
    risk: float = Field(0.8, ge=0.0)
    fuel: float = Field(0.5, ge=0.0)
    eta: float = Field(0.4, ge=0.0)

    @model_validator(mode="after")
    def _non_zero(self) -> "RouteWeights":
        if self.risk + self.fuel + self.eta <= 0:
            raise ValueError("at least one of risk/fuel/eta weights must be > 0")
        return self

    def normalized(self) -> "RouteWeights":
        total = self.risk + self.fuel + self.eta
        return RouteWeights(risk=self.risk / total, fuel=self.fuel / total, eta=self.eta / total)


class IceThresholdsIn(BaseModel):
    passable_max: float = Field(0.30, gt=0.0, lt=1.0)
    caution_max: float = Field(0.60, gt=0.0, lt=1.0)
    restricted_max: float = Field(0.80, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> "IceThresholdsIn":
        if not (self.passable_max < self.caution_max < self.restricted_max):
            raise ValueError("thresholds must satisfy passable_max < caution_max < restricted_max")
        return self


class MissionPlanRequest(BaseModel):
    mission_id: str
    vessel_id: str | None = Field(None, description="Observed vessel id; defaults per mission")
    horizon_hours: int = Field(0, description="Forecast horizon used for hazard evaluation")
    weights: RouteWeights = Field(default_factory=RouteWeights)
    ice_thresholds: IceThresholdsIn | None = None
    start_lon: float | None = Field(
        None,
        ge=-180.0,
        le=180.0,
        description=(
            "Overrides the mission's fixed origin (e.g. Cape Town) with a custom start point -- "
            "the vessel's current position for an underway replan. Must be supplied together with "
            "start_lat. Reuses the same A* engine and navigation domain; not a second routing path."
        ),
    )
    start_lat: float | None = Field(None, ge=-90.0, le=90.0)

    @field_validator("mission_id")
    @classmethod
    def _known_mission(cls, v: str) -> str:
        if v not in MISSIONS:
            raise ValueError(f"unknown mission_id; expected one of {sorted(MISSIONS)}")
        return v

    @field_validator("horizon_hours")
    @classmethod
    def _known_horizon(cls, v: int) -> int:
        if v not in VALID_HORIZONS_HOURS:
            raise ValueError(f"horizon_hours must be one of {list(VALID_HORIZONS_HOURS)}")
        return v

    @model_validator(mode="after")
    def _start_override_is_paired(self) -> "MissionPlanRequest":
        if (self.start_lon is None) != (self.start_lat is None):
            raise ValueError("start_lon and start_lat must be supplied together")
        return self


class FuelEstimate(BaseModel):
    tonnes: float
    label: str = "PROTOTYPE ESTIMATE"
    consumption_t_per_km: float
    environmental_multiplier: float = Field(..., description="Distance-weighted mean fuel multiplier")
    formula: str = "distance x vessel consumption x environmental multiplier"


class SeaIceExposure(BaseModel):
    model: str = "PROTOTYPE PASSABILITY MODEL"
    vessel_ice_class: str
    mean_sic_pct: float
    max_sic_pct: float
    passable_pct: float
    caution_pct: float
    restricted_pct: float
    impassable_pct: float
    ice_exposure_km: float = Field(..., description="Distance with SIC above the PASSABLE threshold")
    assessment: str = Field(..., description="Worst level covering >=10% of route distance")
    max_level_encountered: str


class RelevantIceberg(BaseModel):
    id: str
    name: str
    distance_km: float = Field(..., description="Closest approach of the route to the berg centre")
    exclusion_radius_km: float = Field(..., description="Physical radius + forecast uncertainty radius")
    uncertainty_radius_km: float
    classification: str = Field(..., description="INTERSECTING | POTENTIAL | NEARBY")
    risk_level: str
    confidence: float
    closest_approach_eta_h: float


class IcebergExposure(BaseModel):
    horizon_hours: int
    tracked_count: int
    intersecting_count: int
    potential_count: int
    nearby_count: int
    min_distance_km: float | None
    mean_risk: float
    max_risk: float
    relevant_icebergs: list[RelevantIceberg]


class WeatherExposure(BaseModel):
    mean_wave_m: float
    max_wave_m: float
    mean_wind_kt: float
    max_wind_kt: float
    min_visibility_nm: float
    air_temp_c: float
    pressure_hpa: float
    high_sea_state_pct: float = Field(..., description="Route distance with waves >= 4 m")
    mean_risk: float
    provenance: str


class RouteTradeoff(BaseModel):
    """This route measured against RECOMMENDED. All four are `this - recommended`,
    so a positive eta_delta_hours means this route is slower."""

    distance_delta_km: float
    eta_delta_hours: float
    fuel_delta_t: float
    risk_delta: float


class RiskAcceptability(BaseModel):
    """Navigation risk as an engine-applied constraint, not an operator preference."""

    risk_score: float = Field(..., description="This route's measured risk score")
    safest_candidate_risk: float = Field(..., description="Lowest risk score across all candidates")
    band: float = Field(..., description="How far above the safest candidate still counts as acceptable")
    within_constraint: bool


class RouteDeviation(BaseModel):
    """A bend the route genuinely needed, and the environmental cost that caused it.

    Produced as a by-product of geometry simplification: when the straight
    shortcut past a vertex was rejected for crossing materially worse cells,
    the offending cell is what gets reported here. A bend with no such cause is
    simplified away rather than explained, so this list never invents a hazard
    to justify existing geometry.
    """

    longitude: float = Field(..., description="The retained bend on the route")
    latitude: float
    cause_longitude: float = Field(..., description="The high-cost cell the route steered around")
    cause_latitude: float
    cause: str = Field(..., description="SEA_ICE | ICEBERG | LAND | NAVIGATION_COST")
    detail: str = Field(..., description="Short operator-facing reason, e.g. 'Sea ice 82% concentration'")
    sic_pct: float | None = None
    iceberg_id: str | None = None
    iceberg_distance_km: float | None = None


class RoutePlan(BaseModel):
    route_id: str
    label: str
    objective: str = Field(..., description="What this strategy optimises, in operator language")
    selection_rationale: str = Field(..., description="Why the engine picked this candidate for this role")
    risk_acceptability: RiskAcceptability
    tradeoff_vs_recommended: RouteTradeoff | None = Field(
        None, description="None on the RECOMMENDED route itself"
    )
    deviations: list[RouteDeviation] = Field(
        default_factory=list, description="Bends with a real environmental cause"
    )
    shares_track_with: str | None = Field(
        None,
        description=(
            "Set when the environment offers fewer distinct corridors than strategies, and this "
            "strategy's best answer is the same track another strategy already claimed. Honest "
            "reporting of a real operational situation, not a duplicate route."
        ),
    )
    coordinates: list[list[float]] = Field(..., description="[lon, lat] vertices, origin to destination")
    search_weights: RouteWeights = Field(..., description="Weights of the A* search that produced this geometry (roles are assigned from measured metrics)")
    distance_km: float
    eta_hours: float
    estimated_fuel: FuelEstimate
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    sea_ice_exposure: SeaIceExposure
    iceberg_exposure: IcebergExposure
    weather_exposure: WeatherExposure
    primary_risk_driver: str
    risk_driver_shares: dict[str, float]
    explanation: list[str]
    generation: str = Field(..., description="How this candidate route was searched")
    candidates_evaluated: int = Field(..., description="Distinct A* candidate routes the roles were chosen from")
    provenance: dict[str, str]


class VesselSummary(BaseModel):
    id: str
    name: str
    ice_class: str
    profile_tier: str
    cruise_speed_kt: float
    fuel_t_per_km: float


class DomainSummary(BaseModel):
    lon_range: list[float]
    lat_range: list[float]
    resolution_deg: float
    origin_snap_km: float
    destination_snap_km: float
    note: str


class MissionPlanResponse(BaseModel):
    mission_id: str
    mission_label: str
    origin_name: str
    destination_name: str
    vessel: VesselSummary
    horizon_hours: int
    weights: RouteWeights
    ice_thresholds: IceThresholdsIn
    domain: DomainSummary
    routes: list[RoutePlan]
    warnings: list[str]
    generated_at: str
