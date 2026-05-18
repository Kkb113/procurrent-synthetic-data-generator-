const form = document.getElementById("pipeline-form");
const runButton = document.getElementById("run-button");
const statusMessage = document.getElementById("status-message");
const stageTableBody = document.querySelector("#stage-table tbody");
const moduleTableBody = document.querySelector("#module-table tbody");
const resultsPanel = document.getElementById("results-panel");
const downloadsPanel = document.getElementById("downloads-panel");
const modelVersionSelect = document.getElementById("model-version");
const v2ModelHelp = document.getElementById("v2-model-help");
const procurementCheckbox = form.elements["module_procurement"];
const productionCheckbox = form.elements["module_production"];
const salesCheckbox = form.elements["module_sales"];
const fallbackCheckbox = form.elements["allow_demo_fallback"];
const azureOpenAICheckbox = form.elements["use_azure_openai"];
const azureOpenAIHint = document.getElementById("azure-openai-hint");
const moduleHelper = document.getElementById("module-helper");
const modulesField = document.getElementById("modules-field");

if (modelVersionSelect && v2ModelHelp) {
  modelVersionSelect.addEventListener("change", updateModelHelp);
  updateModelHelp();
}

productionCheckbox.addEventListener("change", () => {
  if (salesCheckbox.checked && !productionCheckbox.checked) {
    productionCheckbox.checked = true;
  }
  if (productionCheckbox.checked) {
    procurementCheckbox.checked = true;
  }
  updateModuleHelper();
});
salesCheckbox.addEventListener("change", () => {
  if (salesCheckbox.checked) {
    productionCheckbox.checked = true;
    procurementCheckbox.checked = true;
  }
  updateModuleHelper();
});
procurementCheckbox.addEventListener("change", () => {
  if ((productionCheckbox.checked || salesCheckbox.checked) && !procurementCheckbox.checked) {
    procurementCheckbox.checked = true;
  }
  updateModuleHelper();
});
fallbackCheckbox.addEventListener("change", updateModuleHelper);
if (azureOpenAICheckbox) {
  azureOpenAICheckbox.checked = false;
  azureOpenAICheckbox.addEventListener("change", updateAzureOpenAIHint);
  updateAzureOpenAIHint();
}
updateModuleHelper();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const modules = selectedModules();
  if (!modules.length) {
    showError("Select at least one module.");
    return;
  }
  if (modules.includes("sales") && modules.join(",") !== "procurement,production,sales") {
    showError("Sales requires Production finished goods and Procurement/Production lineage. Procurement and Production will run first.");
    productionCheckbox.checked = true;
    procurementCheckbox.checked = true;
    updateModuleHelper();
    return;
  }
  if (modules.includes("production") && !modules.includes("procurement") && !fallbackCheckbox.checked && !form.elements["upstream_data"].value.trim()) {
    showError("Production requires Procurement upstream data. Select Procurement + Production or enable demo fallback.");
    return;
  }

  runButton.disabled = true;
  statusMessage.textContent = "Pipeline is running...";
  statusMessage.className = "";
  stageTableBody.innerHTML = "";
  moduleTableBody.innerHTML = "";
  resultsPanel.classList.add("hidden");
  downloadsPanel.classList.add("hidden");

  try {
    const formData = new FormData(form);
    formData.set("modules", modules.join(","));
    for (const name of ["use_azure_openai", "build_prompt", "load_sql", "allow_demo_fallback"]) {
      formData.set(name, form.elements[name].checked ? "true" : "false");
    }

    const endpoint = form.dataset.endpoint || form.action || "/api/pipeline/run-generic";
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Pipeline request failed.");
    }
    renderResults(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    runButton.disabled = false;
  }
});

function selectedModules() {
  const modules = [];
  if (procurementCheckbox.checked) modules.push("procurement");
  if (productionCheckbox.checked) modules.push("production");
  if (salesCheckbox.checked) modules.push("sales");
  return modules;
}

