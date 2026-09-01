import os

from src.main import build_result
from src.enrichment.core import should_auto_enrich, technical_missing_fields, TechnicalEnricher
from src.enrichment.providers import CPUWorldProvider, CPUMonkeyProvider, WikiChipProvider
from src.extractors.ml_specs import extract_specs


def _intel_incomplete_result():
    raw = {
        "ok": True,
        "title": "Processador Intel Core i5-9400F 9a Geracao 2.9GHz LGA1151 OEM",
        "brand": "Intel",
        "model": "Core i5-9400F",
        "mpn": None,
        "gtin": None,
        "description": "Intel Core i5-9400F 2.9 GHz LGA1151",
        "attributes": [
            {"name": "Socket", "value_name": "LGA1151"},
        ],
        "attributes_text": "Socket: LGA1151",
        "product_attributes": [],
        "url_original": "https://www.magazinevoce.com.br/produto/p/abc/in/prsd/",
        "url_final": "https://www.magazinevoce.com.br/produto/p/abc/in/prsd/",
        "price": 500.0,
        "source": "TESTE",
    }
    return build_result(raw, "PROCESSADOR")


def test_v14_12_missing_technical_fields_trigger_enrichment_even_without_required_only():
    result = _intel_incomplete_result()
    assert should_auto_enrich(result) is True
    missing = technical_missing_fields(result)
    assert "nucleos" in missing
    assert "threads" in missing
    assert "frequenciaTurboMhz" in missing


def test_v14_12_default_providers_include_cpu_sources():
    providers = TechnicalEnricher().providers
    assert any(isinstance(p, CPUWorldProvider) for p in providers)
    assert any(isinstance(p, CPUMonkeyProvider) for p in providers)
    assert any(isinstance(p, WikiChipProvider) for p in providers)


def test_v14_12_intel_ark_english_labels_are_parsed():
    text = """
    Intel Core i5-9400F Processor
    Code Name Products formerly Coffee Lake
    Lithography 14 nm
    Total Cores 6
    Total Threads 6
    Max Turbo Frequency 4.10 GHz
    Processor Base Frequency 2.90 GHz
    Intel Smart Cache 9 MB
    TDP 65 W
    Max Memory Size (dependent on memory type) 128 GB
    Memory Types DDR4-2666
    Max # of Memory Channels 2
    ECC Memory Supported No
    PCI Express Revision 3.0
    Max # of PCI Express Lanes 16
    Sockets Supported FCLGA1151
    T_JUNCTION 100°C
    Launch Date Q1'19
    """
    specs = extract_specs("PROCESSADOR", [], context_text=text)
    assert specs["socket"] == "LGA1151"
    assert specs["litografiaNm"] == 14
    assert specs["nucleos"] == 6
    assert specs["threads"] == 6
    assert specs["frequenciaBaseMhz"] == 2900
    assert specs["frequenciaTurboMhz"] == 4100
    assert specs["cacheL3Mb"] == 9
    assert specs["tdpWatts"] == 65
    assert specs["tiposMemoriaSuportados"] == ["DDR4"]
    assert specs["capacidadeMemoriaMaximaGb"] == 128
    assert specs["canaisMemoria"] == 2
    assert specs["suportaEcc"] is False
    assert str(specs["versaoPcie"]) == "3.0"
    assert specs["lanesPcie"] == 16
    assert specs["temperaturaMaximaC"] == 100


def test_v14_12_old_enrichment_auto_false_does_not_mean_disable(monkeypatch):
    # A política nova é expressa pelo helper: ENRICHMENT_AUTO é só enriquecimento
    # opcional; lacunas técnicas continuam obrigatórias salvo ENRICHMENT_DISABLE.
    monkeypatch.setenv("ENRICHMENT_AUTO", "false")
    monkeypatch.delenv("ENRICHMENT_DISABLE", raising=False)
    assert should_auto_enrich(_intel_incomplete_result()) is True


