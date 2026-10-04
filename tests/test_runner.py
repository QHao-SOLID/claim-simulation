from voltvision.assumptions import load_template
from voltvision.runner import run_scenarios
from voltvision.schema import CLAIM_COLS, COLS

from conftest import FROZEN_TEMPLATE


def test_quick_run_writes_csvs_and_manifest(tmp_path):
    results = run_scenarios(grid='scenarios/base.json',
                            template=load_template(FROZEN_TEMPLATE),
                            scenario_names={'base'}, seeds=[42], quick=True,
                            out=tmp_path, verbose=False)
    assert len(results) == 1
    row = results.iloc[0]
    assert row['scenario'] == 'base' and row['seed'] == 42
    assert row['claims'] > 0

    policy = tmp_path / 'base_s42.csv'
    claims = tmp_path / 'base_s42_claims.csv'
    manifest_file = tmp_path / 'manifest.json'
    assert policy.exists() and claims.exists() and manifest_file.exists()

    import pandas as pd

    p = pd.read_csv(policy)
    c = pd.read_csv(claims)
    assert list(p.columns) == COLS
    assert list(c.columns) == CLAIM_COLS
    assert all(not col.upper().startswith('PREM') for col in p.columns)

    import json

    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    entry = manifest['base_s42']
    assert entry['files'] == ['base_s42.csv', 'base_s42_claims.csv']
    assert entry['vehicle'] == {'ICE': 0.96, 'EV': 0.04}
    assert len(entry['cfg_sha256']) == 64
    assert entry['cfg']['n'] == 1000
