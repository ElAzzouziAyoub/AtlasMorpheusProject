"""
Thin wrapper around the Morpheus REST API.

All scripts import this module instead of calling requests directly.
Swap MORPHEUS_URL between mock and real — nothing else changes.
"""

import os
import requests
from dotenv import load_dotenv

# Always load .env from the project root, regardless of where the script is called from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(_REPO_ROOT, ".env"), override=True)


def _base_url() -> str:
    url = os.environ.get("MORPHEUS_URL", "")
    if not url:
        raise EnvironmentError("MORPHEUS_URL is not set. Add it to your .env file.")
    return url.rstrip("/")


def _token() -> str:
    token = os.environ.get("MORPHEUS_TOKEN", "")
    if not token:
        raise EnvironmentError("MORPHEUS_TOKEN is not set. Add it to your .env file.")
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }

TIMEOUT = 30  # seconds


def _get(path: str, params: dict = None) -> dict:
    url = f"{_base_url()}{path}"
    response = requests.get(url, headers=_headers(), params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _post(path: str, payload: dict) -> dict:
    url = f"{_base_url()}{path}"
    response = requests.post(url, headers=_headers(), json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _put(path: str, payload: dict) -> dict:
    url = f"{_base_url()}{path}"
    response = requests.put(url, headers=_headers(), json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------

def list_blueprints() -> list[dict]:
    """Return all blueprints (handles pagination automatically)."""
    all_items = []
    offset = 0
    max_per_page = 100
    while True:
        data = _get("/api/blueprints", params={"max": max_per_page, "offset": offset})
        items = data.get("blueprints", [])
        all_items.extend(items)
        meta = data.get("meta", {})
        if offset + len(items) >= meta.get("total", len(items)):
            break
        offset += max_per_page
    return all_items


def get_blueprint(blueprint_id: int) -> dict:
    return _get(f"/api/blueprints/{blueprint_id}")["blueprint"]


def create_blueprint(payload: dict) -> dict:
    return _post("/api/blueprints", {"blueprint": payload})


def update_blueprint(blueprint_id: int, payload: dict) -> dict:
    return _put(f"/api/blueprints/{blueprint_id}", {"blueprint": payload})


# ---------------------------------------------------------------------------
# Workflows (task sets)
# ---------------------------------------------------------------------------

def list_workflows() -> list[dict]:
    all_items = []
    offset = 0
    max_per_page = 100
    while True:
        data = _get("/api/task-sets", params={"max": max_per_page, "offset": offset})
        items = data.get("taskSets", [])
        all_items.extend(items)
        meta = data.get("meta", {})
        if offset + len(items) >= meta.get("total", len(items)):
            break
        offset += max_per_page
    return all_items


def get_workflow(workflow_id: int) -> dict:
    return _get(f"/api/task-sets/{workflow_id}")["taskSet"]


def create_workflow(payload: dict) -> dict:
    return _post("/api/task-sets", {"taskSet": payload})


# ---------------------------------------------------------------------------
# Infrastructure (read-only references)
# ---------------------------------------------------------------------------

def list_clouds() -> list[dict]:
    return _get("/api/zones")["zones"]


def list_networks() -> list[dict]:
    return _get("/api/networks")["networks"]
