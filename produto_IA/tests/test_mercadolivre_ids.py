from src.scrapers.mercadolivre_scraper import MercadoLivreScraper


def test_catalog_and_item_ids():
    url = (
        "https://www.mercadolivre.com.br/processador-amd/p/MLB21728506"
        "?pdp_filters=item_id:MLB6740306774"
    )
    ids = MercadoLivreScraper.extract_ids(url)
    assert ids["catalog_product_id"] == "MLB21728506"
    assert ids["item_id"] == "MLB6740306774"


def test_direct_item_url():
    url = "https://produto.mercadolivre.com.br/MLB-6740306774-produto-_JM"
    ids = MercadoLivreScraper.extract_ids(url)
    assert ids["item_id"] == "MLB6740306774"
