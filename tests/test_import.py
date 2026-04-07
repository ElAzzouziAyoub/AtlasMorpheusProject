"""
Tests for the importer script transformation logic.
Specifically tests the ID re-mapping (logical names → real IDs).
No network calls.
"""

import pytest
from scripts.importer import _remap_blueprint


MAPPING = {
    "environment": "test",
    "clouds": {
        "DEV-Nutanix": 1,
        "TEST-VMware": 2,
    },
    "networks": {
        "DEV-VLAN-100": 5,
        "TEST-VLAN-200": 9,
    },
    "plans": {
        "plan-12": 6,
    },
}

# This is what the export script produces (logical names, no IDs)
EXPORTED_BLUEPRINT = {
    "name": "ubuntu-web-server",
    "type": "morpheus",
    "config": {
        "name": "ubuntu-web-server",
        "type": "morpheus",
        "tiers": {
            "App": {
                "tierIndex": 1,
                "instances": [
                    {
                        "instance": {"type": "ubuntu"},
                        "cloudName": "DEV-Nutanix",
                        "networkInterfaces": [{"network": {"name": "DEV-VLAN-100"}}],
                        "plan": {"id": 12, "_logical_name": "plan-12"},
                    }
                ],
            }
        },
    },
}


def test_remap_restores_cloud_id():
    result = _remap_blueprint(EXPORTED_BLUEPRINT, MAPPING)
    instance = result["config"]["tiers"]["App"]["instances"][0]
    assert "cloudName" not in instance
    assert instance["cloudId"] == 1  # DEV-Nutanix → ID 1 in TEST mapping


def test_remap_restores_network_id():
    result = _remap_blueprint(EXPORTED_BLUEPRINT, MAPPING)
    net = result["config"]["tiers"]["App"]["instances"][0]["networkInterfaces"][0]["network"]
    assert net["id"] == "network-5"  # DEV-VLAN-100 → network ID 5 in TEST


def test_remap_restores_plan_id():
    result = _remap_blueprint(EXPORTED_BLUEPRINT, MAPPING)
    plan = result["config"]["tiers"]["App"]["instances"][0]["plan"]
    assert "_logical_name" not in plan
    assert plan["id"] == 6  # plan-12 → ID 6 in TEST


def test_remap_raises_on_unknown_cloud():
    bad_mapping = {**MAPPING, "clouds": {}}
    with pytest.raises(ValueError, match="DEV-Nutanix"):
        _remap_blueprint(EXPORTED_BLUEPRINT, bad_mapping)


def test_remap_raises_on_unknown_network():
    bad_mapping = {**MAPPING, "networks": {}}
    with pytest.raises(ValueError, match="DEV-VLAN-100"):
        _remap_blueprint(EXPORTED_BLUEPRINT, bad_mapping)


def test_remap_does_not_mutate_input():
    import copy
    original = copy.deepcopy(EXPORTED_BLUEPRINT)
    _remap_blueprint(EXPORTED_BLUEPRINT, MAPPING)
    assert EXPORTED_BLUEPRINT == original
