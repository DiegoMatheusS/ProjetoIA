from copy import deepcopy

from src.research_agent import intake
from src.build_detection import research as pc
from src.enrichment.core import TechnicalEnricher
from src.enrichment.providers import ManufacturerProvider


def cpu_payload():
    return {"categoria": "PROCESSADOR", "nome": "Ryzen 5 5600G", "especificacaoProcessador": {"tdpWatts": 45}}


def origin(field, value, source="FABRICANTE_OFICIAL", url="https://www.amd.com/products/ryzen-5-5600g"):
    return {"fonte": source, "url": url, "trecho": f"{field}: {value}", "valor": value, "metodo": "EXTRACAO_DETERMINISTICA"}


def test_name_only_research_reads_official_attributes_without_llm_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class OfficialFixture:
        name = "FABRICANTE_OFICIAL"

        def collect(self, identity, category):
            assert identity["marca"] == "AMD"
            assert identity["modelo"] == "Ryzen 5 5600G"
            return {"ok": True, "fonte": self.name, "url": "https://www.amd.com/products/ryzen-5-5600g",
                    "attributes": [{"name": "CPU Cores", "value_name": "6"}, {"name": "Threads", "value_name": "12"}],
                    "context_text": "AMD Ryzen 5 5600G"}

    def local(category, payload, **kwargs):
        result = TechnicalEnricher(providers=[OfficialFixture()]).enrich({
            "categoriaDetectada": category, "payloadParcialBackend": payload,
            "especificacoesEncontradas": payload["especificacaoProcessador"],
        })
        return result["payloadParcialBackend"], result["enriquecimentoTecnico"]

    monkeypatch.setattr(intake, "research_hardware_locally", local)
    result = intake.research_verified_hardware(category="PROCESSADOR", payload=cpu_payload(), local_only=True)
    specs = result["payload"]["especificacaoProcessador"]
    assert specs["nucleos"] == 6 and specs["threads"] == 12
    assert specs["tdpWatts"] == 45
    assert result["payload"]["marca"] == "AMD"
    assert result["origemPorCampo"]["nucleos"]["evidenciaCampoConfirmada"]
    assert result["origemPorCampo"]["nucleos"]["coletadoEm"]


def test_unverified_ai_conflict_and_untrusted_host_do_not_fill_fields(monkeypatch):
    def local(category, payload, **kwargs):
        found = deepcopy(payload)
        found["especificacaoProcessador"].update({"nucleos": 6, "threads": 12, "socket": "AM4", "suportaEcc": False})
        return found, {"origemPorCampo": {
            "nucleos": origin("nucleos", 6), "threads": {"fonte": "OPENAI", "url": "https://amd.com", "trecho": "12"},
            "socket": origin("socket", "AM4", url="https://amd.com.attacker.test/product"),
            "suportaEcc": origin("suportaEcc", False),
        }, "conflitos": [{"campo": "nucleos", "valorPrincipal": 6, "valorExterno": 8}]}
    monkeypatch.setattr(intake, "research_hardware_locally", local)
    result = intake.research_verified_hardware(category="PROCESSADOR", payload=cpu_payload(), local_only=True)
    specs = result["payload"]["especificacaoProcessador"]
    assert "nucleos" not in specs and "threads" not in specs and "socket" not in specs
    assert specs["suportaEcc"] is False


def test_technical_database_is_accepted_but_chip_cannot_fill_board_dimensions(monkeypatch):
    def local(category, payload, **kwargs):
        found = deepcopy(payload)
        found["especificacaoPlacaVideo"] = {"memoriaVideoGb": 8, "comprimentoMm": 200, "clockBoostMhz": 2491}
        return found, {"origemPorCampo": {field: origin(field, value, "TECHPOWERUP", "https://www.techpowerup.com/gpu-specs/radeon-rx-6600")
                       for field, value in found["especificacaoPlacaVideo"].items()}}
    monkeypatch.setattr(intake, "research_hardware_locally", local)
    result = intake.research_verified_hardware(category="PLACA_VIDEO", payload={"nome": "Radeon RX 6600", "marca": "AMD"}, local_only=True)
    assert result["payload"]["especificacaoPlacaVideo"] == {"memoriaVideoGb": 8}
    assert result["escopoIdentidade"] == "CHIP_GRAFICO"


def test_different_cpu_suffix_is_rejected_by_official_page_parser():
    identity = {"metodo": "MARCA_MODELO", "marca": "AMD", "modelo": "Ryzen 5 5600G"}
    parsed = ManufacturerProvider()._parse_candidate_html("https://amd.com/cpu", "https://amd.com/cpu",
        '<html><h1>AMD Ryzen 5 5600</h1><table><tr><th>CPU Cores</th><td>6</td></tr></table></html>', identity)
    assert not parsed["ok"]


