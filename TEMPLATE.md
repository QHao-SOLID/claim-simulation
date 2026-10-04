# base_template.json — key reference

Single source of truth for **simulation assumptions**. Scenarios in
`scenarios/*.json` are flat patches on this file: any key they contain replaces
the base value; everything else is inherited. Unknown keys are rejected by the
loader (this file is the list of what exists).

The engine is premium-independent: no pricing parameters live here and none
are ever produced.

## Run controls

| Key | Unit | Meaning / effect of raising |
|---|---|---|
| `n` | policies | Book size at cohort inception. 10000 for stable portfolio statistics; 1000 for smoke runs. |
| `cohort_year` | year | First policy year; simulation runs `n_years` forward. |
| `n_years` | years | Horizon. |
| `seed` | int | Simulation RNG seed. Overridable per scenario (`"seed": 7`) and by `seeds.json`. |
| `vehicle_ramp` | `{"from": share dict, "to": share dict?}` | Base fleet mix plus optional drift. `from` is the whole-book mix (inception + entrants); `to` (optional) interpolates entrant shares linearly `from` → `to` across the window (`cohort_year` … `cohort_year + n_years − 1`). Entrants only — existing policies keep their fuel. Order (ICE, EV) is part of the RNG draw — keep it. |
| `coverage_ramp` | `{"from": share dict, "to": share dict?}` | Same linear ramp for the coverage mix: `from` is the whole-book mix, `to` optional (absent = static book). Entrants only — existing policies keep their coverage. |
| `flood_event_prob` | P(event year) per region | A flood loading only applies in years a region draws a flood event; the `FLOOD_RISK` flag marks exposure. |
| `severity_inflation` | fraction/yr | Claim payouts compound by `(1+r)^(SIM_YEAR − cohort_year)` (repair/medical inflation). |
| `entrant_growth` | fraction/yr | New-business volume compounds per year: `n × entrant_frac × (1+g)^t`. |
| `sa_depreciation` | fraction/yr | Sum assured marked down at renewal (market value), lowering total-loss payouts with age. |
| `sa_min` | RM | Floor for depreciated sum assured. |

## Book composition

| Key | Unit | Meaning / effect of raising |
|---|---|---|
| `region_pct` | share dict | Peninsular / East Malaysia mix. |
| `generation_pct` | share dict | Driver generation mix. More Young Adults raises frequency. |
| `age_bands` | [lo, hi) | Exact age span per generation band. |
| `gender_pct` | share dict | Male / Female mix (young-male frequency loading). |
| `car_age_median` | years | Inception car age median per generation band. |
| `car_age_sigma` | years | Noise around the median; clipped to 0–10. |
| `sa_stats` | median RM, spread | Log-normal sum assured per fuel type, rounded to RM1,000. Higher median → higher severity (own-damage scales with SA). |
| `engine_bands` | labels | Engine/kW bands; the simulation draws this attribute. |
| `engine_weights` | shares | Band mix; length must equal `engine_bands`. |
| `entrant_frac` | fraction of `n` | Yearly new business volume. |

## NCD

| Key | Unit | Meaning |
|---|---|---|
| `ncd_table` | discount by year | NCD discount lookup keyed 0–5 (years beyond 5 use the top tier). |
| `ncd_entry` | years + weights | Starting NCD years mix for new policies. |

## Frequency (Poisson log-rate)

| Key | Unit | Meaning / effect of raising |
|---|---|---|
| `claim_frequency_base` | log-rate | Base log frequency (−2.00 ≈ 13.5% before rating). Raise (+0.2 ≈ ×1.22 claims) to stress frequency. |
| `frequency_intensity` | multiplier | Linear stress on the whole claim rate: `λ = λ_base × intensity` (1.10 = +10%). Default 1.0. |
| `frequency.young_adult` / `.senior` | log add-on | Driver-band loadings. |
| `frequency.young_male` | log add-on | Interaction for Young Adults × Male. |
| `frequency.ev` | log add-on | EV frequency proxy. |
| `frequency.flood` / `.theft` | log add-on | Risk-flag loadings per true flag. |
| `frequency.car_age_per_year` | log/yr | Older car → more claims. |
| `frequency.ncd_per_year` | log/yr | Claim-free years reduce frequency. |
| `frequency.coverage_multiplier` | multiplier | Applied after exponentiating: TPFT 0.60, TPO 0.45, Comprehensive 1.00. |

## Risk flags

| Key | Unit | Meaning |
|---|---|---|
| `risk_flags.flood` | P(true) per region | Random draw per policy; implemented as `random() > 1 − p` (keeps legacy draw semantics). |
| `risk_flags.theft` | P(true) per region | Same mechanism. |

