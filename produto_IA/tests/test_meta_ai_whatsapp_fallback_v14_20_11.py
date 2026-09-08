from src.api import _sanitize_discovery_result, _meta_ai_whatsapp_enrich_sync, MetaAiWhatsappEnrichmentRequest
from src.extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    merge_meta_ai_response_into_payload,
    parse_meta_ai_response,
    should_use_meta_ai_fallback,
)


def test_fallback_only_when_technical_coverage_is_low():
    assert should_use_meta_ai_fallback(0.43, threshold=0.60) is True
    assert should_use_meta_ai_fallback(0.59, threshold=0.60) is True
    assert should_use_meta_ai_fallback(0.60, threshold=0.60) is False
    assert should_use_meta_ai_fallback(0.82, threshold=0.60) is False


def test_prompt_requests_confirmed_specs_and_missing_fields():
    prompt = build_meta_ai_prompt(
        "PROCESSADOR",
        "AMD Ryzen 5 8400F",
        ["tiposMemoriaSuportados", "cacheL3Mb"],
    )
    assert "AMD Ryzen 5 8400F" in prompt
    assert "uma por linha" in prompt
    assert "Não invente" in prompt
    assert "tiposMemoriaSuportados" in prompt


def test_meta_ai_cpu_text_is_parsed_and_ddr_frequency_is_normalized():
    text = """
Socket: AM5
Cores: 6
Threads: 12
Base Clock: 4.2 GHz
Boost Clock: 4.7 GHz
L3 Cache: 16 MB
TDP: 65 W
Supported Memory Types: DDR5-5200
PCIe: 4.0
"""
    specs = parse_meta_ai_response("PROCESSADOR", text)
    assert specs["socket"] == "AM5"
    assert specs["nucleos"] == 6
    assert specs["threads"] == 12
    assert specs["frequenciaBaseMhz"] == 4200
    assert specs["frequenciaTurboMhz"] == 4700
    assert specs["cacheL3Mb"] == 16
    assert specs["tdpWatts"] == 65
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5200
    assert specs["versaoPcie"] == "4.0"


def test_meta_ai_merge_only_fills_missing_fields_and_preserves_known_values():
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 5 8400F",
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 6,
            "threads": 12,
            "tdpWatts": 70,
            "tiposMemoriaSuportados": [],
        },
    }
    response = """
Socket: LGA1700
TDP: 65 W
Supported Memory Types: DDR5-5200
L3 Cache: 16 MB
"""
    merged, filled, parsed = merge_meta_ai_response_into_payload("PROCESSADOR", payload, response)
    specs = merged["especificacaoProcessador"]
    assert specs["socket"] == "AM5"
    assert specs["tdpWatts"] == 70
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["cacheL3Mb"] == 16
    assert "tiposMemoriaSuportados" in filled
    assert "cacheL3Mb" in filled
    assert parsed["socket"] == "LGA1700"


def test_discovery_marks_only_low_coverage_item_for_whatsapp_fallback():
    result = {
        "itens": [{
            "nome": "AMD Ryzen 5 8400F",
            "payload": {
                "categoria": "PROCESSADOR",
                "nome": "AMD Ryzen 5 8400F",
                "especificacaoProcessador": {
                    "socket": "AM5",
                    "nucleos": 6,
                    "threads": 12,
                    "tiposMemoriaSuportados": [],
                },
            },
            "avisos": [],
        }],
        "quantidadeRetornada": 1,
    }
    out = _sanitize_discovery_result("PROCESSADOR", result)
    fallback = out["itens"][0]["metaAiWhatsappFallback"]
    assert fallback["recomendado"] is True
    assert fallback["somenteQuandoPoucosDados"] is True
    assert fallback["promptSugerido"]


def test_meta_ai_enrichment_is_skipped_when_normal_search_is_already_good():
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "CPU Completa",
        "especificacaoProcessador": {
            "socket": "AM5",
            "familia": "Ryzen 7",
            "arquitetura": "Zen 5",
            "litografiaNm": 4,
            "nucleos": 8,
            "threads": 16,
            "frequenciaBaseMhz": 4000,
            "frequenciaTurboMhz": 5500,
            "cacheL2Mb": 8,
            "cacheL3Mb": 32,
            "tdpWatts": 65,
            "possuiVideoIntegrado": True,
            "modeloVideoIntegrado": "Radeon Graphics",
            "tiposMemoriaSuportados": ["DDR5"],
            "frequenciaMemoriaMaximaMhz": 5600,
            "capacidadeMemoriaMaximaGb": 256,
            "canaisMemoria": 2,
            "suportaEcc": True,
            "temperaturaMaximaC": 95,
            "versaoPcie": "5.0",
            "lanesPcie": 24,
        },
    }
    request = MetaAiWhatsappEnrichmentRequest(
        categoria="PROCESSADOR",
        nome="CPU Completa",
        payload=payload,
        resposta="TDP: 120 W\nSupported Memory Types: DDR4",
    )
    out = _meta_ai_whatsapp_enrich_sync(request)
    assert out["utilizado"] is False
    assert out["motivo"] == "COBERTURA_NORMAL_SUFICIENTE"
    assert out["payload"]["especificacaoProcessador"]["tdpWatts"] == 65


def test_meta_ai_enrichment_is_used_for_low_coverage_payload():
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 5 8400F",
        "especificacaoProcessador": {
            "socket": "AM5",
            "tiposMemoriaSuportados": [],
        },
    }
    request = MetaAiWhatsappEnrichmentRequest(
        categoria="PROCESSADOR",
        nome="AMD Ryzen 5 8400F",
        payload=payload,
        resposta="Supported Memory Types: DDR5-5200\nCores: 6\nThreads: 12\nL3 Cache: 16 MB\nTDP: 65 W",
    )
    out = _meta_ai_whatsapp_enrich_sync(request)
    assert out["utilizado"] is True
    specs = out["payload"]["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["nucleos"] == 6
    assert specs["threads"] == 12
    assert out["coberturaDepois"] > out["coberturaAntes"]
    assert "tiposMemoriaSuportados" in out["camposPreenchidos"]
