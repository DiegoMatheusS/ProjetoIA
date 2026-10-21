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



class FakeCatalogBuyBoxScraper(MercadoLivreScraper):
    def __init__(self):
        self.token = "fake"
        self.calls = []
        self.api_debug = []

    def _api_get(self, path, params=None, allow_public_fallback=False):
        self.calls.append(path)
        if path == "/products/MLB72674962":
            return {
                "name": "Mouse sem fio recarregável",
                "pictures": [{"url": "https://example.com/mouse.jpg"}],
                "attributes": [
                    {"id": "BRAND", "name": "Marca", "value_name": "Genérica"},
                    {"id": "MODEL", "name": "Modelo", "value_name": "RGB"},
                ],
                "buy_box_winner": {
                    "item_id": "MLB1234567890",
                    "seller_id": 123,
                },
            }, None
        if path == "/products/MLB72674962/items":
            return {
                "results": [
                    {
                        "item_id": "MLB1234567890",
                        "price": 79.90,
                        "original_price": 99.90,
                        "currency_id": "BRL",
                        "seller_id": 123,
                    },
                    {
                        "item_id": "MLB9999999999",
                        "price": 74.90,
                        "currency_id": "BRL",
                        "seller_id": 999,
                    },
                ]
            }, None
        return None, "unexpected"


def test_catalog_url_without_item_id_uses_only_explicit_buy_box_offer():
    scraper = FakeCatalogBuyBoxScraper()
    raw = scraper.collect(
        "https://www.mercadolivre.com.br/mouse-sem-fio-recarregavel/p/MLB72674962",
        no_browser=True,
    )
    assert raw["catalog_offer_found"] is True
    assert raw["price"] == 79.90
    assert raw["previous_price"] == 99.90
    assert raw["price_source"] == "CATALOG_ITEMS"
    assert raw["seller_id"] == 123
    # Não escolhe simplesmente o menor preço de outro vendedor.
    assert raw["price"] != 74.90
