import json
import requests

import pytest

from src.extractors.meta_ai_whatsapp import build_meta_ai_prompt
from src.technical_ai.providers import (
    OpenAIProvider,
    TechnicalAIProviderError,
    TechnicalAIResponse,
    get_technical_ai_provider,
)
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


class FakeOpenAI:
    name = "OPENAI"
    configured = True

    def __init__(self, text):
        self.text = text
        self.prompts = []

    def enrich(self, prompt):
        self.prompts.append(prompt)
        return TechnicalAIResponse(
            provider="OPENAI",
            model="gpt-test",
            text=self.text,
            sources=[{"url": "https://example.com/spec", "titulo": "Ficha"}],
        )


class FailingOpenAI:
    name = "OPENAI"
    configured = True

    def enrich(self, _prompt):
        raise TechnicalAIProviderError(
            "LIMITE_PROVEDOR",
            "quota esgotada",
            status_code=503,
            transient=True,
            provider_status_code=429,
        )


def _openai_payload(text):
    return {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/spec",
                                "title": "Ficha",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _disable_local_enrichment(monkeypatch):
    monkeypatch.setattr(
        "src.technical_ai.service._local_enrich",
        lambda _category, payload: (dict(payload), {"camposPreenchidos": [], "fontesConsultadas": [], "conflitos": []}),
    )


def test_openai_provider_uses_env_key_bearer_and_web_search(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "segredo-teste")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_WEB_SEARCH", "true")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    session = FakeSession([FakeResponse(data=_openai_payload("Socket: AM5"))])
    provider = OpenAIProvider(session=session)

    out = provider.enrich("Pesquise a CPU")

    assert out.provider == "OPENAI"
    assert out.model == "gpt-test"
    assert out.text == "Socket: AM5"
    assert out.sources == [{"url": "https://example.com/spec", "titulo": "Ficha"}]
    url, kwargs = session.calls[0]
    assert url == "https://api.openai.com/v1/responses"
    assert "segredo-teste" not in url
    assert kwargs["headers"]["Authorization"] == "Bearer segredo-teste"
    assert kwargs["json"]["tools"] == [{"type": "web_search"}]
    assert kwargs["json"]["store"] is False


def test_openai_provider_can_disable_web_search(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_WEB_SEARCH", "false")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    session = FakeSession([FakeResponse(data=_openai_payload("TDP: 65 W"))])
    provider = OpenAIProvider(session=session)
    provider.enrich("CPU")
    assert "tools" not in session.calls[0][1]["json"]


def test_openai_not_configured_is_specific_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider(session=FakeSession([]))
    with pytest.raises(TechnicalAIProviderError) as exc:
        provider.enrich("CPU")
    assert exc.value.code == "PROVEDOR_NAO_CONFIGURADO"


def test_openai_invalid_key_error_is_specific(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    session = FakeSession([FakeResponse(status_code=401, data={"error": {"message": "invalid key"}})])
    provider = OpenAIProvider(session=session)
    with pytest.raises(TechnicalAIProviderError) as exc:
        provider.enrich("CPU")
    assert exc.value.code == "CHAVE_INVALIDA"
    assert exc.value.provider_status_code == 401
    assert "invalid key" in exc.value.message


def test_openai_quota_error_is_specific(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    session = FakeSession([FakeResponse(status_code=429, data={"error": {"message": "quota"}})])
    provider = OpenAIProvider(session=session)
    with pytest.raises(TechnicalAIProviderError) as exc:
        provider.enrich("CPU")
    assert exc.value.code == "LIMITE_PROVEDOR"
    assert exc.value.status_code == 503
    assert exc.value.provider_status_code == 429


def test_openai_retries_transient_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")
    session = FakeSession([
        requests.Timeout("timeout"),
        FakeResponse(data=_openai_payload("Arquitetura: Zen 4")),
    ])
    provider = OpenAIProvider(session=session)
    out = provider.enrich("CPU")
    assert out.text == "Arquitetura: Zen 4"
    assert len(session.calls) == 2


def test_legacy_gemini_selection_is_routed_to_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    provider = get_technical_ai_provider("GEMINI")
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "OPENAI"


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
    assert "AMD Ryzen 9 7900" in prompt
    assert prompt == build_meta_ai_prompt("PROCESSADOR", "AMD Ryzen 9 7900", missing)
    assert "Responda exatamente no formato Campo: valor" in prompt
    assert "100-100000590BOX" not in prompt


def test_external_ai_enrichment_only_fills_gaps_after_local_layer(monkeypatch):
    _disable_local_enrichment(monkeypatch)
    facts = {"arquitetura": ("Zen 4", "Arquitetura: Zen 4"), "tiposMemoriaSuportados": (["DDR5"], "TiposMemoriaSuportados: DDR5"), "socket": ("AM4", "Socket: AM4")}
    fake = FakeOpenAI(json.dumps({"especificacoes": {k: v[0] for k, v in facts.items()}, "evidencias": {k: {"url": "https://example.com/spec", "trecho": v[1]} for k, v in facts.items()}}))
    def local(category, payload):
        return payload, {"evidenciasColetadas": [{"url": "https://example.com/spec", "trechos": [v[1] for v in facts.values()]}]}
    monkeypatch.setattr("src.technical_ai.service._local_enrich", local)
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
        provider_name="OPENAI",
        category="PROCESSADOR",
        name="AMD Ryzen 9 7900",
        payload=payload,
        hardware_id=123,
        only_fill_gaps=True,
    )

    specs = out["payload"]["especificacaoProcessador"]
    assert out["utilizado"] is True
    assert out["provedor"] == "OPENAI"
    assert specs["socket"] == "AM5"
    assert specs["arquitetura"] == "Zen 4"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert out["payload"]["preco"] == 999.99
    assert "socket" not in out["camposPreenchidos"]
    assert any(x["campo"] == "socket" for x in out["conflitos"])


def test_openai_failure_returns_local_result_instead_of_raising(monkeypatch):
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 9 7900",
        "marca": "AMD",
        "modelo": "Ryzen 9 7900",
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 12,
            "threads": 24,
            "tiposMemoriaSuportados": [],
        },
    }
    local_payload = {
        **payload,
        "especificacaoProcessador": {
            **payload["especificacaoProcessador"],
            "arquitetura": "Zen 4",
        },
    }
    monkeypatch.setattr(
        "src.technical_ai.service._local_enrich",
        lambda _category, _payload: (
            local_payload,
            {
                "camposPreenchidos": ["arquitetura"],
                "fontesConsultadas": [{"fonte": "FABRICANTE_OFICIAL", "ok": True}],
                "conflitos": [],
            },
        ),
    )
    monkeypatch.setattr("src.technical_ai.service.get_technical_ai_provider", lambda _name: FailingOpenAI())

    out = enrich_hardware_with_external_ai(
        provider_name="OPENAI",
        category="PROCESSADOR",
        name="AMD Ryzen 9 7900",
        payload=payload,
    )

    assert out["provedor"] == "PROJETO_IA"
    assert out["provedorExterno"] == "OPENAI"
    assert out["fallbackExternoFalhou"] is True
    assert out["erroProvedor"]["codigo"] == "LIMITE_PROVEDOR"
    assert out["erroProvedor"]["statusProvedor"] == 429
    assert out["payload"]["especificacaoProcessador"]["arquitetura"] == "Zen 4"
    assert "FABRICANTE_OFICIAL" in out["fontesIaPropria"]


def test_external_ai_does_not_allow_automatic_overwrite_mode():
    with pytest.raises(TechnicalAIProviderError) as exc:
        enrich_hardware_with_external_ai(
            provider_name="OPENAI",
            category="PROCESSADOR",
            name="CPU",
            payload={"categoria": "PROCESSADOR", "especificacaoProcessador": {}},
            only_fill_gaps=False,
        )
    assert exc.value.code == "PAYLOAD_INVALIDO"
