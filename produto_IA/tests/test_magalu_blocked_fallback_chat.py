import unittest

from src.main import _category_hint_from_product_url
from src.scrapers.magazine_scraper import MagazineScraper


class MagaluBlockedFallbackTest(unittest.TestCase):
    def test_direct_magazineluiza_url_gets_public_variants(self):
        url = (
            "https://www.magazineluiza.com.br/"
            "smartphone-motorola-moto-g35-256gb-coral-5g-4gb-ram/"
            "p/238760800/te/mg35/?seller_id=magalu"
        )
        candidates = MagazineScraper._magazineluiza_candidate_urls(url)
        urls = [candidate for _, candidate in candidates]

        self.assertTrue(any(item.startswith("https://m.magazineluiza.com.br/") for item in urls))
        self.assertTrue(any("seller_id=" not in item for item in urls))

    def test_blocked_smartphone_url_still_has_safe_category_hint(self):
        url = (
            "https://www.magazineluiza.com.br/"
            "smartphone-motorola-moto-g35-256gb-coral-5g-4gb-ram-8gb-ram-boost-5g/"
            "p/238760800/te/mg35/"
        )
        self.assertEqual(_category_hint_from_product_url(url), "CELULAR")


if __name__ == "__main__":
    unittest.main()
