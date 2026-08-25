from src.extractors.category import detect_category


def test_composite_categories_win_over_internal_components():
    assert detect_category("Notebook ASUS Ryzen 7 RTX 4060 16GB") == "NOTEBOOK"
    assert detect_category("PC Gamer Completo Ryzen 5 7600 RTX 4060") == "PC_MONTADO"
    assert detect_category("Smartphone Galaxy S26 Snapdragon") == "CELULAR"


def test_frontend_categories():
    cases = {
        "Suporte articulado para monitor VESA": "SUPORTE_MONITOR",
        "Webcam Full HD 60 fps": "WEBCAM",
        "Controle gamer bluetooth para PC": "CONTROLE",
        "Cadeira gamer ergonômica": "CADEIRA",
        "Mesa gamer para computador": "MESA",
        "Mousepad RGB grande": "MOUSEPAD",
        "Fita LED RGB para setup": "ILUMINACAO",
        "Headset gamer sem fio": "HEADSET",
    }
    for text, expected in cases.items():
        assert detect_category(text) == expected


def test_core_hardware_categories():
    cases = {
        "Processador AMD Ryzen 5 7600": "PROCESSADOR",
        "Placa-mãe B650 AM5": "PLACA_MAE",
        "Memória RAM DDR5 16GB 6000MHz": "MEMORIA_RAM",
        "Placa de vídeo GeForce RTX 5070": "PLACA_VIDEO",
        "SSD NVMe 1TB PCIe 4.0": "ARMAZENAMENTO",
        "Fonte 750W 80 Plus Gold": "FONTE",
        "Gabinete Mid Tower ATX": "GABINETE",
        "Water Cooler 360mm AM5": "COOLER",
        "Ventoinha 120mm PWM ARGB": "VENTOINHA",
    }
    for text, expected in cases.items():
        assert detect_category(text) == expected
