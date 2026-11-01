const endpoints = ["health", "qa", "supervisor", "agents"];

function createMonitorPanels() {
  let container = document.getElementById("live-monitoring");
  if (!container) {
    container = document.createElement("section");
    container.id = "live-monitoring";
    container.style.cssText = "padding:20px;max-width:1200px;margin:auto";
    const heading = document.createElement("h2");
    heading.textContent = "Supervisor API Monitoring";
    container.appendChild(heading);
    document.body.appendChild(container);
  }

  for (const endpoint of endpoints) {
    if (document.getElementById("monitor-" + endpoint)) continue;
    const panel = document.createElement("div");
    panel.style.cssText = "padding:16px;margin:12px 0;border:1px solid #888;border-radius:12px";
    const title = document.createElement("h3");
    title.textContent = endpoint.toUpperCase();
    const output = document.createElement("pre");
    output.id = "monitor-" + endpoint;
    output.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere";
    output.textContent = "Waiting for monitoring data...";
    panel.append(title, output);
    container.appendChild(panel);
  }
}


function updateSummaryCard(endpoint, data) {
  const names = {
    supervisor: "Supervisor",
    qa: "Independent QA",
    agents: "Builder Agent",
    health: "Financial Engine"
  };

  const card = [...document.querySelectorAll(".grid .card")]
    .find(c => c.querySelector("h2")?.textContent.trim() === names[endpoint]);

  if (!card) return;

  const badge = card.querySelector(".status");
  if (!badge) return;

  let status = "UNVERIFIED";
  let details = "";

  if (endpoint === "supervisor") {
    status = data.monitoring_mode || "UNVERIFIED";
    details = "Production release: " + (data.production_release || "UNKNOWN");
  }

  if (endpoint === "qa") {
    status = data.qa_status || "UNVERIFIED";
    details = "Source: " + (data.data_source || "UNKNOWN")
      + " | Issues: " + (data.issues || []).map(i => i.id).join(", ");
  }

  if (endpoint === "agents") {
    status = "NOT CONNECTED";
    details = "Telemetry source: " + (data.data_source || "UNVERIFIED");
  }

  if (endpoint === "health") {
    status = data.financial_execution_enabled === false
      ? "DISABLED"
      : "VERIFY STATUS";
    details = "Backend health: " + (data.status || "UNKNOWN");
  }

  badge.textContent = status;
  badge.className = "status " +
    (endpoint === "health" || status === "VERIFY STATUS" ? "bad" : "warn");

  let info = card.querySelector(".api-detail");
  if (!info) {
    info = document.createElement("p");
    info.className = "api-detail";
    card.appendChild(info);
  }
  info.textContent = details;
}

async function refreshMonitoring() {
  for (const endpoint of endpoints) {
    const output = document.getElementById("monitor-" + endpoint);
    if (!output) continue;
    try {
      const response = await fetch("/api/" + endpoint, {
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      output.textContent = JSON.stringify(data, null, 2);
      updateSummaryCard(endpoint, data);
    } catch (error) {
      output.textContent = "Monitoring unavailable: " + error.message;
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  createMonitorPanels();
  refreshMonitoring();
  setInterval(refreshMonitoring, 30000);
});
