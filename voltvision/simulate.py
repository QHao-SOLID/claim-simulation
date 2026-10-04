"""Premium-independent simulation engine (bread and butter).

What lives here:
  gen()           builds one book of policies (risk attributes only, no claims,
                  no premium). Used for the starting book (INIT) and yearly
                  entrants (ENT). Every number comes from cfg (base_template).
  claim_lambda()  Poisson rate per policy: log-linear rating model.
  simulate()      evolves a book year by year: age → frequency → peril →
                  severity → retention → NCD update → entrants.
  simulate_book() convenience wrapper (gen + simulate) for callers that need
                  a complete book.

Contract:
  - Output columns follow schema.COLS (POLID first); never premium columns.
  - Same seed + same cfg = identical book (local RNG, no globals).
    - Draw ORDER is part of reproducibility: helper order and float-expression
    grouping are fixed so refactors stay number-identical.
"""

import numpy as np
import pandas as pd

from .schema import CLAIM_COLS, COLS


def normalize_weights(weights):
    """Turn any weights into probabilities summing to exactly 1.

    np.random.choice rejects floats that sum to 0.9999999; normalizing keeps
    the callers free of epsilon guards.
    """
    a = np.array(list(weights), float)
    return a / a.sum()


# Weights below this are float dust (e.g. 1 - 0.4000000000000001): treat as 0.
_ZERO_TOL = 1e-12


def normalize_mix(mix):
    """Validate a vehicle allocation and drop zero-weight fuels.

    A fuel at 0% behaves as if absent — this keeps the random draw identical
    to a single-fuel book (same RNG stream), so `{"ICE": 0.0, "EV": 1.0}` and
    the old one-key form give the same book. Key order is preserved because
    the draw order is part of reproducibility (keep ICE, EV).
    """
    if not isinstance(mix, dict) or not mix:
        raise ValueError(f'vehicle mix must be a non-empty dict, got {mix!r}')
    clean = {}
    for fuel, weight in mix.items():
        if weight < -_ZERO_TOL:
            raise ValueError(f'vehicle mix weight for {fuel!r} is negative: {weight}')
        if weight > _ZERO_TOL:
            clean[fuel] = float(weight)
    if not clean:
        raise ValueError(f'vehicle mix has no positive weight: {mix!r}')
    return clean


def ramp_progress(cfg, year):
    """Linear 0..1 progress across the simulation window.

    Shared by `vehicle_ramp` and `coverage_ramp`: 0 at `cohort_year`, 1 at the
    final window year; `n_years == 1` stays at 0 (the `from` mix).
    """
    start = int(cfg['cohort_year'])
    span = int(cfg['n_years']) - 1
    return 0.0 if span <= 0 else min(max((int(year) - start) / span, 0.0), 1.0)


def blend_mix(start_mix, end_mix, t, order=None):
    """Componentwise linear blend of two mass vectors.

    Same logic for every ramp: `start + t x (end - start)`. Iteration order is
    preserved (default: `start_mix` key order; `order` overrides) because the
    categorical draw order is part of reproducibility.
    """
    return {k: start_mix[k] + t * (end_mix[k] - start_mix[k]) for k in (order or start_mix)}


def entrant_vehicle_mix(cfg, base_mix, year):
    """Vehicle allocation for ONE entrant cohort (new business in `year`).

    The base mix is `vehicle_ramp.from` (or the scenario's `vehicle` override).
    With a `to` mix the shares interpolate linearly `from` -> `to` across the
    simulation window (cohort_year .. cohort_year + n_years - 1); `n_years == 1`
    uses `from`. No `to` -> entrants keep the base mix.
    """
    ramp = cfg.get('vehicle_ramp') or {}
    if 'to' not in ramp:
        return normalize_mix(base_mix)
    return normalize_mix(blend_mix(base_mix, ramp['to'], ramp_progress(cfg, year),
                                   order=list(base_mix)))


def coverage_mix_at(cfg, year):
    """Coverage allocation for ONE cohort (inception or new business in `year`).

    The base mix is `coverage_ramp.from`; with a `to` mix the shares are
    interpolated linearly across the window, using the same ramp as
    `vehicle_ramp`. Iterates `from` key order so the categorical draw stream
    stays fixed.
    """
    ramp = cfg.get('coverage_ramp') or {}
    start = ramp['from']
    if 'to' not in ramp:
        return start
    return blend_mix(start, ramp['to'], ramp_progress(cfg, year), order=list(start))


