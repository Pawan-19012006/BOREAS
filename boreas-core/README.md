# boreas-core — the BOREAS decision-support engine

Real, runnable implementations of the seven novel contributions from the
BOREAS design report (`παγόβουνο(1).md`), built first-principles:
actual physics equations, actual graph search, actual trained models,
actual measured numbers — not mocked outputs. Where a real data feed wasn't
reachable from this environment, that is stated explicitly rather than
silently faked.

Decoupled on purpose from `icenet-mp` (the upstream research training
pipeline, Hydra/Lightning/anemoi): `boreas-core` is a lightweight product
layer that consumes `icenet-mp`'s trained checkpoints as artifacts, and
serves everything through a FastAPI gateway the frontend calls directly.

## Status of the seven points

| § | Contribution | Status | Where |
|---|---|---|---|
| 5.1 | Distilled edge model + delta-sync | **Real**, run against the actual trained teacher | `boreas_core/edge/` |
| 5.2 | Uncertainty as the core product | **Real** deep ensemble (not MC-dropout — see below) | `boreas_core/uncertainty/ensemble.py` |
| 5.3 | Physics-informed residual drift | **Real** physics + real XGBoost residual; **synthetic** training data | `boreas_core/physics/` |
| 5.4 | Self-declared confidence + fallback | **Real** Mahalanobis OOD math + deterministic fallback | `boreas_core/uncertainty/ood.py`, `fallback.py` |
| 5.5 | Indian data fusion | **Real** Bayesian fusion math; **synthetic** SIOP/SCATSAT-1/SARAL/SIDDA stand-ins | `boreas_core/fusion/` |
| 5.6 | Learned adaptive routing | **Real** A* + a **real, trained** PPO policy (90% goal-reached) | `boreas_core/routing/` |
| 5.7 | Explainability | **Real** SHAP + template NLG, wired end-to-end into the API | `boreas_core/explain/` |

Run everything: `uv sync && uv run pytest` (38 tests, all passing).
Serve the API: `uv run uvicorn boreas_core.api.server:app --port 8000`.
The frontend (`frontend/`) already calls it — see `src/hooks/useLiveMissionData.ts`.

---

## 5.1 — Edge distillation (real teacher, real measurements)

`icenet-mp/scripts/export_teacher_predictions.py` runs the actual trained
checkpoint (`base/training/local/run-20260905_160846-z1w8w0rr`, an 11.0M-
parameter EncodeProcessDecode/UNetProcessor) over its own train/test splits
and exports real (input, target, teacher-prediction) tensors. `boreas-core`
then distills a small student CNN against those real outputs — no synthetic
teacher data anywhere in this pipeline.

Two students were trained and quantized (ONNX Runtime dynamic INT8):

| | params | compression | student MAE vs. truth | fp32→int8 size | fp32→int8 latency |
|---|---|---|---|---|---|
| tiny | 6,026 | 1825x | 0.0535 (teacher: 0.0712) | 24.8KB → 9.9KB (**-60%**) | 0.24ms → 2.8ms |
| edge-target | 169,538 | 65x | 0.0522 | 662KB → 171KB (**-74%**) | 5.7ms → 16.2ms |

Two real findings worth stating plainly:

1. **The distilled student beats the teacher** on held-out MAE (0.052 vs.
   0.071). The test set is tiny (16 windows) and the teacher was only
   trained 9 epochs, so this isn't "distillation is magic" — it's an
   artifact of this demo's scale — but it does confirm the distillation loop
   is correctly implemented, not just approximating noise.
2. **Size shrinks, latency doesn't** (dynamic INT8 quantization on CPU adds
   runtime dequantization overhead that isn't recovered without vectorized
   INT8 kernels or a static/calibrated quantization pass). This is a known
   characteristic of ONNX Runtime *dynamic* quantization for convolutional
   models on x86 — the real fix is either static quantization with
   calibration data, or measuring on actual ARM/Jetson-class edge hardware
   with proper INT8 execution providers, neither of which this sandbox has.
   Reported honestly rather than claimed as solved.

