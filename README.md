# SchemaGuard

**DB Schema Validator** — extract, validate, version and compare database schemas across Snowflake, Oracle,
PostgreSQL and SQLite through a lightweight Blue/White enterprise UI, a REST API,
and a CLI — all three backed by the exact same core services.


## 1. Architecture Summary

```
UI (Jinja2 + HTMX + Bootstrap 5)  ─┐
REST API (FastAPI)                ├─► Services ─► Connectors / Schema / Comparison / Reporting
CLI (Typer, `python -m dbvalidator`) ┘
```

  persisted object needed to connect to a database. Runtime connectors are
  created on demand via a `ConnectorFactory` and are never persisted.
  by `SQLiteConnector`, `PostgreSQLConnector`, `OracleConnector`, and
  `SnowflakeConnector` (PAT auth). New types (SQL Server, MySQL, DB2,
  Redshift, Databricks, BigQuery, ...) register via
  `app.connectors.factory.register_connector()` without touching existing code.
  versioned JSON format (`app/schema/canonical.py`), with datatype
  normalization in `strict` or `compatible` mode (`app/schema/normalization.py`).
  canonical schemas — no I/O — so it is identical whether invoked from the
  API, the UI, or the CLI, and is fully unit-testable.
  ends_with, contains, exact, wildcard, and regex matching with independent
  include/exclude pattern lists. Filters are evaluated **independently**
  against each side of a comparison, so they narrow scope without ever
  hiding a genuine difference.
  `data/schemas/<id>/vN.json`; HTML reports live under
  `data/reports/YYYY/MM/<comparison-id>.html`. SQLite (`data/app.db`) stores
  only metadata rows, never the large payloads.
  (`app/security/secret_service.py`), driven by an environment-provided
  master key that is never written to `app.db`, masked in every API
  response and UI view, and scrubbed from log output.


## 2. Project Structure

```
db-schema-validator/
├── app/
│   ├── main.py                 # FastAPI app wiring
│   ├── web.py                  # Server-rendered UI page routes
│   ├── config.py, database.py, models.py, logging_config.py
│   ├── api/                    # REST routers
│   ├── connectors/             # Abstract base + Snowflake/Oracle/Postgres/SQLite + factory
│   ├── schema/                 # Canonical schema model + datatype normalization
│   ├── filters/                # Filter matching engine
│   ├── comparison/             # Severity rules, result models, comparison engine
│   ├── services/                # Config/filter/extraction/schema/comparison/report services
│   ├── storage/                # File-based schema JSON + HTML report storage
│   ├── security/                # SecretService (encryption)
│   ├── reports/                 # Compact HTML report template + renderer
│   ├── cli/                     # Typer CLI (shares services with API/UI)
│   ├── templates/               # Jinja2 pages (Blue/White theme)
│   └── static/                  # CSS + JS
├── dbvalidator/                 # `python -m dbvalidator` entrypoint wrapper
├── data/                        # app.db, schemas/, reports/, uploads/ (created at runtime)
├── test_data/                   # source.db / destination.db (generated)
├── scripts/create_test_databases.py
├── tests/{unit,integration,e2e}/
├── config/comparison_rules.yaml
├── requirements.txt, requirements-dev.txt, .env.example
└── README.md
```


## 3. Installation

```bash
cd SchemaGuard
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
# for running the test suite:
pip install -r requirements-dev.txt
```

`psycopg2-binary`, `oracledb`, and `snowflake-connector-python` are listed in
`requirements.txt` for full Postgres/Oracle/Snowflake support. If any of
these drivers is unavailable in your environment, the app still runs — the
corresponding connector raises a clear error only when you actually try to
use that database type.


## 4. Configuration

