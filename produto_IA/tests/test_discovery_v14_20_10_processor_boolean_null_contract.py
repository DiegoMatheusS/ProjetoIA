from src.api import _sanitize_discovery_result
from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend


def test_processor_null_boolean_fields_are_omitted_but_memory_empty_array_is_kept():
    payload = normalize_hardware_payload_for_backend("PROCESSADOR", {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen Teste",
        "especificacaoProcessador": {
            "socket": "AM5",
            "tiposMemoriaSuportados": None,
            "possuiVideoIntegrado": True,
            "suportaEcc": False,
            "coolerIncluso": None,
            "multiplicadorDesbloqueado": None,
            "suporteOverclock": False,
        },
    })

    specs = payload["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == []
    assert specs["possuiVideoIntegrado"] is True
    assert specs["suportaEcc"] is False
    assert specs["suporteOverclock"] is False
    assert "coolerIncluso" not in specs
    assert "multiplicadorDesbloqueado" not in specs


def test_processor_invalid_boolean_normalizes_to_unknown_and_is_omitted():
    payload = normalize_hardware_payload_for_backend("PROCESSADOR", {
        "categoria": "PROCESSADOR",
        "nome": "CPU Teste",
        "especificacaoProcessador": {
            "tiposMemoriaSuportados": ["DDR5"],
            "coolerIncluso": "desconhecido",
            "multiplicadorDesbloqueado": "n/a",
        },
    })

    specs = payload["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert "coolerIncluso" not in specs
    assert "multiplicadorDesbloqueado" not in specs


def test_http_discovery_response_never_leaks_null_processor_booleans():
    out = _sanitize_discovery_result("PROCESSADOR", {
        "itens": [{
            "payload": {
                "categoria": "PROCESSADOR",
                "nome": "CPU Teste",
                "especificacaoProcessador": {
                    "socket": "AM5",
                    "tiposMemoriaSuportados": [],
                    "coolerIncluso": None,
                    "multiplicadorDesbloqueado": None,
                    "suportaEcc": False,
                },
            }
        }],
        "quantidadeRetornada": 1,
    })

    specs = out["itens"][0]["payload"]["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == []
    assert specs["suportaEcc"] is False
    assert "coolerIncluso" not in specs
    assert "multiplicadorDesbloqueado" not in specs
