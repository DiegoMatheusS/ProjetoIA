import unittest

from src.main import build_result
from src.scrapers.magazine_scraper import MagazineScraper


DIRECT_URL = (
    "https://www.magazineluiza.com.br/"
    "smartphone-motorola-moto-g35-256gb-coral-5g-4gb-ram-8gb-ram-boost-5g-67-cam-dupla-selfie-16mp/"
    "p/238760800/te/mg35/"
)


class MagaluBlockedFallbackTest(unittest.TestCase):
    def test_direct_magalu_generates_mobile_and_clean_variants(self):
        candidates = MagazineScraper._magazineluiza_candidate_urls(DIRECT_URL)
        urls = {mode: url for mode, url in candidates}
        self.assertIn("MAGAZINELUIZA_MOBILE", urls)
        self.assertTrue(urls["MAGAZINELUIZA_MOBILE"].startswith("https://m.magazineluiza.com.br/"))

    def test_blocked_magalu_uses_product_slug_only_as_category_hint(self):
        result = build_result({
            "ok": False,
            "blocked": True,
            "source": "MAGALU_BLOQUEADO",
            "url_original": DIRECT_URL,
            "url_final": DIRECT_URL,
            "error": "MAGALU_COLETA_BLOQUEADA",
        })

        self.assertEqual(result["categoriaDetectada"], "CELULAR")
        self.assertEqual(result["categoriaSlugSugerida"], "celulares")
        self.assertIsNone(result["payloadParcialBackend"]["nome"])
        self.assertEqual(result["erro"], "MAGALU_COLETA_BLOQUEADA")

    def test_unrelated_blocked_url_does_not_invent_category(self):
        result = build_result({
            "ok": False,
            "blocked": True,
            "source": "MAGALU_BLOQUEADO",
            "url_original": "https://www.magazineluiza.com.br/produto-especial/p/123456/xx/yy/",
            "error": "MAGALU_COLETA_BLOQUEADA",
        })
        self.assertIsNone(result["categoriaDetectada"])


if __name__ == "__main__":
    unittest.main()
