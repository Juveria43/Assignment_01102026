import unittest
from types import SimpleNamespace

from src.etl_pipeline import row_hash


class ProductChangeHashTests(unittest.TestCase):
    def setUp(self):
        self.row = SimpleNamespace(
            customer_id="C001", product_id="P01", product_name="Laptop",
            product_category="Electronics", quantity=2, unit_price=999.99,
            discount=0.05, transaction_date="2023-01-15 10:30:00", region="North")

    def test_hash_is_stable_for_same_business_values(self):
        self.assertEqual(row_hash(self.row), row_hash(self.row))

    def test_product_name_change_changes_hash(self):
        changed = SimpleNamespace(**{**vars(self.row), "product_name": "Portable Computer"})
        self.assertNotEqual(row_hash(self.row), row_hash(changed))

    def test_product_category_change_changes_hash(self):
        changed = SimpleNamespace(**{**vars(self.row), "product_category": "Computing"})
        self.assertNotEqual(row_hash(self.row), row_hash(changed))


if __name__ == "__main__":
    unittest.main()
