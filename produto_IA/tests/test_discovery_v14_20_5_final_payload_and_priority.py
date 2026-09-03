from src.api import _sanitize_discovery_result
from src.discovery.core import HardwareDiscoveryService
from src.discovery.sources import DiscoveryCandidate
from src.enrichment.core import _provider_rank
from src.enrichment.providers import GeizhalsProvider, ManufacturerProvider, TechPowerUpProvider
from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend


def test_v14_20_5_processor_payload_final_guard_splits_memory_enum_and_drops_unknown_keys():
    payload = {
        "nome": "AMD Ryzen 5 7600X",
        "marca": "AMD",
        "modelo": "Ryzen 5 7600X",
        "categoria": "PROCESSADOR",
        "especificacaoProcessador": {
            "socket": "AM5",
            "tiposMemoriaSuportados": ["DDR5-5200", "DDR4/DDR5", "LPDDR5"],
            "dataLancamento": "2022",
            "campoQueNaoExisteNoDto": "nao pode sair",
        },
    }
    safe = normalize_hardware_payload_for_backend("PROCESSADOR", payload)
    specs = safe["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == ["DDR5", "DDR4"]
    assert specs["dataLancamento"] is None
    assert "campoQueNaoExisteNoDto" not in specs


def test_v14_20_5_http_guard_rewrites_exact_payload_reused_by_backend():
    result = {
        "itens": [{
            "payload": {
                "nome": "AMD Ryzen Test",
                "marca": "AMD",
                "modelo": "Ryzen Test 1",
                "categoria": "PROCESSADOR",
                "especificacaoProcessador": {
                    "socket": "AM5",
                    "tiposMemoriaSuportados": ["DDR4/DDR5"],
                },
            },
            "payloadHardware": {"stale": True},
        }]
    }
    out = _sanitize_discovery_result("PROCESSADOR", result)
    item = out["itens"][0]
    assert item["payload"] is item["payloadHardware"]
    assert item["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]


class _FakeCatalog:
    allow_browser_fallback = False
    resolver = None

    def discover(self, **kwargs):
        return [
            DiscoveryCandidate(
                nome="AMD Ryzen 5 7600X",
                url="https://example.com/7600x",
                fonte="PC_KOMBO",
                marca="AMD",
                resumo={
                    "specs": {
                        "socket": "AM5",
                        "tiposMemoriaSuportados": ["DDR5-5200", "DDR4/DDR5"],
                        "nucleos": 6,
                        "threads": 12,
                    }
                },
            )
        ], []


def test_v14_20_5_discovery_payload_itself_is_dto_safe_before_frontend():
    service = HardwareDiscoveryService(catalog=_FakeCatalog())
    result = service.discover("PROCESSADOR", limite=1, detalhar=False, enriquecer=False, no_browser=True)
    payload = result["itens"][0]["payload"]
    assert payload["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR5", "DDR4"]


def test_v14_20_5_specialized_sources_come_before_manufacturer_for_weak_categories():
    geizhals = GeizhalsProvider()
    manufacturer = ManufacturerProvider()
    techpowerup = TechPowerUpProvider()
    for category in ["PLACA_MAE", "MEMORIA_RAM", "ARMAZENAMENTO", "FONTE", "GABINETE", "COOLER", "VENTOINHA"]:
        assert _provider_rank(category, geizhals) < _provider_rank(category, manufacturer)
    assert _provider_rank("PLACA_VIDEO", techpowerup) < _provider_rank("PLACA_VIDEO", manufacturer)
    assert _provider_rank("PLACA_VIDEO", geizhals) < _provider_rank("PLACA_VIDEO", manufacturer)
