from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend
from src.research_agent.agent import TechnicalResearchAgent
from src.research_agent.planner import build_research_plan
from src.technical_ai.providers import TechnicalAIResponse
from src.technical_ai.service import enrich_hardware_with_external_ai


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


def test_planner_prioritizes_authoritative_sources_and_leaves_pc_kombo_as_fallback():
    payload = normalize_hardware_payload_for_backend("PLACA_MAE", _motherboard_payload())
    result = {
        "categoriaDetectada": "PLACA_MAE",
        "especificacoesEncontradas": payload["especificacaoPlacaMae"],
        "payloadParcialBackend": payload,
    }

    plan = build_research_plan("PLACA_MAE", result)

    assert plan.mode == "PROFUNDA"
    assert plan.sources[0] == "FABRICANTE_OFICIAL"
    assert plan.sources[-1] == "PC_KOMBO"
    assert "chipset" in plan.missing_fields
    assert "slotsM2" in plan.missing_fields
    assert plan.max_sources <= len(plan.sources)


def test_agent_builds_plan_and_returns_same_enrichment_contract(monkeypatch):
    captured = {}

    class FakeEnricher:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def enrich(self, result):
            output = dict(result)
            payload = dict(result["payloadParcialBackend"])
            specs = dict(payload["especificacaoPlacaMae"])
            specs["chipset"] = "B550"
            payload["especificacaoPlacaMae"] = specs
            output["payloadParcialBackend"] = payload
            output["especificacoesEncontradas"] = specs
            output["enriquecimentoTecnico"] = {
                "executado": True,
                "camposPreenchidos": ["chipset"],
                "fontesConsultadas": [
                    {
                        "fonte": "FABRICANTE_OFICIAL",
                        "ok": True,
                        "url": "https://example.com/msi-b550-a-pro",
                    }
                ],
                "origemPorCampo": {
                    "chipset": {
                        "fonte": "FABRICANTE_OFICIAL",
                        "url": "https://example.com/msi-b550-a-pro",
                    }
                },
                "conflitos": [],
            }
            return output

    monkeypatch.setattr("src.research_agent.agent.TechnicalEnricher", FakeEnricher)
    monkeypatch.setattr(
        "src.research_agent.agent.build_providers",
        lambda names: [f"fake:{name}" for name in names],
    )

    payload, info = TechnicalResearchAgent(enabled=True).research(
        category="PLACA_MAE",
        payload=_motherboard_payload(),
        name="MSI B550-A Pro",
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B550"
    assert info["camposPreenchidos"] == ["chipset"]
    assert info["agentePesquisa"]["ativo"] is True
    assert info["agentePesquisa"]["versao"] == 1
    assert info["agentePesquisa"]["plano"]["fontesPlanejadas"][0] == "FABRICANTE_OFICIAL"
    assert captured["auto_mode"] is True
    assert captured["max_sources_override"] >= 1


def test_agent_failure_does_not_block_openai_meta_prompt_flow(monkeypatch):
    class FakeOpenAI:
        name = "OPENAI"
        configured = True

        def enrich(self, prompt):
            assert "Responda exatamente no formato Campo: valor" in prompt
            return TechnicalAIResponse(
                provider="OPENAI",
                model="gpt-test",
                text="chipset: B550\nformato: ATX",
                sources=[{"url": "https://example.com/spec", "titulo": "Ficha"}],
            )

    def fail_agent(*_args, **_kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("src.technical_ai.service.research_hardware_locally", fail_agent)
    monkeypatch.setattr(
        "src.technical_ai.service.get_technical_ai_provider",
        lambda _name: FakeOpenAI(),
    )
    monkeypatch.setattr(
        "src.technical_ai.service.collect_cited_sources",
        lambda *_args, **_kwargs: None,
    )

    out = enrich_hardware_with_external_ai(
        provider_name="OPENAI",
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
    )

    specs = out["payload"]["especificacaoPlacaMae"]
    assert specs["chipset"] == "B550"
    assert specs["formato"] == "ATX"
    assert "chipset" in out["camposPreenchidos"]
    assert out["enriquecimentoProprio"]["motivoIgnorado"] == "ERRO_AGENTE_PESQUISA_TECNICA"
    assert out["enriquecimentoProprio"]["agentePesquisa"]["resultado"] == "ERRO_COM_FALLBACK_OPENAI"
