import pytest

from src.extractors.ml_specs import extract_specs
from src.extractors.dto_normalizer import normalize_specs_for_backend
from src.enrichment.core import essential_missing_fields, TechnicalEnricher
from src.main import build_result


def attrs(**fields):
    return [{"id": key, "name": key, "value_name": value} for key, value in fields.items()]


def test_ml_notebook_os_wifi_camera_and_keyboard_attributes():
    spec = extract_specs("NOTEBOOK", attrs(
        OPERATING_SYSTEM_NAME="Windows", OPERATING_SYSTEM_VERSION="11 Home",
        WITH_WI_FI="Sim", WIFI_STANDARD="Wi-Fi 6 (802.11ax)",
        BLUETOOTH_VERSION="5.3", WITH_WEBCAM="Sim", WEBCAM_RESOLUTION="720p",
        WITH_NUMERIC_KEYPAD="Não", WITH_BACKLIT_KEYBOARD="Sim",
    ))
    assert spec["sistemaOperacional"] == "Windows 11 Home"
    assert spec["wifi"] == "Wi-Fi 6 (802.11ax)"
    assert spec["bluetooth"] == "Bluetooth 5.3"
    assert spec["webcam"] is True
    assert spec["resolucaoWebcam"] == "720p"
    assert spec["tecladoNumerico"] is False
    assert spec["tecladoIluminado"] is True


def test_icecat_labels_are_supported():
    spec = extract_specs("NOTEBOOK", attrs(**{
        "Operating system installed": "Linux",
        "Top Wi-Fi standard": "Wi-Fi 6E",
        "Front camera": "Yes",
        "Front camera HD type": "Full HD",
        "Numeric keypad": "No",
        "Keyboard backlit": "Yes",
        "Display diagonal": "15.6",
        "Internal memory": "16 GB",
        "Total storage capacity": "512 GB",
    }))
    assert spec["sistemaOperacional"] == "Linux"
    assert spec["wifi"] == "Wi-Fi 6E"
    assert spec["webcam"] is True
    assert spec["resolucaoWebcam"] == "Full HD"
    assert spec["ramInstaladaGb"] == 16
    assert spec["armazenamentoGb"] == 512


def test_missing_data_is_not_false_and_screen_resolution_is_not_webcam():
    spec = extract_specs("NOTEBOOK", [], "Notebook Tela IPS 1920x1080, Full HD 1080p")
    for field in ["sistemaOperacional", "webcam", "resolucaoWebcam", "wifi", "bluetooth", "tecladoNumerico"]:
        assert field not in spec


def test_labelled_description_and_explicit_negatives():
    spec = extract_specs("NOTEBOOK", [], (
        "Sistema operacional: Ubuntu 24.04\nWi-Fi 6; Bluetooth 5.2\n"
        "Sem webcam. Sem teclado numérico. Webcam: Não\n"
    ))
    assert spec["sistemaOperacional"] == "Ubuntu 24.04"
    assert spec["wifi"] == "Wi-Fi 6"
    assert spec["bluetooth"] == "Bluetooth 5.2"
    assert spec["webcam"] is False
    assert spec["tecladoNumerico"] is False


def test_declared_variant_os_wins_over_compatibility_text():
    spec = extract_specs("NOTEBOOK", attrs(OPERATING_SYSTEM="FreeDOS", WITH_WEBCAM="Não"),
                         "Compatível com Windows 11. Câmera HD.")
    assert spec["sistemaOperacional"] == "FreeDOS"
    assert spec["webcam"] is False
    assert "sistemaOperacional" not in extract_specs("NOTEBOOK", [], "Compatível com Windows 11")


def test_notebook_payload_normalizes_units_strings_and_preserves_false():
    spec = normalize_specs_for_backend("NOTEBOOK", {
        "webcam": "false", "tecladoIluminado": "Sim", "clockBaseMhz": "2.4 GHz",
        "ramInstaladaGb": "16 GB", "pesoKg": "1,65", "wifi": "Não encontrado",
    })
    assert spec["webcam"] is False
    assert spec["tecladoIluminado"] is True
    assert spec["clockBaseMhz"] == 2400
    assert spec["ramInstaladaGb"] == 16
    assert spec["pesoKg"] == 1.65
    assert spec["wifi"] is None


def test_os_webcam_wifi_are_essential_and_false_is_confirmed():
    result = {"categoriaDetectada": "NOTEBOOK", "especificacoesEncontradas": {
        "processadorNome": "Core i5", "ramInstaladaGb": 16, "armazenamentoGb": 512,
        "tamanhoTelaPolegadas": 15.6, "webcam": False,
    }}
    assert set(essential_missing_fields(result)) == {"wifi", "sistemaOperacional"}


def test_notebook_enrichment_fills_essential_gaps_and_keeps_advertised_os():
    class Manufacturer:
        name = "FABRICANTE_OFICIAL"
        def supports(self, category, identity):
            return category == "NOTEBOOK"
        def collect(self, identity, category):
            return {
                "ok": True, "fonte": self.name, "url": "https://example.com/exact-sku",
                "attributes": attrs(OPERATING_SYSTEM="Windows 11", WIFI_STANDARD="Wi-Fi 6", WITH_WEBCAM="Sim"),
            }
    base = build_result({
        "ok": True, "title": "Notebook Acer A515-57", "brand": "Acer", "model": "A515-57",
        "mpn": "NX.KNVAL.001", "attributes": attrs(OPERATING_SYSTEM="Linux"),
    }, forced_category="NOTEBOOK")
    result = TechnicalEnricher(providers=[Manufacturer()]).enrich(base)
    spec = result["payloadParcialBackend"]["especificacao"]
    assert spec["sistemaOperacional"] == "Linux"
    assert spec["wifi"] == "Wi-Fi 6"
    assert spec["webcam"] is True
    assert any(conflict["campo"] == "sistemaOperacional" for conflict in result["enriquecimentoTecnico"]["conflitos"])
