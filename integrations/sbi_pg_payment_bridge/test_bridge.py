import io
import sys
import types
sys.modules.setdefault("flask", types.SimpleNamespace(jsonify=None, request=None))
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sbi_payment_pg_bridge import ContractError, payment_rows, _credit_paise


def fixture(formula=False, shared=False):
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def row(num, strings):
        out=[]
        for i, value in enumerate(strings):
            addr=f'{chr(65+i)}{num}'
            if formula and num==2 and i==2:
                out.append(f'<c r="{addr}"><f>100+18</f><v>118</v></c>')
            elif shared:
                out.append(f'<c r="{addr}" t="s"><v>{i if num==1 else 3+i}</v></c>')
            else:
                out.append(f'<c r="{addr}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        return f'<row r="{num}">{"".join(out)}</row>'
    s=f'<worksheet xmlns="{ns}"><sheetData>'+row(1,['Description','SOL ID','Credit Amount'])+row(2,['TEST PAYMENT','99999','118.00'])+'</sheetData></worksheet>'
    workbook=f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    sst=f'<sst xmlns="{ns}">'+''.join(f'<si><t>{x}</t></si>' for x in ['Description','SOL ID','Credit Amount','TEST PAYMENT','99999','118.00'])+'</sst>'
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for key, val in {'[Content_Types].xml':'<Types/>','xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':rels,'xl/worksheets/sheet1.xml':s,**({'xl/sharedStrings.xml':sst} if shared else {})}.items():
            z.writestr(key,val)
    return stream.getvalue()

class Tests(unittest.TestCase):
    def test_inline(self):
        self.assertEqual(payment_rows(fixture()),[(2,{'Description':'TEST PAYMENT','SOL ID':'99999','Credit Amount':'118.00'},11800)])
    def test_shared(self):
        self.assertEqual(payment_rows(fixture(shared=True))[0][2],11800)
    def test_formula_rejected(self):
        with self.assertRaises(ContractError): payment_rows(fixture(formula=True))
    def test_precision(self):
        with self.assertRaises(ContractError): _credit_paise('118.001')
    def test_zero(self):
        with self.assertRaises(ContractError): _credit_paise('0')

if __name__=='__main__': unittest.main()
