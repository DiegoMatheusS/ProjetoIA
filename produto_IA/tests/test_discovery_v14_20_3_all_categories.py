from src.discovery.sources import DiscoverySourceCatalog
from src.enrichment.core import complete_specs, technical_coverage
from src.enrichment.identity import text_matches_identity
from src.extractors.backend_schemas import SCHEMAS
from src.extractors.ml_specs import extract_specs


def test_v14_20_3_ram_catalog_extracts_kit_capacity_from_real_shape():
    raw = "Corsair Dominator Platinum + AF 16 GB DDR4-3600 Kit of 2"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "MEMORIA_RAM")
    assert specs["tipo"] == "DDR4"
    assert specs["frequenciaMhz"] == 3600
    assert specs["quantidadeModulos"] == 2
    assert specs["capacidadePorModuloGb"] == 8


def test_v14_20_3_ram_catalog_extracts_single_stick_and_cl():
    raw = "Corsair Dominator Platinum DDR4-2666 CL15 32 GB DDR4-2666 Kit of 1"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "MEMORIA_RAM")
    assert specs["tipo"] == "DDR4"
    assert specs["frequenciaMhz"] == 2666
    assert specs["quantidadeModulos"] == 1
    assert specs["capacidadePorModuloGb"] == 32
    assert specs["latenciaCl"] == 15


def test_v14_20_3_techpowerup_catalog_row_already_has_useful_gpu_specs():
    cells = [
        "Radeon RX 7600M Specs",
        "Navi 33",
        "Jan 4th, 2023",
        "PCIe 4.0 x16",
        "8 GB, GDDR6, 128 bit",
        "1500 MHz",
        "2000 MHz",
        "1792 / 112 / 64",
    ]
    specs = DiscoverySourceCatalog._techpowerup_summary(
        "AMD Radeon RX 7600M Specs", " | ".join(cells), cells
    )
    assert specs["gpu"] == "Radeon RX 7600M"
    assert specs["chipset"] == "Navi 33"
    assert specs["geracaoPcie"] == 4
    assert specs["larguraPcie"] == 16
    assert specs["memoriaVideoGb"] == 8
    assert specs["tipoMemoriaVideo"] == "GDDR6"
    assert specs["barramentoBits"] == 128
    assert specs["clockBaseMhz"] == 1500


def test_v14_20_3_techpowerup_parser_preserves_row_specs_without_detail():
    html = """
    <table><tbody><tr>
      <td><a href='/gpu-specs/radeon-rx-7600m.c4123'>AMD Radeon RX 7600M Specs</a></td>
      <td>Navi 33</td><td>Jan 4th, 2023</td><td>PCIe 4.0 x16</td>
      <td>8 GB, GDDR6, 128 bit</td><td>1500 MHz</td><td>2000 MHz</td><td>1792 / 112 / 64</td>
    </tr></tbody></table>
    """
    catalog = DiscoverySourceCatalog()
    catalog._fetch_html = lambda *a, **k: (html, "https://www.techpowerup.com/gpu-specs/", None)
    catalog._fetch_rendered_catalog = lambda *a, **k: (None, a[0], "NAO_NECESSARIO")
    items, error = catalog._techpowerup(limit=1)
    assert error is None
    assert len(items) == 1
    assert items[0].nome == "AMD Radeon RX 7600M"
    assert items[0].resumo["specs"]["memoriaVideoGb"] == 8
    assert items[0].resumo["specs"]["barramentoBits"] == 128


def test_v14_20_3_gpu_generic_parser_understands_techpowerup_detail_labels():
    attrs = [
        {"name": "Graphics Processor", "value_name": "Heathrow"},
        {"name": "GPU Name", "value_name": "Heathrow"},
        {"name": "Architecture", "value_name": "GCN 1.0"},
        {"name": "Memory Size", "value_name": "2 GB"},
        {"name": "Memory Type", "value_name": "GDDR5"},
        {"name": "Bus Width", "value_name": "128 bit"},
        {"name": "Bus Interface", "value_name": "PCIe 3.0 x16"},
        {"name": "GPU Clock", "value_name": "800 MHz"},
        {"name": "TDP", "value_name": "45 W"},
    ]
    specs = extract_specs("PLACA_VIDEO", attrs, "AMD Radeon HD 7870M")
    assert specs["gpu"] == "Heathrow"
    assert specs["arquitetura"] == "GCN 1.0"
    assert specs["memoriaVideoGb"] == 2
    assert specs["tipoMemoriaVideo"] == "GDDR5"
    assert specs["barramentoBits"] == 128
    assert specs["geracaoPcie"] == 3
    assert specs["larguraPcie"] == 16
    assert specs["clockBaseMhz"] == 800
    assert specs["consumoWatts"] == 45


