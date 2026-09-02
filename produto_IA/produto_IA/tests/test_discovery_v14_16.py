from src.discovery.core import HardwareDiscoveryService, infer_identity, PROVIDER_BY_SOURCE
from src.discovery.sources import DiscoverySourceCatalog, DiscoveryCandidate
from src.enrichment.core import TechnicalEnricher


class FakeResponse:
    def __init__(self, text, url="https://example.com", status_code=200):
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

    def get(self, url, **kwargs):
        return FakeResponse(self.html, self.final_url, 200)


def test_v14_16_cpu_monkey_catalog_discovers_multiple_processors():
    html = """
    <html><body>
      <a href="/en/cpu-intel_core_i5_9500">Intel Core i5-9500</a>
      <a href="/en/cpu-intel_core_i5_9600k">Intel Core i5-9600K</a>
      <a href="/en/cpu-amd_ryzen_5_7600">AMD Ryzen 5 7600</a>
    </body></html>
    """
    catalog = DiscoverySourceCatalog(session=FakeSession(html, "https://www.cpu-monkey.com/en/search"))
    catalog.rate_limiter.wait = lambda *_: None
    items, error = catalog._cpu_monkey(marca="Intel", consulta="Core i5", limit=10)
    assert error is None
    assert [x.nome for x in items] == ["Intel Core i5-9500", "Intel Core i5-9600K"]
    assert all(x.fonte == "CPU_MONKEY" for x in items)


def test_v14_16_techpowerup_catalog_discovers_gpu_pages_only():
    html = """
    <html><body>
      <a href="/gpu-specs/geforce-rtx-5080.c4217">GeForce RTX 5080</a>
      <a href="/gpu-specs/radeon-rx-9070-xt.c4229">Radeon RX 9070 XT</a>
      <a href="/gpu-specs/">GPU Database</a>
      <a href="/gpu-specs/docs/test.pdf">PDF</a>
    </body></html>
    """
    catalog = DiscoverySourceCatalog(session=FakeSession(html, "https://www.techpowerup.com/gpu-specs/"))
    catalog.rate_limiter.wait = lambda *_: None
    items, error = catalog._techpowerup(limit=10)
    assert error is None
    assert [x.nome for x in items] == ["GeForce RTX 5080", "Radeon RX 9070 XT"]


def test_v14_16_infer_identity_builds_backend_dedupe_key():
    intel = infer_identity("Intel Core i5-9500", "PROCESSADOR")
    assert intel["marca"] == "Intel"
    assert intel["modelo"] == "Core i5-9500"
    assert intel["metodo"] == "MARCA_MODELO"
    assert intel["chave"] == "intel|corei59500"

    gpu = infer_identity("GeForce RTX 5080", "PLACA_VIDEO")
    assert gpu["marca"] == "NVIDIA"
    assert gpu["modelo"] == "GeForce RTX 5080"
    assert gpu["chave"] == "nvidia|geforcertx5080"


def test_v14_16_discovery_list_never_returns_price_and_backend_filters_existing():
    class FakeCatalog:
        def discover(self, **kwargs):
            return [
                DiscoveryCandidate("Intel Core i5-9500", "https://www.cpu-monkey.com/en/cpu-intel_core_i5_9500", "CPU_MONKEY")
            ], [{"fonte": "CPU_MONKEY", "encontrados": 1, "erro": None}]

    service = HardwareDiscoveryService(catalog=FakeCatalog())
    result = service.discover("PROCESSADOR", limite=20, detalhar=False, enriquecer=False)
    assert result["modo"] == "DESCOBERTA_HARDWARES"
    assert result["politica"]["somenteHardware"] is True
    assert result["politica"]["precoNaoColetado"] is True
    assert result["politica"]["backendDeveOcultarJaCadastrados"] is True
    assert len(result["itens"]) == 1
    item = result["itens"][0]
    assert item["preco"] is None
    assert item["payloadHardware"]["categoria"] == "PROCESSADOR"
    assert item["chaveComparacao"] == "intel|corei59500"


def test_v14_16_detail_normalizes_cpu_specs(monkeypatch):
    class FakeCPUProvider:
        allow_browser_fallback = False
        resolver = None

        def fetch_candidate(self, url, identity):
            return {
                "ok": True,
                "fonte": "CPU_MONKEY",
                "url": url,
                "title": "Intel Core i5-9500",
                "brand": "Intel",
                "model": "Core i5-9500",
                "attributes": [
                    {"name": "Socket", "value_name": "LGA1151"},
                    {"name": "Total Cores", "value_name": "6"},
                    {"name": "Total Threads", "value_name": "6"},
                    {"name": "Processor Base Frequency", "value_name": "3.00 GHz"},
                    {"name": "Max Turbo Frequency", "value_name": "4.40 GHz"},
                    {"name": "TDP", "value_name": "65 W"},
                    {"name": "Memory Types", "value_name": "DDR4-2666"},
                ],
                "context_text": "Intel Core i5-9500 Socket LGA1151 6 cores 6 threads 3.00 GHz 4.40 GHz TDP 65 W DDR4-2666",
            }

    monkeypatch.setitem(PROVIDER_BY_SOURCE, "CPU_MONKEY", FakeCPUProvider)
    service = HardwareDiscoveryService(catalog=None)
    item = service.detail(
        "PROCESSADOR",
        "Intel Core i5-9500",
        "https://www.cpu-monkey.com/en/cpu-intel_core_i5_9500",
        "CPU_MONKEY",
        enriquecer=False,
    )
    specs = item["especificacoesEncontradas"]
    assert specs["socket"] == "LGA1151"
    assert specs["nucleos"] == 6
    assert specs["threads"] == 6
    assert specs["frequenciaBaseMhz"] == 3000
    assert specs["frequenciaTurboMhz"] == 4400
    assert specs["tdpWatts"] == 65
    assert item["payloadHardware"]["especificacaoProcessador"]["socket"] == "LGA1151"
    assert item["preco"] is None


def test_v14_16_discovery_enrichment_has_own_small_budget():
    enricher = TechnicalEnricher(
        providers=[],
        auto_mode=True,
        total_timeout_override=5,
        max_sources_override=2,
        source_timeout_override=2,
    )
    assert enricher.total_timeout == 5
    assert enricher.max_sources == 2
