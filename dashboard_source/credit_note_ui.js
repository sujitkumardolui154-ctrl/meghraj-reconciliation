/* Credit note generation — manual note/date, verified invoice numbers from DB.
   Every control uses same-origin authenticated Firebase + CSRF.
*/
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  if (!$("ig-cn-form")) return;
  const numbers = $("ig-cn-entries");
  const noteNo = $("ig-cn-number");
  const noteDate = $("ig-cn-date");
  const reason = $("ig-cn-reason");
  const previewButton = $("ig-cn-preview");
  const lookupButton = $("ig-cn-lookup");
  const finalize = $("ig-cn-finalize");
  const download = $("ig-cn-download");
  const notice = $("ig-cn-message");
  const found = $("ig-cn-found");
  let approvedPreview = null, lastFinalized = null, busy = false;

  function invalidate() {
    approvedPreview = null; lastFinalized = null;
    finalize.disabled = true; download.disabled = true;
  }
  for (const el of [numbers, noteNo, noteDate, reason]) {
    el.addEventListener("input", invalidate);
    el.addEventListener("change", invalidate);
  }
  $("ig-cn-form").addEventListener("submit", event => event.preventDefault());

  function parseRows() {
    const rows = numbers.value.trim().split(/\r?\n/);
    if (!rows.length || rows.length > 1000)
      throw new Error("Provide 1–1,000 original invoice rows.");
    const out = [], seen = new Set();
    for (const item of rows) {
      if (!item.trim()) continue;
      const parts = item.split("\t").map(x => x.trim());
      if (parts.length !== 2)
        throw new Error("Each row must have Invoice No [TAB] Credited Taxable Amount.");
      if (parts[0].toLowerCase() === "invoice no" ||
          parts[0].toLowerCase() === "invoice no.") continue;
      if (!/^MXP[0-9]{4,10}$/.test(parts[0]))
        throw new Error("Invalid original invoice number: " + parts[0]);
      if (seen.has(parts[0]))
        throw new Error("Same invoice repeated: " + parts[0]);
      if (!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(parts[1]) ||
          Number(parts[1]) <= 0)
        throw new Error("Invalid credit amount for " + parts[0]);
      seen.add(parts[0]);
      out.push({invoice_no:parts[0],credited_taxable:parts[1]});
    }
    if (!out.length) throw new Error("No credit note rows supplied.");
    return out;
  }

  function requestPayload() {
    const id = noteNo.value.trim();
    if (!/^MXP\/[0-9]{4}-[0-9]{4}\/[0-9]{1,6}$/.test(id))
      throw new Error("Enter a unique note number, e.g. MXP/2026-2027/01.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(noteDate.value))
      throw new Error("Select the credit note date.");
    if (reason.value.trim().length < 10)
      throw new Error("Provide a reason of at least 10 characters.");
    return {
      credit_note_no: id, credit_note_date: noteDate.value,
      reason: reason.value.trim(), entries: parseRows()
    };
  }
  async function csrf() {
    const r = await fetch("/auth/csrf", {
      credentials:"same-origin", cache:"no-store", redirect:"error"
    });
    if (!r.ok) throw new Error("Sign in before generating credit notes.");
    const token = (await r.json()).csrf_token || "";
    if (!/^[0-9a-f]{64}$/.test(token)) throw new Error("Invalid CSRF token.");
    return token;
  }
  async function post(path,data) {
    const token = await csrf();
    const r = await fetch("/api/credit-notes/"+path, {
      method:"POST", credentials:"same-origin", cache:"no-store",redirect:"error",
      headers:{"Content-Type":"application/json","X-DIL-CSRF":token},
      body:JSON.stringify(data)
    });
    if (!(r.headers.get("Content-Type") || "").includes("application/json"))
      throw new Error("Credit note service unavailable.");
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || "Credit note request failed.");
    return body;
  }
  function setBusy(v) {
    busy = v;
    previewButton.disabled = v;
    lookupButton.disabled = v;
    finalize.disabled = v || !approvedPreview;
    download.disabled = v || !lastFinalized;
  }
  function showInvoices(invoices) {
    const table = document.createElement("table");
    const head = document.createElement("tr");
    for (const col of ["Invoice No","Status","Invoice Date","Month","SOL","Original Taxable","Previously Credited","Remaining"]) {
      const th = document.createElement("th"); th.textContent=col;
      th.style.textAlign="left";th.style.padding="5px";head.appendChild(th);
    }
    table.appendChild(head);
    for (const source of invoices) {
      const tr = document.createElement("tr");
      const vals = [
        source.invoice_no,source.status,source.invoice_date,
        source.service_month,source.sol_id,source.original_taxable,
        source.previously_credited,source.remaining_taxable
      ];
      for (const val of vals) {
        const td=document.createElement("td");
        td.textContent=String(val ?? "—"); td.style.padding="5px";
        td.style.borderTop="1px solid #999";tr.appendChild(td);
      }
      table.appendChild(tr);
    }
    found.replaceChildren(table);
  }
  lookupButton.addEventListener("click", async () => {
    if (busy) return;
    setBusy(true);
    try {
      const rows = parseRows();
      const r = await post("lookup",{invoice_numbers:rows.map(x=>x.invoice_no)});
      showInvoices(r.invoices || []);
      notice.textContent = "Lookup complete. Confirm original invoice dates, months, " +
        "GSTIN and credit balance. Historical invoices not present in the isolated " +
        "registry are NOT assumed to exist.";
    } catch(e) {notice.textContent=e.message;}
    finally {setBusy(false);}
  });
  previewButton.addEventListener("click", async () => {
    if (busy) return;
    setBusy(true);invalidate();
    try {
      const values=requestPayload();
      const r=await post("preview",values);
      const data=r.credit_note;
      approvedPreview=JSON.stringify(values);
      notice.textContent="PREVIEW ONLY — "+data.credit_note_no+
        "\nDate: "+data.credit_note_date+
        "\nCustomer: "+data.customer_name+" | GSTIN: "+data.customer_gstin+
        "\nInvoices: "+data.line_count+
        "\nCredit taxable: Rs "+data.taxable+
        "\nCGST 9%: Rs "+data.cgst+" | SGST 9%: Rs "+data.sgst+
        "\nTotal credit note: Rs "+data.total+
        "\nNo database write performed.";
    } catch(e) {notice.textContent=e.message;}
    finally {setBusy(false);}
  });
  finalize.addEventListener("click", async () => {
    if (busy || !approvedPreview) return;
    setBusy(true);
    try {
      const payload=requestPayload();
      if (approvedPreview !== JSON.stringify(payload))
        throw new Error("Credit note fields changed; preview again.");
      if (!window.confirm("Finalize credit note "+payload.credit_note_no+
                          " in isolated QA only? This is immutable.")) return;
      const r=await post("finalize",payload);
      approvedPreview=null; lastFinalized=r.credit_note_no;
      notice.textContent="CREDIT NOTE QA RECORDED: "+r.credit_note_no+
        "\nInvoices: "+r.line_count+" | Total: Rs "+r.total+
        "\nNo payment reconciliation, GST filing or ledger posting executed.";
    } catch(e) {approvedPreview=null; notice.textContent=e.message;}
    finally {setBusy(false);}
  });
  download.addEventListener("click", async () => {
    if (busy || !lastFinalized) return;
    setBusy(true);
    try {
      const r=await fetch("/api/credit-notes/pdf?no="+encodeURIComponent(lastFinalized),{
        credentials:"same-origin",cache:"no-store",redirect:"error"
      });
      if (!r.ok) {
        const body=await r.json().catch(()=>({}));
        throw new Error(body.error || "PDF unavailable.");
      }
      if (!(r.headers.get("Content-Type") || "").includes("application/pdf"))
        throw new Error("Invalid PDF response content-type.");
      const blob=await r.blob();
      if (new TextDecoder().decode(await blob.slice(0,5).arrayBuffer()) !== "%PDF-")
        throw new Error("Invalid PDF file.");
      const href=URL.createObjectURL(blob), a=document.createElement("a");
      a.href=href;a.download="Meghraj-Credit-Note-"+lastFinalized.replace(/\//g,"-")+".pdf";
      document.body.appendChild(a);a.click();a.remove();
      setTimeout(()=>URL.revokeObjectURL(href),60000);
      notice.textContent="Credit Note PDF downloaded: "+lastFinalized;
    } catch(e){notice.textContent=e.message;}
    finally{setBusy(false);}
  });
})();
