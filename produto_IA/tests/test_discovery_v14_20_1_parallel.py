import time

from src.discovery.core import HardwareDiscoveryService
from src.discovery.sources import DiscoveryCandidate


class FakeCatalog:
    allow_browser_fallback = True
    resolver = None

    def discover(self, categoria, marca=None, consulta=None, fontes=None, limit=20):
        items = [
            DiscoveryCandidate(
                nome=f"Corsair Vengeance DDR5 6000 2x16 GB {i}",
                url=f"https://example.com/ram-{i}",
                fonte="PC_KOMBO",
                marca="Corsair",
                resumo={"catalog_text": "DDR5 6000 MHz 2x16 GB DIMM"},
            )
            for i in range(6)
        ]
        return items, []


def test_v14_20_1_details_candidates_in_parallel(monkeypatch):
    service = HardwareDiscoveryService(catalog=FakeCatalog())
    service.detail_workers = 6
    service.request_budget = 5

    def fake_detail(candidate, categoria, enrich, no_browser=False, bulk_mode=False):
        time.sleep(0.12)
        return {
            "payloadHardware": {"nome": candidate.nome, "categoria": categoria, "especificacaoMemoriaRam": {}},
            "especificacoesEncontradas": {},
            "camposObrigatoriosAusentes": [],
            "conflitos": [],
            "coberturaTecnica": 0.0,
            "detalhesColetados": True,
            "chaveComparacao": candidate.nome,
        }

    monkeypatch.setattr(service, "_detail_candidate", fake_detail)
    started = time.monotonic()
    result = service.discover("MEMORIA_RAM", limite=6, detalhar=True, enriquecer=True)
    elapsed = time.monotonic() - started

    assert result["quantidadeRetornada"] == 6
    assert elapsed < 0.45
    assert all(item["detalhesColetados"] for item in result["itens"])


def test_v14_20_1_bulk_browser_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DISCOVERY_BULK_BROWSER_FALLBACK", raising=False)
    service = HardwareDiscoveryService(catalog=FakeCatalog())
    assert service.bulk_browser_fallback is False
