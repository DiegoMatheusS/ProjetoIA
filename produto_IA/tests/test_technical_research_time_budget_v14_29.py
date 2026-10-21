import requests

import src.technical_ai.iterative_research as iterative
from src.technical_ai.providers import OpenAIProvider, TechnicalAIResponse


class BudgetAwareProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def enrich_with_budget(self, prompt, *, budget_seconds):
        self.calls.append({"prompt": prompt, "budget": budget_seconds})
        text = self.responses.pop(0)
        return TechnicalAIResponse(
            provider="OPENAI",
            model="teste",
            text=text,
            sources=[],
        )


class FakeResponse:
    status_code = 200

    @staticmethod
    def json():
        return {
            "status": "completed",
            "output_text": "chipset: B550",
            "output": [],
        }


class RecordingSession:
    def __init__(self):
        self.timeouts = []

    def post(self, *args, **kwargs):
        self.timeouts.append(kwargs.get("timeout"))
        return FakeResponse()


def _motherboard_payload(**specs):
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": dict(specs),
    }


def test_iterative_research_uses_budget_aware_provider(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_TOTAL_BUDGET_SECONDS", "50")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_MAX_ROUND_SECONDS", "28")
    provider = BudgetAwareProvider(["chipset: B550", "socket: AM4"])

    result = iterative.run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    assert len(provider.calls) == 2
    assert all(3 <= call["budget"] <= 28 for call in provider.calls)
    assert result.rounds[0]["orcamentoRodadaSegundos"] <= 28
    assert result.rounds[1]["orcamentoRodadaSegundos"] <= 28
    assert "chipset" in result.filled_fields
    assert "socket" in result.filled_fields


def test_external_budget_can_stop_before_call(monkeypatch):
    monkeypatch.setattr(iterative, "_total_budget_seconds", lambda: 0.5)
    monkeypatch.setattr(iterative, "_max_round_budget_seconds", lambda: 0.5)
    provider = BudgetAwareProvider(["chipset: B550"])

    result = iterative.run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    assert provider.calls == []
    assert result.provider_error is not None
    assert result.provider_error.code == "ORCAMENTO_TEMPO_ESGOTADO"
    assert result.rounds[0]["status"] == "ORCAMENTO_TEMPO_ESGOTADO"


def test_openai_provider_caps_http_timeout_to_round_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-teste")
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")
    session = RecordingSession()
    provider = OpenAIProvider(session=session)

    response = provider.enrich_with_budget("teste", budget_seconds=7)

    assert response.text == "chipset: B550"
    assert len(session.timeouts) == 1
    assert 1 <= session.timeouts[0] <= 7
    assert response.raw_metadata["budgetSegundos"] == 7.0
    assert response.raw_metadata["timeoutEfetivoSegundos"] <= 7


def test_provider_does_not_retry_when_budget_is_already_consumed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-teste")
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")

    class TimeoutSession:
        def __init__(self):
            self.calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            raise requests.Timeout("timeout")

    session = TimeoutSession()
    provider = OpenAIProvider(session=session)

    try:
        provider.enrich_with_budget("teste", budget_seconds=3)
    except Exception as exc:
        assert getattr(exc, "code", None) in {"TIMEOUT_PROVEDOR", "ORCAMENTO_TEMPO_ESGOTADO"}
    else:
        raise AssertionError("Era esperado erro de timeout/orcamento")

    assert session.calls <= 2
