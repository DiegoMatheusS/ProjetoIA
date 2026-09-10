from src.extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    merge_meta_ai_response_into_payload_detailed,
    parse_meta_ai_response,
)
from src.api import MetaAiWhatsappEnrichmentRequest, _meta_ai_whatsapp_enrich_sync


RYZEN_7900_RESPONSE = """AMD Ryzen 9 7900 - categoria PROCESSADOR:
Linha: Ryzen 9
Geracao: 7000
Arquitetura: Zen 4
LitografiaNm: 5
CacheL2Mb: 12
CacheL3Mb: 64
TdpWatts: 65
PossuiVideoIntegrado: Sim
ModeloVideoIntegrado: AMD Radeon Graphics
TiposMemoriaSuportados: DDR5-SDRAM
FrequenciaMemoriaMaximaMhz: 5200
CapacidadeMemoriaMaximaGb: 128
CanaisMemoria: 2
SuportaEcc: Sim
TemperaturaMaximaC: 95
VersaoPcie: 5.0
LanesPcie: 24
CoolerIncluso: Sim
"""


def test_real_ryzen_7900_regression_interprets_all_supported_fields():
    specs = parse_meta_ai_response("PROCESSADOR", RYZEN_7900_RESPONSE)
    expected = {
        "linha": "Ryzen 9",
        "geracao": "7000",
        "arquitetura": "Zen 4",
        "litografiaNm": 5,
        "cacheL2Mb": 12,
        "cacheL3Mb": 64,
        "tdpWatts": 65,
        "possuiVideoIntegrado": True,
        "modeloVideoIntegrado": "AMD Radeon Graphics",
        "tiposMemoriaSuportados": ["DDR5"],
        "frequenciaMemoriaMaximaMhz": 5200,
        "capacidadeMemoriaMaximaGb": 128,
        "canaisMemoria": 2,
        "suportaEcc": True,
        "temperaturaMaximaC": 95,
        "versaoPcie": "5.0",
        "lanesPcie": 24,
        "coolerIncluso": True,
    }
    for field, value in expected.items():
        assert specs[field] == value
    assert len(specs) >= len(expected)


def test_memory_normalization_and_embedded_frequency():
    specs = parse_meta_ai_response(
        "PROCESSADOR",
        "TiposMemoriaSuportados: DDR4 / DDR5-5600\n",
    )
    assert specs["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5600


def test_numbers_booleans_pcie_and_complete_date_are_normalized():
    specs = parse_meta_ai_response(
        "PROCESSADOR",
        """Litografia: 5 nm
Cache L2: 12 MB
TDP: 65 W
Max Memory: 128 GB
Max Temperature: 95 °C
PCI Express: PCIe Gen 5
PCIe Lanes: 24 lanes
Cooler incluso: Sim
Suporta ECC: Nao
Data de lançamento: 2023-01-10
""",
    )
    assert specs["litografiaNm"] == 5
    assert specs["cacheL2Mb"] == 12
    assert specs["tdpWatts"] == 65
    assert specs["capacidadeMemoriaMaximaGb"] == 128
    assert specs["temperaturaMaximaC"] == 95
    assert specs["versaoPcie"] == "5.0"
    assert specs["lanesPcie"] == 24
    assert specs["coolerIncluso"] is True
    assert specs["suportaEcc"] is False
    assert specs["dataLancamento"] == "2023-01-10T00:00:00.000Z"


def test_partial_date_is_not_invented():
    specs = parse_meta_ai_response("PROCESSADOR", "DataLancamento: 2023\n")
    assert "dataLancamento" not in specs


def test_merge_only_fills_gaps_preserving_false_zero_and_conflicts():
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "CPU Teste",
        "especificacaoProcessador": {
            "socket": "AM5",
            "suportaEcc": False,
            "lanesPcie": 0,
            "tiposMemoriaSuportados": [],
        },
    }
    text = """Socket: AM4
SuportaEcc: Sim
LanesPcie: 24
TiposMemoriaSuportados: DDR5-SDRAM
Arquitetura: Zen 4
"""
    after, filled, parsed, conflicts = merge_meta_ai_response_into_payload_detailed(
        "PROCESSADOR", payload, text
    )
    specs = after["especificacaoProcessador"]
    assert specs["socket"] == "AM5"
    assert specs["suportaEcc"] is False
    assert specs["lanesPcie"] == 0
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["arquitetura"] == "Zen 4"
    assert set(filled) == {"tiposMemoriaSuportados", "arquitetura"}
    assert parsed["socket"] == "AM4"
    assert {item["campo"] for item in conflicts} >= {"socket", "suportaEcc", "lanesPcie"}


