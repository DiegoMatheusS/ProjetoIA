from src.offers.identical_product_router import (
    IdenticalProductOffersRequest,
    _marketplace_query,
    _query,
    _short_name_query,
)


def _payload(nome: str, **kwargs):
    return IdenticalProductOffersRequest(
        nome=nome,
        marca=kwargs.get("marca"),
        modelo=kwargs.get("modelo"),
        mpn=kwargs.get("mpn"),
        gtin=kwargs.get("gtin"),
    )


def test_short_name_query_mouse_uses_only_first_words():
    nome = "Mouse Gamer Fortrek Black Hawk RGB USB 7200 DPI Switch Huano Cor Preto"
    assert _short_name_query(nome) == "Mouse Gamer Fortrek Black Hawk RGB"


def test_short_name_query_ssd_uses_only_first_words():
    nome = "SSD Kingston NV3 500GB M2 2280 NVMe PCIe 4.0 Gen 4x4"
    assert _short_name_query(nome) == "SSD Kingston NV3 500GB M2 2280"


def test_short_name_query_motherboard_uses_only_first_words():
    nome = "Placa Mae ASRock B450M Steel Legend AMD AM4 mATX DDR4"
    assert _short_name_query(nome) == "Placa Mae ASRock B450M Steel Legend"


def test_search_query_prefers_short_product_name_even_with_identity_fields():
    payload = _payload(
        "Mouse Gamer Fortrek Black Hawk RGB USB 7200 DPI Switch Huano Cor Preto",
        marca="Fortrek",
        modelo="Black Hawk",
        mpn="999999",
        gtin="7890000000000",
    )
    assert _query(payload) == "Mouse Gamer Fortrek Black Hawk RGB"
    assert _marketplace_query(payload) == "Mouse Gamer Fortrek Black Hawk RGB"
