"""FastAPI inference gateway tying together the BOREAS decision-support core.

Run with:
    uv run uvicorn boreas_core.api.server:app --port 8000 --reload
"""

import json

import numpy as np
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from boreas_core.data.synthetic_drift import FEATURE_COLUMNS
from boreas_core.explain.rationale import generate_drift_rationale, generate_route_rationale
from boreas_core.fusion.indian_data import IndianDataFusionLayer
from boreas_core.physics.drift import PhysicsDriftModel, constant_forcing
from boreas_core.physics.geometry import IcebergGeometry
from boreas_core.physics.forces import net_acceleration
from boreas_core.routing.directions import build_route_legs
from boreas_core.routing.grid import synthetic_southern_ocean_grid
from boreas_core.satellite.quicklook import get_quicklook
from boreas_core.satellite.status import get_all_statuses
from boreas_core.uncertainty.ood import ConfidenceAssessment
from boreas_core.vessels import live_lookup
from boreas_core.vessels.roster import ROSTER

from .schemas import (
    DriftForecastRequest,
    DriftForecastResponse,
    EdgeReportResponse,
    EnsembleGridResponse,
    EnsembleSummaryResponse,
    FusionRequest,
    FusionResponse,
    RouteLegOut,
    RouteOptionOut,
    RoutePlanRequest,
    RoutePlanResponse,
    SatelliteSourceStatus,
    SatelliteStatusResponse,
    VesselOut,
    VesselRosterResponse,
)
from .state import ARTIFACTS_DIR, get_state

# The ensemble export's 32x32 grid carries no coordinate metadata of its own;
# this mapping is sourced from icenet_mp/ingestion/sources/synthetic.py,
# which builds the dataset's coordinates via
# np.meshgrid(np.linspace(-90, 90, 32), np.linspace(-180, 180, 32), indexing="ij")
# with the array's H axis = latitude, W axis = longitude. Both endpoints are
# inclusive (31 intervals), so lon=-180/180 is the same meridian sampled
# twice and lat=-90/90 are the poles -- harmless for a heatmap, worth noting
# so nobody "fixes" it later.
ENSEMBLE_GRID_LAT = np.linspace(-90, 90, 32)
ENSEMBLE_GRID_LON = np.linspace(-180, 180, 32)

