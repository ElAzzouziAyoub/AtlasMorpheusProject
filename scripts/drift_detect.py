"""
Drift detection script.

Exports the current live state of Morpheus and compares it to what is
stored in Git. Reports any differences (objects added, removed, or modified
outside of the Git workflow).

Usage:
    python scripts/drift_detect.py --env dev
    python scripts/drift_detect.py --env dev --type blueprints

Exit codes:
    0 — no drift detected
    1 — drift detected (use this to fail the CI job and trigger an alert)
"""

import argparse
import copy
import os
import sys
import tempfile

import yaml
from deepdiff import DeepDiff

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.morpheus_client as client
from scripts.export import (  # noqa: F401 — re-exported for drift use
    _build_cloud_map,
    _build_network_map,
    _replace_ids_in_blueprint,
    _strip_keys,
    BLUEPRINT_STRIP_FIELDS,
    WORKFLOW_STRIP_FIELDS,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_git_objects(env: str, obj_type: str) -> dict[str, dict]:
    """Load all YAML files for a given object type from the Git tree."""
    obj_dir = os.path.join(REPO_ROOT, "environments", env, obj_type)
    if not os.path.isdir(obj_dir):
        return {}
    result = {}
    for fname in os.listdir(obj_dir):
        if fname.endswith(".yml"):
            with open(os.path.join(obj_dir, fname)) as f:
                obj = yaml.safe_load(f)
            name = obj.get("name") or fname.replace(".yml", "")
            result[name] = obj
    return result


def _fetch_live_blueprints(cloud_map: dict, network_map: dict) -> dict[str, dict]:
    """Fetch live blueprints from Morpheus and normalise them (same as export)."""
    result = {}
    for bp in client.list_blueprints():
        normalised = _replace_ids_in_blueprint(copy.deepcopy(bp), cloud_map, network_map)
        name = normalised.get("name", f"blueprint-{bp['id']}")
        result[name] = normalised
    return result


def _fetch_live_workflows() -> dict[str, dict]:
    result = {}
    for wf in client.list_workflows():
        normalised = _strip_keys(wf, WORKFLOW_STRIP_FIELDS)
        name = normalised.get("name", f"workflow-{wf['id']}")
        result[name] = normalised
    return result


def _compare(obj_type: str, git_objects: dict, live_objects: dict) -> list[str]:
    """Return a list of human-readable drift findings."""
    findings = []

    git_names = set(git_objects)
    live_names = set(live_objects)

    for name in live_names - git_names:
        findings.append(f"  [EXTRA]   {obj_type}/{name} exists in Morpheus but not in Git")

    for name in git_names - live_names:
        findings.append(f"  [MISSING] {obj_type}/{name} exists in Git but not in Morpheus")

    for name in git_names & live_names:
        diff = DeepDiff(git_objects[name], live_objects[name], ignore_order=True)
        if diff:
            findings.append(f"  [CHANGED] {obj_type}/{name}:")
            for change_type, details in diff.items():
                findings.append(f"    {change_type}: {details}")

    return findings


def main():
    parser = argparse.ArgumentParser(description="Detect drift between Morpheus and Git")
    parser.add_argument("--env", required=True, choices=["dev", "test", "prod"])
    parser.add_argument("--type", dest="obj_type", default="all",
                        choices=["all", "blueprints", "workflows"])
    args = parser.parse_args()

    print(f"Drift detection: Morpheus ({args.env}) vs Git")
    print("=" * 60)

    cloud_map = _build_cloud_map()
    network_map = _build_network_map()

    all_findings = []

    if args.obj_type in ("all", "blueprints"):
        git_bps = _load_git_objects(args.env, "blueprints")
        live_bps = _fetch_live_blueprints(cloud_map, network_map)
        findings = _compare("blueprints", git_bps, live_bps)
        all_findings.extend(findings)

    if args.obj_type in ("all", "workflows"):
        git_wfs = _load_git_objects(args.env, "workflows")
        live_wfs = _fetch_live_workflows()
        findings = _compare("workflows", git_wfs, live_wfs)
        all_findings.extend(findings)

    if all_findings:
        print(f"DRIFT DETECTED — {len(all_findings)} finding(s):\n")
        for f in all_findings:
            print(f)
        print("\nAction: open a Git issue or MR to reconcile the drift.")
        sys.exit(1)
    else:
        print("No drift detected. Morpheus state matches Git.")
        sys.exit(0)


if __name__ == "__main__":
    main()
