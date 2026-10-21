import json

from src.scrapers.generic_scraper import GenericScraper


def parse(html):
    return GenericScraper()._parse_html('https://shop.example/p', 'https://shop.example/p', html)


def test_graph_references_across_scripts_and_cycles():
    product = {'@type': 'https://schema.org/Product', 'name': 'SSD ABC 1TB',
               'brand': {'@id': '#brand'}, 'offers': {'@id': '#offer'},
               'image': {'@id': '#image'}, 'additionalProperty': {'@id': '#spec'}}
    graph = {'@graph': [
        {'@id': '#brand', '@type': 'Brand', 'name': 'ABC', 'subjectOf': {'@id': '#brand'}},
        {'@id': '#offer', '@type': 'Offer', 'priceSpecification': {'price': '399.90'},
         'availability': 'https://schema.org/InStock'},
        {'@id': '#image', '@type': 'ImageObject', 'url': '/ssd.jpg'},
        {'@id': '#spec', '@type': 'PropertyValue', 'name': 'Capacidade', 'value': '1 TB'}]}
    raw = parse(f'<script type="application/ld+json">{json.dumps(product)}</script>'
                f'<script type="application/ld+json">{json.dumps(graph)}</script>')
    assert raw['brand'] == 'ABC'
    assert raw['price'] == 399.90
    assert raw['price_source'] == 'JSON_LD'
    assert raw['image_url'] == 'https://shop.example/ssd.jpg'
    assert raw['available'] is True
    assert raw['attributes'][0]['value_name'] == '1 TB'


def test_microdata_nested_offer_brand_and_specs():
    raw = parse('''<article itemscope itemtype="https://schema.org/Product">
      <meta itemprop="name" content="Notebook ABC 16GB">
      <div itemprop="brand" itemscope itemtype="https://schema.org/Brand">
        <meta itemprop="name" content="ABC"></div>
      <meta itemprop="model" content="N16"><meta itemprop="gtin13" content="1234567890123">
      <div itemprop="description">Notebook com 16 GB de RAM e SSD de 512 GB.</div>
      <link itemprop="image" href="/notebook.jpg">
      <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
        <meta itemprop="price" content="2999.90"><meta itemprop="priceCurrency" content="BRL">
        <link itemprop="availability" href="https://schema.org/OutOfStock"></div>
      <div itemprop="additionalProperty" itemscope itemtype="https://schema.org/PropertyValue">
        <meta itemprop="name" content="Memória"><meta itemprop="value" content="16 GB"></div>
    </article>''')
    assert raw['title'] == 'Notebook ABC 16GB'
    assert raw['brand'] == 'ABC'
    assert raw['model'] == 'N16'
    assert raw['gtin'] == '1234567890123'
    assert raw['price'] == 2999.90
    assert raw['price_source'] == 'MICRODATA'
    assert raw['available'] is False
    assert raw['image_url'] == 'https://shop.example/notebook.jpg'
    assert '512 GB' in raw['description']
    assert raw['attributes'][0]['value_name'] == '16 GB'


def test_duplicate_graph_product_is_not_ambiguous():
    product = {'@id': '#p', '@type': 'Product', 'name': 'Monitor ABC'}
    raw = parse(f'<script type="application/ld+json">{json.dumps([product, product])}</script>')
    assert raw['title'] == 'Monitor ABC'


def test_multiple_products_do_not_mix_structured_details():
    raw = parse('''<h1>Escolha seu produto</h1>
      <div itemscope itemtype="https://schema.org/Product"><meta itemprop="brand" content="ABC"></div>
      <div itemscope itemtype="https://schema.org/Product"><meta itemprop="brand" content="XYZ"></div>''')
    assert raw['brand'] is None


def test_zero_price_and_meta_price_provenance():
    raw = parse('<script type="application/ld+json">{"@type":"Product","name":"Brinde",'
                '"offers":{"price":0}}</script><meta property="product:price:amount" content="999">')
    assert raw['price'] == 0
    assert raw['price_source'] == 'JSON_LD'
    raw = parse('<h1>Monitor</h1><meta property="product:price:amount" content="799.90">')
    assert raw['price'] == 799.90
    assert raw['price_source'] == 'META'


def test_webpage_main_entity_reference_and_other_graph_product():
    graph = {'@graph': [
        {'@type': 'WebPage', 'mainEntity': {'@id': '#main'}},
        {'@id': '#main', '@type': 'Product', 'name': 'SSD ABC', 'url': 'https://shop.example/p'},
        {'@type': 'Product', 'name': 'SSD XYZ', 'url': 'https://shop.example/other'}]}
    raw = parse('<link rel="canonical" href="https://shop.example/p">'
                f'<script type="application/ld+json">{json.dumps(graph)}</script>')
    assert raw['title'] == 'SSD ABC'


def test_invalid_json_does_not_prevent_microdata_fallback():
    raw = parse('''<script type="application/ld+json">{broken}</script>
      <div itemscope itemtype="https://schema.org/Product">
      <meta itemprop="name" content="SSD ABC"><meta itemprop="mpn" content="ABC-1"></div>''')
    assert raw['title'] == 'SSD ABC'
    assert raw['mpn'] == 'ABC-1'
