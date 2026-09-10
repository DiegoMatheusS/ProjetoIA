import asyncio

from src import api
from src.technical_ai import auto as auto_mod


class ConfiguredProvider:
    name = "GEMINI"
    configured = True


class UnconfiguredProvider:
    name = "GEMINI"
    configured = False


def _cpu_payload():
    return {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen Teste",
        "marca": "AMD",
        "modelo": "Ryzen Teste",
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 8,
            "threads": 16,
            "tiposMemoriaSuportados": [],
        },
    }


def test_maybe_auto_enrich_low_coverage_uses_provider_and_keeps_contract(monkeypatch):
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    monkeypatch.setenv("IA_TECNICA_AUTO_COVERAGE", "0.60")
    monkeypatch.setattr(auto_mod, "get_technical_ai_provider", lambda _name: ConfiguredProvider())

    def fake_enrich(**kwargs):
        payload = dict(kwargs["payload"])
        specs = dict(payload["especificacaoProcessador"])
        specs.update({
            "arquitetura": "Zen 4",
            "tdpWatts": 65,
            "tiposMemoriaSuportados": ["DDR5"],
            "frequenciaMemoriaMaximaMhz": 5200,
        })
        payload["especificacaoProcessador"] = specs
        return {
            "utilizado": True,
            "provedor": "GEMINI",
            "modelo": "gemini-test",
            "statusFicha": "PRECISA_REVISAO",
            "camposPreenchidos": ["arquitetura", "tdpWatts", "tiposMemoriaSuportados", "frequenciaMemoriaMaximaMhz"],
            "camposAusentes": [],
            "conflitos": [],
            "fontesDeclaradas": [],
            "payload": payload,
        }

    monkeypatch.setattr(auto_mod, "enrich_hardware_with_external_ai", fake_enrich)
    out = auto_mod.maybe_auto_enrich_hardware(
        category="PROCESSADOR", name="AMD Ryzen Teste", payload=_cpu_payload(), provider_name="GEMINI"
    )
    assert out["utilizado"] is True
    assert out["automatico"] is True
    assert out["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR5"]
    assert out["coberturaDepois"] > out["coberturaAntes"]


def test_auto_discovery_enriches_transparently_without_new_frontend_contract(monkeypatch):
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    monkeypatch.setenv("IA_TECNICA_AUTO_MAX_ITEMS", "20")
    monkeypatch.setattr(auto_mod, "get_technical_ai_provider", lambda _name: ConfiguredProvider())

    def fake_maybe(**kwargs):
        payload = dict(kwargs["payload"])
        specs = dict(payload["especificacaoProcessador"])
        specs["tiposMemoriaSuportados"] = ["DDR5"]
        specs["tdpWatts"] = 65
        specs["cacheL3Mb"] = 32
        payload["especificacaoProcessador"] = specs
        return {
            "automatico": True,
            "utilizado": True,
            "provedor": "GEMINI",
            "modelo": "gemini-test",
            "coberturaAntes": 0.20,
            "coberturaDepois": 0.65,
            "camposPreenchidos": ["tiposMemoriaSuportados", "tdpWatts", "cacheL3Mb"],
            "camposAusentes": ["litografiaNm"],
            "conflitos": [],
            "fontesDeclaradas": [],
            "statusFicha": "PRECISA_REVISAO",
            "payload": payload,
        }

    monkeypatch.setattr(auto_mod, "maybe_auto_enrich_hardware", fake_maybe)
    result = {
        "itens": [{
            "idTemporario": "processador-amd-ryzen-teste",
            "payloadHardware": _cpu_payload(),
            "fontes": ["PC-Kombo"],
        }]
    }
    out = auto_mod.auto_enrich_discovery_result("PROCESSADOR", result)
    item = out["itens"][0]
    assert item["idTemporario"] == "processador-amd-ryzen-teste"
    assert item["payloadHardware"] == item["payload"]
    assert item["payload"]["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR5"]
    assert "GEMINI" in item["fontes"]
    assert out["iaTecnicaAutomatica"]["tentados"] == 1
    assert out["iaTecnicaAutomatica"]["enriquecidos"] == 1


