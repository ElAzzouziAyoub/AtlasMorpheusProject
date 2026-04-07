"""
Import script: Git (YAML) → Morpheus

Reads YAML files from environments/<env>/ and pushes them into Morpheus.
Uses the environment mapping config (config/mapping_<env>.yml) to translate
logical names back into the real IDs that exist in the target environment.

Usage:
    python scripts/import.py --env test
    python scripts/import.py --env prod --type blueprints --dry-run
"""

import argparse
import copy
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.morpheus_client as client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Mapping config loader
# ---------------------------------------------------------------------------

def _load_mapping(env: str) -> dict:
    path = os.path.join(REPO_ROOT, "config", f"mapping_{env}.yml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Mapping config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# ID re-mapping (reverse of export.py)
# ---------------------------------------------------------------------------

def _remap_blueprint(bp: dict, mapping: dict) -> dict:
    """
    Replace logical names with real IDs for the target environment.
    This is the inverse of export._replace_ids_in_blueprint().
    """
    bp = copy.deepcopy(bp)
    cloud_map = {name: id_ for name, id_ in mapping.get("clouds", {}).items()}
    network_map = {name: id_ for name, id_ in mapping.get("networks", {}).items()}
    plan_map = {name: id_ for name, id_ in mapping.get("plans", {}).items()}

    config = bp.get("config", {})
    tiers = config.get("tiers", {})
    for tier_name, tier in tiers.items():
        for instance in tier.get("instances", []):
            # Logical cloud name → real cloud ID
            if "cloudName" in instance:
                cloud_name = instance.pop("cloudName")
                instance["cloudId"] = cloud_map.get(cloud_name)
                if instance["cloudId"] is None:
                    raise ValueError(
                        f"Cloud '{cloud_name}' not found in mapping for env "
                        f"'{mapping['environment']}'. Update config/mapping_{mapping['environment']}.yml"
                    )

            # Logical network name → real network ID string
            for iface in instance.get("networkInterfaces", []):
                net = iface.get("network", {})
                if "name" in net and "id" not in net:
                    net_name = net["name"]
                    net_id = network_map.get(net_name)
                    if net_id is None:
                        raise ValueError(
                            f"Network '{net_name}' not found in mapping for env "
                            f"'{mapping['environment']}'"
                        )
                    net["id"] = f"network-{net_id}"

            # Plan logical name → real plan ID
            if "plan" in instance and "_logical_name" in instance["plan"]:
                logical = instance["plan"].pop("_logical_name")
                real_id = plan_map.get(logical)
                if real_id is None:
                    raise ValueError(
                        f"Plan '{logical}' not found in mapping for env "
                        f"'{mapping['environment']}'"
                    )
                instance["plan"]["id"] = real_id

    return bp


# ---------------------------------------------------------------------------
# Upsert logic (create or update based on name)
# ---------------------------------------------------------------------------

def _upsert_blueprint(bp: dict, existing: dict[str, dict], dry_run: bool) -> str:
    """
    If a blueprint with this name already exists → update it.
    Otherwise → create it.
    Returns 'created', 'updated', or 'dry-run'.
    """
    name = bp.get("name") or bp.get("config", {}).get("name", "unknown")

    if dry_run:
        action = "would update" if name in existing else "would create"
        print(f"    [dry-run] {action}: {name}")
        return "dry-run"

    if name in existing:
        bp_id = existing[name]["id"]
        client.update_blueprint(bp_id, bp)
        return "updated"
    else:
        client.create_blueprint(bp)
        return "created"


def _import_blueprints(env: str, in_dir: str, mapping: dict, dry_run: bool):
    bp_dir = os.path.join(in_dir, "blueprints")
    if not os.path.isdir(bp_dir):
        print("  No blueprints directory found, skipping.")
        return

    # Build index of existing blueprints by name for upsert logic
    existing = {bp["name"]: bp for bp in client.list_blueprints()}

    yml_files = [f for f in os.listdir(bp_dir) if f.endswith(".yml")]
    print(f"  Found {len(yml_files)} blueprint file(s)")

    stats = {"created": 0, "updated": 0, "dry-run": 0, "errors": 0}

    for fname in yml_files:
        fpath = os.path.join(bp_dir, fname)
        with open(fpath) as f:
            bp = yaml.safe_load(f)

        try:
            remapped = _remap_blueprint(bp, mapping)
            result = _upsert_blueprint(remapped, existing, dry_run)
            stats[result] += 1
            name = bp.get("name", fname)
            print(f"    {result}: {name}")
        except (ValueError, KeyError) as exc:
            print(f"    ERROR in {fname}: {exc}")
            stats["errors"] += 1

    print(f"  Summary: {stats}")


def _import_workflows(env: str, in_dir: str, dry_run: bool):
    wf_dir = os.path.join(in_dir, "workflows")
    if not os.path.isdir(wf_dir):
        print("  No workflows directory found, skipping.")
        return

    existing = {wf["name"]: wf for wf in client.list_workflows()}
    yml_files = [f for f in os.listdir(wf_dir) if f.endswith(".yml")]
    print(f"  Found {len(yml_files)} workflow file(s)")

    for fname in yml_files:
        fpath = os.path.join(wf_dir, fname)
        with open(fpath) as f:
            wf = yaml.safe_load(f)

        name = wf.get("name", fname)
        if dry_run:
            action = "would update" if name in existing else "would create"
            print(f"    [dry-run] {action}: {name}")
            continue

        if name in existing:
            # Workflows don't have a generic update in this mock; extend as needed
            print(f"    skipped (already exists): {name}")
        else:
            client.create_workflow(wf)
            print(f"    created: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import YAML objects into Morpheus")
    parser.add_argument("--env", required=True, choices=["dev", "test", "prod"],
                        help="Target environment to import into")
    parser.add_argument("--type", dest="obj_type", default="all",
                        choices=["all", "blueprints", "workflows"],
                        help="Object type to import (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and print what would happen without making changes")
    args = parser.parse_args()

    if args.dry_run:
        print("--- DRY RUN MODE — no changes will be made ---")

    mapping = _load_mapping(args.env)
    in_dir = os.path.join(REPO_ROOT, "environments", args.env)

    if not os.path.isdir(in_dir):
        print(f"ERROR: Source directory not found: {in_dir}")
        print(f"Run the export script first: python scripts/export.py --env {args.env}")
        sys.exit(1)

    print(f"Importing from {in_dir} → Morpheus ({args.env})")

    if args.obj_type in ("all", "blueprints"):
        print("\n[blueprints]")
        _import_blueprints(args.env, in_dir, mapping, args.dry_run)

    if args.obj_type in ("all", "workflows"):
        print("\n[workflows]")
        _import_workflows(args.env, in_dir, args.dry_run)

    print("\nImport complete.")


if __name__ == "__main__":
    main()
