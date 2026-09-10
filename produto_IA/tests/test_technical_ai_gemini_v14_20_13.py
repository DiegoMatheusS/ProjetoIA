import os

import pytest
import requests

from src.technical_ai.providers import GeminiProvider, TechnicalAIProviderError, TechnicalAIResponse
from src.technical_ai.service import build_technical_ai_prompt, enrich_hardware_with_external_ai


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeGemini:
    name = "GEMINI"
    configured = True

    def __init__(self, text):
        self.text = text
        self.prompts = []

    def enrich(self, prompt):
        self.prompts.append(prompt)
        return TechnicalAIResponse(
            provider="GEMINI",
            model="gemini-test",
            text=self.text,
            sources=[{"url": "https://example.com/spec", "titulo": "Ficha"}],
        )


def _gemini_payload(text):
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://example.com/spec", "title": "Ficha"}},
                        {"web": {"uri": "https://example.com/spec", "title": "Duplicada"}},
                    ]
                },
            }
        ]
    }


def test_gemini_provider_uses_env_key_header_and_google_search(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "segredo-teste")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("GEMINI_GOOGLE_SEARCH", "true")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "0")
    session = FakeSession([FakeResponse(data=_gemini_payload("Socket: AM5"))])
    provider = GeminiProvider(session=session)

    out = provider.enrich("Pesquise a CPU")

    assert out.provider == "GEMINI"
    assert out.model == "gemini-test"
    assert out.text == "Socket: AM5"
    assert out.sources == [{"url": "https://example.com/spec", "titulo": "Ficha"}]
    url, kwargs = session.calls[0]
    assert "segredo-teste" not in url
    assert kwargs["headers"]["x-goog-api-key"] == "segredo-teste"
    assert kwargs["json"]["tools"] == [{"google_search": {}}]
    assert kwargs["timeout"] >= 5


def test_gemini_provider_can_disable_google_search(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_GOOGLE_SEARCH", "false")
    session = FakeSession([FakeResponse(data=_gemini_payload("TDP: 65 W"))])
    provider = GeminiProvider(session=session)
    provider.enrich("CPU")
    assert "tools" not in session.calls[0][1]["json"]


def test_gemini_not_configured_is_specific_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = GeminiProvider(session=FakeSession([]))
    with pytest.raises(TechnicalAIProviderError) as exc:
        provider.enrich("CPU")
    assert exc.value.code == "PROVEDOR_NAO_CONFIGURADO"


def test_gemini_invalid_key_error_is_specific(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "0")
    session = FakeSession([FakeResponse(status_code=401, data={"error": {"message": "invalid key"}})])
    provider = GeminiProvider(session=session)
    with pytest.raises(TechnicalAIProviderError) as exc:
        provider.enrich("CPU")
    assert exc.value.code == "CHAVE_INVALIDA"
    assert "invalid key" in exc.value.message


def test_gemini_retries_transient_timeout(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "1")
    session = FakeSession([
        requests.Timeout("timeout"),
        FakeResponse(data=_gemini_payload("Arquitetura: Zen 4")),
    ])
    provider = GeminiProvider(session=session)
    out = provider.enrich("CPU")
    assert out.text == "Arquitetura: Zen 4"
    assert len(session.calls) == 2


def test_prompt_requests_only_real_missing_fields():
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 9 7900",
        "marca": "AMD",
        "modelo": "Ryzen 9 7900",
        "mpn": "100-100000590BOX",
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 12,
            "threads": 24,
            "tiposMemoriaSuportados": [],
        },
    }
    prompt, missing = build_technical_ai_prompt("PROCESSADOR", "AMD Ryzen 9 7900", payload)
    assert "tiposMemoriaSuportados" in missing
    assert "MPN" not in prompt or "100-100000590BOX" in prompt
    assert "AMD Ryzen 9 7900" in prompt
    assert "- socket\n" not in prompt
    assert "- nucleos\n" not in prompt
    assert "- threads\n" not in prompt
    assert "Google" not in prompt  # prompt não depende de um mecanismo específico