# ---------------------------------------------------------------------------
# Book generation, split into named steps (called in order by gen()).
# ---------------------------------------------------------------------------

def _draw_product_mix(cfg, vehicle_pct, rng, n, coverage_mix=None):
    """Coverage, fuel type and region — three independent categorical draws."""
    df = pd.DataFrame(index=range(n))
    vehicle_mix = normalize_mix(vehicle_pct)
    mix = cfg['coverage_ramp']['from'] if coverage_mix is None else coverage_mix
    df['COVERAGE_TYPE'] = rng.choice(list(mix),
                                     p=normalize_weights(mix.values()), size=n)
    df['VEHICLE_TYPE'] = rng.choice(list(vehicle_mix),
                                    p=normalize_weights(vehicle_mix.values()), size=n)
    df['REGION'] = rng.choice(list(cfg['region_pct']),
                              p=normalize_weights(cfg['region_pct'].values()), size=n)
    return df


def _draw_sum_assured(df, cfg, rng, n):
    """Log-normal sum assured per fuel type, rounded to RM1,000 (tariff steps)."""
    sa = np.zeros(n)
    for fuel, stats in cfg['sa_stats'].items():
        mask = df['VEHICLE_TYPE'].values == fuel
        sa[mask] = rng.lognormal(np.log(stats['median']), stats['spread'], int(mask.sum()))
    df['SUM_ASSURED'] = np.round(sa / 1000) * 1000


def _draw_engine_bands(df, cfg, rng, n):
    """Engine / EV-kW tariff band — a vehicle attribute the book carries."""
    df['ENGINE_CAPACITY'] = rng.choice(cfg['engine_bands'],
                                       p=normalize_weights(cfg['engine_weights']), size=n)


def _draw_driver_profile(df, cfg, rng, n):
    """Generation band first, then an exact age inside the band's span."""
    df['DRIVER_AGE_CAT'] = rng.choice(list(cfg['generation_pct']),
                                      p=normalize_weights(cfg['generation_pct'].values()), size=n)
    lo = np.array([cfg['age_bands'][c][0] for c in df['DRIVER_AGE_CAT']])
    hi = np.array([cfg['age_bands'][c][1] for c in df['DRIVER_AGE_CAT']])
    df['DRIVER_AGE'] = rng.integers(lo, hi)
    df['DRIVER_GENDER'] = rng.choice(list(cfg['gender_pct']),
                                     p=normalize_weights(cfg['gender_pct'].values()), size=n)


def _draw_car_age(df, cfg, rng, n):
    """Inception car age: band median + noise, clipped to 0–10 years."""
    car_age = np.zeros(n)
    for band, median in cfg['car_age_median'].items():
        mask = df['DRIVER_AGE_CAT'].values == band
        age = np.round(median + rng.normal(0, cfg['car_age_sigma'], int(mask.sum())))
        car_age[mask] = np.clip(age, 0, 10)
    df['CAR_AGE'] = car_age.astype(int)


def _draw_risk_flags(df, cfg, rng, n):
    """Flood / theft booleans, drawn per region in order of first appearance.

    The template stores P(True); the draw is `random() > 1 - p`, which is the
    legacy comparison exactly (keeping historical results reproducible).
    """
    flood = np.zeros(n, bool)
    theft = np.zeros(n, bool)
    for region in df['REGION'].unique():
        mask = df['REGION'].values == region
        count = int(mask.sum())
        flood[mask] = rng.random(count) > round(1.0 - cfg['risk_flags']['flood'][region], 12)
        theft[mask] = rng.random(count) > round(1.0 - cfg['risk_flags']['theft'][region], 12)
    df['FLOOD_RISK'] = flood
    df['THEFT_RISK'] = theft


