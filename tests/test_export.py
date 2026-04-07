"""
Tests for the export script transformation logic.
No network calls — all Morpheus responses are mocked.
"""

import pytest
from scripts.export import (
    _strip_keys,
    _replace_ids_in_blueprint,
    BLUEPRINT_STRIP_FIELDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BLUEPRINT = {
    "id": 1,
    "name": "ubuntu-web-server",
    "type": "morpheus",
    "description": "Test blueprint",
    "owner": {"id": 1, "username": "admin"},
    "dateCreated": "2024-01-15T09:00:00Z",
    "lastUpdated": "2024-03-10T14:30:00Z",
    "config": {
        "name": "ubuntu-web-server",
        "type": "morpheus",
        "tiers": {
            "App": {
                "tierIndex": 1,
                "instances": [
                    {
                        "instance": {"type": "ubuntu"},
                        "cloudId": 3,
                        "networkInterfaces": [{"network": {"id": "network-17"}}],
                        "plan": {"id": 12},
                    }
                ],
            }
        },
    },
}

CLOUD_MAP = {3: "DEV-Nutanix", 7: "TEST-VMware"}
NETWORK_MAP = {"network-17": "DEV-VLAN-100", "network-23": "TEST-VLAN-200"}


# ---------------------------------------------------------------------------
# _strip_keys
# ---------------------------------------------------------------------------

def test_strip_keys_removes_top_level():
    result = _strip_keys({"id": 1, "name": "foo", "owner": "bar"}, {"id", "owner"})
    assert "id" not in result
    assert "owner" not in result
    assert result["name"] == "foo"


def test_strip_keys_nested():
    data = {"a": {"id": 1, "b": 2}, "c": [{"id": 3, "d": 4}]}
    result = _strip_keys(data, {"id"})
    assert "id" not in result["a"]
    assert "id" not in result["c"][0]
    assert result["a"]["b"] == 2
    assert result["c"][0]["d"] == 4


def test_strip_keys_leaves_unmatched():
    data = {"name": "test", "config": {"tiers": {}}}
    result = _strip_keys(data, {"id"})
    assert result == data


# ---------------------------------------------------------------------------
# _replace_ids_in_blueprint
# ---------------------------------------------------------------------------

def test_blueprint_strips_env_fields():
    result = _replace_ids_in_blueprint(SAMPLE_BLUEPRINT.copy(), CLOUD_MAP, NETWORK_MAP)
    assert "id" not in result
    assert "owner" not in result
    assert "dateCreated" not in result


def test_blueprint_replaces_cloud_id_with_name():
    result = _replace_ids_in_blueprint(SAMPLE_BLUEPRINT.copy(), CLOUD_MAP, NETWORK_MAP)
    instance = result["config"]["tiers"]["App"]["instances"][0]
    assert "cloudId" not in instance
    assert instance["cloudName"] == "DEV-Nutanix"


def test_blueprint_replaces_network_id_with_name():
    result = _replace_ids_in_blueprint(SAMPLE_BLUEPRINT.copy(), CLOUD_MAP, NETWORK_MAP)
    iface = result["config"]["tiers"]["App"]["instances"][0]["networkInterfaces"][0]
    net = iface["network"]
    assert "id" not in net
    assert net["name"] == "DEV-VLAN-100"


def test_blueprint_adds_plan_logical_name():
    result = _replace_ids_in_blueprint(SAMPLE_BLUEPRINT.copy(), CLOUD_MAP, NETWORK_MAP)
    plan = result["config"]["tiers"]["App"]["instances"][0]["plan"]
    assert plan["_logical_name"] == "plan-12"
    assert plan["id"] == 12  # original ID kept alongside


def test_blueprint_unknown_cloud_gets_fallback():
    result = _replace_ids_in_blueprint(SAMPLE_BLUEPRINT.copy(), {}, NETWORK_MAP)
    instance = result["config"]["tiers"]["App"]["instances"][0]
    assert instance["cloudName"] == "unknown-cloud-3"
