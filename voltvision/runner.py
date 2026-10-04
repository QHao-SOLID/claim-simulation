"""The loop: for each scenario × seed → simulate → save one CSV per table.

Output (all in `out`, default results/):
  <scenario>_s<seed>.csv         policy-year rows, columns = schema.COLS
  <scenario>_s<seed>_claims.csv  one row per claim, columns = schema.CLAIM_COLS
  manifest.json                  provenance: files, run facts, cfg + SHA-256

Simulation data only — never premium. The engine is premium-independent:
same seed + same cfg = identical files.
"""

import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from .assumptions import (
    build_cfg, deep_merge, describe_patch, load_seeds, load_template,
)
from .simulate import normalize_mix, simulate_book
from . import io


def load_scenario_groups(grid):
    """Scenario groups from a directory of *.json files (or a single file).

    Each file is a JSON list of scenario dicts; the file stem becomes the
    group name. Returns [(group_name, [scenario, ...]), ...] in file order.
    """
    p = Path(grid)
    files = sorted(p.glob('*.json')) if p.is_dir() else [p]
    if not files:
        raise FileNotFoundError(f'no scenario files found in {grid}')
    groups = []
    for f in files:
        scenarios = json.loads(f.read_text(encoding='utf-8'))
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError(f'{f.name}: expected a non-empty JSON list of scenarios')
        groups.append((f.stem, scenarios))
    return groups


def resolve_vehicle(vehicle, cfg):
    """Vehicle allocation for one scenario.

    Explicit allocation dict wins (e.g. {"ICE": 0.0, "EV": 1.0} for an
    EV-only book); absent -> the template's `vehicle_ramp.from`. Zero weights
    are dropped, so a fuel at 0% behaves exactly like an absent fuel.
    """
    if vehicle is None:
        return normalize_mix(cfg['vehicle_ramp']['from'])
    if not isinstance(vehicle, dict):
        raise ValueError(
            f'vehicle must be an allocation dict, e.g. {{"ICE": 0.0, "EV": 1.0}} '
            f'or {{"ICE": 0.6, "EV": 0.4}} — got {vehicle!r}')
    unknown = set(vehicle) - set(cfg['vehicle_ramp']['from'])
    if unknown:
        raise ValueError(f'vehicle has unknown fuel(s) {sorted(unknown)} — '
                         f'known: {sorted(cfg["vehicle_ramp"]["from"])}')
    return normalize_mix(vehicle)


def _summary(book, claims, vehicle, policy_path):
    """One line of run facts (all simulation-side, no premium)."""
    return {
        'policies': int(book['POLID'].nunique()),
        'rows': len(book),
        'claims': len(claims),
        'claim_amount': round(float(book['CLAIM_AMOUNT'].sum()), 2),
        'freq': round(float(book['CLAIM_OCCURRED'].mean()), 4),
        'vehicle': vehicle,
        'file': Path(policy_path).name,
    }


def run_scenarios(grid='scenarios', template=None, scenario_names=None,
                  seeds=None, quick=False, out=None, verbose=True):
    """Execute scenario groups and write CSVs + manifest per (scenario, seed).

    grid            directory of scenario JSON files (or one file)
    template        base assumptions dict (default: base_template.json)
    scenario_names  optional subset filter by scenario name
    seeds           optional explicit seed list (default: seeds.json, else
                    the template seed; a scenario patching 'seed' runs once)
    quick           smoke mode: n=1000, n_years=2
    out             output directory (default: results/)

    Returns a tidy DataFrame: scenario, seed, policies, rows, claims,
    claim_amount, freq, vehicle, file.
    """
    base = template if template is not None else load_template()
    if quick:
        base = deep_merge(base, {'n': 1000, 'n_years': 2})
    seed_list = seeds if seeds is not None else (load_seeds() or [base['seed']])

    rows = []
    for group, scenarios in load_scenario_groups(grid):
        selected = [s for s in scenarios
                    if s.get('enabled', True) is not False
                    and (not scenario_names or s['name'] in scenario_names)]
        skipped = [s['name'] for s in scenarios if s.get('enabled', True) is False]
        if verbose and skipped:
            print(f"\n=== {group} | skip (disabled): {', '.join(skipped)}")
        if not selected:
            continue
        for scenario in selected:
            name = scenario['name']
            cfg = build_cfg(base, scenario)
            vehicle = resolve_vehicle(scenario.get('vehicle'), cfg)
            scenario_seeds = [scenario['seed']] if 'seed' in scenario else seed_list
            cfg_sha256 = hashlib.sha256(
                json.dumps(cfg, sort_keys=True, default=str).encode('utf-8')).hexdigest()

            if verbose:
                print(f"\n=== {group} / {name} | vehicle={vehicle} "
                      f"| seeds={scenario_seeds}")
                for line in describe_patch(base, scenario):
                    print(f"    patch {line}")

            for seed in scenario_seeds:
                started = time.time()
                book, claims = simulate_book(cfg, vehicle, seed,
                                             n_years=cfg['n_years'],
                                             return_claims=True)
                policy_path = io.save_csv(name, seed, book, out=out)
                claims_path = io.save_claims_csv(name, seed, claims, out=out)
                summary = _summary(book, claims, vehicle, policy_path)
                rows.append({'scenario': name, 'seed': seed, **summary})
                io.update_manifest(io.result_stem(name, seed), {
                    'scenario': name,
                    'seed': int(seed),
                    'files': [policy_path.name, claims_path.name],
                    'rows': summary['rows'],
                    'policies': summary['policies'],
                    'claims': summary['claims'],
                    'claim_amount': summary['claim_amount'],
                    'freq': summary['freq'],
                    'vehicle': vehicle,
                    'cfg_sha256': cfg_sha256,
                    'cfg': cfg,
                }, out=out)
                if verbose:
                    print(f"    seed {seed} | rows {summary['rows']} "
                          f"| claims {summary['claims']} "
                          f"| claim amount RM{summary['claim_amount']:,.0f} "
                          f"| freq {summary['freq']:.2%} "
                          f"-> {policy_path.name}, {claims_path.name} "
                          f"({time.time() - started:.0f}s)")

    return pd.DataFrame(rows)
