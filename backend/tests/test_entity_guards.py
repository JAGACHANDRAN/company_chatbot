import unittest
from app.utils.normalization import is_company_match, normalize_company_name


class TestEntityGuards(unittest.TestCase):

    def test_multi_word_exact_and_extended_matches(self):
        # Multi-word query 'delphi tvs' MUST match Delphi TVS variants
        self.assertTrue(is_company_match("delphi tvs", "Delphi TVS"))
        self.assertTrue(is_company_match("delphi tvs", "Delphi TVS Pvt Ltd"))
        self.assertTrue(is_company_match("delphi tvs", "Delphi TVS Private Limited"))
        self.assertTrue(is_company_match("delphi tvs", "Delphi-TVS Diesel Systems"))
        self.assertTrue(is_company_match("delphi tvs", "DELPHI TVS DIESEL SYSTEMS LIMITED"))

    def test_multi_word_rejects_standalone_partial_entities(self):
        # Multi-word query 'delphi tvs' MUST NOT match standalone 'tvs' companies or 'delphi' alone
        self.assertFalse(is_company_match("delphi tvs", "TVS"))
        self.assertFalse(is_company_match("delphi tvs", "TVS Motors"))
        self.assertFalse(is_company_match("delphi tvs", "TVS Motor Company"))
        self.assertFalse(is_company_match("delphi tvs", "TVS Motor Company Ltd"))
        self.assertFalse(is_company_match("delphi tvs", "TVS Group"))
        self.assertFalse(is_company_match("delphi tvs", "TVS Supply Chain"))
        self.assertFalse(is_company_match("delphi tvs", "Lucas TVS"))
        self.assertFalse(is_company_match("delphi tvs", "Lucas TVS Limited"))
        self.assertFalse(is_company_match("delphi tvs", "Delphi Automotive"))
        self.assertFalse(is_company_match("delphi tvs", "Delphi"))

    def test_single_word_broad_matching(self):
        # Single-word query 'tvs' matches all TVS family companies
        self.assertTrue(is_company_match("tvs", "TVS"))
        self.assertTrue(is_company_match("tvs", "TVS Motors"))
        self.assertTrue(is_company_match("tvs", "TVS Motor Company"))
        self.assertTrue(is_company_match("tvs", "Delphi TVS"))
        self.assertTrue(is_company_match("tvs", "Lucas TVS"))

    def test_ashok_leyland_guards(self):
        self.assertTrue(is_company_match("ashok leyland", "Ashok Leyland Ltd"))
        self.assertTrue(is_company_match("ashok leyland", "Ashok Leyland Limited"))
        self.assertFalse(is_company_match("ashok leyland", "Leyland"))
        self.assertFalse(is_company_match("ashok leyland", "Ashok Motors"))
        self.assertFalse(is_company_match("ashok leyland", "Ashok Enterprises"))

    def test_tata_motors_guards(self):
        self.assertTrue(is_company_match("tata motors", "Tata Motors"))
        self.assertTrue(is_company_match("tata motors", "Tata Motors Limited"))
        self.assertFalse(is_company_match("tata motors", "Tata Steel"))
        self.assertFalse(is_company_match("tata motors", "Tata Consultancy Services"))
        self.assertFalse(is_company_match("tata motors", "General Motors"))


if __name__ == "__main__":
    unittest.main()
