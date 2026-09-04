import pytest

from src.extractors.dto_normalizer import normalize_specs_for_backend, normalize_hardware_payload_for_backend
from src.discovery.sources import DiscoverySourceCatalog


@pytest.mark.parametrize("raw,expected", [
    ("DDR4", ["DDR4"]),
    ("ddr4", ["DDR4"]),
    ("Ddr4", ["DDR4"]),
    ("DDR 4", ["DDR4"]),
    ("DDR4/DDR5", ["DDR4", "DDR5"]),
    ("ddr4, dDr5", ["DDR4", "DDR5"]),
    (["ddr5", "DDR4", "Ddr5"], ["DDR5", "DDR4"]),
])
def test_memory_types_accept_common_variations(raw, expected):
    out = normalize_specs_for_backend("PROCESSADOR", {"tiposMemoriaSuportados": raw})
    assert out["tiposMemoriaSuportados"] == expected


def test_ram_combined_memory_type_is_rejected_instead_of_invented():
    out = normalize_specs_for_backend("MEMORIA_RAM", {"tipo": "DDR4 / DDR5"})
    assert out["tipo"] is None


@pytest.mark.parametrize("raw,expected", [
    ("4.7 GHz", 4700),
    ("4,7 GHz", 4700),
    ("4700 MHz", 4700),
    ("DDR5-6000", 6000),
    ("ddr 4 3200", 3200),
])
def test_frequency_units_and_ddr_notation(raw, expected):
    category = "MEMORIA_RAM" if "DDR" in raw.upper() else "PROCESSADOR"
    field = "frequenciaMhz" if category == "MEMORIA_RAM" else "frequenciaBaseMhz"
    out = normalize_specs_for_backend(category, {field: raw})
    assert out[field] == expected


@pytest.mark.parametrize("raw,expected", [
    ("16 GB", 16),
    ("16gb", 16),
    ("1 TB", 1024),
    ("2048 MB", 2),
])
def test_capacity_units(raw, expected):
    out = normalize_specs_for_backend("ARMAZENAMENTO", {"capacidadeGb": raw})
    assert out["capacidadeGb"] == expected


def test_cache_converts_gb_to_mb():
    out = normalize_specs_for_backend("PROCESSADOR", {"cacheL3Mb": "0.03125 GB"})
    assert out["cacheL3Mb"] == 32.0


@pytest.mark.parametrize("raw,expected", [
    ("306 mm", 306.0),
    ("30.6 cm", 306.0),
    ("30,6 cm", 306.0),
])
def test_dimension_units(raw, expected):
    out = normalize_specs_for_backend("PLACA_VIDEO", {"comprimentoMm": raw})
    assert out["comprimentoMm"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("360 W", 360),
    ("0.65 kW", 650),
    ("0,65 kW", 650),
])
def test_power_units(raw, expected):
    out = normalize_specs_for_backend("FONTE", {"potenciaWatts": raw})
    assert out["potenciaWatts"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("SIM", True), ("sim", True), ("Yes", True), ("enabled", True),
    ("possui", True), ("presente", True), ("NÃO", False), ("nao", False),
    ("disabled", False), ("ausente", False), ("não possui", False),
])
def test_boolean_variations(raw, expected):
    out = normalize_specs_for_backend("MEMORIA_RAM", {"rgb": raw})
    assert out["rgb"] is expected


