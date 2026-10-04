# Claim Simulation — premium-independent motor book simulator

Two packages, one dependency direction:

| Package | Role |
|---|---|
| `voltvision/` | **Core** — the simulation generator (engine + runner + panel API). Knows nothing about pricing or the competition. |
| `competition/` | **Application** — Excel-first pricing competition built on `voltvision` (imports its public API; the engine never imports it). |

The engine simulates policy attributes and claims only — **no premium is ever
simulated or priced**, so same seed + same cfg = identical output. Scenario
JSON files go in; per scenario × seed: a policy-year CSV, a claim-level CSV,
and a manifest come out.

## Quickstart

```bash
pip install -e .                          # installs voltvision + competition deps
pip install pytest                        # tests only

python run_scenarios.py --quick          # smoke: n=1000, 2 years -> results/
python run_scenarios.py                  # full sweep: all scenarios x seeds.json
python run_scenarios.py --scenarios MIX,base --seeds 42
python run_scenarios.py --grid scenarios/frequency.json --out my_results
python -m pytest -q                      # test suite
```

## Competition (Excel-first)

`competition/` turns the simulator into a pricing competition: Python
generates one public workbook (base-world train + combined all-scenario test
set), teams price the held-out set in Excel, and one master workbook merges
all team prices and compares. Cheapest premium wins each policy; ties split
equally; any scenario LR ≥ 100% disqualifies overall. See
[`competition/README.md`](competition/README.md).

```bash
python -m competition.build_dataset      # public + hidden truth + master (parallel)
python -m competition.make_master        # rebuild master after editing teams.txt
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
`telematics_blend`, `telematics_rank_pct` — drawn for every vehicle) and
`telematics_score` (EV-only; ICE rows `NaN`). Never a premium column.

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
├─ pyproject.toml        packaging: voltvision + competition, deps
├─ base_template.json   simulation assumptions (single source of truth)
├─ TEMPLATE.md          every template/scenario key: unit + effect
├─ seeds.json           seeds each scenario runs unless it patches its own
├─ scenarios/*.json     scenario groups (flat patches on the template)
├─ run_scenarios.py     CLI: scenarios in -> CSV out
├─ results/             generated CSVs + manifest.json
├─ voltvision/          CORE — simulation generator (no competition imports)
│  ├─ schema.py         COLS / CLAIM_COLS — canonical column order
│  ├─ assumptions.py    template + scenario patches + seeds (validation)
│  ├─ simulate.py       gen / claim_lambda / simulate / simulate_book,
│  │                    build_panel / replay_claims (public panel API)
│  ├─ io.py             CSV + manifest write (simulation data only)
│  └─ runner.py         scenario x seed loop
├─ competition/         APPLICATION — pricing competition (imports voltvision)
│  ├─ build_dataset.py  factory: public + hidden truth + master workbooks
│  ├─ workbooks.py      xlsx writers (public, truth, master scoring)
│  ├─ make_master.py    rebuild master from saved artifacts
│  ├─ sanitize.py       public/hidden column whitelists
│  ├─ rounds.json       scenario list — scale freely
│  └─ teams.txt         team names — scale freely
└─ tests/               pytest suite (engine + competition)
```

## Reproducibility

The engine uses a local RNG per book; draw order and float-expression
grouping in `simulate.py` are part of the result. Do not reorder RNG calls or
regroup arithmetic without re-verifying output.
