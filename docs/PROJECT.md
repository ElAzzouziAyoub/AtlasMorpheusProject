# ATLAS — GitOps Pipeline for Morpheus / ACS

## What this project is about

Companies that use **Morpheus** (or Atlas Cloud Services) to manage cloud infrastructure typically do so through the GUI — clicking around to create blueprints, configure workflows, and set policies. When they want the same configuration in a TEST or PROD environment, they click it all again. There is no history of who changed what, no review process, and no way to roll back.

This project replaces that manual GUI work with **Git**. After this pipeline is in place, the workflow becomes:

1. Edit a YAML file in Git
2. Open a Merge Request
3. It gets reviewed and approved
4. A CI/CD pipeline automatically pushes the change into Morpheus

That's the whole idea. It's called **GitOps** — Git is the single source of truth for infrastructure configuration.

---

## Goals

| # | Goal | Description |
|---|------|-------------|
| F1 | Export | Fetch objects from Morpheus and store them as YAML files in Git |
| F2 | Versioning | Use Git branching and Merge Requests to review and approve changes |
| F3 | Automated deployment | CI/CD pipeline that imports changes into the right environment on merge |
| F4 | Multi-environment portability | Handle the fact that IDs (cloud IDs, network IDs) differ between DEV, TEST, and PROD |
| F5 | Drift detection | Detect when someone changes Morpheus directly through the GUI, bypassing Git |

---

## The core problem: Object IDs

This is the hardest part of the project and worth understanding clearly.

When you export a blueprint from DEV Morpheus, it contains internal IDs like:

```json
"cloudId": 3,
"network": { "id": "network-17" }
```

These IDs **do not exist in TEST or PROD**. Cloud ID 3 in DEV might be a Nutanix cluster. In TEST, the equivalent cloud might be ID 1. In PROD it might be ID 3 again but pointing to a completely different VMware cluster.

**Our solution:** a two-step translation.

- **Export:** replace numeric IDs with logical names (`cloudId: 3` → `cloudName: "DEV-Nutanix"`)
- **Import:** read a mapping config file (`config/mapping_<env>.yml`) that says "in TEST, DEV-Nutanix maps to cloud ID 1" and translate back

This makes the YAML files in Git **environment-agnostic** — they describe *what* you want, not *where* it lives.

---

## Project structure

```
ATLASproject/
│
├── .env.example                  Template for credentials (copy to .env, never commit .env)
├── .gitignore
├── .gitlab-ci.yml                GitLab CI/CD pipeline definition
├── requirements.txt              Python dependencies
│
├── config/
│   ├── mapping_dev.yml           Maps logical names → real IDs in DEV
│   ├── mapping_test.yml          Maps logical names → real IDs in TEST
│   └── mapping_prod.yml          Maps logical names → real IDs in PROD
│
├── environments/
│   ├── dev/
│   │   ├── blueprints/           YAML files exported from DEV Morpheus
│   │   └── workflows/
│   ├── test/
│   │   ├── blueprints/
│   │   └── workflows/
│   └── prod/
│       ├── blueprints/
│       └── workflows/
│
├── mock_server/
│   └── app.py                    Fake Morpheus API (Flask) for local development
│
├── samples/
│   ├── blueprints_list.json      Realistic sample API responses based on Morpheus docs
│   ├── workflows_list.json
│   ├── clouds_list.json
│   └── networks_list.json
│
├── scripts/
│   ├── morpheus_client.py        Single wrapper for all Morpheus API calls
│   ├── export.py                 Morpheus → YAML (the "pull" direction)
│   ├── importer.py               YAML → Morpheus (the "push" direction)
│   └── drift_detect.py           Compares live Morpheus state to Git
│
└── tests/
    ├── test_export.py            Tests for the export transformation logic
    ├── test_import.py            Tests for the ID re-mapping logic
    └── test_mock_server.py       Integration tests for the mock server endpoints
```

---

## Component breakdown

### `scripts/morpheus_client.py`

A thin HTTP client that wraps every Morpheus API endpoint we use. All other scripts import this module instead of calling `requests` directly.

The key design decision: it reads `MORPHEUS_URL` and `MORPHEUS_TOKEN` lazily (at call time, not at import time). This means you can import the module in tests without having credentials set — the error only fires when you actually try to make an API call.

### `scripts/export.py`

Fetches objects from Morpheus and writes them as YAML files into `environments/<env>/`.

The important transformation steps:
1. Strip top-level environment-specific fields (`id`, `owner`, `dateCreated`, `lastUpdated`)
2. Replace `cloudId: 3` with `cloudName: "DEV-Nutanix"` (using a live lookup of cloud names)
3. Replace `network.id: "network-17"` with `network.name: "DEV-VLAN-100"` (same approach)
4. Add a `_logical_name` field to plan references so the importer can resolve them

Currently supports: **blueprints** and **workflows**. Designed to be extended.

### `scripts/importer.py`

The reverse of export. Reads YAML files from `environments/<env>/` and pushes them into Morpheus.

Before pushing, it runs the **ID re-mapping** step: reads `config/mapping_<env>.yml` and translates logical names back to real IDs for the target environment. If a name is missing from the mapping, it raises a clear error rather than pushing bad data silently.

