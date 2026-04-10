"""
Integration tests for the Flask mock server.
Starts the mock app in test mode and calls its endpoints.
"""

import json
import pytest
import mock_server.app as mock_app
from mock_server.app import app

HEADERS = {"Authorization": "Bearer mock-token-dev"}


@pytest.fixture(autouse=True)
def reset_store():
    """Reset in-memory store before each test so tests are independent."""
    mock_app._store = {k: None for k in mock_app._store}


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_ping_no_auth(client):
    r = client.get("/api/ping")
    assert r.status_code == 200


def test_blueprints_requires_auth(client):
    r = client.get("/api/blueprints")
    assert r.status_code == 401


def test_blueprints_with_auth(client):
    r = client.get("/api/blueprints", headers=HEADERS)
    assert r.status_code == 200
    data = r.get_json()
    assert "blueprints" in data
    assert "meta" in data


# ---------------------------------------------------------------------------
# Blueprints CRUD
# ---------------------------------------------------------------------------

def test_get_blueprint_by_id(client):
    r = client.get("/api/blueprints/1", headers=HEADERS)
    assert r.status_code == 200
    assert r.get_json()["blueprint"]["id"] == 1


def test_get_blueprint_not_found(client):
    r = client.get("/api/blueprints/9999", headers=HEADERS)
    assert r.status_code == 404


def test_create_blueprint(client):
    payload = {"blueprint": {"name": "new-bp", "type": "morpheus"}}
    r = client.post("/api/blueprints", headers=HEADERS,
                    data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 201
    data = r.get_json()
    assert data["success"] is True
    assert data["blueprint"]["name"] == "new-bp"
    assert "id" in data["blueprint"]


def test_update_blueprint(client):
    payload = {"blueprint": {"name": "updated-bp", "type": "morpheus"}}
    r = client.put("/api/blueprints/1", headers=HEADERS,
                   data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["blueprint"]["name"] == "updated-bp"


def test_delete_blueprint(client):
    r = client.delete("/api/blueprints/2", headers=HEADERS)
    assert r.status_code == 200
    # Verify it's gone
    r2 = client.get("/api/blueprints/2", headers=HEADERS)
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

def test_list_workflows(client):
    r = client.get("/api/task-sets", headers=HEADERS)
    assert r.status_code == 200
    assert "taskSets" in r.get_json()


def test_get_workflow_by_id(client):
    r = client.get("/api/task-sets/5", headers=HEADERS)
    assert r.status_code == 200
    assert r.get_json()["taskSet"]["id"] == 5


# ---------------------------------------------------------------------------
# Clouds & Networks
# ---------------------------------------------------------------------------

def test_list_clouds(client):
    r = client.get("/api/zones", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.get_json()["zones"]) > 0


def test_list_networks(client):
    r = client.get("/api/networks", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.get_json()["networks"]) > 0
