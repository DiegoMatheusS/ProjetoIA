from src.api import _sanitize_discovery_result
from src.enrichment.core import PROVIDER_PRIORITY
from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend


def test_processor_missing_memory_is_visible_registerable_and_serialized_as_empty_array():
    result = {
        "itens": [{
            "payload": {
                "categoria": "PROCESSADOR",
                "nome": "CPU Teste",
                "especificacaoProcessador": {
                    "socket": "AM5",
                    "tiposMemoriaSuportados": None,
                },
            },
            "avisos": [],
        }],
        "quantidadeRetornada": 1,
    }
    out = _sanitize_discovery_result("PROCESSADOR", result)
    assert out["quantidadeRetornada"] == 1
    item = out["itens"][0]
    assert item["cadastravel"] is True
    assert item["cadastroBloqueado"] is False
    specs = item["payload"]["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == []


def test_processor_valid_memory_is_registerable_and_normalized():
    payload = normalize_hardware_payload_for_backend("PROCESSADOR", {
        "categoria": "PROCESSADOR",
        "nome": "CPU Teste",
        "especificacaoProcessador": {
            "socket": "LGA1700",
            "tiposMemoriaSuportados": ["DDR4/DDR5", "DDR5-5600"],
        },
    })
    result = {"itens": [{"payload": payload}], "quantidadeRetornada": 1}
    out = _sanitize_discovery_result("PROCESSADOR", result)
    item = out["itens"][0]
    assert item["cadastravel"] is True
    assert item["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]


def test_gpu_prioritizes_techpowerup_and_geizhals_before_icecat():
    order = PROVIDER_PRIORITY["PLACA_VIDEO"]
    assert order.index("TECHPOWERUP") < order.index("ICECAT")
    assert order.index("GEIZHALS") < order.index("ICECAT")


def test_low_coverage_categories_prioritize_richer_sources_and_ram_order_is_preserved():
    assert PROVIDER_PRIORITY["PLACA_MAE"][:2] == ["GEIZHALS", "FABRICANTE_OFICIAL"]
    assert PROVIDER_PRIORITY["ARMAZENAMENTO"][:2] == ["GEIZHALS", "FABRICANTE_OFICIAL"]
    assert PROVIDER_PRIORITY["FONTE"][:2] == ["FABRICANTE_OFICIAL", "GEIZHALS"]
    assert PROVIDER_PRIORITY["GABINETE"][:2] == ["GEIZHALS", "FABRICANTE_OFICIAL"]
    assert PROVIDER_PRIORITY["COOLER"][:2] == ["GEIZHALS", "FABRICANTE_OFICIAL"]
    assert PROVIDER_PRIORITY["VENTOINHA"][:2] == ["GEIZHALS", "FABRICANTE_OFICIAL"]
    assert PROVIDER_PRIORITY["MEMORIA_RAM"][:3] == ["ICECAT", "GEIZHALS", "FABRICANTE_OFICIAL"]
