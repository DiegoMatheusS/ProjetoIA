from src.extractors.ml_specs import extract_specs
from src.scrapers.magazine_scraper import MagazineScraper
from src.scrapers.mercadolivre_scraper import MercadoLivreScraper
from src.offers.identical_product_router import IdenticalProductOffersRequest, _identity_match_raw, _identity_match_marketplace_name


def test_phone_negative_nfc_and_thousands():
    specs = extract_specs('CELULAR', [
        {'id': 'BATTERY_CAPACITY', 'name': 'Capacidade da bateria', 'value_name': '5.000 mAh'},
        {'id': 'WITH_NFC', 'name': 'NFC', 'value_name': 'Não'},
    ], context_text='Smartphone com NFC: Não')
    assert specs['bateriaMah'] == 5000
    assert specs['nfc'] is False


def test_phone_does_not_invent_nfc_from_question():
    assert 'nfc' not in extract_specs('CELULAR', [], context_text='Este celular tem NFC?')


def test_ml_keeps_all_values_and_structured_units():
    merged = MercadoLivreScraper._merge_attributes([
        {'id': 'CONNECTIVITY', 'name': 'Conexões', 'values': [{'name': 'Wi-Fi'}, {'name': 'Bluetooth'}]},
        {'id': 'BATTERY', 'name': 'Bateria', 'value_struct': {'number': 5000, 'unit': 'mAh'}},
    ])
    assert merged[0]['value_name'] == 'Wi-Fi, Bluetooth'
    assert merged[1]['value_name'] == '5000 mAh'


def test_magalu_nested_attributes_and_false():
    values = MagazineScraper._structured_pairs([{'specifications': [
        {'name': 'NFC', 'value': False}, {'name': 'Conectividade', 'values': ['Wi-Fi', 'Bluetooth']},
        {'Bateria': '5000 mAh'},
    ]}])
    attrs = {v['name']: v['value_name'] for v in values}
    assert attrs == {'NFC': 'Não', 'Conectividade': 'Wi-Fi, Bluetooth', 'Bateria': '5000 mAh'}


def test_pc_separates_collapsed_labels():
    specs = extract_specs('PC_MONTADO', [], context_text='Processador: Ryzen 5 5600 Placa mãe: B550 Fonte: 500 W')
    assert [c['nome'] for c in specs['componentes']] == ['Ryzen 5 5600', 'B550', '500 W']


def test_offer_rejects_conflicting_ids_and_gpu_variant():
    product = IdenticalProductOffersRequest(nome='ASUS RTX 4070', marca='ASUS', modelo='RTX 4070', mpn='DUAL-RTX4070-12G', gtin='4711387123456')
    wrong = {'title': 'ASUS RTX 4070 Ti SUPER', 'model': 'RTX 4070 Ti SUPER', 'brand': 'ASUS', 'mpn': 'DUAL-RTX4070TIS-16G', 'gtin': '4711387999999'}
    assert not _identity_match_raw(product, wrong)[0]
    assert not _identity_match_marketplace_name(product, wrong['title'])[0]
    assert not _identity_match_marketplace_name(product, 'ASUS RTX 40700')[0]
    assert _identity_match_marketplace_name(product, 'ASUS RTX 4070')[0]


def test_store_failure_does_not_discard_other_offers(monkeypatch):
    from src.offers import identical_product_router as module
    def search(_payload, store, _domains, _limit, *args):
        if store == 'MERCADO_LIVRE':
            raise RuntimeError('store unavailable')
        return [{'marketplace': 'MAGALU', 'urlOriginal': 'https://www.magazineluiza.com.br/ssd/p/123/', 'preco': 100}], {'encontrados': 1}
    monkeypatch.setattr(module, '_validate_api_key', lambda key: None)
    monkeypatch.setattr(module, '_search_web_store', search)
    monkeypatch.setattr(module, '_search_shopee', lambda *args: ([], {'encontrados': 0}))
    result = module.find_identical_product_offers(IdenticalProductOffersRequest(nome='Kingston NV3', modelo='NV3'))
    assert result['quantidade'] == 1
    assert result['fontes']['mercadoLivre']['statusBusca'] == 'ERRO'
    assert result['fontes']['magalu']['encontrados'] == 1


def test_pc_retains_generic_parts_and_accessories_in_description():
    from src.main import build_result
    description = 'Processador: Ryzen 5 5600\nRAM: 16 GB sem marca informada\nAcompanha teclado e mouse.'
    result = build_result({'ok': True, 'title': 'PC Gamer', 'description': description, 'url_original': 'https://www.magazineluiza.com.br/pc/p/123/'}, 'PC_MONTADO')
    assert result['payloadParcialBackend']['descricao'] == description
