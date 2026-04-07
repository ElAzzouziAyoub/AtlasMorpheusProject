"""
Mock Morpheus API server.

Serves realistic responses based on the JSON samples in /samples/.
Use this for local development until you have real Morpheus credentials.

Run with:
    python mock_server/app.py

The server starts at http://localhost:5000.
Set MORPHEUS_URL=http://localhost:5000 in your .env to use it.
"""

import json
import os
from flask import Flask, jsonify, request

app = Flask(__name__)

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")

# In-memory store so the mock can handle POST/PUT/DELETE during a session
_store = {
    "blueprints": None,
    "taskSets": None,
    "zones": None,
    "networks": None,
}


def _load(filename: str) -> dict:
    path = os.path.join(SAMPLES_DIR, filename)
    with open(path) as f:
        return json.load(f)


def _blueprints():
    if _store["blueprints"] is None:
        _store["blueprints"] = _load("blueprints_list.json")["blueprints"]
    return _store["blueprints"]


def _workflows():
    if _store["taskSets"] is None:
        _store["taskSets"] = _load("workflows_list.json")["taskSets"]
    return _store["taskSets"]


def _clouds():
    if _store["zones"] is None:
        _store["zones"] = _load("clouds_list.json")["zones"]
    return _store["zones"]


def _networks():
    if _store["networks"] is None:
        _store["networks"] = _load("networks_list.json")["networks"]
    return _store["networks"]


def _paginate(items: list) -> dict:
    return {
        "meta": {"offset": 0, "max": 25, "size": len(items), "total": len(items)},
    }


# ---------------------------------------------------------------------------
# Auth check (the real Morpheus API uses Bearer tokens in the header)
# ---------------------------------------------------------------------------

def _check_auth() -> bool:
    auth = request.headers.get("Authorization", "")
    # Accept any non-empty Bearer token in mock mode
    return auth.startswith("Bearer ") and len(auth) > 10


def _unauthorized():
    return jsonify({"success": False, "msg": "Unauthorized"}), 401


# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------

@app.route("/api/blueprints", methods=["GET"])
def list_blueprints():
    if not _check_auth():
        return _unauthorized()
    items = _blueprints()
    resp = {"blueprints": items}
    resp.update(_paginate(items))
    return jsonify(resp)


@app.route("/api/blueprints/<int:blueprint_id>", methods=["GET"])
def get_blueprint(blueprint_id: int):
    if not _check_auth():
        return _unauthorized()
    for bp in _blueprints():
        if bp["id"] == blueprint_id:
            return jsonify({"blueprint": bp})
    return jsonify({"success": False, "msg": "Blueprint not found"}), 404


@app.route("/api/blueprints", methods=["POST"])
def create_blueprint():
    if not _check_auth():
        return _unauthorized()
    data = request.get_json(silent=True) or {}
    blueprint = data.get("blueprint", data)
    blueprint["id"] = max((b["id"] for b in _blueprints()), default=0) + 1
    _blueprints().append(blueprint)
    print(f"[MOCK] Created blueprint: {blueprint.get('name')}")
    return jsonify({"success": True, "blueprint": blueprint}), 201


@app.route("/api/blueprints/<int:blueprint_id>", methods=["PUT"])
def update_blueprint(blueprint_id: int):
    if not _check_auth():
        return _unauthorized()
    data = request.get_json(silent=True) or {}
    blueprint = data.get("blueprint", data)
    for i, bp in enumerate(_blueprints()):
        if bp["id"] == blueprint_id:
            blueprint["id"] = blueprint_id
            _blueprints()[i] = blueprint
            print(f"[MOCK] Updated blueprint id={blueprint_id}")
            return jsonify({"success": True, "blueprint": blueprint})
    return jsonify({"success": False, "msg": "Blueprint not found"}), 404


@app.route("/api/blueprints/<int:blueprint_id>", methods=["DELETE"])
def delete_blueprint(blueprint_id: int):
    if not _check_auth():
        return _unauthorized()
    for i, bp in enumerate(_blueprints()):
        if bp["id"] == blueprint_id:
            _blueprints().pop(i)
            print(f"[MOCK] Deleted blueprint id={blueprint_id}")
            return jsonify({"success": True})
    return jsonify({"success": False, "msg": "Blueprint not found"}), 404


# ---------------------------------------------------------------------------
# Workflows (taskSets)
# ---------------------------------------------------------------------------

@app.route("/api/task-sets", methods=["GET"])
def list_workflows():
    if not _check_auth():
        return _unauthorized()
    items = _workflows()
    resp = {"taskSets": items}
    resp.update(_paginate(items))
    return jsonify(resp)


@app.route("/api/task-sets/<int:workflow_id>", methods=["GET"])
def get_workflow(workflow_id: int):
    if not _check_auth():
        return _unauthorized()
    for wf in _workflows():
        if wf["id"] == workflow_id:
            return jsonify({"taskSet": wf})
    return jsonify({"success": False, "msg": "Workflow not found"}), 404


@app.route("/api/task-sets", methods=["POST"])
def create_workflow():
    if not _check_auth():
        return _unauthorized()
    data = request.get_json(silent=True) or {}
    workflow = data.get("taskSet", data)
    workflow["id"] = max((w["id"] for w in _workflows()), default=0) + 1
    _workflows().append(workflow)
    print(f"[MOCK] Created workflow: {workflow.get('name')}")
    return jsonify({"success": True, "taskSet": workflow}), 201


# ---------------------------------------------------------------------------
# Clouds & Networks (read-only — these are infrastructure, not managed by us)
# ---------------------------------------------------------------------------

@app.route("/api/zones", methods=["GET"])
def list_clouds():
    if not _check_auth():
        return _unauthorized()
    items = _clouds()
    resp = {"zones": items}
    resp.update(_paginate(items))
    return jsonify(resp)


@app.route("/api/networks", methods=["GET"])
def list_networks():
    if not _check_auth():
        return _unauthorized()
    items = _networks()
    resp = {"networks": items}
    resp.update(_paginate(items))
    return jsonify(resp)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"success": True, "msg": "Morpheus mock server is running"})


if __name__ == "__main__":
    print("Starting Morpheus mock server at http://localhost:5000")
    print("Use Authorization: Bearer mock-token-dev in your requests")
    app.run(host="0.0.0.0", port=5000, debug=True)
