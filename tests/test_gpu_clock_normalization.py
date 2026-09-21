from src.extractors.dto_normalizer import normalize_specs_for_backend
from src.extractors.ml_specs import extract_specs


def test_gt730_processor_clock_is_base_not_boost():
    attrs = [
        {"name": "Clock do Processador de Vídeo", "value_name": "902 MHz"},
        {"name": "Velocidade da memória", "value_name": "1600 MHz"},
        {"name": "Memória de vídeo", "value_name": "4 GB"},
        {"name": "Tipo de memória de vídeo", "value_name": "DDR3"},
    ]

    specs = extract_specs(
        "PLACA_VIDEO",
        attrs,
        "Placa de Vídeo NVIDIA GeForce GT 730 4GB DDR3 HDMI VGA PCI-E 2.0",
    )

    assert specs["clockBaseMhz"] == 902
    assert "clockBoostMhz" not in specs
    assert specs["memoriaVideoGb"] == 4
    assert specs["tipoMemoriaVideo"] == "DDR3"


def test_gpu_invalid_base_boost_pair_never_reaches_backend():
    specs = normalize_specs_for_backend(
        "PLACA_VIDEO",
        {
            "clockBaseMhz": 1600,
            "clockBoostMhz": 902,
            "comprimentoMm": 146,
        },
    )

    assert specs["clockBaseMhz"] == 1600
    assert specs["clockBoostMhz"] is None
    assert specs["comprimentoMm"] == 146


def test_gpu_valid_base_boost_pair_is_preserved():
    specs = normalize_specs_for_backend(
        "PLACA_VIDEO",
        {
            "clockBaseMhz": 2205,
            "clockBoostMhz": 2505,
            "comprimentoMm": 240,
        },
    )

    assert specs["clockBaseMhz"] == 2205
    assert specs["clockBoostMhz"] == 2505
