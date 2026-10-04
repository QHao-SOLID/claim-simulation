"""Assumptions loader: base_template.json + scenario patches + seeds.

The template is the single source of truth for SIMULATION assumptions.
Scenarios are flat patches: keys present replace the base, everything else is
inherited; nested dicts merge key-by-key. Unknown keys are rejected with a
pointer to TEMPLATE.md. No pricing keys exist — the simulation is
premium-independent.
"""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / 'base_template.json'
SEEDS_PATH = ROOT / 'seeds.json'

# Every key a template (or scenario patch) may contain. Anything else errors.
# Keep in sync with TEMPLATE.md.
TEMPLATE_KEYS = [
    # run controls
    'n', 'cohort_year', 'n_years', 'seed',
    'vehicle_ramp', 'coverage_ramp',
    # claim-experience levers
    'flood_event_prob', 'severity_inflation',
    'entrant_growth', 'sa_depreciation', 'sa_min',
    # book composition
    'region_pct', 'generation_pct', 'age_bands', 'gender_pct',
    'car_age_median', 'car_age_sigma', 'sa_stats', 'engine_bands',
    'engine_weights', 'entrant_frac',
    # ncd
    'ncd_table', 'ncd_entry',
    # frequency
    'claim_frequency_base', 'frequency', 'frequency_intensity', 'risk_flags',
    # loadings / aging
    'aging',
    # severity
    'severity', 'peril_dist', 'severity_multiplier',
    # telematics & retention
    'telematics', 'behavior_risk', 'retention',
]

# Keys the runner consumes directly; never merged into the simulation cfg.
SCENARIO_RESERVED = ('name', 'vehicle', 'enabled')


