"""R27.1 FFI-001 negative intake and minimal synthetic OOXML tests."""
import hashlib
from io import BytesIO
from dataclasses import replace
import sys,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r27_1_ffi001_fresh_intake_structure_gate import (
    FreshIntakeRefusal,FreshIntakeRequest,inspect_fresh_file_structure,
    STAGE,
)

NS="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P="http://schemas.openxmlformats.org/package/2006/relationships"
REQ=FreshIntakeRequest("fresh_sbi_input.xlsx","CURRENT_RUN_USER_ATTACHMENT",
    "SYN-CURRENT-SESSION-0001",True)


def stub_file(sheet_names=("Invoice Details.","PAYMNENT"), *,
              hidden=None, bad_rel=False, traversal=False, malicious_xml=False):
    hidden=hidden or set()
    sheet_entries=[]
    rel_entries=[]
    paths={}
    for i,name in enumerate(sheet_names,1):
        hidden_attr=' state="hidden"' if name in hidden else ""
        sheet_entries.append(
          f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"{hidden_attr}/>')
        target="../bad.xml" if bad_rel and i==1 else f"worksheets/sheet{i}.xml"
        rel_entries.append(
          f'<Relationship Id="rId{i}" Type="{R}/worksheet" Target="{target}"/>')
        paths[f"xl/worksheets/sheet{i}.xml"]=f'<worksheet xmlns="{NS}"><sheetData/></worksheet>'
    wb=f'<workbook xmlns="{NS}" xmlns:r="{R}"><sheets>{"".join(sheet_entries)}</sheets></workbook>'
    if malicious_xml:
        wb='<!DOCTYPE x [<!ENTITY entity SYSTEM "file:///etc/passwd">]>'+wb
    rels=f'<Relationships xmlns="{P}">{"".join(rel_entries)}</Relationships>'
    entries={
        "[Content_Types].xml":'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "_rels/.rels":f'<Relationships xmlns="{P}"/>',
        "xl/workbook.xml":wb,
        "xl/_rels/workbook.xml.rels":rels,
        **paths,
    }
    if traversal:
        entries["../unsafe.txt"]="hidden"
    out=BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,value in entries.items():
            z.writestr(name,value)
    return out.getvalue()


class FreshFFI001Test(unittest.TestCase):
    def refused(self,reason,source=None,request=None,**kw):
        with self.assertRaisesRegex(FreshIntakeRefusal,reason):
            inspect_fresh_file_structure(
                stub_file() if source is None else source,
                REQ if request is None else request,**kw)

    def test_01_synthetic_valid_structure_not_authority(self):
        file=stub_file()
        x=inspect_fresh_file_structure(file,REQ)
        self.assertEqual(x["stage"],STAGE)
        self.assertTrue(x["required_sheets_present"])
        self.assertEqual(x["sha256_of_bytes_inspected"],hashlib.sha256(file).hexdigest())
        self.assertFalse(x["host_authenticated_fresh_upload_provenance_verified"])
        self.assertFalse(x["genuine_financial_source_certified"])
        self.assertFalse(x["financial_header_and_row_count_verified"])
        self.assertFalse(x["bank_credit_column_i_and_invoice_s_verified"])
        self.assertIsNone(x["final_payment_status"])
        self.assertEqual(x["real_bank_allocations"],0)
        self.assertEqual(x["real_database_writes"],0)
        self.assertTrue(x["financial_apply_locked"])
        self.assertFalse(x["production_release_authorized"])

    def test_02_current_attachment_must_be_explicit(self):
        self.refused("FFI001_FRESH",request=replace(
            REQ,selected_as_current_run_input=False))

    def test_03_historical_drive_file_disallowed(self):
        self.refused("FFI001_FRESH",request=replace(
            REQ,selected_origin="HISTORICAL_GOOGLE_DRIVE"))

    def test_04_library_file_disallowed(self):
        self.refused("FFI001_FRESH",request=replace(
            REQ,selected_origin="LIBRARY_REFERENCE"))

    def test_05_project_file_disallowed(self):
        self.refused("FFI001_FRESH",request=replace(
            REQ,selected_origin="OLD_PROJECT_UPLOAD"))

    def test_06_untrusted_session_id_denied(self):
        self.refused("NEW_CURRENT_RUN_ID",request=replace(REQ,current_run_id=""))

    def test_07_wrong_expected_original_hash_denied(self):
        self.refused("FRESH_ORIGINAL_FILE_SHA256_MISMATCH",request=replace(
            REQ,expected_original_file_sha256="a"*64))

    def test_08_matching_hash_is_still_not_signed_approval(self):
        f=stub_file()
        x=inspect_fresh_file_structure(f,replace(REQ,
            expected_original_file_sha256=hashlib.sha256(f).hexdigest()))
        self.assertFalse(x["host_authenticated_fresh_upload_provenance_verified"])
        self.assertFalse(x["genuine_financial_source_certified"])

    def test_09_missing_paymnent_sheet_denied(self):
        self.refused("REQUIRED_INVOICE_AND_PAYMNENT_TABS_MISSING",
                     source=stub_file(sheet_names=("Invoice Details.",)))

    def test_10_missing_invoice_sheet_denied(self):
        self.refused("REQUIRED_INVOICE_AND_PAYMNENT_TABS_MISSING",
                     source=stub_file(sheet_names=("PAYMNENT",)))

    def test_11_hidden_payment_sheet_denied(self):
        self.refused("REQUIRED_FINANCIAL_SHEET_HIDDEN",
                     source=stub_file(hidden={"PAYMNENT"}))

    def test_12_unsafe_zip_traversal_denied(self):
        self.refused("UNSAFE_ENCRYPTED_OR_TRAVERSAL_XLSX_ENTRY",
                     source=stub_file(traversal=True))

    def test_13_unsafe_relationship_denied(self):
        self.refused("UNSAFE_SHEET_RELATIONSHIP",
                     source=stub_file(bad_rel=True))

    def test_14_xml_entity_denied(self):
        self.refused("UNTRUSTED_XML_ENTITIES_REFUSED",
                     source=stub_file(malicious_xml=True))

    def test_15_nonzip_not_accepted(self):
        self.refused("INVALID_XLSX_CONTAINER_SIGNATURE",source=b"not a zip")

    def test_16_false_xlsx_name_denied(self):
        self.refused("FRESH_XLSX_FILE_NAME_REQUIRED",request=replace(
            REQ,file_name="source.xlsm"))

    def test_17_financial_apply_nonlocked_denied(self):
        self.refused("FINANCIAL_APPLY_LOCK_REQUIRED",financial_apply="ENABLED")

    def test_18_missing_required_content_types_denied(self):
        file=BytesIO()
        with zipfile.ZipFile(file,"w") as z:
            z.writestr("xl/workbook.xml","invalid")
        self.refused("MISSING_REQUIRED_XLSX_CORE_PARTS",source=file.getvalue())

    def test_19_duplicate_sheet_name_denied(self):
        self.refused("INVALID_OR_DUPLICATE_XLSX_SHEET",
                     source=stub_file(sheet_names=("PAYMNENT","PAYMNENT","Invoice Details.")))

if __name__=="__main__":
    unittest.main()