@pytest.mark.parametrize("raw,expected", [
    ("micro-atx", "MICRO_ATX"), ("Micro ATX", "MICRO_ATX"),
    ("mATX", "MICRO_ATX"), ("mini itx", "MINI_ITX"), ("E-ATX", "E_ATX"),
])
def test_motherboard_form_variations(raw, expected):
    out = normalize_specs_for_backend("PLACA_MAE", {"formato": raw})
    assert out["formato"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("M.2", "M2"), ("2280", "M2"), ("2.5 inch", "POLEGADAS_2_5"),
    ("3,5 polegadas", "POLEGADAS_3_5"), ("PCIe Add-in Card", "PLACA_PCIE"),
])
def test_storage_format_variations(raw, expected):
    out = normalize_specs_for_backend("ARMAZENAMENTO", {"formato": raw})
    assert out["formato"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("NVMe PCIe 4.0", "NVME_PCIE"), ("nvme", "NVME_PCIE"),
    ("SATA III", "SATA"), ("SAS 12Gb/s", "SAS"),
])
def test_storage_interface_variations(raw, expected):
    out = normalize_specs_for_backend("ARMAZENAMENTO", {"interface": raw})
    assert out["interface"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("M-Key", "M"), ("key m", "M"), ("B Key", "B"),
    ("B+M", "B_M"), ("B / M", "B_M"), ("b-m", "B_M"),
])
def test_m2_key_variations(raw, expected):
    out = normalize_specs_for_backend("ARMAZENAMENTO", {"chaveM2": raw})
    assert out["chaveM2"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("não modular", "NAO_MODULAR"), ("non-modular", "NAO_MODULAR"),
    ("semi modular", "SEMI_MODULAR"), ("full modular", "MODULAR"),
    ("modular", "MODULAR"),
])
def test_psu_modularity_variations(raw, expected):
    out = normalize_specs_for_backend("FONTE", {"modularidade": raw})
    assert out["modularidade"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("PWM 4-pin", "PWM_4_PINOS"), ("4 pinos", "PWM_4_PINOS"),
    ("3-pin", "DC_3_PINOS"), ("Molex", "MOLEX"), ("proprietário", "PROPRIETARIO"),
])
def test_fan_connector_variations(raw, expected):
    out = normalize_specs_for_backend("VENTOINHA", {"conector": raw})
    assert out["conector"] == expected


def test_motherboard_frequency_lists_ignore_ddr_generation_number():
    out = normalize_specs_for_backend("PLACA_MAE", {
        "frequenciasMemoriaOverclockMhz": "DDR5-7600 / 7200 / 6800 / 6400 MT/s (OC)",
    })
    assert out["frequenciasMemoriaOverclockMhz"] == [7600, 7200, 6800, 6400]


@pytest.mark.parametrize("raw,expected", [
    ("2020", None),
    ("07/2020", None),
    ("2020-07-21", "2020-07-21T00:00:00.000Z"),
    ("21 July 2020", "2020-07-21T00:00:00.000Z"),
    ("21 julho 2020", "2020-07-21T00:00:00.000Z"),
])
def test_release_date_variations(raw, expected):
    out = normalize_specs_for_backend("PROCESSADOR", {"dataLancamento": raw})
    assert out["dataLancamento"] == expected


