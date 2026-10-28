"""Birim testleri: python3 -m unittest -v

Örnek veriler (config.example.json + transactions.example.csv) için beklenen değerler
elle hesaplanmıştır; açıklamalar her testin içinde.
"""

from __future__ import annotations

import copy
import csv
import json
import logging
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from llc_tax import engine, mercury

ROOT = Path(__file__).resolve().parent.parent
logging.getLogger("pypdf").setLevel(logging.ERROR)


def example_case(year: int | None = None) -> dict:
    """Örnek veriler; year verilirse tüm tarihler o yıla taşınır (kuruluş tarihi hariç)."""
    case = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    with (ROOT / "transactions.example.csv").open(encoding="utf-8-sig", newline="") as f:
        case["transactions"] = list(csv.DictReader(f))
    if year:
        case["tax_year"] = year
        for t in case["transactions"]:
            t["date"] = f"{year}{t['date'][4:]}"
    return case


def computed(case: dict) -> dict:
    errors, txns = engine.validate(case)
    assert not errors, errors
    return engine.compute(case, txns)


class EngineTests(unittest.TestCase):
    def test_example_numbers(self):
        n = computed(example_case())["numbers"]
        # Nakit: 1250 + 2000 - 99 - 10 + 412.37 - 50 + 188.10 - 800 - 5 + 500 - 200 - 600 = 2586.47
        # (Google Play Console 25 USD ortağın kartıyla ödendi -> LLC nakdini etkilemez)
        self.assertEqual(n["total_assets"], 2586)
        # Part V: sermaye 2000 + ortağın ödediği gider 25 + çekim 800+600
        self.assertEqual(n["contributions"], 2000)
        self.assertEqual(n["owner_paid_expenses"], 25)
        self.assertEqual(n["distributions"], 1400)
        self.assertEqual(n["part_v_total"], 3425)
        # Part IV: ortaktan borç 500, geri ödeme 200 -> 17a 0, 17b 300; 22 = 17b
        self.assertEqual((n["line17a"], n["line17b"], n["line22"]), (0, 300, 300))
        self.assertEqual((n["line31b"], n["line32"], n["line36"]), (0, 0, 0))
        # 1f = 22 + 36 + Part V
        self.assertEqual(n["gross_payments"], 300 + 0 + 3425)

    def test_contributions_and_draws_never_in_part_iv(self):
        # Reg. §1.6038A-2(b)(3)(x)-(xi): sermaye/çekim Part IV 21/35'e girmez
        case = example_case()
        case["transactions"] = [t for t in case["transactions"]
                                if t["category"] in ("capital_contribution", "owner_draw")]
        n = computed(case)["numbers"]
        self.assertEqual((n["line22"], n["line36"]), (0, 0))
        self.assertEqual(n["part_v_total"], 3400)
        self.assertEqual(n["gross_payments"], 3400)

    def test_third_party_items_not_reported(self):
        # App Store geliri ve LLC hesabından ödenen giderler 5472'ye girmez
        case = example_case()
        case["transactions"] = [t for t in case["transactions"]
                                if t["category"] in ("revenue", "software_expense") and t["paid_by"] == "llc"]
        n = computed(case)["numbers"]
        self.assertEqual(n["gross_payments"], 0)
        self.assertEqual(n["part_v_total"], 0)

    def test_ending_balance_reconciliation_warning(self):
        case = example_case()
        case["company"]["ending_cash_balance_usd_actual"] = "2586.47"
        self.assertFalse(any("banka bakiyesinden" in w for w in computed(case)["warnings"]))
        case["company"]["ending_cash_balance_usd_actual"] = "3000"
        self.assertTrue(any("banka bakiyesinden" in w for w in computed(case)["warnings"]))

    def assertInvalid(self, case: dict, fragment: str):
        errors, _ = engine.validate(case)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_validation_rules(self):
        base = example_case()
        c = copy.deepcopy(base); c["eligibility"]["owner_not_in_us"] = False
        self.assertInvalid(c, "Uygunluk")
        c = copy.deepcopy(base); c["owner"]["reference_id"] = ""
        self.assertInvalid(c, "Reference ID zorunlu")
        c = copy.deepcopy(base); c["owner"]["reference_id"] = "OWNER-001"
        self.assertInvalid(c, "harf/rakam")
        c = copy.deepcopy(base); c["owner"]["address"]["country"] = "TR"
        self.assertInvalid(c, "kısaltma")
        c = copy.deepcopy(base); c["company"]["ein"] = "123456789"
        self.assertInvalid(c, "EIN formatı")
        c = copy.deepcopy(base); c["transactions"][0]["date"] = "2024-12-31"
        self.assertInvalid(c, "vergi yılı")
        c = copy.deepcopy(base); c["transactions"][0]["paid_by"] = "llc"  # sermaye LLC'den ödenemez
        self.assertInvalid(c, "ödeyen Ortak olmalı")
        c = copy.deepcopy(base); c["transactions"][0]["category"] = ""
        self.assertInvalid(c, "kategori seçilmedi")
        c = copy.deepcopy(base); c["transactions"][0]["amount_usd"] = "-5"
        self.assertInvalid(c, "pozitif")

    def test_loan_requires_part_vii_answers(self):
        case = example_case()
        case["part_vii"] = {"q42a": "", "q42b": ""}
        self.assertTrue(any("42a/42b" in w for w in computed(case)["warnings"]))