def _draw_ncd_entry(df, cfg, rng, n):
    """Starting NCD years per policy (mix from the template), then the tier."""
    entry = cfg['ncd_entry']
    df['NCD_YEARS'] = rng.choice(entry['years'],
                                 p=normalize_weights(entry['weights']), size=n)
    df['NCD_LEVEL'] = df['NCD_YEARS'].map(lambda y: cfg['ncd_table'][min(int(y), 5)])


def _draw_telematics(df, cfg, rng, n):
    """Raw driving signals → one safe-score (20–100) → latent BEHAVIOR_RISK.

    Score: blend of min-maxed harsh braking / speeding / night share.
    Behavior risk: rank-map the score onto [lo, hi] so the worst driver always
    gets `hi` and the shape stays uniform whatever the raw gammas do.

    All raw signals are kept in the output (clipped draws, blend, rank); the
    device columns are withheld from ICE rows further down.
    """
    tel = cfg['telematics']
    hb = tel['hard_braking']
    raw_hb = np.clip(rng.gamma(hb['shape'], hb['scale'], size=n), 0, hb['max'])
    sp = tel['speeding']
    raw_sp = np.clip(rng.gamma(sp['shape'], sp['scale'], size=n), 0, sp['max'])
    nd = tel['night_driving']
    raw_nd = np.clip(rng.beta(nd['a'], nd['b'], size=n) * nd['scale'], 0, nd['max'])
    df['telematics_hard_braking'] = raw_hb
    df['telematics_speeding'] = raw_sp
    df['telematics_night_share'] = raw_nd

    # Blend of min-maxed inputs. Written `weight * (x - min) / (max - min)`
    # (multiply before divide) to keep the legacy float rounding bit-exact.
    w = tel['weights']
    blend = (w['hard_braking'] * (raw_hb - raw_hb.min()) / (raw_hb.max() - raw_hb.min())
             + w['speeding'] * (raw_sp - raw_sp.min()) / (raw_sp.max() - raw_sp.min())
             + w['night_driving'] * (raw_nd - raw_nd.min()) / (raw_nd.max() - raw_nd.min()))
    df['telematics_blend'] = blend
    df['telematics_score'] = np.clip(tel['score_max'] - blend * tel['score_span'],
                                     tel['score_min'], tel['score_max'])

    br = cfg['behavior_risk']
    rank_pct = np.argsort(np.argsort(df['telematics_score'].values)) / (max(n - 1, 1))
    df['telematics_rank_pct'] = rank_pct
    df['BEHAVIOR_RISK'] = br['hi'] - (br['hi'] - br['lo']) * rank_pct
    # Telematics device data only exists for EVs (can't instrument ICE). The
    # latent BEHAVIOR_RISK above stays for every vehicle; every observable
    # device signal (raw, blend, score, rank) is withheld from ICE rows.
    device_cols = ['telematics_hard_braking', 'telematics_speeding',
                   'telematics_night_share', 'telematics_blend',
                   'telematics_score', 'telematics_rank_pct']
    df.loc[df['VEHICLE_TYPE'].values != 'EV', device_cols] = np.nan


def _make_policy_ids(df, year, prefix, n):
    """Deterministic IDs: prefix + cohort year + running sequence."""
    df['POLID'] = [f"{prefix}{year}-{i + 1:06d}" for i in range(n)]


def gen(cfg, vehicle_pct, seed, year=None, prefix='INIT', n=None, coverage_mix=None):
    """Build one book of n policies from cfg — attributes only.

    No claims, no premium, no SIM_YEAR yet; steps run in the legacy order so
    results stay reproducible against previous versions. `coverage_mix`
    overrides the coverage draw for this cohort (ramps); None = template mix.
    """
    n = int(n or cfg['n'])
    rng = np.random.default_rng(seed)
    yr = year or cfg['cohort_year']

    df = _draw_product_mix(cfg, vehicle_pct, rng, n, coverage_mix=coverage_mix)
    _draw_sum_assured(df, cfg, rng, n)
    _draw_engine_bands(df, cfg, rng, n)
    _draw_driver_profile(df, cfg, rng, n)
    _draw_car_age(df, cfg, rng, n)
    _draw_risk_flags(df, cfg, rng, n)
    _draw_ncd_entry(df, cfg, rng, n)
    df['COHORT_YEAR'] = yr
    _draw_telematics(df, cfg, rng, n)
    _make_policy_ids(df, yr, prefix, n)
    return df