app = FastAPI(
    title="BOREAS Core API",
    description="Physics-informed drift, uncertainty, routing, and explainability for the BOREAS Antarctic platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    state = get_state()
    return {
        "status": "OK",
        "system": "BOREAS Core",
        "ppo_policy_loaded": state.router.has_policy,
    }


@app.post("/drift/forecast", response_model=DriftForecastResponse)
def forecast_drift(request: DriftForecastRequest) -> DriftForecastResponse:
    state = get_state()
    geometry = IcebergGeometry(**request.geometry.model_dump())

    residual_fn = state.residual_model.as_residual_correction_fn() if request.use_residual_correction else None
    model = PhysicsDriftModel(geometry=geometry, residual_correction=residual_fn)

    wind = np.array([request.wind_east_ms, request.wind_north_ms])
    current = np.array([request.current_east_ms, request.current_north_ms])
    start_velocity = np.array([request.velocity_east_ms, request.velocity_north_ms])

    result = model.simulate(
        start_lon=request.lon,
        start_lat=request.lat,
        start_velocity=start_velocity,
        forcing_fn=constant_forcing(wind, current),
        duration_hours=request.duration_hours,
    )

    # Confidence/OOD assessment against the training feature distribution,
    # evaluated at the initial state (BOREAS design doc §5.4).
    physics_accel = net_acceleration(
        iceberg_velocity=start_velocity,
        wind_velocity=wind,
        current_velocity=current,
        latitude_deg=request.lat,
        mass_kg=geometry.mass_kg,
        sail_area_m2=geometry.sail_area_m2,
        draft_area_m2=geometry.draft_area_m2,
    )
    physics_velocity = start_velocity + physics_accel * 3600.0
    feature_row = {
        "physics_vel_east": physics_velocity[0],
        "physics_vel_north": physics_velocity[1],
        "wind_east": wind[0],
        "wind_north": wind[1],
        "current_east": current[0],
        "current_north": current[1],
        "latitude": request.lat,
        "length_m": geometry.length_m,
        "width_m": geometry.width_m,
        "thickness_m": geometry.thickness_m,
        "sail_area_m2": geometry.sail_area_m2,
        "draft_area_m2": geometry.draft_area_m2,
    }
    feature_vector = np.array([feature_row[col] for col in FEATURE_COLUMNS])

    # Ensemble spread stand-in: perturb the residual prediction inputs slightly
    # and measure output spread, until a real multi-checkpoint ensemble
    # (uncertainty/ensemble.py) is wired into this endpoint.
    rng = np.random.default_rng(0)
    perturbed_preds = [
        state.residual_model.predict_single(
            {**feature_row, "wind_east": feature_row["wind_east"] + rng.normal(0, 0.3)}
        )
        for _ in range(8)
    ]
    ensemble_std = float(np.std(perturbed_preds))

    assessment: ConfidenceAssessment = state.confidence_scorer.assess(feature_vector, ensemble_std)
    top_factors = state.drift_explainer.top_factors(feature_row, k=3)
    rationale = generate_drift_rationale(confidence=assessment, top_factors=top_factors)

    return DriftForecastResponse(
        track=result.track,
        final_velocity_ms=(float(result.velocity[-1, 0]), float(result.velocity[-1, 1])),
        confidence=assessment.confidence,
        ood_p_value=assessment.ood_p_value,
        degraded=assessment.degraded,
        rationale=rationale,
        top_factors=top_factors,
    )


@app.get("/vessels/roster", response_model=VesselRosterResponse)
def vessels_roster() -> VesselRosterResponse:
    """Real vessel roster with each vessel's live-AIS status resolved
    server-side (BOREAS design doc: voyage planner ship picker). See
    boreas_core/vessels/roster.py for citations and boreas_core/vessels/
    live_lookup.py for the VesselAPI lookup + caching.
    """
    vessels = []
    for vessel in ROSTER:
        lookup = live_lookup.lookup_vessel_position(vessel)
        vessels.append(
            VesselOut(
                id=vessel.id,
                name=vessel.name,
                imo=vessel.imo,
                mmsi=vessel.mmsi,
                vessel_type=vessel.vessel_type,
                home_port=vessel.home_port,
                assigned_station_ids=list(vessel.assigned_station_ids),
                active=vessel.active,
                status=lookup.status,
                lon=lookup.lon,
                lat=lookup.lat,
                note=lookup.note,
            )
        )
    return VesselRosterResponse(vessels=vessels)


def _legs_out(legs) -> list[RouteLegOut]:
    return [
        RouteLegOut(
            start_lonlat=leg.start_lonlat,
            end_lonlat=leg.end_lonlat,
            bearing_deg=leg.bearing_deg,
            compass_label=leg.compass_label,
            distance_km=leg.distance_km,
        )
        for leg in legs
    ]


@app.get("/satellite/status", response_model=SatelliteStatusResponse)
def satellite_status() -> SatelliteStatusResponse:
    """Real, env-var-gated connectivity status for the satellite tile
    sources that need credentials (Sentinel-1/2 via CDSE, Copernicus Marine)
    -- see boreas_core/satellite/status.py. NASA Worldview/GIBS is keyless
    and not included here; the frontend treats any source missing from this
    map as connected.
    """
    statuses = get_all_statuses()
    return SatelliteStatusResponse(
        sources={
            source_id: SatelliteSourceStatus(connected=status.connected, reason=status.reason)
            for source_id, status in statuses.items()
        }
    )


@app.get("/satellite/{source_id}/quicklook")
def satellite_quicklook(source_id: str) -> Response:
    """Real, freshly-fetched (30-minute-cached) quicklook imagery for a
    satellite tile source -- see boreas_core/satellite/quicklook.py. Returns
    the actual image bytes on success; a 503 with a clear reason (never a
    silent fallback image) if the source isn't connected or the upstream
    fetch failed, so the frontend can distinguish "no data available" from
    "here's live data" instead of masquerading one as the other.
    """
    result = get_quicklook(source_id)
    if not result.available or result.image_bytes is None:
        # `debug` carries the raw upstream error (CDSE token response,
        # Sentinel Hub API response, or the copernicusmarine exception +
        # traceback) so the real cause -- bad credentials vs. no scene in
        # range vs. an auth scope issue -- is visible in the response body,
        # not just a flattened message. Also logged server-side (see each
        # fetch module's logger.warning calls) for terminal visibility.
        raise HTTPException(status_code=503, detail={"reason": result.reason, "debug": result.debug})

    headers = {}
    if result.metadata:
        if "scene_id" in result.metadata:
            headers["X-Sentinel-Scene-ID"] = str(result.metadata["scene_id"])
        if "cloud_cover" in result.metadata and result.metadata["cloud_cover"] is not None and result.metadata["cloud_cover"] >= 0:
            headers["X-Sentinel-Cloud-Cover"] = f"{result.metadata['cloud_cover']:.1f}%"
        if "datetime" in result.metadata:
            headers["X-Sentinel-Datetime"] = str(result.metadata["datetime"])
        if "polarization" in result.metadata:
            headers["X-Sentinel-Polarization"] = str(result.metadata["polarization"])
        if "bands" in result.metadata:
            headers["X-Sentinel-Bands"] = "/".join(result.metadata["bands"])
        if "bbox" in result.metadata and result.metadata["bbox"]:
            headers["X-Sentinel-Bbox"] = ",".join(str(coord) for coord in result.metadata["bbox"])

    headers["Access-Control-Expose-Headers"] = (
        "X-Sentinel-Scene-ID, X-Sentinel-Cloud-Cover, X-Sentinel-Datetime, "
        "X-Sentinel-Polarization, X-Sentinel-Bands, X-Sentinel-Bbox"
    )

    return Response(content=result.image_bytes, media_type=result.content_type, headers=headers)


@app.get("/satellite/{source_id}/metadata")
def satellite_metadata(source_id: str) -> dict:
    """Lightweight metadata endpoint exposing scene metadata (scene ID, datetime,
    cloud cover, and rendered geographic bbox) for the cached quicklook scene.
    """
    result = get_quicklook(source_id)
    if not result.available or not result.metadata:
        raise HTTPException(status_code=503, detail={"reason": result.reason, "debug": result.debug})
    return result.metadata


@app.post("/route/plan", response_model=RoutePlanResponse)
def plan_route(request: RoutePlanRequest) -> RoutePlanResponse:
    """Returns multiple labeled route options (Google-Maps-style
    alternatives), each scored on the same real, time-aware forecast basis
    and exactly one marked `recommended`, per BOREAS's voyage-planner design
    (see boreas_core/routing/scoring.py for the ranking mechanism and its
    disclosed lead-step limitation).
    """
    from boreas_core.routing.astar import RouteResult, astar_route
    from boreas_core.routing.polarroute_adapter import plan_polar_route
    from boreas_core.routing.scoring import ScoredCandidate, rank_candidates, time_aware_max_risk
    from boreas_core.uncertainty.ensemble import load_ensemble_forecast

    state = get_state()
    grid = synthetic_southern_ocean_grid(seed=0)

    for lon, lat, radius_km in zip(
        request.hazard_lon, request.hazard_lat, request.hazard_radius_km, strict=True
    ):
        grid.stamp_circular_hazard(center_lon=lon, center_lat=lat, radius_km=radius_km)

    start = grid.nearest_index(request.start_lon, request.start_lat)
    goal = grid.nearest_index(request.goal_lon, request.goal_lat)
    speed_km_per_hour = request.vessel_speed_kt * 1.852

    warnings: list[str] = []

    # Real trained ensemble forecast, one mean grid per lead step -- the
    # single, unified risk basis every candidate below is judged on (see
    # scoring.time_aware_max_risk's module docstring for the real ~1-2 day
    # forecast-horizon limitation this implies).
    ice_mean_by_lead_step: list = []
    npz_path = ARTIFACTS_DIR / "ensemble_export.npz"
    if npz_path.exists():
        forecast = load_ensemble_forecast(npz_path)
        ice_mean_by_lead_step = [forecast.mean[0, t, 0] for t in range(forecast.mean.shape[1])]
    else:
        warnings.append(
            "No ensemble forecast export found -- route risk scores fall back to each "
            "route's own synthetic risk-grid cost instead of the real trained forecast."
        )

    def _risk_for(legs, fallback_risk: float) -> float:
        if ice_mean_by_lead_step:
            return time_aware_max_risk(
                legs,
                vessel_speed_kt=request.vessel_speed_kt,
                ice_lat=ENSEMBLE_GRID_LAT,
                ice_lon=ENSEMBLE_GRID_LON,
                ice_mean_by_lead_step=ice_mean_by_lead_step,
            )
        return fallback_risk

    # candidates: list of (engine_key, label, RouteResult, legs, duration_hours, risk, rationale)
    candidates: list[tuple[str, str, RouteResult, list, float, float, str]] = []

    # --- AI Risk-Adjusted Route (existing default behaviour: astar_route at
    # risk_weight=2.0, optionally PPO-assisted on re-plan) -- the one
    # candidate that must always succeed or the whole request fails, same
    # as before this multi-option upgrade.
    try:
        decision = state.router.plan(grid, start, goal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    route = decision.result
    legs = build_route_legs(route)
    duration_hours = route.total_distance_km / speed_km_per_hour
    risk = _risk_for(legs, route.max_risk_on_path)
    pseudo_confidence = ConfidenceAssessment(
        ensemble_std=0.0,
        ood_distance=0.0,
        ood_p_value=1.0,
        confidence=1.0 - route.max_risk_on_path,
        degraded=route.max_risk_on_path >= 0.7,
    )
    base_rationale = generate_route_rationale(
        route=route,
        replanned=decision.replanned,
        replan_reason=decision.replan_reason,
        confidence=pseudo_confidence,
        data_sources=["OSI-SAF (synthetic stand-in)", "SIDDA (synthetic stand-in)"],
    ).full_text
    rationale = (
        base_rationale
        + " Displayed risk score reflects the real trained ensemble forecast at each leg's "
        "estimated arrival time, not this search's internal (synthetic) risk-grid cost."
    )
    candidates.append(("boreas_ai_risk_adjusted", "AI Risk-Adjusted Route", route, legs, duration_hours, risk, rationale))

    # --- Shortest Path (near-ice-naive baseline, same grid/connectivity) ---
    shortest = astar_route(grid, start, goal, risk_weight=0.05)
    if shortest is not None:
        legs = build_route_legs(shortest)
        duration_hours = shortest.total_distance_km / speed_km_per_hour
        risk = _risk_for(legs, shortest.max_risk_on_path)
        rationale = (
            f"Shortest-path baseline (A* with minimal risk weighting): {shortest.total_distance_km:.0f} km. "
            "Displayed risk score reflects the real trained ensemble forecast at each leg's estimated "
            "arrival time -- this route was not planned to avoid it."
        )
        candidates.append(("boreas_ai_shortest", "Shortest Path", shortest, legs, duration_hours, risk, rationale))

    # --- Published Route (PolarRoute) -- only included if it actually
    # produces a route; any failure degrades to a warning, never a crash.
    if request.include_polar_route and ice_mean_by_lead_step:
        polar_result = plan_polar_route(
            start_lonlat=(request.start_lon, request.start_lat),
            goal_lonlat=(request.goal_lon, request.goal_lat),
            ice_lat=ENSEMBLE_GRID_LAT,
            ice_lon=ENSEMBLE_GRID_LON,
            ice_mean=ice_mean_by_lead_step[0],
            hazard_lon=request.hazard_lon,
            hazard_lat=request.hazard_lat,
            hazard_radius_km=request.hazard_radius_km,
        )
        if polar_result.available:
            polar_route_result = RouteResult(
                path_cells=[],
                path_lonlat=polar_result.path_lonlat,
                total_distance_km=polar_result.total_distance_km,
                total_cost=polar_result.total_distance_km,
                max_risk_on_path=0.0,
            )
            legs = build_route_legs(polar_route_result)
            risk = _risk_for(legs, 0.0)
            rationale = (
                "PolarRoute (published route-optimisation engine: MeshiPhi environmental mesh "
                "built from the real ensemble ice forecast + an SDA-class ice-resistance vessel "
                f"performance model): {polar_result.total_traveltime_hours:.0f}h transit, "
                f"{polar_result.total_fuel_tons:.1f}t fuel estimated. Displayed risk score reflects "
                "the real trained ensemble forecast at each leg's estimated arrival time."
            )
            candidates.append(
                (
                    "polar_route",
                    "Published Route (PolarRoute)",
                    polar_route_result,
                    legs,
                    polar_result.total_traveltime_hours,
                    risk,
                    rationale,
                )
            )
        else:
            warnings.append(polar_result.note)
    elif not request.include_polar_route:
        pass  # deliberately skipped by the caller (see include_polar_route docstring) -- not a failure
    else:
        warnings.append("PolarRoute skipped: no ensemble forecast export available to build its mesh from.")

    scored = [
        ScoredCandidate(key=key, label=label, distance_km=route.total_distance_km, duration_hours=duration_hours, risk=risk)
        for key, label, route, _legs, duration_hours, risk, _rationale in candidates
    ]
    recommended_by_key = {c.key: c.recommended for c in rank_candidates(scored)}

    options = [
        RouteOptionOut(
            engine=key,
            label=label,
            recommended=recommended_by_key[key],
            path=route.path_lonlat,
            total_distance_km=route.total_distance_km,
            estimated_duration_hours=duration_hours,
            max_risk_on_path=risk,
            rationale=rationale,
            legs=_legs_out(legs),
        )
        for key, label, route, legs, duration_hours, risk, rationale in candidates
    ]

    return RoutePlanResponse(options=options, warnings=warnings)


@app.get("/forecast/ensemble-summary", response_model=EnsembleSummaryResponse)
def ensemble_summary() -> EnsembleSummaryResponse:
    """Summary stats from the real deep ensemble of independently-seeded
    icenet-mp checkpoints (BOREAS design doc §5.2) -- see
    icenet-mp/scripts/export_ensemble_predictions.py for how this is produced.
    """
    from boreas_core.uncertainty.ensemble import load_ensemble_forecast

    npz_path = ARTIFACTS_DIR / "ensemble_export.npz"
    if not npz_path.exists():
        return EnsembleSummaryResponse(
            available=False,
            note="No ensemble export found -- run icenet-mp/scripts/export_ensemble_predictions.py first.",
        )

    forecast = load_ensemble_forecast(npz_path)
    maes = [forecast.single_model_mean_absolute_error(i) for i in range(forecast.n_members)]
    return EnsembleSummaryResponse(
        available=True,
        n_members=forecast.n_members,
        mean_ensemble_std=float(forecast.std.mean()),
        max_ensemble_std=float(forecast.std.max()),
        ensemble_mae_vs_truth=forecast.mean_absolute_error_vs_truth(),
        best_single_member_mae_vs_truth=min(maes),
        note=(
            "At this training budget (8-9 epochs on a 96-sample synthetic set), member "
            "quality varies enough that mean-averaging can underperform the best single "
            "member -- the point of exposing ensemble spread is precisely to flag that "
            "situation rather than hide it behind a point estimate."
        ),
    )


@app.get("/forecast/ensemble-grid", response_model=EnsembleGridResponse)
def ensemble_grid(sample_index: int = 0, lead_step: int = 0) -> EnsembleGridResponse:
    """Raw 32x32 mean/std grid from the real deep ensemble, for draping as a
    heatmap layer on the globe (BOREAS design doc §5.2). See
    `/forecast/ensemble-summary` for aggregate stats instead of the raw grid.
    """
    from boreas_core.uncertainty.ensemble import load_ensemble_forecast

    npz_path = ARTIFACTS_DIR / "ensemble_export.npz"
    if not npz_path.exists():
        return EnsembleGridResponse(
            available=False,
            note="No ensemble export found -- run icenet-mp/scripts/export_ensemble_predictions.py first.",
        )

    forecast = load_ensemble_forecast(npz_path)
    if not (0 <= sample_index < forecast.mean.shape[0]) or not (
        0 <= lead_step < forecast.mean.shape[1]
    ):
        raise HTTPException(status_code=422, detail="sample_index/lead_step out of range")

    mean_grid = forecast.mean[sample_index, lead_step, 0]  # squeeze channel dim -> (32, 32)
    std_grid = forecast.std[sample_index, lead_step, 0]

    return EnsembleGridResponse(
        available=True,
        lat=ENSEMBLE_GRID_LAT.tolist(),
        lon=ENSEMBLE_GRID_LON.tolist(),
        mean=mean_grid.tolist(),
        std=std_grid.tolist(),
        sample_index=sample_index,
        lead_step=lead_step,
        note="32x32 synthetic global grid (icenet-mp samp_sicglobal_synthetic dataset).",
    )


@app.get("/edge/report", response_model=EdgeReportResponse)
def edge_report() -> EdgeReportResponse:
    """Real distillation/quantization measurements (BOREAS design doc §5.1).
    See boreas-core/scripts/run_edge_distillation.py for how this is produced.
    """
    report_path = ARTIFACTS_DIR / "edge_report.json"
    if not report_path.exists():
        return EdgeReportResponse(
            available=False,
            note="No edge report found -- run boreas-core/scripts/run_edge_distillation.py first.",
        )

    data = json.loads(report_path.read_text())
    return EdgeReportResponse(available=True, tiny=data.get("tiny"), edge_target=data.get("edge_target"))


@app.post("/fusion/demo", response_model=FusionResponse)
def fuse_indian_data(request: FusionRequest) -> FusionResponse:
    layer = IndianDataFusionLayer()
    result = layer.fuse(
        global_model_mean=request.global_model_mean,
        global_model_variance=request.global_model_variance,
        latitude_deg=request.latitude_deg,
        month=request.month,
        true_concentration_for_synthetic_obs=request.true_concentration_for_synthetic_obs,
    )
    return FusionResponse(
        global_model_mean=result.global_model_estimate.mean,
        global_model_variance=result.global_model_estimate.variance,
        prior_mean=result.indian_prior.mean,
        prior_variance=result.indian_prior.variance,
        correction_mean=result.indian_correction.mean,
        correction_variance=result.indian_correction.variance,
        fused_mean=result.fused.mean,
        fused_variance=result.fused.variance,
    )
