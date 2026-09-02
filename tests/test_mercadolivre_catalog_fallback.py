from src.scrapers.mercadolivre_scraper import MercadoLivreScraper


class FakeMercadoLivreScraper(MercadoLivreScraper):
    def __init__(self):
        self.token = "fake"
        self.calls = []
        self.api_debug = []

    def _api_get(self, path, params=None, allow_public_fallback=False):
        self.calls.append(path)
        if path.startswith("/items/"):
            return None, f"{path} -> HTTP 403: forbidden"
        if path == "/products/MLB21728506":
            return {
                "name": "AMD Ryzen 5 7600",
                "short_description": {"content": "Socket: AM5 Memória - DDR5"},
                "pictures": [{"url": "https://example.com/cpu.jpg"}],
                "attributes": [
                    {"id": "BRAND", "name": "Marca", "value_name": "AMD"},
                    {"id": "MODEL", "name": "Modelo", "value_name": "7600"},
                ],
            }, None
        if path == "/products/MLB21728506/items":
            return {
                "results": [{
                    "item_id": "MLB6740306774",
                    "price": 1318.0,
                    "original_price": 1658.51,
                    "currency_id": "BRL",
                    "seller_id": 101939943,
                }]
            }, None
        return None, "unexpected"


def test_catalog_offer_is_used_without_hammering_restricted_price_endpoints(monkeypatch):
    monkeypatch.setenv("ML_TRY_RESTRICTED_PRICE_ENDPOINTS", "false")
    scraper = FakeMercadoLivreScraper()
    url = (
        "https://www.mercadolivre.com.br/processador/p/MLB21728506"
        "?pdp_filters=item_id:MLB6740306774"
    )
    raw = scraper.collect(url, no_browser=True)
    assert raw["catalog_offer_found"] is True
    assert raw["price"] == 1318.0
    assert raw["previous_price"] == 1658.51
    assert raw["price_source"] == "CATALOG_ITEMS"
    assert raw["seller_id"] == 101939943
    assert raw["available"] is True
    assert "/items/MLB6740306774/sale_price" not in scraper.calls
    assert "/items/MLB6740306774/prices" not in scraper.calls
