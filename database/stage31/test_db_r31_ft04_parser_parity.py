"""R31 approved bulk parser parity around duplicate source rows (synthetic)."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from db_r31_ft04_parser_parity import (
    classify_exact_ft04_rows,RowParityReviewRequired,
)

def payment(desc="SAME PAYMENT",sol="001505",amt="10.00"):
    return {"Description":desc,"SOL ID":sol,"Credit Amount":amt}


class StubFT04:
    def __init__(self,rows):
        self.rows=rows
        self.single_calls=0
    def _all_source_rows(self,payload):
        return self.rows
    def _single_row_xlsx(self,payload,number):
        self.single_calls+=1
        return ("one:"+str(number)).encode()


class ParserParity(unittest.TestCase):
    def setup_duplicate(self):
        rows=[(2,payment(),None),(3,payment(),None)]
        ft=StubFT04(rows)
        def parser(data):
            if data==b"all":
                return {"source_rows":2,"valid_rows":1,"review_rows":1,
                        "valid_credit_total":"10.00"}
            return {"source_rows":1,"valid_rows":1,"review_rows":0,
                    "valid_credit_total":"10.00","preview":[{
                        "description":"SAME PAYMENT","sol_id":"001505",
                        "credit_amount":"10.00","review_flags":[]} ]}
        return ft,parser

    def test_01_second_duplicate_is_review_not_fictional_credit(self):
        ft,parser=self.setup_duplicate()
        good,bad=classify_exact_ft04_rows(b"all",parser,ft)
        self.assertEqual([r[0] for r in good],[2])
        self.assertEqual(bad,[{"source_row":3,
            "reason":"REPEATED_SOURCE_ROW_REVIEW"}])

    def test_02_exact_parser_credit_consistency(self):
        ft,parser=self.setup_duplicate()
        good,bad=classify_exact_ft04_rows(b"all",parser,ft)
        self.assertEqual(sum(x[2] for x in good),1000)
        self.assertEqual(len(good)+len(bad),2)

    def test_03_duplicate_full_book_ineligible_not_global_stop(self):
        ft,parser=self.setup_duplicate()
        ft.rows += [(4,payment(desc="INDEPENDENT",amt="20.00"),None)]
        def original(data):
            if data==b"all":
                return {"source_rows":3,"valid_rows":2,"review_rows":1,
                        "valid_credit_total":"30.00"}
            rowno=int(data.decode().split(":")[-1])
            amount="20.00" if rowno==4 else "10.00"
            return {"source_rows":1,"valid_rows":1,"review_rows":0,
                    "valid_credit_total":amount,"preview":[{
                        "description":"INDEPENDENT" if rowno==4 else "SAME PAYMENT",
                        "sol_id":"001505","credit_amount":amount,
                        "review_flags":[]} ]}
        good,bad=classify_exact_ft04_rows(b"all",original,ft)
        self.assertEqual([x[0] for x in good],[2,4])
        self.assertEqual(bad[0]["source_row"],3)

    def test_04_fast_path_without_review_avoids_reparse(self):
        ft=StubFT04([(2,payment(),None),
                       (3,payment("OTHER","1505","5.00"),None)])
        def parser(data):
            self.assertEqual(data,b"all")
            return {"source_rows":2,"valid_rows":2,"review_rows":0,
                    "valid_credit_total":"15.00"}
        good,bad=classify_exact_ft04_rows(b"all",parser,ft)
        self.assertEqual(len(good),2)
        self.assertEqual(len(bad),0)
        self.assertEqual(ft.single_calls,0)

    def test_05_fast_path_total_mismatch_blocks(self):
        ft=StubFT04([(2,payment(),None)])
        def parser(data):
            return {"source_rows":1,"valid_rows":1,"review_rows":0,
                    "valid_credit_total":"99.00"}
        with self.assertRaisesRegex(RowParityReviewRequired,
                                    "FULL_SOURCE_ACCEPTED_CREDIT_PARITY_FAILED"):
            classify_exact_ft04_rows(b"all",parser,ft)

    def test_06_invalid_source_requires_matching_source_count(self):
        ft,parser=self.setup_duplicate()
        ft.rows.pop()
        with self.assertRaisesRegex(RowParityReviewRequired,
                                    "FULL_SOURCE_ROW_COUNT_DISAGREES"):
            classify_exact_ft04_rows(b"all",parser,ft)

    def test_07_over_2000_review_rows_fail_closed(self):
        ft=StubFT04([(i+2,payment(str(i)),None) for i in range(2001)])
        def parser(data):
            return {"source_rows":2001,"valid_rows":2000,"review_rows":1,
                    "valid_credit_total":"20000.00"}
        with self.assertRaisesRegex(RowParityReviewRequired,
                                    "INDIVIDUAL_ROW_PARSER_LIMIT"):
            classify_exact_ft04_rows(b"all",parser,ft)

    def test_08_bad_per_row_preview_denied(self):
        ft,parser=self.setup_duplicate()
        def broken(data):
            if data==b"all":return parser(data)
            return {"source_rows":1,"valid_rows":1,"review_rows":0,
                    "valid_credit_total":"10.00","preview":[]}
        with self.assertRaisesRegex(RowParityReviewRequired,
                                    "SINGLE_ROW_NORMALIZATION_UNVERIFIED"):
            classify_exact_ft04_rows(b"all",broken,ft)

    def test_09_full_file_count_mismatch_denied(self):
        ft,parser=self.setup_duplicate()
        def broken(data):
            v=parser(data)
            if data==b"all":v["valid_rows"]=2
            return v
        with self.assertRaisesRegex(RowParityReviewRequired,
                                    "EXACT_DUPLICATE_ROW_PARSER_COUNT_MISMATCH"):
            classify_exact_ft04_rows(b"all",broken,ft)

    def test_10_no_database_or_settlement_side_effect(self):
        ft,parser=self.setup_duplicate()
        p,b=classify_exact_ft04_rows(b"all",parser,ft)
        self.assertFalse(hasattr(ft,"database"))
        self.assertEqual([x["source_row"] for x in b],[3])
        self.assertEqual([x[2] for x in p],[1000])


if __name__=="__main__":
    unittest.main()
