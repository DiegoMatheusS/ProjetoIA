from copy import deepcopy
import pytest
from src.extractors.category import detect_category
from src.extension import router, router_v2, amazon_fallback
from src.extension.router_v2 import PageCapture

@pytest.mark.parametrize('title,expected', [
 ('Memória RAM DDR4 16GB compatível B550 RTX 4060', 'MEMORIA_RAM'),
 ('Placa de vídeo RTX 4060 compatível B550M', 'PLACA_VIDEO'),
 ('Kingston Fury Beast 16GB 3200MHz', 'MEMORIA_RAM'),
 ('Corsair Vengeance LPX 32GB 3600MHz', 'MEMORIA_RAM'),
 ('ASUS TUF Gaming B550M-Plus WiFi II DDR4', 'PLACA_MAE'),
 ('MSI PRO B760M-P DDR4 LGA1700', 'PLACA_MAE'),
 ('Gigabyte B650 AORUS ELITE AX', 'PLACA_MAE'),
 ('MSI Ventus RTX 4060 8GB GDDR6', 'PLACA_VIDEO'),
 ('Intel Arc B580 Limited Edition 12GB', 'PLACA_VIDEO'),
 ('Monitor Gamer para RTX 4060 HDMI', 'MONITOR'),
 ('Processador Ryzen 5 5600 compatível B550M', 'PROCESSADOR'),
 ('PC Gamer Ryzen 5 5600 RTX 4060 16GB RAM SSD 1TB', 'PC_MONTADO'),
 ('Notebook gamer RTX 4060 DDR5 16GB', 'NOTEBOOK'),
])
def test_component_identity_without_confusing_compatibility(title, expected):
 assert detect_category(title) == expected

@pytest.mark.parametrize('module,function', [(router, '_import_sync'), (router_v2, '_import_new_with_ai')])
def test_unknown_category_requests_selection_before_saving(monkeypatch, module, function):
 monkeypatch.setattr(module, '_analyze_sync', lambda request: {'categoriaDetectada': 'DESCONHECIDA', 'payloadParcialBackend': {'nome': 'Item sem identificação'}})
 if module is router_v2:
  monkeypatch.setattr(module, 'hydrate_marketplace_analysis', lambda analysis, **kwargs: analysis)
  result = getattr(module, function)(router_v2.ImportAffiliateOfferV2Request(urlProduto='https://amazon.com.br/dp/B012345678', urlAfiliada='https://amzn.to/teste'), 'NAO_ENCONTRADO')
 else:
  result = getattr(module, function)(router.ImportAffiliateOfferRequest(urlProduto='https://amazon.com.br/dp/B012345678', urlAfiliada='https://amzn.to/teste'))
 assert result['status'] == 'REVISAO_NECESSARIA'
 assert result['solicitarCategoria'] is True

@pytest.mark.parametrize('title,category', [('Kingston Fury Beast 16GB 3200MHz', 'MEMORIA_RAM'), ('ASUS TUF Gaming B550M-Plus', 'PLACA_MAE'), ('MSI Ventus RTX 4060 8GB', 'PLACA_VIDEO')])
def test_browser_title_corrects_server_category(monkeypatch, title, category):
 monkeypatch.setattr(amazon_fallback, 'auto_enrich_link_result', lambda result: result)
 remote = {'categoriaDetectada': 'PROCESSADOR', 'payloadParcialBackend': {'nome': 'Ryzen', 'especificacaoProcessador': {'nucleos': 6}}}
 result = amazon_fallback.hydrate_marketplace_analysis(deepcopy(remote), url='https://www.amazon.com.br/dp/B012345678', capture=PageCapture(nome=title))
 assert result['categoriaDetectada'] == category
 assert 'especificacaoProcessador' not in result['payloadParcialBackend']
