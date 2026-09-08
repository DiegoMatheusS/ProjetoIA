import pytest

from src.api import _sanitize_discovery_result
from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend


@pytest.mark.parametrize("raw", [None, "", [], [None], ["DDR6"], "LPDDR5"])
def test_processor_unknown_memory_is_always_empty_array(raw):
    payload = normalize_hardware_payload_for_backend("PROCESSADOR", {
        "categoria": "PROCESSADOR",
        "nome": "CPU Teste",
        "especificacaoProcessador": {"socket": "AM5", "tiposMemoriaSuportados": raw},
    })
    assert payload["especificacaoProcessador"]["tiposMemoriaSuportados"] == []


@pytest.mark.parametrize("raw, expected", [
    ("DDR5", ["DDR5"]),
    (["DDR4/DDR5"], ["DDR4", "DDR5"]),
    (["DDR5-5600"], ["DDR5"]),
    (["ddr4", "DDR5-5600"], ["DDR4", "DDR5"]),
])
def test_processor_known_memory_never_leaks_invalid_format(raw, expected):
    payload = normalize_hardware_payload_for_backend("PROCESSADOR", {
        "categoria": "PROCESSADOR",
        "nome": "CPU Teste",
        "especificacaoProcessador": {"socket": "AM5", "tiposMemoriaSuportados": raw},
    })
    assert payload["especificacaoProcessador"]["tiposMemoriaSuportados"] == expected


def test_http_response_keeps_memory_field_when_unknown():
    out = _sanitize_discovery_result("PROCESSADOR", {
        "itens": [{
            "payload": {
                "categoria": "PROCESSADOR",
                "nome": "CPU Sem DDR confirmado",
                "especificacaoProcessador": {"socket": "AM5"},
            }
        }],
        "quantidadeRetornada": 1,
    })
    item = out["itens"][0]
    assert item["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == []
    assert item["cadastravel"] is True
    assert item["cadastroBloqueado"] is False
