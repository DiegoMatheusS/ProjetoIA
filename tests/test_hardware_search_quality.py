import json
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from src.enrichment.identity import build_identity, candidate_matches_identity, text_matches_identity
from src.enrichment.providers import ManufacturerProvider, ExternalTechnicalProvider
from src.enrichment.quality import validate_specs, evidence_for_specs, source_diagnostic
from src.enrichment.core import TechnicalEnricher
from src.scrapers.generic_scraper import GenericScraper
from src.technical_ai.evidence import filter_grounded_response, grounded_prompt


def identity(model='RTX 4070', mpn=None):
    return build_identity({'payloadParcialBackend': {'marca': 'ASUS', 'modelo': model, 'mpn': mpn}})


@pytest.mark.parametrize('title', ['ASUS RTX 4070 Ti', 'ASUS RTX 4070 SUPER', 'ASUS RTX 4070 OC'])
def test_gpu_variants_not_interchangeable(title):
    assert not candidate_matches_identity(identity(), {'title': title}, title)


def test_mpn_substring_is_not_a_match():
    ident = identity(mpn='ABC-123')
    assert text_matches_identity(ident, 'ASUS ABC-123')
    assert not text_matches_identity(ident, 'ASUS ABC-1234')
    assert not candidate_matches_identity(ident, {'mpn': 'ABC-124'}, 'ASUS ABC-123')


def test_recommended_product_does_not_confirm_page():
    assert not candidate_matches_identity(identity(), {'title': 'ASUS RTX 4060'}, 'ASUS RTX 4060 Recommended ASUS RTX 4070')


def test_gtin_cannot_be_built_by_concatenating_unrelated_numbers():
    ident = {'metodo': 'GTIN', 'gtin': '12345678'}
    assert not text_matches_identity(ident, '1234 cores and 5678 MHz')


def test_json_ld_quantities_keep_units_false_and_zero():
    product = {'additionalProperty': [{'name': 'Height', 'value': 12, 'unitText': 'mm'},
        {'name': 'RGB', 'value': False}, {'name': 'Fans', 'value': 0}]}
    attrs = GenericScraper._visible_attributes(BeautifulSoup('', 'html.parser'), product)
    assert [a['value_name'] for a in attrs] == ['12 mm', 'No', '0']


def test_evidence_is_field_specific():
    source = {'fonte': 'FABRICANTE_OFICIAL', 'url': 'https://asus.com/p',
              'attributes': [{'name': 'TDP', 'value_name': '120 W'}, {'name': 'Socket', 'value_name': 'AM5'}]}
    evidence = evidence_for_specs('PROCESSADOR', source, {'tdpWatts': 120, 'socket': 'AM5'})
    assert evidence['tdpWatts']['trecho'] == 'TDP: 120 W'
    assert evidence['socket']['trecho'] == 'Socket: AM5'


def test_invalid_intervals_and_kit_are_reported():
    specs, issues = validate_specs('PROCESSADOR', {'nucleos': 16, 'threads': 8})
    assert specs['nucleos'] is None and len(issues) == 2
    specs, issues = validate_specs('MEMORIA_RAM', {'capacidadePorModuloGb': 16, 'quantidadeModulos': 2},
        [{'name': 'Total capacity', 'value_name': '16 GB'}])
    assert specs['capacidadePorModuloGb'] is None
    assert issues[0]['motivo'] == 'CAPACIDADE_KIT_INCONSISTENTE'


