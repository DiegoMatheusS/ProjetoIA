import json

from src.batch.price_updater import BatchPriceUpdater, load_batch_items, normalize_batch_item


def collector_factory(data):
    def collect(url, no_browser=False):
        return data[url]
    return collect


def test_normalize_batch_item_accepts_criabyte_style_fields():
    item = normalize_batch_item({
        "ofertaId": "of1",
        "produtoId": "p1",
        "link": "https://loja/item",
        "preco": "1.234,56",
        "disponivel": True,
    })
    assert item["ofertaId"] == "of1"
    assert item["url"] == "https://loja/item"
    assert item["precoAtual"] == 1234.56
    assert item["disponivelAtual"] is True


def test_batch_marks_price_change_for_update():
    url = "https://loja/item1"
    updater = BatchPriceUpdater(collector=collector_factory({
        url: {"ok": True, "preco": 899.9, "precoAnterior": 999.9, "disponivel": True, "fonte": "TESTE"}
    }))
    result = updater.check_many([{"ofertaId": "o1", "url": url, "precoAtual": 999.9, "disponivelAtual": True}])
    assert result["resumo"]["atualizar"] == 1
    assert result["atualizacoes"][0]["preco"] == 899.9
    assert result["atualizacoes"][0]["alterarPreco"] is True


def test_batch_keeps_equal_price_unchanged():
    url = "https://loja/item2"
    updater = BatchPriceUpdater(collector=collector_factory({
        url: {"ok": True, "preco": 500.0, "disponivel": True, "fonte": "TESTE"}
    }))
    result = updater.check_many([{"url": url, "precoAtual": 500.0, "disponivelAtual": True}])
    assert result["resumo"]["semAlteracao"] == 1
    assert result["itens"][0]["status"] == "SEM_ALTERACAO"


def test_batch_detects_availability_change_without_price_change():
    url = "https://loja/item3"
    updater = BatchPriceUpdater(collector=collector_factory({
        url: {"ok": True, "preco": 500.0, "disponivel": False, "fonte": "TESTE"}
    }))
    result = updater.check_many([{"url": url, "precoAtual": 500.0, "disponivelAtual": True}])
    update = result["atualizacoes"][0]
    assert update["alterarPreco"] is False
    assert update["alterarDisponibilidade"] is True
    assert update["disponivel"] is False


def test_batch_does_not_invent_price_when_source_has_none():
    url = "https://loja/item4"
    updater = BatchPriceUpdater(collector=collector_factory({
        url: {"ok": True, "preco": None, "disponivel": False, "fonte": "TESTE"}
    }))
    result = updater.check_many([{"url": url, "precoAtual": 700.0, "disponivelAtual": True}])
    update = result["atualizacoes"][0]
    assert update["preco"] == 700.0
    assert update["alterarPreco"] is False
    assert update["disponivel"] is False


def test_batch_collect_error_is_reported_and_does_not_create_update():
    url = "https://loja/erro"
    updater = BatchPriceUpdater(collector=collector_factory({
        url: {"ok": False, "erro": "HTTP_404", "fonte": "TESTE"}
    }))
    result = updater.check_many([{"url": url, "precoAtual": 100.0}])
    assert result["resumo"]["erros"] == 1
    assert result["atualizacoes"] == []


def test_batch_policy_is_sequential_and_offer_only():
    result = BatchPriceUpdater(collector=lambda url: {"ok": False, "erro": "X"}).check_many([])
    assert result["politica"]["processamentoSequencial"] is True
    assert result["politica"]["umaUrlPorVez"] is True
    assert result["politica"]["alteraSomenteOferta"] is True
    assert result["politica"]["alteraFichaTecnica"] is False


def test_load_batch_json_with_ofertas_key(tmp_path):
    path = tmp_path / "ofertas.json"
    path.write_text(json.dumps({"ofertas": [{"ofertaId": "o1", "url": "https://a", "preco": 10}]}), encoding="utf-8")
    items = load_batch_items(path)
    assert len(items) == 1
    assert items[0]["ofertaId"] == "o1"
    assert items[0]["precoAtual"] == 10.0


def test_load_batch_txt_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "links.txt"
    path.write_text("# links\nhttps://a\n\nhttps://b\n", encoding="utf-8")
    items = load_batch_items(path)
    assert [x["url"] for x in items] == ["https://a", "https://b"]