# ---------------------------------------------------------------------------
# Rating pieces (used by the engine).
# ---------------------------------------------------------------------------

def claim_lambda(df, cfg):
    """Poisson claim rate per policy (claims per year).

    Log-linear: start from the base log-rate, add rating factors in log space
    (so they multiply), exponentiate, then scale by coverage (TPO has no
    own-damage; TPFT fire/theft only).
    """
    freq = cfg['frequency']
    cat = df['DRIVER_AGE_CAT'].values
    # Flood is an EVENT: the flag marks exposure, but the loading only bites
    # in river-basin flood years (`FLOOD_EVENT_YEAR` per row, drawn per
    # region-year).
    flood_hit = df['FLOOD_RISK'].values
    if 'FLOOD_EVENT_YEAR' in df.columns:
        flood_hit = flood_hit * df['FLOOD_EVENT_YEAR'].values
    # Expression grouping mirrors the legacy code (sums are added as groups)
    # so float rounding — and therefore every historic result — is preserved.
    log_rate = (np.full(len(df), cfg['claim_frequency_base'])
                + freq['young_adult'] * (cat == 'Young Adults')
                + freq['senior'] * (cat == 'Seniors'))
    log_rate += (freq['young_male'] * ((cat == 'Young Adults') & (df['DRIVER_GENDER'].values == 'Male'))
                 + freq['ev'] * (df['VEHICLE_TYPE'].values == 'EV'))
    log_rate += (freq['flood'] * flood_hit
                 + freq['theft'] * df['THEFT_RISK'].values
                 + np.log(df['BEHAVIOR_RISK'].values))
    log_rate += (freq['car_age_per_year'] * df['CAR_AGE'].values
                 + freq['ncd_per_year'] * df['NCD_YEARS'].values)
    mult = df['COVERAGE_TYPE'].map(freq['coverage_multiplier']).values
    return np.exp(log_rate) * mult * cfg.get('frequency_intensity', 1.0)


# ---------------------------------------------------------------------------
# Severity helpers.
# ---------------------------------------------------------------------------

def draw_perils(coverage, count, rng, cfg):
    """Draw one peril name per claim from the coverage's mix.

    Mechanics: one uniform vector vs the cumulative mix (legacy draw — kept
    bit-identical; changing the mechanics would change every claim).
    """
    perils = cfg['severity']['perils']
    mix = np.array([[cfg['peril_dist'][c].get(p, 0.0) for p in perils] for c in coverage])
    idx = np.minimum((rng.random(count)[:, None] > np.cumsum(mix, axis=1)).sum(axis=1),
                     len(perils) - 1)
    return np.array(perils)[idx]


def severity_params(perils, sum_assured, cfg):
    """Per-claim Gamma shape / scale / cap arrays from the template specs.

    scale: absolute RM, or clip(SUM_ASSURED × sa_fraction, min, max).
    cap:   null (uncapped) | RM number | 'sum_assured'.
    The global severity multiplier applies to every peril.
    """
    specs = cfg['severity']['specs']
    sev_mult = cfg['severity_multiplier']
    shape = np.zeros(len(perils))
    scale = np.zeros(len(perils))
    cap = np.full(len(perils), np.inf)
    for name in cfg['severity']['perils']:
        spec = specs[name]
        mask = perils == name
        shape[mask] = spec['shape']
        if isinstance(spec['scale'], dict):
            rule = spec['scale']
            base = np.clip(sum_assured[mask] * rule['sa_fraction'], rule['min'], rule['max'])
            scale[mask] = base * sev_mult
        else:
            scale[mask] = spec['scale'] * sev_mult
        if spec['cap'] == 'sum_assured':
            cap[mask] = sum_assured[mask]
        elif spec['cap'] is not None:
            cap[mask] = spec['cap']
    return shape, scale, cap


