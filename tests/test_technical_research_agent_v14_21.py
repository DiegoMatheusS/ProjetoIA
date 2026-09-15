from src.extractors.dto_normalizer import normalize_hardware_payload_for_backend
from src.research_agent.agent import TechnicalResearchAgent
from src.research_agent.cache import merge_cached_gaps
from src.research_agent.confidence import annotate_field_confidence
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


def test_cache_fills_only_gaps_and_never_overwrites_confirmed_value():
    current = _motherboard_payload()
    cached = _motherboard_payload()
    cached["especificacaoPlacaMae"] = {
        **cached["especificacaoPlacaMae"],
        "socket": "AM5",
        "chipset": "B550",
        "formato": "ATX",
    }

    merged = merge_cached_gaps("PLACA_MAE", current, cached)
    specs = merged["especificacaoPlacaMae"]

    assert specs["socket"] == "AM4"
    assert specs["chipset"] == "B550"
    assert specs["formato"] == "ATX"


def test_confidence_marks_authoritative_source_and_reduces_conflicted_field():
    info = annotate_field_confidence({
        "origemPorCampo": {
            "chipset": {"fonte": "FABRICANTE_OFICIAL", "url": "https://example.com/msi"},
            "ethernet": {"fonte": "GEIZHALS", "url": "https://example.com/geizhals"},
        },
        "conflitos": [
            {"campo": "ethernet", "valorPrincipal": "1 GbE", "valorExterno": "2.5 GbE"}
        ],
    })

    assert info["confiancaPorCampo"]["chipset"]["nivel"] == "MUITO_ALTA"
    assert info["confiancaPorCampo"]["chipset"]["score"] == 0.98
    assert info["confiancaPorCampo"]["ethernet"]["comConflito"] is True
    assert info["confiancaPorCampo"]["ethernet"]["score"] < 0.86


def test_agent_builds_plan_runs_rounds_and_returns_same_enrichment_contract(monkeypatch):
    captured = {"calls": [], "provider_kwargs": []}

    class NoCache:
        def get(self, *_args, **_kwargs):
            return None

        def set(self, *_args, **_kwargs):
            return None

    class FakeResolver:
        focus_terms = ("chipset", "M.2 slots")
        queries_executed = ["MSI B550-A Pro chipset M.2 slots"]

    class FakeProvider:
        name = "FABRICANTE_OFICIAL"
        resolver = FakeResolver()

    class FakeEnricher:
        def __init__(self, **kwargs):
            captured["calls"].append(kwargs)

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

    def fake_build_providers(names, **kwargs):
        captured["provider_kwargs"].append(kwargs)
        return [FakeProvider() for _name in names[:1]]

    monkeypatch.setattr("src.research_agent.agent.TechnicalEnricher", FakeEnricher)
    monkeypatch.setattr("src.research_agent.agent.build_providers", fake_build_providers)

    payload, info = TechnicalResearchAgent(enabled=True, cache=NoCache()).research(
        category="PLACA_MAE",
        payload=_motherboard_payload(),
        name="MSI B550-A Pro",
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B550"
    assert info["camposPreenchidos"] == ["chipset"]
    assert info["agentePesquisa"]["ativo"] is True
    assert info["agentePesquisa"]["versao"] == 3
    assert info["agentePesquisa"]["plano"]["fontesPlanejadas"][0] == "FABRICANTE_OFICIAL"
    assert len(info["agentePesquisa"]["rodadas"]) >= 1
    assert info["agentePesquisa"]["consultasEspecificasExecutadas"] >= 1
    assert info["confiancaPorCampo"]["chipset"]["score"] == 0.98
    assert captured["calls"]
    assert all(call["auto_mode"] is True for call in captured["calls"])
    assert all(call["max_sources_override"] >= 1 for call in captured["calls"])
    assert captured["provider_kwargs"][0]["category"] == "PLACA_MAE"
    assert "chipset" in captured["provider_kwargs"][0]["missing_fields"]


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
