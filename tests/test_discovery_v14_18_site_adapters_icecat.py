import os

from src.discovery.sources import DiscoverySourceCatalog
from src.enrichment.providers import IcecatProvider


class FakeResponse:
    def __init__(self, text='', url='https://example.com', status_code=200, json_data=None):
        self.text = text
        self.url = url
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        if self._json_data is None:
            raise ValueError('no json')
        return self._json_data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError('unexpected request')
        return self.responses.pop(0)


class FakeBrowser:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def surfsky_configured(self):
        return True

    def fetch_surfsky(self, url, *args, **kwargs):
        self.calls.append(url)
        return {
            'html': self.html,
            'final_url': url,
            'error': None,
            'blocked': False,
        }


def test_v14_18_pc_kombo_http_sparse_uses_rendered_catalog_like_marketplace_fallback():
    sparse = '''
    <html><body>
      <a href="/us/product/cpu/1_Intel%20Core%20i5-9500">Intel Core i5-9500 Socket 1151 Clock 3.0 GHz Turbo 4.4 GHz 6 Cores 6 Threads</a>
    </body></html>
    '''
    rendered = '''
    <html><body>
      <a href="/us/product/cpu/1_Intel%20Core%20i5-9500">Intel Core i5-9500 Socket 1151 Clock 3.0 GHz Turbo 4.4 GHz 6 Cores 6 Threads</a>
      <a href="/us/product/cpu/2_Intel%20Core%20i5-9600K">Intel Core i5-9600K Socket 1151 Clock 3.7 GHz Turbo 4.6 GHz 6 Cores 6 Threads</a>
      <a href="/us/product/cpu/3_Intel%20Core%20i5-10400F">Intel Core i5-10400F Socket 1200 Clock 2.9 GHz Turbo 4.3 GHz 6 Cores 12 Threads</a>
      <a href="/us/product/cpu/4_Intel%20Core%20i5-11400F">Intel Core i5-11400F Socket 1200 Clock 2.6 GHz Turbo 4.4 GHz 6 Cores 12 Threads</a>
      <a href="/us/product/cpu/5_Intel%20Core%20i5-12400F">Intel Core i5-12400F Socket 1700 Clock 2.5 GHz Turbo 4.4 GHz 6 Cores 12 Threads</a>
    </body></html>
    '''
    session = FakeSession([FakeResponse(sparse, 'https://www.pc-kombo.com/us/components/cpus')])
    catalog = DiscoverySourceCatalog(session=session)
    catalog.rate_limiter.wait = lambda *_: None
    catalog.browser = FakeBrowser(rendered)

    items, error = catalog._pc_kombo('PROCESSADOR', marca='Intel', limit=50)
    assert error is None
    assert len(items) == 5
    assert items[0].nome == 'Intel Core i5-9500'
    assert catalog.browser.calls == ['https://www.pc-kombo.com/us/components/cpus']


def test_v14_18_icecat_json_api_maps_identifiers_image_and_features(monkeypatch):
    data = {
        'data': {
            'GeneralInfo': {
                'Title': 'Intel Core i5-9500 processor 3 GHz 9 MB Smart Cache',
                'Brand': 'Intel',
                'ProductName': 'Core i5-9500',
                'BrandPartCode': 'BX80684I59500',
                'GTIN': ['5032037150453'],
            },
            'Image': {
                'HighPic': 'https://images.icecat.biz/test.jpg',
            },
            'FeaturesGroups': [
                {
                    'Features': [
                        {'ID': 1, 'PresentationValue': 'LGA 1151', 'Feature': {'ID': 'socket', 'Name': {'Value': 'Processor socket'}}},
                        {'ID': 2, 'PresentationValue': '6', 'Feature': {'ID': 'cores', 'Name': {'Value': 'Processor cores'}}},
                        {'ID': 3, 'PresentationValue': '6', 'Feature': {'ID': 'threads', 'Name': {'Value': 'Processor threads'}}},
                        {'ID': 4, 'PresentationValue': '3 GHz', 'Feature': {'ID': 'base', 'Name': {'Value': 'Processor base frequency'}}},
                        {'ID': 5, 'PresentationValue': '4.4 GHz', 'Feature': {'ID': 'turbo', 'Name': {'Value': 'Processor boost frequency'}}},
                        {'ID': 6, 'PresentationValue': '65 W', 'Feature': {'ID': 'tdp', 'Name': {'Value': 'Thermal Design Power (TDP)'}}},
                    ]
                }
            ],
        },
        'msg': 'OK',
    }
    session = FakeSession([FakeResponse(url='https://live.icecat.biz/api/', json_data=data)])
    provider = IcecatProvider(session=session)
    provider.username = 'open-user'
    provider.api_token = 'token-test'
    provider.content_token = ''
    provider.rate_limiter.wait = lambda *_: None

    result = provider.collect({
        'marca': 'Intel',
        'modelo': 'Core i5-9500',
        'mpn': 'BX80684I59500',
        'gtin': '5032037150453',
    }, 'PROCESSADOR')

    assert result['ok'] is True
    assert result['fonte'] == 'ICECAT'
    assert result['modoColeta'] == 'ICECAT_JSON_API'
    assert result['brand'] == 'Intel'
    assert result['mpn'] == 'BX80684I59500'
    assert result['gtin'] == '5032037150453'
    assert result['image_url'].endswith('test.jpg')
    attrs = {x['name']: x['value_name'] for x in result['attributes']}
    assert attrs['Processor socket'] == 'LGA 1151'
    assert attrs['Processor cores'] == '6'
    _, kwargs = session.calls[0]
    assert kwargs['params']['GTIN'] == '5032037150453'
    assert kwargs['headers']['api-token'] == 'token-test'


def test_v14_18_icecat_is_optional_and_not_used_without_username(monkeypatch):
    monkeypatch.delenv('ICECAT_USERNAME', raising=False)
    provider = IcecatProvider(session=FakeSession([]))
    assert provider.supports('PROCESSADOR', {'marca': 'Intel', 'mpn': 'ABC'}) is False


def test_v14_18_icecat_requires_strong_lookup_identifier(monkeypatch):
    provider = IcecatProvider(session=FakeSession([]))
    provider.username = 'open-user'
    assert provider.supports('PROCESSADOR', {'marca': 'Intel', 'modelo': 'Core i5-9500'}) is False
    assert provider.supports('PROCESSADOR', {'marca': 'Intel', 'mpn': 'BX80684I59500'}) is True