def settle_claims(claim_amounts, perils, sum_assured, young, cfg, rng, year):
    """Settlement on top of the Gamma draws: total-loss rules + excesses.

    One simple rule per own-damage peril:
      Theft  -> always a total loss: payout = sum assured - excess
      Fire   -> mixed: total loss with prob `total_loss_prob`, else partial - excess
      AD     -> mixed: same shape; Young Adults carry `young_excess`
    Partial payouts are inflated to the claim year, excess-subtracted, then
    capped at `max(SA - excess, 0)` (the policy limit); a partial claim at or
    below the excess is not reported (payout 0). Total-loss payouts use the
    (renewal-depreciated) sum assured.

    Returns `(payouts, detail)` where `detail` carries the per-claim
    settlement breakdown (total-loss flag, excess applied, inflation factor)
    used for the claim-level CSV.
    """
    specs = cfg['severity']['specs']
    inflation = (1.0 + cfg.get('severity_inflation', 0.0)) ** (int(year) - int(cfg['cohort_year']))
    out = claim_amounts.copy()
    n = len(claim_amounts)
    total_loss = np.zeros(n, dtype=bool)
    excess_applied = np.zeros(n)
    inflation_applied = np.ones(n)
    for peril in ('AD', 'Fire', 'Theft'):
        spec = specs.get(peril)
        if not spec:
            continue
        mask = perils == peril
        if not mask.any():
            continue
        sa = sum_assured[mask]
        excess = np.where(young[mask], spec.get('young_excess', spec['excess']), spec['excess'])
        policy_limit = np.maximum(sa - excess, 0.0)
        excess_applied[mask] = excess
        payout = spec['payout']
        if payout == 'total':
            total_loss[mask] = True
            out[mask] = policy_limit
        else:
            total = rng.random(int(mask.sum())) < spec['total_loss_prob']
            partial = np.maximum(out[mask] * inflation - excess, 0.0)
            partial = np.minimum(partial, policy_limit)
            out[mask] = np.where(total, policy_limit, partial)
            total_loss[mask] = total
            inflation_applied[mask] = np.where(total, 1.0, inflation)
    detail = {
        'TOTAL_LOSS': total_loss,
        'EXCESS_APPLIED': excess_applied,
        'INFLATION_FACTOR': inflation_applied,
    }
    return out, detail


# ---------------------------------------------------------------------------
# Yearly evolution steps (called in order by simulate()).
# ---------------------------------------------------------------------------

def _age_inforce(book, year, cfg):
    """Age in-force policies by one year; upgrade bands at the cfg cutoffs.

    Also depreciates the sum assured at renewal (market value, floor `sa_min`)
    when `sa_depreciation` > 0 — lowers total-loss payouts and the tariff base
    with vehicle age.
    """
    aging = cfg['aging']
    mask = book['COHORT_YEAR'] < year
    if mask.any():
        book.loc[mask, 'DRIVER_AGE'] += 1
        book.loc[mask, 'CAR_AGE'] = np.minimum(book.loc[mask, 'CAR_AGE'] + 1, aging['car_age_cap'])
        book.loc[mask, 'DRIVER_AGE_CAT'] = np.select(
            [book.loc[mask, 'DRIVER_AGE'] <= aging['young_max'],
             book.loc[mask, 'DRIVER_AGE'] <= aging['adult_max'],
             book.loc[mask, 'DRIVER_AGE'] <= aging['mature_max']],
            ['Young Adults', 'Adults', 'Mature Adults'], default='Seniors')
        dep = cfg.get('sa_depreciation', 0.0)
        if dep > 0:
            floor = cfg.get('sa_min', 0)
            keep = np.round(book.loc[mask, 'SUM_ASSURED'] * (1 - dep) / 1000) * 1000
            book.loc[mask, 'SUM_ASSURED'] = np.maximum(keep, floor)


def _add_frequency(book, cfg, rng):
    """Claim counts: one Poisson draw per policy around its rate."""
    # NCD snapshot BEFORE this year's claims (priced NCD lags one year behind).
    book['NCD_LEVEL_PRICED'] = book['NCD_LEVEL']
    book['CLAIM_LAMBDA'] = claim_lambda(book, cfg)
    book['CLAIM_COUNT'] = rng.poisson(book['CLAIM_LAMBDA'].values)
    book['CLAIM_OCCURRED'] = book['CLAIM_COUNT'] > 0


