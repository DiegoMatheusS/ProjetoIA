from src.extractors.ml_specs import extract_specs
from src.scrapers.magazine_scraper import MagazineScraper


def attrs(rows):
    return [{"id": None, "name": name, "value_name": value} for name, value in rows]


def test_ssd_kingston_nv3_real_page_fields():
    rows = attrs([
        ("Marca", "Kingston"),
        ("Recursos", "Desempenho Gen 4x4 NVMe PCIe | Até 6.000 MB/s de leitura, 4.000 MB/s de gravação"),
        ("Especificações", "Fator de forma: M.2 2280 | Interface: PCIe 4.0x4 NVMe | Capacidade: 1 TB | Leitura/escrita sequencial: 6.000/4.000 MB/s"),
        ("Dimensão", "22 mm x 80 mm x 2,3 mm"),
        ("Modelo", "SNV3S/1000G"),
        ("Capacidade", "1TB"),
    ])
    text = "SSD Kingston NV3 1TB M.2 NVMe 2280 PCIe 4.0 Leitura 6000MBs e Gravação 4000MBs " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("ARMAZENAMENTO", rows, text)
    assert specs["tipo"] == "SSD"
    assert specs["formato"] == "M2"
    assert specs["interface"] == "NVME_PCIE"
    assert specs["capacidadeGb"] == 1024
    assert specs["tamanhoM2Mm"] == 80
    assert specs["geracaoPcie"] == 4
    assert specs["pistasPcie"] == 4
    assert specs["leituraSequencialMbps"] == 6000
    assert specs["escritaSequencialMbps"] == 4000
    assert specs["larguraMm"] == 22
    assert specs["profundidadeMm"] == 80
    assert specs["espessuraMm"] == 2.3


def test_psu_msi_real_page_non_modular_dimensions_and_connectors():
    rows = attrs([
        ("Características", "Marca: MSI | Modelo: 306-7ZP6B22-809"),
        ("Especificações", "Nome do produto MAG A600DN | Fator de forma ATX | Potência nominal 600W | Classificação de eficiência 80 Plus White (até 80%) | Modular Não | Dimensões (PxLxA) 150mm x 140mm x 86mm | Faixa de tensão de entrada110~240v | Proteção OCP,OVP,OPP,OTP,SCP,UVP | ATX (24 pinos) 1 | EPS (8 pinos) 1 | PCI-E (6+2 pinos) 2 | SATA (15 pinos) 5 | MOLEX (4 pinos) 2"),
        ("Dimensões do Produto", "150mm x 140mm x 86mm"),
        ("Modelo", "MAG A600DN"),
        ("Potência", "600W"),
    ])
    generic = {"title": "Fonte MSI MAG A600DN 600W - 306-7ZP6B22-809", "brand": "MSI", "model": "MAG A600DN", "mpn": "MAG A600DN"}
    _, model, mpn = MagazineScraper._refine_identity(generic, rows)
    assert model == "MAG A600DN"
    assert mpn == "306-7ZP6B22-809"
    text = " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("FONTE", rows, text)
    assert specs["formato"] == "ATX"
    assert specs["potenciaWatts"] == 600
    assert specs["modularidade"] == "NAO_MODULAR"
    assert specs["comprimentoMm"] == 150
    assert specs["larguraMm"] == 140
    assert specs["alturaMm"] == 86
    assert specs["conectoresAtx24Pinos"] == 1
    assert specs["conectoresEpsCpu"] == 1
    assert specs["conectoresPcie8Pinos"] == 2
    assert specs["conectoresSata"] == 5
    assert specs["conectoresMolex"] == 2
    assert specs["tensaoEntrada"] == "110~240v"