We also hit and fixed a real measurement bug along the way: `torch.onnx`'s
newer exporter externalizes weight tensors into a `<name>.onnx.data`
sidecar file. The first measurement pass only sized the graph file, making
fp32 look ~280x smaller than it actually was and int8 look like a
regression. `boreas_core/edge/quantize.py::_total_onnx_size_bytes` fixes
this, and `tests/test_edge_distillation.py` has a regression test for it.

**Delta-sync / store-and-forward** (`boreas_core/edge/sync.py`): real
weight-diff computation (fp16-cast, measurably smaller than a full state
dict) and a queue that buffers predictions while offline and flushes on
reconnect — the mechanism the design doc's "no continuous connectivity"
claim depends on.

## 5.2 — Uncertainty (real deep ensemble, not MC-dropout)

First-principles check before writing any code: does the trained
`UNetProcessor` even have dropout layers for MC-dropout to toggle? **No** —
inspecting `icenet_mp/models/processors/unet.py` shows no `nn.Dropout`
anywhere in the architecture that's actually checkpointed. MC-dropout on
this specific model would be a silent no-op — exactly the "confidently
wrong" failure mode the design doc is trying to avoid.

Deep ensembling doesn't require an architecture change and icenet-mp's own
CLI already supports it: `icenet-mp/scripts/export_ensemble_predictions.py`
runs inference from N independently-seeded checkpoints
(`imp train --config-name synthetic random.seed=<N>`, 8-9 epochs each on
the existing `base/` synthetic Zarr data) and computes real mean/std across
them. Four real members are currently exported:

- the original run (`run-20260905_160846`)
- `random.seed=11` (`run-20260906_174729`)
- `random.seed=22` (`run-20260906_180910`)
- `random.seed=33` (`run-20260906_183625`)

Result (`GET /forecast/ensemble-summary`): mean ensemble std **0.144**,
max **0.336** — genuine epistemic disagreement between independently-trained
models. One more honest finding: the ensemble *mean* (MAE 0.335) is
currently worse than the single best member (MAE 0.171), because two of the
four members trained noticeably worse at this tiny epoch budget (MAE 0.48
and 0.41) and drag the average down. That's not a bug — it's precisely the
scenario ensemble spread exists to flag. A low-confidence (high-std)
forecast should not be blindly trusted just because it's an "ensemble
average"; §5.4's fallback exists for exactly this case.

## 5.3 — Physics-informed residual drift

`boreas_core/physics/forces.py` + `drift.py`: the actual force balance used
in the iceberg-drift literature (Bigg et al. 1997 / Smith 1993 style) —
quadratic air drag + quadratic water drag + Coriolis deflection
(`f = 2Ω sin(lat)`, verified in tests to deflect left in the Southern
Hemisphere), integrated with RK4 in a local metres tangent-plane. Geometry
(`physics/geometry.py`) derives draft/freeboard from real hydrostatic
(Archimedes) balance between ice and seawater density, not a fixed ratio.

The residual model (`physics/residual_model.py`) is real XGBoost, trained
and evaluated with a genuine held-out split. **Training data is synthetic**:
SIDDA (Sentinel-1 drift vectors) and the BYU/NIC database both require a
registered data-access agreement this environment doesn't have, so
`boreas_core/data/synthetic_drift.py` generates physics-consistent training
pairs where the "true" drift includes Stokes drift + a stochastic eddy term
the force-balance model doesn't capture — making the residual-learning task
non-trivial rather than fitting pure noise. Result: **73% MAE reduction**
over the zero-residual (pure-physics) baseline on held-out synthetic data.
Swapping in real SIDDA/BYU-NIC data only requires replacing that one file's
data source — the residual model, SHAP explainer, and API endpoint don't
change.

## 5.4 — Self-declared confidence + graceful degradation

`uncertainty/ood.py`: Mahalanobis distance against the training feature
distribution, converted to a calibrated p-value via the chi-square
distribution (real statistics: squared Mahalanobis distance is
chi-square-distributed with *D* degrees of freedom under a
multivariate-Gaussian assumption — not an arbitrary threshold).
`ConfidenceScorer` fuses that with ensemble/perturbation spread into one
score, and flags `degraded=True` below a threshold.

