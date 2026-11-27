/* Invoice number cancellation / void — isolated QA only.
   Never modifies payment, reconciliation, credit-note or GST filing records.
*/
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const form = $("ig-cancel-form");
  if (!form) return;
  const number = $("ig-cancel-number");
  const code = $("ig-cancel-code");
  const reason = $("ig-cancel-reason");
  const review = $("ig-cancel-review");
  const attest = $("ig-cancel-attest");
  const check = $("ig-cancel-check");
  const submit = $("ig-cancel-submit");
  const notice = $("ig-cancel-message");
  const logButton = $("ig-cancel-log-refresh");
  const logArea = $("ig-cancel-log");
  let inspected = null;
  let busy = false;

  function invalidate() {
    inspected = null;
    submit.disabled = true;
  }
  for (const element of [number, code, reason, review, attest]) {
    element.addEventListener("input", invalidate);
    element.addEventListener("change", invalidate);
  }
  form.addEventListener("submit", event => event.preventDefault());

  async function read(path) {
    const response = await fetch("/api/invoice-gst/" + path, {
      credentials: "same-origin", cache: "no-store", redirect: "error"
    });
    if (!(response.headers.get("Content-Type") || "").includes("application/json"))
      throw new Error("Invoice service unavailable or sign-in expired.");
    return { response, data: await response.json() };
  }
  async function csrf() {
    const response = await fetch("/auth/csrf", {
      credentials: "same-origin", cache: "no-store", redirect: "error"
    });
    if (!response.ok) throw new Error("Sign in again before cancellation.");
    const token = (await response.json()).csrf_token || "";
    if (!/^[0-9a-f]{64}$/.test(token)) throw new Error("Invalid CSRF token.");
    return token;
  }
  function getNumber() {
    const id = number.value.trim();
    if (!/^MXP[0-9]{4,10}$/.test(id))
      throw new Error("Enter a valid MXP invoice number.");
    return id;
  }

  check.addEventListener("click", async () => {
    if (busy) return;
    invalidate();
    busy = true; check.disabled = true;
    try {
      const id = getNumber();
      const register = await read("cancellations?invoice_no=" + encodeURIComponent(id));
      if (!register.response.ok) throw new Error(register.data.error || "Cancellation registry unavailable.");
      if (register.data.count) {
        notice.textContent = "ALREADY CANCELLED / VOID — " + id +
          "\nAudit exists. This number cannot be reused or cancelled again.";
        return;
      }
      const lookup = await read("invoices/" + encodeURIComponent(id));
      let kind;
      if (lookup.response.status === 404 && lookup.data.error === "INVOICE_NOT_FOUND") {
        kind = "VOID_UNUSED";
      } else if (lookup.response.ok && lookup.data.invoice?.status === "FINALIZED") {
        kind = "CANCEL_FINALIZED";
      } else {
        throw new Error(lookup.data.error || "Invoice status cannot be confirmed.");
      }
      inspected = { invoiceNo: id, kind };
      submit.disabled = false;
      notice.textContent = kind === "VOID_UNUSED"
        ? "NO FINALIZED INVOICE IN ISOLATED REGISTRY — " + id +
          "\nThis number can be marked VOID_UNUSED in isolated QA only. " +
          "Historical records are NOT independently checked."
        : "FINALIZED INVOICE FOUND — " + id +
          "\nA review reference and accounting confirmation are mandatory. " +
          "This action does not create a credit note or reverse bank payments.";
    } catch (error) {
      notice.textContent = error.message;
    } finally {
      busy = false; check.disabled = false;
    }
  });

  logButton.addEventListener("click", async () => {
    if (busy) return;
    logButton.disabled = true;
    try {
      const result = await read("cancellations");
      if (!result.response.ok)
        throw new Error(result.data.error || "Audit register unavailable.");
      const records = result.data.records || [];
      if (!records.length) {
        logArea.textContent = "No cancellation or void records in this database.";
        return;
      }
      const table = document.createElement("table");
      table.style.width = "100%";
      table.style.borderCollapse = "collapse";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      const names = ["Invoice No", "Type", "Reason", "Date / Time", "Operator UID", "Review Ref"];
      for (const name of names) {
        const cell = document.createElement("th");
        cell.textContent = name;
        cell.style.textAlign = "left";
        cell.style.padding = "6px";
        headRow.appendChild(cell);
      }
      thead.appendChild(headRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      for (const record of records) {
        const tr = document.createElement("tr");
        const values = [record.invoice_no, record.cancellation_kind,
          record.reason_code + ": " + record.reason_text,
          record.cancelled_at, record.cancelled_by_uid,
          record.review_reference || "—"];
        for (const value of values) {
          const td = document.createElement("td");
          td.textContent = String(value || "");
          td.style.padding = "6px";
          td.style.borderTop = "1px solid #aaaaaa";
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      logArea.replaceChildren(table);
      logArea.style.overflowX = "auto";
    } catch (error) {
      logArea.textContent = error.message;
    } finally {
      logButton.disabled = false;
    }
  });

  submit.addEventListener("click", async () => {
    if (busy || !inspected) return;
    const before = inspected;
    try {
      const id = getNumber();
      if (id !== before.invoiceNo)
        throw new Error("Invoice number changed. Recheck status.");
      if (!code.value || reason.value.trim().length < 10)
        throw new Error("Select a reason and enter at least 10 characters.");
      if (before.kind === "VOID_UNUSED" && code.value !== "NUMBER_UNUSED")
        throw new Error("Unused invoice numbers must use the Number Unused reason.");
      if (before.kind === "CANCEL_FINALIZED" &&
          (review.value.trim().length < 6 || !attest.checked))
        throw new Error("Finalized invoice needs accounting review reference and confirmation.");
      if (!window.confirm("Permanently " + before.kind + " number " + id +
                          " in the isolated QA audit register? This cannot be undone."))
        return;
      busy = true; submit.disabled = true; check.disabled = true;
      const token = await csrf();
      const response = await fetch("/api/invoice-gst/cancellations", {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: {"Content-Type": "application/json", "X-DIL-CSRF": token},
        body: JSON.stringify({
          invoice_no: id, reason_code: code.value,
          reason: reason.value.trim(), review_reference: review.value.trim(),
          accounting_review_confirmed: attest.checked
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Cancellation rejected.");
      notice.textContent = "AUDIT RECORDED — " + data.invoice_no +
        "\nStatus: CANCELLED / " + data.cancellation_kind +
        "\nOriginal invoice and shipments have not been deleted." +
        "\nNo GST filing or payment reversal executed.";
      invalidate();
    } catch (error) {
      notice.textContent = error.message;
      invalidate();
    } finally {
      busy = false; check.disabled = false;
    }
  });
})();
