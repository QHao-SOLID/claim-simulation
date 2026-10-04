# Claim Simulation — premium-independent motor book simulator

Stripped-down simulation engine extracted from MET-X. Scenario JSON files go
in; per scenario × seed: a policy-year CSV, a claim-level CSV, and a manifest
come out. The engine simulates policy attributes and claims only — **no
premium is ever simulated or priced**, so same seed + same cfg = identical
output.

## Quickstart

```bash
pip install numpy pandas
pip install pytest                       # tests only

python run_scenarios.py --quick          # smoke: n=1000, 2 years -> results/
python run_scenarios.py                  # full sweep: all scenarios x seeds.json
python run_scenarios.py --scenarios MIX,base --seeds 42
python run_scenarios.py --grid scenarios/frequency.json --out my_results
python -m pytest -q                      # test suite
```

## Input — scenario files

`scenarios/*.json` — one file per group, a JSON list of scenario dicts:

```json
[
  {"name": "base"},
  {"name": "EV", "vehicle": {"EV": 1.0}},
  {"name": "freq_p10", "frequency_intensity": 1.10},
  {"name": "coverage_shift", "coverage_ramp": {"to": {"Comprehensive": 0.45, "TPFT": 0.20, "TPO": 0.35}}}
]
```

Every key besides the reserved `name`, `enabled`, `vehicle`, `seed` is a flat
patch on `base_template.json` (nested dicts merge key-by-key; unknown keys
fail loud). Full key reference: [`TEMPLATE.md`](TEMPLATE.md).

## Output — simulation data

`results/<scenario>_s<seed>.csv` — one row per policy-year, columns exactly
`schema.COLS`: policy attributes, claim counts/amounts/perils, renewal and NCD
state, flood-event marker, plus the full raw telematics block
(`telematics_hard_braking`, `telematics_speeding`, `telematics_night_share`,
`telematics_blend`, `telematics_score`, `telematics_rank_pct` — EV-only; ICE
rows `NaN`). Never a premium column.

`results/<scenario>_s<seed>_claims.csv` — one row per claim,
columns exactly `schema.CLAIM_COLS`: peril, sum assured, raw Gamma draw, cap,
total-loss flag, excess applied, inflation factor, settled payout.

`results/manifest.json` — provenance per run: files, rows, policies, claims,
claim amount, frequency, vehicle mix, cfg SHA-256 and the resolved cfg.

Realism note: own-damage partial payouts (AD/Fire) are inflated, excess-
subtracted, then capped at `max(SA − excess, 0)`; Theft always settles as a
total loss at the same limit. Third-party / windscreen claims keep their own
peril caps.

## Layout

```
├─ base_template.json   simulation assumptions (single source of truth)
├─ TEMPLATE.md          every template/scenario key: unit + effect
├─ seeds.json           seeds each scenario runs unless it patches its own
├─ scenarios/*.json     scenario groups (flat patches on the template)
├─ run_scenarios.py     CLI: scenarios in -> CSV out
├─ results/             generated CSVs + manifest.json
├─ tests/               pytest suite (frozen-template reproducibility fixture)
└─ voltvision/
   ├─ schema.py         COLS / CLAIM_COLS — canonical column order
   ├─ assumptions.py    template + scenario patches + seeds (validation)
   ├─ simulate.py       the engine: gen / claim_lambda / simulate / simulate_book
   ├─ io.py             CSV + manifest write (simulation data only)
   └─ runner.py         scenario x seed loop
```

## Reproducibility

The engine uses a local RNG per book; draw order and float-expression
grouping in `simulate.py` are part of the result. Do not reorder RNG calls or
regroup arithmetic without re-verifying output.
