from src.discovery.sources import DiscoverySourceCatalog, DiscoveryCandidate
from src.discovery.core import HardwareDiscoveryService


class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
    def get(self, url, **kwargs):
        return self.response


class NoSurfsky:
    def surfsky_configured(self):
        return False


def _catalog(html, url='https://www.pc-kombo.com/us/components/cpus'):
    c = DiscoverySourceCatalog(session=FakeSession(FakeResponse(html, url)))
    c.rate_limiter.wait = lambda *_: None
    c.browser = NoSurfsky()
    return c


def test_v14_19_pc_kombo_cpu_catalog_keeps_list_specs_without_detail_page():
    html = '''<html><body>
    <a href="/us/product/cpu/0730143312042_AMD%20Ryzen%205%205600X">AMD Ryzen 5 5600X Socket AM4 Clock 3.7 GHz Turbo 4.6 GHz 6 Cores 12 Threads</a>
    <a href="/us/product/cpu/5032037150453_Intel%20Core%20i5-9500">Intel Core i5-9500 Socket 1151 Clock 3.0 GHz Turbo 4.4 GHz 6 Cores 6 Threads</a>
    </body></html>'''
    c = _catalog(html)
    items, err = c._pc_kombo('PROCESSADOR', limit=50)
    assert err is None
    assert len(items) == 2
    assert items[0].nome == 'AMD Ryzen 5 5600X'
    assert items[0].resumo['specs'] == {
        'socket': 'AM4', 'frequenciaBaseMhz': 3700, 'frequenciaTurboMhz': 4600,
        'nucleos': 6, 'threads': 12,
    }


def test_v14_19_catalog_first_service_returns_backend_compatible_payload_fast():
    class FakeCatalog:
        allow_browser_fallback = True
        resolver = None
        def discover(self, **kwargs):
            return [DiscoveryCandidate(
                nome='Intel Core i5-9500',
                url='https://www.pc-kombo.com/us/product/cpu/x_Intel_Core_i5-9500',
                fonte='PC_KOMBO',
                resumo={
                    'catalog_text': 'Intel Core i5-9500 Socket 1151 Clock 3.0 GHz Turbo 4.4 GHz 6 Cores 6 Threads',
                    'specs': {'socket':'1151','frequenciaBaseMhz':3000,'frequenciaTurboMhz':4400,'nucleos':6,'threads':6},
                },
            )], [{'fonte':'PC_KOMBO','encontrados':1,'erro':None}]

    result = HardwareDiscoveryService(catalog=FakeCatalog()).discover(
        'PROCESSADOR', pagina=1, limite=50, detalhar=False, enriquecer=False,
    )
    assert result['quantidadeRetornada'] == 1
    item = result['itens'][0]
    assert item['payload']['nome'] == 'Intel Core i5-9500'
    assert item['payload']['especificacaoProcessador']['socket'] == '1151'
    assert item['payload']['especificacaoProcessador']['nucleos'] == 6
    assert item['idTemporario'].startswith('processador-')
    assert item['statusFicha'] in {'PRONTO','FICHA_INCOMPLETA'}
    assert item['qualidade'] > 0


def test_v14_19_pc_kombo_motherboard_catalog_summary():
    text = 'MSI B550-A Pro ATX Socket AM4 Chipset B550 4 Ramslots'
    assert DiscoverySourceCatalog._pc_kombo_name(text, 'PLACA_MAE') == 'MSI B550-A Pro'
    specs = DiscoverySourceCatalog._pc_kombo_summary(text, 'PLACA_MAE')
    assert specs == {'formato':'ATX','socket':'AM4','chipset':'B550','slotsMemoria':4}


def test_v14_19_pc_kombo_ssd_catalog_summary():
    text = 'Crucial P2 1000 GB 1000 GB NVM Protocol M.2 Format'
    assert DiscoverySourceCatalog._pc_kombo_name(text, 'ARMAZENAMENTO') == 'Crucial P2 1000 GB'
    specs = DiscoverySourceCatalog._pc_kombo_summary(text, 'ARMAZENAMENTO')
    assert specs['tipo'] == 'SSD'
    assert specs['capacidadeGb'] == 1000
    assert specs['interface'] == 'NVMe'
    assert specs['formato'] == 'M.2'


def test_v14_19_pc_kombo_psu_catalog_summary():
    text = 'Seasonic Core GM 80 Plus Gold, semi-modular ATX 650W'
    specs = DiscoverySourceCatalog._pc_kombo_summary(text, 'FONTE')
    assert specs['formato'] == 'ATX'
    assert specs['potenciaWatts'] == 650
    assert specs['certificacao'] == '80 PLUS Gold'
    assert specs['modularidade'] == 'SEMI_MODULAR'
