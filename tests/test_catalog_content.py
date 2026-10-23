import json
from pathlib import Path

import pytest

from src.catalog_content import technical_name, technical_description, refine_catalog_result
from src.enrichment.identity import build_identity, identity_is_strong
from src.research_agent.focused_search import FocusedSearchResolver
from src.research_agent.products import research_product_specs


CASES = json.loads((Path(__file__).parent / 'fixtures/catalog-names.json').read_text())


@pytest.mark.parametrize('case', CASES)
def test_technical_name_preserves_sku_and_removes_narrative(case):
    assert technical_name(case['nome'], case.get('marca'), case.get('modelo'), case.get('categoria')) == case['esperado']


def test_description_uses_only_available_specs_including_false_and_zero():
    text = technical_description('PROCESSADOR', 'AMD Ryzen 5 5600G', {
        'nucleos': 6, 'threads': 12, 'tdpWatts': 65,
        'possuiVideoIntegrado': False, 'cacheL3Mb': 0,
        'id': 1555, 'historia': 'Desde 1989', 'preco': 399,
    }, 'Conheça nossa história. Produto perfeito e o melhor preço.')
    assert 'Núcleos: 6' in text and '65 W' in text
    assert 'Não' in text and '0 MB' in text
    assert 'história' not in text and 'melhor preço' not in text
    assert 'MHz' not in text
    assert '1555' not in text and '1989' not in text and '399' not in text


def test_original_listing_survives_technical_catalog_summary():
    original = 'Nossa história começou há décadas. SSD com capacidade de 1000 GB.'
    result = refine_catalog_result({
        'categoriaDetectada': 'ARMAZENAMENTO', 'especificacoesEncontradas': {'capacidadeGb': 1000},
        'payloadParcialBackend': {'nome': 'SSD Kingston NV2. Conheça sua história.', 'descricao': original},
    })
    assert result['descricaoAnuncio'] == original
    assert result['payloadParcialBackend']['nome'] == 'SSD Kingston NV2'
    assert '1000 GB' in result['payloadParcialBackend']['descricao']
    assert 'história' not in result['payloadParcialBackend']['descricao']


def test_multiword_commercial_model_is_specific_but_adjectives_are_not():
    assert identity_is_strong(build_identity({'payloadParcialBackend': {'marca': 'HyperX', 'modelo': 'Cloud III'}}))
    assert not identity_is_strong(build_identity({'payloadParcialBackend': {'marca': 'HyperX', 'modelo': 'Wireless Pro'}}))


def test_wrong_variant_focus_can_reach_exact_model_query():
    class Search:
        timeout = 4
        def results(self, query, domains, limit=3):
            return [{'url': 'https://official.example/exact' if query == 'Brand "M2"' else 'https://official.example/wrong'}]
    resolver = FocusedSearchResolver(Search(), category='PLACA_VIDEO', missing_fields=['comprimentoMm'])
    rows = resolver.fallback_results('Brand "M2"', ['official.example'], time_budget_seconds=1)
    assert rows[-1]['url'].endswith('/exact')
    assert resolver.queries_executed[-1] == 'Brand "M2"'


class ProductSource:
    name = 'FABRICANTE_OFICIAL'
    def __init__(self, watts='100 W'):
        self.watts = watts
    def collect(self, identity, category):
        return {'ok': True, 'fonte': self.name, 'url': 'https://official.example/M200',
                'attributes': [{'name': 'Potência', 'value_name': self.watts},
                               {'name': 'Tensão', 'value_name': '220 V'},
                               {'name': 'Frete', 'value_name': 'Grátis'},
                               {'name': '__proto__', 'value_name': 'poluição'}]}


def test_generic_product_records_explicit_fields_with_sources_and_preserves_manual_values():
    result = research_product_specs(category='IMPRESSORA_3D', payload={
        'nome': 'Impressora Maker M200', 'marca': 'Maker', 'modelo': 'M200',
        'metadados': {'especificacoes': {'Tensão': '127 V', 'Duplex': False}},
    }, providers=[ProductSource()])
    specs = result['payload']['metadados']['especificacoesEncontradas']
    assert specs['Potência'] == '100 W' and specs['Tensão'] == '127 V'
    assert specs['Duplex'] is False
    assert 'Frete' not in specs and '__proto__' not in specs
    assert result['origemPorCampo']['Potência']['trecho'] == 'Potência: 100 W'
    assert '100 W' in result['descricaoTecnica']


def test_generic_product_conflicting_sources_leave_field_unconfirmed():
    result = research_product_specs(category='IMPRESSORA_3D', payload={
        'nome': 'Maker M200', 'marca': 'Maker', 'modelo': 'M200',
    }, providers=[ProductSource('100 W'), ProductSource('150 W')])
    assert 'Potência' not in result['payload']['metadados']['especificacoesEncontradas']
    assert any(item['campo'] == 'Potência' for item in result['conflitos'])


def test_generic_product_without_specific_model_does_not_guess_or_call_source():
    class FailSource:
        def collect(self, *args):
            pytest.fail('Pesquisa não pode começar sem identidade do modelo')
    result = research_product_specs(category='IMPRESSORA_3D', payload={'nome': 'Impressora em promoção'}, providers=[FailSource()])
    assert result['camposPreenchidos'] == []
    assert result['motivo'] == 'MODELO_EXATO_NAO_IDENTIFICADO'
