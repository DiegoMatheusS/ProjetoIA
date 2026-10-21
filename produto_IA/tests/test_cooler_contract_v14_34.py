from src.extractors.backend_schemas import SCHEMAS
from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend


def test_cooler_nao_expõe_fluxo_ar_cfm_no_contrato_backend():
    campos_cooler = SCHEMAS["COOLER"][2]
    campos_ventoinha = SCHEMAS["VENTOINHA"][2]

    assert "fluxoArCfm" not in campos_cooler
    assert "fluxoArCfm" in campos_ventoinha


def test_normalizador_remove_fluxo_ar_cfm_de_cooler_e_preserva_outros_campos():
    payload = normalize_hardware_payload_for_backend(
        "COOLER",
        {
            "nome": "Cooler Teste",
            "marca": "Teste",
            "modelo": "C1",
            "categoria": "COOLER",
            "especificacaoCooler": {
                "tipo": "AIR_COOLER",
                "socketsSuportados": ["AM5"],
                "velocidadeMaxRpm": 1850,
                "fluxoArCfm": 66.17,
                "ruidoDb": 25.8,
            },
        },
    )

    specs = payload["especificacaoCooler"]
    assert "fluxoArCfm" not in specs
    assert specs["velocidadeMaxRpm"] == 1850
    assert specs["ruidoDb"] == 25.8
