from src.research_agent.evidence_resolver import resolve_cache_conflicts
from src.technical_ai.iterative_research import run_iterative_external_research
from src.technical_ai.providers import TechnicalAIProviderError, TechnicalAIResponse


def _motherboard_payload():
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": {
            "socket": "AM4",
            "tiposMemoriaSuportados": ["DDR4"],
        },
    }


def test_iterative_openai_reasks_only_remaining_gaps(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")

    class FakeProvider:
        calls = 0

        def enrich(self, prompt):
            self.calls += 1
            if self.calls == 1:
                assert "- chipset" in prompt
                return TechnicalAIResponse(
                    provider="OPENAI",
                    model="gpt-test",
                    text="chipset: B550",
                    sources=[{"url": "https://example.com/one", "titulo": "Fonte 1"}],
                )
            # "chipset" pode aparecer nas regras gerais do prompt, mas nao deve
            # voltar para a lista de Campos necessarios depois de preenchido.
            assert "- chipset" not in prompt
            assert "- formato" in prompt
            return TechnicalAIResponse(
                provider="OPENAI",
                model="gpt-test",
                text="formato: ATX",
                sources=[{"url": "https://example.com/two", "titulo": "Fonte 2"}],
            )

    provider = FakeProvider()
    out = run_iterative_external_research(
        provider=provider,
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
        local_info={},
    )

    specs = out.payload["especificacaoPlacaMae"]
    assert specs["chipset"] == "B550"
    assert specs["formato"] == "ATX"
    assert provider.calls == 2
    assert len(out.rounds) == 2
    assert "chipset" in out.filled_fields
    assert "formato" in out.filled_fields
    assert out.provenance["chipset"]["rodada"] == 1
    assert out.provenance["formato"]["rodada"] == 2


def test_second_openai_failure_preserves_first_round_progress(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "2")

    class FakeProvider:
        calls = 0

        def enrich(self, _prompt):
            self.calls += 1
            if self.calls == 1:
                return TechnicalAIResponse(
                    provider="OPENAI",
                    model="gpt-test",
                    text="chipset: B550",
                    sources=[],
                )
            raise TechnicalAIProviderError(
                "TIMEOUT_PROVEDOR",
                "timeout simulado",
                status_code=503,
            )

    out = run_iterative_external_research(
        provider=FakeProvider(),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
        local_info={},
    )

    assert out.payload["especificacaoPlacaMae"]["chipset"] == "B550"
    assert "chipset" in out.filled_fields
    assert out.provider_error is not None
    assert out.provider_error.code == "TIMEOUT_PROVEDOR"
    assert out.rounds[-1]["status"] == "ERRO_PROVEDOR"


def test_fresh_authoritative_evidence_can_replace_only_cached_value():
    original = _motherboard_payload()
    researched = _motherboard_payload()
    researched["especificacaoPlacaMae"] = {
        **researched["especificacaoPlacaMae"],
        "ethernet": "1 GbE",
    }
    info = {
        "origemPorCampo": {
            "ethernet": {
                "fonte": "PC_KOMBO",
                "url": "https://example.com/cache",
            }
        },
        "conflitos": [
            {
                "campo": "ethernet",
                "valorPrincipal": "1 GbE",
                "valorExterno": "2.5 GbE",
                "fonte": "FABRICANTE_OFICIAL",
                "url": "https://example.com/manufacturer",
            }
        ],
    }

    payload, resolved = resolve_cache_conflicts(
        "PLACA_MAE",
        original_payload=original,
        researched_payload=researched,
        info=info,
        cached_fields=["ethernet"],
    )

    assert payload["especificacaoPlacaMae"]["ethernet"] == "2.5 GbE"
    assert not resolved["conflitos"]
    assert resolved["camposCacheSubstituidosPorEvidenciaAtual"] == ["ethernet"]
    assert resolved["conflitosResolvidos"][0]["fonteEscolhida"] == "FABRICANTE_OFICIAL"


def test_original_confirmed_value_is_never_replaced_by_conflict():
    original = _motherboard_payload()
    original["especificacaoPlacaMae"]["ethernet"] = "1 GbE"
    researched = _motherboard_payload()
    researched["especificacaoPlacaMae"]["ethernet"] = "1 GbE"
    info = {
        "origemPorCampo": {"ethernet": {"fonte": "PC_KOMBO"}},
        "conflitos": [
            {
                "campo": "ethernet",
                "valorPrincipal": "1 GbE",
                "valorExterno": "2.5 GbE",
                "fonte": "FABRICANTE_OFICIAL",
            }
        ],
    }

    payload, resolved = resolve_cache_conflicts(
        "PLACA_MAE",
        original_payload=original,
        researched_payload=researched,
        info=info,
        cached_fields=["ethernet"],
    )

    assert payload["especificacaoPlacaMae"]["ethernet"] == "1 GbE"
    assert resolved["conflitos"]
    assert not resolved["camposCacheSubstituidosPorEvidenciaAtual"]