class MercuryTests(unittest.TestCase):
    def test_signed_amount_layout(self):
        csv_text = ("Date (UTC),Description,Amount,Status,Bank Description\n"
                    "01-05-2025,Jane Doe,2000.00,Sent,WIRE IN\n"
                    "01-10-2025,Apple Developer,-99.00,Sent,APPLE.COM/BILL\n"
                    "02-15-2025,Apple Inc,412.37,Sent,APPLE PAYMENT\n"
                    "04-01-2025,Jane Doe,-800.00,Sent,TRANSFER\n"
                    "05-01-2025,Vendor,-40.00,Failed,X\n"
                    "06-01-2024,Old,-1.00,Sent,X\n")
        res = mercury.parse(csv_text, "Jane Doe", 2025)
        got = [(t["date"], t["category"], t["paid_by"], t["amount_usd"]) for t in res["transactions"]]
        self.assertEqual(got, [
            ("2025-01-05", "capital_contribution", "owner", "2000.00"),
            ("2025-01-10", "software_expense", "llc", "99.00"),
            ("2025-02-15", "revenue", "llc", "412.37"),
            ("2025-04-01", "owner_draw", "llc", "800.00"),
        ])
        self.assertEqual(len(res["skipped"]), 2)  # Failed + yıl dışı

    def test_split_debit_credit_layout(self):
        csv_text = ("Date,Description,Debit,Credit\n"
                    "2025-01-05,Jane Doe,,\"2,000.00\"\n"
                    "01/10/2025,Github,(10.00),\n")
        res = mercury.parse(csv_text, "Jane Doe", 2025)
        self.assertEqual([(t["direction"], t["amount_usd"]) for t in res["transactions"]],
                         [("in", "2000.00"), ("out", "10.00")])

    def test_unknown_layout_lists_headers(self):
        with self.assertRaisesRegex(ValueError, "Foo, Bar"):
            mercury.parse("Foo,Bar\n1,2\n", "x", 2025)


def pdf_values(path: Path) -> dict:
    """Doldurulmuş PDF'teki alan değerleri: {'f1_8': '12-3456789', 'c1_4': '/1', ...}"""
    from pypdf import PdfReader
    out = {}
    for page in PdfReader(path).pages:
        for a in page.get("/Annots", []) or []:
            a = a.get_object()
            t = str(a.get("/T", ""))
            if a.get("/FT") == "/Btn":
                out[t] = str(a.get("/AS", "/Off"))
            elif a.get("/V") not in (None, ""):
                out[t.split("[")[0]] = str(a.get("/V"))
    return out