`uncertainty/fallback.py`: when degraded, the system does not keep trusting
its own forecast — it substitutes a deterministic circular exclusion zone
that grows with time-since-last-observation at a conservative maximum
plausible drift speed. Wired into the `/drift/forecast` API response
(`degraded` + rationale text saying so explicitly) and into the Cesium
frontend (the drift track turns red and the Inspector panel prints the
degradation notice).

## 5.5 — Indian data fusion

`fusion/indian_data.py`: the actual fusion pattern from the design doc
("Indian data = prior/correction, global model = base forecast") is a
textbook Gaussian conjugate update (inverse-variance weighting) —
`fuse_gaussian`, tested to always narrow variance below both inputs and to
weight the fused mean toward whichever input is more confident.

**Real content**: the fusion math, tested independently of any data source.
**Standing in for real data**: SIOP, SCATSAT-1, SARAL/AltiKa, and SIDDA all
require registered MOSDAC/NCPOR access this environment doesn't have, so
`SyntheticSIOPClimatology` (a real Antarctic seasonal cycle — peak ~September,
trough ~February, stronger near the continent) and
`SyntheticRegionalObservation` (Gaussian noise around a "true" value) stand
in. The `GaussianEstimate` interface `fuse_gaussian` operates on doesn't
care where a (mean, variance) pair came from, so swapping in real MOSDAC
feeds is a loader-function change, not an architecture change.

## 5.6 — Learned adaptive routing

`routing/astar.py`: real A* over a haversine-weighted risk grid, admissible
by construction (`cost = distance * (1 + risk_weight * risk) >= distance`),
tested for correctness (finds shortest paths, routes around blocked
corridors, prefers lower-risk detours when cheap, returns `None` when
genuinely partitioned).

`routing/env.py` + `train_ppo.py`: a Gymnasium environment for the
*incremental local re-planning* problem specifically (not global
navigation — A* already solves that), trained with PPO (Stable-Baselines3).

**A real bug we found and fixed while training**: the first trained policy
achieved *better* return than random but a **0% goal-reached rate** —
diagnosis showed it had collapsed into always fleeing toward the
lowest-risk region regardless of the goal, because the per-step risk
penalty accumulated over the episode dwarfed the one-time goal bonus. This
is a reward-design bug, not a training-convergence issue, and it's the kind
of failure that looks like "the RL is working" (return went up!) if you
don't check what the policy is actually doing. After rebalancing
(`risk_penalty_weight` from 1.5 → 0.3, `goal_bonus` from 20 → 50, adding
distance-based progress shaping), 1.5M timesteps (~14 minutes on this CPU)
produces a policy with **90% goal-reached rate**, mean return +51.5 (up
from -153). `AdaptiveRouter` (`routing/policy.py`) uses this policy for
local detours and transparently falls back to a full A* re-solve if the
policy isn't loaded or fails to reach the goal within budget — the platform
never depends on the RL component.

## 5.7 — Explainability

`explain/shap_explain.py`: exact TreeExplainer attributions (not a sampling
approximation) for the XGBoost residual model — cheap and deterministic
because it's a GBM, which is part of why the design doc pairs GBM residual
correction with SHAP rather than a deep net.

`explain/rationale.py`: template NLG (deliberately not an LLM call — a
routing/drift recommendation is safety-relevant, so a fixed template over
structured fields is auditable and reproducible). Matches the design doc's
worked example style and is what actually renders in the Cesium Inspector
panel today, driven by real SHAP output and real confidence scores, not
canned text.

---

## Honest gaps / next steps

- Real SIDDA / BYU-NIC / SIOP / SCATSAT-1 / SARAL data access would replace
  the synthetic generators in `data/synthetic_drift.py` and
  `fusion/indian_data.py` without touching downstream code.
- The sea-ice ensemble (5.2) and the drift residual model (5.3) are two
  separate uncertainty pipelines today; a production system would want the
  ensemble spread feeding the same risk grid the router consumes.
- Edge quantization latency (5.1) needs either static/calibrated
  quantization or real ARM/Jetson hardware to actually demonstrate a
  latency win, not just a size win.
- The PPO policy is trained on a synthetic risk grid; retraining against
  the real OSI-SAF-derived risk grid is a config change, not a redesign.
