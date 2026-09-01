from src.extractors.category import detect_category
from src.extractors.ml_specs import extract_specs
from src.scrapers.magazine_scraper import MagazineScraper


def attrs(rows):
    return [{"id": None, "name": name, "value_name": value} for name, value in rows]


def test_v10_fonte_corsair_rm650e_modular():
    title = "Fonte CORSAIR RM650e, 650W, Platinum, Full Modular, ATX 3.1 e PCIe 5.1 - CP-9020302-BR"
    assert detect_category(title) == "FONTE"
    rows = attrs([
        ("Especificações", "Eficiência Cibenética: Ouro | Conector PATA: 2 | Conector EPS: 2 | Conector SATA: 6 | Dimensões: 140x150x86 | Modular: Completamente | Conector PCIe: 3 | Potência Contínua W: 650 Watts | Conector ATX: 1 | Versão ATX12V: 3.1"),
        ("Certificações", "Cybenetics Gold, PCIe 5.1"),
        ("Conectores da Fonte", "1x ATX, 2x EPS, 3x PCIe, 6x SATA, 2x PATA"),
        ("Dimensões do Produto", "140x150x86"),
        ("Padrão de Conexão da Fonte", "ATX 3.1"),
        ("Potência", "650W"),
    ])
    text = title + " cabo nativo 12V-2x6 " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("FONTE", rows, text)
    assert specs["formato"] == "ATX"
    assert specs["potenciaWatts"] == 650
    assert specs["modularidade"] == "MODULAR"
    assert specs["padraoAtx"] == "3.1"
    assert specs["conectoresAtx24Pinos"] == 1
    assert specs["conectoresEpsCpu"] == 2
    assert specs["conectoresPcie8Pinos"] == 3
    assert specs["conectoresSata"] == 6
    assert specs["conectoresMolex"] == 2
    assert specs["conectores12v2x6"] == 1


def test_v10_teclado_redragon_kumara():
    title = "Teclado Mecânico Gamer Redragon Kumara, RGB, Switch Outemu Brown, ABNT2 - K552RGB-1 (PT-BROWN)"
    assert detect_category(title) == "TECLADO"
    rows = attrs([
        ("Conectividade", "Com fio"),
        ("Conexões", "USB"),
        ("Padrão de Teclado", "ABNT2"),
        ("Switch", "Outemu Brown"),
        ("Tipo de Teclado", "Mecânico"),
        ("Especificações", "Switch removível | TKL/Porcentagem: 75% | Iluminação RGB"),
    ])
    text = title + " " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("TECLADO", rows, text)
    assert specs["tipo"] == "Mecânico"
    assert specs["layout"] == "ABNT2"
    assert specs["switch"] == "Outemu Brown"
    assert specs["tamanho"] == "TKL"
    assert specs["abnt2"] is True
    assert specs["usb"] is True
    assert specs["rgb"] is True
    assert specs["hotSwap"] is True


def test_v10_ram_corsair_ddr5_2x16():
    title = "Memória Ram Para PC 32GB Corsair Vengeance RGB DDR5 2x16Gb 6000Mhz CL36 CMH32GX5M2E6000C36W"
    assert detect_category(title) == "MEMORIA_RAM"
    rows = attrs([
        ("Quantidade", "2x16Gb"),
        ("Tipo de Memória", "DDR5"),
        ("Formato de memória de pacote", "DIMM"),
        ("Velocidade de Clock", "6000Mhz"),
        ("Latência", "CL36"),
        ("Voltagem", "1,40 V"),
        ("Iluminação", "RGB"),
    ])
    text = title + " Intel XMP " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("MEMORIA_RAM", rows, text)
    assert specs["tipo"] == "DDR5"
    assert specs["formato"] == "DIMM"
    assert specs["quantidadeModulos"] == 2
    assert specs["capacidadePorModuloGb"] == 16
    assert specs["frequenciaMhz"] == 6000
    assert specs["latenciaCl"] == 36
    assert specs["tensaoVolts"] == 1.4
    assert specs["rgb"] is True
    assert specs["suportaXmp"] is True


def test_v10_ventoinha_corsair_rs120():
    title = "Kit com 3 Ventoinhas Corsair RS120 ARGB, 120mm, PWM, Preto - CO-9050181-WW - Peças para Computador e Notebook"
    assert detect_category(title) == "VENTOINHA"
    text = title + " velocidades de até 2.100 RPM, conectadas em um único PWM de 4 pinos e cabeçote +5V ARGB"
    specs = extract_specs("VENTOINHA", [], text)
    assert specs["tamanhoMm"] == 120
    assert specs["rpmMaxima"] == 2100
    assert specs["conector"] == "PWM_4_PINOS"
    assert specs["pwm"] is True
    assert specs["argb"] is True
    assert specs["rgb"] is True


