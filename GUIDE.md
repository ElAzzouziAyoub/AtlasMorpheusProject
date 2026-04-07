# How to use and test the ATLAS project

This guide walks you through every part of the project hands-on.
You will run real commands and see real output at each step.

---

## Before anything else — activate the environment

Every time you open a new terminal in this project, run this first:

```bash
source .venv/bin/activate
```

You will know it worked when you see `(.venv)` at the start of your terminal line.
If the `.venv` folder does not exist yet:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## The big picture — what runs where

You will use **two terminals** at the same time:

| Terminal | What it does |
|----------|-------------|
| Terminal 1 | Runs the mock server (stays open the whole time) |
| Terminal 2 | Where you run your scripts and commands |

---

## Step 1 — Start the mock server

In **Terminal 1**, run:

```bash
source .venv/bin/activate
python mock_server/app.py
```

Expected output:
```
Starting Morpheus mock server at http://localhost:5000
Use Authorization: Bearer mock-token-dev in your requests
 * Running on http://127.0.0.1:5000
```

Leave this terminal open. This is your fake Morpheus. Every script you run talks to it.
When you make a request, you will see it logged here in real time — very useful for debugging.

---

## Step 2 — Check your credentials file

In **Terminal 2**, look at your `.env` file:

```bash
cat .env
```

Expected output:
```
MORPHEUS_URL=http://localhost:5000
MORPHEUS_TOKEN=mock-token-dev
MORPHEUS_ENV=dev
```

This tells every script where Morpheus is and how to authenticate.
When you get real credentials later, you only change this file — nothing else.

---

## Step 3 — Explore the API by hand (curl)

This is how you talk to Morpheus directly, like Postman but in the terminal.
Understanding the raw API is essential before you touch any script.

### Ping the server
```bash
curl -s http://localhost:5000/api/ping
```
```json
{"msg": "Morpheus mock server is running", "success": true}
```

### List all blueprints
```bash
curl -s http://localhost:5000/api/blueprints \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

### Get one blueprint by ID
```bash
curl -s http://localhost:5000/api/blueprints/1 \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

### What happens with no token?
```bash
curl -s http://localhost:5000/api/blueprints
```
```json
{"msg": "Unauthorized", "success": false}
```

### List workflows
```bash
curl -s http://localhost:5000/api/task-sets \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

### List clouds and networks
```bash
curl -s http://localhost:5000/api/zones \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool

curl -s http://localhost:5000/api/networks \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

The clouds and networks are important — the export script fetches them to build the
ID-to-name translation tables.

---

## Step 4 — Run the export script

This script fetches objects from Morpheus and writes them as YAML files into `environments/dev/`.

```bash
python scripts/export.py --env dev
```

Expected output:
```
Exporting from Morpheus (dev) → .../environments/dev

[blueprints]
  Found 2 blueprint(s)
    Exported: environments/dev/blueprints/ubuntu-web-server.yml
    Exported: environments/dev/blueprints/nginx-lb.yml

[workflows]
  Found 2 workflow(s)
    Exported: environments/dev/workflows/provision-web-server.yml
    Exported: environments/dev/workflows/decommission-cleanup.yml

Export complete.
```

Now look at what was exported:

```bash
cat environments/dev/blueprints/ubuntu-web-server.yml
```

Notice what happened to the IDs:
- `cloudId: 3` became `cloudName: DEV-Nutanix`
- `network.id: "network-17"` became `network.name: DEV-VLAN-100`
- `id`, `owner`, `dateCreated`, `lastUpdated` are gone

This is the whole point — the YAML file is now portable. It describes *what* the blueprint is,
not *where* it lives.

### Export options

```bash
# Export only blueprints
python scripts/export.py --env dev --type blueprints

# Export only workflows
python scripts/export.py --env dev --type workflows

# Export from a different environment (once you have TEST credentials)
python scripts/export.py --env test
```

---

## Step 5 — Understand the mapping config

Open `config/mapping_dev.yml`:

```bash
cat config/mapping_dev.yml
```

This file is the translation table. It says:
- Logical name `DEV-Nutanix` = cloud ID `3` in DEV Morpheus
- Logical name `DEV-VLAN-100` = network ID `17` in DEV Morpheus

When you import into TEST, the script reads `config/mapping_test.yml` instead,
which maps those same logical names to the different IDs that exist in TEST Morpheus.

**When you get real credentials**, this is the file you fill in with real values.
You find the real IDs by running:

```bash
curl -s https://your-real-morpheus/api/zones \
  -H "Authorization: Bearer your-real-token" | python3 -m json.tool
```

---