def test_external_ai_enrichment_reuses_v14_20_12_parser_and_only_fills_gaps(monkeypatch):
    response = """Arquitetura: Zen 4
Litografia: 5 nm
Cache L3: 64 MB
TDP: 65 W
TiposMemoriaSuportados: DDR5-5200
FrequenciaMemoriaMaximaMhz: 5200
Socket: AM4
"""
    fake = FakeGemini(response)
    monkeypatch.setattr("src.technical_ai.service.get_technical_ai_provider", lambda _name: fake)
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 9 7900",
        "marca": "AMD",
        "modelo": "Ryzen 9 7900",
        "preco": 999.99,
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 12,
            "threads": 24,
            "tiposMemoriaSuportados": [],
        },
    }

    out = enrich_hardware_with_external_ai(
        provider_name="GEMINI",
        category="PROCESSADOR",
        name="AMD Ryzen 9 7900",
        payload=payload,
        hardware_id=123,
        only_fill_gaps=True,
    )

    specs = out["payload"]["especificacaoProcessador"]
    assert out["utilizado"] is True
    assert out["provedor"] == "GEMINI"
    assert out["modelo"] == "gemini-test"
    assert out["hardwareId"] == 123
    assert specs["socket"] == "AM5"
    assert specs["arquitetura"] == "Zen 4"
    assert specs["litografiaNm"] == 5
    assert specs["cacheL3Mb"] == 64
    assert specs["tdpWatts"] == 65
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5200
    assert out["payload"]["preco"] == 999.99
    assert out["coberturaDepois"] > out["coberturaAntes"]
    assert "socket" not in out["camposPreenchidos"]
    assert any(x["campo"] == "socket" for x in out["conflitos"])
    assert out["fontesDeclaradas"][0]["url"] == "https://example.com/spec"
    assert out["somentePreencheLacunas"] is True
    assert out["payloadOriginal"]["especificacaoProcessador"]["socket"] == "AM5"


def test_external_ai_preserves_false_zero_and_never_overwrites(monkeypatch):
    fake = FakeGemini("SuportaEcc: Sim\nLanesPcie: 24\n")
    monkeypatch.setattr("src.technical_ai.service.get_technical_ai_provider", lambda _name: fake)
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "CPU",
        "especificacaoProcessador": {
            "socket": "AM5",
            "suportaEcc": False,
            "lanesPcie": 0,
            "tiposMemoriaSuportados": [],
        },
    }
    out = enrich_hardware_with_external_ai(
        provider_name="GEMINI", category="PROCESSADOR", name="CPU", payload=payload
    )
    specs = out["payload"]["especificacaoProcessador"]
    assert specs["suportaEcc"] is False
    assert specs["lanesPcie"] == 0
    assert {c["campo"] for c in out["conflitos"]} >= {"suportaEcc", "lanesPcie"}


def test_external_ai_does_not_allow_automatic_overwrite_mode(monkeypatch):
    with pytest.raises(TechnicalAIProviderError) as exc:
        enrich_hardware_with_external_ai(
            provider_name="GEMINI",
            category="PROCESSADOR",
            name="CPU",
            payload={"categoria": "PROCESSADOR", "especificacaoProcessador": {}},
            only_fill_gaps=False,
        )
    assert exc.value.code == "PAYLOAD_INVALIDO"


def test_external_ai_parser_without_usable_fields_is_specific_error(monkeypatch):
    fake = FakeGemini("Preço: R$ 1.999\nLoja: qualquer\n")
    monkeypatch.setattr("src.technical_ai.service.get_technical_ai_provider", lambda _name: fake)
    with pytest.raises(TechnicalAIProviderError) as exc:
        enrich_hardware_with_external_ai(
            provider_name="GEMINI",
            category="PROCESSADOR",
            name="CPU",
            payload={"categoria": "PROCESSADOR", "especificacaoProcessador": {"tiposMemoriaSuportados": []}},
        )
    assert exc.value.code == "PARSER_SEM_DADOS"
