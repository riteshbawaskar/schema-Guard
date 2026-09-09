let mappingConfig = null;

function mappingRow(item = {}, containerId = "mappingRows") {
  const row = document.createElement("tr");
  row.innerHTML = `<td><input class="form-check-input map-enabled" type="checkbox" ${item.enabled !== false ? "checked" : ""}></td>
    <td><input class="form-control map-source" value="${item.source || ""}"></td>
    <td><input class="form-control map-target" value="${item.target || ""}"></td>
    <td><input class="form-check-input map-compare" type="checkbox" ${item.compare !== false ? "checked" : ""}></td>
    <td><button class="btn btn-outline-danger btn-sm remove-map" title="Remove mapping"><i class="bi bi-trash"></i></button></td>`;
  row.querySelector(".remove-map").onclick = () => row.remove();
  document.getElementById(containerId).appendChild(row);
}

function tableMappingRow(item = {}) {
  const row = document.createElement("tr");
  row.innerHTML = `<td><input class="form-check-input table-map-enabled" type="checkbox" ${item.enabled !== false ? "checked" : ""}></td>
    <td><input class="form-control table-map-source" value="${item.source || ""}"></td>
    <td><input class="form-control table-map-destination" value="${item.destination || ""}"></td>
    <td><button class="btn btn-outline-danger btn-sm remove-table-map" title="Remove table mapping"><i class="bi bi-trash"></i></button></td>`;
  row.querySelector(".remove-table-map").onclick = () => row.remove();
  document.getElementById("tableMappingRows").appendChild(row);
}

function renderMapping(config) {
  const xml = config.xml || {};
  mappingConfig = config;
  const tables = config.table_matching || {};
  document.getElementById("tableMatchingEnabled").checked = tables.enabled !== false;
  document.getElementById("ignoreTableNames").checked = tables.ignore_names === true;
  document.getElementById("tableMappingRows").innerHTML = "";
  (tables.mappings || []).forEach(tableMappingRow);
  document.getElementById("enabled").checked = xml.enabled !== false;
  document.getElementById("objectType").value = xml.object_type || "DataSource";
  document.getElementById("scope").value = xml.validate_scope || "selected_objects";
  document.getElementById("objectTypes").value = (xml.validate_object_types || []).join(", ");
  document.getElementById("ignoredAttributes").value = (xml.ignored_attributes || []).join(", ");
  document.getElementById("missingSeverity").value = (xml.missing_attribute || {}).severity || "WARNING";
  document.getElementById("missingFail").checked = Boolean((xml.missing_attribute || {}).fail);
  document.getElementById("mappingRows").innerHTML = "";
  (config.attribute_mappings || []).forEach(item => mappingRow(item, "mappingRows"));
  document.getElementById("xmlMappingRows").innerHTML = "";
  (xml.attribute_mappings || []).forEach(item => mappingRow(item, "xmlMappingRows"));
}

function collectMapping() {
  const tableMatching = { ...(mappingConfig.table_matching || {}) };
  tableMatching.enabled = document.getElementById("tableMatchingEnabled").checked;
  tableMatching.ignore_names = document.getElementById("ignoreTableNames").checked;
  tableMatching.mappings = [...document.querySelectorAll("#tableMappingRows tr")].map(row => ({
    source: row.querySelector(".table-map-source").value.trim(),
    destination: row.querySelector(".table-map-destination").value.trim(),
    enabled: row.querySelector(".table-map-enabled").checked,
  })).filter(item => item.source && item.destination);
  const xml = { ...(mappingConfig.xml || {}) };
  xml.enabled = document.getElementById("enabled").checked;
  xml.object_type = document.getElementById("objectType").value.trim();
  xml.validate_scope = document.getElementById("scope").value;
  xml.validate_object_types = document.getElementById("objectTypes").value.split(",").map(v => v.trim()).filter(Boolean);
  xml.ignored_attributes = document.getElementById("ignoredAttributes").value.split(",").map(v => v.trim()).filter(Boolean);
  xml.missing_attribute = { severity: document.getElementById("missingSeverity").value, fail: document.getElementById("missingFail").checked };
  const readMappings = selector => [...document.querySelectorAll(`${selector} tr`)].map(row => ({
    source: row.querySelector(".map-source").value.trim(), target: row.querySelector(".map-target").value.trim(),
    enabled: row.querySelector(".map-enabled").checked, compare: row.querySelector(".map-compare").checked,
  })).filter(item => item.source && item.target);
  xml.attribute_mappings = readMappings("#xmlMappingRows");
  return { ...mappingConfig, table_matching: tableMatching, attribute_mappings: readMappings("#mappingRows"), xml };
}

async function loadMapping() {
  try { renderMapping(await apiRequest("/api/compare-config")); }
  catch (error) { document.getElementById("mappingStatus").innerHTML = `<div class="alert alert-danger">${error.message}</div>`; }
}

document.getElementById("addMapping").onclick = () => mappingRow();
document.getElementById("addTableMapping").onclick = () => tableMappingRow();
document.getElementById("addXmlMapping").onclick = () => mappingRow({}, "xmlMappingRows");
document.getElementById("saveMapping").onclick = async () => {
  try {
    renderMapping(await apiRequest("/api/compare-config", { method: "PUT", body: collectMapping() }));
    showToast("XML mapping saved", "success");
  } catch (error) { showToast(error.message, "danger"); }
};
loadMapping();
