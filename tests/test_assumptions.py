import pytest

from voltvision.assumptions import build_cfg, load_template
from voltvision.runner import resolve_vehicle

from conftest import FROZEN_TEMPLATE


def test_unknown_key_rejected():
    base = load_template(FROZEN_TEMPLATE)
    with pytest.raises(KeyError):
        build_cfg(base, {'name': 'bad', 'not_a_template_key': 1})


def test_patch_merges_deeply_and_keeps_reserved_keys_out_of_cfg():
    base = load_template(FROZEN_TEMPLATE)
    cfg = build_cfg(base, {'name': 'x', 'enabled': True,
                           'frequency_intensity': 1.2,
                           'retention': {'base': 0.5}})
    assert cfg['frequency_intensity'] == 1.2
    assert cfg['retention']['base'] == 0.5
    assert cfg['retention']['claim_delta'] == base['retention']['claim_delta']
    assert 'name' not in cfg


def test_vehicle_unknown_fuel_rejected():
    base = load_template(FROZEN_TEMPLATE)
    with pytest.raises(ValueError):
        resolve_vehicle({'HYDROGEN': 1.0}, base)
    assert resolve_vehicle({'EV': 1.0}, base) == {'EV': 1.0}
