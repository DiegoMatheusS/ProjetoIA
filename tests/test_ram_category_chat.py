from src.extractors.category import detect_category
from src.main import _category_hint_from_product_url


def test_ram_title_with_capacity_before_ddr_is_hardware():
    title = "Kingston Fury Beast 16GB 3200MHz DDR4 CL16"
    assert detect_category(title) == "MEMORIA_RAM"


def test_ram_title_with_ddr_before_capacity_is_hardware():
    title = "DDR5 32GB 6000MHz Kingston Fury Beast"
    assert detect_category(title) == "MEMORIA_RAM"


def test_ram_title_with_dimm_is_hardware():
    title = "Corsair Vengeance SODIMM DDR5 16GB 5600MHz"
    assert detect_category(title) == "MEMORIA_RAM"


def test_explicit_memory_title_is_hardware():
    title = "Memória Kingston Fury Beast 8GB 3200MHz DDR4"
    assert detect_category(title) == "MEMORIA_RAM"


def test_notebook_with_ddr_and_capacity_remains_notebook():
    title = "Notebook Lenovo Ryzen 7 16GB DDR5 512GB SSD"
    assert detect_category(title) == "NOTEBOOK"


def test_smartphone_with_ram_remains_cellphone():
    title = "Smartphone Samsung Galaxy 8GB RAM 256GB"
    assert detect_category(title) == "CELULAR"


def test_blocked_ram_slug_keeps_hardware_category():
    url = (
        "https://www.mercadolivre.com.br/"
        "memoria-kingston-fury-beast-16gb-3200mhz-ddr4/"
        "p/MLB12345678"
    )
    assert _category_hint_from_product_url(url) == "MEMORIA_RAM"