def test_payload_final_barrier_keeps_only_backend_schema_and_safe_enums():
    out = normalize_hardware_payload_for_backend("PROCESSADOR", {
        "categoria": "processador",
        "nome": "CPU",
        "especificacaoProcessador": {
            "tiposMemoriaSuportados": "ddr4 + DDR5 / lpddr5",
            "frequenciaBaseMhz": "4.5 GHz",
            "dataLancamento": "2022",
            "campoQueNaoExiste": "x",
        },
    })
    spec = out["especificacaoProcessador"]
    assert spec["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert spec["frequenciaBaseMhz"] == 4500
    assert spec["dataLancamento"] is None
    assert "campoQueNaoExiste" not in spec


def test_pc_kombo_motherboard_summary_extracts_more_from_dense_row():
    specs = DiscoverySourceCatalog._pc_kombo_summary(
        "ASRock B650 LiveMixer ATX Socket AM5 Chipset B650 4 Ramslots DDR5 DIMM Max Memory 192 GB "
        "4x SATA 3x M.2 PCIe 4.0 Wi-Fi 6E Bluetooth 5.2 2.5GbE XMP EXPO HDMI DisplayPort BIOS Flashback",
        "PLACA_MAE",
    )
    assert specs["socket"] == "AM5"
    assert specs["chipset"] == "B650"
    assert specs["slotsMemoria"] == 4
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["formatosMemoriaSuportados"] == ["DIMM"]
    assert specs["capacidadeMaximaMemoriaGb"] == 192
    assert specs["portasSata"] == 4
    assert specs["slotsM2"] == 3
    assert specs["versaoPcie"] == "4.0"
    assert specs["wifi"] is True and specs["bluetooth"] is True
    assert specs["suportaXmp"] is True and specs["suportaExpo"] is True
    assert "HDMI" in specs["saidasVideo"] and "DisplayPort" in specs["saidasVideo"]


def test_pc_kombo_gpu_summary_extracts_dense_row_fields():
    specs = DiscoverySourceCatalog._pc_kombo_summary(
        "ASUS RTX 5080 GeForce RTX 5080 16 GB GDDR7 256 bit PCIe 5.0 x16 Base Clock 2295 MHz "
        "Boost Clock 2617 MHz Length 30.6 cm 2.5 slots 360W Recommended PSU 850W "
        "1x 12V-2x6 1x HDMI 3x DisplayPort",
        "PLACA_VIDEO",
    )
    assert specs["memoriaVideoGb"] == 16
    assert specs["tipoMemoriaVideo"] == "GDDR7"
    assert specs["barramentoBits"] == 256
    assert specs["geracaoPcie"] == 5 and specs["larguraPcie"] == 16
    assert specs["clockBaseMhz"] == 2295 and specs["clockBoostMhz"] == 2617
    assert specs["comprimentoMm"] == 306.0
    assert specs["slotsOcupados"] == 2.5
    assert specs["potenciaFonteRecomendadaWatts"] == 850
    assert specs["conectores12v2x6"] == 1
    assert specs["hdmi"] == 1 and specs["displayPort"] == 3


def test_pc_kombo_storage_psu_case_dense_rows():
    storage = DiscoverySourceCatalog._pc_kombo_summary(
        "Samsung 990 Pro 2 TB SSD NVMe PCIe 4.0 x4 M.2 2280 M-Key Read 7450 MB/s Write 6900 MB/s with heatsink Power 7.8 W",
        "ARMAZENAMENTO",
    )
    assert storage["capacidadeGb"] == 2048
    assert storage["tipo"] == "SSD" and storage["interface"] == "NVME_PCIE"
    assert storage["geracaoPcie"] == 4 and storage["pistasPcie"] == 4
    assert storage["leituraSequencialMbps"] == 7450 and storage["escritaSequencialMbps"] == 6900
    assert storage["chaveM2"] == "M" and storage["possuiDissipador"] is True

    psu = DiscoverySourceCatalog._pc_kombo_summary(
        "Corsair RM850x ATX 850W 80 PLUS Gold full modular ATX 3.1 Efficiency 90% 1x 24-pin 2x CPU 8-pin "
        "4x PCIe 6+2-pin 1x 12V-2x6 14x SATA 4x Molex OVP UVP OCP OPP OTP SCP Input 100-240V",
        "FONTE",
    )
    assert psu["potenciaWatts"] == 850 and psu["modularidade"] == "MODULAR"
    assert psu["padraoAtx"] == "3.1"
    assert psu["conectoresAtx24Pinos"] == 1 and psu["conectoresEpsCpu"] == 2
    assert psu["conectoresPcie8Pinos"] == 4 and psu["conectores12v2x6"] == 1
    assert "OVP" in psu["protecoes"] and "SCP" in psu["protecoes"]

    case = DiscoverySourceCatalog._pc_kombo_summary(
        "NZXT H7 Flow Mid Tower ATX Micro-ATX Mini-ITX Dimensions 505 x 230 x 480 mm "
        "GPU Clearance 400 mm CPU Cooler Clearance 185 mm PSU Clearance 200 mm Expansion Slots 7 vertical GPU",
        "GABINETE",
    )
    assert case["tamanho"] == "MID_TOWER"
    assert case["alturaMm"] == 505 and case["larguraMm"] == 230 and case["profundidadeMm"] == 480
    assert case["comprimentoMaximoGpuMm"] == 400
    assert case["alturaMaximaCoolerCpuMm"] == 185
    assert case["slotsTraseiros"] == 7 and case["suportaGpuVertical"] is True
