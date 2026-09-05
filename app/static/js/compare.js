// Compare page logic. Renders identical selector UI for "source" and
// "destination" sides, resolves user selections into a /api/compare payload,
// and renders the JSON comparison result returned by the shared comparison
// engine (the same engine used by the CLI).

let CONFIGS = [];
let FILTERS = [];
let VERSIONS = [];

async function initComparePage() {
  CONFIGS = await apiRequest("/api/database-configurations");
  FILTERS = await apiRequest("/api/filters");
  VERSIONS = await apiRequest("/api/schema/versions");

  document.getElementById("sourceSide").innerHTML = renderSide("source");
  document.getElementById("destinationSide").innerHTML = renderSide("destination");
  wireSide("source");
  wireSide("destination");

  const params = new URLSearchParams(window.location.search);
  if (params.get("source_type")) {
    document.getElementById("source_type").value = params.get("source_type");
    onTypeChange("source");
  }
  if (params.get("source_reference")) {
    onTypeChange("source").then(() => {
      const el = document.getElementById("source_reference_version");
      if (el) el.value = params.get("source_reference");
    });
  }

  const destFilterSel = document.getElementById("destinationFilterId");
  destFilterSel.innerHTML = `<option value="">(no filter)</option>` + FILTERS.map(f => `<option value="${f.id}">${f.name}</option>`).join("");
}

function filterOptions(selected) {
  return `<option value="">(no filter - all tables)</option>` +
    FILTERS.map(f => `<option value="${f.id}" ${f.id===selected?'selected':''}>${f.name}</option>`).join("");
}

function renderSide(prefix) {
  return `
    <div class="mb-3">
      <label class="form-label">Source Kind</label>
      <select class="form-select" id="${prefix}_type" onchange="onTypeChange('${prefix}')">
        <option value="live">Live Database</option>
        <option value="schema_version">Saved Schema Version</option>
        <option value="uploaded_json">Upload JSON</option>
      </select>
    </div>
    <div id="${prefix}_fields"></div>
    ${prefix === "source" ? `
    <div class="mb-3" id="${prefix}_filterWrap">
      <label class="form-label">Filter</label>
      <select class="form-select" id="${prefix}FilterId">${filterOptions()}</select>
    </div>` : ""}
  `;
}

function wireSide(prefix) {
  onTypeChange(prefix);
}

async function onTypeChange(prefix) {
  const type = document.getElementById(`${prefix}_type`).value;
  const container = document.getElementById(`${prefix}_fields`);
  if (type === "live") {
    container.innerHTML = `
      <div class="mb-2">
        <label class="form-label">Database Configuration</label>
        <select class="form-select" id="${prefix}_config" onchange="onLiveConfigChange('${prefix}')">
          <option value="">Select...</option>
          ${CONFIGS.filter(c => c.enabled).map(c => `<option value="${c.id}">${c.name} (${c.database_type})</option>`).join("")}
        </select>
      </div>
      <div class="mb-2"><label class="form-label">Database</label><select class="form-select" id="${prefix}_database" onchange="onDatabaseChange('${prefix}')"></select></div>
      <div class="mb-2"><label class="form-label">Schema</label><select class="form-select" id="${prefix}_schema"></select></div>
    `;
  } else if (type === "schema_version") {
    container.innerHTML = `
      <div class="mb-2">
        <label class="form-label">Schema Version</label>
        <select class="form-select" id="${prefix}_reference_version">
          <option value="">Select...</option>
          ${VERSIONS.map(v => `<option value="${v.id}">${v.name} (v${v.version}, ${v.table_count} tables)</option>`).join("")}
        </select>
      </div>
    `;
  } else if (type === "uploaded_json") {
    container.innerHTML = `
      <div class="mb-2">
        <label class="form-label">Upload canonical schema JSON</label>
        <input class="form-control" type="file" id="${prefix}_upload_file" accept=".json" onchange="onUpload('${prefix}')">
        <input type="hidden" id="${prefix}_uploaded_path">
        <div class="form-text" id="${prefix}_upload_status"></div>
      </div>
    `;
  }
}

async function onUpload(prefix) {
  const fileInput = document.getElementById(`${prefix}_upload_file`);
  const statusEl = document.getElementById(`${prefix}_upload_status`);
  if (!fileInput.files.length) return;
  statusEl.textContent = "Uploading...";
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const resp = await fetch("/api/schema/upload", { method: "POST", body: formData });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Upload failed");
    document.getElementById(`${prefix}_uploaded_path`).value = data.path;
    statusEl.textContent = "Uploaded successfully.";
  } catch (e) {
    statusEl.textContent = "Error: " + e.message;
  }
}

