from src.mercadolivre.router import _normalize_result, _technical_attributes


def test_api_details_expose_attributes_and_product_identity():
    raw = {
        "source": "MERCADO_LIVRE_API",
        "api_used": True,
        "title": "Celular Samsung Galaxy A55",
        "brand": "Samsung",
        "model": "Galaxy A55",
        "mpn": "SM-A556E",
        "gtin": "7890001234567",
        "description": "Tela AMOLED e NFC",
        "price": 1699,
        "product_attributes": [
            {"nome": "NFC", "valor": "Sim"},
            {"nome": "Bateria", "valor": "5.000 mAh"},
            {"nome": "NFC", "valor": "Sim"},
        ],
        "api_debug": [{"endpoint": "/items/MLB1234567", "status": 200}],
    }
    item = _normalize_result(raw, "https://produto.mercadolivre.com.br/MLB-1234567", "MLB1234567")
    assert item["marca"] == "Samsung"
    assert item["modelo"] == "Galaxy A55"
    assert item["mpn"] == "SM-A556E"
    assert item["gtin"] == "7890001234567"
    assert item["descricao"] == "Tela AMOLED e NFC"
    assert item["atributos"] == [
        {"nome": "NFC", "valor": "Sim"},
        {"nome": "Bateria", "valor": "5.000 mAh"},
    ]
    assert item["totalAtributos"] == 2
    assert item["apiDebug"][0]["status"] == 200


def test_standard_raw_api_attribute_shape_is_retained():
    raw = {
        "attributes": [
            {"id": "NFC", "name": "NFC", "value_name": "Não"},
            {"id": "BATTERY_CAPACITY", "name": "Capacidade da bateria", "value_name": "4500 mAh"},
        ],
    }
    assert _technical_attributes(raw) == [
        {"nome": "NFC", "valor": "Não"},
        {"nome": "Capacidade da bateria", "valor": "4500 mAh"},
    ]


def test_missing_attributes_are_not_invented():
    item = _normalize_result({"source": "MERCADO_LIVRE_API", "price": 100}, "https://example.com", None)
    assert item["atributos"] == []
    assert item["totalAtributos"] == 0
    assert item["gtin"] is None
