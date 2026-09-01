from src.criabyte.planner import CriaBytePlanner
from src.batch.price_updater import BatchPriceUpdater, normalize_batch_item


def result_processador(**payload_overrides):
    payload = {
        "nome": "AMD Ryzen 7 7800X3D",
        "marca": "AMD",
        "modelo": "7800X3D",
        "descricao": "Processador AMD Ryzen 7 7800X3D",
        "mpn": "100-100000910WOF",
        "gtin": None,
        "imagemUrl": "https://img.example/7800x3d.jpg",
        "categoria": "PROCESSADOR",
        "especificacaoProcessador": {
            "socket": "AM5",
            "tiposMemoriaSuportados": ["DDR5"],
            "nucleos": 8,
            "threads": 16,
            "tdpWatts": 120,
        },
    }
    payload.update(payload_overrides)
    return {
        "categoriaDetectada": "PROCESSADOR",
        "tipoCadastro": "HARDWARE",
        "payloadParcialBackend": payload,
        "ofertaColetada": {
            "preco": 1999.90,
            "precoAnterior": 2199.90,
            "disponivel": True,
            "urlOriginal": "https://www.magazineluiza.com.br/ryzen-7800x3d/p/abc123/",
            "urlProduto": "https://www.magazineluiza.com.br/ryzen-7800x3d/p/abc123/",
        },
        "origemColeta": {"plataforma": "MAGALU", "host": "www.magazineluiza.com.br"},
    }


def base_state():
    return {
        "hardwares": [],
        "produtos": [],
        "ofertas": [],
        "parceiros": [{"id": 7, "nome": "Magazine Luiza", "slug": "magalu", "dominio": "magazineluiza.com.br"}],
        "categorias": [{"id": 10, "slug": "processadores", "nome": "Processadores"}],
    }


def test_same_model_different_brand_does_not_match_product_or_hardware():
    state = base_state()
    state["hardwares"] = [{"id": 1, "nome": "Fake 7800X3D", "marca": "OutraMarca", "modelo": "7800X3D", "mpn": None, "gtin": None}]
    state["produtos"] = [{"id": 2, "nome": "Fake 7800X3D", "marca": "OutraMarca", "modelo": "7800X3D", "mpn": None, "gtin": None}]
    plan = CriaBytePlanner(state).plan(result_processador(mpn=None))
    assert plan["hardware"]["match"]["confirmado"] is False
    assert plan["produto"]["match"]["confirmado"] is False


def test_same_brand_and_model_is_confirmed_match():
    state = base_state()
    state["hardwares"] = [{"id": 1, "nome": "Ryzen", "marca": "AMD", "modelo": "7800X3D", "mpn": None, "gtin": None, "produtoId": None}]
    plan = CriaBytePlanner(state).plan(result_processador(mpn=None), hardware_detail=state["hardwares"][0])
    assert plan["hardware"]["match"]["confirmado"] is True
    assert plan["hardware"]["match"]["metodo"] == "MARCA_MODELO"


def test_same_gtin_with_conflicting_brand_is_not_auto_matched():
    state = base_state()
    state["produtos"] = [{"id": 2, "nome": "Outro", "marca": "Intel", "modelo": "X", "gtin": "7891234567895", "mpn": None}]
    plan = CriaBytePlanner(state).plan(result_processador(gtin="7891234567895"))
    assert plan["produto"]["match"]["confirmado"] is False
    assert "CONFLITO_DE_IDENTIDADE" in plan["bloqueios"]


def test_existing_hardware_only_fills_empty_fields_and_keeps_full_spec_payload():
    state = base_state()
    hardware = {
        "id": 4,
        "produtoId": None,
        "nome": "AMD Ryzen 7 7800X3D",
        "marca": "AMD",
        "modelo": "7800X3D",
        "descricao": None,
        "mpn": "100-100000910WOF",
        "gtin": None,
        "imagemUrl": None,
        "especificacaoProcessador": {
            "id": 99,
            "hardwareId": 4,
            "socket": "AM5",
            "tiposMemoriaSuportados": ["DDR5"],
            "nucleos": 8,
            "threads": None,
            "tdpWatts": None,
        },
    }
    state["hardwares"] = [hardware]
    plan = CriaBytePlanner(state).plan(result_processador(), hardware_detail=hardware)
    patch = plan["hardware"]["patch"]
    assert patch["descricao"].startswith("Processador AMD")
    assert patch["imagemUrl"].startswith("https://")
    assert patch["especificacaoProcessador"]["socket"] == "AM5"
    assert patch["especificacaoProcessador"]["tiposMemoriaSuportados"] == ["DDR5"]
    assert patch["especificacaoProcessador"]["threads"] == 16
    assert patch["especificacaoProcessador"]["tdpWatts"] == 120
    assert "id" not in patch["especificacaoProcessador"]
    assert "hardwareId" not in patch["especificacaoProcessador"]