## Step 6 — Run the import script

This script reads the YAML files and pushes them into Morpheus.
Always run with `--dry-run` first to see what would happen.

```bash
# Dry run first — no changes made
python scripts/importer.py --env dev --dry-run
```

Expected output:
```
--- DRY RUN MODE — no changes will be made ---
Importing from .../environments/dev → Morpheus (dev)

[blueprints]
  Found 2 blueprint file(s)
    [dry-run] would update: nginx-lb
    [dry-run] would update: ubuntu-web-server
  Summary: {'created': 0, 'updated': 0, 'dry-run': 2, 'errors': 0}

[workflows]
  Found 2 workflow file(s)
    [dry-run] would update: provision-web-server
    [dry-run] would update: decommission-cleanup

Import complete.
```

It says "would update" because those blueprints already exist in the mock server.
If they did not exist, it would say "would create".

```bash
# Real import
python scripts/importer.py --env dev
```

### Import options

```bash
# Only import blueprints
python scripts/importer.py --env dev --type blueprints

# Import into TEST (needs TEST credentials in .env and mapping_test.yml filled in)
python scripts/importer.py --env test --dry-run
```

---

## Step 7 — Test the full round-trip

This is the most important test. It proves the whole bridge works:
export from Morpheus → store in Git → import back into Morpheus.

```bash
# 1. Export current state
python scripts/export.py --env dev

# 2. Check what was exported
ls environments/dev/blueprints/
cat environments/dev/blueprints/nginx-lb.yml

# 3. Import it back (dry-run first)
python scripts/importer.py --env dev --dry-run

# 4. Real import
python scripts/importer.py --env dev

# 5. Verify it landed in the mock server
curl -s http://localhost:5000/api/blueprints \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

---

## Step 8 — Test drift detection

Drift detection answers: *"Has someone changed Morpheus directly through the GUI, bypassing Git?"*

### No drift scenario

```bash
# After a clean export, there should be no drift
python scripts/drift_detect.py --env dev
```
```
Drift detection: Morpheus (dev) vs Git
============================================================
No drift detected. Morpheus state matches Git.
```

### Simulate drift

Pretend someone clicked around in the Morpheus GUI and changed a blueprint:

```bash
curl -s -X PUT http://localhost:5000/api/blueprints/2 \
  -H "Authorization: Bearer mock-token-dev" \
  -H "Content-Type: application/json" \
  -d '{"blueprint": {"id": 2, "name": "nginx-lb", "description": "CHANGED IN GUI"}}'
```

Now run drift detection again:

```bash
python scripts/drift_detect.py --env dev
```

Expected output:
```
DRIFT DETECTED — 1 finding(s):

  [CHANGED] blueprints/nginx-lb:
    values_changed: {"root['description']": {'new_value': 'CHANGED IN GUI', 'old_value': 'NGINX load balancer blueprint'}}

Action: open a Git issue or MR to reconcile the drift.
```

The script exits with code 1 when drift is found — this is what fails the CI job and triggers an alert.

### Fix the drift

You have two options:
- **Git wins:** re-run the import to overwrite the GUI change with the Git version
- **GUI wins:** re-run the export to capture the change into Git, then commit it

---

## Step 9 — Add a new blueprint and test it

This is how you would work day-to-day once you have real access.

### Option A: Create it via the API (simulating someone creating it in the GUI first)

```bash
curl -s -X POST http://localhost:5000/api/blueprints \
  -H "Authorization: Bearer mock-token-dev" \
  -H "Content-Type: application/json" \
  -d '{
    "blueprint": {
      "name": "my-test-blueprint",
      "type": "morpheus",
      "description": "My first blueprint",
      "config": {
        "name": "my-test-blueprint",
        "type": "morpheus",
        "tiers": {
          "App": {
            "tierIndex": 1,
            "instances": [{
              "instance": {"type": "ubuntu"},
              "cloudId": 3,
              "networkInterfaces": [{"network": {"id": "network-17"}}],
              "plan": {"id": 12}
            }]
          }
        }
      },
      "visibility": "private"
    }
  }' | python3 -m json.tool
```

Now export it:

```bash
python scripts/export.py --env dev --type blueprints
cat environments/dev/blueprints/my-test-blueprint.yml
```

You will see the new YAML file with IDs already replaced by logical names.

### Option B: Write the YAML directly and import it

Create `environments/dev/blueprints/my-new-blueprint.yml`:

```yaml
name: my-new-blueprint
type: morpheus
description: Created directly in Git
config:
  name: my-new-blueprint
  type: morpheus
  tiers:
    App:
      tierIndex: 1
      instances:
        - instance:
            type: ubuntu
          cloudName: DEV-Nutanix
          networkInterfaces:
            - network:
                name: DEV-VLAN-100
          plan:
            id: 12
            _logical_name: plan-12