Uses **upsert logic**: if a blueprint with that name already exists in Morpheus, it updates it. If not, it creates it. This makes the import idempotent — you can run it multiple times safely.

Supports a `--dry-run` flag that validates and prints what would happen without making any changes.

### `scripts/drift_detect.py`

Scheduled script that answers: *"Has anyone changed Morpheus directly through the GUI without going through Git?"*

It exports the current live state of Morpheus (same normalisation as `export.py`), loads the YAML files from Git, and diffs them using `deepdiff`. Any differences are printed and the script exits with code 1, which fails the CI job and triggers an alert.

### `mock_server/app.py`

A Flask application that mimics the Morpheus API. It serves the sample JSON files in `samples/` at the correct endpoint paths, handles auth headers, and supports basic CRUD operations in memory.

**Why this exists:** Morpheus credentials are not always available during development — waiting for access can block weeks of work. The mock server lets you develop and test the entire pipeline locally. When real credentials arrive, you change one line (the base URL in `.env`) and everything works against the real system.

### `config/mapping_<env>.yml`

One file per environment. Maps human-readable logical names to the real numeric IDs that exist in that Morpheus instance.

```yaml
clouds:
  DEV-Nutanix: 3       # In DEV, "DEV-Nutanix" is cloud ID 3
  PROD-VMware: 12      # In DEV, "PROD-VMware" is cloud ID 12

networks:
  DEV-VLAN-100: 17     # In DEV, that network is ID 17
```

**These files must be filled in with real values once you have API access.** Until then, they contain placeholder values based on the sample data.

---

## CI/CD Pipeline

The GitLab pipeline (`.gitlab-ci.yml`) has four stages:

```
push to any branch
       │
       ▼
  [ validate ]
  - Check all YAML files are valid
  - Run the test suite
       │
       ▼ (merge to `test` branch only)
  [ deploy ]
  - Dry-run import to TEST (validate mapping)
  - Real import to TEST Morpheus
       │
       ▼ (merge to `main` branch, manual approval required)
  [ promote ]
  - Dry-run import to PROD
  - Real import to PROD Morpheus
       │
  [ drift ] ← runs on a schedule (e.g. daily at 6am)
  - Export live state, compare to Git
  - Fail job if drift is found
```

The PROD promotion step requires **manual approval** in GitLab — someone must click "Run" before it executes. This is the safety gate.

### Required CI/CD variables

Set these in GitLab → Settings → CI/CD → Variables (masked, not visible in logs):

| Variable | Description |
|----------|-------------|
| `MORPHEUS_URL_DEV` | Base URL of DEV Morpheus instance |
| `MORPHEUS_URL_TEST` | Base URL of TEST Morpheus instance |
| `MORPHEUS_URL_PROD` | Base URL of PROD Morpheus instance |
| `MORPHEUS_TOKEN_DEV` | API token for DEV |
| `MORPHEUS_TOKEN_TEST` | API token for TEST |
| `MORPHEUS_TOKEN_PROD` | API token for PROD |

---

## Branching model

```
main          ← PROD deployments (protected, MR required, manual pipeline)
 │
test          ← TEST deployments (protected, MR required, auto pipeline)
 │
feature/*     ← Daily work (open branches, no restrictions)
```

Work happens on `feature/` branches. When ready, open an MR to `test`. After validation in TEST, open an MR from `test` to `main` for PROD promotion.

---

## How to run locally

```bash
# 1. Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Set up credentials (pointing at mock for now)
cp .env.example .env
# Edit .env:
#   MORPHEUS_URL=http://localhost:5000
#   MORPHEUS_TOKEN=mock-token-dev
#   MORPHEUS_ENV=dev

# 3. Start the mock server
python mock_server/app.py

# 4. Export blueprints and workflows from the mock
python scripts/export.py --env dev

# 5. Check the exported YAML files
cat environments/dev/blueprints/ubuntu-web-server.yml

# 6. Test the import (dry-run first)
python scripts/importer.py --env dev --dry-run
python scripts/importer.py --env dev

# 7. Run drift detection
python scripts/drift_detect.py --env dev

# 8. Run the tests
pytest tests/ -v
```

---

## What to do when you get real Morpheus access

1. Update `.env` with the real `MORPHEUS_URL` and `MORPHEUS_TOKEN`
2. Run `python scripts/export.py --env dev` — this will hit the real API
3. Open the exported YAML files and compare the IDs to what you see in the Morpheus UI
4. Fill in `config/mapping_dev.yml` with the real cloud and network IDs
5. Repeat for TEST and PROD environments
6. Run the full round-trip: export from DEV → commit → merge to `test` → pipeline imports to TEST

---

## Work split

| Person A | Person B |
|----------|----------|
| Export script (`export.py`) | Import script (`importer.py`) |
| Git repo structure & branching | CI/CD pipeline (`.gitlab-ci.yml`) |
| Drift detection (`drift_detect.py`) | Secrets management (CI/CD variables) |
| Both together: API exploration, mapping config, testing, documentation, report |

---

## Object types roadmap

| Object type | Status |
|-------------|--------|
| Blueprints | Implemented |
| Workflows (task sets) | Implemented |
| Policies | To do |
| Instance types | To do |
| Tasks | To do |
| Catalog items | To do |

Start with blueprints and workflows — they cover the most common use cases. Expand once the end-to-end flow is validated.
