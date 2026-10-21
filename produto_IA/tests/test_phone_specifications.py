from copy import deepcopy

from src.main import build_result
from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend
from src.extractors.ml_specs import extract_specs
from src.extension.router import _product_payload_for_backend
from src.research_agent import intake


def test_phone_payload_reaches_extension_and_description_is_short():
    raw = {"ok": True, "title": "Smartphone Samsung Galaxy S24", "brand": "Samsung", "model": "SM-TESTE",
           "url_original": "https://www.amazon.com.br/dp/B0TEST0000", "description": "Texto longo da loja",
           "attributes": [{"name": key, "value_name": value} for key, value in [
               ("Memória RAM", "8 GB"), ("Memória interna", "256 GB"), ("Tamanho da tela", "6.7"),
               ("Capacidade da bateria", "5000 mAh"), ("NFC", "Não"), ("Câmera principal", "50 MP")]]}
    result = build_result(raw, forced_category="CELULAR")
    specs = result["payloadParcialBackend"]["especificacaoCelular"]
    assert specs["nfc"] is False and specs["bateriaMah"] == 5000
    description = result["payloadParcialBackend"]["descricao"]
    assert len(description.split(" · ")) == 4
    assert "mAh" in description and "NFC" not in description and "Câmera" not in description
    product = _product_payload_for_backend("CELULAR", result, result["payloadParcialBackend"])
    assert product["especificacaoCelular"]["cameraPrincipalMp"] == 50
    assert product["categoriaSlug"] == "celulares"


def test_phone_normalization_preserves_false_and_omits_unconfirmed():
    safe = normalize_hardware_payload_for_backend("CELULAR", {"nome": "Galaxy Teste", "especificacaoCelular": {
        "ramGb": "8 GB", "nfc": "Não", "esim": None, "inventado": "não aceito"}})
    assert safe["especificacaoCelular"] == {"ramGb": 8, "nfc": False}
    assert "categoria" not in safe


def test_phone_local_research_accepts_official_evidence_and_never_replaces_editor(monkeypatch):
    payload = {"nome": "Samsung Galaxy S24", "marca": "Samsung", "modelo": "Galaxy S24", "especificacaoCelular": {"nfc": False}}

    def local(category, seed, **kwargs):
        assert category == "CELULAR"
        found = deepcopy(seed)
        found["especificacaoCelular"].update({"nfc": True, "bateriaMah": 5000})
        return found, {"origemPorCampo": {"bateriaMah": {"fonte": "FABRICANTE_OFICIAL", "url": "https://www.samsung.com/teste",
                                                        "trecho": "Capacidade da bateria: 5000 mAh", "valor": 5000, "metodo": "EXTRACAO_DETERMINISTICA"}}}

    monkeypatch.setattr(intake, "research_hardware_locally", local)
    result = intake.research_verified_hardware(category="CELULAR", payload=payload, local_only=True)
    assert result["payload"]["especificacaoCelular"] == {"nfc": False, "bateriaMah": 5000}
    assert result["origemPorCampo"]["bateriaMah"]["evidenciaCampoConfirmada"]


def test_phone_nfc_requires_explicit_confirmation():
    assert extract_specs("CELULAR", [], "Não possui NFC")["nfc"] is False
    assert extract_specs("CELULAR", [], "Possui NFC")["nfc"] is True
    assert "nfc" not in extract_specs("CELULAR", [], "NFC não informado")
