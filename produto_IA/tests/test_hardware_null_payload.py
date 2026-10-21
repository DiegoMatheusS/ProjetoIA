from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend


def test_fonte_unknown_optional_fields_are_omitted_not_null():
    payload = {
        "categoria": "FONTE",
        "nome": "Fonte ATX 700W",
        "marca": "Digital Informatica",
        "modelo": "700W",
        "especificacaoFonte": {
            "formato": "ATX",
            "potenciaWatts": 700,
            "modularidade": None,
            "eficienciaPercentual": None,
            "certificacao": None,
            "protecoes": ["CURTO", "SOBRECARGA"],
        },
    }

    normalized = normalize_hardware_payload_for_backend("FONTE", payload)
    specs = normalized["especificacaoFonte"]

    assert specs["formato"] == "ATX"
    assert specs["potenciaWatts"] == 700
    assert "modularidade" not in specs
    assert "eficienciaPercentual" not in specs
    assert "certificacao" not in specs
    assert specs["protecoes"] == ["CURTO", "SOBRECARGA"]
