from src.research_agent.cache import (
    filter_cached_entry_for_reuse,
    merge_cached_gaps,
)


def _payload(**specs):
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": dict(specs),
    }


def _value(specs, field):
    return specs.get(field)


def test_cache_reuses_only_fields_with_quality_and_without_conflict(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_CACHE_MIN_CONFIDENCE", "0.80")
    monkeypatch.setenv("TECH_RESEARCH_CACHE_REQUIRE_PROVENANCE", "true")

    cached = {
        "payload": _payload(
            chipset="B550",
            ethernet="Realtek 1 GbE",
            wifi=True,
        ),
        "origemPorCampo": {
            "chipset": {"fonte": "FABRICANTE_OFICIAL", "url": "https://example.com/msi"},
            "ethernet": {"fonte": "PC_KOMBO", "url": "https://example.com/pc-kombo"},
            "wifi": {"fonte": "ICECAT", "url": "https://example.com/icecat"},
        },
        "confiancaPorCampo": {
            "chipset": {"fonte": "FABRICANTE_OFICIAL", "score": 0.98, "comConflito": False},
            "ethernet": {"fonte": "PC_KOMBO", "score": 0.78, "comConflito": False},
            "wifi": {"fonte": "ICECAT", "score": 0.94, "comConflito": True},
        },
        "conflitos": [
            {
                "campo": "wifi",
                "valorPrincipal": True,
                "valorExterno": False,
                "fonte": "GEIZHALS",
            }
        ],
    }

    filtered = filter_cached_entry_for_reuse("PLACA_MAE", cached)
    specs = filtered["payload"]["especificacaoPlacaMae"]

    assert _value(specs, "chipset") == "B550"
    assert _value(specs, "ethernet") in (None, "", [])
    assert _value(specs, "wifi") in (None, "", [])
    assert filtered["cacheQualidade"]["camposReutilizaveis"] == ["chipset"]

    ignored = {
        item["campo"]: item["motivo"]
        for item in filtered["cacheQualidade"]["camposIgnorados"]
    }
    assert ignored["ethernet"] == "CONFIANCA_ABAIXO_DO_LIMIAR"
    assert ignored["wifi"] == "CONFLITO_NAO_RESOLVIDO"


def test_cache_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_CACHE_MIN_CONFIDENCE", "0.90")
    monkeypatch.setenv("TECH_RESEARCH_CACHE_REQUIRE_PROVENANCE", "true")

    cached = {
        "payload": _payload(chipset="B550"),
        "origemPorCampo": {
            "chipset": {"fonte": "GEIZHALS"},
        },
        "confiancaPorCampo": {
            "chipset": {"fonte": "GEIZHALS", "score": 0.86, "comConflito": False},
        },
    }

    filtered = filter_cached_entry_for_reuse("PLACA_MAE", cached)
    specs = filtered["payload"]["especificacaoPlacaMae"]

    assert _value(specs, "chipset") in (None, "", [])
    assert filtered["cacheQualidade"]["camposIgnorados"][0]["motivo"] == "CONFIANCA_ABAIXO_DO_LIMIAR"


def test_cache_can_require_explicit_source_provenance(monkeypatch):
    cached = {
        "payload": _payload(chipset="B550"),
        "origemPorCampo": {"chipset": {}},
        "confiancaPorCampo": {
            "chipset": {"fonte": None, "score": 0.95, "comConflito": False},
        },
    }

    monkeypatch.setenv("TECH_RESEARCH_CACHE_MIN_CONFIDENCE", "0.80")
    monkeypatch.setenv("TECH_RESEARCH_CACHE_REQUIRE_PROVENANCE", "true")
    strict = filter_cached_entry_for_reuse("PLACA_MAE", cached)
    assert strict["payload"]["especificacaoPlacaMae"].get("chipset") in (None, "", [])
    assert strict["cacheQualidade"]["camposIgnorados"][0]["motivo"] == "SEM_PROVENIENCIA"

    monkeypatch.setenv("TECH_RESEARCH_CACHE_REQUIRE_PROVENANCE", "false")
    relaxed = filter_cached_entry_for_reuse("PLACA_MAE", cached)
    assert relaxed["payload"]["especificacaoPlacaMae"]["chipset"] == "B550"


def test_cache_merge_never_overwrites_current_value(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_CACHE_MIN_CONFIDENCE", "0.80")
    monkeypatch.setenv("TECH_RESEARCH_CACHE_REQUIRE_PROVENANCE", "true")

    cached = {
        "payload": _payload(chipset="B550"),
        "origemPorCampo": {
            "chipset": {"fonte": "FABRICANTE_OFICIAL"},
        },
        "confiancaPorCampo": {
            "chipset": {"fonte": "FABRICANTE_OFICIAL", "score": 0.98, "comConflito": False},
        },
    }
    filtered = filter_cached_entry_for_reuse("PLACA_MAE", cached)

    merged = merge_cached_gaps(
        "PLACA_MAE",
        _payload(chipset="X570"),
        filtered["payload"],
    )

    assert merged["especificacaoPlacaMae"]["chipset"] == "X570"