def test_provider_failure_never_breaks_discovery(monkeypatch):
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    monkeypatch.setattr(auto_mod, "get_technical_ai_provider", lambda _name: UnconfiguredProvider())
    original = _cpu_payload()
    result = {"itens": [{"payloadHardware": original, "fontes": ["PC-Kombo"]}]}
    out = auto_mod.auto_enrich_discovery_result("PROCESSADOR", result)
    assert out["itens"][0]["payloadHardware"] == original
    assert out["iaTecnicaAutomatica"]["provedorConfigurado"] is False
    assert out["iaTecnicaAutomatica"]["enriquecidos"] == 0


def test_link_flow_normalizes_null_boolean_and_memory_without_touching_offer(monkeypatch):
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    monkeypatch.setattr(auto_mod, "get_technical_ai_provider", lambda _name: UnconfiguredProvider())
    result = {
        "categoriaDetectada": "PROCESSADOR",
        "tipoCadastro": "HARDWARE",
        "payloadParcialBackend": {
            "nome": "CPU Teste",
            "categoria": "PROCESSADOR",
            "especificacaoProcessador": {
                "socket": "AM5",
                "tiposMemoriaSuportados": None,
                "coolerIncluso": None,
                "multiplicadorDesbloqueado": None,
                "suportaEcc": False,
            },
        },
        "ofertaColetada": {"preco": 999.9, "urlOriginal": "https://example.com/cpu"},
    }
    out = auto_mod.auto_enrich_link_result(result)
    specs = out["payloadParcialBackend"]["especificacaoProcessador"]
    assert specs["tiposMemoriaSuportados"] == []
    assert "coolerIncluso" not in specs
    assert "multiplicadorDesbloqueado" not in specs
    assert specs["suportaEcc"] is False
    assert out["ofertaColetada"] == {"preco": 999.9, "urlOriginal": "https://example.com/cpu"}
    assert out["enriquecimentoIaTecnica"]["utilizado"] is False


def test_existing_discovery_endpoint_invokes_auto_enrichment_without_new_route(monkeypatch):
    monkeypatch.delenv("PRODUTO_IA_API_KEY", raising=False)
    calls = []

    def fake_discover(*args, **kwargs):
        return {"itens": [{"payloadHardware": _cpu_payload()}]}

    def fake_auto(category, result):
        calls.append(category)
        result["autoTeste"] = True
        return result

    monkeypatch.setattr(api._discovery_service, "discover", fake_discover)
    monkeypatch.setattr(api, "auto_enrich_discovery_result", fake_auto)
    req = api.HardwareDiscoveryRequest(categoria="PROCESSADOR", limite=1, enriquecer=True)
    out = asyncio.run(api.descobrir_hardwares(req, None))
    assert calls == ["PROCESSADOR"]
    assert out["autoTeste"] is True


def test_existing_analisar_link_flow_invokes_auto_enrichment_and_preserves_url(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_DISABLE", "true")
    monkeypatch.setenv("ENRICHMENT_AUTO", "false")
    called = []

    raw = {
        "ok": True,
        "blocked": False,
        "source": "TESTE",
        "url_original": "https://example.com/cpu",
        "url_final": "https://example.com/cpu",
        "title": "AMD Ryzen 5 Teste",
        "brand": "AMD",
        "model": "Ryzen 5 Teste",
        "mpn": "TEST-MPN",
        "gtin": None,
        "image_url": None,
        "description": "Processador socket AM5 DDR5",
        "price": 500.0,
        "previous_price": 600.0,
        "price_source": "TESTE",
        "currency": "BRL",
        "available": True,
        "attributes": [],
        "product_attributes": [],
    }

    monkeypatch.setattr(api.GenericScraper, "collect", lambda self, url, no_browser=False: dict(raw))

    def fake_auto(result):
        called.append(True)
        result["iaTecnicaAutomatica"] = {"utilizado": False, "motivo": "TESTE"}
        return result

    monkeypatch.setattr(api, "auto_enrich_link_result", fake_auto)
    out = api._analyze_sync(api.AnalyzeRequest(url="https://example.com/cpu", categoria="PROCESSADOR"))
    assert called == [True]
    assert out["ofertaColetada"]["urlOriginal"] == "https://example.com/cpu"
    assert out["ofertaColetada"]["preco"] == 500.0
