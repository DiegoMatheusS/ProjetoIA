import unittest
from unittest.mock import patch

from src.shopee.router import _page_details


class ShopeePageDetailsTest(unittest.TestCase):
    def test_collects_description_and_attributes_without_commercial_fields(self):
        raw = {
            "ok": True,
            "source": "NAVEGADOR_GENERICO",
            "title": "PC Gamer Ryzen 5 5600G",
            "description": "Ryzen 5 5600G, 16 GB DDR4 e SSD NVMe 1 TB",
            "brand": "CriaByte",
            "model": "CB-5600G",
            "mpn": None,
            "gtin": None,
            "image_url": "https://example.com/pc.jpg",
            "attributes": [{"name": "Memória", "value_name": "16 GB DDR4"}],
            "attributes_text": "Memória: 16 GB DDR4",
            "product_attributes": [{"name": "Memória", "value_name": "16 GB DDR4"}],
            "selected_variants": [],
            "blocked": False,
            "requires_local_capture": False,
            "error": None,
            "collection_attempts": [],
        }

        with patch("src.shopee.router.GenericScraper.collect", return_value=raw) as collect:
            result = _page_details(
                "https://shopee.com.br/PC-Gamer-i.123.456",
                no_browser=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["descricao"], raw["description"])
        self.assertEqual(result["atributosTexto"], "Memória: 16 GB DDR4")
        self.assertEqual(result["modelo"], "CB-5600G")
        collect.assert_called_once()

    def test_returns_safe_failure_when_page_collection_fails(self):
        with patch(
            "src.shopee.router.GenericScraper.collect",
            side_effect=RuntimeError("bloqueado"),
        ):
            result = _page_details(
                "https://shopee.com.br/PC-Gamer-i.123.456",
                no_browser=True,
            )

        self.assertFalse(result["ok"])
        self.assertIn("bloqueado", result["erro"])


if __name__ == "__main__":
    unittest.main()
