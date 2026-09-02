from src.discovery.sources import DiscoverySourceCatalog, DEFAULT_SOURCES_BY_CATEGORY
from src.scrapers.generic_scraper import GenericScraper


class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, html, final_url):
        self.html = html
        self.final_url = final_url
        self.headers = {}
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        return FakeResponse(self.html, self.final_url, 200)


def test_v14_17_cpu_monkey_uses_family_catalog_not_search_page():
    html = '''
    <html><body>
      <table>
        <tr><td><a href="/en/cpu-intel_core_i5_14600k">Intel Core i5-14600K</a></td><td>14C 20T @ 3.50 GHz</td></tr>
        <tr><td><a href="/en/cpu-intel_core_i5_14500">Intel Core i5-14500</a></td><td>14C 20T @ 2.60 GHz</td></tr>
      </table>
    </body></html>
    '''
    session = FakeSession(html, "https://www.cpu-monkey.com/en/cpu_family-intel_core_i5")
    catalog = DiscoverySourceCatalog(session=session)
    catalog.rate_limiter.wait = lambda *_: None
    items, error = catalog._cpu_monkey(marca="Intel", consulta="Core i5", limit=10)
    assert error is None
    assert session.requested == ["https://www.cpu-monkey.com/en/cpu_family-intel_core_i5"]
    assert [x.nome for x in items] == ["Intel Core i5-14600K", "Intel Core i5-14500"]


def test_v14_17_cpu_monkey_specific_old_intel_model_uses_generation_page():
    pages = DiscoverySourceCatalog._cpu_monkey_pages("Intel", "Core i5-9500")
    assert pages == ["https://www.cpu-monkey.com/en/cpu_group-intel_core_i_9000"]


def test_v14_17_pc_kombo_cpu_catalog_extracts_real_product_links_and_clean_names():
    html = '''
    <html><body>
      <a href="/us/product/cpu/0730143312042_AMD%20Ryzen%205%205600X">AMD Ryzen 5 5600X Socket AM4 Clock 3.7 GHz Turbo 4.6 GHz 6 Cores 12 Threads</a>
      <a href="/us/product/cpu/5032037104791_Intel%20Core%20i5-9400F">Intel Core i5-9400F Socket 1151 Clock 2.9 GHz Turbo 4.1 GHz 6 Cores 6 Threads</a>
      <a href="https://www.amazon.com/x">USD 100.00</a>
    </body></html>
    '''
    session = FakeSession(html, "https://www.pc-kombo.com/us/components/cpus")
    catalog = DiscoverySourceCatalog(session=session)
    catalog.rate_limiter.wait = lambda *_: None
    items, error = catalog._pc_kombo("PROCESSADOR", limit=10)
    assert error is None
    assert [x.nome for x in items] == ["AMD Ryzen 5 5600X", "Intel Core i5-9400F"]
    assert all("/us/product/cpu/" in x.url for x in items)
    assert all(x.fonte == "PC_KOMBO" for x in items)


def test_v14_17_processor_discovery_prioritizes_pc_kombo_then_cpu_monkey():
    sources = DEFAULT_SOURCES_BY_CATEGORY["PROCESSADOR"]
    assert sources[:2] == ["PC_KOMBO", "CPU_MONKEY"]
    assert "CPU_WORLD" in sources
    assert "WIKICHIP" in sources


def test_v14_17_generic_parser_understands_pc_kombo_producer_mpn_ean():
    html = '''
    <html><body>
      <h1>AMD Ryzen 5 5600X</h1>
      <dl>
        <dt>Producer</dt><dd>AMD</dd>
        <dt>MPN</dt><dd>100-100000065BOX</dd>
        <dt>EAN</dt><dd>0730143312042</dd>
        <dt>Base Clock</dt><dd>3.7 GHz</dd>
        <dt>Turbo Clock</dt><dd>4.6 GHz</dd>
        <dt>Cores</dt><dd>6</dd>
        <dt>Threads</dt><dd>12</dd>
        <dt>TDP</dt><dd>65 W</dd>
        <dt>Socket</dt><dd>AM4</dd>
      </dl>
    </body></html>
    '''
    raw = GenericScraper()._parse_html(
        "https://www.pc-kombo.com/us/product/cpu/0730143312042",
        "https://www.pc-kombo.com/us/product/cpu/0730143312042",
        html,
        source="PC_KOMBO",
    )
    assert raw["brand"] == "AMD"
    assert raw["mpn"] == "100-100000065BOX"
    assert raw["gtin"] == "0730143312042"
    by_name = {x["name"]: x["value_name"] for x in raw["attributes"]}
    assert by_name["Socket"] == "AM4"
    assert by_name["Cores"] == "6"