```

Then import it:

```bash
python scripts/importer.py --env dev --dry-run
python scripts/importer.py --env dev
```

Verify it appeared in Morpheus:

```bash
curl -s http://localhost:5000/api/blueprints \
  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

---

## Step 10 — Run the tests

The test suite validates all the logic without needing the mock server running.

```bash
pytest tests/ -v
```

Expected output:
```
tests/test_export.py::test_strip_keys_removes_top_level PASSED
tests/test_export.py::test_blueprint_replaces_cloud_id_with_name PASSED
tests/test_export.py::test_blueprint_replaces_network_id_with_name PASSED
...
tests/test_mock_server.py::test_blueprints_with_auth PASSED
tests/test_mock_server.py::test_create_blueprint PASSED
...
26 passed in 0.32s
```

### Run only one test file

```bash
pytest tests/test_export.py -v
pytest tests/test_import.py -v
pytest tests/test_mock_server.py -v
```

### Run only one specific test

```bash
pytest tests/test_export.py::test_blueprint_replaces_cloud_id_with_name -v
```

### Run tests and see print output

```bash
pytest tests/ -v -s
```

---

## Step 11 — Add your own test

Open `tests/test_export.py` and add a function at the bottom:

```python
def test_my_new_case():
    bp = {
        "name": "test-bp",
        "config": {
            "tiers": {
                "App": {
                    "instances": [{
                        "cloudId": 7,
                        "networkInterfaces": [{"network": {"id": "network-23"}}],
                        "plan": {"id": 10}
                    }]
                }
            }
        }
    }
    cloud_map = {7: "TEST-VMware"}
    network_map = {"network-23": "TEST-VLAN-200"}

    result = _replace_ids_in_blueprint(bp, cloud_map, network_map)
    instance = result["config"]["tiers"]["App"]["instances"][0]

    assert instance["cloudName"] == "TEST-VMware"
    assert instance["networkInterfaces"][0]["network"]["name"] == "TEST-VLAN-200"
```

Run it:

```bash
pytest tests/test_export.py::test_my_new_case -v
```

---

## Common errors and what they mean

| Error | Cause | Fix |
|-------|-------|-----|
| `EnvironmentError: MORPHEUS_URL is not set` | `.env` file missing or wrong path | Check `.env` exists in the project root with the right values |
| `ConnectionError: Failed to resolve ...` | Mock server not running | Start `python mock_server/app.py` in a separate terminal |
| `FileNotFoundError: mapping_test.yml` | You ran import for `test` but no mapping exists | Fill in `config/mapping_test.yml` with real IDs |
| `ValueError: Cloud 'X' not found in mapping` | A cloud name in your YAML is not in the mapping file | Add the entry to `config/mapping_<env>.yml` |
| `401 Unauthorized` | Wrong or missing token | Check `MORPHEUS_TOKEN` in `.env` matches the header |

---

## Switching from mock to real Morpheus

When you get real credentials, this is the only thing you change:

```bash
# .env
MORPHEUS_URL=https://your-real-morpheus-instance.com
MORPHEUS_TOKEN=your-real-api-token
MORPHEUS_ENV=dev
```

Then fill in the real IDs in `config/mapping_dev.yml` by running:

```bash
# Find real cloud IDs
curl -s https://your-real-morpheus/api/zones \
  -H "Authorization: Bearer your-real-token" | python3 -m json.tool

# Find real network IDs
curl -s https://your-real-morpheus/api/networks \
  -H "Authorization: Bearer your-real-token" | python3 -m json.tool
```

Copy those IDs into the mapping file, then run the export. Everything else is identical.

---

## Quick reference — all commands

```bash
# Setup
source .venv/bin/activate

# Mock server
python mock_server/app.py

# Export
python scripts/export.py --env dev
python scripts/export.py --env dev --type blueprints

# Import
python scripts/importer.py --env dev --dry-run
python scripts/importer.py --env dev

# Drift detection
python scripts/drift_detect.py --env dev

# Tests
pytest tests/ -v
pytest tests/test_export.py -v
pytest tests/test_mock_server.py -v

# Curl shortcuts
curl -s http://localhost:5000/api/ping
curl -s http://localhost:5000/api/blueprints -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
curl -s http://localhost:5000/api/task-sets  -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
curl -s http://localhost:5000/api/zones      -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
curl -s http://localhost:5000/api/networks   -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```
