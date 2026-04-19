# Transitioning from Mock Server to Real Morpheus API

This guide walks through the steps to cut over from the local Flask mock server to a real Morpheus instance. No code changes are needed — the entire switch is configuration.

---

## Overview

The mock server (`mock_server/app.py`) and the real Morpheus API expose identical endpoints. The only thing that changes is:

1. Where the client points (`MORPHEUS_URL`)
2. What token it uses (`MORPHEUS_TOKEN`)
3. What IDs actually exist in the real instance (mapping files)

---

## Step 1 — Obtain Your Credentials

From your Morpheus administrator, you need:

- **Base URL** of each environment (e.g. `https://morpheus-dev.company.com`)
- **API token** for each environment — generated in Morpheus under *User Settings → API Access*

You will need these for three environments: DEV, TEST, and PROD.

---

## Step 2 — Update Your Local `.env`

Open `.env` (copy from `.env.example` if not done yet) and replace the mock values:

```bash
# Before (mock)
MORPHEUS_URL=http://localhost:5000
MORPHEUS_TOKEN=mock-token-dev
MORPHEUS_ENV=dev

# After (real DEV instance)
MORPHEUS_URL=https://morpheus-dev.company.com
MORPHEUS_TOKEN=<your-dev-api-token>
MORPHEUS_ENV=dev
```

**Do not commit `.env`.** It is in `.gitignore` for this reason.

---

## Step 3 — Verify Connectivity

Run a quick sanity check against the real API before touching any pipeline scripts:

```bash
# Activate your virtual environment first
source .venv/bin/activate

# Test connectivity — should return a list of blueprints, not a connection error
python -c "
from scripts.morpheus_client import MorpheusClient
c = MorpheusClient()
print(c.list_blueprints())
"
```

Expected: a JSON list (possibly empty). Any `401 Unauthorized` means the token is wrong. Any `ConnectionError` means the URL is wrong or the instance is unreachable.

---

## Step 4 — Export Live State from DEV

Now run the export script against the real DEV Morpheus. This both validates connectivity and gives you the actual resource names used in that instance:

```bash
python scripts/export.py --env dev
```

This will:
- Hit the real `/api/blueprints`, `/api/task-sets`, `/api/zones`, `/api/networks` endpoints
- Replace raw IDs with logical names
- Write YAML files into `environments/dev/blueprints/` and `environments/dev/workflows/`

Open the exported files and note the `cloudName`, `network.name`, and `plan._logical_name` values — you will need these in Step 5.

---

## Step 5 — Populate the Mapping Files

The mapping files (`config/mapping_*.yml`) currently contain placeholder values based on the mock server's sample data. You must replace them with the real IDs from your Morpheus instances.

### How to find real IDs

Option A — from the export output:  
The export script logs the live cloud and network names with their IDs. Check the script's stdout or add a temporary print if needed.

Option B — from the Morpheus UI:  
Navigate to *Infrastructure → Clouds* and *Infrastructure → Networks*. The URL or detail panel shows the numeric ID.

Option C — direct API call:
```bash
# List clouds with their IDs
python -c "
from scripts.morpheus_client import MorpheusClient
for cloud in MorpheusClient().list_clouds():
    print(cloud['id'], cloud['name'])
"

# List networks
python -c "
from scripts.morpheus_client import MorpheusClient
for net in MorpheusClient().list_networks():
    print(net['id'], net['name'])
"
```

### Update each mapping file

Edit `config/mapping_dev.yml`, `config/mapping_test.yml`, and `config/mapping_prod.yml`. Replace placeholder IDs with the real ones for each environment:

```yaml
# config/mapping_test.yml — example after filling in real values
environment: test

clouds:
  DEV-Nutanix: 1        # Real ID in TEST Morpheus — verify via UI or API
  TEST-VMware: 2
  PROD-VMware: 3

networks:
  DEV-VLAN-100: 5
  TEST-VLAN-200: 5
  PROD-VLAN-300: 9

plans:
  plan-10: 4
  plan-12: 6
```