def test_v14_12_cpu_monkey_labels_are_parsed():
    attrs = [
        {"name": "Family", "value_name": "Intel Core i5"},
        {"name": "Architecture", "value_name": "Coffee Lake S Refresh"},
        {"name": "Technology", "value_name": "14 nm"},
        {"name": "Socket", "value_name": "LGA 1151-2"},
        {"name": "Generation", "value_name": "9"},
        {"name": "CPU Cores / Threads", "value_name": "6 / 6"},
        {"name": "Frequency", "value_name": "2.90 GHz"},
        {"name": "Turbo Frequency (1 Core)", "value_name": "4.10 GHz"},
        {"name": "L3-Cache", "value_name": "9.00 MB"},
        {"name": "Overclocking", "value_name": "No"},
        {"name": "GPU name", "value_name": "no iGPU"},
        {"name": "Max. Memory", "value_name": "128 GB"},
        {"name": "Memory channels", "value_name": "2"},
        {"name": "ECC", "value_name": "✗"},
        {"name": "PCIe", "value_name": "3.0 x 16"},
        {"name": "T. junction max.", "value_name": "100 °C"},
        {"name": "TDP", "value_name": "65 W"},
        {"name": "Release date", "value_name": "Q1/2019"},
    ]
    specs = extract_specs("PROCESSADOR", attrs, context_text="Intel Core i5-9400F DDR4-2666")
    assert specs["familia"] == "Intel Core i5"
    assert specs["arquitetura"] == "Coffee Lake S Refresh"
    assert specs["litografiaNm"] == 14
    assert specs["socket"] == "LGA1151"
    assert str(specs["geracao"]) == "9"
    assert specs["nucleos"] == 6
    assert specs["threads"] == 6
    assert specs["frequenciaBaseMhz"] == 2900
    assert specs["frequenciaTurboMhz"] == 4100
    assert specs["cacheL3Mb"] == 9
    assert specs["suporteOverclock"] is False
    assert specs["possuiVideoIntegrado"] is False
    assert specs["capacidadeMemoriaMaximaGb"] == 128
    assert specs["canaisMemoria"] == 2
    assert specs["suportaEcc"] is False
    assert str(specs["versaoPcie"]) == "3.0"
    assert specs["lanesPcie"] == 16
    assert specs["temperaturaMaximaC"] == 100
    assert specs["tdpWatts"] == 65


def test_v14_12_enricher_merges_external_cpu_specs_into_backend_payload():
    class FakeIntelProvider:
        name = "FABRICANTE_OFICIAL"

        def collect(self, identity, category):
            assert category == "PROCESSADOR"
            assert identity["marca"] == "Intel"
            return {
                "ok": True,
                "fonte": self.name,
                "url": "https://www.intel.com/example/i5-9400f",
                "attributes": [],
                "context_text": """
                Intel Core i5-9400F Processor
                Lithography 14 nm
                Total Cores 6
                Total Threads 6
                Max Turbo Frequency 4.10 GHz
                Processor Base Frequency 2.90 GHz
                Cache 9 MB Intel Smart Cache
                TDP 65 W
                Max Memory Size (dependent on memory type) 128 GB
                Memory Types DDR4-2666
                Max # of Memory Channels 2
                ECC Memory Supported No
                PCI Express Revision 3.0
                Max # of PCI Express Lanes 16
                Sockets Supported FCLGA1151
                T_JUNCTION 100°C
                Launch Date Q1'19
                """,
            }

    result = _intel_incomplete_result()
    enriched = TechnicalEnricher(providers=[FakeIntelProvider()]).enrich(result)
    specs = enriched["payloadParcialBackend"]["especificacaoProcessador"]
    assert specs["socket"] == "LGA1151"  # valor comercial preservado
    assert specs["nucleos"] == 6
    assert specs["threads"] == 6
    assert specs["frequenciaBaseMhz"] == 2900
    assert specs["frequenciaTurboMhz"] == 4100
    assert specs["tiposMemoriaSuportados"] == ["DDR4"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 2666
    assert specs["capacidadeMemoriaMaximaGb"] == 128
    assert "nucleos" in enriched["enriquecimentoTecnico"]["camposPreenchidos"]
    assert enriched["enriquecimentoTecnico"]["origemPorCampo"]["nucleos"]["fonte"] == "FABRICANTE_OFICIAL"


def test_v14_12_cpu_monkey_direct_url_for_i5_9400f():
    provider = CPUMonkeyProvider()
    url = provider._direct_url({"marca": "Intel", "modelo": "i5-9400F"})
    assert url == "https://www.cpu-monkey.com/en/cpu-intel_core_i5_9400f"
