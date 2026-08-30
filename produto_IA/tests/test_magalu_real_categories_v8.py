from src.extractors.ml_specs import extract_specs
from src.scrapers.magazine_scraper import MagazineScraper


def attrs(rows):
    return [{"id": None, "name": name, "value_name": value} for name, value in rows]


def test_gpu_magalu_aliases_and_reference_mpn():
    rows = attrs([
        ("Marca", "Palit"),
        ("Referência", "NE61650S1BG1117"),
        ("Modelo", "GeForce GTX 1650"),
        ("GPU", "GeForce GTX 1650"),
        ("Capacidade", "4GB"),
        ("Tipo de Memória", "GDDR5"),
        ("Interface de Memória", "128 Bits"),
        ("Barramento", "PCI-E 3.0x16"),
        ("Conexões", "- 2 Display Port - 1 HDMI"),
    ])
    generic = {
        "title": "Placa de Vídeo Palit GeForce GTX 1650 - 4GB GDDR5 128 Bits GamingPro OC",
        "brand": "Palit",
        "model": "GeForce GTX 1650",
        "mpn": "GeForce GTX 1650",  # JSON-LD ruim observado no Magalu
    }
    _, model, mpn = MagazineScraper._refine_identity(generic, rows)
    assert model == "GeForce GTX 1650"
    assert mpn == "NE61650S1BG1117"

    text = "A premiada arquitetura NVIDIA Turing. " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("PLACA_VIDEO", rows, text)
    assert specs["gpu"] == "GeForce GTX 1650"
    assert specs["arquitetura"] == "Turing"
    assert specs["memoriaVideoGb"] == 4
    assert specs["tipoMemoriaVideo"] == "GDDR5"
    assert specs["barramentoBits"] == 128
    assert specs["geracaoPcie"] == 3
    assert specs["larguraPcie"] == 16
    assert specs["displayPort"] == 2
    assert specs["hdmi"] == 1
    assert "comprimentoMm" not in specs  # dimensão de varejo/embalagem não vira tamanho da placa


def test_motherboard_magalu_detailed_fields():
    rows = attrs([
        ("Chipset", "AMD B850"),
        ("CPU", "Suporta processadores AMD Ryzen série 9000/8000/7000 para desktop | Socket AM5"),
        ("Memória", "4x DDR5 UDIMM, Capacidade máxima de memória 256 GB | Suporte de memória DDR5 8400 5600 (OC) MT/s / 5600 4800 (JEDEC) MT/s"),
        ("Armazenar", "4x M.2 (Qtd) | 4x SATA 6G (Qtd)"),
        ("Formato da Placa Mãe", "ATX"),
        ("Memória da Placa Mãe", "256 GB"),
        ("Soquete do Processador", "AM5"),
        ("Tipo de Memória", "DDR5 UDIMM"),
        ("LAN", "Realtek 8126VB 5G LAN"),
    ])
    text = " ".join(f"{r['name']}: {r['value_name']}" for r in rows) + " Wi-Fi 7 Bluetooth 5.4 AMD EXPO memória não ECC, sem buffer Flash BIOS HDMI PCIe 5.0"
    specs = extract_specs("PLACA_MAE", rows, text)
    assert specs["socket"] == "AM5"
    assert specs["chipset"] == "AMD B850"
    assert specs["formato"] == "ATX"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["formatosMemoriaSuportados"] == ["DIMM"]
    assert specs["slotsMemoria"] == 4
    assert specs["capacidadeMaximaMemoriaGb"] == 256
    assert specs["frequenciasMemoriaOverclockMhz"] == [8400, 5600]
    assert specs["frequenciasMemoriaJedecMhz"] == [5600, 4800]
    assert specs["portasSata"] == 4
    assert specs["wifi"] is True
    assert specs["bluetooth"] is True
    assert specs["suportaExpo"] is True
    assert specs["suportaEcc"] is False
    assert specs["suportaMemoriaRegistrada"] is False


def test_ram_magalu_aliases_and_embedded_part_number():
    rows = attrs([
        ("Características", "Marca: Rise Mode Gamer | Modelo: Z Series 8GB Preta | Part Number: RM-D4-8G-3200Z"),
        ("Especificações", "Capacidade: 8GB | 3200Mhz | DDR4-3200 | Latência: CL19-19-19-43 1.35v | 288-Pin DIMM"),
        ("Tipo de Memória", "DDR4"),
        ("Velocidade de Clock", "3200MHz"),
        ("Latência", "CL19"),
        ("Voltagem", "1.35v"),
        ("Modelo", "Z"),
        ("Referência", "RM-D4-8G-3200Z"),
    ])
    generic = {
        "title": "Memória RAM Rise Mode Z, 8GB, 3200MHz, DDR4, CL19, Preto - RM-D4-8G-3200Z",
        "brand": "Rise Mode",
        "model": "Z",
        "mpn": None,
    }
    _, _, mpn = MagazineScraper._refine_identity(generic, rows)
    assert mpn == "RM-D4-8G-3200Z"

    text = " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("MEMORIA_RAM", rows, text)
    assert specs["tipo"] == "DDR4"
    assert specs["formato"] == "DIMM"
    assert specs["frequenciaMhz"] == 3200
    assert specs["latenciaCl"] == 19
    assert specs["tensaoVolts"] == 1.35
    assert "quantidadeModulos" not in specs
    assert "capacidadePorModuloGb" not in specs