def test_case_pichau_real_page_without_inventing_external_dimensions():
    rows = attrs([
        ("Marca", "Pichau"),
        ("Modelo", "PG-ATOM-BK"),
        ("Referência", "PG-ATOM-BK"),
    ])
    text = (
        "Gabinete Gamer Pichau Atom Mini-Tower - PG-ATOM-BK "
        "Placa mãe suportada: Micro-ATX / ITX - Painel Frontal: Vidro temperado - "
        "Baias: 1x HDD 3.5\" 2x SSD 2.5\" - Slots de expansão: 4 - "
        "Ventoinhas Suportadas: Superior: 2x 120mm Traseiro: 1x 120mm Painel inferior: 2x 120mm - "
        "Altura Máxima do Cooler: 160 mm - Comprimento Máximo da GPU: 260 mm - Tipo de Fonte: ATX"
    )
    specs = extract_specs("GABINETE", rows, text)
    assert specs["tamanho"] == "MINI_TOWER"
    assert specs["formatosPlacaMaeSuportados"] == ["MICRO_ATX", "MINI_ITX"]
    assert specs["formatosFonteSuportados"] == ["ATX"]
    assert specs["comprimentoMaximoGpuMm"] == 260
    assert specs["alturaMaximaCoolerCpuMm"] == 160
    assert specs["baias25"] == 2
    assert specs["baias35"] == 1
    assert specs["slotsTraseiros"] == 4
    assert specs["suportesFans"] == [
        {"posicao": "TOPO", "tamanhoMm": 120, "quantidadeMaxima": 2},
        {"posicao": "TRASEIRA", "tamanhoMm": 120, "quantidadeMaxima": 1},
        {"posicao": "INFERIOR", "tamanhoMm": 120, "quantidadeMaxima": 2},
    ]
    assert "alturaMm" not in specs
    assert "larguraMm" not in specs
    assert "profundidadeMm" not in specs


def test_air_cooler_real_page_fields():
    rows = attrs([
        ("Especificações Técnicas", "TDP Máximo: 220W | Dimensões: 120 x 92 x 150mm"),
        ("Ventoinha", "Tamanho: 120 x 120 x 25mm | Velocidade: 2000 RPM +/- 10% | Fluxo de Ar: 74.9 CFM máximo | Pressão Estática: 2.85 mm H2O máximo | Nível de Ruído: Inferior ou igual a 27.8 dB(A) | Conector: 4 PIN PWM"),
        ("Compatibilidade Intel", "LGA 115X | LGA 1200 | LGA 1700 | LGA 1851"),
        ("Compatibilidade AMD", "AM4 | AM5"),
    ])
    text = "Air Cooler MACH1 STORM DIGITAL 120mm " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("COOLER", rows, text)
    assert specs["tipo"] == "AIR_COOLER"
    assert specs["socketsSuportados"] == ["LGA115X", "LGA1200", "LGA1700", "LGA1851", "AM4", "AM5"]
    assert specs["capacidadeTermicaWatts"] == 220
    assert specs["tamanhoVentoinhaMm"] == 120
    assert specs["espessuraVentoinhaMm"] == 25
    assert specs["ruidoDb"] == 27.8
    assert specs["velocidadeMaxRpm"] == 2000
    # 120x92x150 não traz rótulo L/A/P; não inventar eixos.
    assert "alturaMm" not in specs


def test_water_cooler_real_page_fields():
    rows = attrs([
        ("Especificações", "Tamanho da Ventoinha: 120 x 120 x 25 mm | Velocidade da Ventoinha: 800~1800±10% RPM | Número de Ventoinhas: 3 un. | Fluxo de Ar: 62 CFM | Iluminação: ARGB | TDP: 280W"),
        ("Compatibilidade", "Intel: LGA115X / 1200 / 1700 / 1366 / 2011 / 2066 | AMD: AM3 / AM4 / AM5"),
    ])
    text = "Water Cooler Husky Freezy ARGB 360mm AMD e Intel " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("COOLER", rows, text)
    assert specs["tipo"] == "WATER_COOLER"
    assert set(specs["socketsSuportados"]) == {"LGA115X", "LGA1200", "LGA1700", "LGA1366", "LGA2011", "LGA2066", "AM3", "AM4", "AM5"}
    assert specs["capacidadeTermicaWatts"] == 280
    assert specs["tamanhoRadiadorMm"] == 360
    assert specs["quantidadeVentoinhas"] == 3
    assert specs["tamanhoVentoinhaMm"] == 120
    assert specs["espessuraVentoinhaMm"] == 25
    assert specs["velocidadeMaxRpm"] == 1800
    assert specs["argb"] is True
    assert specs["rgb"] is True