def test_v10_gpu_xfx_rx9070xt():
    title = "Placa de Vídeo XFX Swift RX 9070 XT, 16GB, GDDR6, HDMI 3xDP, RDNA 4 - RX-97TSWF3W9"
    assert detect_category(title) == "PLACA_VIDEO"
    rows = attrs([
        ("Especificações", "Tipo de barramento PCI-E 5.0 | Primárias clock base até 1660 MHz | Clock de reforço até: 2970 MHz | Barramento de memória: 256 bits | Tamanho da memória: 16 GB | Tipo de memória: GDDR6 | Perfil do cartão 3,5 slots"),
        ("Saídas", "DisplayPort 2.1: 3 x HDMI | 2.1: 1x"),
        ("Requisitos", "Alimentação externa 3x PCI-E 8 pinos conexões | Requisito mínimo de alimentação: 800 watts"),
        ("Dimensões", "Dimensões do cartão 32,5 x 15 x 6,5"),
        ("GPU", "AMD Radeon RX série 9000"),
        ("Interface de Memória", "256 bits"),
        ("Memória de Vídeo", "16 GB"),
        ("Tipo de Memória", "GDDR6"),
    ])
    text = title + " Arquitetura AMD RDNA 4 " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("PLACA_VIDEO", rows, text)
    assert specs["arquitetura"] == "RDNA 4"
    assert specs["memoriaVideoGb"] == 16
    assert specs["tipoMemoriaVideo"] == "GDDR6"
    assert specs["barramentoBits"] == 256
    assert specs["clockBaseMhz"] == 1660
    assert specs["clockBoostMhz"] == 2970
    assert specs["geracaoPcie"] == 5
    assert specs["comprimentoMm"] == 325
    assert specs["alturaMm"] == 150
    assert specs["espessuraMm"] == 65
    assert specs["slotsOcupados"] == 3.5
    assert specs["potenciaFonteRecomendadaWatts"] == 800
    assert specs["conectoresPcie8Pinos"] == 3
    assert specs["displayPort"] == 3
    assert specs["hdmi"] == 1


def test_v10_headset_logitech_g332():
    title = "Headset Gamer Logitech G332 PC PS4 Xbox One Preto"
    assert detect_category(title) == "HEADSET"
    rows = attrs([
        ("Conexão", "P2"),
        ("Impedância", "- 39 ohms (passiva) - 5.000 ohms (ativa)"),
        ("Peso do Produto", "259g"),
    ])
    text = title + " drivers de áudio de 50mm, microfone de 6mm " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("HEADSET", rows, text)
    assert specs["tipoConexao"] == "P2"
    assert specs["driverMm"] == 50
    assert specs["microfone"] is True
    assert specs["impedancia"] == 39
    assert specs["pesoGramas"] == 259


def test_v10_mouse_redragon_cobra_prioriza_ficha_tecnica():
    title = "Mouse Gamer Redragon Cobra, Chroma RGB, 12400 DPI, 8 Botões, Preto - M711"
    assert detect_category(title) == "MOUSE"
    text = title + " Sensor: Pixart PWM3325 DPI: Até 10000 DPI Polling Rate: Até 1000Hz Botões Programáveis: 8 Conectividade: USB 2.0 Pegada ergonômica ideal para destros Iluminação RGB"
    specs = extract_specs("MOUSE", [], text)
    assert specs["sensor"] == "Pixart PWM3325"
    # A ficha técnica explícita prevalece sobre o número conflitante do título.
    assert specs["dpiMaximo"] == 10000
    assert specs["pollingRateHz"] == 1000
    assert specs["botoes"] == 8
    assert specs["conexao"] == "USB 2.0"
    assert specs["cabo"] is True
    assert specs["mao"] == "Destro"
    assert specs["rgb"] is True