Copy `.env.example` to `.env` and set a master key:

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the output as DB_VALIDATOR_MASTER_KEY in .env
```

| Variable | Purpose | Default |
|---|---|---|
| `DB_VALIDATOR_MASTER_KEY` | Encrypts secrets at rest. **Never commit this.** | *(none — dev fallback generates an ephemeral key with a warning)* |
| `DB_VALIDATOR_APP_DB` | Path to the application SQLite metadata store | `data/app.db` |
| `DB_VALIDATOR_DATA_DIR` | Root for schemas/reports/uploads | `data` |
| `DB_VALIDATOR_LOG_LEVEL` | Logging verbosity | `INFO` |

Severity rules, the compatible-mode datatype mapping, and CI `fail_on`
thresholds are configurable in `config/comparison_rules.yaml`.

Axiom DataSource XML uploads use `config/axiom_mapping.yaml`. The single
top-level `attribute_mappings` list applies to XML and database comparisons,
mapping names such as `type`, `size`, or `allowNulls` to canonical attributes.
`compare: false` excludes that mapped attribute from comparison. The
top-level `value_mappings` list normalizes values such as `TEXT`, `STRING`,
`CHAR`, `NUMBER`, and `FLOAT`; datatype behavior is configured there rather
than hardcoded in the parser. These settings can be edited from the
**Compare Configuration** page. Missing mapped attributes are reported as
`WARNING` and do not fail comparisons by default. The file is read for each
XML upload and comparison, so mapping edits take effect without restarting.

The XML policy also controls `validate_object_types` and `validate_scope`.
`selected_objects` currently validates the configured object types (the default
is `DataSource:field`); adding other Axiom object types is a configuration
change, not a parser change. The policy is deliberately kept in YAML so a
future complete-document validator can use the same backend contract.


## 5. How to Run

```bash
uvicorn app.main:app --reload --port 8000
```

Then open:

The app creates `data/app.db` and the `data/schemas`, `data/reports`,
`data/uploads` folders automatically on first startup, and preserves all
configurations, filters, versions, comparisons, and reports across restarts.


## 6. Creating the SQLite Test Databases

```bash
python scripts/create_test_databases.py
```

Produces `test_data/source.db` and `test_data/destination.db` with
intentional, documented differences: added/removed tables, added/removed
columns, a datatype mismatch, a nullable mismatch, a default mismatch, a
composite primary key difference, a foreign key difference, and an index
difference — enough to exercise the complete workflow without any external
database. Add them as `sqlite` Database Configurations (UI: **Database
Configurations → Add Configuration**, or via the CLI/API) pointing at those
two files to try the full app.


## 7. Snowflake PAT Setup

1. In Snowflake, generate a **Programmatic Access Token** for the user that
   will run comparisons (`ALTER USER <user> ADD PROGRAMMATIC ACCESS TOKEN ...`,
   or via Snowsight: *Admin → Users & Roles → \<user\> → Programmatic access tokens*).
2. In DB Schema Validator, create a Database Configuration of type
   **Snowflake** with: `account`, `username`, the generated PAT (stored as
   `pat`, encrypted at rest), `warehouse`, `database`, `schema`, and
   optionally `role`.
3. Click **Test Configuration** to verify connectivity before extracting or
   comparing.

The PAT is never logged, never included in canonical schema JSON or
reports, never returned by `GET /api/database-configurations`, and is shown
masked (`********`) in the UI.


## 8. CLI Examples

```bash
# Extract a schema from a live configuration, applying a saved filter, and save it as a version
python -m dbvalidator extract \
  --database-config "QA Snowflake" \
  --schema CUSTOMER \
  --filter "AX Tables" \
  --save-version "QA Snowflake CUSTOMER v1"

# Compare two live database configurations, same filter on both sides
python -m dbvalidator compare \
  --source-config "QA Snowflake" \
  --destination-config "PROD Snowflake" \
  --filter "AX Tables" \
  --report report.html

# Compare two JSON schema files (e.g. in CI, no live DB access needed)
python -m dbvalidator compare \
  --source schema_v1.json \
  --destination schema_v2.json \
  --report report.html \
  --fail-on CRITICAL,HIGH
```

Exit codes: `0` = PASS, `1` = schema differences found (per `--fail-on`),
`2` = configuration/execution error. This makes the CLI directly usable as
a CI/CD gate (Jenkins, GitHub Actions, GitLab CI, Azure DevOps).


## 9. API Documentation

Full interactive documentation (request/response schemas, try-it-out) is
served at **`/docs`** once the app is running. Key endpoint groups:

```
GET/POST/PUT/DELETE  /api/database-configurations
POST                 /api/database-configurations/{id}/test
GET                  /api/database-configurations/{id}/databases|schemas|tables

GET/POST/PUT/DELETE  /api/filters
POST                 /api/filters/{id}/preview

POST                 /api/extraction/preview
POST                 /api/schema/extract
GET/POST             /api/schema/versions
GET/DELETE           /api/schema/versions/{id}
POST                 /api/schema/versions/import
POST                 /api/schema/upload         (ad-hoc JSON for one-off comparisons)

POST                 /api/compare
GET                  /api/compare, /api/compare/{id}

GET                  /api/reports, /api/reports/{id}, /api/reports/{id}/html
```

There is intentionally **no** `/api/connections` endpoint — connections are
always ephemeral, built at request time from a `DatabaseConfiguration`.


## 10. Test Execution

```bash
pip install -r requirements-dev.txt
python scripts/create_test_databases.py   # tests generate their own copies, but useful for manual runs too
pytest                                     # runs unit + integration + e2e (51 tests)
pytest tests/unit                          # filter engine, normalization, canonical schema, comparison engine
pytest tests/integration                   # SQLite extraction, persistence-across-restart, report generation
pytest tests/e2e                           # full acceptance-criteria workflow
pytest --cov=app --cov-report=term-missing # with coverage
```

Every test uses an isolated temporary `app.db` and `data/` directory (see
`tests/conftest.py`), so running the suite never touches a real running
instance's data. Snowflake/Oracle/PostgreSQL connector code is exercised via
unit-level construction and (where installed) driver import checks; live
integration tests against real Snowflake/Oracle/Postgres instances are
environment-driven (via connection env vars) and automatically skip when
credentials aren't present — no credentials are ever hard-coded.
