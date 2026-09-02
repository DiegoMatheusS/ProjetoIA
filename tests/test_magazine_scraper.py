from src.main import build_result
from src.scrapers.magazine_scraper import MagazineScraper


MAGALU_URL = (
    "https://www.magazineluiza.com.br/processador-amd-ryzen-5-7600-5-1ghz-max-turbo-"
    "cache-38mb-am5-6-nucleos-video-integrado-100-100001015box/p/jhk3d95a72/in/prsd/"
    "?seller_id=kabum"
)


def test_magazine_url_detection_and_ids():
    assert MagazineScraper.is_magazine(MAGALU_URL)
    assert MagazineScraper.is_magazine("https://www.magazinevoce.com.br/loja/produto/p/abc123/")
    assert MagazineScraper.product_code_from_url(MAGALU_URL) == "jhk3d95a72"
    assert MagazineScraper.seller_slug_from_url(MAGALU_URL) == "kabum"


def test_magazine_product_page_parser():
    html = r'''
    <html><head>
      <meta property="og:title" content="Processador AMD Ryzen 5 7600, 5.1GHz Max Turbo, AM5">
      <meta property="og:image" content="https://a-static.mlcdn.com.br/ryzen.jpg">
      <script type="application/ld+json">{
        "@context":"https://schema.org",
        "@type":"Product",
        "name":"Processador AMD Ryzen 5 7600, 5.1GHz Max Turbo, AM5",
        "brand":{"@type":"Brand","name":"AMD"},
        "model":"Ryzen 5 7600",
        "mpn":"100-100001015BOX",
        "image":"https://a-static.mlcdn.com.br/ryzen.jpg",
        "offers":{"@type":"Offer","price":"1294.10","priceCurrency":"BRL","availability":"https://schema.org/InStock"}
      }</script>
      <script id="__NEXT_DATA__" type="application/json">{
        "props":{"pageProps":{"product":{"technicalSpecifications":[
          {"name":"Socket","value":"AM5"},
          {"name":"Número de núcleos","value":"6"},
          {"name":"Número de threads","value":"12"},
          {"name":"Tipo de memória RAM","value":"DDR5"}
        ]}}}
      }</script>
    </head><body>
      <h1>Processador AMD Ryzen 5 7600, 5.1GHz Max Turbo, AM5</h1>
      <div>Vendido por KaBuM! e entregue por Magalu</div>
      <div>Preço R$ 1.268,22 R$ 1.268,22 no Pix</div>
      <button>Adicionar à sacola</button>
      <section>
        <h2>Descrição e ficha técnica</h2>
        Processador AMD Ryzen 5 7600 - Socket: AM5 - Nº de núcleos de CPU: 6 -
        Nº de threads: 12 - Clock básico: 3.8GHz - Clock de Max Boost: Até 5.1GHz -
        Cache L2 total: 6 MB - Cache L3 total: 32 MB - TDP: 65W - Memória DDR5 -
        Velocidade máxima: 5200 MHz - Modelo Gráfico: AMD Radeon.
      </section>
      <h2>Avaliações</h2>
    </body></html>
    '''
    scraper = MagazineScraper()
    raw = scraper._parse_magazine_html(MAGALU_URL, MAGALU_URL, html)
    assert raw["source"] == "MAGALU_PAGINA"
    assert raw["price"] == 1268.22
    assert raw["price_source"] == "MAGALU_PIX"
    assert raw["available"] is True
    assert "seller_name" not in raw
    assert "seller_slug" not in raw
    assert raw["marketplace_product_code"] == "jhk3d95a72"
    assert any(a["name"] == "Socket" and a["value_name"] == "AM5" for a in raw["attributes"])

    result = build_result(raw)
    assert result["categoriaDetectada"] == "PROCESSADOR"
    assert result["origemColeta"]["plataforma"] == "MAGALU"
    assert result["origemColeta"]["modoIntegracao"] == "EXTRATOR_ESPECIFICO"
    assert result["ofertaColetada"]["preco"] == 1268.22
    assert "vendedorMarketplace" not in result["ofertaColetada"]
    assert "vendedorMarketplaceSlug" not in result["ofertaColetada"]
    assert "vendedorId" not in result["ofertaColetada"]
    specs = result["payloadParcialBackend"]["especificacaoProcessador"]
    assert specs["socket"] == "AM5"
    assert specs["nucleos"] == 6
    assert specs["threads"] == 12
    assert specs["frequenciaBaseMhz"] == 3800
    assert specs["frequenciaTurboMhz"] == 5100
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]


def test_magazine_does_not_use_installment_total_as_previous_price():
    html = r'''
    <html><head>
      <script type="application/ld+json">{
        "@context":"https://schema.org","@type":"Product","name":"Teclado mecânico USB RGB",
        "offers":{"@type":"Offer","price":"399.90","priceCurrency":"BRL"}
      }</script>
    </head><body>
      <h1>Teclado mecânico USB RGB</h1>
      <div>Preço R$ 349,90 R$ 349,90 no Pix</div>
      <div>Ou R$ 399,90 em 10x de R$ 39,99 sem juros</div>
      <button>Adicionar à sacola</button>
    </body></html>
    '''
    raw = MagazineScraper()._parse_magazine_html(MAGALU_URL, MAGALU_URL, html)
    assert raw["price"] == 349.90
    assert raw["previous_price"] is None


