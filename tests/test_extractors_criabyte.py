from src.extractors.ml_specs import extract_specs


def attr(name, value, aid=None):
    return {"id": aid or name.upper().replace(" ", "_"), "name": name, "value_name": value}


def test_cpu_does_not_store_instruction_set_as_microarchitecture():
    attrs = [
        attr("Socket", "AM5", "CPU_SOCKET"),
        attr("Arquitetura", "x86-64", "ARCHITECTURE"),
        attr("Tipo de memória RAM", "DDR5", "RAM_MEMORY_TYPE"),
    ]
    specs = extract_specs("PROCESSADOR", attrs, "Processador Ryzen")
    assert specs["socket"] == "AM5"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert "arquitetura" not in specs


def test_motherboard():
    text = "Placa-mãe Socket: AM5 Chipset: B650 Formato: ATX 4 x DIMM DDR5 Wi-Fi 6 Bluetooth 5.2 XMP EXPO HDMI DisplayPort"
    specs = extract_specs("PLACA_MAE", [], text)
    assert specs["socket"] == "AM5"
    assert specs["chipset"] == "B650"
    assert specs["formato"] == "ATX"
    assert specs["slotsMemoria"] == 4
    assert specs["wifi"] is True
    assert specs["bluetooth"] is True


def test_ram_kit():
    specs = extract_specs("MEMORIA_RAM", [], "Kit Memória RAM DDR5 DIMM 2x16GB 6000MHz CL30 1.35V XMP EXPO RGB")
    assert specs["tipo"] == "DDR5"
    assert specs["formato"] == "DIMM"
    assert specs["quantidadeModulos"] == 2
    assert specs["capacidadePorModuloGb"] == 16
    assert specs["frequenciaMhz"] == 6000
    assert specs["latenciaCl"] == 30
    assert specs["rgb"] is True


def test_gpu():
    text = "GeForce RTX 5070 12 GB GDDR7 PCIe 5.0 x16 Comprimento: 304 mm TGP: 250 W Fonte recomendada: 650 W 3 x DisplayPort 1 x HDMI"
    specs = extract_specs("PLACA_VIDEO", [], text)
    assert specs["memoriaVideoGb"] == 12
    assert specs["tipoMemoriaVideo"] == "GDDR7"
    assert specs["geracaoPcie"] == 5
    assert specs["larguraPcie"] == 16
    assert specs["comprimentoMm"] == 304
    assert specs["consumoWatts"] == 250
    assert specs["hdmi"] == 1
    assert specs["displayPort"] == 3


def test_storage_nvme():
    text = "SSD NVMe M.2 2280 1TB PCIe Gen4 x4 Leitura: 7000 MB/s Escrita: 6000 MB/s com dissipador"
    specs = extract_specs("ARMAZENAMENTO", [], text)
    assert specs["tipo"] == "SSD"
    assert specs["formato"] == "M2"
    assert specs["interface"] == "NVME_PCIE"
    assert specs["capacidadeGb"] == 1024
    assert specs["tamanhoM2Mm"] == 80
    assert specs["geracaoPcie"] == 4
    assert specs["pistasPcie"] == 4
    assert specs["possuiDissipador"] is True


def test_psu():
    specs = extract_specs("FONTE", [], "Fonte ATX 750W 80 Plus Gold totalmente modular ATX 3.1 OVP OCP SCP")
    assert specs["formato"] == "ATX"
    assert specs["potenciaWatts"] == 750
    assert "Gold" in specs["certificacao"]
    assert specs["modularidade"] == "MODULAR"
    assert specs["padraoAtx"] == "3.1"


def test_cooler_and_fan():
    cooler = extract_specs("COOLER", [], "Water Cooler AIO 360 mm compatível AM5 LGA1700 3 ventoinhas ARGB 2100 RPM 25 dB")
    assert cooler["tipo"] == "WATER_COOLER"
    assert "AM5" in cooler["socketsSuportados"]
    assert cooler["tamanhoRadiadorMm"] == 360
    assert cooler["argb"] is True

    fan = extract_specs("VENTOINHA", [], "Ventoinha 120 mm PWM 4 pinos 1800 RPM 62.5 CFM 1.8 mmH2O 25 dB ARGB")
    assert fan["tamanhoMm"] == 120
    assert fan["conector"] == "PWM_4_PINOS"
    assert fan["rpmMaxima"] == 1800
    assert fan["argb"] is True


def test_monitor_keyboard_headset():
    monitor = extract_specs("MONITOR", [], 'Monitor 27" 2560x1440 IPS 180Hz 1ms HDR FreeSync 2 x HDMI 1 x DisplayPort VESA 100x100')
    assert monitor["tamanhoPolegadas"] == 27
    assert monitor["resolucao"] == "2560x1440"
    assert monitor["taxaAtualizacaoHz"] == 180
    assert monitor["tipoPainel"] == "IPS"

    keyboard = extract_specs("TECLADO", [], "Teclado mecânico ABNT2 USB-C Bluetooth 2.4GHz RGB hot-swap 75%")
    assert keyboard["tipo"] == "Mecânico"
    assert keyboard["abnt2"] is True
    assert keyboard["rgb"] is True
    assert keyboard["hotSwap"] is True

    headset = extract_specs("HEADSET", [], "Headset Bluetooth wireless driver 50 mm microfone 7.1 bateria 30 h")
    assert headset["bluetooth"] is True
    assert headset["wireless"] is True
    assert headset["driverMm"] == 50
    assert headset["microfone"] is True
    assert headset["somSurround"] is True


def test_notebook_and_phone():
    notebook_attrs = [
        attr("Processador", "Intel Core i5-13420H", "PROCESSOR_MODEL"),
        attr("Memória RAM", "16 GB", "RAM_MEMORY_CAPACITY"),
        attr("Tipo de memória RAM", "DDR5", "RAM_MEMORY_TYPE"),
        attr("Capacidade de armazenamento", "512 GB", "STORAGE_CAPACITY"),
        attr("Tamanho da tela", '15.6"', "SCREEN_SIZE"),
        attr("Resolução da tela", "1920x1080", "SCREEN_RESOLUTION"),
    ]
    notebook = extract_specs("NOTEBOOK", notebook_attrs, "Notebook")
    assert notebook["processadorNome"] == "Intel Core i5-13420H"
    assert notebook["ramInstaladaGb"] == 16
    assert notebook["tipoMemoria"] == "DDR5"
    assert notebook["armazenamentoGb"] == 512
    assert notebook["resolucaoLargura"] == 1920

    phone_attrs = [
        attr("Memória RAM", "12 GB", "RAM_MEMORY_CAPACITY"),
        attr("Memória interna", "256 GB", "INTERNAL_MEMORY"),
        attr("Capacidade da bateria", "5000 mAh", "BATTERY_CAPACITY"),
    ]
    phone = extract_specs("CELULAR", phone_attrs, "Smartphone 5G NFC")
    assert phone["ramGb"] == 12
    assert phone["armazenamentoGb"] == 256
    assert phone["bateriaMah"] == 5000
    assert phone["cincoG"] is True
    assert phone["nfc"] is True
