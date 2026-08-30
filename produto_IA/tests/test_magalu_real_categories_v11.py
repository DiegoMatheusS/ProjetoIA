from src.extractors.category import detect_category
from src.extractors.ml_specs import extract_specs
from src.scrapers.magazine_scraper import MagazineScraper


def attrs(rows):
    return [{"id": None, "name": name, "value_name": value} for name, value in rows]


def test_v11_hdd_35_sata_nao_confunde_categoria_da_loja():
    title = "HD Seagate 2TB 3.5 Sata III ST2000DM001"
    assert detect_category(title) == "ARMAZENAMENTO"
    rows = attrs([
        ("Capacidade", "2t"),
        ("Capacidade do Armazenamento", "2TB"),
        ("Tipo de armazenamento do disco", "HDD"),
        ("Conectividade", "SATA III"),
    ])
    specs = extract_specs("ARMAZENAMENTO", rows, title + " " + " ".join(r["value_name"] for r in rows))
    assert specs["tipo"] == "HDD"
    assert specs["formato"] == "POLEGADAS_3_5"
    assert specs["interface"] == "SATA"
    assert specs["capacidadeGb"] == 2048


def test_v11_ssd_sata_25():
    title = 'SSD Kingston A400, 240GB, SATA III, 2.5", Leitura: 500MB/s, Gravação: 350MB/s'
    specs = extract_specs("ARMAZENAMENTO", [], title)
    assert specs["tipo"] == "SSD"
    assert specs["formato"] == "POLEGADAS_2_5"
    assert specs["interface"] == "SATA"
    assert specs["capacidadeGb"] == 240
    assert specs["leituraSequencialMbps"] == 500
    assert specs["escritaSequencialMbps"] == 350


def test_v11_ssd_pcie5_samsung_9100_pro():
    rows = attrs([
        ("Capacidade do Armazenamento", "1 TB"),
        ("Fator de Forma", "M.2 2280"),
        ("Interface de Conexão", "PCIe 5.0 x4 / NVMe 2.0"),
        ("Performance", "Leitura sequencial de até 14.700 MB/s, Gravação sequencial de até 13.300 MB/s"),
    ])
    text = "SSD Samsung 1TB 9100 PRO PCIe 5.0 M.2 2280 " + " ".join(f"{x['name']}: {x['value_name']}" for x in rows)
    specs = extract_specs("ARMAZENAMENTO", rows, text)
    assert specs["tipo"] == "SSD"
    assert specs["formato"] == "M2"
    assert specs["interface"] == "NVME_PCIE"
    assert specs["geracaoPcie"] == 5
    assert specs["pistasPcie"] == 4
    assert specs["capacidadeGb"] == 1024
    assert specs["leituraSequencialMbps"] == 14700
    assert specs["escritaSequencialMbps"] == 13300


def test_v11_processador_i5_fclga1700():
    rows = attrs([
        ("Soquetes compatíveis", "FCLGA1700"),
        ("Tipos de memória RAM suportadas", "DDR4 e DDR5"),
        ("Quantidade de núcleos de CPU", "6"),
    ])
    text = "Processador Intel Core i5-12400F 6 Núcleos 12 Threads Sem Vídeo Integrado 4.4GHz Max Turbo"
    specs = extract_specs("PROCESSADOR", rows, text)
    assert specs["socket"] == "LGA1700"
    assert specs["tiposMemoriaSuportados"] == ["DDR4", "DDR5"]
    assert specs["nucleos"] == 6
    assert specs["threads"] == 12
    assert specs["possuiVideoIntegrado"] is False


def test_v11_processador_lga1851_sem_inventar_memoria():
    text = "Processador Intel Core Ultra 5 250K 3.7GHz 5.4GHz Turbo 14 Núcleos 14 Threads LGA 1851 Com Vídeo Integrado"
    specs = extract_specs("PROCESSADOR", [], text)
    assert specs["socket"] == "LGA1851"
    assert specs["nucleos"] == 14
    assert specs["threads"] == 14
    assert specs["possuiVideoIntegrado"] is True
    assert "tiposMemoriaSuportados" not in specs


def test_v11_ryzen_sem_video_e_sem_cooler():
    text = "Processador AMD Ryzen 7 5700X AM4 3,4GHz 4,6GHz Turbo 8 Cores 16 Threads S Cooler S Vídeo Tipo de Memória DDR4"
    rows = attrs([("Tipo de Memória", "DDR4")])
    specs = extract_specs("PROCESSADOR", rows, text)
    assert specs["socket"] == "AM4"
    assert specs["possuiVideoIntegrado"] is False
    assert specs["coolerIncluso"] is False
    assert specs["tiposMemoriaSuportados"] == ["DDR4"]


def test_v11_fonte_semi_modular_conectores_expandidos():
    rows = attrs([
        ("Fator de forma", "ATX"),
        ("Potência", "750W"),
        ("Tipo de Fonte", "Semi-Modular"),
        ("Conectores", "1x Placa-mãe ATX (20+4 pinos), 1x CPU / Processador (P4+4 pinos), 1x CPU / Processador (P8 pinos), 3x GPU / Placa de Vídeo (PCI-E 6+2 pinos), 1x GPU / Placa de Vídeo (PCI-E 6 pinos), 6x Armazenamento / HD / SSD (SATA 15 pinos)"),
        ("Eficiência", "93%"),
    ])
    text = "Fonte Xilence 750W 80 Plus Gold Semi-Modular " + " ".join(f"{x['name']}: {x['value_name']}" for x in rows)
    specs = extract_specs("FONTE", rows, text)
    assert specs["modularidade"] == "SEMI_MODULAR"
    assert specs["eficienciaPercentual"] == 93
    assert specs["conectoresAtx24Pinos"] == 1
    assert specs["conectoresEpsCpu"] == 2
    assert specs["conectoresPcie8Pinos"] == 3
    assert specs["conectoresPcie6Pinos"] == 1
    assert specs["conectoresSata"] == 6


