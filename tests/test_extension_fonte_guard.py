from src.criabyte.client import _error_detail
from src.extension.payload_guard import (
    extension_registration_issues,
    sanitize_extension_hardware_payload,
)


def _hardware_fonte(**spec_overrides):
    specs = {
        "formato": "ATX",
        "potenciaWatts": 700,
        **spec_overrides,
    }
    return {
        "nome": "Fonte ATX 700W",
        "categoria": "FONTE",
        "marca": "Marca Teste",
        "modelo": "Modelo 700W",
        "especificacaoFonte": specs,
    }


def test_error_detail_reads_criabyte_portuguese_message():
    payload = {
        "statusCode": 400,
        "codigo": "REQUISICAO_INVALIDA",
        "mensagem": "especificacaoFonte.potenciaWatts must not be greater than 100000",
        "detalhes": {},
    }
    assert "potenciaWatts" in _error_detail(payload)


def test_error_detail_joins_nest_message_array():
    payload = {
        "message": [
            "hardwarePayload.marca must be a string",
            "hardwarePayload.modelo should not be empty",
        ]
    }
    detail = _error_detail(payload)
    assert "marca" in detail
    assert "modelo" in detail


def test_fonte_rejects_ambiguous_concatenated_power_before_backend():
    payload = _hardware_fonte(potenciaWatts=500600700)
    sanitized = sanitize_extension_hardware_payload("FONTE", payload)
    issues = extension_registration_issues("FONTE", sanitized)
    assert "especificacaoFonte.potenciaWatts não confirmada" in issues


def test_fonte_rejects_missing_format_before_backend():
    payload = _hardware_fonte(formato=None)
    sanitized = sanitize_extension_hardware_payload("FONTE", payload)
    issues = extension_registration_issues("FONTE", sanitized)
    assert "especificacaoFonte.formato não confirmado" in issues


def test_fonte_drops_invalid_optional_connector_but_keeps_valid_payload():
    payload = _hardware_fonte(conectoresSata=999)
    sanitized = sanitize_extension_hardware_payload("FONTE", payload)
    assert "conectoresSata" not in sanitized["especificacaoFonte"]
    assert extension_registration_issues("FONTE", sanitized) == []