def test_v10_notebook_acer_nitro_v15_rtx4050():
    title = "Notebook Gamer Acer Nitro V15 Intel Core i5 512GB SSD 16GB RAM 15.6 Full HD 165Hz IPS NVIDIA RTX 4050 6GB Linux"
    assert detect_category(title) == "NOTEBOOK"
    rows = attrs([
        ("Processador", "Intel Core i5"),
        ("Geração do Processador", "13ª Geração"),
        ("Velocidade do Processador", "4.60GHz"),
        ("Memória RAM", "16GB"),
        ("Memória Expansível", "Até 32GB"),
        ("Barramento da Memória", "DDR5"),
        ("Clock da Memória", "5200Mhz"),
        ("Tipo de Armazenamento", "SSD"),
        ("Capacidade do Armazenamento", "512GB"),
        ("Interface de Conexão", "NVMe"),
        ("Sistema Operacional", "Linux"),
        ("Painel da Tela", "IPS"),
        ("Tamanho da Tela", "15.6”"),
        ("Taxa de Atualização da Tela", "165Hz"),
        ("Memória da Placa de Vídeo", "6GB GDDR6"),
        ("Tipo de Placa de Vídeo", "Dedicada"),
        ("Placa de Vídeo", "Nvidia GeForce RTX 4050"),
        ("Conexões", "Porta para cabo de rede (RJ-45), Porta HDMI 2.1, 2x Portas USB 3.2 Gen 1, Porta USB Tipo-C Thunderbolt 4"),
        ("Conectividade", "Wi-fi, Bluetooth"),
        ("Duração Aproximada da Bateria", "5 Horas"),
        ("Peso do Produto", "2,11kg"),
        ("Dimensões do Produto", "Largura: 36,2cm, Altura: 2,35cm, Profundidade: 23,9cm"),
        ("Funcionalidades", "Webcam, teclado retroiluminado"),
    ])
    text = title + " " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("NOTEBOOK", rows, text)
    assert specs["gpuDedicada"] is True
    assert specs["gpuNome"] == "Nvidia GeForce RTX 4050"
    assert specs["vramGb"] == 6
    assert specs["ramInstaladaGb"] == 16
    assert specs["ramMaximaGb"] == 32
    assert specs["upgradeRam"] is True
    assert specs["tipoMemoria"] == "DDR5"
    assert specs["frequenciaMhz"] == 5200
    assert specs["tipoArmazenamento"] == "SSD NVMe"
    assert specs["usbC"] == 1
    assert specs["thunderbolt"] == 1
    assert specs["hdmi"] == 1
    assert specs["ethernet"] is True
    assert specs["autonomiaInformadaHoras"] == 5
    assert specs["tecladoIluminado"] is True


def test_v10_microfone_fifine_am8():
    title = "Microfone Dinâmico Gamer Fifine Ampligame, RGB, Cardióide, USB-C, Anti-Ruído, Preto - AM8"
    assert detect_category(title) == "MICROFONE"
    rows = attrs([
        ("Especificações", "Tipo: Dinâmico | Padrão polar: Cardióide | Conexão de saída: USB tipo C (extremidade do microfone) para tipo A 2.0 (extremidade do computador)/XLR | Profundidade de bits/taxa de amostragem: 16 bits/44,1k-48k Hz | Resposta de frequência: 50-16 kHz"),
    ])
    text = title + " " + rows[0]["value_name"]
    specs = extract_specs("MICROFONE", rows, text)
    assert specs["padraoPolar"] == "Cardióide"
    assert specs["taxaAmostragemKhz"] == 48
    assert "USB tipo C" in specs["conexao"]
    assert "XLR" in specs["conexao"]


def test_v10_placa_mae_intel_b760m():
    title = "Placa Mãe Gamer Gigabyte B760M GAMING X WIFI6E GEN5, Micro ATX, DDR5, LGA 1700, Wi-Fi 6E, Bluetooth 5.3"
    assert detect_category(title) == "PLACA_MAE"
    rows = attrs([
        ("Destaques", "Suporte para memórias DDR5 até 7600MHz em OC | Wi-Fi 6E e Bluetooth 5.3 | Rede LAN 2.5GbE | Slot principal PCIe 5.0 x16 | Dois conectores M.2 NVMe PCIe 4.0 | Q-Flash Plus"),
        ("Chipset", "Intel B760 Express"),
        ("Memória", "4 slots DDR5 DIMM | Suporte máximo de 192GB | Suporte para módulos ECC e Non-ECC | Suporte para perfis XMP"),
        ("Interface de Armazenamento", "2 conectores M.2 PCIe 4.0 x4 | 4 conectores SATA 6Gb/s"),
        ("Formato", "Micro ATX"),
        ("LAN", "Realtek 2.5GbE LAN chip 2.5 Gbps"),
        ("Soquete do Processador", "LGA 1700"),
        ("Tipo de Memória", "DDR5"),
    ])
    text = title + " " + " ".join(f"{r['name']}: {r['value_name']}" for r in rows)
    specs = extract_specs("PLACA_MAE", rows, text)
    assert specs["socket"] == "LGA1700"
    assert specs["chipset"] == "Intel B760 Express"
    assert specs["formato"] == "MICRO_ATX"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["formatosMemoriaSuportados"] == ["DIMM"]
    assert specs["slotsMemoria"] == 4
    assert specs["capacidadeMaximaMemoriaGb"] == 192
    assert specs["portasSata"] == 4
    assert specs["slotsM2"] == 2
    assert specs["versaoPcie"] == "5.0"
    assert specs["wifi"] is True
    assert specs["bluetooth"] is True
    assert specs["suportaXmp"] is True
    assert specs["suportaEcc"] is True
    assert specs["biosFlashback"] is True
