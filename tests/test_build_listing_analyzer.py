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


def test_unstructured_multicomponent_listing_requires_review():
    result = analyze_listing("Super oferta", "Processador Ryzen 5 5600, placa-mãe B550 e memória DDR4")
    assert result["confirmacaoObrigatoria"] is True
    assert result["tipoSugerido"] in {"KIT_UPGRADE", "INDEFINIDO"}