def test_existing_filled_spec_conflict_is_not_overwritten():
    state = base_state()
    hardware = {
        "id": 4, "produtoId": None,
        "nome": "AMD Ryzen 7 7800X3D", "marca": "AMD", "modelo": "7800X3D", "mpn": "100-100000910WOF", "gtin": None,
        "especificacaoProcessador": {"socket": "AM5", "tiposMemoriaSuportados": ["DDR5"], "tdpWatts": 105},
    }
    state["hardwares"] = [hardware]
    plan = CriaBytePlanner(state).plan(result_processador(), hardware_detail=hardware)
    assert plan["hardware"]["patch"]["especificacaoProcessador"]["tdpWatts"] == 105 if "especificacaoProcessador" in plan["hardware"]["patch"] else True
    assert any(c["campo"] == "tdpWatts" and c["entidade"] == "HARDWARE" for c in plan["conflitos"])


def test_new_hardware_plan_follows_backend_order_and_keeps_price_outside_hardware_product():
    plan = CriaBytePlanner(base_state()).plan(result_processador())
    action_types = [a["tipo"] for a in plan["acoesSugeridas"]]
    assert action_types[:3] == ["CRIAR_HARDWARE", "CRIAR_PRODUTO_DE_HARDWARE", "CRIAR_OFERTA"]
    hw_payload = plan["acoesSugeridas"][0]["payload"]
    product_payload = plan["acoesSugeridas"][1]["payload"]
    offer_payload = plan["acoesSugeridas"][2]["payload"]
    assert "preco" not in hw_payload
    assert "preco" not in product_payload
    assert offer_payload["preco"] == 1999.90
    assert offer_payload["parceiroId"] == 7


def test_existing_linked_product_is_used_and_empty_product_fields_are_filled():
    state = base_state()
    hardware = {
        "id": 4, "produtoId": 20,
        "nome": "AMD Ryzen 7 7800X3D", "marca": "AMD", "modelo": "7800X3D", "mpn": "100-100000910WOF", "gtin": None,
        "especificacaoProcessador": {"socket": "AM5", "tiposMemoriaSuportados": ["DDR5"]},
    }
    product = {
        "id": 20, "nome": "AMD Ryzen 7 7800X3D", "marca": "AMD", "modelo": "7800X3D", "mpn": "100-100000910WOF",
        "gtin": None, "descricao": None, "imagemUrl": None,
    }
    state["hardwares"] = [hardware]
    state["produtos"] = [product]
    plan = CriaBytePlanner(state).plan(result_processador(), hardware_detail=hardware, product_detail=product)
    assert plan["produto"]["match"]["metodo"] == "VINCULO_HARDWARE_PRODUTO"
    assert plan["produto"]["patch"]["descricao"].startswith("Processador AMD")
    assert plan["produto"]["patch"]["imagemUrl"].startswith("https://")


def test_existing_offer_generates_backend_patch_only_for_offer_price():
    state = base_state()
    hardware = {
        "id": 4, "produtoId": 20,
        "nome": "AMD Ryzen 7 7800X3D", "marca": "AMD", "modelo": "7800X3D", "mpn": "100-100000910WOF", "gtin": None,
        "especificacaoProcessador": {"socket": "AM5", "tiposMemoriaSuportados": ["DDR5"], "nucleos": 8, "threads": 16, "tdpWatts": 120},
    }
    product = {"id": 20, "nome": "AMD Ryzen 7 7800X3D", "marca": "AMD", "modelo": "7800X3D", "mpn": "100-100000910WOF", "gtin": None, "descricao": "x", "imagemUrl": "https://img"}
    state["hardwares"] = [hardware]
    state["produtos"] = [product]
    state["ofertas"] = [{
        "id": 30, "produtoId": 20, "parceiroId": 7, "preco": "2099.90", "status": "ATIVA",
        "urlOriginal": "https://www.magazineluiza.com.br/ryzen-7800x3d/p/abc123/?utm_source=x",
    }]
    plan = CriaBytePlanner(state).plan(result_processador(), hardware_detail=hardware, product_detail=product)
    offer_action = next(a for a in plan["acoesSugeridas"] if a["tipo"] == "ATUALIZAR_OFERTA")
    assert offer_action["rota"] == "/admin/ofertas/30"
    assert offer_action["payload"] == {"preco": 1999.90}
    assert all("preco" not in a["payload"] for a in plan["acoesSugeridas"] if a["tipo"] != "ATUALIZAR_OFERTA")