def test_dynamic_prompt_requests_only_missing_fields():
    prompt = build_meta_ai_prompt(
        "PROCESSADOR",
        "AMD Ryzen 9 7900",
        ["linha", "tiposMemoriaSuportados", "dataLancamento"],
    )
    assert "- linha" in prompt
    assert "- tiposMemoriaSuportados" in prompt
    assert "- dataLancamento" in prompt
    assert "- socket\n" not in prompt
    assert "DDR3" in prompt and "DDR4" in prompt and "DDR5" in prompt
    assert "Não invente" in prompt


def test_unknown_field_is_ignored_by_real_schema():
    specs = parse_meta_ai_response(
        "PROCESSADOR",
        "Arquitetura: Zen 4\nCampoQueNaoExiste: qualquer coisa\nPreço: 999\n",
    )
    assert specs == {"arquitetura": "Zen 4"}


def test_markdown_list_and_table_are_accepted():
    specs = parse_meta_ai_response(
        "PROCESSADOR",
        """- **Litografia**: 5 nm
| Campo | Valor |
| --- | --- |
| Cache L3 | 64 MB |
| Supported Memory | DDR5-5200 |
""",
    )
    assert specs["litografiaNm"] == 5
    assert specs["cacheL3Mb"] == 64
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5200


def test_endpoint_recalculates_coverage_missing_status_and_fallback():
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 9 7900",
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 12,
            "threads": 24,
            "tiposMemoriaSuportados": [],
        },
    }
    req = MetaAiWhatsappEnrichmentRequest(
        categoria="PROCESSADOR",
        nome="AMD Ryzen 9 7900",
        payload=payload,
        resposta=RYZEN_7900_RESPONSE,
        forcar=True,
    )
    out = _meta_ai_whatsapp_enrich_sync(req)
    assert out["utilizado"] is True
    assert out["coberturaDepois"] > out["coberturaAntes"]
    assert "tiposMemoriaSuportados" in out["camposPreenchidos"]
    assert "tiposMemoriaSuportados" not in out["camposAusentes"]
    assert out["statusFicha"] in {"PRONTO", "PRECISA_REVISAO", "FICHA_INCOMPLETA"}
    assert out["metaAiWhatsappFallback"]["coberturaAtual"] == out["coberturaDepois"]
    assert out["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR5"]


def test_all_nine_hardware_categories_accept_canonical_fields_and_aliases():
    cases = {
        "PLACA_MAE": ("Memory Slots: 4\nPCI Express: 5.0\n", {"slotsMemoria": 4, "versaoPcie": "5.0"}),
        "MEMORIA_RAM": ("Tipo DDR: DDR5\nMemory Speed: 6000 MHz\n", {"tipo": "DDR5", "frequenciaMhz": 6000}),
        "PLACA_VIDEO": ("VRAM: 16 GB\nMemory Bus: 256 bit\n", {"memoriaVideoGb": 16, "barramentoBits": 256}),
        "ARMAZENAMENTO": ("Capacity: 2 TB\nSequential Read: 7450 MB/s\n", {"capacidadeGb": 2048, "leituraSequencialMbps": 7450}),
        "FONTE": ("Wattage: 850 W\nModularity: Full Modular\n", {"potenciaWatts": 850}),
        "GABINETE": ("Max GPU Length: 400 mm\nMax CPU Cooler Height: 170 mm\n", {"comprimentoMaximoGpuMm": 400, "alturaMaximaCoolerCpuMm": 170}),
        "COOLER": ("Noise: 25.8 dB\nAirflow: 74.9 CFM\n", {"ruidoDb": 25.8, "fluxoArCfm": 74.9}),
        "VENTOINHA": ("Fan Size: 120 mm\nMax RPM: 2000 RPM\n", {"tamanhoMm": 120, "rpmMaxima": 2000}),
    }
    for category, (text, expected) in cases.items():
        specs = parse_meta_ai_response(category, text)
        for field, value in expected.items():
            assert specs[field] == value, (category, field, specs)
