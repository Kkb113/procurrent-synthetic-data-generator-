const form = document.getElementById("pipeline-form");
const runButton = document.getElementById("run-button");
const statusMessage = document.getElementById("status-message");
const resultsPanel = document.getElementById("results-panel");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  runButton.disabled = true;
  statusMessage.textContent = "Generating MES lifecycle data. This can take a few minutes for analytics-scale runs.";
  statusMessage.className = "muted";
  resultsPanel.classList.add("hidden");

  try {
    const formData = new FormData(form);
    for (const name of ["use_azure_openai", "build_prompt", "load_sql"]) {
      formData.set(name, form.elements[name].checked ? "true" : "false");
    }

    const endpoint = form.dataset.endpoint || form.action || "/api/pipeline/run-mes";
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "MES lifecycle request failed.");
    }
    renderResults(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    runButton.disabled = false;
  }
});

function renderResults(payload) {
  statusMessage.textContent = payload.message || "MES lifecycle generation completed.";
  statusMessage.className = statusClass(payload.status);

  const moduleRows = payload.per_module_row_counts || {};
  document.getElementById("result-status").textContent = payload.status || "-";
  document.getElementById("result-rows").textContent = formatNumber(payload.total_rows ?? payload.total_rows_generated);
  document.getElementById("result-procurement-rows").textContent = formatNumber(moduleRows.procurement);
  document.getElementById("result-production-rows").textContent = formatNumber(moduleRows.production);
  document.getElementById("result-sales-rows").textContent = formatNumber(moduleRows.sales);
  document.getElementById("result-validation").textContent = payload.validation_status || combinedModuleQuality(payload.module_results) || "-";
  document.getElementById("result-sql").textContent = payload.sql_status || payload.sql_load_status || "not_run";
  document.getElementById("result-issues").textContent = `${payload.warning_count ?? 0} / ${payload.error_count ?? 0}`;

  renderArtifactPaths(payload.artifact_paths || {});
  renderDownloads(payload.downloads || {});
  renderList("warnings-list", payload.warnings || []);
  renderList("errors-list", payload.errors || []);

  resultsPanel.classList.remove("hidden");
}

function renderArtifactPaths(artifacts) {
  const container = document.getElementById("artifact-paths");
  container.innerHTML = "";
  const entries = Object.entries(artifacts);
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Artifacts will appear here after the run completes.";
    container.appendChild(empty);
    return;
  }
  for (const [key, path] of entries) {
    const item = document.createElement("div");
    item.innerHTML = `<span>${escapeHtml(labelFor(key))}</span><strong>${escapeHtml(path)}</strong>`;
    container.appendChild(item);
  }
}

function renderDownloads(downloads) {
  const container = document.getElementById("download-links");
  container.innerHTML = "";
  const entries = Object.entries(downloads);
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Download links are available when artifacts are generated.";
    container.appendChild(empty);
    return;
  }
  for (const [key, href] of entries) {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = labelFor(key);
    link.target = "_blank";
    container.appendChild(link);
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

function combinedModuleQuality(moduleResults) {
  if (!moduleResults) return "";
  return Object.entries(moduleResults)
    .map(([moduleId, result]) => `${moduleId}: ${result.data_quality_status || "not_run"}`)
    .join("; ");
}

function labelFor(key) {
  const labels = {
    final_data: "Final data",
    final_data_zip: "Final data ZIP",
    row_budget_report: "Row budget report",
    row_count_audit: "Row-count audit",
    llm_planning_report: "LLM planning report",
    generated_industry_profile: "Generated industry profile",
    performance_profile_phase4: "Performance profile",
  };
  return labels[key] || key.replaceAll("_", " ");
}

function formatNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : String(value);
}

function showError(message) {
  statusMessage.textContent = message;
  statusMessage.className = "status-failed";
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