def test_batch_accepts_url_original_without_affiliate_link_and_builds_backend_status_patch():
    item = normalize_batch_item({
        "ofertaId": 30,
        "produtoId": 20,
        "urlOriginal": "https://loja/item",
        "urlAfiliada": None,
        "preco": 1000,
        "status": "ATIVA",
    })
    assert item["url"] == "https://loja/item"
    updater = BatchPriceUpdater(collector=lambda url, no_browser=False: {
        "ok": True, "preco": None, "disponivel": False, "fonte": "TESTE"
    })
    result = updater.check_many([item])
    update = result["atualizacoes"][0]
    assert update["rotaBackend"] == "/admin/ofertas/30"
    assert update["payloadBackend"] == {"status": "INDISPONIVEL"}
    assert result["politica"]["urlOriginalTemPrioridade"] is True


def test_batch_reactivates_offer_and_changes_price_using_atualizar_oferta_dto_shape():
    updater = BatchPriceUpdater(collector=lambda url, no_browser=False: {
        "ok": True, "preco": 899.9, "disponivel": True, "fonte": "TESTE"
    })
    result = updater.check_many([{
        "ofertaId": 31, "urlOriginal": "https://loja/item", "preco": 999.9, "status": "INDISPONIVEL"
    }])
    payload = result["atualizacoes"][0]["payloadBackend"]
    assert payload == {"preco": 899.9, "status": "ATIVA"}


def result_monitor():
    return {
        "categoriaDetectada": "MONITOR",
        "tipoCadastro": "PRODUTO",
        "payloadParcialBackend": {
            "nome": "Monitor ABC 27",
            "marca": "MarcaX",
            "modelo": "ABC27",
            "descricao": "Monitor QHD",
            "mpn": "ABC27-BR",
            "gtin": None,
            "imagemUrl": "https://img.example/monitor.jpg",
            "especificacaoMonitor": {"tamanhoPolegadas": 27, "resolucao": "2560x1440", "taxaAtualizacaoHz": 180},
        },
        "ofertaColetada": {
            "preco": 1499.9, "precoAnterior": None, "disponivel": True,
            "urlOriginal": "https://www.magazineluiza.com.br/monitor/p/m1/",
        },
        "origemColeta": {"plataforma": "MAGALU"},
    }


def test_new_generic_product_uses_real_category_id_then_creates_offer():
    state = base_state()
    state["categorias"].append({"id": 44, "slug": "monitores", "nome": "Monitores"})
    plan = CriaBytePlanner(state).plan(result_monitor())
    create_product = next(a for a in plan["acoesSugeridas"] if a["tipo"] == "CRIAR_PRODUTO")
    create_offer = next(a for a in plan["acoesSugeridas"] if a["tipo"] == "CRIAR_OFERTA")
    assert create_product["rota"] == "/admin/produtos"
    assert create_product["payload"]["categoriaId"] == 44
    assert create_product["payload"]["especificacaoMonitor"]["resolucao"] == "2560x1440"
    assert create_offer["payload"]["produtoId"] == "{produtoIdCriado}"


def test_new_unavailable_offer_is_not_created_as_active_by_mistake():
    data = result_monitor()
    data["ofertaColetada"]["disponivel"] = False
    state = base_state()
    state["categorias"].append({"id": 44, "slug": "monitores", "nome": "Monitores"})
    plan = CriaBytePlanner(state).plan(data)
    assert not any(a["tipo"] == "CRIAR_OFERTA" for a in plan["acoesSugeridas"])
    assert "BACKEND_NAO_CRIA_NOVA_OFERTA_JA_INDISPONIVEL" in plan["bloqueios"]


def test_fone_does_not_send_headset_spec_to_backend_fones_category():
    from src.extractors.backend_schemas import SCHEMAS
    assert SCHEMAS["FONE"][1] is None
    assert SCHEMAS["HEADSET"][1] == "especificacaoHeadset"