def _add_severity(book, cfg, rng):
    """Per-claim severity: explode claimants → peril → Gamma → cap → regroup.

    Vectorized hot path kept for exact reproducibility:
      - one uniform vector draws all perils (see draw_perils),
      - one gamma call draws all amounts,
      - np.add.at regroups claim amounts in index order.
    Returns one row per claim (raw draw → settlement breakdown) for the
    claim-level CSV; empty frame when the year has no claims.
    """
    amount = np.zeros(len(book))
    peril_string = np.full(len(book), '', dtype=object)
    counts = book['CLAIM_COUNT'].values
    claimed = counts > 0
    if not claimed.any():
        book['CLAIM_AMOUNT'] = amount
        book['CLAIM_PERIL'] = peril_string
        return pd.DataFrame(columns=CLAIM_COLS)

    # One row per claim: repeat the claimant's index by its claim count.
    claim_index = np.repeat(np.flatnonzero(claimed), counts[claimed])
    coverage = book['COVERAGE_TYPE'].values[claim_index]
    sum_assured = book['SUM_ASSURED'].values[claim_index]
    perils = draw_perils(coverage, len(claim_index), rng, cfg)

    shape, scale, cap = severity_params(perils, sum_assured, cfg)
    raw_amounts = rng.gamma(shape, scale)
    claim_amounts = np.minimum(raw_amounts, cap)
    young = book['DRIVER_AGE_CAT'].values[claim_index] == 'Young Adults'
    claim_amounts, detail = settle_claims(claim_amounts, perils, sum_assured, young,
                                          cfg, rng, book['SIM_YEAR'].iloc[0])
    np.add.at(amount, claim_index, claim_amounts)

    # One peril string per policy; multiple claims joined by '/'.
    joined = pd.Series(perils).groupby(pd.Series(claim_index)).agg('/'.join)
    peril_string[np.flatnonzero(claimed)] = joined.values

    book['CLAIM_AMOUNT'] = amount
    book['CLAIM_PERIL'] = peril_string

    claims = pd.DataFrame({
        'POLID': book['POLID'].values[claim_index],
        'SIM_YEAR': book['SIM_YEAR'].values[claim_index],
        'COHORT_YEAR': book['COHORT_YEAR'].values[claim_index],
        'COVERAGE_TYPE': coverage,
        'VEHICLE_TYPE': book['VEHICLE_TYPE'].values[claim_index],
        'DRIVER_AGE_CAT': book['DRIVER_AGE_CAT'].values[claim_index],
        'CLAIM_PERIL': perils,
        'SUM_ASSURED': sum_assured,
        'RAW_GAMMA': raw_amounts,
        'CAP': cap,
        'TOTAL_LOSS': detail['TOTAL_LOSS'],
        'EXCESS_APPLIED': detail['EXCESS_APPLIED'],
        'INFLATION_FACTOR': detail['INFLATION_FACTOR'],
        'SETTLED_PAYOUT': claim_amounts,
    })
    return claims[CLAIM_COLS]


def _add_retention(book, cfg, rng):
    """Premium-independent renewal probability, then the renewal draw.

    Plain ndarray math (not Series) with the legacy expression grouping, so
    float rounding stays bit-identical.
    """
    ret = cfg['retention']
    p = np.full(len(book), ret['base']) - np.where(book['CLAIM_OCCURRED'].values,
                                                   -ret['claim_delta'], -ret['clean_delta'])
    p = p + np.select([book['NCD_YEARS'].values >= 3, book['NCD_YEARS'].values >= 2],
                      [ret['ncd3_bonus'], ret['ncd2_bonus']], default=0.0)
    score = book['telematics_score'].values
    high, mid = ret['telematics_high'], ret['telematics_mid']
    p = p + np.where(score >= high['threshold'],
                     high['bonus'] * (score - high['threshold']) / high['span'],
                     np.where(score >= mid['threshold'], mid['bonus'], 0.0))
    p = p - ret['behavior_penalty'] * (book['BEHAVIOR_RISK'].values - 1.0)
    book['RENEWAL_PROB'] = np.clip(p, ret['clip'][0], ret['clip'][1])
    book['RENEWED'] = rng.random(len(book)) < book['RENEWAL_PROB'].values


