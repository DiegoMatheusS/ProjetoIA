
from src.discovery.core import HardwareDiscoveryService
from src.discovery.sources import DiscoveryCandidate
from src.enrichment.core import TechnicalEnricher
from src.extractors.backend_schemas import SCHEMAS, HARDWARE_CATEGORIES


CATEGORY_EXAMPLES = {
    "PROCESSADOR": ("AMD Ryzen 5 7600X", "AMD", "Socket AM5 Clock 4.7 GHz Turbo 5.3 GHz 6 Cores 12 Threads"),
    "PLACA_MAE": ("ASUS TUF B650M-PLUS", "ASUS", "Micro-ATX Socket AM5 Chipset B650 4 Ramslots DDR5"),
    "MEMORIA_RAM": ("Corsair Vengeance DDR5 32GB", "Corsair", "DDR5-6000 2x16 GB DIMM CL30 1.35V XMP"),
    "PLACA_VIDEO": ("ASUS GeForce RTX 5070 12GB", "ASUS", "GeForce RTX 5070 12 GB 250W GDDR7 192 bit"),
    "ARMAZENAMENTO": ("Samsung 990 EVO 1TB", "Samsung", "1024 GB NVME Protocol M.2 Format"),
    "FONTE": ("Corsair RM750e", "Corsair", "80 PLUS Gold modular ATX 750W"),
    "GABINETE": ("Corsair 4000D Airflow", "Corsair", "Mid Tower ATX PC case"),
    "COOLER": ("DeepCool AK620", "DeepCool", "CPU cooler For socket AM5 LGA1700 120 mm 1850 RPM 68.99 CFM 28 dBA"),
    "VENTOINHA": ("Corsair AF120", "Corsair", "120 mm 2100 RPM 74 CFM 2.8 mm H2O 34 dBA PWM ARGB"),
}


class OneCandidateCatalog:
    allow_browser_fallback = True
    resolver = None

    def __init__(self, categoria):
        self.categoria = categoria

    def discover(self, categoria, marca=None, consulta=None, fontes=None, limit=20):
        nome, brand, text = CATEGORY_EXAMPLES[categoria]
        return [
            DiscoveryCandidate(
                nome=nome,
                url=f"https://example.com/{categoria.lower()}",
                fonte="PC_KOMBO",
                marca=brand,
                resumo={"catalog_text": text},
            )
        ], []


def test_v14_20_2_every_hardware_category_returns_the_full_schema():
    for categoria in sorted(HARDWARE_CATEGORIES):
        service = HardwareDiscoveryService(catalog=OneCandidateCatalog(categoria))
        result = service.discover(categoria, limite=1, detalhar=False, enriquecer=False)
        item = result["itens"][0]
        expected = SCHEMAS[categoria][2]
        specs = item["especificacoesEncontradas"]

        assert list(specs.keys())[:len(expected)] == expected
        assert set(expected).issubset(specs.keys())
        assert item["camposAusentes"] == [
            field for field in expected if specs.get(field) in (None, "", [])
        ]
        spec_field = SCHEMAS[categoria][1]
        assert item["payloadHardware"][spec_field] == specs


def test_v14_20_2_sources_are_frontend_friendly_and_keep_diagnostics():
    service = HardwareDiscoveryService(catalog=OneCandidateCatalog("PROCESSADOR"))
    result = service.discover("PROCESSADOR", limite=1, detalhar=False, enriquecer=False)
    item = result["itens"][0]

    assert item["fontes"] == ["PC-Kombo"]
    assert item["fontesDetalhadas"][0]["fonte"] == "PC_KOMBO"
    assert item["fonte"] == "PC-Kombo"


def test_v14_20_2_defaults_are_faster_than_v14_20_1(monkeypatch):
    for key in (
        "DISCOVERY_TOTAL_TIMEOUT_SECONDS",
        "DISCOVERY_ENRICHMENT_TIMEOUT_SECONDS",
        "DISCOVERY_ENRICHMENT_MAX_SOURCES",
        "DISCOVERY_DETAIL_WORKERS",
        "DISCOVERY_DETAIL_SOURCE_TIMEOUT_SECONDS",
        "DISCOVERY_BULK_TARGET_COVERAGE",
    ):
        monkeypatch.delenv(key, raising=False)

    service = HardwareDiscoveryService(catalog=OneCandidateCatalog("PROCESSADOR"))
    assert service.request_budget == 45.0
    assert service.detail_enrichment_timeout == 6.0
    assert service.detail_enrichment_sources == 2
    assert service.detail_workers == 8
    assert service.detail_source_timeout == 4
    assert service.bulk_target_coverage == 0.82


class FakeProvider:
    def __init__(self, name, calls, specs):
        self.name = name
        self.calls = calls
        self.specs = specs
        self.allow_browser_fallback = False

    def supports(self, category, identity):
        return True

    def collect(self, identity, category):
        self.calls.append(self.name)
        attrs = [{"name": k, "value_name": str(v)} for k, v in self.specs.items()]
        return {
            "ok": True,
            "fonte": self.name,
            "url": f"https://example.com/{self.name.lower()}",
            "attributes": attrs,
            "context_text": "",
        }


def test_v14_20_2_bulk_enrichment_excludes_candidate_source_and_limits_sources():
    calls = []
    # Os parsers podem não reconhecer os campos genéricos deste fake; o objetivo
    # aqui é garantir ordem/limite/exclusão, sem rede.
    providers = [
        FakeProvider("PC_KOMBO", calls, {}),
        FakeProvider("CPU_WORLD", calls, {}),
        FakeProvider("CPU_MONKEY", calls, {}),
        FakeProvider("GEIZHALS", calls, {}),
    ]
    enricher = TechnicalEnricher(
        providers=providers,
        auto_mode=True,
        total_timeout_override=2,
        max_sources_override=2,
        source_timeout_override=1,
        target_coverage_override=0.82,
        excluded_sources={"PC_KOMBO"},
    )
    result = {
        "categoriaDetectada": "PROCESSADOR",
        "payloadParcialBackend": {
            "marca": "AMD",
            "modelo": "Ryzen 5 7600X",
            "mpn": None,
            "gtin": None,
        },
        "especificacoesEncontradas": {"socket": "AM5"},
    }
    enricher.enrich(result)
    assert calls == ["CPU_MONKEY", "CPU_WORLD"]


def test_v14_20_2_filtered_pc_kombo_does_not_open_surfsky_after_match(monkeypatch):
    from src.discovery.sources import DiscoverySourceCatalog

    catalog = DiscoverySourceCatalog()
    html = """
    <html><body>
      <a href="/us/product/cpu/AMD-Ryzen-5-7600X">
        AMD Ryzen 5 7600X Socket AM5 Clock 4.7 GHz Turbo 5.3 GHz 6 Cores 12 Threads
      </a>
    </body></html>
    """
    monkeypatch.setattr(catalog, "_fetch_html", lambda *args, **kwargs: (html, "https://www.pc-kombo.com/us/components/cpus", None))
    calls = []
    monkeypatch.setattr(
        catalog,
        "_fetch_rendered_catalog",
        lambda *args, **kwargs: (calls.append("surfsky") or (None, args[0], "NAO_DEVERIA_CHAMAR")),
    )

    found, error = catalog._pc_kombo("PROCESSADOR", marca="AMD", consulta="7600X", limit=20)

    assert error is None
    assert len(found) == 1
    assert calls == []
