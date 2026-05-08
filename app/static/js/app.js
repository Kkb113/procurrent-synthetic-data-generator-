const form = document.getElementById("pipeline-form");
const runButton = document.getElementById("run-button");
const statusMessage = document.getElementById("status-message");
const stageTableBody = document.querySelector("#stage-table tbody");
const resultsPanel = document.getElementById("results-panel");
const downloadsPanel = document.getElementById("downloads-panel");
const modelVersionSelect = document.getElementById("model-version");
const v2ModelHelp = document.getElementById("v2-model-help");

if (modelVersionSelect && v2ModelHelp) {
  modelVersionSelect.addEventListener("change", updateModelHelp);
  updateModelHelp();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  runButton.disabled = true;
  statusMessage.textContent = "Pipeline is running...";
  stageTableBody.innerHTML = "";
  resultsPanel.classList.add("hidden");
  downloadsPanel.classList.add("hidden");

  try {
    const formData = new FormData(form);
    for (const name of ["use_azure_openai", "build_prompt", "load_sql"]) {
      formData.set(name, form.elements[name].checked ? "true" : "false");
    }

    const response = await fetch("/api/pipeline/run", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Pipeline request failed.");
    }
    renderResults(payload);
  } catch (error) {
    statusMessage.textContent = error.message;
    statusMessage.className = "status-failed";
  } finally {
    runButton.disabled = false;
  }
});

function renderResults(payload) {
  statusMessage.textContent = payload.message || "Pipeline completed.";
  statusMessage.className = statusClass(payload.status);
  renderStages(payload.stage_summary || []);

  document.getElementById("result-status").textContent = payload.status || "-";
  document.getElementById("result-model-version").textContent = payload.model_version || "v1";
  document.getElementById("result-tables").textContent = payload.tables_generated ?? "-";
  document.getElementById("result-rows").textContent = payload.total_rows_generated ?? "-";
  document.getElementById("result-quality").textContent = payload.data_quality_status || "-";
  document.getElementById("result-sql").textContent = payload.sql_load_status || "-";
  renderList("warnings-list", payload.warnings || []);
  renderList("errors-list", payload.errors || []);
  renderDownloads(payload.downloads || {});

  resultsPanel.classList.remove("hidden");
  downloadsPanel.classList.remove("hidden");
}

function updateModelHelp() {
  v2ModelHelp.hidden = modelVersionSelect.value !== "v2";
}

function renderStages(stages) {
  stageTableBody.innerHTML = "";
  for (const stage of stages) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(stage.stage_name || "")}</td>
      <td class="${statusClass(stage.status)}">${escapeHtml(stage.status || "")}</td>
      <td>${stage.errors_count ?? 0}</td>
      <td>${stage.warnings_count ?? 0}</td>
    `;
    stageTableBody.appendChild(row);
  }
}

function renderList(elementId, items) {
  const list = document.getElementById(elementId);
  list.innerHTML = "";
  if (!items.length) {
    const item = document.createElement("li");
    item.textContent = "None";
    list.appendChild(item);
    return;
  }
  for (const value of items) {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  }
}

function renderDownloads(downloads) {
  const container = document.getElementById("download-links");
  container.innerHTML = "";
  const labels = {
    audit_md: "Audit Markdown",
    audit_json: "Audit JSON",
    pipeline_json: "Pipeline JSON",
    final_data_zip: "Final Data ZIP",
    generated_plan: "Generated Plan JSON",
    raw_llm_response: "Raw LLM Response",
  };
  for (const [key, href] of Object.entries(downloads)) {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = labels[key] || key;
    link.target = "_blank";
    container.appendChild(link);
  }
}

function statusClass(status) {
  if (!status) return "";
  if (status.includes("failed")) return "status-failed";
  if (status.includes("warning")) return "status-warning";
  if (status.includes("passed")) return "status-passed";
  return "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