function updateModuleHelper() {
  if (salesCheckbox.checked) {
    productionCheckbox.checked = true;
    procurementCheckbox.checked = true;
  }
  if (productionCheckbox.checked) {
    procurementCheckbox.checked = true;
  }
  const modules = selectedModules();
  if (modulesField) {
    modulesField.value = modules.join(",");
  }
  if (modules.includes("sales")) {
    moduleHelper.textContent = "Sales requires Production finished goods and Procurement/Production lineage. Procurement and Production will run first.";
  } else if (modules.includes("production") && modules.includes("procurement")) {
    moduleHelper.textContent = "Production consumes Procurement output. Procurement will run first.";
  } else if (modules.includes("production") && fallbackCheckbox.checked) {
    moduleHelper.textContent = "Production will use explicit demo fallback upstream data.";
  } else if (modules.includes("production")) {
    moduleHelper.textContent = "Production requires Procurement upstream data. Select Procurement + Production or enable demo fallback.";
  } else {
    moduleHelper.textContent = "Procurement-only runs generate the 25-table Procurement v2 flow.";
  }
}

function updateAzureOpenAIHint() {
  if (!azureOpenAIHint || !azureOpenAICheckbox) return;
  if (azureOpenAICheckbox.checked) {
    azureOpenAIHint.textContent = "Azure OpenAI planning is enabled and requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT. Uncheck to use the bundled deterministic plan.";
  } else {
    azureOpenAIHint.textContent = "Leave unchecked for local deterministic runs. Check only when Azure OpenAI environment variables are configured.";
  }
}

function renderResults(payload) {
  statusMessage.textContent = payload.message || "Pipeline completed.";
  statusMessage.className = statusClass(payload.status);
  renderStages(payload.stage_summary || []);
  renderModules(payload);

  document.getElementById("result-status").textContent = payload.status || "-";
  document.getElementById("result-model-version").textContent = payload.model_version || "generic";
  document.getElementById("result-modules").textContent = (payload.module_ids || ["procurement"]).join(", ");
  document.getElementById("result-tables").textContent = payload.tables_generated ?? totalModuleTables(payload.module_results) ?? "-";
  document.getElementById("result-rows").textContent = payload.total_rows_generated ?? "-";
  document.getElementById("result-quality").textContent = payload.data_quality_status || combinedModuleQuality(payload.module_results) || "-";
  document.getElementById("result-sql").textContent = payload.sql_load_status || "not_run";
  document.getElementById("result-execution-order").textContent = (payload.module_ids || ["procurement"]).join(" -> ");
  document.getElementById("result-adjusted-fgi").textContent = adjustedInventoryText(payload.adjusted_finished_goods_inventory);
  renderList("warnings-list", payload.warnings || []);
  renderList("errors-list", payload.errors || []);
  renderDownloads(payload.downloads || {});

  resultsPanel.classList.remove("hidden");
  downloadsPanel.classList.toggle("hidden", Object.keys(payload.downloads || {}).length === 0);
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

function renderModules(payload) {
  moduleTableBody.innerHTML = "";
  const moduleResults = payload.module_results || {
    procurement: {
      status: payload.status,
      tables_generated: payload.tables_generated,
      data_quality_status: payload.data_quality_status,
      output_folder: payload.output_folder,
    },
  };
  for (const [moduleId, result] of Object.entries(moduleResults)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(moduleId)}</td>
      <td class="${statusClass(result.status)}">${escapeHtml(result.status || "")}</td>
      <td>${result.tables_generated ?? "-"}</td>
      <td>${escapeHtml(result.data_quality_status || "-")}</td>
      <td>${escapeHtml(result.output_folder || "-")}</td>
    `;
    moduleTableBody.appendChild(row);
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

function adjustedInventoryText(adjustedInventory) {
  if (!adjustedInventory || !adjustedInventory.available) return "not available";
  return adjustedInventory.path ? `available: ${adjustedInventory.path}` : "available";
}

function totalModuleTables(moduleResults) {
  if (!moduleResults) return null;
  return Object.values(moduleResults).reduce((total, result) => total + Number(result.tables_generated || 0), 0);
}

function combinedModuleQuality(moduleResults) {
  if (!moduleResults) return "";
  return Object.entries(moduleResults)
    .map(([moduleId, result]) => `${moduleId}: ${result.data_quality_status || "not_run"}`)
    .join("; ");
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