def _update_ncd(book, cfg):
    """NCD after the year: clean year earns a year, any claim resets to 0."""
    book.loc[~book['CLAIM_OCCURRED'], 'NCD_YEARS'] += 1
    book.loc[book['CLAIM_OCCURRED'], 'NCD_YEARS'] = 0
    book['NCD_LEVEL'] = book['NCD_YEARS'].map(lambda y: cfg['ncd_table'][min(int(y), 5)])


def _add_entrants(book, cfg, vehicle_pct, seed, year, n_years):
    """Yearly new business: fresh book, mix for THIS year (vehicle ramp aware).

    Entrant volume compounds with `entrant_growth` per year.
    """
    growth = cfg.get('entrant_growth', 0.0)
    count = int(cfg['n'] * cfg['entrant_frac'] * (1 + growth) ** (year - cfg['cohort_year']))
    mix = entrant_vehicle_mix(cfg, vehicle_pct, year)
    entrants = gen(cfg, mix, seed + (year - cfg['cohort_year']),
                   year=year, prefix='ENT', n=count,
                   coverage_mix=coverage_mix_at(cfg, year))
    return pd.concat([book[book['RENEWED']], entrants], ignore_index=True)


def _draw_flood_events(cfg, years, rng):
    """One flood-event draw per (region, year).

    Returns {year: {region: bool}}; a True year activates the flood loading
    for flood-flagged policies of that region (see claim_lambda).
    """
    probs = cfg['flood_event_prob']
    return {int(y): {r: bool(rng.random() < probs[r]) for r in sorted(probs)}
            for y in years}


# ---------------------------------------------------------------------------
# Main loop.
# ---------------------------------------------------------------------------

def simulate(df0, cfg, vehicle_pct, seed, n_years=None, verbose=True,
             return_claims=False):
    """Evolve a book across n_years: age → frequency → severity → retention →
    NCD → (survivors + entrants) → repeat.

    Returns the full history, one row per policy-year, columns = schema.COLS
    (including lapsers, so retention stays measurable). Never premium.
    With `return_claims=True` returns `(book, claims)`: the policy-year frame
    plus one row per claim (columns = schema.CLAIM_COLS).
    """
    n_years = int(n_years or cfg['n_years'])
    rng = np.random.default_rng(seed)
    active = df0.copy()
    history = []
    claim_frames = []
    years = [cfg['cohort_year'] + offset for offset in range(n_years)]
    flood_events = _draw_flood_events(cfg, years, rng)
    for offset in range(n_years):
        year = cfg['cohort_year'] + offset
        active['SIM_YEAR'] = year
        # Event marker for this year; consumed by claim_lambda's flood term.
        active['FLOOD_EVENT_YEAR'] = active['REGION'].map(flood_events[year]).astype(bool)

        _age_inforce(active, year, cfg)
        _add_frequency(active, cfg, rng)
        claims = _add_severity(active, cfg, rng)
        if return_claims and len(claims):
            claim_frames.append(claims)
        _add_retention(active, cfg, rng)
        _update_ncd(active, cfg)

        history.append(active[COLS].copy())
        if verbose:
            print(f"Year {year}: {len(active)} pols, claims {active['CLAIM_COUNT'].sum()}, "
                  f"freq {active['CLAIM_OCCURRED'].mean():.1%}")

        if offset < n_years - 1:
            active = _add_entrants(active, cfg, vehicle_pct, seed, year + 1, n_years)

    book = pd.concat(history, ignore_index=True)
    if not return_claims:
        return book
    all_claims = (pd.concat(claim_frames, ignore_index=True) if claim_frames
                  else pd.DataFrame(columns=CLAIM_COLS))
    return book, all_claims


# ---------------------------------------------------------------------------
# Convenience wrapper for callers that need a complete book.
# ---------------------------------------------------------------------------

def simulate_book(cfg, vehicle, seed, n_years=None, return_claims=False):
    """Simulate a full book in one call (gen + simulate)."""
    years = int(n_years or cfg['n_years'])
    return simulate(gen(cfg, vehicle, seed,
                        coverage_mix=coverage_mix_at(cfg, cfg['cohort_year'])),
                    cfg, vehicle, seed=seed, n_years=years, verbose=False,
                    return_claims=return_claims)