> Every logical name that appears in any YAML file under `environments/` must have an entry in each mapping file. If one is missing, the importer will error clearly before making any changes.

---

## Step 6 — Validate with Dry-Run

Before making any real changes to Morpheus, run the importer in dry-run mode:

```bash
python scripts/importer.py --env dev --dry-run
```

Dry-run:
- Loads all YAML files
- Validates every logical name against the mapping file
- Prints exactly what would be created or updated
- Makes **zero API calls**
- Exits with code 1 if anything is missing — fix mapping files and re-run

Only proceed once dry-run exits cleanly (code 0).

---

## Step 7 — Run the Real Import

```bash
python scripts/importer.py --env dev
```

This creates or updates blueprints and workflows in the real DEV Morpheus. Because the importer is idempotent (upsert logic), it is safe to run multiple times — existing objects are updated, not duplicated.

Verify the result in the Morpheus UI: *Provisioning → Blueprints* and *Library → Automation → Workflows*.

---

## Step 8 — Configure CI/CD Secrets

Stop using the `.env` file for pipeline credentials. Add the real URLs and tokens as protected, masked variables in your CI/CD system.

### GitHub Actions

Go to: **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `MORPHEUS_URL_DEV` | `https://morpheus-dev.company.com` |
| `MORPHEUS_TOKEN_DEV` | DEV API token |
| `MORPHEUS_URL_TEST` | `https://morpheus-test.company.com` |
| `MORPHEUS_TOKEN_TEST` | TEST API token |
| `MORPHEUS_URL_PROD` | `https://morpheus-prod.company.com` |
| `MORPHEUS_TOKEN_PROD` | PROD API token |

### GitLab CI

Go to: **Settings → CI/CD → Variables** — mark each as *Masked* and *Protected*.

Same variable names as above.

---

## Step 9 — Run the Full Pipeline End-to-End

With secrets in place, trigger the pipeline manually to confirm the full flow works:

1. Push a trivial YAML change to a `feature/` branch
2. Open a Merge Request / Pull Request to the `test` branch
3. Review and merge
4. Watch the pipeline: validate → dry-run → real import to TEST Morpheus
5. Verify the change appears in the TEST Morpheus UI
6. Open an MR from `test` to `main`
7. Merge, then trigger the `workflow_dispatch` (GitHub) or manual job (GitLab) for PROD
8. A reviewer approves → pipeline imports to PROD

---

## Step 10 — Enable Drift Detection

The drift detection job runs on a cron schedule and requires the real API to be reachable. Confirm the scheduled job is active in your CI/CD platform and that `MORPHEUS_URL_DEV` / `MORPHEUS_TOKEN_DEV` are set.

Run it manually to confirm it works:

```bash
python scripts/drift_detect.py --env dev
```

Expected output when Git and Morpheus are in sync:
```
Drift detection: Morpheus (dev) vs Git
============================================================
No drift detected. Git is the source of truth.
```

---

## What You Can Stop Using

Once the real API is connected and the pipeline is verified:

- The **mock server** (`mock_server/app.py`) is no longer needed for day-to-day work. You can keep it for offline development or for running `test_mock_server.py` integration tests without hitting the real API.
- The **sample JSON files** (`samples/`) remain useful for those tests — do not delete them.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `401 Unauthorized` on every call | Wrong or expired token | Regenerate token in Morpheus UI → User Settings → API Access |
| `ConnectionError` / timeout | Wrong base URL or network issue | Check VPN, firewall rules, and that the URL has no trailing slash |
| `ValueError: Cloud 'X' not found in mapping` | Missing entry in `config/mapping_<env>.yml` | Add the real ID for that logical name |
| `FileNotFoundError: mapping_test.yml` | Mapping file is empty/missing | Fill in `config/mapping_test.yml` with real IDs and commit it |
| Export writes empty YAML files | Morpheus instance has no objects yet | Normal for a fresh environment — create objects via UI first or import from DEV |
| Drift detected immediately after first import | Minor field differences between YAML and live state | Review the diff output; adjust exported YAML or accept as baseline with a new commit |
