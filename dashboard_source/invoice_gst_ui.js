/* SBI approved Invoice UI Version 2. Authenticated same-origin API only.
   The AWB table is a working draft: final invoice rows are immutable.
   Selection and edits are revalidated by the server at preview/finalize.
*/
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const branch = $("ig-branch");
  const branchSearch = $("ig-branch-search");
  const preview = $("ig-preview");
  const finalize = $("ig-finalize");
  const pdfButton = $("ig-pdf");
  const notice = $("ig-message");
  const gstButton = $("ig-gst-download");
  const gstNotice = $("ig-gst-message");
  if (!branch || !branchSearch || !preview || !finalize || !gstButton) return;

  const PAGE_SIZE = 100;
  const labelMonths = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
  let awbs = [];
  let approvedPreview = null;
  let lastFinalized = null;
  let loadedOriginal = null;
  let correctionSource = null;
  let mode = "new";
  let page = 0;
  let busy = false;
  let lookupSequence = 0;
  let lookupDebounce = null;
  $("ig-form").addEventListener("submit", event => event.preventDefault());

  function message(text) { notice.textContent = text; }
  function invalidate() {
    approvedPreview = null;
    finalize.disabled = true;
    if (mode !== "view") lastFinalized = null;
    pdfButton.disabled = !lastFinalized || busy;
  }
  function whenBusy(value) {
    busy = value;
    preview.disabled = value || mode === "view";
    finalize.disabled = value || !approvedPreview || mode !== "new";
    pdfButton.disabled = value || !lastFinalized;
    $("ig-merge-excel").disabled = value || mode === "view";
    $("ig-merge-paste").disabled = value || mode === "view";
    $("ig-find").disabled = value;
  }
  async function api(path, options={}) {
    const response = await fetch("/api/invoice-gst/" + path, {
      credentials:"same-origin", cache:"no-store", redirect:"error", ...options
    });
    if (!(response.headers.get("Content-Type") || "").includes("application/json"))
      throw new Error("Unexpected response. Check sign-in and feature status.");
    const body = await response.json();
    if (!response.ok)
      throw new Error(body.error || "Invoice service unavailable (" + response.status + ")");
    return body;
  }
  async function csrf() {
    const response = await fetch("/auth/csrf", {
      credentials:"same-origin", cache:"no-store", redirect:"error"
    });
    if (!response.ok) throw new Error("Sign in again before submitting invoice data.");
    const token = (await response.json()).csrf_token || "";
    if (!/^[0-9a-f]{64}$/.test(token)) throw new Error("Invalid CSRF token.");
    return token;
  }
  async function submit(action, data) {
    const token = await csrf();
    return api(action,{
      method:"POST",
      headers:{"Content-Type":"application/json","X-DIL-CSRF":token},
      body:JSON.stringify(data),
    });
  }

  function fy(dateStr) {
    const parts = dateStr.split("-").map(Number);
    if (parts.length !== 3 || parts.some(n => !Number.isInteger(n))) return "";
    const start = parts[1] >= 4 ? parts[0] : parts[0]-1;
    return String(start) + "-" + String(start+1);
  }
  function validIso(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
    const t = new Date(iso + "T00:00:00Z");
    return !Number.isNaN(t.getTime()) && t.toISOString().slice(0,10) === iso;
  }
  function isoDate(raw) {
    const text = String(raw || "").trim();
    if (validIso(text)) return text;
    const d = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(text);
    if (!d) throw new Error("Invalid dispatch date: " + text);
    const iso = d[3] + "-" + d[2].padStart(2,"0") + "-" + d[1].padStart(2,"0");
    if (!validIso(iso)) throw new Error("Invalid dispatch date: " + text);
    return iso;
  }
  function serviceLabel(a,b) {
    if (!validIso(a) || !validIso(b) || a>b) return "";
    const [ay,am] = a.split("-").map(Number),[by,bm] = b.split("-").map(Number);
    if (ay===by && am===bm) {
      return new Date(a+"T00:00:00Z").toLocaleDateString("en-GB",{
        month:"long",year:"numeric",timeZone:"UTC"
      });
    }
    return ay===by
      ? labelMonths[am-1]+" To "+labelMonths[bm-1]+" "+by
      : labelMonths[am-1]+" "+ay+" To "+labelMonths[bm-1]+" "+by;
  }
  function billPeriod() {
    const first=$("ig-from").value,last=$("ig-to").value;
    return validIso(first) && validIso(last) && first<=last && fy(first)===fy(last);
  }
  function periodUpdate() {
    const a=$("ig-from").value,b=$("ig-to").value;
    $("ig-service-label").value=serviceLabel(a,b);
    $("ig-fy-label").value=validIso(a)&&validIso(b)&&fy(a)===fy(b)?fy(a):"Review required";
    const status=$("ig-period-status");
    if (!a || !b) status.textContent="Enter Bill Period From and To dates.";
    else if (!billPeriod()) status.textContent=
      "Invalid period or cross-financial-year billing. Review before invoicing.";
    else status.textContent="Service Period: "+serviceLabel(a,b)+
      (a.slice(0,7)!==b.slice(0,7)
        ? " · Cross-month GST filing allocation requires separate release approval."
        : " · Single-month period.");
    updateTotals();
  }
  function inPeriod(row) {
    return billPeriod() && row.dispatch_date >= $("ig-from").value &&
      row.dispatch_date <= $("ig-to").value;
  }
  function validCents(raw) {
    if (typeof raw !== "string" || !/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(raw))
      return null;
    const digits=raw.split(".");
    const cents=Number(digits[0])*100+Number((digits[1]||"").padEnd(2,"0"));
    return Number.isSafeInteger(cents) && cents>0 ? cents : null;
  }
  function validWeight(raw) {
    return typeof raw==="string" &&
      /^(?:0|[1-9]\d*)(?:\.\d{1,3})?$/.test(raw) &&
      Number(raw)>0 && Number.isFinite(Number(raw));
  }
  function validateRow(row) {
    if (!validIso(row.dispatch_date) || !/^[A-Za-z0-9/-]{1,40}$/.test(row.lr_no))
      return "Invalid original AWB/date";
    if (row.packet_ref_no.length>80 || /[\x00-\x1f]/.test(row.packet_ref_no))
      return "Invalid Packet Ref";
    if (!row.consignee.trim() || row.consignee.length>200 ||
        /[\x00-\x1f]/.test(row.consignee)) return "Invalid Consignee";
    if (!validWeight(row.weight_kg)) return "Invalid Weight";
    if (validCents(row.amount)===null) return "Invalid Amount";
    if (!inPeriod(row)) return "Outside bill period";
    return "";
  }
  function formatRupees(cents) {
    return "₹"+(cents/100).toLocaleString("en-IN",{
      minimumFractionDigits:2,maximumFractionDigits:2
    });
  }
  function updateTotals() {
    let selected=0,valid=0,amount=0,review=0;
    for (const row of awbs) {
      if (!row.selected) continue;
      selected++;
      const issue=validateRow(row);
      if (issue) {review++;continue;}
      const cents=validCents(row.amount);
      if (cents!==null) {valid++;amount+=cents;}
    }
    const cgst=Math.round(amount*9/100),sgst=Math.round(amount*9/100);
    $("ig-awb-count").textContent="Imported: "+awbs.length+
      " | Selected: "+selected+" | Excluded: "+(awbs.length-selected)+
      " | Selected needing review: "+review;
    $("ig-awb-summary").textContent="Selected eligible: "+valid+
      " | Taxable "+formatRupees(amount)+
      " | CGST 9% "+formatRupees(cgst)+
      " | SGST 9% "+formatRupees(sgst)+
      " | Total "+formatRupees(amount+cgst+sgst);
  }
  function editableInput(row,field,cell,kind) {
    const input=document.createElement("input");
    input.type="text";
    input.value=row[field];
    input.disabled=mode==="view";
    input.setAttribute("aria-label",field.replaceAll("_"," ")+" for "+row.lr_no);
    input.autocomplete="off";
    if (kind==="money") input.inputMode="decimal";
    if (kind==="weight") input.inputMode="decimal";
    input.addEventListener("input",()=>{
      row[field]=input.value;
      invalidate();
      updateTotals();
      const issue=validateRow(row);
      const status=cell.parentElement.lastChild;
      status.textContent=issue||"Eligible";
    });
    cell.appendChild(input);
  }
  function paintRows() {
    const body=$("ig-awb-body");
    body.replaceChildren();
    const pages=Math.ceil(awbs.length/PAGE_SIZE);
    page=Math.max(0,Math.min(page,Math.max(0,pages-1)));
    const slice=awbs.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
    if (!slice.length) {
      const tr=document.createElement("tr"),td=document.createElement("td");
      td.colSpan=8;td.textContent="No AWBs loaded. Upload a six-column Excel annexure.";
      tr.appendChild(td);body.appendChild(tr);
    }
    for (const row of slice) {
      const tr=document.createElement("tr");
      if (!row.selected)tr.className="ig-v2-excluded";
      const td = text => {
        const cell=document.createElement("td");
        cell.textContent=String(text??"");
        tr.appendChild(cell);return cell;
      };
      const choose=td("");
      const cb=document.createElement("input");
      cb.type="checkbox";cb.checked=row.selected;cb.disabled=mode==="view";
      cb.setAttribute("aria-label","Include AWB "+row.lr_no);
      cb.addEventListener("change",()=>{
        row.selected=cb.checked;invalidate();
        tr.className=row.selected?"":"ig-v2-excluded";
        const issue=validateRow(row);
        tr.lastChild.textContent=row.selected ? (issue||"Eligible") : "Excluded";
        updateTotals();
      });
      choose.appendChild(cb);
      td(row.dispatch_date);
      td(row.lr_no);
      for (const field of ["packet_ref_no","consignee","weight_kg","amount"]) {
        const c=td("");
        editableInput(row,field,c,field==="amount"?"money":field==="weight_kg"?"weight":"text");
      }
      td(row.selected ? (validateRow(row)||"Eligible") : "Excluded");
      body.appendChild(tr);
    }
    $("ig-awb-page").textContent="Page "+(pages?page+1:0)+" of "+pages;
    $("ig-awb-prev").disabled=page<=0;
    $("ig-awb-next").disabled=page>=pages-1;
    updateTotals();
  }
  function normalizeRow(row) {
    return {
      dispatch_date:isoDate(row.dispatch_date),
      lr_no:String(row.lr_no??"").trim(),
      packet_ref_no:String(row.packet_ref_no??"").trim(),
      consignee:String(row.consignee??"").trim(),
      weight_kg:String(row.weight_kg??"").trim(),
      amount:String(row.amount??"").trim(),
      selected:true
    };
  }
  function mergeRows(rows, uploadDuplicates=0) {
    if (mode==="view") throw new Error("Finalized invoice is read-only.");
    if (!Array.isArray(rows)||!rows.length)throw new Error("No AWBs supplied.");
    if (rows.length+awbs.length>10000)throw new Error("Annexure merge limit exceeded.");
    const keys=new Set(awbs.map(x=>x.dispatch_date+"|"+x.lr_no));
    let added=0,dups=uploadDuplicates,outside=0;
    const pending=[];
    for (const raw of rows) {
      const row=normalizeRow(raw),key=row.dispatch_date+"|"+row.lr_no;
      if (keys.has(key)) {dups++;continue;}
      if (awbs.length+pending.length>=5000)
        throw new Error("Maximum 5,000 AWBs per draft. No rows from this upload were merged.");
      keys.add(key);
      row.selected=validateRow(row)==="";
      if(!row.selected)outside++;
      pending.push(row);added++;
    }
    // Atomic local merge: even a rejected 5001st AWB cannot leave a partial
    // uploaded draft or invalidate a previously approved preview unnoticed.
    awbs.push(...pending);
    page=0;invalidate();paintRows();
    $("ig-merge-status").textContent="Merged "+added+" AWB(s), skipped "+dups+
      " duplicate(s), "+outside+" outside period or invalid (unchecked). "+
      "Edit Packet Ref, Consignee, Weight or Amount directly in the table.";
  }
  function pastedRows() {
    const raw=$("ig-annexure").value.trim();
    if(!raw)throw new Error("Paste the six Excel columns first.");
    const result=[];
    for(const line of raw.split(/\r?\n/)) {
      if(!line.trim())continue;
      const parts=line.split("\t").map(v=>v.trim());
      if(parts[0]?.toLowerCase()==="dispatch date")continue;
      if(parts.length!==6)throw new Error("Each Excel row must have six tab-separated fields.");
      result.push({
        dispatch_date:isoDate(parts[0]),lr_no:parts[1],
        packet_ref_no:parts[2],consignee:parts[3],
        weight_kg:parts[4],amount:parts[5]
      });
    }
    return result;
  }
  function setMode(next) {
    mode=next;
    const locked=next==="view";
    for (const id of ["ig-branch","ig-branch-search","ig-number","ig-date","ig-from",
                       "ig-to","ig-annexure","ig-annexure-file","ig-select-all",
                       "ig-deselect-all","ig-remove-excluded","ig-merge-excel","ig-merge-paste"]) {
      $(id).disabled=locked;
    }
    $("ig-correction").hidden=!locked||!loadedOriginal||loadedOriginal.status!=="FINALIZED";
    $("ig-loaded-banner").textContent=locked
      ? "FINALIZED / CANCELLED — READ ONLY · The original invoice and AWBs cannot be changed."
      : next==="correction"
        ? "CORRECTION WORKING COPY — REVIEW ONLY · New invoice number required; finalization locked."
        : "NEW WORKING INVOICE · Editing is local until an authorized finalization.";
    whenBusy(busy);
    paintRows();
  }
  async function loadBranches(query="", preferred="") {
    const serial=++lookupSequence;
    try {
      const data=await api("branches?search="+encodeURIComponent(query));
      if(serial!==lookupSequence)return false;
      branch.replaceChildren(new Option("Select verified SBI branch",""));
      let found=false;
      for(const item of data.branches||[]) {
        branch.appendChild(new Option(
          item.client_name+" — SOL "+item.sol_id+" ("+item.invoice_branch+")",
          item.branch_key
        ));
        if(item.branch_key===preferred)found=true;
      }
      if(found)branch.value=preferred;
      $("ig-branch-status").textContent=String(data.count)+" verified branch matches"+
        (preferred&&!found?" · Original branch is not available in verified master.":"")+
        ". Select one option; typing alone does not verify a branch.";
      return found;
    } catch(e) {
      if(serial===lookupSequence)$("ig-branch-status").textContent=e.message;
      return false;
    }
  }
  branchSearch.addEventListener("input",()=>{
    if(mode==="view")return;
    branch.value="";invalidate();
    const query=branchSearch.value.trim();
    clearTimeout(lookupDebounce);
    lookupDebounce=setTimeout(()=>loadBranches(query),250);
  });
  branch.addEventListener("change",invalidate);
  for(const id of ["ig-number","ig-date"]) $(id).addEventListener("input",invalidate);
  for(const id of ["ig-from","ig-to"]) $(id).addEventListener("change",()=>{
    invalidate();periodUpdate();paintRows();
  });

  $("ig-merge-excel").addEventListener("click",async()=>{
    if(busy||mode==="view")return;
    const file=$("ig-annexure-file").files?.[0];
    if(!file||!file.name.toLowerCase().endsWith(".xlsx")) {
      $("ig-merge-status").textContent="Select a .xlsx Excel annexure first.";return;
    }
    if(file.size>8*1024*1024) {
      $("ig-merge-status").textContent="Maximum upload size: 8 MB.";return;
    }
    whenBusy(true);
    try {
      const token=await csrf();
      const data=new FormData();
      data.append("file",file,file.name);
      const result=await api("annexure/parse",{
        method:"POST",headers:{"X-DIL-CSRF":token},body:data
      });
      if(result.persisted!==false||result.financial_writes!==false)
        throw new Error("Unsafe annexure import result.");
      mergeRows(result.shipments,result.duplicate_rows_skipped||0);
    }catch(e){$("ig-merge-status").textContent=e.message;}
    finally{$("ig-annexure-file").value="";whenBusy(false);}
  });
  $("ig-merge-paste").addEventListener("click",()=>{
    if(busy||mode==="view")return;
    try{mergeRows(pastedRows());$("ig-annexure").value="";}
    catch(e){$("ig-merge-status").textContent=e.message;}
  });
  $("ig-select-all").addEventListener("click",()=>{
    if(busy||mode==="view")return;
    for(const row of awbs)row.selected=validateRow(row)==="";
    invalidate();paintRows();
  });
  $("ig-deselect-all").addEventListener("click",()=>{
    if(busy||mode==="view")return;
    for(const row of awbs)row.selected=false;
    invalidate();paintRows();
  });
  $("ig-remove-excluded").addEventListener("click",()=>{
    if(busy||mode==="view")return;
    awbs=awbs.filter(x=>x.selected);
    invalidate();page=0;paintRows();
    $("ig-merge-status").textContent="Excluded AWBs removed from this working draft only. No database update.";
  });
  $("ig-awb-prev").addEventListener("click",()=>{
    if(page>0){page--;paintRows();}
  });
  $("ig-awb-next").addEventListener("click",()=>{
    if((page+1)*PAGE_SIZE<awbs.length){page++;paintRows();}
  });

  function requestPayload() {
    if(!billPeriod())throw new Error("Valid same-financial-year bill period required.");
    if(!branch.value)throw new Error("Select a verified SBI branch, by SOL or name.");
    if(!/^MXP[0-9]{4,10}$/.test($("ig-number").value.trim()))
      throw new Error("Enter a valid unique MXP invoice number.");
    if(!validIso($("ig-date").value))
      throw new Error("Select an invoice date.");
    const chosen=awbs.filter(r=>r.selected);
    if(!chosen.length)throw new Error("Select at least one AWB.");
    for(const row of chosen) {
      const issue=validateRow(row);
      if(issue)throw new Error("AWB "+row.lr_no+": "+issue+". Edit it or deselect it.");
    }
    const data={
      branch_key:branch.value,
      invoice_no:$("ig-number").value.trim(),
      service_from:$("ig-from").value,
      service_to:$("ig-to").value,
      invoice_date:$("ig-date").value,
      shipments:chosen.map(r=>({
        dispatch_date:r.dispatch_date,lr_no:r.lr_no,
        packet_ref_no:r.packet_ref_no,consignee:r.consignee,
        weight_kg:r.weight_kg,amount:r.amount
      }))
    };
    if(correctionSource)data.replaces_invoice_no=correctionSource;
    return data;
  }
  preview.addEventListener("click",async()=>{
    if(busy||mode==="view")return;
    whenBusy(true);
    try {
      const values=requestPayload();
      const result=await submit("preview",values);
      approvedPreview=JSON.stringify(values);
      const p=result.invoice;
      message("PREVIEW ONLY — "+p.invoice_no+
        "\nBranch: "+p.client_name+" | SOL: "+p.sol_id+
        "\nService period: "+p.service_month+
        "\nAWBs selected: "+p.shipment_count+
        "\nTaxable: ₹"+p.taxable+" | CGST: ₹"+p.cgst+" | SGST: ₹"+p.sgst+
        "\nGrand total: ₹"+p.total+
        (p.multi_month_period
          ? "\nMULTI-MONTH: GST reporting allocation requires separate release approval."
          : "")+
        (result.invoice.correction_review_only
          ? "\nCORRECTION REVIEW ONLY: Existing finalized original is immutable; finalization blocked."
          : "\nNo database write performed."));
    }catch(e){approvedPreview=null;message(e.message);}
    finally{whenBusy(false);}
  });
  finalize.addEventListener("click",async()=>{
    if(busy||mode!=="new"||!approvedPreview)return;
    whenBusy(true);
    try {
      const values=requestPayload();
      if(JSON.stringify(values)!==approvedPreview)
        throw new Error("Working invoice changed since preview. Preview again.");
      if(!window.confirm("Finalize invoice "+values.invoice_no+
                         " with "+values.shipments.length+" selected AWBs? This is immutable."))
        return;
      const data=await submit("finalize",values);
      approvedPreview=null;
      lastFinalized=data.invoice_no;
      loadedOriginal={invoice_no:data.invoice_no,status:"FINALIZED"};
      correctionSource=null;
      setMode("view");
      message("FINALIZED & DATABASE RECORDED: "+data.invoice_no+
        "\nAWBs: "+data.shipment_count+" | Total: ₹"+data.total+
        "\nOriginal invoice is immutable. No reconciliation executed.");
    }catch(e){approvedPreview=null;message(e.message);}
    finally{whenBusy(false);}
  });
  $("ig-find").addEventListener("click",async()=>{
    if(busy)return;
    const number=$("ig-search-number").value.trim().toUpperCase();
    if(!/^MXP[0-9]{4,10}$/.test(number)){message("Enter a valid MXP invoice number.");return;}
    whenBusy(true);
    try {
      const record=await api("invoices/"+encodeURIComponent(number)+"?include_lines=1");
      if(!record.original_immutable||!record.correction_requires_separate_approval ||
         !Array.isArray(record.shipments))
        throw new Error("Full immutable invoice and annexure not verified.");
      const original=record.invoice;
      $("ig-number").value=original.invoice_no;
      $("ig-date").value=original.invoice_date;
      $("ig-from").value=original.service_from;
      $("ig-to").value=original.service_to;
      branchSearch.value=original.sol_id||original.client_name;
      const matched=await loadBranches(branchSearch.value,original.branch_key);
      awbs=record.shipments.map(r=>normalizeRow(r));
      page=0;loadedOriginal=original;correctionSource=null;approvedPreview=null;
      lastFinalized=original.status==="FINALIZED"?original.invoice_no:null;
      periodUpdate();setMode("view");
      message("DATABASE INVOICE LOADED — "+original.invoice_no+
        "\nStatus: "+original.status+
        "\nOriginal annexure: "+awbs.length+" AWBs"+
        (matched?"":"\nVerified branch not available in current master.")+
        "\nNo original fields changed. Use 'Prepare Correction Draft' for review.");
    }catch(e){message(e.message);}
    finally{whenBusy(false);}
  });
  $("ig-correction").addEventListener("click",()=>{
    if(busy||!loadedOriginal||loadedOriginal.status!=="FINALIZED")return;
    correctionSource=loadedOriginal.invoice_no;
    lastFinalized=null;approvedPreview=null;
    $("ig-number").value="";
    $("ig-number").placeholder="Enter NEW MXP invoice number";
    setMode("correction");
    message("CORRECTION REVIEW DRAFT from "+correctionSource+
      ". The original is immutable. Enter a NEW invoice number, review AWBs, and preview. "+
      "Finalization is blocked until a separately approved revision/audit workflow exists.");
  });
  $("ig-new").addEventListener("click",()=>{
    if(busy)return;
    loadedOriginal=null;correctionSource=null;
    lastFinalized=null;approvedPreview=null;awbs=[];page=0;
    for(const id of ["ig-number","ig-date","ig-from","ig-to","ig-service-label",
                     "ig-fy-label","ig-annexure","ig-search-number","ig-annexure-file",
                     "ig-branch-search"]) $(id).value="";
    branch.value="";
    setMode("new");periodUpdate();
    message("NEW WORKING INVOICE. Select a verified branch and merge AWBs.");
  });
  pdfButton.addEventListener("click",async()=>{
    if(busy||!lastFinalized)return;
    whenBusy(true);
    try {
      const response=await fetch("/api/invoice-gst/invoices/"+
        encodeURIComponent(lastFinalized)+".pdf",{
          credentials:"same-origin",cache:"no-store",redirect:"error"
        });
      if(!response.ok){
        const r=await response.json().catch(()=>({}));
        throw new Error(r.error||"Invoice PDF not available.");
      }
      if(!(response.headers.get("Content-Type")||"").includes("application/pdf"))
        throw new Error("Unexpected PDF response type.");
      const blob=await response.blob();
      if(new TextDecoder().decode(await blob.slice(0,5).arrayBuffer())!=="%PDF-")
        throw new Error("Invalid PDF signature.");
      const url=URL.createObjectURL(blob),link=document.createElement("a");
      link.href=url;link.download="Meghraj-"+lastFinalized+".pdf";
      document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),60000);
      message("Finalized invoice PDF downloaded: "+lastFinalized);
    }catch(e){message(e.message);}
    finally{whenBusy(false);}
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
  periodUpdate();
  paintRows();
})();
