import numpy as np
import pandas as pd

from voltvision.assumptions import deep_merge, load_template
from voltvision.schema import CLAIM_COLS, COLS
from voltvision.simulate import simulate_book

from conftest import FROZEN_TEMPLATE

# Pinned reproducibility reference (frozen fixture, n=200, 2 years, seed
# 20260916). Update only when simulate.py changes intentionally.
PINNED_ROWS = 400
PINNED_HASH = 11932143242030860547


def make_cfg():
    base = load_template(FROZEN_TEMPLATE)
    return deep_merge(base, {'n': 200, 'n_years': 2, 'seed': 42})


def test_book_columns_and_reproducibility():
    cfg = make_cfg()
    b1 = simulate_book(cfg, cfg['vehicle_ramp']['from'], 20260916, n_years=2)
    b2 = simulate_book(cfg, cfg['vehicle_ramp']['from'], 20260916, n_years=2)
    assert isinstance(b1, pd.DataFrame)
    assert list(b1.columns) == COLS
    assert len(b1) == PINNED_ROWS
    assert b1.equals(b2)
    assert int(pd.util.hash_pandas_object(b1).sum()) == PINNED_HASH


def test_flood_event_year_is_boolean():
    cfg = make_cfg()
    book = simulate_book(cfg, cfg['vehicle_ramp']['from'], 20260916, n_years=2)
    assert book['FLOOD_EVENT_YEAR'].dtype == bool


def test_claims_frame_and_settlement_invariants():
    cfg = make_cfg()
    book, claims = simulate_book(cfg, cfg['vehicle_ramp']['from'], 20260916,
                                 n_years=2, return_claims=True)
    assert list(claims.columns) == CLAIM_COLS
    assert len(claims) == int(book['CLAIM_COUNT'].sum())
    assert (claims['SETTLED_PAYOUT'] >= 0).all()
    assert (claims['RAW_GAMMA'] >= 0).all()
    assert (claims['INFLATION_FACTOR'] >= 1.0).all()

    own_damage = claims[claims['CLAIM_PERIL'].isin(['AD', 'Fire', 'Theft'])]
    limit = (own_damage['SUM_ASSURED'] - own_damage['EXCESS_APPLIED']).clip(lower=0)
    assert (own_damage['SETTLED_PAYOUT'] <= limit + 1e-9).all()

    theft = claims[claims['CLAIM_PERIL'] == 'Theft']
    if len(theft):
        assert theft['TOTAL_LOSS'].all()
        assert np.allclose(theft['SETTLED_PAYOUT'],
                           (theft['SUM_ASSURED'] - theft['EXCESS_APPLIED']).clip(lower=0))
        assert (theft['INFLATION_FACTOR'] == 1.0).all()

    partials = claims[claims['CLAIM_PERIL'].isin(['AD', 'Fire'])]
    if len(partials):
        assert partials[['TOTAL_LOSS']].notna().all().all()
