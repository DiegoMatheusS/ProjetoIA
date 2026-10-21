from src.build_detection.analyzer import analyze_listing


def test_pc_with_unbranded_memory_and_keyboard_mouse_stays_descriptive():
    result = analyze_listing(
        "Oferta gamer especial",
        "Computador montado\nProcessador: AMD Ryzen 5 5600G\nMemória RAM: 16 GB DDR4\n"
        "SSD NVMe: 500 GB\nAcompanha teclado e mouse",
        [{"id": 17, "categoria": "PROCESSADOR", "marca": "AMD", "modelo": "Ryzen 5 5600G", "nome": "AMD Ryzen 5 5600G"},
         {"id": 18, "categoria": "MEMORIA_RAM", "marca": "Kingston", "modelo": "16 GB DDR4", "nome": "Kingston 16 GB DDR4"}],
    )
    assert result["tipoSugerido"] == "PC_MONTADO"
    links = {c["categoria"]: c["hardwareId"] for c in result["componentesDetectados"]}
    assert links["PROCESSADOR"] == 17
    assert links["MEMORIA_RAM"] is None
    assert "teclado" in result["acessoriosNaDescricao"]
    assert "mouse" in result["acessoriosNaDescricao"]
    assert result["descricaoOriginal"].endswith("teclado e mouse")
    assert not result["componentesObrigatorios"]


def test_kit_identified_from_description_not_title():
    result = analyze_listing(
        "Oferta imperdível de peças",
        "Kit upgrade com processador Intel Core i5 12400F, placa-mãe ASUS H610M, RAM 16 GB",
    )
    assert result["tipoSugerido"] == "KIT_UPGRADE"


def test_one_graphics_chip_is_not_automatically_assigned_to_board_brand():
    result = analyze_listing(
        "Pc gamer",
        "Computador completo\nPlaca de vídeo: NVIDIA RTX 4060\nMemória RAM: 16GB",
        [{"id": 1, "categoria": "PLACA_VIDEO", "marca": "ASUS", "modelo": "RTX 4060", "nome": "ASUS RTX 4060"}],
    )
    gpu = next(c for c in result["componentesDetectados"] if c["categoria"] == "PLACA_VIDEO")
    assert gpu["hardwareId"] is None


def test_processor_suffix_must_match():
    result = analyze_listing(
        "Gamer", "Processador AMD Ryzen 5 5600G",
        [{"id": 1, "categoria": "PROCESSADOR", "marca": "AMD", "modelo": "Ryzen 5 5600", "nome": "5600"}],
    )
    cpu = next(c for c in result["componentesDetectados"] if c["categoria"] == "PROCESSADOR")
    assert cpu["hardwareId"] is None


def test_generic_ram_does_not_borrow_motherboard_brand():
    result = analyze_listing(
        "Pc gamer", "Placa-mãe ASUS B550M\nMemória RAM: 16 GB DDR4\nSSD: 500 GB",
        [{"id": 20, "categoria": "MEMORIA_RAM", "marca": "ASUS", "modelo": "16 GB DDR4", "nome": "RAM ASUS"}],
    )
    ram = next(c for c in result["componentesDetectados"] if c["categoria"] == "MEMORIA_RAM")
    assert ram["hardwareId"] is None


def test_generic_ram_does_not_borrow_brand_in_unstructured_line():
    result = analyze_listing(
        "Oferta", "Placa-mãe ASUS B550M acompanha Memória RAM 16 GB DDR4",
        [{"id": 20, "categoria": "MEMORIA_RAM", "marca": "ASUS", "modelo": "16 GB DDR4", "nome": "RAM ASUS"}],
    )
    ram = next(c for c in result["componentesDetectados"] if c["categoria"] == "MEMORIA_RAM")
    assert ram["hardwareId"] is None


def test_unstructured_multicomponent_listing_requires_review():
    result = analyze_listing("Super oferta", "Processador Ryzen 5 5600, placa-mãe B550 e memória DDR4")
    assert result["confirmacaoObrigatoria"] is True
    assert result["tipoSugerido"] in {"KIT_UPGRADE", "INDEFINIDO"}


