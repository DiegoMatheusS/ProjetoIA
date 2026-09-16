from src.technical_ai.iterative_research import run_iterative_external_research
from src.technical_ai.providers import TechnicalAIResponse


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def enrich(self, prompt):
        self.prompts.append(prompt)
        text = self.responses.pop(0)
        return TechnicalAIResponse(
            provider="OPENAI",
            model="teste",
            text=text,
            sources=[],
        )


def _motherboard_payload(**specs):
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": dict(specs),
    }


def test_no_advance_first_round_uses_second_round_as_format_repair(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_REPAIR_ON_NO_ADVANCE", "true")
    provider = FakeProvider(
        [
            "Consultei as fontes, mas vou apresentar os dados em outro formato.",
            "chipset: B550",
        ]
    )

    result = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    assert len(provider.prompts) == 2
    assert "ATENCAO DE FORMATO" not in provider.prompts[0]
    assert "ATENCAO DE FORMATO" in provider.prompts[1]
    assert result.rounds[0]["status"] == "SEM_AVANCO"
    assert result.rounds[0]["modo"] == "PADRAO_META_AI"
    assert result.rounds[1]["modo"] == "REPARO_FORMATO"
    assert "chipset" in result.filled_fields
    assert result.payload["especificacaoPlacaMae"]["chipset"] == "B550"


def test_format_repair_never_creates_third_openai_call(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_REPAIR_ON_NO_ADVANCE", "true")
    provider = FakeProvider(
        [
            "Resposta em prosa sem linhas Campo: valor.",
            "Outra resposta sem nenhum campo reconhecivel.",
        ]
    )

    result = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    assert len(provider.prompts) == 2
    assert len(result.rounds) == 2
    assert result.rounds[-1]["status"] == "SEM_AVANCO"
    assert result.rounds[-1]["reparoDeFormato"] is True
    assert result.filled_fields == []


def test_format_repair_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_REPAIR_ON_NO_ADVANCE", "false")
    provider = FakeProvider(
        [
            "Resposta em prosa sem campos interpretaveis.",
            "chipset: B550",
        ]
    )

    result = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    assert len(provider.prompts) == 1
    assert len(result.rounds) == 1
    assert result.rounds[0]["status"] == "SEM_AVANCO"
    assert result.filled_fields == []


def test_normal_second_round_remains_meta_ai_prompt_when_first_round_advances(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_REPAIR_ON_NO_ADVANCE", "true")
    provider = FakeProvider(
        [
            "chipset: B550",
            "socket: AM4",
        ]
    )

    result = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    assert len(provider.prompts) == 2
    assert "ATENCAO DE FORMATO" not in provider.prompts[0]
    assert "ATENCAO DE FORMATO" not in provider.prompts[1]
    assert result.rounds[0]["modo"] == "PADRAO_META_AI"
    assert result.rounds[1]["modo"] == "PADRAO_META_AI"
    assert "chipset" in result.filled_fields
    assert "socket" in result.filled_fields
