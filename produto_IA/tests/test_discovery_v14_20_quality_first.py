from src.api import HardwareDiscoveryRequest
from src.discovery.sources import DiscoverySourceCatalog, PC_KOMBO_CATALOGS
from src.enrichment.core import technical_coverage, technical_status, essential_missing_fields
from src.extractors.ml_specs import extract_specs


def test_v14_20_discovery_defaults_to_detail_and_enrichment():
    req = HardwareDiscoveryRequest(categoria="MEMORIA_RAM")
    assert req.detalhar is True
    assert req.enriquecer is True


def test_v14_20_pc_kombo_ram_uses_real_catalog_path():
    assert PC_KOMBO_CATALOGS["MEMORIA_RAM"] == (
        "https://www.pc-kombo.com/us/components/ram",
        "/us/product/ram/",
    )


def test_v14_20_pc_kombo_ram_catalog_extracts_core_specs():
    text = "Corsair Vengeance RGB DDR5-6000 CL30 2x16 GB DIMM 1.35 V XMP"
    specs = DiscoverySourceCatalog._pc_kombo_summary(text, "MEMORIA_RAM")
    assert specs["tipo"] == "DDR5"
    assert specs["frequenciaMhz"] == 6000
    assert specs["latenciaCl"] == 30
    assert specs["quantidadeModulos"] == 2
    assert specs["capacidadePorModuloGb"] == 16
    assert specs["formato"] == "DIMM"
    assert specs["tensaoVolts"] == 1.35
    assert specs["suportaXmp"] is True


def test_v14_20_ram_parser_understands_english_technical_labels():
    attrs = [
        {"name": "Memory Type", "value_name": "DDR5"},
        {"name": "Form Factor", "value_name": "DIMM"},
        {"name": "Number of modules", "value_name": "2"},
        {"name": "Capacity per module", "value_name": "16 GB"},
        {"name": "Memory Speed", "value_name": "6000 MHz"},
        {"name": "CAS Latency", "value_name": "30"},
        {"name": "Voltage", "value_name": "1.35 V"},
    ]
    specs = extract_specs("MEMORIA_RAM", attrs, "Corsair DDR5 XMP")
    assert specs["tipo"] == "DDR5"
    assert specs["formato"] == "DIMM"
    assert specs["quantidadeModulos"] == 2
    assert specs["capacidadePorModuloGb"] == 16
    assert specs["frequenciaMhz"] == 6000
    assert specs["latenciaCl"] == 30
    assert specs["tensaoVolts"] == 1.35


def test_v14_20_weighted_coverage_values_essential_fields_more():
    strong = {
        "categoriaDetectada": "PROCESSADOR",
        "especificacoesEncontradas": {
            "socket": "AM5", "nucleos": 6, "threads": 12,
            "frequenciaBaseMhz": 3800, "frequenciaTurboMhz": 5100,
            "tdpWatts": 65, "cacheL3Mb": 32,
            "tiposMemoriaSuportados": ["DDR5"], "versaoPcie": "5.0",
        },
    }
    weak = {
        "categoriaDetectada": "PROCESSADOR",
        "especificacoesEncontradas": {
            "familia": "Ryzen 5", "linha": "Ryzen", "geracao": "7000",
            "arquitetura": "Zen 4", "litografiaNm": 5, "dataLancamento": "2022",
            "coolerIncluso": True, "multiplicadorDesbloqueado": True,
            "suporteOverclock": True,
        },
    }
    assert technical_coverage(strong) > technical_coverage(weak)


def test_v14_20_status_respects_threshold_and_essential_fields():
    ready = {
        "categoriaDetectada": "MEMORIA_RAM",
        "especificacoesEncontradas": {
            "tipo": "DDR5", "formato": "DIMM", "capacidadePorModuloGb": 16,
            "quantidadeModulos": 2, "frequenciaMhz": 6000,
            "frequenciaJedecMhz": 4800, "latenciaCl": 30, "tensaoVolts": 1.35,
            "ecc": False, "registrada": False, "suportaXmp": True,
            "suportaExpo": False, "rgb": True, "alturaMm": 44,
        },
    }
    assert technical_coverage(ready) >= 0.80
    assert essential_missing_fields(ready) == []
    assert technical_status(ready) == "PRONTO"

    missing_essential = {
        "categoriaDetectada": "MEMORIA_RAM",
        "especificacoesEncontradas": dict(ready["especificacoesEncontradas"]),
    }
    missing_essential["especificacoesEncontradas"].pop("frequenciaMhz")
    assert technical_status(missing_essential) != "PRONTO"


def test_v14_20_cooler_extracts_airflow():
    specs = extract_specs("COOLER", [], "Air cooler AM5 LGA1700 120 mm 2100 RPM 74.9 CFM 25.8 dB RGB")
    assert specs["fluxoArCfm"] == 74.9
    assert specs["velocidadeMaxRpm"] == 2100
    assert specs["ruidoDb"] == 25.8
