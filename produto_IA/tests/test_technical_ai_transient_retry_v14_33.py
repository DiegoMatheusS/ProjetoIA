from src.technical_ai.providers import TechnicalAIProviderError, TechnicalAIResponse
from src.technical_ai.retry_research import run_iterative_external_research_with_retry


class TimeoutThenSuccessProvider:
    def __init__(self):
        self.calls = 0

    def enrich_with_budget(self, prompt, *, budget_seconds):
        self.calls += 1
        if self.calls == 1:
            raise TechnicalAIProviderError(
                "TIMEOUT_PROVEDOR",
                "Timeout ao consultar OpenAI",
                status_code=504,
                transient=True,
            )
        return TechnicalAIResponse(
            provider="OPENAI",
            model="gpt-test",
            text="tiposMemoriaSuportados: DDR5",
            sources=[],
        )


class NoCreditsProvider:
    def __init__(self):
        self.calls = 0

    def enrich_with_budget(self, prompt, *, budget_seconds):
        self.calls += 1
        raise TechnicalAIProviderError(
            "LIMITE_PROVEDOR",
            "You have no credits remaining",
            status_code=503,
            transient=True,
            provider_status_code=429,
        )


def _payload():
    return {
        "categoria": "PLACA_MAE",
        "nome": "ASRock B650E PG Riptide WIFI",
        "marca": "ASRock",
        "modelo": "B650E PG Riptide WIFI",
        "especificacaoPlacaMae": {
            "socket": "AM5",
            "chipset": "B650E",
            "formato": "ATX",
            "slotsMemoria": 4,
            "wifi": True,
            "tiposMemoriaSuportados": [],
        },
    }


def test_transient_timeout_gets_one_real_retry_and_preserves_recovered_fields(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_TRANSIENT_RETRY_BUDGET_SECONDS", "10")
    provider = TimeoutThenSuccessProvider()

    result = run_iterative_external_research_with_retry(
        provider=provider,
        category="PLACA_MAE",
        name="ASRock B650E PG Riptide WIFI",
        payload=_payload(),
        local_info={},
    )

    assert provider.calls == 2
    assert result.provider_error is None
    assert "tiposMemoriaSuportados" in result.filled_fields
    assert result.payload["especificacaoPlacaMae"]["tiposMemoriaSuportados"] == ["DDR5"]
    assert any(row.get("tentativaExterna") == "RETRY_TRANSIENTE" for row in result.rounds)


def test_no_credit_error_is_not_retried(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    provider = NoCreditsProvider()

    result = run_iterative_external_research_with_retry(
        provider=provider,
        category="PLACA_MAE",
        name="ASRock B650E PG Riptide WIFI",
        payload=_payload(),
        local_info={},
    )

    assert provider.calls == 1
    assert result.provider_error is not None
    assert result.provider_error.code == "LIMITE_PROVEDOR"