def test_ai_must_cite_a_collected_passage_and_matching_value():
    info = {'evidenciasColetadas': [{'url': 'https://amd.com/p', 'fonte': 'FABRICANTE_OFICIAL', 'trechos': ['TDP: 120 W']} ]}
    text = json.dumps({'especificacoes': {'tdpWatts': 120}, 'evidencias': {'tdpWatts': {'url': 'https://amd.com/p', 'trecho': 'TDP: 120 W'}}})
    accepted, origins, rejected = filter_grounded_response('PROCESSADOR', text, info)
    assert json.loads(accepted)['especificacoes']['tdpWatts'] == 120
    assert origins['tdpWatts']['trecho'] == 'TDP: 120 W' and not rejected
    accepted, _, rejected = filter_grounded_response('PROCESSADOR', text.replace('120', '65'), info)
    assert not json.loads(accepted)['especificacoes'] and rejected
    accepted, _, rejected = filter_grounded_response('PROCESSADOR', 'TDP: 65 W', info)
    assert not json.loads(accepted)['especificacoes'] and rejected


def test_retry_uses_next_candidate_for_wrong_model(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    class Resolver:
        def first_result(self, *_): return 'https://asus.com/wrong'
        def results(self, *_, **kw): return [{'url': 'https://asus.com/wrong'}, {'url': 'https://asus.com/correct'}]
    p = ManufacturerProvider(resolver=Resolver())
    calls = []
    def fetch(url, ident):
        calls.append(url)
        return {'ok': url.endswith('correct'), 'url': url, 'erro': None if url.endswith('correct') else 'IDENTIDADE_NAO_CONFIRMADA'}
    monkeypatch.setattr(p, 'fetch_candidate', fetch)
    result = p.collect(identity(), 'PLACA_VIDEO')
    assert result['ok'] and len(calls) == 2


def test_cache_is_scoped_to_identity(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    p = ExternalTechnicalProvider()
    calls = []
    monkeypatch.setattr(p, '_fetch_candidate_uncached', lambda url, ident: calls.append(ident) or {'ok': True, 'attributes': [{'name': 'Socket', 'value_name': 'AM5'}]})
    assert not p.fetch_candidate('https://example.com/p', identity())['cacheHit']
    assert p.fetch_candidate('https://example.com/p', identity())['cacheHit']
    p.fetch_candidate('https://example.com/p', identity('RTX 4080'))
    assert len(calls) == 2


@pytest.mark.parametrize('error,status', [('HTTP_403', 'BLOQUEADO'), ('HTTP_503', 'FALHA_TEMPORARIA'), ('IDENTIDADE_NAO_CONFIRMADA', 'MODELO_DIVERGENTE'), ('NAO_ENCONTRADO', 'NAO_ENCONTRADO')])
def test_source_diagnostics(error, status):
    assert source_diagnostic({'ok': False, 'erro': error}) == status


def test_official_source_precedes_specialist_for_missing_field():
    class Provider:
        def __init__(self, name, watts): self.name, self.watts = name, watts
        def collect(self, *_): return {'ok': True, 'fonte': self.name, 'url': 'https://example.com/p', 'attributes': [{'name': 'TDP', 'value_name': f'{self.watts} W'}]}
    result = {'categoriaDetectada': 'PROCESSADOR', 'payloadParcialBackend': {'marca': 'AMD', 'modelo': 'Ryzen 7 7800X3D'}, 'especificacoesEncontradas': {}}
    out = TechnicalEnricher([Provider('CPU_MONKEY', 105), Provider('FABRICANTE_OFICIAL', 120)]).enrich(result)
    assert out['especificacoesEncontradas']['tdpWatts'] == 120
    assert out['enriquecimentoTecnico']['conflitos'][0]['campo'] == 'tdpWatts'


def test_manufacturer_layout_extraction(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    p = ManufacturerProvider()
    html = '<h1>ASUS RTX 4070</h1><div class="TechSpec__row"><div class="TechSpec__title">Memory Size</div><div class="TechSpec__info">12 GB</div></div>'
    out = p._parse_candidate_html('https://asus.com/p', 'https://asus.com/p', html, identity())
    assert out['ok'] and out['attributes'][0]['value_name'] == '12 GB'


def test_ram_kit_count_is_identity():
    ident = build_identity({'payloadParcialBackend': {'marca': 'Corsair', 'modelo': 'Vengeance DDR4 16 GB Kit of 2'}})
    assert not candidate_matches_identity(ident, {'title': 'Corsair Vengeance DDR4 16 GB'}, 'Corsair Vengeance DDR4 16 GB')


def test_citations_are_fetched_only_from_manufacturer(monkeypatch, tmp_path):
    from src.technical_ai.evidence import collect_cited_sources
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    calls = []
    def fetch(self, url, ident):
        calls.append(url)
        return {'ok': True, 'url': url, 'attributes': [{'name': 'Socket', 'value_name': 'AM5'}]}
    monkeypatch.setattr(ManufacturerProvider, 'fetch_candidate', fetch)
    info = {}
    collect_cited_sources('PROCESSADOR', {'marca': 'AMD', 'modelo': 'Ryzen 7 7800X3D'},
        [{'url': 'https://amd.com.evil.test/p'}, {'url': 'http://127.0.0.1'}, {'url': 'https://amd.com/p'}], info)
    assert calls == ['https://amd.com/p']
    assert info['evidenciasColetadas'][0]['trechos'] == ['Socket: AM5']


def test_actual_pdf_datasheet_and_size_limit(monkeypatch, tmp_path):
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 250 Td (ASUS RTX 4070) Tj 0 -20 Td (Memory Size: 12 GB) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    buf = BytesIO(); writer.write(buf)
    response = SimpleNamespace(iter_content=lambda size: [buf.getvalue()], close=lambda: None)
    out = ManufacturerProvider()._parse_pdf('https://asus.com/spec.pdf', response, identity())
    assert out['ok'] and '12 GB' in out['context_text']
    response = SimpleNamespace(iter_content=lambda size: [b'x' * (8 * 1024 * 1024 + 1)], close=lambda: None)
    assert ManufacturerProvider()._parse_pdf('https://asus.com/spec.pdf', response, identity())['erro'] == 'PDF_MUITO_GRANDE'


def test_redirect_cannot_fetch_outside_source(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    calls = []
    class Session:
        headers = {}
        def get(self, url, **kwargs):
            calls.append(url)
            assert kwargs['allow_redirects'] is False
            return SimpleNamespace(status_code=302, headers={'Location': 'http://127.0.0.1/internal'}, close=lambda: None)
    p = ManufacturerProvider(session=Session())
    p.allow_browser_fallback = False
    p.rate_limiter.wait = lambda *_: None
    out = p.fetch_candidate('https://asus.com/p', identity())
    assert not out['ok'] and calls == ['https://asus.com/p']



def test_transient_page_failure_is_retried_after_short_ttl(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    clock = [1000.0]
    monkeypatch.setattr('src.enrichment.providers.time.time', lambda: clock[0])
    p = ExternalTechnicalProvider()
    calls = []
    monkeypatch.setattr(p, '_fetch_candidate_uncached', lambda *args: calls.append(True) or {'ok': False, 'erro': 'ERRO_HTTP: ReadTimeout'})
    p.fetch_candidate('https://example.com/p', identity())
    assert p.fetch_candidate('https://example.com/p', identity())['cacheHit']
    clock[0] += 16
    assert not p.fetch_candidate('https://example.com/p', identity())['cacheHit']
    assert len(calls) == 2


def test_search_cache_reuses_candidates_and_isolates_domains(monkeypatch, tmp_path):
    from src.enrichment.search import WebSearchResolver
    monkeypatch.setenv('HTTP_CACHE_DIR', str(tmp_path))
    resolver = WebSearchResolver()
    calls = []
    monkeypatch.setattr(resolver, '_results_uncached', lambda query, domains, **kw: calls.append(domains) or [{'url': 'https://' + domains[0] + '/p', 'title': 'Model'}])
    assert resolver.results('ABC123', ['asus.com'])
    assert resolver.results('ABC123', ['asus.com'])
    assert len(calls) == 1
    resolver.results('ABC123', ['msi.com'])
    assert len(calls) == 2
