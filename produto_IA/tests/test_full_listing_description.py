import pytest

from src.main import build_result
from src.scrapers.generic_scraper import GenericScraper
from src.scrapers.listing_description import description_text
from src.technical_ai.auto import auto_enrich_link_result


@pytest.mark.parametrize('category', ['PROCESSADOR', 'NOTEBOOK', 'PC_MONTADO', 'MONITOR', 'WEBCAM'])
def test_original_listing_survives_normalization_for_every_destination(category):
    description = ('Descrição original do vendedor, com acessórios e garantia.\n\n' * 250).strip()
    result = build_result({'title': 'Produto', 'description': description,
                          'url_original': 'https://shopee.com.br/product/123/456'}, category)
    assert len(description) > 12000
    assert result['payloadParcialBackend']['descricao'] == description
    assert result['descricaoAnuncio'] == description


def test_no_description_is_not_replaced_by_a_technical_summary():
    result = build_result({'title': 'Ryzen 5 5600G', 'brand': 'AMD'}, 'PROCESSADOR')
    assert result['payloadParcialBackend']['descricao'] is None


def test_blocked_page_does_not_become_listing_text():
    result = build_result({'blocked': True, 'description': 'Verifique se você é humano'}, 'PROCESSADOR')
    assert result['payloadParcialBackend']['descricao'] is None


def test_html_preserves_blocks_and_inline_words_without_executable_content():
    text = description_text('<p>Processador <b>Ryzen</b> 5</p><ul><li>16 GB RAM</li><li>SSD 1 TB</li></ul><script>alert(1)</script>')
    assert text == 'Processador Ryzen 5\n\n16 GB RAM\n\nSSD 1 TB'


def test_shopee_full_description_overrides_short_meta_and_ignores_recommendations():
    description = '<p>Conteúdo completo do anúncio. Garantia e acessórios incluídos.</p>' * 250
    html = f'<h1>PC Gamer</h1><meta name="description" content="Compre PC"><div class="shopee-product-detail__description">{description}</div><aside><div id="description">OUTRO PRODUTO</div></aside>'
    url = 'https://shopee.com.br/product/123/456'
    raw = GenericScraper()._parse_html(url, url, html)
    assert len(raw['description']) > 12000
    assert raw['description_source'] == 'PAGINA'
    assert 'OUTRO PRODUTO' not in raw['description']
    assert build_result(raw, 'PC_MONTADO')['payloadParcialBackend']['descricao'] == raw['description']


def test_amazon_keeps_bullets_description_and_aplus_without_nested_duplicates():
    html = '<h1>Produto</h1><div id="feature-bullets"><ul><li>Característica importante</li></ul></div><div id="productDescription"><p>Texto do vendedor</p></div><div id="aplus"><div itemprop="description">Detalhes do fabricante</div></div>'
    raw = GenericScraper()._parse_html('https://amazon.com.br/dp/B012345678', 'https://amazon.com.br/dp/B012345678', html)
    assert 'Característica importante' in raw['description']
    assert 'Texto do vendedor' in raw['description']
    assert raw['description'].count('Detalhes do fabricante') == 1


def test_technical_ai_cannot_overwrite_seller_description(monkeypatch):
    monkeypatch.setattr('src.technical_ai.auto.maybe_auto_enrich_hardware', lambda **kwargs: {
        'utilizado': True, 'payload': {**kwargs['payload'], 'descricao': 'Resumo inventado'},
    })
    result = build_result({'title': 'Ryzen 5 5600G', 'description': 'Texto original\n\nGarantia do vendedor'}, 'PROCESSADOR')
    enriched = auto_enrich_link_result(result)
    assert enriched['payloadParcialBackend']['descricao'] == 'Texto original\n\nGarantia do vendedor'