async function onLiveConfigChange(prefix) {
  const configId = document.getElementById(`${prefix}_config`).value;
  const dbSel = document.getElementById(`${prefix}_database`);
  const schemaSel = document.getElementById(`${prefix}_schema`);
  dbSel.innerHTML = ""; schemaSel.innerHTML = "";
  if (!configId) return;
  try {
    const { databases } = await apiRequest(`/api/database-configurations/${configId}/databases`);
    dbSel.innerHTML = databases.map(d => `<option value="${d}">${d}</option>`).join("");
    await onDatabaseChange(prefix);
  } catch (e) { showToast(e.message, "danger"); }
}

async function onDatabaseChange(prefix) {
  const configId = document.getElementById(`${prefix}_config`).value;
  const database = document.getElementById(`${prefix}_database`).value;
  const schemaSel = document.getElementById(`${prefix}_schema`);
  schemaSel.innerHTML = "";
  if (!configId || !database) return;
  try {
    const { schemas } = await apiRequest(
      `/api/database-configurations/${configId}/schemas?database=${encodeURIComponent(database)}`
    );
    schemaSel.innerHTML = schemas.map(s => `<option value="${s}">${s}</option>`).join("");
  } catch (e) { showToast(e.message, "danger"); }
}

function toggleSameFilter() {
  const same = document.getElementById("sameFilter").checked;
  document.getElementById("destFilterWrap").style.display = same ? "none" : "block";
}

function getSidePayload(prefix) {
  const type = document.getElementById(`${prefix}_type`).value;
  if (type === "live") {
    return {
      type: "live",
      reference: document.getElementById(`${prefix}_config`).value,
      database: document.getElementById(`${prefix}_database`).value,
      schema_name: document.getElementById(`${prefix}_schema`).value,
    };
  } else if (type === "schema_version") {
    return { type: "schema_version", reference: document.getElementById(`${prefix}_reference_version`).value };
  } else {
    return { type: "uploaded_json", reference: document.getElementById(`${prefix}_uploaded_path`).value };
  }
}

async function runComparison() {
  const resultDiv = document.getElementById("compareResult");
  const src = getSidePayload("source");
  const dst = getSidePayload("destination");
  if (!src.reference || !dst.reference) { showToast("Please complete both source and destination selections", "warning"); return; }

  const sameFilter = document.getElementById("sameFilter").checked;
  const sourceFilterId = document.getElementById("sourceFilterId").value || null;
  const destinationFilterId = sameFilter ? sourceFilterId : (document.getElementById("destinationFilterId").value || null);

  document.getElementById("filterWarning").style.display = (!sameFilter && sourceFilterId !== destinationFilterId) ? "block" : "none";

  resultDiv.innerHTML = `<div class="section-card text-center text-muted py-4"><span class="spinner-border spinner-border-sm"></span> Running comparison...</div>`;

  const payload = {
    source_type: src.type, source_reference: src.reference,
    destination_type: dst.type, destination_reference: dst.reference,
    source_filter_id: sourceFilterId, destination_filter_id: destinationFilterId,
    source_database: src.database || null, source_schema: src.schema_name || null,
    destination_database: dst.database || null, destination_schema: dst.schema_name || null,
    normalization_mode: document.getElementById("normalizationMode").value,
  };

  try {
    const data = await apiRequest("/api/compare", { method: "POST", body: payload });
    resultDiv.innerHTML = `<div class="section-card"><div class="alert alert-warning mb-0">Comparison job created with status ${statusBadge(data.comparison.status)}. Track progress on the Reports page.</div></div>`;
    window.location.href = "/reports";
  } catch (e) {
    resultDiv.innerHTML = `<div class="section-card"><div class="alert alert-danger mb-0">${e.message}</div></div>`;
  }
}

function renderComparisonSummary(data) {
  const c = data.comparison;
  const r = data.result;
  const resultDiv = document.getElementById("compareResult");
  resultDiv.innerHTML = `
    <div class="section-card">
      <div class="d-flex justify-content-between align-items-center mb-1">
        <h5 class="mb-0">Comparison Result ${statusBadge(c.status)}</h5>
        <a class="btn btn-primary" href="/reports/view/${c.id}" target="_blank"><i class="bi bi-file-earmark-text"></i> Open Full Report</a>
      </div>
      <p class="text-muted small mb-3">${c.source_label || c.source_reference} &rarr; ${c.destination_label || c.destination_reference}</p>
      <div class="row g-2 mb-2">
        <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">${r.summary.tables_compared}</div><div class="stat-lbl">Tables</div></div></div>
        <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">${r.summary.tables_added}</div><div class="stat-lbl">Added</div></div></div>
        <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">${r.summary.tables_removed}</div><div class="stat-lbl">Removed</div></div></div>
        <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">${r.summary.tables_modified}</div><div class="stat-lbl">Modified</div></div></div>
        <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">${r.summary.difference_count}</div><div class="stat-lbl">Differences</div></div></div>
        <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num" style="color:#C62828">${r.summary.critical_count}</div><div class="stat-lbl">Critical</div></div></div>
      </div>
      <p class="text-muted small mb-0">Full drill-down (search, per-column diffs, severity filters) is available in the report.</p>
    </div>`;
}

initComparePage();
