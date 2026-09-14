import pytest
from bs4 import BeautifulSoup
from src.extractors.meta_ai_whatsapp import parse_meta_ai_response
from src.technical_ai.providers import GeminiProvider, TechnicalAIProviderError
from src.scrapers.generic_scraper import GenericScraper
from src.batch.price_updater import _float_or_none


def test_ai_accepts_json_with_native_false_and_array():
    text = '```json\n{"especificacaoProcessador":{"socket":"AM5","nucleos":8,"possuiVideoIntegrado":false,"tiposMemoriaSuportados":["DDR5"]}}\n```'
    specs = parse_meta_ai_response('PROCESSADOR', text)
    assert specs['socket'] == 'AM5'
    assert specs['nucleos'] == 8
    assert specs['possuiVideoIntegrado'] is False
    assert specs['tiposMemoriaSuportados'] == ['DDR5']


def test_ai_does_not_parse_internal_thoughts():
    payload = {'candidates': [{'content': {'parts': [{'thought': True, 'text': 'Socket: AM4'}, {'text': 'Socket: AM5'}]}}]}
    assert GeminiProvider._response_text(payload) == 'Socket: AM5'


def test_truncated_ai_response_is_not_applied(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test')
    class Response:
        status_code = 200
        def json(self):
            return {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'Socket: AM5'}]}}]}
    class Session:
        def post(self, *args, **kwargs):
            return Response()
    with pytest.raises(TechnicalAIProviderError, match='interrompida'):
        GeminiProvider(session=Session()).enrich('CPU')


def test_recommendations_are_not_the_product():
    soup = BeautifulSoup('<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"@type":"Product","name":"recomendado","offers":{"price":5}}]}</script>', 'html.parser')
    assert GenericScraper._product_json_ld(soup) == {}


def test_canonical_product_wins_over_another_product():
    soup = BeautifulSoup('<link rel="canonical" href="https://loja.com/item"><script type="application/ld+json">[{"@type":"Product","url":"https://loja.com/outro","name":"outro"},{"@type":"Product","url":"https://loja.com/item","name":"certo"}]</script>', 'html.parser')
    assert GenericScraper._product_json_ld(soup)['name'] == 'certo'


@pytest.mark.parametrize('value', ['nan', 'inf', '-1', 0])
def test_invalid_prices_are_rejected(value):
    assert _float_or_none(value) is None
