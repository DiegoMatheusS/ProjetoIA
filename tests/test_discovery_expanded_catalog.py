import asyncio
import time
from urllib.parse import parse_qs, urlparse

from src import api
from src.discovery.core import HardwareDiscoveryService
from src.discovery.sources import DiscoveryCandidate, DiscoverySourceCatalog


def cpu(index, source="PC_KOMBO"):
    return DiscoveryCandidate(f"Intel Core i5-{9000 + index}", f"https://example.test/cpu/{index}", source)


class Catalog:
    def __init__(self, candidates):
        self.candidates = candidates
        self.requests = []

    def discover(self, **kwargs):
        self.requests.append(kwargs)
        return self.candidates[:kwargs["limit"]], []


def discover(service, **kwargs):
    return service.discover("PROCESSADOR", detalhar=False, enriquecer=False, **kwargs)


def test_registering_every_result_advances_the_next_search_to_new_models():
    catalog = Catalog([cpu(i) for i in range(400)])
    service = HardwareDiscoveryService(catalog)
    first = discover(service, limite=100)
    registered = [item["payload"] for item in first["itens"]]
    second = discover(service, limite=100, hardwares_cadastrados=registered)
    assert len(first["itens"]) == len(second["itens"]) == 100
    assert not {item["payload"]["nome"] for item in first["itens"]} & {item["payload"]["nome"] for item in second["itens"]}
    assert second["jaCadastradosIgnorados"] == 100
    assert second["itens"][0]["payload"]["nome"] == "Intel Core i5-9100"
    assert second["temMais"] is True


def test_registered_catalog_does_not_consume_the_first_new_page():
    catalog = Catalog([cpu(i) for i in range(700)])
    service = HardwareDiscoveryService(catalog)
    registered = [{"nome": f"Processador Intel Core i5-{9000+i}", "marca": "Intel", "modelo": f"Core i5-{9000+i}"} for i in range(500)]
    result = discover(service, limite=50, hardwares_cadastrados=registered)
    assert result["jaCadastradosIgnorados"] == 500
    assert len(result["itens"]) == 50
    assert result["itens"][0]["payload"]["nome"] == "Intel Core i5-9500"
    assert catalog.requests[-1]["limit"] >= 600


def test_page_five_reaches_models_beyond_the_old_200_candidate_ceiling():
    service = HardwareDiscoveryService(Catalog([cpu(i) for i in range(500)]))
    result = discover(service, pagina=5, limite=50)
    assert len(result["itens"]) == 50
    assert result["itens"][0]["payload"]["nome"] == "Intel Core i5-9200"
    assert result["temMais"] is True


def test_source_support_is_consulted_and_interleaved_even_when_first_source_is_full(monkeypatch):
    catalog = DiscoverySourceCatalog()
    calls = []
    monkeypatch.setattr(catalog, "_pc_kombo", lambda *args: ([cpu(i) for i in range(50)], None))

    def monkey(*args):
        calls.append("CPU_MONKEY")
        return [cpu(500, "CPU_MONKEY")], None

    monkeypatch.setattr(catalog, "_cpu_monkey", monkey)
    items, diagnostics = catalog.discover("PROCESSADOR", fontes=["PC_KOMBO", "CPU_MONKEY"], limit=2)
    assert calls == ["CPU_MONKEY"]
    assert [item.nome for item in items] == ["Intel Core i5-9000", "Intel Core i5-9500"]
    assert len(diagnostics) == 2


def test_gpu_reference_models_participate_in_discovery(monkeypatch):
    catalog = DiscoverySourceCatalog()
    monkeypatch.setattr(catalog, "_pc_kombo", lambda *args: ([], None))
    monkeypatch.setattr(catalog, "_techpowerup_reference_index", lambda: ({"rx580": {
        "nome": "Radeon RX 580", "url": "https://www.techpowerup.com/gpu-specs/radeon-rx-580.c2938", "specs": {"memoriaVideoGb": 8},
    }}, None))
    items, _ = catalog.discover("PLACA_VIDEO", fontes=["PC_KOMBO", "TECHPOWERUP"], limit=50)
    assert [item.nome for item in items] == ["Radeon RX 580"]


def test_gpu_reference_failure_does_not_discard_the_primary_catalog(monkeypatch):
    catalog = DiscoverySourceCatalog()
    monkeypatch.setattr(catalog, "_pc_kombo", lambda *args: ([DiscoveryCandidate("Sapphire RX 580", "https://example.test/rx580", "PC_KOMBO")], None))

    def fail():
        raise RuntimeError("blocked")

    monkeypatch.setattr(catalog, "_techpowerup_reference_index", fail)
    items, diagnostics = catalog.discover("PLACA_VIDEO", fontes=["PC_KOMBO", "TECHPOWERUP"], limit=50)
    assert len(items) == 1
    assert "ERRO_FONTE" in diagnostics[1]["erro"]


def test_pangoly_can_read_beyond_the_four_old_pages(monkeypatch):
    catalog = DiscoverySourceCatalog()
    catalog.allow_browser_fallback = False
    pages = []

    def fetch(url, domains):
        page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
        pages.append(page)
        html = "".join(f'<a href="/en/product/noctua-fan-{i}">Noctua Fan {i}</a>' for i in range((page-1)*24, page*24)) if page <= 5 else ""
        return html, url, None

    monkeypatch.setattr(catalog, "_fetch_html", fetch)
    items, error = catalog._pangoly_case_fans(limit=120)
    assert len(items) == 120
    assert pages == [1, 2, 3, 4, 5]
    assert error is None


def test_source_failure_preserves_other_results_and_restores_deadlines(monkeypatch):
    catalog = DiscoverySourceCatalog()
    catalog.deadline = 123
    catalog.resolver.deadline = 456
    monkeypatch.setattr(catalog, "_pc_kombo", lambda *args: ([cpu(1)], None))

    def fail(*args):
        raise RuntimeError("blocked")

    monkeypatch.setattr(catalog, "_cpu_monkey", fail)
    items, diagnostics = catalog.discover("PROCESSADOR", fontes=["PC_KOMBO", "CPU_MONKEY"], deadline=time.monotonic()+5)
    assert len(items) == 1
    assert "ERRO_FONTE" in diagnostics[1]["erro"]
    assert catalog.deadline == 123
    assert catalog.resolver.deadline == 456


def test_api_accepts_100_and_forwards_model_and_registered_catalog(monkeypatch):
    monkeypatch.delenv("PRODUTO_IA_API_KEY", raising=False)
    calls = []

    def fake_discover(*args):
        calls.append(args)
        return {"itens": [], "temMais": False}

    monkeypatch.setattr(api._discovery_service, "discover", fake_discover)
    registered = [{"nome": "Intel Core i5-9400F", "marca": "Intel", "modelo": "Core i5-9400F"}]
    request = api.HardwareDiscoveryRequest(categoria="PROCESSADOR", consulta="i5-9500", limite=100, hardwaresCadastrados=registered, enriquecer=False)
    asyncio.run(api.descobrir_hardwares(request, None))
    assert calls[0][2] == "i5-9500"
    assert calls[0][5] == 100
    assert calls[0][-1] == registered
