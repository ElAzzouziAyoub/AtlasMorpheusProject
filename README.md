<div align="center">

<pre>
 █████╗ ████████╗██╗      █████╗ ███████╗
██╔══██╗╚══██╔══╝██║     ██╔══██╗██╔════╝
███████║   ██║   ██║     ███████║███████╗
██╔══██║   ██║   ██║     ██╔══██║╚════██║
██║  ██║   ██║   ███████╗██║  ██║███████║
╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝
</pre>

<blockquote>

<p align="center">
<!-- Consistent badge style: flat-square, with logos -->

<!-- Version, License -->
<img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="MIT License" />

<!-- Languages & Tools -->
<img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
<img src="https://img.shields.io/badge/GitLab_CI-181717?style=flat-square&logo=gitlab&logoColor=white" alt="GitLab CI" />
<img src="https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask&logoColor=white" alt="Flask" />

<!-- Libraries -->
<img src="https://img.shields.io/badge/Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="Pytest" />

<!-- Domains -->
<img src="https://img.shields.io/badge/GitOps-000000?style=flat-square&logo=git&logoColor=white" alt="GitOps" />
<img src="https://img.shields.io/badge/Morpheus-326CE5?style=flat-square&logo=cloud&logoColor=white" alt="Morpheus" />


</p>

</blockquote>


</div>

# ☁️ ATLAS — GitOps Pipeline for Morpheus / ACS

<div align="center">

</div>

Replacing manual GUI work in Morpheus with automated, version-controlled infrastructure as code.

## Installation

Clone this repo and build your Python environment.  
*(Requires Python 3.8+)*

```sh
git clone https://github.com/yourusername/AtlasMorpheusProject.git
cd AtlasMorpheusProject
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Project Structure

```
ATLASproject/
├── config/                # Environment ID mappings
│   ├── mapping_dev.yml
│   ├── mapping_test.yml
│   └── mapping_prod.yml
├── docs/                  # Project documentation files
├── environments/          # Exported YAML definitions
│   ├── dev/
│   ├── test/
│   └── prod/
├── mock_server/           # Fake Morpheus API for local development
│   └── app.py
├── samples/               # Realistic sample API responses
├── scripts/               # Core pipeline scripts
│   ├── morpheus_client.py # HTTP client wrapper
│   ├── export.py          # Morpheus -> YAML
│   ├── importer.py        # YAML -> Morpheus
│   └── drift_detect.py    # Live state vs Git comparison
└── tests/                 # Unit and integration tests
```

## Dependencies

- **Python 3.8+**: Core programming language
- **Flask**: Used to run the mock API server locally
- **Requests**: HTTP client for API interaction
- **Pytest**: Unit testing framework

## Step-by-Step Guide

### 1. Start the Mock Server
In **Terminal 1**, run the fake Morpheus server. Every script you run talks to it.
```bash
source .venv/bin/activate
python mock_server/app.py
```

### 2. Set Up Credentials
In **Terminal 2**, copy the example config and verify your `.env` file:
```bash
cp .env.example .env
cat .env
```
*(Expected: `MORPHEUS_URL=http://localhost:5000` and `MORPHEUS_TOKEN=mock-token-dev`)*

### 3. Explore the API by Hand (curl)
Ping the server and list blueprints directly to understand the raw API:
```bash
curl -s http://localhost:5000/api/ping
curl -s http://localhost:5000/api/blueprints -H "Authorization: Bearer mock-token-dev" | python3 -m json.tool
```

### 4. Run the Export Script
Fetch objects from Morpheus and write them as YAML files into `environments/dev/`:
```bash
python scripts/export.py --env dev
```
Check `environments/dev/blueprints/` and notice that numeric IDs (`cloudId: 3`) have been replaced by logical names (`cloudName: DEV-Nutanix`)!

### 5. Run the Import Script
Read the YAML files and push them back into Morpheus. Always run with `--dry-run` first to see what would happen:
```bash
python scripts/importer.py --env dev --dry-run
python scripts/importer.py --env dev
```

### 6. Test Drift Detection
Drift detection answers: *"Has someone changed Morpheus directly through the GUI, bypassing Git?"*
```bash
python scripts/drift_detect.py --env dev
```
If you manually change a blueprint via `curl` PUT request and run it again, it will detect the drift and fail!

## Configuration & Mappings

When exporting, logical names are built. When importing, `config/mapping_<env>.yml` acts as the translation table:
* Logical name `DEV-Nutanix` = cloud ID `3` in DEV Morpheus
* Logical name `DEV-VLAN-100` = network ID `17` in DEV Morpheus

```yaml
clouds:
  DEV-Nutanix: 3       # In DEV, "DEV-Nutanix" is cloud ID 3
  PROD-VMware: 12      # In DEV, "PROD-VMware" is cloud ID 12

networks:
  DEV-VLAN-100: 17     # In DEV, that network is ID 17
```

## Testing

Run the comprehensive test suite to validate logic without the mock server:
```bash
pytest tests/ -v
```

### Test Coverage
- **Export Logic**: Transformation and normalization of exported API data
- **Import Mapping**: ID re-mapping and validation logic
- **Mock Server**: Integration tests for all endpoints

## Switching to Real Morpheus

When you get real credentials, simply update your `.env`:
```bash
MORPHEUS_URL=https://your-real-morpheus-instance.com
MORPHEUS_TOKEN=your-real-api-token
MORPHEUS_ENV=dev
```
Then find the real IDs by curling your actual Morpheus instance (`/api/zones`, `/api/networks`) and fill in `config/mapping_dev.yml`. Everything else works identically!

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `EnvironmentError: MORPHEUS_URL is not set` | `.env` file missing or wrong path | Check `.env` exists in the project root |
| `ConnectionError: Failed to resolve ...` | Mock server not running | Start `python mock_server/app.py` in a separate terminal |
| `FileNotFoundError: mapping_test.yml` | You ran import for `test` but no mapping exists | Fill in `config/mapping_test.yml` with real IDs |
| `ValueError: Cloud 'X' not found in mapping` | A cloud name in your YAML is not in the mapping file | Add the entry to `config/mapping_<env>.yml` |
| `401 Unauthorized` | Wrong or missing token | Check `MORPHEUS_TOKEN` in `.env` matches the header |

## Quick Reference

```bash
# Setup & Mock Server
source .venv/bin/activate
python mock_server/app.py

# Scripts
python scripts/export.py --env dev
python scripts/importer.py --env dev --dry-run
python scripts/drift_detect.py --env dev
pytest tests/ -v
```

## CI/CD Pipeline

The GitLab pipeline (`.gitlab-ci.yml`) is divided into 4 stages:

1. **Validate**: Syntax and unit tests (all branches)
2. **Deploy**: Import to TEST environment (on merge to `test` branch)
3. **Promote**: Import to PROD environment (on merge to `main` branch, manual approval)
4. **Drift Detection**: Scheduled sync to detect manual GUI changes

## Motivation & What I Learned

Companies that use Morpheus to manage cloud infrastructure typically do so through the GUI — clicking around to create blueprints, configure workflows, and set policies. When they want the same configuration in a TEST or PROD environment, they click it all again. There is no history of who changed what, no review process, and no way to roll back.

This project was built to replace manual GUI work with GitOps. By simulating a real-world orchestration system I practiced:

- Abstracting environment-specific numeric IDs into logical names
- Establishing robust CI/CD deployment gates
- Creating mock servers for isolated development
- Enforcing infrastructure-as-code principles

## License

Distributed under the MIT License. See [LICENSE](./LICENSE) for details.

## Author

**Yasser BAOUZIL**
**Ayoub EL AZZOUZI**
