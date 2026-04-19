# ATLAS — GitOps Pipeline for Morpheus Infrastructure

ATLAS is a GitOps automation pipeline that brings **version control, code review, and automated deployment** to Morpheus cloud infrastructure. Instead of managing infrastructure through a GUI, every change is tracked in Git, reviewed via Pull Requests, and deployed automatically through a CI/CD pipeline.

---

## Table of Contents

1. [The Problem It Solves](#the-problem-it-solves)
2. [How It Works — Big Picture](#how-it-works--big-picture)
3. [The Key Technical Challenge: Environment IDs](#the-key-technical-challenge-environment-ids)
4. [Project Structure](#project-structure)
5. [Components In Detail](#components-in-detail)
   - [morpheus\_client.py — API Layer](#morpheus_clientpy--api-layer)
   - [export.py — Pull from Morpheus](#exportpy--pull-from-morpheus)
   - [importer.py — Push to Morpheus](#importerpy--push-to-morpheus)
   - [drift\_detect.py — Drift Detection](#drift_detectpy--drift-detection)
   - [mock\_server — Local Development](#mock_server--local-development)
   - [config/mapping\_\*.yml — ID Translation Tables](#configmapping_yml--id-translation-tables)
6. [CI/CD Pipeline](#cicd-pipeline)
7. [Branching Model](#branching-model)
8. [Full Data Flow](#full-data-flow)
9. [File Formats](#file-formats)
10. [Environment Variables & Secrets](#environment-variables--secrets)
11. [Running Locally](#running-locally)
12. [Running Tests](#running-tests)
13. [Tech Stack](#tech-stack)
14. [Security](#security)
15. [Common Errors](#common-errors)

---

## The Problem It Solves

Companies using **Morpheus** (a cloud infrastructure management platform) typically manage things like blueprints, workflows, and policies through a web GUI — clicking buttons to create and modify configurations.

This approach has serious problems:

| Problem | Impact |
|---------|--------|
| No version history | Nobody knows what changed, when, or why |
| No review process | Changes go live without approval |
| No rollback | Reverting a mistake is manual and risky |
| Repetitive manual work | Every environment (DEV, TEST, PROD) must be configured by hand |
| Config drift | Someone edits the GUI; nobody notices; environments diverge |

**ATLAS solves all of these** by making Git the single source of truth:

- Infrastructure config is stored as YAML files in Git
- Changes require a Pull Request with code review
- CI/CD automatically deploys on merge
- Daily drift detection catches unauthorized GUI changes
- Rollback = reverting a Git commit

---

## How It Works — Big Picture

```
Developer edits YAML file
         ↓
   git push → opens PR
         ↓
  Code review + approval
         ↓
   Merge to "test" branch
         ↓
GitHub Actions Pipeline:
  1. Validate YAML syntax
  2. Run tests
  3. Dry-run import (validate only)
  4. Real import → TEST Morpheus
         ↓
  Validated in TEST environment
         ↓
   Merge to "main" branch
   + manual workflow trigger
         ↓
  Required reviewers approve
         ↓
  Real import → PROD Morpheus
         ↓
  Daily: drift detection check
```

---

## The Key Technical Challenge: Environment IDs

This is the **hardest problem** the project solves, and understanding it is key to understanding everything else.

### The Problem

When Morpheus creates a cloud, a network, or a service plan, it assigns an internal integer ID. These IDs are **different in every environment**:

| Resource | DEV | TEST | PROD |
|----------|-----|------|------|
| Nutanix Cloud | ID `3` | ID `1` | ID `2` |
| VLAN-100 Network | ID `17` | ID `5` | ID `11` |
| Standard Plan | ID `12` | ID `6` | ID `10` |

So if you export a blueprint from DEV and it contains `cloudId: 3`, that ID is **meaningless** (or points to the wrong thing) in TEST and PROD.

### The Solution: Logical Names + Mapping Files

ATLAS uses a two-step process:

**Step 1 — Export (DEV → Git):**  
Replace every raw ID with a human-readable logical name:
```
cloudId: 3  →  cloudName: "DEV-Nutanix"
network.id: 17  →  network.name: "DEV-VLAN-100"
```

The YAML file stored in Git now contains names, not IDs — it is **environment-agnostic**.

**Step 2 — Import (Git → any environment):**  
Before pushing to TEST or PROD, look up the logical name in a mapping file to get the correct local ID:

`config/mapping_test.yml`:
```yaml
clouds:
  DEV-Nutanix: 1       # In TEST, this cloud is ID 1
networks:
  DEV-VLAN-100: 5      # In TEST, this network is ID 5
```

So `cloudName: "DEV-Nutanix"` becomes `cloudId: 1` in TEST, and `cloudId: 2` in PROD.  
The same YAML file works everywhere. You just maintain the mapping files per environment.

---

## Project Structure

```
ATLASproject/
│
├── .env                        Credentials (git-ignored, never committed)
├── .env.example                Template — copy this to .env and fill in values
├── requirements.txt            Python dependencies
├── GUIDE.md                    Step-by-step usage tutorial
│
├── .github/
│   └── workflows/
│       └── pipeline.yml        GitHub Actions CI/CD pipeline
│
├── config/
│   ├── mapping_dev.yml         Logical name → real ID for DEV Morpheus
│   ├── mapping_test.yml        Logical name → real ID for TEST Morpheus
│   └── mapping_prod.yml        Logical name → real ID for PROD Morpheus
│
├── environments/               YAML files exported from Morpheus (tracked in Git)
│   ├── dev/
│   │   ├── blueprints/         e.g. ubuntu-web-server.yml, nginx-lb.yml
│   │   └── workflows/          e.g. provision-web-server.yml
│   ├── test/
│   │   ├── blueprints/
│   │   └── workflows/
│   └── prod/
│       ├── blueprints/
│       └── workflows/
│
├── mock_server/
│   ├── __init__.py
│   └── app.py                  Flask server that fakes the Morpheus API (for local dev)
│
├── samples/                    Static JSON loaded by the mock server
│   ├── blueprints_list.json
│   ├── workflows_list.json
│   ├── clouds_list.json
│   └── networks_list.json
│
├── scripts/
│   ├── __init__.py
│   ├── morpheus_client.py      HTTP wrapper — all Morpheus API calls go through here
│   ├── export.py               Fetch from Morpheus, transform, write YAML to Git
│   ├── importer.py             Read YAML from Git, transform back, push to Morpheus
│   ├── drift_detect.py         Compare live Morpheus state vs Git, report differences
│   └── rollback.sh             Emergency rollback from Git history
│
└── tests/
    ├── __init__.py
    ├── test_export.py          Unit tests for ID→Name transformation
    ├── test_import.py          Unit tests for Name→ID re-mapping
    └── test_mock_server.py     Integration tests for Flask mock endpoints
```

---

## Components In Detail

### `morpheus_client.py` — API Layer

**Role**: The only file that talks directly to the Morpheus REST API. All other scripts import it instead of making raw HTTP calls.

**What it wraps**:

| Method | HTTP Call | Description |
|--------|-----------|-------------|
| `list_blueprints()` | `GET /api/blueprints` | Fetch all blueprints (handles pagination) |
| `get_blueprint(id)` | `GET /api/blueprints/{id}` | Fetch one blueprint |
| `create_blueprint(data)` | `POST /api/blueprints` | Create a new blueprint |
| `update_blueprint(id, data)` | `PUT /api/blueprints/{id}` | Update existing blueprint |
| `list_workflows()` | `GET /api/task-sets` | Fetch all workflows |
| `get_workflow(id)` | `GET /api/task-sets/{id}` | Fetch one workflow |
| `create_workflow(data)` | `POST /api/task-sets` | Create a workflow |
| `update_workflow(id, data)` | `PUT /api/task-sets/{id}` | Update workflow |
| `list_clouds()` | `GET /api/zones` | Fetch all cloud providers |
| `list_networks()` | `GET /api/networks` | Fetch all networks |

**Authentication**: Uses `Authorization: Bearer {token}` header with the token from `.env`.

**Pagination**: Morpheus returns max 100 items per page. The client automatically loops through all pages.

---

### `export.py` — Pull from Morpheus

**Role**: Fetches live configuration from Morpheus and saves it as portable YAML files in `environments/{env}/`.

**Step-by-step what it does**:

1. **Fetch all blueprints and workflows** via `morpheus_client`
2. **Build lookup maps** from the live API (e.g., `{3: "DEV-Nutanix"}` for clouds)
3. **Strip environment-specific metadata** (top-level `id`, `owner`, `dateCreated`, `lastUpdated`, `resourcePermission`)
4. **Replace IDs with logical names**:
   - `cloudId: 3` → `cloudName: "DEV-Nutanix"`
   - `network.id: 17` → `network.name: "DEV-VLAN-100"`
   - `plan.id: 12` → adds `plan._logical_name: "plan-12"` alongside the original ID
5. **Write YAML files** to `environments/{env}/blueprints/` or `environments/{env}/workflows/`

**Usage**:
```bash
python scripts/export.py --env dev                        # Export everything from DEV
python scripts/export.py --env dev --type blueprints      # Only blueprints
python scripts/export.py --env test --type workflows      # Only workflows from TEST
```

**Before/After Example**:

Raw API response:
```json
{
  "id": 1,
  "name": "ubuntu-web-server",
  "owner": {"id": 1, "username": "admin"},
  "dateCreated": "2024-01-15T09:00:00Z",
  "cloudId": 3,
  "network": {"id": "network-17"},
  "plan": {"id": 12}
}
```

YAML written to Git:
```yaml
name: ubuntu-web-server
config:
  tiers:
    App:
      instances:
        - cloudName: DEV-Nutanix
          networkInterfaces:
            - network:
                name: DEV-VLAN-100
          plan:
            id: 12
            _logical_name: plan-12
```

---

### `importer.py` — Push to Morpheus

**Role**: Reads YAML files from Git and pushes them into a Morpheus environment, translating logical names back to real IDs.

**Step-by-step what it does**:

1. **Load mapping file** for the target environment (`config/mapping_{env}.yml`)
2. **Validate all references** — every logical name in the YAML must exist in the mapping. If not, it errors clearly:
   ```
   ERROR: Cloud 'DEV-Nutanix' not found in mapping for env 'test'.
   Update config/mapping_test.yml
   ```
3. **Replace logical names with real IDs** for the target environment
4. **Upsert** (create or update) in Morpheus — checks if an object with the same name already exists, updates it if so, creates it if not. This makes imports **idempotent** (safe to run multiple times with the same result)

**Usage**:
```bash
python scripts/importer.py --env test --dry-run      # Validate only, no API calls
python scripts/importer.py --env test                # Real import to TEST
python scripts/importer.py --env prod --dry-run      # Validate before PROD import
python scripts/importer.py --env prod                # Real import to PROD
```

**Dry-run mode** is critical: it loads all YAML, validates all mappings, prints exactly what would happen, but **makes zero API calls**. If anything is wrong, it exits with code 1 and fails the CI/CD job before any changes are made.

---

### `drift_detect.py` — Drift Detection

**Role**: Scheduled script that detects when someone changes Morpheus through the GUI, bypassing Git.

**Algorithm**:

1. Fetch live state from Morpheus API
2. Normalize it (same ID→Name transformation as export)
3. Load YAML files from `environments/{env}/`
4. Deep-compare using `deepdiff` library (ignores field ordering)
5. Report findings:

```
Drift detection: Morpheus (dev) vs Git
============================================================
DRIFT DETECTED — 1 finding(s):

  [CHANGED] blueprints/nginx-lb:
    values_changed: {
      "root['description']": {
        'new_value': 'CHANGED IN GUI',
        'old_value': 'NGINX load balancer'
      }
    }

Action: open a Git issue or MR to reconcile the drift.
```

**Finding types**:
- `[EXTRA]` — Object exists in Morpheus but not in Git (created through GUI)
- `[MISSING]` — Object exists in Git but not in Morpheus (deleted through GUI)
- `[CHANGED]` — Field differences detected

**Exit codes**: `0` = no drift (CI passes), `1` = drift found (CI fails, triggers alert)

**Usage**:
```bash
python scripts/drift_detect.py --env dev
python scripts/drift_detect.py --env dev --type blueprints
```

---

### `mock_server` — Local Development

**Role**: A Flask application that mimics the Morpheus REST API, so developers can build and test everything locally without real Morpheus credentials.

**Why it exists**: Getting access to a real Morpheus platform takes time. Without the mock server, the whole project would be blocked on credential access. With it, you can develop and test the entire pipeline locally.

**Endpoints it implements**:
```
GET  /api/ping
GET  /api/blueprints          (paginated)
GET  /api/blueprints/{id}
POST /api/blueprints
PUT  /api/blueprints/{id}
DELETE /api/blueprints/{id}
GET  /api/task-sets           (paginated)
GET  /api/task-sets/{id}
POST /api/task-sets
PUT  /api/task-sets/{id}
GET  /api/zones               (clouds)
GET  /api/networks
```

**Authentication**: Accepts any non-empty Bearer token. Returns `401` if missing.

**Data**: Loads sample JSON from `samples/` on startup. Stores in memory (resets on restart — keeps tests independent).

**Pre-loaded sample data**:
- Blueprints: `ubuntu-web-server`, `nginx-lb`
- Workflows: `provision-web-server`, `decommission-cleanup`
- Clouds: `DEV-Nutanix` (ID 3), `TEST-VMware` (ID 7), `PROD-VMware` (ID 12)
- Networks: `DEV-VLAN-100` (ID 17), `TEST-VLAN-200` (ID 23), `PROD-VLAN-300` (ID 31)

**Starting the mock server**:
```bash
python mock_server/app.py
# → http://localhost:5000
# → Use Authorization: Bearer mock-token-dev
```

---

### `config/mapping_*.yml` — ID Translation Tables

**Role**: One file per environment, mapping every logical name to its real local ID. These are what make the same YAML file deployable to DEV, TEST, and PROD.

**Structure**:
```yaml
environment: test

clouds:
  DEV-Nutanix: 1         # In TEST, this cloud exists as ID 1
  TEST-VMware: 2
  PROD-VMware: 3

networks:
  DEV-VLAN-100: 5        # In TEST, this network is ID 5
  TEST-VLAN-200: 5
  PROD-VLAN-300: 9

plans:
  plan-10: 4
  plan-12: 6
```

**How to populate**: After connecting to a real Morpheus instance:
1. Run `export.py` — this fetches the live ID-to-name mapping
2. Cross-reference with the YAML files to see which logical names are used
3. Fill in the correct IDs for the target environment
4. Validate with `importer.py --dry-run`

---

## CI/CD Pipeline

The pipeline lives in `.github/workflows/pipeline.yml` and has 4 stages.

### Stage 1 — VALIDATE
**Triggered by**: Every push to any branch

**Jobs**:
- `validate-yaml` — Parses every `.yml` file in `environments/` to catch syntax errors
- `tests` — Runs the full pytest test suite

Both must pass before downstream stages run.

---

### Stage 2 — DEPLOY to TEST
**Triggered by**: Push to the `test` branch (after a PR merge)

**Requires**: Stage 1 passing

**Steps**:
1. `python scripts/importer.py --env test --dry-run` — Validates everything, no changes
2. `python scripts/importer.py --env test` — Creates/updates blueprints and workflows in TEST Morpheus

**GitHub secrets required**: `MORPHEUS_URL_TEST`, `MORPHEUS_TOKEN_TEST`

---

### Stage 3 — PROMOTE to PROD
**Triggered by**: Manual `workflow_dispatch` (someone clicks "Run workflow" in GitHub Actions)

> **Why manual?** GitHub's required-reviewer approval only works on `workflow_dispatch` events, not on pushes. This ensures a human must deliberately trigger the PROD deployment, and required reviewers must approve before it executes.

**Steps**:
1. `python scripts/importer.py --env prod --dry-run` — Validate
2. `python scripts/importer.py --env prod` — Deploy to PROD Morpheus

**GitHub secrets required**: `MORPHEUS_URL_PROD`, `MORPHEUS_TOKEN_PROD`

**To set up approval gates**: GitHub → Settings → Environments → `production` → Add required reviewers

---

### Stage 4 — DRIFT DETECTION
**Triggered by**: Daily cron at `06:00 UTC` (and also on `workflow_dispatch`)

**Step**:
- `python scripts/drift_detect.py --env dev`

**Result**: If drift is found, the job fails and GitHub sends an alert notification. A developer must then open a PR to reconcile the divergence.

**GitHub secrets required**: `MORPHEUS_URL_DEV`, `MORPHEUS_TOKEN_DEV`

---

### All Required GitHub Secrets

Go to: **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|-------------|-------|
| `MORPHEUS_URL_DEV` | `https://morpheus-dev.company.com` |
| `MORPHEUS_TOKEN_DEV` | DEV API token |
| `MORPHEUS_URL_TEST` | `https://morpheus-test.company.com` |
| `MORPHEUS_TOKEN_TEST` | TEST API token |
| `MORPHEUS_URL_PROD` | `https://morpheus-prod.company.com` |
| `MORPHEUS_TOKEN_PROD` | PROD API token |

---

## Branching Model

```
main ──────────────────────────────────────────────────────►
      ↑                             ↑
      │  PR + review + approval     │  PR + review
      │                             │
test ─────────────────────────────────────────────────────►
           ↑                  ↑
           │  PR + review     │  PR + review
           │                  │
feature/change-X        feature/add-workflow-Y
```

**Standard workflow**:
1. Create `feature/your-description` branch from `test`
2. Edit YAML files
3. Commit and push
4. Open Pull Request to `test`
5. Reviewer approves and merges
6. Pipeline auto-deploys to TEST Morpheus
7. After TEST validation, open PR from `test` to `main`
8. Additional review
9. Merge to `main`
10. Go to GitHub Actions → Run workflow (workflow\_dispatch)
11. Required reviewers approve
12. Pipeline deploys to PROD

---

## Full Data Flow

```
┌─────────────────┐
│  DEV Morpheus   │ ← Real cloud infrastructure platform
└────────┬────────┘
         │  GET /api/blueprints, /api/zones, /api/networks
         ↓
┌─────────────────────────────┐
│  export.py                  │
│  - Replace IDs with names   │
│  - Strip ephemeral fields   │
│  - Write YAML files         │
└────────┬────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│  Git Repository             │
│  environments/dev/*.yml     │ ← Version controlled, reviewed
└────────┬────────────────────┘
         │  PR → merge to "test"
         ↓
┌─────────────────────────────┐
│  GitHub Actions Pipeline    │
│  1. Validate YAML           │
│  2. Run tests               │
│  3. Dry-run import          │
│  4. Real import             │
└────────┬────────────────────┘
         │  using config/mapping_test.yml
         │  to translate names back to TEST IDs
         ↓
┌─────────────────┐
│  TEST Morpheus  │ ← Same config, different IDs
└─────────────────┘
         │  (repeat for PROD with workflow_dispatch + approval)
         ↓
┌─────────────────┐
│  PROD Morpheus  │
└─────────────────┘

      Every day at 06:00 UTC:
┌─────────────────────────────┐
│  drift_detect.py            │
│  Live Morpheus ↔ Git YAML   │ → Alert if diverged
└─────────────────────────────┘
```

---

## File Formats

### Blueprint YAML (stored in `environments/`)

```yaml
name: ubuntu-web-server
type: morpheus
description: Standard Ubuntu 22.04 web server blueprint
visibility: private
config:
  name: ubuntu-web-server
  type: morpheus
  tiers:
    App:
      tierIndex: 1
      linkedTiers: []
      instances:
        - instance:
            type: ubuntu
            name: ${userInitials}-ubuntu-${sequence}
            instanceContext: production
          cloudName: DEV-Nutanix          # ← logical name, not raw ID
          networkInterfaces:
            - network:
                name: DEV-VLAN-100        # ← logical name
          volumes:
            - name: root
              rootVolume: true
              size: 20
              storageType: 1
          plan:
            id: 12
            _logical_name: plan-12        # ← logical reference kept alongside ID
```

### Workflow YAML

```yaml
name: provision-web-server
description: Post-provision setup for web servers
type: provision
visibility: private
tasks:
  - name: install-nginx
    order: 1
    taskType:
      name: Shell Script
    executeTarget: resource
  - name: configure-firewall
    order: 2
    taskType:
      name: Shell Script
    executeTarget: resource
```

---

## Environment Variables & Secrets

### `.env` (local file, never committed)

```bash
MORPHEUS_URL=http://localhost:5000     # Point to mock server locally
MORPHEUS_TOKEN=mock-token-dev          # Any value works with mock server
MORPHEUS_ENV=dev
```

Copy from template:
```bash
cp .env.example .env
# Then edit .env with your values
```

For production use, replace with real Morpheus URL and API token.

---

## Running Locally

### Prerequisites

- Python 3.11+
- Git

### Setup

```bash
# Clone the repo
git clone https://github.com/your-org/ATLASproject.git
cd ATLASproject

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate      # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure credentials
cp .env.example .env
# .env already points to localhost:5000 for local development
```

### Start the mock server (Terminal 1)

```bash
python mock_server/app.py
# → Mock Morpheus API running at http://localhost:5000
```

### Run the pipeline (Terminal 2)

```bash
# Export from mock "DEV Morpheus"
python scripts/export.py --env dev

# Validate the import (dry-run — no changes)
python scripts/importer.py --env dev --dry-run

# Actually import
python scripts/importer.py --env dev

# Check for drift
python scripts/drift_detect.py --env dev
```

### Emergency rollback

```bash
./scripts/rollback.sh --env test
# Reverts TEST Morpheus to the state from the previous Git commit
```

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run only export tests
pytest tests/test_export.py -v

# Run a single test
pytest tests/test_export.py::test_blueprint_replaces_cloud_id_with_name -v
```

**Test coverage**:
- `test_export.py` — Unit tests for the ID→Name transformation logic
- `test_import.py` — Unit tests for the Name→ID re-mapping logic
- `test_mock_server.py` — Integration tests for all Flask mock API endpoints

All tests run without a real Morpheus instance.

---

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Core language |
| requests | 2.31.0 | HTTP client for Morpheus API calls |
| PyYAML | 6.0.1 | Read/write YAML configuration files |
| Flask | 3.0.3 | Mock Morpheus API server |
| deepdiff | 6.7.1 | Deep comparison of nested objects (drift detection) |
| pytest | 8.1.1 | Test framework |
| python-dotenv | 1.0.1 | Load `.env` file for credentials |
| GitHub Actions | — | CI/CD pipeline automation |

---

## Security

| Measure | How |
|---------|-----|
| Credentials never in Git | `.env` is in `.gitignore`; secrets stored in GitHub Secrets |
| No accidental changes | Every import runs dry-run first; dry-run makes zero API calls |
| PROD gated by humans | `workflow_dispatch` + required reviewers must approve |
| Drift alerts | Daily job fails if unauthorized GUI changes detected |
| Rollback available | `rollback.sh` re-imports previous Git state |
| Secret masking | GitHub Actions masks secret values in all log output |

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `EnvironmentError: MORPHEUS_URL not set` | `.env` missing or empty | Copy `.env.example` → `.env` and fill values |
| `ConnectionRefusedError` | Mock server not running | Run `python mock_server/app.py` first |
| `FileNotFoundError: mapping_test.yml` | Mapping config not populated | Fill in `config/mapping_test.yml` with real IDs |
| `ValueError: Cloud 'X' not found in mapping` | Missing entry in mapping file | Add `X: <real_id>` to `config/mapping_{env}.yml` |
| `401 Unauthorized` | Wrong or missing API token | Check `MORPHEUS_TOKEN` in `.env` |
| `YAML parse error` | Bad indentation in `.yml` file | Fix YAML syntax (use spaces, not tabs) |
| CI job fails on validate-yaml | Syntax error in exported YAML | Run `python -c "import yaml; yaml.safe_load(open('file.yml'))"` locally |

---

## Glossary

| Term | Meaning |
|------|---------|
| **Blueprint** | An infrastructure template in Morpheus (defines a VM, its OS, network, storage) |
| **Workflow / Task Set** | A sequence of automated steps run during provisioning (e.g., install nginx, configure firewall) |
| **Cloud / Zone** | A cloud provider or datacenter registered in Morpheus (e.g., Nutanix, VMware) |
| **GitOps** | The practice of using Git as the single source of truth for infrastructure configuration |
| **Idempotent** | An operation that produces the same result regardless of how many times it is run |
| **Drift** | When the live system state diverges from what is described in Git |
| **Upsert** | Create if not exists, update if exists |
| **Logical name** | A human-readable, environment-agnostic identifier used instead of raw integer IDs |
| **Dry-run** | A mode that validates and simulates an operation without making any real changes |
| **workflow\_dispatch** | A GitHub Actions trigger that requires a human to manually click "Run workflow" |