## Aging (year-on-year evolution)

| Key | Unit | Meaning |
|---|---|---|
| `aging.young_max` / `.adult_max` / `.mature_max` | age | Band upgrade thresholds (≤ young_max → Young, ≤ adult_max → Adult, ≤ mature_max → Mature, else Senior). |
| `aging.car_age_cap` | years | Car age stops increasing beyond this. |

## Severity (per-claim Gamma)

| Key | Unit | Meaning |
|---|---|---|
| `severity.perils` | ordered list | Draw order of perils — **order is part of the RNG sequence**; changing it changes every claim draw. |
| `severity.specs.<peril>.shape` | Gamma shape | Lower shape = heavier tail. |
| `severity.specs.<peril>.scale` | RM or SA rule | Number = absolute RM; object = `clip(SUM_ASSURED × sa_fraction, min, max)`. |
| `severity.specs.<peril>.cap` | RM / `"sum_assured"` / `null` | Payout cap per claim. |
| `severity.specs.<peril>.payout` | `partial` / `total` / `mixed` | Settlement: `total` pays sum assured − excess; `mixed` flips a `total_loss_prob` coin per claim; `partial` keeps the Gamma draw. |
| `severity.specs.<peril>.total_loss_prob` | share | Probability a claim is settled as a total loss (mixed payout only). |
| `severity.specs.<peril>.excess` | RM | Deductible subtracted from the payout (partial at/below excess → not reported). |
| `severity.specs.<peril>.young_excess` | RM | Higher excess for Young Adults (overrides `excess`). |
| `peril_dist` | shares per coverage | Peril mix used when drawing a claim's peril; keys must equal `severity.perils`. |
| `severity_multiplier` | multiplier | Global claim-cost shock on every peril (1.20 = +20%). |

## Telematics generator

| Key | Unit | Meaning |
|---|---|---|
| `telematics.hard_braking` | Γ(shape, scale), max | Raw harsh-braking draw, clipped. |
| `telematics.speeding` | Γ(shape, scale), max | Raw speeding draw, clipped. |
| `telematics.night_driving` | β(a, b) × scale, max | Raw night-share draw, clipped. |
| `telematics.weights` | shares | Blend weights (must match the three inputs). |
| `telematics.score_max` / `.score_min` / `.score_span` | score | `score = clip(score_max − blend × score_span, score_min, score_max)` (higher = safer). |
| `behavior_risk.lo` / `.hi` | multiplier | Rank-mapped latent risk range; safest driver gets `lo`, riskiest `hi`. |

The observable telematics columns are **EV-only** (ICE rows are `NaN`):
`telematics_hard_braking`, `telematics_speeding`, `telematics_night_share`
(clipped raw draws), `telematics_blend` (weighted min-max blend),
`telematics_score` and `telematics_rank_pct`. The latent `BEHAVIOR_RISK` is
drawn for every vehicle and still drives frequency + retention.

## Retention

| Key | Unit | Meaning |
|---|---|---|
| `retention.base` | probability | Baseline renewal probability. |
| `retention.claim_delta` | pp | Applied when a claim occurred. |
| `retention.clean_delta` | pp | Applied when claim-free. |
| `retention.ncd3_bonus` / `.ncd2_bonus` | pp | Loyalty bonuses at NCD ≥ 3 / ≥ 2. |
| `retention.telematics_high` | threshold + bonus + span | Safe-driver bonus scaling to the score. |
| `retention.telematics_mid` | threshold + bonus | Mid-score flat bonus. |
| `retention.behavior_penalty` | pp per unit | Penalty proportional to `BEHAVIOR_RISK − 1`. |
| `retention.clip` | [lo, hi] | Final probability clip. |

## Scenario files

Reserved keys in a scenario entry:

| Key | Meaning |
|---|---|
| `name` | Scenario name; used in result file names. |
| `enabled` | `false` skips the scenario (default true). Toggle to run a subset without deleting entries or passing `--scenarios`. |
| `vehicle` | Allocation dict only: `{"ICE": 0.0, "EV": 1.0}` (EV-only) or `{"ICE": 0.6, "EV": 0.4}` (mixed). Absent → template `vehicle_ramp.from`. Zero weights are dropped (0% behaves as absent). |
| `seed` | Runs this scenario once with this seed (overrides `seeds.json`). |

Everything else patches the template keys above (deep merge for nested dicts).

## Seeds

`seeds.json` — `{"seeds": [0, 1, 2]}`. Every scenario runs once per seed unless
it patches `seed`. Result files are always seed-suffixed:
`results/<scenario>_s<seed>.csv`, with exactly the schema columns (simulation
data: attributes + claims; never premium).
