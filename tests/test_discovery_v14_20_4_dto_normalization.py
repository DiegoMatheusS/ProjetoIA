from src.enrichment.core import complete_specs
from src.extractors.dto_normalizer import normalize_specs_for_backend
from src.main import build_result


def test_processor_memory_enum_is_split_and_date_year_is_not_invented():
    specs = normalize_specs_for_backend("PROCESSADOR", {
        "tiposMemoriaSuportados": ["DDR4/DDR5"],
        "dataLancamento": "2020",
        "nucleos": "6 cores",
        "possuiVideoIntegrado": "Sim",
    })
    assert specs["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert specs["dataLancamento"] is None
    assert specs["nucleos"] == 6
    assert specs["possuiVideoIntegrado"] is True


def test_processor_complete_date_becomes_iso_8601():
    specs = normalize_specs_for_backend("PROCESSADOR", {"dataLancamento": "21 July 2020"})
    assert specs["dataLancamento"] == "2020-07-21T00:00:00.000Z"


def test_ambiguous_numeric_date_is_dropped():
    specs = normalize_specs_for_backend("PROCESSADOR", {"dataLancamento": "07/08/2020"})
    assert specs["dataLancamento"] is None


def test_motherboard_enums_lists_numbers_and_booleans_are_dto_safe():
    specs = normalize_specs_for_backend("PLACA_MAE", {
        "formato": "mATX",
        "tiposMemoriaSuportados": "DDR4, DDR5",
        "formatosMemoriaSuportados": "UDIMM / SO-DIMM",
        "slotsMemoria": "4 slots",
        "wifi": "yes",
        "versaoPcie": "PCIe 5",
    })
    assert specs["formato"] == "MICRO_ATX"
    assert specs["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert specs["formatosMemoriaSuportados"] == ["DIMM", "SO_DIMM"]
    assert specs["slotsMemoria"] == 4
    assert specs["wifi"] is True
    assert specs["versaoPcie"] == "5.0"


def test_ram_gpu_and_storage_final_types_are_safe():
    ram = normalize_specs_for_backend("MEMORIA_RAM", {
        "tipo": "DDR5-6000",
        "formato": "UDIMM",
        "capacidadePorModuloGb": "16 GB",
        "tensaoVolts": "1,35 V",
        "ecc": "Não",
    })
    assert ram == {
        "tipo": "DDR5", "formato": "DIMM", "capacidadePorModuloGb": 16,
        "tensaoVolts": 1.35, "ecc": False,
    }

    gpu = normalize_specs_for_backend("PLACA_VIDEO", {
        "memoriaVideoGb": "16 GB", "barramentoBits": "256-bit",
        "slotsOcupados": "2.5 slots", "saidasVideo": "1x HDMI, 3x DisplayPort",
    })
    assert gpu["memoriaVideoGb"] == 16
    assert gpu["barramentoBits"] == 256
    assert gpu["slotsOcupados"] == 2.5
    assert gpu["saidasVideo"] == ["1x HDMI", "3x DisplayPort"]

    storage = normalize_specs_for_backend("ARMAZENAMENTO", {
        "tipo": "NVMe SSD", "formato": "M.2 2280", "interface": "PCIe 4.0 NVMe",
        "capacidadeGb": "1000 GB", "possuiDissipador": "No",
    })
    assert storage["tipo"] == "SSD"
    assert storage["formato"] == "M2"
    assert storage["interface"] == "NVME_PCIE"
    assert storage["capacidadeGb"] == 1000
    assert storage["possuiDissipador"] is False


def test_psu_case_cooler_fan_enums_are_normalized():
    psu = normalize_specs_for_backend("FONTE", {
        "formato": "SFX-L", "modularidade": "Full modular", "potenciaWatts": "850 W",
    })
    assert psu["formato"] == "SFX_L"
    assert psu["modularidade"] == "MODULAR"
    assert psu["potenciaWatts"] == 850

    case = normalize_specs_for_backend("GABINETE", {
        "tamanho": "Mid Tower", "formatosPlacaMaeSuportados": "ATX / mATX / Mini-ITX",
        "formatosFonteSuportados": "ATX / SFX", "suportaGpuVertical": "Sim",
    })
    assert case["tamanho"] == "MID_TOWER"
    assert case["formatosPlacaMaeSuportados"] == ["ATX", "MICRO_ATX", "MINI_ITX"]
    assert case["formatosFonteSuportados"] == ["ATX", "SFX"]
    assert case["suportaGpuVertical"] is True

    cooler = normalize_specs_for_backend("COOLER", {
        "tipo": "AIO liquid cooler", "socketsSuportados": "AM5 / LGA 1700",
        "rgb": "yes", "fluxoArCfm": "74,9 CFM",
    })
    assert cooler["tipo"] == "WATER_COOLER"
    assert cooler["socketsSuportados"] == ["AM5", "LGA1700"]
    assert cooler["rgb"] is True
    assert cooler["fluxoArCfm"] == 74.9

    fan = normalize_specs_for_backend("VENTOINHA", {
        "conector": "4-pin PWM", "pwm": "true", "rpmMaxima": "2100 RPM",
    })
    assert fan["conector"] == "PWM_4_PINOS"
    assert fan["pwm"] is True
    assert fan["rpmMaxima"] == 2100


def test_invalid_enum_becomes_missing_instead_of_breaking_backend():
    specs = complete_specs("MEMORIA_RAM", {"tipo": "DDR4/DDR5", "formato": "qualquer"})
    assert specs["tipo"] is None
    assert specs["formato"] is None


def test_url_flow_also_uses_dto_normalization():
    raw = {
        "ok": True,
        "blocked": False,
        "title": "AMD Ryzen Test",
        "brand": "AMD",
        "model": "Ryzen Test",
        "description": "",
        "attributes_text": "",
        "attributes": [
            {"name": "Socket", "value_name": "AM5"},
            {"name": "Memory Types", "value_name": "DDR4/DDR5"},
            {"name": "Launch Date", "value_name": "2020"},
        ],
        "url_original": "https://example.com/item",
        "url_final": "https://example.com/item",
    }
    result = build_result(raw, "PROCESSADOR")
    specs = result["payloadParcialBackend"]["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert specs.get("dataLancamento") is None
