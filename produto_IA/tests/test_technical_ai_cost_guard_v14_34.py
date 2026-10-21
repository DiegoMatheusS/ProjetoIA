from src.technical_ai.iterative_research import run_iterative_external_research
from src.technical_ai.providers import TechnicalAIResponse


class CountingOpenAIProvider:
    name = "OPENAI"
    model = "gpt-5.6-luna"
    web_search = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.prompts = []

    def enrich(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        text = self.responses.pop(0)
        return TechnicalAIResponse(
            provider="OPENAI",
            model=self.model,
            text=text,
            sources=[],
        )


def _motherboard_minimal():
    return {
        "categoria": "PLACA_MAE",
        "nome": "Placa Teste B650",
        "marca": "Teste",
        "modelo": "B650 Teste",
        "especificacaoPlacaMae": {
            "socket": "AM5",
            "chipset": "B650",
            "formato": "ATX",
            "tiposMemoriaSuportados": ["DDR5"],
            "slotsMemoria": 4,
        },
    }


def _motherboard_high_coverage():
    return {
        "categoria": "PLACA_MAE",
        "nome": "ASRock B650E PG Riptide WIFI",
        "marca": "ASRock",
        "modelo": "B650E PG Riptide WIFI",
        "especificacaoPlacaMae": {
            "socket": "AM5",
            "chipset": "B650E",
            "formato": "ATX",
            "revisao": None,
            "biosInicial": None,
            "tiposMemoriaSuportados": ["DDR5"],
            "formatosMemoriaSuportados": ["DIMM"],
            "frequenciasMemoriaJedecMhz": [5200, 5600],
            "frequenciasMemoriaOverclockMhz": [7600],
            "slotsMemoria": 4,
            "capacidadeMaximaMemoriaGb": 256,
            "capacidadeMaximaPorSlotGb": 64,
            "suportaXmp": True,
            "suportaExpo": True,
            "suportaEcc": True,
            "suportaMemoriaRegistrada": False,
            "saidasVideo": ["1 x HDMI 2.1"],
            "portasSata": 4,
            "versaoPcie": "5.0",
            "wifi": True,
            "bluetooth": True,
            "ethernet": "Intel Killer E3100G (2.5Gb/s)",
            "biosFlashback": True,
            "biosMinima": None,
            "slotsM2": [
                {"codigo": "M2_1", "interfacesSuportadas": [], "chavesSuportadas": [], "tamanhosSuportadosMm": []},
                {"codigo": "M2_2", "interfacesSuportadas": [], "chavesSuportadas": [], "tamanhosSuportadosMm": []},
                {"codigo": "M2_3", "interfacesSuportadas": [], "chavesSuportadas": [], "tamanhosSuportadosMm": []},
            ],
        },
    }


def test_reuses_paid_openai_response_for_identical_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_RESPONSE_CACHE_ENABLED", "true")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    provider = CountingOpenAIProvider(["wifi: true"])

    first = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="Placa Teste B650",
        payload=_motherboard_minimal(),
    )
    second = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="Placa Teste B650",
        payload=_motherboard_minimal(),
    )

    assert provider.calls == 1
    assert first.rounds[0]["cacheHitOpenAI"] is False
    assert second.rounds[0]["cacheHitOpenAI"] is True
    assert second.rounds[0]["chamadaExecutada"] is False
    assert second.payload["especificacaoPlacaMae"]["wifi"] is True


def test_high_local_coverage_with_required_fields_skips_openai(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_SKIP_COVERAGE", "0.88")
    provider = CountingOpenAIProvider(["biosInicial: 1.00"])

    result = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="ASRock B650E PG Riptide WIFI",
        payload=_motherboard_high_coverage(),
        local_info={"camposPreenchidos": ["ethernet", "slotsM2"]},
    )

    assert provider.calls == 0
    assert result.rounds[0]["status"] == "OPENAI_IGNORADA_COBERTURA_LOCAL"
    assert result.rounds[0]["chamadaExecutada"] is False
    assert result.rounds[0]["camposObrigatoriosAusentes"] == []


def test_second_openai_round_is_not_used_for_optional_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_RESPONSE_CACHE_ENABLED", "true")
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")
    provider = CountingOpenAIProvider(["wifi: true", "bluetooth: true"])

    result = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="Placa Teste B650",
        payload=_motherboard_minimal(),
    )

    assert provider.calls == 1
    assert len(result.rounds) == 1
    assert result.rounds[0]["camposObrigatoriosAusentesDepois"] == []
    assert result.payload["especificacaoPlacaMae"]["wifi"] is True
