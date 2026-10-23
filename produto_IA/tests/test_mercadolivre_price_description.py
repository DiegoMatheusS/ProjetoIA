import unittest

from src.main import _build_spec_description, build_result
from src.scrapers.mercadolivre_scraper import MercadoLivreScraper


class MercadoLivrePriceAndDescriptionTest(unittest.TestCase):
    def test_pdp_promotional_price_overrides_regular_api_price(self):
        merged = MercadoLivreScraper._merge_raw_sources(
            {
                "title": "AMD Ryzen 7 5700G",
                "price": 998.0,
                "previous_price": None,
                "price_source": "ITEM_LEGACY_PRICE",
                "currency": "BRL",
                "attributes": [],
            },
            {
                "title": "AMD Ryzen 7 5700G",
                "price": 918.0,
                "previous_price": 998.0,
                "price_source": "MERCADO_LIVRE_PDP",
                "currency": "BRL",
                "attributes": [],
            },
            "MERCADO_LIVRE_API_SURFSKY",
        )

        self.assertEqual(merged["price"], 918.0)
        self.assertEqual(merged["previous_price"], 998.0)
        self.assertEqual(merged["price_source"], "MERCADO_LIVRE_PDP")

    def test_offer_contract_corrects_reversed_current_and_previous_price(self):
        result = build_result(
            {
                "title": "Produto teste",
                "brand": "Marca",
                "model": "Modelo",
                "price": 998.0,
                "previous_price": 918.0,
                "price_source": "TEST",
                "url_original": "https://example.com/produto",
                "attributes": [],
                "product_attributes": [],
            },
            "CELULAR",
        )

        self.assertEqual(result["ofertaColetada"]["preco"], 918.0)
        self.assertEqual(result["ofertaColetada"]["precoAnterior"], 998.0)

    def test_description_is_concatenated_from_specs_not_raw_page_text(self):
        raw = {
            "brand": "AMD",
            "model": "Ryzen 7 5700G",
            "description": "TEXTO BRUTO DA PAGINA " * 100,
            "product_attributes": [],
        }
        description = _build_spec_description(
            raw,
            {
                "socket": "AM4",
                "nucleos": 8,
                "threads": 16,
                "clockBaseGhz": 3.8,
                "clockBoostGhz": 4.6,
                "tdpWatts": 65,
            },
        )

        self.assertIn("Marca: AMD", description)
        self.assertIn("Modelo: Ryzen 7 5700G", description)
        self.assertIn("Socket: AM4", description)
        self.assertIn("Núcleos: 8", description)
        self.assertIn("Threads: 16", description)
        self.assertIn("Clock base: 3.8 GHz", description)
        self.assertIn("TDP: 65 W", description)
        self.assertNotIn("TEXTO BRUTO", description)
        self.assertLessEqual(len(description), 1200)


if __name__ == "__main__":
    unittest.main()
