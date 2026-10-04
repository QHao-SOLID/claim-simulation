from voltvision.schema import CLAIM_COLS, COLS


def test_cols_unique_and_premium_free():
    assert len(COLS) == len(set(COLS))
    assert all(not c.upper().startswith('PREM') for c in COLS)


def test_claim_cols_unique_and_premium_free():
    assert len(CLAIM_COLS) == len(set(CLAIM_COLS))
    assert all(not c.upper().startswith('PREM') for c in CLAIM_COLS)


def test_flood_event_year_exposed():
    assert 'FLOOD_EVENT_YEAR' in COLS