class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from llc_tax import pdf_fill
        # forms/f1120.pdf hangi yıla aitse testler o yılla çalışır
        cls.year = y = pdf_fill.form_year(pdf_fill.F1120)
        cls.case = example_case(y)
        cls.result = computed(cls.case)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pdf_fill.generate(cls.case, cls.result, Path(cls.tmp.name))
        cls.dir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_files_generated(self):
        self.assertEqual(self.out["missing"], [])
        y = self.year
        self.assertEqual(self.out["files"], [f"{y}_FAX_PAKETI.pdf", f"{y}_1_pro_forma_1120.pdf",
                                             f"{y}_2_form_5472.pdf", f"{y}_3_part_v_statement.pdf"])

    def test_form_5472_fields(self):
        v = pdf_values(self.dir / f"{self.year}_2_form_5472.pdf")
        expected = {
            "f1_2": str(self.year), "f1_4": str(self.year),          # vergi yılı başlangıç/bitiş
            "f1_5": "EXAMPLE APPS LLC",              # 1a
            "f1_8": "12-3456789",                    # 1b
            "f1_9": "2,586",                         # 1c
            "f1_11": "513210",                       # 1e
            "f1_12": "3,725", "f1_14": "3,725",      # 1f, 1h
            "f1_13": "1",                            # 1g
            "f1_16": "United States",                # 1l
            "f1_17": "03/15/2024",                   # 1m
            "f1_22": "OWNER001", "f1_23": "12345678901",  # 4b(2), 4b(3)
            "f1_25": "Turkey",                       # 4d
            "f2_3": "OWNER001",                      # 8b(2)
            "f2_18": "0", "f2_19": "300",            # 17a, 17b
            "f2_24": "300",                          # 22
            "f2_40": "0",                            # 36
        }
        for field, value in expected.items():
            self.assertEqual(v.get(field), value, field)
        self.assertNotIn("f2_23", v)  # 21: sermaye Part IV'e yazılmaz
        self.assertNotIn("f2_39", v)  # 35: çekim Part IV'e yazılmaz
        checked = {
            "c1_3[0]": "/1",     # 2: >= %50 yabancı
            "c1_4[0]": "/1",     # 3: foreign-owned U.S. DE
            "c2_1[0]": "/1",     # Part III: foreign person
            "c2_4[0]": "/1",     # 8e: 25% foreign shareholder
            "c2_6[0]": "/1",     # Part V
            "c3_1[1]": "/2",     # 37: No
            "c3_7[1]": "/2",     # 42a: No
            "c3_8[1]": "/2",     # 42b: No
        }
        for field, value in checked.items():
            self.assertEqual(v.get(field), value, field)
        self.assertEqual(v.get("c1_2[0]"), "/Off")  # 1j: ilk yıl değil

    def test_pro_forma_1120_fields(self):
        from pypdf import PdfReader
        path = self.dir / f"{self.year}_1_pro_forma_1120.pdf"
        v = pdf_values(path)
        expected = {"f1_4": "EXAMPLE APPS LLC", "f1_5": "123 Example St, Suite 100",
                    "f1_7": "Albuquerque", "f1_8": "NM", "f1_10": "87101",
                    "f1_11": "12-3456789", "f1_12": "03/15/2024", "f1_13": "2,586"}
        for field, value in expected.items():
            self.assertEqual(v.get(field), value, field)
        self.assertEqual(v.get("c1_6[0]"), "/Off")  # E(1) initial return: ilk yıl değil
        self.assertIn("Foreign-owned U.S. DE", PdfReader(path).pages[0].extract_text())
        # 1120 D ile 5472 1c aynı olmalı
        self.assertEqual(v["f1_13"], pdf_values(self.dir / f"{self.year}_2_form_5472.pdf")["f1_9"])

    def test_first_year_checkboxes(self):
        from llc_tax import pdf_fill
        y = self.year
        case = example_case(y)
        case["company"]["first_year_filing_5472"] = True
        with tempfile.TemporaryDirectory() as d:
            pdf_fill.generate(case, computed(case), Path(d))
            self.assertEqual(pdf_values(Path(d) / f"{y}_2_form_5472.pdf")["c1_2[0]"], "/1")
            self.assertEqual(pdf_values(Path(d) / f"{y}_1_pro_forma_1120.pdf")["c1_6[0]"], "/1")

    def test_wrong_year_f1120_refused(self):
        from llc_tax import pdf_fill
        y = self.year - 1
        case = example_case(y)
        with tempfile.TemporaryDirectory() as d:
            out = pdf_fill.generate(case, computed(case), Path(d))
            self.assertTrue(any(f"{self.year} yılına ait" in m for m in out["missing"]))
            self.assertNotIn(f"{y}_FAX_PAKETI.pdf", out["files"])


class ServerTests(unittest.TestCase):
    def test_localhost_only(self):
        from llc_tax.server import serve
        httpd = serve(0)
        port = httpd.server_address[1]
        self.assertEqual(httpd.server_address[0], "127.0.0.1")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta") as r:
                self.assertIn("eligibility", json.loads(r.read()))
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/meta", headers={"Host": "evil.example"})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 403)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
