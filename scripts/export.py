"""
Export script: Morpheus → Git (YAML files)

Fetches objects from Morpheus and writes them as portable YAML files
into the environments/<env>/ directory. Environment-specific IDs (cloud IDs,
network IDs, plan IDs) are replaced with logical names so the files can be
safely promoted across environments.

Usage:
    python scripts/export.py --env dev
    python scripts/export.py --env dev --type blueprints
    python scripts/export.py --env dev --type workflows
"""

import argparse
import os
import re
import sys

import yaml

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.morpheus_client as client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _safe_filename(name: str) -> str:
    """Replace characters that are unsafe in filenames with underscores."""
    return re.sub(r"[^\w\-]", "_", name)


# Fields that are environment-specific and must be stripped on export.
# The importer will resolve these from the environment mapping config.
BLUEPRINT_STRIP_FIELDS = {"id", "owner", "dateCreated", "lastUpdated", "resourcePermission"}


# ---------------------------------------------------------------------------
# ID → logical name resolution
# ---------------------------------------------------------------------------

def _build_cloud_map() -> dict[int, str]:
    """Map cloud (zone) numeric IDs to logical names."""
    return {z["id"]: z["name"] for z in client.list_clouds()}


def _build_network_map() -> dict[str, str]:
    """Map network IDs (as strings, e.g. 'network-17') to logical names."""
    return {f"network-{n['id']}": n["name"] for n in client.list_networks()}


# ---------------------------------------------------------------------------
# Blueprint normalisation
# ---------------------------------------------------------------------------

def _strip_keys(obj, keys_to_remove: set):
    """Recursively remove keys from dicts."""
    if isinstance(obj, dict):
        return {k: _strip_keys(v, keys_to_remove) for k, v in obj.items() if k not in keys_to_remove}
    if isinstance(obj, list):
        return [_strip_keys(i, keys_to_remove) for i in obj]
    return obj


def _replace_ids_in_blueprint(bp: dict, cloud_map: dict, network_map: dict) -> dict:
    """
    Walk the blueprint config and replace numeric IDs with logical names.
    The import script does the reverse using the environment mapping config.

    Only strips BLUEPRINT_STRIP_FIELDS at the TOP LEVEL — nested dicts (network,
    plan) also contain an "id" field that we need to read before replacing.
    """
    import copy
    bp = copy.deepcopy(bp)
    for key in BLUEPRINT_STRIP_FIELDS:
        bp.pop(key, None)

    # Walk tiers → instances
    config = bp.get("config", {})
    tiers = config.get("tiers", {})
    for tier_name, tier in tiers.items():
        for instance in tier.get("instances", []):
            # Cloud ID → cloud name
            if "cloudId" in instance:
                cloud_id = instance["cloudId"]
                instance["cloudName"] = cloud_map.get(cloud_id, f"unknown-cloud-{cloud_id}")
                del instance["cloudId"]

            # Network ID → network name
            for iface in instance.get("networkInterfaces", []):
                net = iface.get("network", {})
                net_id = net.get("id", "")
                if net_id in network_map:
                    net["name"] = network_map[net_id]
                    del net["id"]

            # Plan ID — keep as reference, add a comment-friendly name field
            # (plan IDs vary per cloud; the mapping config handles this)
            if "plan" in instance and "id" in instance["plan"]:
                instance["plan"]["_logical_name"] = f"plan-{instance['plan']['id']}"

    return bp


def _export_blueprints(env: str, out_dir: str, cloud_map: dict, network_map: dict):
    blueprints = client.list_blueprints()
    print(f"  Found {len(blueprints)} blueprint(s)")

    bp_dir = os.path.join(out_dir, "blueprints")
    os.makedirs(bp_dir, exist_ok=True)

    for bp in blueprints:
        name = bp.get("name", f"blueprint-{bp['id']}")
        normalised = _replace_ids_in_blueprint(bp, cloud_map, network_map)

        out_path = os.path.join(bp_dir, f"{_safe_filename(name)}.yml")
        with open(out_path, "w") as f:
            yaml.dump(normalised, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"    Exported: {out_path}")


# ---------------------------------------------------------------------------
# Workflow normalisation
# ---------------------------------------------------------------------------

WORKFLOW_STRIP_FIELDS = {"id", "dateCreated", "lastUpdated"}


def _export_workflows(env: str, out_dir: str):
    workflows = client.list_workflows()
    print(f"  Found {len(workflows)} workflow(s)")

    wf_dir = os.path.join(out_dir, "workflows")
    os.makedirs(wf_dir, exist_ok=True)

    for wf in workflows:
        name = wf.get("name", f"workflow-{wf['id']}")
        normalised = _strip_keys(wf, WORKFLOW_STRIP_FIELDS)

        out_path = os.path.join(wf_dir, f"{_safe_filename(name)}.yml")
        with open(out_path, "w") as f:
            yaml.dump(normalised, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"    Exported: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Export Morpheus objects to YAML")
    parser.add_argument("--env", required=True, choices=["dev", "test", "prod"],
                        help="Source environment to export from")
    parser.add_argument("--type", dest="obj_type", default="all",
                        choices=["all", "blueprints", "workflows"],
                        help="Object type to export (default: all)")
    args = parser.parse_args()

    out_dir = os.path.join(REPO_ROOT, "environments", args.env)
    os.makedirs(out_dir, exist_ok=True)

    print(f"Exporting from Morpheus ({args.env}) → {out_dir}")

    cloud_map = _build_cloud_map()
    network_map = _build_network_map()

    if args.obj_type in ("all", "blueprints"):
        print("\n[blueprints]")
        _export_blueprints(args.env, out_dir, cloud_map, network_map)

    if args.obj_type in ("all", "workflows"):
        print("\n[workflows]")
        _export_workflows(args.env, out_dir)

    print("\nExport complete.")


if __name__ == "__main__":
    main()