def test_v11_fonte_80plus_nao_vira_80_porcento():
    rows = attrs([("Eficiência", "80 Plus Gold"), ("Potência", "750W"), ("Fator de forma", "ATX")])
    specs = extract_specs("FONTE", rows, "Fonte 750W 80 Plus Gold")
    assert "eficienciaPercentual" not in specs


def test_v11_gabinete_lwh_e_compatibilidades():
    rows = attrs([
        ("Especificações", "Placa-Mãe: ATX / M-ATX / ITX | Fontes de Alimentação: ATX (não inclusa) | Dimensões (L x W x H): L 418mm x W 277mm x H 440mm"),
    ])
    text = "Gabinete Gamer Rise Mode Galaxy Full Glass Mid Tower ATX Suporte a Placa de Vídeo até 400MM Suporte Air cooler até 157mm " + rows[0]["value_name"]
    specs = extract_specs("GABINETE", rows, text)
    assert specs["tamanho"] == "MID_TOWER"
    assert specs["profundidadeMm"] == 418
    assert specs["larguraMm"] == 277
    assert specs["alturaMm"] == 440
    assert specs["formatosPlacaMaeSuportados"] == ["ATX", "MICRO_ATX", "MINI_ITX"]
    assert specs["formatosFonteSuportados"] == ["ATX"]
    assert specs["comprimentoMaximoGpuMm"] == 400
    assert specs["alturaMaximaCoolerCpuMm"] == 157


def test_v11_monitor_oled_portas_explicitas():
    rows = attrs([
        ("Tamanho da tela", '27"'),
        ("Resolução", "QHD (2560 x 1440)"),
        ("Painel da Tela", "OLED"),
        ("Taxa de Atualização da Tela", "180Hz"),
        ("Tempo de resposta", "0.03ms"),
        ("HDMI", "1 EA"),
        ("Display Port", "1 EA"),
    ])
    specs = extract_specs("MONITOR", rows, "Monitor Samsung Odyssey OLED G5 G-Sync FreeSync HDR")
    assert specs["tipoPainel"] == "OLED"
    assert specs["taxaAtualizacaoHz"] == 180
    assert specs["hdmi"] == 1
    assert specs["displayPort"] == 1


def test_v11_monitor_ultrawide_21_9():
    rows = attrs([
        ("Resolução", "FHD (2560x1080)"),
        ("Painel da Tela", "IPS"),
        ("Taxa de Atualização da Tela", "100Hz"),
        ("Conexões", "1 HDMI, 1 DisplayPort, 1 USB Tipo-C"),
    ])
    specs = extract_specs("MONITOR", rows, "Monitor LG Ultrawide 29 21:9 HDR10 AMD FreeSync")
    assert specs["resolucao"] == "2560x1080"
    assert specs["tipoPainel"] == "IPS"
    assert specs["hdmi"] == 1
    assert specs["displayPort"] == 1


def test_v11_mouse_bluetooth_receptor_usb_nao_e_cabeado():
    rows = attrs([
        ("Conexão", "Receptor USB"),
        ("Com Bluetooth", "Sim"),
        ("É sem fio", "Sim"),
        ("Quantidade de botões", "5"),
    ])
    text = "Mouse Sem Fio Logitech Signature M650 Bluetooth USB 2000 DPI 5 Botões"
    specs = extract_specs("MOUSE", rows, text)
    assert specs["bluetooth"] is True
    assert specs["wireless"] is True
    assert specs["cabo"] is False
    assert specs["conexao"] == "Bluetooth / Receptor USB"


def test_v11_teclado_bluetooth_compacto_e_wireless():
    rows = attrs([
        ("Conectividade", "Bluetooth"),
        ("Padrão de Teclado", "ABNT2"),
        ("Tipo de Teclado", "Compacto"),
    ])
    text = "Teclado Sem Fio Logitech K250 Compacto Bluetooth ABNT2"
    specs = extract_specs("TECLADO", rows, text)
    assert specs["bluetooth"] is True
    assert specs["wireless"] is True
    assert specs["tamanho"] == "Compacto"
    assert "tipo" not in specs
    assert specs["abnt2"] is True


def test_v11_identidade_prefere_marca_rotulada_e_modelo_comercial_cpu():
    generic = {"brand": "AMD PCYES", "model": "100-100000926WOFO", "mpn": None, "title": "Processador AMD Ryzen 7 5700X - 100-100000926WOFO"}
    rows = attrs([("Marca", "AMD"), ("Modelo", "100-100000926WOFO"), ("Referência", "100-100000926WOFO")])
    brand, model, mpn = MagazineScraper._refine_identity(generic, rows)
    assert brand == "AMD"
    assert model == "5700X"
    assert mpn == "100-100000926WOFO"
