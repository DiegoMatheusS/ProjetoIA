from src.discovery.core import HardwareDiscoveryService
from src.discovery.sources import DiscoveryCandidate, DiscoverySourceCatalog
from src.enrichment.core import technical_coverage
from src.extractors.ml_specs import extract_specs


def test_v14_20_4_ram_corsair_desktop_family_is_not_left_at_42_percent():
    text = "Corsair Vengeance LPX Series red DDR4-3200 16 GB DDR4-3200 Kit of 2 CL16"
    specs = extract_specs("MEMORIA_RAM", [], text)
    assert specs["tipo"] == "DDR4"
    assert specs["formato"] == "DIMM"
    assert specs["quantidadeModulos"] == 2
    assert specs["capacidadePorModuloGb"] == 8
    assert specs["frequenciaMhz"] == 3200
    assert specs["latenciaCl"] == 16
    assert specs["ecc"] is False
    assert specs["registrada"] is False
    assert specs["suportaXmp"] is True
    coverage = technical_coverage({"categoriaDetectada": "MEMORIA_RAM", "especificacoesEncontradas": specs})
    assert coverage >= 0.65


def test_v14_20_4_motherboard_understands_pc_kombo_detail_labels():
    attrs = [
        {"name": "Socket", "value_name": "AM5"},
        {"name": "Chipset", "value_name": "B650"},
        {"name": "Form Factor", "value_name": "ATX"},
        {"name": "Memory Type", "value_name": "DDR5"},
        {"name": "Memory Capacity", "value_name": "128"},
        {"name": "Ramslots", "value_name": "4"},
        {"name": "SATA", "value_name": "2"},
        {"name": "M.2 (PCI-E 3.0)", "value_name": "0"},
        {"name": "M.2 (PCI-E 4.0)", "value_name": "2"},
        {"name": "PCI-E 3.0 x16", "value_name": "0"},
        {"name": "PCI-E 4.0 x16", "value_name": "2"},
        {"name": "HDMI", "value_name": "1"},
        {"name": "Display Port", "value_name": "1"},
        {"name": "DVI", "value_name": "0"},
        {"name": "VGA", "value_name": "0"},
    ]
    specs = extract_specs("PLACA_MAE", attrs, "ASRock B650 Live Mixer")
    assert specs["socket"] == "AM5"
    assert specs["chipset"] == "B650"
    assert specs["formato"] == "ATX"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["slotsMemoria"] == 4
    assert specs["capacidadeMaximaMemoriaGb"] == 128
    assert specs["portasSata"] == 2
    assert specs["slotsM2"] == 2
    assert specs["versaoPcie"] == "4.0"
    assert specs["saidasVideo"] == ["HDMI", "DisplayPort"]


def test_v14_20_4_gpu_reference_key_matches_aib_compact_names():
    key = DiscoverySourceCatalog._gpu_reference_key
    assert key("Sapphire Pulse Radeon RX 6600 Gaming") == "rx6600"
    assert key("ASRock Radeon RX 9070 XT Taichi OC") == "rx9070xt"
    assert key("ASUS Dual RTX5060TI-O16G") == "rtx5060ti"
    assert key("ASRock Arc B580 Challenger OC") == "arcb580"


def test_v14_20_4_gpu_reference_merge_completes_pc_kombo_candidate_without_per_item_search():
    catalog = DiscoverySourceCatalog()
    candidate = DiscoveryCandidate(
        nome="ASUS Dual RTX5060TI-O16G",
        url="https://www.pc-kombo.com/us/product/gpu/example",
        fonte="PC_KOMBO",
        resumo={"specs": {"gpu": "RTX5060TI", "memoriaVideoGb": 16, "consumoWatts": 180}},
    )
    reference = {
        "rtx5060ti": {
            "fonte": "TECHPOWERUP",
            "url": "https://www.techpowerup.com/gpu-specs/geforce-rtx-5060-ti.c0000",
            "specs": {
                "gpu": "GeForce RTX 5060 Ti",
                "chipset": "GB206",
                "geracaoPcie": 5,
                "larguraPcie": 8,
                "memoriaVideoGb": 16,
                "tipoMemoriaVideo": "GDDR7",
                "barramentoBits": 128,
                "clockBaseMhz": 2407,
            },
        }
    }
    merged = catalog._merge_gpu_reference_specs([candidate], reference)
    assert merged == 1
    specs = candidate.resumo["specs"]
    assert specs["consumoWatts"] == 180
    assert specs["tipoMemoriaVideo"] == "GDDR7"
    assert specs["barramentoBits"] == 128
    assert specs["geracaoPcie"] == 5
    assert specs["larguraPcie"] == 8
    assert candidate.resumo["reference_sources"][0]["fonte"] == "TECHPOWERUP"


def test_v14_20_4_gpu_discover_merges_reference_catalog_even_when_pc_kombo_fills_limit(monkeypatch):
    catalog = DiscoverySourceCatalog()
    pc_items = [
        DiscoveryCandidate(
            nome="Sapphire Pulse Radeon RX 6600 Gaming",
            url="https://www.pc-kombo.com/us/product/gpu/rx6600",
            fonte="PC_KOMBO",
            resumo={"specs": {"gpu": "Radeon RX 6600", "memoriaVideoGb": 8, "consumoWatts": 132}},
        )
    ]
    monkeypatch.setattr(catalog, "_pc_kombo", lambda *a, **k: (pc_items, None))
    monkeypatch.setattr(catalog, "_techpowerup_reference_index", lambda: ({
        "rx6600": {
            "fonte": "TECHPOWERUP",
            "url": "https://www.techpowerup.com/gpu-specs/radeon-rx-6600.c0000",
            "specs": {
                "gpu": "Radeon RX 6600", "chipset": "Navi 23", "geracaoPcie": 4,
                "larguraPcie": 8, "memoriaVideoGb": 8, "tipoMemoriaVideo": "GDDR6",
                "barramentoBits": 128, "clockBaseMhz": 1626,
            },
        }
    }, None))
    items, diagnostics = catalog.discover("PLACA_VIDEO", limit=1)
    assert len(items) == 1
    assert items[0].resumo["specs"]["tipoMemoriaVideo"] == "GDDR6"
    assert any(x.get("fonte") == "TECHPOWERUP" and x.get("mesclados") == 1 for x in diagnostics)


class _FakeCatalog:
    allow_browser_fallback = False
    resolver = None

    def discover(self, **kwargs):
        return [
            DiscoveryCandidate(
                nome="AMD Ryzen 5 7600X",
                url="https://example.com/7600x",
                fonte="PC_KOMBO",
                marca="AMD",
                resumo={"specs": {"socket": "AM5", "nucleos": 6, "threads": 12}},
            )
        ], []


def test_v14_20_4_all_missing_fields_have_explicit_campos_ainda_ausentes_alias():
    service = HardwareDiscoveryService(catalog=_FakeCatalog())
    result = service.discover("PROCESSADOR", limite=1, detalhar=False, enriquecer=False, no_browser=True)
    item = result["itens"][0]
    assert item["camposAusentes"]
    assert item["camposAindaAusentes"] == item["camposAusentes"]