def test_magazine_rejects_browser_error_page():
    scraper = MagazineScraper()
    assert scraper._is_access_error_page(
        "Não é possível acessar a página",
        "ERR_CONNECTION_RESET",
    ) is True


def test_magazine_local_capture_parser():
    html = r'''
    <html><head>
      <script type="application/ld+json">{
        "@context":"https://schema.org",
        "@type":"Product",
        "name":"Processador AMD Ryzen 5 7600, AM5",
        "brand":{"@type":"Brand","name":"AMD"},
        "model":"Ryzen 5 7600",
        "mpn":"100-100001015BOX",
        "image":"https://a-static.mlcdn.com.br/ryzen.jpg",
        "offers":{"@type":"Offer","price":"1299.90","priceCurrency":"BRL","availability":"https://schema.org/InStock"}
      }</script>
    </head><body>
      <h1>Processador AMD Ryzen 5 7600, AM5</h1>
      <div>Vendido por KaBuM! e entregue por Magalu</div>
      <div>R$ 1.249,90 no Pix</div>
      <button>Adicionar à sacola</button>
      <h2>Descrição e ficha técnica</h2>
      <div>Socket: AM5</div>
      <div>Número de núcleos: 6</div>
      <div>Número de threads: 12</div>
      <div>Tipo de memória RAM: DDR5</div>
    </body></html>
    '''
    capture = {
        "original_url": MAGALU_URL,
        "final_url": MAGALU_URL,
        "title": "Processador AMD Ryzen 5 7600, AM5",
        "html": html,
        "text": "Processador AMD Ryzen 5 7600 AM5 Vendido por KaBuM! R$ 1.249,90 no Pix Adicionar à sacola",
        "blocked": False,
        "error": None,
    }
    raw = MagazineScraper().collect_from_local_capture(MAGALU_URL, capture)
    assert raw["ok"] is True
    assert raw["source"] == "MAGALU_NAVEGADOR_LOCAL"
    assert raw["local_capture"] is True
    assert raw["price"] == 1249.90
    assert "seller_name" not in raw

    result = build_result(raw)
    assert result["origemColeta"]["capturaLocal"] is True
    assert result["politicaColeta"]["capturaLocalImportada"] is True
    assert result["categoriaDetectada"] == "PROCESSADOR"


def test_magazine_local_capture_rejects_blocked_page():
    capture = {
        "original_url": MAGALU_URL,
        "final_url": MAGALU_URL,
        "title": "Não é possível acessar a página",
        "html": "<html><body>ERR_CONNECTION_RESET</body></html>",
        "text": "Não é possível acessar a página ERR_CONNECTION_RESET",
        "blocked": True,
        "error": "CAPTURA_LOCAL_SEM_ACESSO_A_PAGINA",
    }
    raw = MagazineScraper().collect_from_local_capture(MAGALU_URL, capture)
    assert raw["ok"] is False
    assert raw["blocked"] is True
    assert raw["error"] == "CAPTURA_LOCAL_SEM_ACESSO_A_PAGINA"


def test_magazine_keeps_only_product_information_and_best_image():
    html = r'''<html><head>
      <meta property="og:title" content="Processador AMD Ryzen 7 7800X3D, AM5, 8 Núcleos - 100-100000910WOF">
      <meta property="og:image" content="https://a-static.mlcdn.com.br/470x352/produto/kabum/1/foto.jpeg">
      <link rel="preload" as="image" href="https://a-static.mlcdn.com.br/1500x1500/produto/kabum/1/foto.jpeg">
      <script type="application/ld+json">{
        "@type":"Product","name":"Processador AMD Ryzen 7 7800X3D, AM5, 8 Núcleos - 100-100000910WOF",
        "brand":{"name":"AMD"}
      }</script>
      <script id="__NEXT_DATA__" type="application/json">{
        "props":{"pageProps":{"product":{"technicalSpecifications":[
          {"name":"Marca","value":"AMD"},
          {"name":"Modelo","value":"100-100000910WOF"},
          {"name":"Número do Processador","value":"7800X3D"},
          {"name":"Tipo de Memória","value":"DDR5"},
          {"name":"Garantia","value":"3 Anos"},
          {"name":"Cor","value":"Preto"},
          {"name":"Vendido por","value":"KaBuM!"},
          {"name":"Frete","value":"Grátis"}
        ]}}}
      }</script>
    </head><body>
      <h1>Processador AMD Ryzen 7 7800X3D, AM5, 8 Núcleos - 100-100000910WOF</h1>
      <div>Vendido por KaBuM! e entregue por Magalu</div>
      <div>R$ 2.163,75 no Pix</div><button>COMPRAR AGORA</button>
    </body></html>'''
    raw = MagazineScraper()._parse_magazine_html(MAGALU_URL, MAGALU_URL, html)
    assert raw["image_url"] == "https://a-static.mlcdn.com.br/1500x1500/produto/kabum/1/foto.jpeg"
    assert raw["model"] == "7800X3D"
    assert raw["mpn"] == "100-100000910WOF"
    assert "seller_name" not in raw
    names = {row["nome"] for row in raw["product_attributes"]}
    assert "Marca" in names
    assert "Garantia" in names
    assert "Cor" in names
    assert "Vendido por" not in names
    assert "Frete" not in names
    result = build_result(raw)
    assert "vendedorMarketplace" not in result["ofertaColetada"]
    assert any(x["nome"] == "Garantia" for x in result["informacoesProdutoEncontradas"])