def test_complete_pc_title_detects_components_and_links_existing_hardware():
    result = analyze_listing(
        "PC Gamer AMD Ryzen 5 5600G ASUS B550M 16GB RAM Kingston NV2 SSD 1TB Gigabyte RTX 4060",
        "Computador completo montado e pronto para uso.",
        [
            {"id": 101, "categoria": "PROCESSADOR", "marca": "AMD", "modelo": "Ryzen 5 5600G", "nome": "AMD Ryzen 5 5600G"},
            {"id": 102, "categoria": "PLACA_MAE", "marca": "ASUS", "modelo": "B550M", "nome": "ASUS B550M"},
            {"id": 103, "categoria": "ARMAZENAMENTO", "marca": "Kingston", "modelo": "NV2", "nome": "Kingston NV2"},
            {"id": 104, "categoria": "PLACA_VIDEO", "marca": "Gigabyte", "modelo": "RTX 4060", "nome": "Gigabyte RTX 4060"},
        ],
    )
    assert result["tipoSugerido"] == "PC_MONTADO"
    detected = {item["categoria"]: item for item in result["componentesDetectados"]}
    assert detected["PROCESSADOR"]["hardwareId"] == 101
    assert detected["PLACA_MAE"]["hardwareId"] == 102
    assert detected["ARMAZENAMENTO"]["hardwareId"] == 103
    assert detected["PLACA_VIDEO"]["hardwareId"] == 104
    assert "MEMORIA_RAM" in detected


def test_title_only_pc_does_not_become_individual_processor():
    result = analyze_listing(
        "Computador Ryzen 7 5700G 16GB RAM SSD 480GB",
        "",
        [{"id": 201, "categoria": "PROCESSADOR", "marca": "AMD", "modelo": "Ryzen 7 5700G", "nome": "AMD Ryzen 7 5700G"}],
    )
    assert result["tipoSugerido"] == "PC_MONTADO"
    cpu = next(c for c in result["componentesDetectados"] if c["categoria"] == "PROCESSADOR")
    assert cpu["hardwareId"] == 201


def test_description_links_branded_components_and_keeps_important_details():
    description = 'Compre agora!\nProcessador: AMD Ryzen 5 5500\nSSD: Kingston NV2 1TB\nRAM: 16 GB DDR4\nAcompanha teclado e mouse\nGarantia de 12 meses'
    result = analyze_listing('PC Gamer', description, [
        {'id': 180, 'categoria': 'PROCESSADOR', 'marca': 'AMD', 'modelo': 'Ryzen 5 5500', 'nome': 'Ryzen 5 5500'},
        {'id': 181, 'categoria': 'ARMAZENAMENTO', 'marca': 'Kingston', 'modelo': 'NV2', 'nome': 'Kingston NV2 1TB'},
    ])
    linked = {c['categoria']: c for c in result['componentesDetectados']}
    assert linked['PROCESSADOR']['hardwareId'] == 180
    assert linked['PROCESSADOR']['marca'] == 'AMD'
    assert linked['PROCESSADOR']['modelo'] == 'Ryzen 5 5500'
    assert linked['PROCESSADOR']['vinculoConfirmadoNoAnuncio'] is True
    assert linked['ARMAZENAMENTO']['hardwareId'] == 181
    assert linked['MEMORIA_RAM']['hardwareId'] is None
    assert 'Compre agora' not in result['descricaoSugerida']
    for important in ['16 GB DDR4', 'teclado e mouse', 'Garantia de 12 meses']:
        assert important in result['descricaoSugerida']
    assert result['descricaoOriginal'] == description


def test_optional_parts_and_wrong_gpu_suffix_are_not_linked():
    catalog = [{'id': 1, 'categoria': 'PLACA_VIDEO', 'marca': 'ASUS', 'modelo': 'RTX 4060', 'nome': 'ASUS RTX 4060'}]
    for description in ['Placa de vídeo: ASUS RTX 4060 Ti', 'Placa de vídeo: ASUS RTX 4060 ou RTX 4070', 'Compatível com placa de vídeo ASUS RTX 4060']:
        result = analyze_listing('PC Gamer', description, catalog)
        gpu = next(c for c in result['componentesDetectados'] if c['categoria'] == 'PLACA_VIDEO')
        assert gpu['hardwareId'] is None
