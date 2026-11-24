/* SBI invoice generation + approved GST report UI.
   Always uses authenticated same-origin endpoints; no reconciliation writes. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const branch = $("ig-branch");
  const preview = $("ig-preview");
  const finalize = $("ig-finalize");
  const notice = $("ig-message");
  const gstButton = $("ig-gst-download");
  const gstNotice = $("ig-gst-message");
  if (!branch || !preview || !finalize || !gstButton) return;
  let approvedPreview = null;
  let busy = false;

  function whenBusy(status) {
    busy = status;
    preview.disabled = status;
    finalize.disabled = status || !approvedPreview;
    gstButton.disabled = status;
  }

  async function api(path, options = {}) {
    const response = await fetch("/api/invoice-gst/" + path, {
      credentials: "same-origin", cache: "no-store", redirect: "error", ...options
    });
    if (!response.headers.get("Content-Type")?.includes("application/json"))
      throw new Error("Unexpected response. Check your sign-in and feature status.");
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error || "Invoice service unavailable (" + response.status + ")");
    return payload;
  }

  async function csrf() {
    const response = await fetch("/auth/csrf", {
      credentials: "same-origin", cache: "no-store", redirect: "error"
    });
    if (!response.ok) throw new Error("Sign in again before submitting an invoice.");
    const token = (await response.json()).csrf_token || "";
    if (!/^[0-9a-f]{64}$/.test(token)) throw new Error("Invalid CSRF token.");
    return token;
  }

  function isoDate(raw) {
    const value = raw.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value);
    if (!m) throw new Error("Invalid dispatch date: " + value);
    return m[3] + "-" + m[2].padStart(2, "0") + "-" + m[1].padStart(2, "0");
  }

  function parseAnnexure() {
    const lines = $("ig-annexure").value.trim().split(/\r?\n/);
    const shipments = [];
    for (const line of lines) {
      if (!line.trim()) continue;
      const cols = line.split("\t").map(x => x.trim());
      if (cols[0]?.toLowerCase() === "dispatch date") continue;
      if (cols.length !== 6)
        throw new Error("Annexure requires exactly 6 tab-separated columns per row.");
      shipments.push({
        dispatch_date: isoDate(cols[0]), lr_no: cols[1],
        packet_ref_no: cols[2], consignee: cols[3],
        weight_kg: cols[4], amount: cols[5]
      });
    }
    if (!shipments.length || shipments.length > 5000)
      throw new Error("Paste 1 to 5000 shipment rows, copied from Excel.");
    return shipments;
  }

  function payload() {
    return {
      branch_key: branch.value, invoice_no: $("ig-number").value.trim(),
      service_from: $("ig-from").value,
      service_to: $("ig-to").value,
      invoice_date: $("ig-date").value,
      shipments: parseAnnexure()
    };
  }

  async function submit(action, content) {
    const token = await csrf();
    return api(action, {
      method: "POST", headers: {
        "Content-Type": "application/json", "X-DIL-CSRF": token
      }, body: JSON.stringify(content)
    });
  }

  async function loadBranches() {
    try {
      const data = await api("branches");
      branch.replaceChildren();
      const empty = new Option("Select verified SBI branch", "");
      branch.appendChild(empty);
      for (const row of data.branches || []) {
        branch.appendChild(new Option(
          row.client_name + " — SOL " + row.sol_id, row.branch_key
        ));
      }
      notice.textContent = data.count
        ? "Select a verified branch. No invoice will be saved until Finalize."
        : "No verified branch records loaded. Connect the approved branch master.";
    } catch (error) {
      notice.textContent = error.message;
    }
  }

  for (const id of ["ig-branch", "ig-number", "ig-from", "ig-to", "ig-date", "ig-annexure"]) {
    $(id).addEventListener("input", () => {
      approvedPreview = null;
      finalize.disabled = true;
    });
  }

  preview.addEventListener("click", async () => {
    if (busy) return;
    whenBusy(true);
    try {
      const values = payload();
      const result = await submit("preview", values);
      approvedPreview = JSON.stringify(values);
      const p = result.invoice;
      notice.textContent =
        "PREVIEW ONLY — " + p.invoice_no +
        "\nBranch: " + p.client_name + " | SOL: " + p.sol_id +
        "\nService month: " + p.service_month +
        "\nShipments: " + p.shipment_count +
        "\nTaxable: Rs " + p.taxable +
        "\nCGST: Rs " + p.cgst + " | SGST: Rs " + p.sgst +
        "\nGrand total: Rs " + p.total +
        "\nNo database write performed.";
    } catch (error) {
      approvedPreview = null;
      notice.textContent = error.message;
    } finally {
      whenBusy(false);
    }
  });

  finalize.addEventListener("click", async () => {
    if (busy || !approvedPreview) return;
    whenBusy(true);
    try {
      const values = payload();
      if (JSON.stringify(values) !== approvedPreview)
        throw new Error("Invoice changed since preview. Preview again.");
      const data = await submit("finalize", values);
      approvedPreview = null;
      notice.textContent = "FINALIZED & DATABASE RECORDED: " + data.invoice_no +
        "\nShipments: " + data.shipment_count + " | Total: Rs " + data.total +
        "\nReconciliation was NOT executed. A second finalization is blocked.";
    } catch (error) {
      approvedPreview = null;
      notice.textContent = error.message;
    } finally {
      whenBusy(false);
    }
  });

  gstButton.addEventListener("click", async () => {
    if (busy) return;
    const month = $("ig-gst-month").value;
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) {
      gstNotice.textContent = "Select a valid service month.";
      return;
    }
    whenBusy(true);
    gstNotice.textContent = "Checking verified, finalized invoices...";
    try {
      const response = await fetch("/api/invoice-gst/gst.xlsx?month=" +
        encodeURIComponent(month), {
          credentials: "same-origin", cache: "no-store", redirect: "error"
        });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "GST report unavailable.");
      }
      const ct = (response.headers.get("Content-Type") || "").toLowerCase();
      if (!ct.includes("spreadsheetml.sheet"))
        throw new Error("Unexpected report type.");
      const blob = await response.blob();
      const header = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
      if (header[0] !== 0x50 || header[1] !== 0x4b)
        throw new Error("Invalid Excel document.");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "SBI-GST-" + month + ".xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      gstNotice.textContent = "GST report downloaded. Rows: " +
        (response.headers.get("X-Report-Rows") || "unknown") +
        ". Approved 16-column header; no reconciliation writes.";
    } catch (error) {
      gstNotice.textContent = error.message;
    } finally {
      whenBusy(false);
    }
  });

  loadBranches();
})();
