# SchemaGuard Project Instructions

## Purpose

SchemaGuard extracts, stores, compares, and reports database schemas from SQLite, PostgreSQL, Oracle, Snowflake, and configurable XML sources. The same comparison engine is used by the REST API, web UI, and CLI.

## Project Structure

- `app/connectors/`: database-specific extraction adapters.
- `app/schema/`: canonical schema models, normalization, and XML parsing.
- `app/comparison/`: comparison engine, diff models, and severity rules.
- `app/services/`: orchestration and editable configuration services.
- `app/api/`: FastAPI endpoints.
- `app/templates/`: server-rendered UI pages.
- `app/static/`: browser JavaScript and CSS.
- `app/reports/`: HTML report renderer and template.
- `app/storage/`: schema and report file storage.
- `config/`: runtime-editable YAML configuration.
- `tests/`: unit, integration, and end-to-end tests.

## Development Commands

Use the project virtual environment on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run the application:

```powershell
uvicorn app.main:app --reload --port 8000
```

Run all tests:

```powershell
pytest -q
```

Run focused tests:

```powershell
pytest -q tests/unit
pytest -q tests/integration
```

## Configuration Ownership

- `config/comparison_rules.yaml` owns severity rules, fail thresholds, and datatype normalization rules.
- `config/axiom_mapping.yaml` owns editable comparison policy:
  - table-name mappings and table-name ignoring
  - shared attribute mappings
  - value mappings
  - ignored attributes
  - missing-attribute warning behavior
  - XML enablement, root object type, validation scope, and object types
- The Compare Configuration UI and `/api/compare-config` are the supported editing surfaces.
- Configuration must be loaded at runtime for uploads and comparisons. Do not require a restart for YAML changes.
- Preserve backward compatibility when reading older configuration shapes, but write the current shape.

## Generic Schema Rules

1. Do not hardcode business column names, XML property names, datatype aliases, table names, or vendor-specific attributes in Python, JavaScript, templates, or tests.
2. Do not add examples such as `account_id`, `allowNulls`, `Native_Datatype`, `TEXT`, or `VARCHAR` as code logic. They belong in editable YAML or test fixtures only.
3. Attribute mapping must always be configuration-driven. A mapping may define source name, target name, enabled state, and compare state.
4. `compare: false` must exclude the mapped attribute from comparison diffs and report detail rows.
5. Value mappings must be selected by configured attribute name and applied before comparison. Attribute-name matching may be case-insensitive, but do not create implicit aliases.
6. If users need both raw and normalized fields mapped, they must configure both mappings explicitly.
7. Ignore-table-name behavior and table-name mappings must be configuration-driven.
8. Missing mapped attributes should use the configured warning policy and must not fail by default.
9. Do not derive fields. Never parse a datatype string to invent `length`, `precision`, `scale`, nullable state, identity, default, or any other attribute.
10. Extraction output must contain only attributes explicitly supplied by the source connector or XML mapping. Do not serialize model defaults as if they came from the database.
11. Arbitrary XML properties should be retained in configured source-property storage. ValueType-only empty XML containers may be ignored when configured or when they contain no explicit value.
12. XML object selection, validation scope, root type, and identity mappings must be configurable. Do not assume `DataSource:field` is the only supported object type in code.

## Canonical Model Boundary

The canonical model provides the smallest cross-source envelope needed by the existing engine to identify and compare objects. Any required envelope fields must remain source-neutral. Source-specific or optional attributes belong in source-property data and must not be fabricated.

When adding a new source format:

1. Parse source data without inventing missing values.
2. Use the Compare Configuration policy to select and map source attributes.
3. Preserve configured source attributes for field-level reporting.
4. Populate only values explicitly available from the source.
5. Add focused parser and comparison tests using generic fixture names.

## Comparison Rules

- Compare dynamically available attributes, not a fixed list.
- Apply ignored attributes and `compare: false` before producing `FieldDiff` records.
- Apply configured value mappings before comparing values.
- Keep missing-attribute warnings separate from failing severities.
- Use explicit table mappings first, exact names second, and name-agnostic pairing only when configured.
- Do not use report presentation code to change comparison semantics.

## Reporting Rules

- Reports must show only attributes available in the compared source data.
- Database null values should display as `null`; absent source attributes should display as `Missing`.
- XML-to-XML reports show configured XML source attributes without synthetic prefixes.
- XML-to-database reports show only the configured canonical attributes.
- Matches are green, mismatches are red, and warnings are orange.
- Preserve safe JSON embedding and escape script-closing sequences.

## UI Rules

- All editable comparison behavior belongs on the Compare Configuration page.
- Do not add a second hidden configuration path for XML.
- New mapping rows must support enable/disable, compare enable/disable, edit, remove, and save.
- Buttons that modify mapping rows must be explicit non-submit buttons.
- Keep generic mappings, value mappings, table mappings, and XML validation settings visually distinct.

## Testing Rules

Every behavior change should include a focused test for:

- configuration load/save and validation
- generic source attribute mapping
- value mapping
- `compare: false`
- missing-attribute warning behavior
- table-name mapping or ignoring
- extraction output containing only supplied attributes
- report visibility and severity colors

Run focused tests before the full suite. Do not change user configuration merely to make a test pass. If a test conflicts with an intentional active configuration, document that conflict and add a policy-specific test.

## Editing Rules

- Keep changes minimal and localized.
- Preserve user edits to YAML and unrelated files.
- Use `apply_patch` for source edits.
- Do not commit or create branches unless explicitly requested.
- Do not add hardcoded schema examples to production code.
- Add comments only for non-obvious behavior, especially configuration fallback, security, and serialization boundaries.