def deep_merge(base, patch):
    """Recursive merge: dicts merge key-by-key, everything else replaces.

    Returns a new dict; inputs are never mutated (patches stay reusable).
    """
    out = {k: (copy.deepcopy(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _check_keys(d, where):
    unknown = [k for k in d if k not in TEMPLATE_KEYS]
    if unknown:
        raise KeyError(f"unknown key(s) in {where}: {unknown} — see TEMPLATE.md for the key list")


def _normalize(cfg):
    # JSON keys are strings; the NCD table is looked up by integer year.
    cfg['ncd_table'] = {int(k): v for k, v in cfg['ncd_table'].items()}
    return cfg


def load_template(path=None):
    """Read base_template.json (validated, normalized). Returns the base cfg."""
    p = Path(path) if path else TEMPLATE_PATH
    cfg = json.loads(p.read_text(encoding='utf-8'))
    _check_keys(cfg, p.name)
    cfg = _normalize(cfg)
    validate(cfg)
    return cfg


def load_seeds(path=None):
    """Read seeds.json. Returns a list of ints, or None when the file is absent.

    Accepted shapes: [0, 1, 2] or {"seeds": [0, 1, 2]}.
    """
    p = Path(path) if path else SEEDS_PATH
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding='utf-8'))
    seeds = data['seeds'] if isinstance(data, dict) else data
    if not isinstance(seeds, list) or not seeds:
        raise ValueError(f'{p.name}: expected a non-empty list of seeds')
    return [int(s) for s in seeds]


def build_cfg(template, scenario):
    """Merge one scenario patch onto the template → run cfg.

    Reserved runner keys (name, vehicle, enabled) are ignored here; `seed`
    stays in the cfg because it is also a template key.
    """
    patch = {k: v for k, v in scenario.items() if k not in SCENARIO_RESERVED}
    _check_keys(patch, f"scenario {scenario.get('name')!r}")
    return _normalize(deep_merge(template, patch))


def _validate_ramp(ramp, name, required_keys):
    """Validate a ramp's `from`/`to` mix dicts against a required key set.

    `from` is required (it is the base allocation); `to` is optional (absent =
    static book). Both, when present, must be full share dicts over exactly
    `required_keys` with weights in [0, 1].
    """
    if not isinstance(ramp, dict) or 'from' not in ramp:
        raise ValueError(f'{name} requires a `from` mix (the base allocation)')
    for key in ('from', 'to'):
        mix = ramp.get(key)
        if mix is None:
            continue
        if not isinstance(mix, dict) or set(mix) != required_keys:
            raise ValueError(f'{name}.{key} keys {sorted(mix)} must equal '
                             f'{sorted(required_keys)}')
        for k, w in mix.items():
            if not isinstance(w, (int, float)) or not 0.0 <= w <= 1.0:
                raise ValueError(f'{name}.{key}.{k} must be a share within [0, 1] — '
                                 f'got {w!r}')


def validate(cfg):
    """Fail loud on inconsistent assumptions. Returns cfg for chaining."""
    # Bands: one weight per band.
    if len(cfg['engine_bands']) != len(cfg['engine_weights']):
        raise ValueError('engine_bands and engine_weights length mismatch')
    # Severity: perils == spec keys == union of peril_dist keys.
    perils = cfg['severity']['perils']
    specs = set(cfg['severity']['specs'])
    if set(perils) != specs:
        raise ValueError(f'severity.perils {sorted(perils)} != specs {sorted(specs)}')
    used = {p for dist in cfg['peril_dist'].values() for p in dist}
    if used - specs:
        raise ValueError(f'peril_dist references unknown perils: {sorted(used - specs)}')
    # Every coverage in peril_dist must equal the base coverage mix keys.
    cramp = cfg['coverage_ramp']
    _validate_ramp(cramp, 'coverage_ramp', required_keys=set(cfg['peril_dist']))
    if set(cfg['peril_dist']) != set(cramp['from']):
        raise ValueError('peril_dist and coverage_ramp.from cover different coverages')
    # Risk flags must know every region.
    for flag, by_region in cfg['risk_flags'].items():
        missing = set(cfg['region_pct']) - set(by_region)
        if missing:
            raise ValueError(f'risk_flags.{flag} missing regions: {sorted(missing)}')
    # Fuel stats must match the base vehicle mix keys.
    vramp = cfg['vehicle_ramp']
    _validate_ramp(vramp, 'vehicle_ramp', required_keys=set(cfg['sa_stats']))
    if set(cfg['sa_stats']) != set(vramp['from']):
        raise ValueError(f'sa_stats must cover fuels {sorted(vramp["from"])}')
    _validate_claim_levers(cfg)
    return cfg


def _validate_claim_levers(cfg):
    """Validate the claim-experience levers and settlement specs."""
    missing = set(cfg['region_pct']) - set(cfg.get('flood_event_prob', {}))
    if missing:
        raise ValueError(f'flood_event_prob missing regions: {sorted(missing)}')
    for region, prob in cfg['flood_event_prob'].items():
        if not 0.0 <= prob <= 1.0:
            raise ValueError(f'flood_event_prob[{region!r}] must be within [0, 1] — got {prob!r}')
    for key, hi in (('severity_inflation', 0.25), ('entrant_growth', 0.5),
                    ('sa_depreciation', 0.5)):
        value = cfg.get(key, 0.0)
        if not 0.0 <= value <= hi:
            raise ValueError(f'{key} must be within [0, {hi}] — got {value!r}')
    intensity = cfg.get('frequency_intensity', 1.0)
    if not 0.0 <= intensity <= 5.0:
        raise ValueError(f'frequency_intensity must be within [0, 5] — got {intensity!r}')
    if cfg.get('sa_min', 0) <= 0:
        raise ValueError('sa_min must be positive')
    for peril, spec in cfg['severity']['specs'].items():
        payout = spec.get('payout', 'partial')
        if payout not in ('partial', 'total', 'mixed'):
            raise ValueError(f'severity.specs[{peril!r}].payout must be '
                             f"partial | total | mixed — got {payout!r}")
        if payout == 'mixed':
            prob = spec.get('total_loss_prob')
            if not isinstance(prob, (int, float)) or not 0.0 <= prob <= 1.0:
                raise ValueError(f'severity.specs[{peril!r}].total_loss_prob must be '
                                 f'within [0, 1] — got {prob!r}')
        for key in ('excess', 'young_excess'):
            if key in spec and spec[key] < 0:
                raise ValueError(f'severity.specs[{peril!r}].{key} must be >= 0')


def describe_patch(template, scenario):
    """Plain-English diff of a scenario against the template (runner log).

    Returns lines like: 'coverage_ramp.to.TPO: 0.15 -> 0.35'. Reserved keys are
    listed as-is (vehicle/seed are shown by the runner separately).
    """
    lines = []

    def walk(prefix, base, patch):
        for k, v in patch.items():
            path = f'{prefix}{k}'
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                walk(path + '.', base[k], v)
            else:
                lines.append(f'{path}: {base.get(k)!r} -> {v!r}')

    walk('', template, {k: v for k, v in scenario.items() if k not in SCENARIO_RESERVED})
    return lines
