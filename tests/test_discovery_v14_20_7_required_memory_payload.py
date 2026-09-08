import pytest

from src.api import _sanitize_discovery_result
from src.discovery.core import HardwareDiscoveryService
from src.discovery.sources import DiscoveryCandidate, DiscoverySourceCatalog
from src.extractors.dto_normalizer import (
    normalize_hardware_payload_for_backend,
    registration_payload_issues,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("DDR4", ["DDR4"]),
        ("ddr4", ["DDR4"]),
        ("Ddr5", ["DDR5"]),
        ("DDR 4", ["DDR4"]),
        ("DDR4/DDR5", ["DDR4", "DDR5"]),
        ("DDR4 + DDR5", ["DDR4", "DDR5"]),
        (["DDR4/DDR5"], ["DDR4", "DDR5"]),
        (["DDR5-5600"], ["DDR5"]),
        (["ddr4", "DDR5-5600", "DDR4"], ["DDR4", "DDR5"]),
    ],
)
def test_required_processor_memory_variants_are_normalized_to_non_empty_enum_array(raw, expected):
    payload = normalize_hardware_payload_for_backend(
        "PROCESSADOR",
        {
            "categoria": "PROCESSADOR",
            "nome": "CPU Teste",
            "especificacaoProcessador": {
                "socket": "AM5",
                "tiposMemoriaSuportados": raw,
            },
        },
    )
    assert payload["especificacaoProcessador"]["tiposMemoriaSuportados"] == expected
    assert registration_payload_issues("PROCESSADOR", payload) == []


@pytest.mark.parametrize("raw", [None, "", [], ["LPDDR5"], ["DDR6"], [None]])
def test_required_processor_memory_missing_or_invalid_becomes_empty_array(raw):
    payload = normalize_hardware_payload_for_backend(
        "PROCESSADOR",
        {
            "categoria": "PROCESSADOR",
            "nome": "CPU Teste",
            "especificacaoProcessador": {
                "socket": "AM5",
                "tiposMemoriaSuportados": raw,
            },
        },
    )
    assert payload["especificacaoProcessador"]["tiposMemoriaSuportados"] == []
    assert registration_payload_issues("PROCESSADOR", payload) == []


def test_http_guard_keeps_processor_visible_without_sending_null_memory_types():
    result = {
        "itens": [
            {
                "payload": {
                    "categoria": "PROCESSADOR",
                    "nome": "CPU Sem Memoria",
                    "especificacaoProcessador": {
                        "socket": "AM5",
                        "tiposMemoriaSuportados": None,
                    },
                }
            },
            {
                "payload": {
                    "categoria": "PROCESSADOR",
                    "nome": "CPU Valida",
                    "especificacaoProcessador": {
                        "socket": "AM5",
                        "tiposMemoriaSuportados": "DDR5-5600",
                    },
                }
            },
        ],
        "quantidadeRetornada": 2,
    }
    out = _sanitize_discovery_result("PROCESSADOR", result)
    assert out["quantidadeRetornada"] == 2
    assert len(out["itens"]) == 2
    incomplete = out["itens"][0]
    incomplete_spec = incomplete["payload"]["especificacaoProcessador"]
    assert incomplete_spec["tiposMemoriaSuportados"] == []
    assert incomplete["cadastravel"] is True
    assert incomplete["cadastroBloqueado"] is False
    assert incomplete["motivosNaoCadastravel"] == []
    valid = out["itens"][1]
    assert valid["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR5"]
    assert valid["cadastravel"] is True
    assert out["descartadosPayloadObrigatorio"] == 0


class _CatalogMissingRequiredMemory:
    allow_browser_fallback = False
    resolver = None

    def discover(self, **kwargs):
        return [
            DiscoveryCandidate(
                nome="AMD Ryzen Test Sem Memoria",
                url="https://example.com/cpu-sem-memoria",
                fonte="PC_KOMBO",
                marca="AMD",
                resumo={"specs": {"socket": "AM5", "nucleos": 6, "threads": 12}},
            )
        ], []


def test_http_discovery_keeps_uncadastrable_processor_visible_without_null_memory():
    service = HardwareDiscoveryService(catalog=_CatalogMissingRequiredMemory())
    internal = service.discover(
        "PROCESSADOR",
        limite=1,
        detalhar=False,
        enriquecer=False,
        no_browser=True,
    )
    # O núcleo pode manter a ficha para diagnóstico/revisão interna.
    assert len(internal["itens"]) == 1
    # A resposta HTTP mantém a CPU visível e envia [] como "não informado".
    out = _sanitize_discovery_result("PROCESSADOR", internal)
    assert len(out["itens"]) == 1
    assert out["quantidadeRetornada"] == 1
    item = out["itens"][0]
    assert item["cadastravel"] is True
    assert item["cadastroBloqueado"] is False
    assert item["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == []
    assert out["descartadosPayloadObrigatorio"] == 0


def test_pc_kombo_cpu_catalog_summary_extracts_memory_types_and_frequency():
    specs = DiscoverySourceCatalog._pc_kombo_summary(
        "AMD Ryzen 9 Test Socket AM5 Clock 4.2 GHz Turbo 5.7 GHz 16 Cores 32 Threads DDR5-5600 170 W",
        "PROCESSADOR",
    )
    assert specs["socket"] == "AM5"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5600


def test_pc_kombo_cpu_catalog_summary_handles_two_memory_generations():
    specs = DiscoverySourceCatalog._pc_kombo_summary(
        "Intel CPU Test Socket LGA1700 Clock 3.4 GHz Turbo 5.2 GHz 16 Cores 24 Threads DDR4-3200 / DDR5-5600 125 W",
        "PROCESSADOR",
    )
    assert specs["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5600