def test_v14_20_3_pc_kombo_gpu_compact_line_is_not_zero_percent():
    raw = "GIGABYTE Radeon RX 7600 Gaming OC Radeon RX 7600 8 GB 165W"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "PLACA_VIDEO")
    assert specs["gpu"] == "Radeon RX 7600"
    assert specs["memoriaVideoGb"] == 8
    assert specs["consumoWatts"] == 165
    result = {"categoriaDetectada": "PLACA_VIDEO", "especificacoesEncontradas": specs}
    assert technical_coverage(result) > 0


def test_v14_20_3_motherboard_catalog_extracts_identity_compatibility_fields():
    raw = "ASUS TUF GAMING B650-PLUS ATX Socket AM5 Chipset B650 4 Ramslots DDR5"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "PLACA_MAE")
    assert specs["formato"] == "ATX"
    assert specs["socket"] == "AM5"
    assert specs["chipset"] == "B650"
    assert specs["slotsMemoria"] == 4
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]


def test_v14_20_3_storage_catalog_extracts_core_fields():
    raw = "Samsung 990 PRO 2 TB NVMe PCIe 4.0 x4 M.2 2280 Read 7450 MB/s Write 6900 MB/s"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "ARMAZENAMENTO")
    assert specs["tipo"] == "SSD"
    assert specs["capacidadeGb"] == 2048
    assert specs["interface"] == "NVME_PCIE"
    assert specs["formato"] == "M2"
    assert specs["tamanhoM2Mm"] == 80
    assert specs["geracaoPcie"] == 4
    assert specs["pistasPcie"] == 4
    assert specs["leituraSequencialMbps"] == 7450
    assert specs["escritaSequencialMbps"] == 6900


def test_v14_20_3_psu_catalog_extracts_core_fields():
    raw = "Corsair RM850e 80 PLUS Gold modular ATX 3.1 850W"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "FONTE")
    assert specs["formato"] == "ATX"
    assert specs["potenciaWatts"] == 850
    assert specs["certificacao"] == "80 PLUS Gold"
    assert specs["modularidade"] == "MODULAR"
    assert specs["padraoAtx"] == "3.1"


def test_v14_20_3_case_catalog_extracts_size_and_board_support():
    raw = "Corsair 4000D Airflow Tempered Glass Midi-Tower - black Window E-ATX"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "GABINETE")
    assert specs["tamanho"] == "MID_TOWER"
    assert "E_ATX" in specs["formatosPlacaMaeSuportados"]


def test_v14_20_3_cooler_catalog_extracts_socket_fans_and_thermal_data():
    raw = "Thermalright Peerless Assassin 120 SE 2x 120mm TDP 245W 155mm Height For socket 1700, AM4, AM5"
    specs = DiscoverySourceCatalog._pc_kombo_summary(raw, "COOLER")
    assert specs["tipo"] == "AIR_COOLER"
    assert "LGA1700" in specs["socketsSuportados"]
    assert "AM5" in specs["socketsSuportados"]
    assert specs["quantidadeVentoinhas"] == 2
    assert specs["tamanhoVentoinhaMm"] == 120
    assert specs["capacidadeTermicaWatts"] == 245


def test_v14_20_3_fan_generic_parser_extracts_main_fields():
    text = "120 mm PWM 4-pin 600-2100 RPM 74.9 CFM 2.8 mm H2O 25.8 dBA 12 V ARGB"
    specs = extract_specs("VENTOINHA", [], text)
    assert specs["tamanhoMm"] == 120
    assert specs["rpmMinima"] == 600
    assert specs["rpmMaxima"] == 2100
    assert specs["fluxoArCfm"] == 74.9
    assert specs["pressaoEstaticaMmH2o"] == 2.8
    assert specs["ruidoDb"] == 25.8
    assert specs["conector"] == "PWM_4_PINOS"
    assert specs["pwm"] is True
    assert specs["argb"] is True


def test_v14_20_3_ram_identity_accepts_catalog_suffix_when_page_confirms_same_sku():
    identity = {
        "metodo": "MARCA_MODELO",
        "marca": "Corsair",
        "modelo": "Dominator Platinum 16 GB DDR4-3600 Kit of 2",
    }
    page = "Corsair Dominator Platinum Size 16 GB Ram Type DDR4-3600 Clock 3600 Sticks 2"
    assert text_matches_identity(identity, page) is True


def test_v14_20_3_every_hardware_category_can_return_full_schema_keys():
    for category in (
        "PROCESSADOR", "PLACA_MAE", "MEMORIA_RAM", "PLACA_VIDEO", "ARMAZENAMENTO",
        "FONTE", "GABINETE", "COOLER", "VENTOINHA",
    ):
        completed = complete_specs(category, {})
        assert list(completed.keys()) == SCHEMAS[category][2]
        assert all(value is None for value in completed.values())
