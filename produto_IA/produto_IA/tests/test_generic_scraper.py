from src.scrapers.generic_scraper import GenericScraper
from src.main import build_result


def test_generic_jsonld_and_table_specs():
    html = '''
    <html><head>
      <script type="application/ld+json">{
        "@context":"https://schema.org","@type":"Product",
        "name":"Memória RAM DDR5 16GB 6000MHz",
        "brand":{"@type":"Brand","name":"Kingston"},
        "model":"KF560C36",
        "mpn":"KF560C36BBE-16",
        "image":"https://example.com/memoria.jpg",
        "offers":{"@type":"Offer","price":"499.90","priceCurrency":"BRL","availability":"https://schema.org/InStock"}
      }</script>
    </head><body>
      <table><tr><th>Formato</th><td>DIMM</td></tr><tr><th>Latência CL</th><td>36</td></tr></table>
    </body></html>
    '''
    raw = GenericScraper()._parse_html(
        'https://example.com/produto', 'https://example.com/produto', html
    )
    result = build_result(raw)
    assert raw['brand'] == 'Kingston'
    assert raw['price'] == 499.90
    assert raw['available'] is True
    assert result['categoriaDetectada'] == 'MEMORIA_RAM'
    assert result['categoriaSlugSugerida'] == 'memorias-ram'
    assert result['payloadParcialBackend']['mpn'] == 'KF560C36BBE-16'


def test_generic_product_without_backend_spec_does_not_inject_unknown_fields():
    raw = {
        'title': 'Webcam Full HD 60 fps USB com microfone',
        'brand': 'Teste', 'model': 'W1', 'description': None,
        'attributes': [], 'attributes_text': '', 'image_url': None,
        'price': 100, 'previous_price': None, 'currency': 'BRL',
        'available': True, 'url_original': 'https://example.com/webcam',
        'url_final': 'https://example.com/webcam', 'seller_id': None,
        'source': 'HTTP_GENERICO', 'api_used': False, 'error': None,
    }
    result = build_result(raw)
    assert result['categoriaDetectada'] == 'WEBCAM'
    assert result['tipoCadastro'] == 'PRODUTO'
    assert result['categoriaSlugSugerida'] == 'webcams'
    assert 'especificacaoWebcam' not in result['payloadParcialBackend']
    assert result['especificacoesEncontradas']['fps'] == 60