def test_notebook_dell_real_page_fields_and_cm_to_mm():
    rows = attrs([
        ("Processador", "Intel Core i5 1334U"),
        ("Geração do Processador", "13ª Geração"),
        ("Velocidade do Processador", "Até 4.6GHz"),
        ("Memória RAM", "8GB"),
        ("Capacidade do Armazenamento", "512GB"),
        ("Sistema Operacional", "Windows 11"),
        ("Painel da Tela", "WVA"),
        ("Tamanho da Tela", "15.6\""),
        ("Resolução da Tela", "Full HD (1920x1080)"),
        ("Taxa de Atualização da Tela", "120 Hz"),
        ("Tipo de Placa de Vídeo", "Integrada"),
        ("Placa de Vídeo", "Intel UHD com memória gráfica compartilhada"),
        ("Conexões", "1 porta USB 2.0, 1 porta USB 3.2 Type-A de 1ª geração, 1 porta USB 3.2 Type-C de 1ª geração (somente dados)"),
        ("Conectividade", "Wi-Fi, Bluetooth"),
        ("Multimídia", "Webcam HD widescreen integrada (720p) com Single Digital Microphone"),
        ("Padrão de Teclado", "Numérico padrão em português"),
        ("Peso do Produto", "1,63kg"),
        ("Dimensões do Produto", "Largura: 35,85cm Altura: 1,89cm Profundidade: 23,55cm"),
    ])
    text = "Notebook Dell Inspiron 15 Intel Core i5 8GB RAM 512GB SSD 15.6 Full HD Windows 11 " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("NOTEBOOK", rows, text)
    assert specs["processadorNome"] == "Intel Core i5 1334U"
    assert specs["processadorMarca"] == "Intel"
    assert specs["clockTurboMhz"] == 4600
    assert specs["gpuNome"].startswith("Intel UHD")
    assert specs["gpuIntegrada"] is True
    assert specs["gpuDedicada"] is False
    assert specs["ramInstaladaGb"] == 8
    assert specs["armazenamentoGb"] == 512
    assert specs["tipoPainel"] == "WVA"
    assert specs["pesoKg"] == 1.63
    assert specs["larguraMm"] == 358.5
    assert specs["alturaMm"] == 18.9
    assert specs["profundidadeMm"] == 235.5
    assert specs["wifi"] == "Wi-Fi"
    assert specs["bluetooth"] == "Bluetooth"
    assert specs["usbA"] == 1
    assert specs["usbC"] == 1
    assert specs["resolucaoWebcam"] == "720p"
    assert specs["tecladoNumerico"] is True


def test_monitor_tcl_real_page_does_not_confuse_hdmi_version_with_count():
    rows = attrs([
        ("Tamanho da Tela", "27\""),
        ("Tipo de Display", "QD-Mini LED"),
        ("Painel da Tela", "HVA"),
        ("Resolução", "QHD (2560x1440)"),
        ("Taxa de Atualização da Tela", "180Hz"),
        ("Tempo de Resposta", "1ms (GTG)"),
        ("Conexões", "HDMI2.1, DP, Entrada Fone de Ouvido (P3), Entrada de energia"),
        ("Brilho", "Brilho (teste instantâneo): 600 nits. Brilho (teste de longa duração): 350cd/m2"),
        ("Padrão de Furação", "100x100mm"),
        ("Características", "HDR600. Compatível com FreeSync & G-SYNC."),
    ])
    text = "Monitor Gamer TCL 27 QHD MiniLED 180Hz 27G64 " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("MONITOR", rows, text)
    assert specs["tamanhoPolegadas"] == 27
    assert specs["resolucao"] == "2560x1440"
    assert specs["taxaAtualizacaoHz"] == 180
    assert specs["tipoPainel"] == "HVA"
    assert specs["tempoRespostaMs"] == 1
    assert specs["brilhoNits"] == 600
    assert specs["hdr"] is True
    assert specs["gSync"] is True
    assert specs["freeSync"] is True
    assert specs["vesa"] == "100x100"
    assert "hdmi" not in specs  # HDMI2.1 é versão, não "2 portas HDMI".
    assert "displayPort" not in specs  # DP sem quantidade explícita.