def test_pc_research_without_catalog_gets_cpu_but_never_chooses_generic_ram(monkeypatch):
    calls = []
    def fake(**kwargs):
        calls.append(kwargs)
        seed = kwargs["payload"]
        assert seed["modelo"] == "Ryzen 5 5600G"
        return {"utilizado": True, "motivo": "ESPECIFICACOES_DOCUMENTADAS", "escopoIdentidade": "MODELO_EXATO",
                "payload": {**seed, "especificacaoProcessador": {"nucleos": 6}}, "origemPorCampo": {"nucleos": origin("nucleos", 6)}}
    monkeypatch.setattr(pc, "research_verified_hardware", fake)
    description = "Processador: AMD Ryzen 5 5600G\nMemória RAM: 16 GB DDR4\nSSD: 500 GB\nAcompanha teclado e mouse"
    result = pc.research_pc_listing("Computador completo", description)
    pieces = {c["categoria"]: c for c in result["componentesDetectados"]}
    assert len(calls) == 1 and calls[0]["time_budget_seconds"] == 10
    assert pieces["PROCESSADOR"]["cadastroHardwareSugerido"]["especificacaoProcessador"]["nucleos"] == 6
    assert pieces["MEMORIA_RAM"]["statusPesquisa"] == "MODELO_EXATO_NAO_IDENTIFICADO"
    assert pieces["MEMORIA_RAM"]["hardwareId"] is None
    assert result["descricaoOriginal"] == description and result["nenhumRegistroCriado"]


def test_source_failure_preserves_pc_description_and_price(monkeypatch):
    monkeypatch.setattr(pc, "research_verified_hardware", lambda **kwargs: (_ for _ in ()).throw(ConnectionError()))
    offer = {"preco": 2999.90, "urlOriginal": "https://amazon.com.br/dp/example"}
    result = pc.research_imported_pc({"payloadParcialBackend": {"nome": "PC Gamer", "descricao": "AMD Ryzen 5 5600G"}, "ofertaColetada": offer})
    assert result["ofertaColetada"] == offer
    assert result["analiseComputador"]["componentesDetectados"][0]["statusPesquisa"] == "FONTE_INDISPONIVEL"


def test_auto_starts_local_research_even_without_external_provider(monkeypatch):
    from src.technical_ai import auto
    calls = []
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    def fake(**kwargs):
        calls.append(kwargs)
        return {"utilizado": False, "payload": kwargs["payload"], "camposPreenchidos": [], "origemPorCampo": {}}
    monkeypatch.setattr(auto, "enrich_hardware_with_external_ai", fake)
    auto.maybe_auto_enrich_hardware(category="PROCESSADOR", name="Ryzen 5 5600G", payload=cpu_payload())
    assert len(calls) == 1


def test_optional_pc_configuration_is_not_treated_as_installed_component(monkeypatch):
    monkeypatch.setattr(pc, "research_verified_hardware", lambda **kwargs: (_ for _ in ()).throw(AssertionError("Não pesquisar variante opcional")))
    result = pc.research_pc_listing("PC Gamer", "Processador: Ryzen 5 5600G ou Ryzen 7 5700G\nMemória RAM: 16GB")
    cpu = next(c for c in result["componentesDetectados"] if c["categoria"] == "PROCESSADOR")
    assert cpu["statusPesquisa"] == "MODELO_EXATO_NAO_IDENTIFICADO"


def test_processor_in_seller_attributes_is_researched_without_description(monkeypatch):
    calls = []
    def fake(**kwargs):
        calls.append(kwargs)
        return {"utilizado": False, "motivo": "SEM_DADOS_CONFIRMADOS", "escopoIdentidade": "MODELO_EXATO", "payload": kwargs["payload"], "origemPorCampo": {}}
    monkeypatch.setattr(pc, "research_verified_hardware", fake)
    result = pc.research_imported_pc({"payloadParcialBackend": {"nome": "PC Completo", "descricao": ""},
                                    "especificacoesEncontradas": {"componentes": [{"categoria": "PROCESSADOR", "nome": "AMD Ryzen 5 5600G"}]}})
    assert calls[0]["payload"]["modelo"] == "Ryzen 5 5600G"
    assert result["analiseComputador"]["descricaoOriginal"] == ""


def test_generic_memory_and_chipset_do_not_select_a_manufacturer_sku(monkeypatch):
    monkeypatch.setattr(intake, "research_hardware_locally", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SKU insuficiente")))
    for category, name in [("MEMORIA_RAM", "Kingston 16GB DDR4"), ("PLACA_MAE", "ASUS B550M")]:
        result = intake.research_verified_hardware(category=category, payload={"nome": name}, local_only=True)
        assert result["motivo"] == "MODELO_EXATO_NAO_IDENTIFICADO"
