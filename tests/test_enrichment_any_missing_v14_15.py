from src.main import build_result
from src.enrichment.core import TechnicalEnricher, should_auto_enrich, technical_missing_fields


def _ml_i5_9500_sparse_result():
    raw = {
        "ok": True,
        "title": "Processador Intel Core i5-9500 6 Cores 4.4GHz",
        "brand": "Intel",
        "model": "Core i5-9500",
        "mpn": None,
        "gtin": None,
        "description": "Processador Intel Core i5-9500 6 Cores 4.4GHz",
        "attributes": [
            {"name": "Marca", "value_name": "Intel"},
            {"name": "Modelo", "value_name": "Core i5-9500"},
            {"name": "Quantidade de núcleos", "value_name": "6"},
            {"name": "Frequência máxima", "value_name": "4.4 GHz"},
        ],
        "attributes_text": "Marca: Intel | Modelo: Core i5-9500 | Quantidade de núcleos: 6 | Frequência máxima: 4.4 GHz",
        "product_attributes": [],
        "url_original": "https://www.mercadolivre.com.br/processador-intel-core-i59500-6-cores-44ghz/up/MLBU4409116891?pdp_filters=item_id:MLB4940542185",
        "url_final": "https://www.mercadolivre.com.br/processador-intel-core-i59500-6-cores-44ghz/up/MLBU4409116891?pdp_filters=item_id:MLB4940542185",
        "price": 899.90,
        "source": "MERCADO_LIVRE_SURFSKY_CLOUD",
    }
    return build_result(raw, "PROCESSADOR")


def test_v14_15_ml_i5_9500_sparse_listing_triggers_external_enrichment():
    result = _ml_i5_9500_sparse_result()
    assert result["payloadParcialBackend"]["marca"] == "Intel"
    assert "i5-9500" in result["payloadParcialBackend"]["modelo"].casefold()
    assert technical_missing_fields(result)
    assert should_auto_enrich(result) is True


def test_v14_15_enrichment_fills_missing_fields_without_overwriting_marketplace_values():
    class FakeOfficialIntel:
        name = "FABRICANTE_OFICIAL"
        allow_browser_fallback = True

        def supports(self, category, identity):
            return category == "PROCESSADOR"

        def collect(self, identity, category):
            assert identity["marca"] == "Intel"
            assert "i5-9500" in identity["modelo"].casefold()
            return {
                "ok": True,
                "fonte": self.name,
                "url": "https://www.intel.com/example/i5-9500",
                "attributes": [],
                "context_text": """
                Intel Core i5-9500 Processor
                Code Name Products formerly Coffee Lake
                Lithography 14 nm
                Total Cores 6
                Total Threads 6
                Max Turbo Frequency 4.40 GHz
                Processor Base Frequency 3.00 GHz
                Intel Smart Cache 9 MB
                TDP 65 W
                Max Memory Size (dependent on memory type) 128 GB
                Memory Types DDR4-2666
                Max # of Memory Channels 2
                ECC Memory Supported No
                PCI Express Revision 3.0
                Max # of PCI Express Lanes 16
                Sockets Supported FCLGA1151
                Intel UHD Graphics 630
                T_JUNCTION 100°C
                """,
            }

    result = _ml_i5_9500_sparse_result()
    # O anúncio já informou 6 núcleos e 4.4 GHz. O enriquecimento deve preservar
    # esses dados e completar as lacunas restantes.
    before = result["especificacoesEncontradas"].copy()
    enriched = TechnicalEnricher(providers=[FakeOfficialIntel()], auto_mode=True).enrich(result)
    specs = enriched["especificacoesEncontradas"]
    assert specs["nucleos"] == before.get("nucleos") == 6
    assert specs["frequenciaTurboMhz"] == before.get("frequenciaTurboMhz") == 4400
    assert specs["socket"] == "LGA1151"
    assert specs["threads"] == 6
    assert specs["frequenciaBaseMhz"] == 3000
    assert specs["cacheL3Mb"] == 9
    assert specs["tdpWatts"] == 65
    assert specs["tiposMemoriaSuportados"] == ["DDR4"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 2666
    assert specs["capacidadeMemoriaMaximaGb"] == 128
    assert specs["canaisMemoria"] == 2
    assert str(specs["versaoPcie"]) == "3.0"
    assert specs["lanesPcie"] == 16
    assert enriched["enriquecimentoTecnico"]["executado"] is True
    assert "socket" in enriched["enriquecimentoTecnico"]["camposPreenchidos"]
    assert enriched["enriquecimentoTecnico"]["origemPorCampo"]["socket"]["fonte"] == "FABRICANTE_OFICIAL"
