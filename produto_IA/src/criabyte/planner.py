import copy
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit

from ..enrichment.identity import build_identity
from ..extractors.backend_schemas import CATEGORY_SLUGS, REQUIRED, SCHEMAS


SYSTEM_KEYS = {
    "id", "hardwareId", "produtoId", "criadoEm", "atualizadoEm",
    "createdAt", "updatedAt", "slug", "_count",
}
BASE_FIELDS = ("nome", "marca", "modelo", "descricao", "mpn", "gtin", "imagemUrl", "imagemHoverUrl")
IDENTITY_FIELDS = {"marca", "modelo", "mpn", "gtin"}


def _missing(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _norm(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", "", text) or None


def _digits(value):
    return re.sub(r"\D", "", str(value or "")) or None


def _same(a, b):
    if isinstance(a, (int, float, bool)) or isinstance(b, (int, float, bool)):
        return a == b
    return _norm(a) == _norm(b)


def _strip_system(value):
    if isinstance(value, list):
        return [_strip_system(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _strip_system(child)
        for key, child in value.items()
        if key not in SYSTEM_KEYS and not key.startswith("_")
    }


def _canonical_url(url):
    if not url:
        return None
    try:
        parsed = urlsplit(str(url).strip())
    except ValueError:
        return str(url).strip()
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not host:
        return str(url).strip()
    port = f":{parsed.port}" if parsed.port else ""
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold() or "https", host + port, path, "", ""))


def _host(url):
    try:
        return (urlsplit(url or "").hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _brand_compatible(incoming, existing):
    a, b = _norm(incoming), _norm(existing)
    if not a or not b:
        return True
    return a == b


def _match_one(payload, records):
    brand = payload.get("marca")
    model = payload.get("modelo")
    mpn = payload.get("mpn")
    gtin = _digits(payload.get("gtin"))
    name = payload.get("nome")
    scored = []
    conflicts = []

    for record in records or []:
        rec_brand = record.get("marca")
        rec_model = record.get("modelo")
        rec_mpn = record.get("mpn")
        rec_gtin = _digits(record.get("gtin"))
        score = 0
        method = None

        if gtin and rec_gtin and gtin == rec_gtin:
            if not _brand_compatible(brand, rec_brand):
                conflicts.append({
                    "id": record.get("id"), "motivo": "GTIN_IGUAL_MARCA_DIFERENTE",
                    "marcaEncontrada": rec_brand,
                })
                continue
            score, method = 100, "GTIN"
        elif mpn and rec_mpn and _norm(mpn) == _norm(rec_mpn):
            if not _brand_compatible(brand, rec_brand):
                conflicts.append({
                    "id": record.get("id"), "motivo": "MPN_IGUAL_MARCA_DIFERENTE",
                    "marcaEncontrada": rec_brand,
                })
                continue
            score, method = 95, "MARCA_MPN"
        elif brand and model and rec_brand and rec_model and _norm(brand) == _norm(rec_brand) and _norm(model) == _norm(rec_model):
            score, method = 90, "MARCA_MODELO"
        elif brand and name and rec_brand and record.get("nome") and _norm(brand) == _norm(rec_brand):
            ratio = SequenceMatcher(None, _norm(name) or "", _norm(record.get("nome")) or "").ratio()
            if ratio >= 0.94:
                score, method = 65, "NOME_SIMILAR_MESMA_MARCA"

        if score:
            scored.append((score, method, record))

    scored.sort(key=lambda item: (-item[0], int(item[2].get("id") or 0)))
    strong = [item for item in scored if item[0] >= 90]
    if len(strong) == 1:
        score, method, record = strong[0]
        return {
            "confirmado": True,
            "ambiguo": False,
            "metodo": method,
            "confianca": "MUITO_ALTA" if score >= 95 else "ALTA",
            "score": score,
            "registro": record,
            "candidatos": [],
            "conflitosIdentidade": conflicts,
        }
    if len(strong) > 1:
        return {
            "confirmado": False,
            "ambiguo": True,
            "metodo": None,
            "confianca": "AMBIGUA",
            "score": strong[0][0],
            "registro": None,
            "candidatos": [x[2] for x in strong[:5]],
            "conflitosIdentidade": conflicts,
        }
    return {
        "confirmado": False,
        "ambiguo": False,
        "metodo": None,
        "confianca": "INSUFICIENTE",
        "score": scored[0][0] if scored else 0,
        "registro": None,
        "candidatos": [x[2] for x in scored[:5]],
        "conflitosIdentidade": conflicts,
    }


def _merge_missing(existing, incoming, path=""):
    existing = _strip_system(copy.deepcopy(existing)) if isinstance(existing, dict) else {}
    incoming = _strip_system(copy.deepcopy(incoming)) if isinstance(incoming, dict) else {}
    merged = copy.deepcopy(existing)
    filled = []
    conflicts = []

    for key, new_value in incoming.items():
        if key in SYSTEM_KEYS or _missing(new_value):
            continue
        field_path = f"{path}.{key}" if path else key
        old_value = merged.get(key)
        if _missing(old_value):
            merged[key] = copy.deepcopy(new_value)
            filled.append(field_path)
            continue
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            child, child_filled, child_conflicts = _merge_missing(old_value, new_value, field_path)
            merged[key] = child
            filled.extend(child_filled)
            conflicts.extend(child_conflicts)
            continue
        # Listas não são mescladas item a item: isso poderia recriar slots/suportes errados.
        if not _same(old_value, new_value):
            conflicts.append({
                "campo": field_path,
                "valorBanco": old_value,
                "valorEncontrado": new_value,
            })
    return merged, filled, conflicts


def _base_patch(existing, incoming):
    patch = {}
    conflicts = []
    filled = []
    for field in BASE_FIELDS:
        found = incoming.get(field)
        if _missing(found):
            continue
        current = existing.get(field)
        if _missing(current):
            patch[field] = found
            filled.append(field)
        elif not _same(current, found):
            conflicts.append({
                "campo": field,
                "valorBanco": current,
                "valorEncontrado": found,
                "identidade": field in IDENTITY_FIELDS,
            })
    return patch, filled, conflicts


def _category_by_slug(categories, slug):
    for category in categories or []:
        if _norm(category.get("slug")) == _norm(slug):
            return category
    return None


def _find_partner(partners, url, plataforma=None):
    host = _host(url)
    for partner in partners or []:
        domain = str(partner.get("dominio") or "").casefold().removeprefix("www.")
        if domain and (host == domain or host.endswith("." + domain) or domain.endswith("." + host)):
            return partner

    aliases = {
        "MERCADO_LIVRE": {"mercadolivre", "mercadolivrebrasil", "mercadolibre"},
        "MAGALU": {"magalu", "magazineluiza", "magazinevoce"},
        "SHOPEE": {"shopee"},
        "KABUM": {"kabum"},
        "PICHAU": {"pichau"},
        "TERABYTE": {"terabyte", "terabyteshop"},
    }
    wanted = aliases.get(plataforma or "", set())
    if wanted:
        for partner in partners or []:
            tokens = {_norm(partner.get("nome")), _norm(partner.get("slug")), _norm(partner.get("dominio"))}
            if any(token and any(alias in token for alias in wanted) for token in tokens):
                return partner
    return None


def _match_offer(offers, produto_id, partner_id, url):
    target = _canonical_url(url)
    if not target or not produto_id:
        return None, []
    candidates = []
    for offer in offers or []:
        if int(offer.get("produtoId") or 0) != int(produto_id):
            continue
        if partner_id is not None and int(offer.get("parceiroId") or offer.get("parceiro", {}).get("id") or 0) != int(partner_id):
            continue
        if _canonical_url(offer.get("urlOriginal")) == target:
            candidates.append(offer)
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


def _offer_patch(existing, collected):
    patch = {}
    price = collected.get("preco")
    available = collected.get("disponivel")
    current_price = existing.get("preco")
    try:
        current_price = float(current_price) if current_price is not None else None
    except (TypeError, ValueError):
        current_price = None
    if price is not None and (current_price is None or abs(float(price) - current_price) > 0.009):
        patch["preco"] = round(float(price), 2)
    if available is False and existing.get("status") != "INDISPONIVEL":
        patch["status"] = "INDISPONIVEL"
    elif available is True and existing.get("status") == "INDISPONIVEL":
        patch["status"] = "ATIVA"
    return patch


def _public_match(match):
    record = match.get("registro")
    return {
        "confirmado": match.get("confirmado"),
        "ambiguo": match.get("ambiguo"),
        "metodo": match.get("metodo"),
        "confianca": match.get("confianca"),
        "score": match.get("score"),
        "id": record.get("id") if record else None,
        "nome": record.get("nome") if record else None,
        "candidatos": [
            {"id": x.get("id"), "nome": x.get("nome"), "marca": x.get("marca"), "modelo": x.get("modelo")}
            for x in match.get("candidatos") or []
        ],
        "conflitosIdentidade": match.get("conflitosIdentidade") or [],
    }


class CriaBytePlanner:
    def __init__(self, state):
        self.state = state or {}

    def plan(self, result, hardware_detail=None, product_detail=None):
        payload = copy.deepcopy(result.get("payloadParcialBackend") or {})
        category = result.get("categoriaDetectada")
        schema = SCHEMAS.get(category)
        tipo, spec_field, _ = schema if schema else (None, None, [])
        collected_offer = result.get("ofertaColetada") or {}
        source = result.get("origemColeta") or {}
        identity = build_identity(result)
        actions = []
        blockers = []
        conflicts = []

        hardware_match = _match_one(payload, self.state.get("hardwares") or []) if tipo == "HARDWARE" else {
            "confirmado": False, "ambiguo": False, "registro": None, "candidatos": [], "conflitosIdentidade": []
        }
        product_match = _match_one(payload, self.state.get("produtos") or []) if tipo in {"HARDWARE", "PRODUTO"} else {
            "confirmado": False, "ambiguo": False, "registro": None, "candidatos": [], "conflitosIdentidade": []
        }

        if hardware_match.get("ambiguo") or product_match.get("ambiguo"):
            blockers.append("IDENTIDADE_AMBIGUA_NO_CRIABYTE")
        if hardware_match.get("conflitosIdentidade") or product_match.get("conflitosIdentidade"):
            blockers.append("CONFLITO_DE_IDENTIDADE")

        hw_record = hardware_detail or hardware_match.get("registro")
        prod_record = product_detail or product_match.get("registro")

        # Se o Hardware já está vinculado a Produto, esse vínculo prevalece sobre uma
        # busca paralela do Produto e evita criar duplicado comercial.
        linked_product_id = hw_record.get("produtoId") if isinstance(hw_record, dict) else None
        if linked_product_id:
            linked = next((p for p in self.state.get("produtos") or [] if p.get("id") == linked_product_id), None)
            if linked:
                prod_record = product_detail if product_detail and product_detail.get("id") == linked_product_id else linked
                product_match = {
                    "confirmado": True, "ambiguo": False, "metodo": "VINCULO_HARDWARE_PRODUTO",
                    "confianca": "MUITO_ALTA", "score": 100, "registro": prod_record,
                    "candidatos": [], "conflitosIdentidade": [],
                }

        hw_patch = {}
        hw_filled = []
        prod_patch = {}
        prod_filled = []

        if tipo == "HARDWARE" and hw_record:
            base_patch, filled, base_conflicts = _base_patch(hw_record, payload)
            hw_patch.update(base_patch)
            hw_filled.extend(filled)
            conflicts.extend({"entidade": "HARDWARE", **item} for item in base_conflicts)

            incoming_spec = payload.get(spec_field) if spec_field else None
            existing_spec = hw_record.get(spec_field) if spec_field else None
            if spec_field and isinstance(incoming_spec, dict):
                merged, spec_filled, spec_conflicts = _merge_missing(existing_spec or {}, incoming_spec)
                conflicts.extend({"entidade": "HARDWARE", **item} for item in spec_conflicts)
                if spec_filled:
                    required_missing = [x for x in REQUIRED.get(category, []) if _missing(merged.get(x))]
                    if required_missing:
                        blockers.append({
                            "codigo": "ESPECIFICACAO_HARDWARE_AINDA_INCOMPLETA",
                            "campos": required_missing,
                        })
                    else:
                        hw_patch[spec_field] = merged
                        hw_filled.extend(spec_filled)
            if hw_patch:
                actions.append({
                    "tipo": "ATUALIZAR_HARDWARE_CAMPOS_VAZIOS",
                    "metodo": "PATCH",
                    "rota": f"/admin/hardwares/{hw_record.get('id')}",
                    "payload": hw_patch,
                    "automaticamenteSeguro": True,
                })

        if prod_record:
            base_patch, filled, base_conflicts = _base_patch(prod_record, payload)
            prod_patch.update(base_patch)
            prod_filled.extend(filled)
            conflicts.extend({"entidade": "PRODUTO", **item} for item in base_conflicts)
            if tipo == "PRODUTO" and spec_field and isinstance(payload.get(spec_field), dict):
                existing_spec = prod_record.get(spec_field) or {}
                merged, spec_filled, spec_conflicts = _merge_missing(existing_spec, payload.get(spec_field))
                conflicts.extend({"entidade": "PRODUTO", **item} for item in spec_conflicts)
                if spec_filled:
                    prod_patch[spec_field] = merged
                    prod_filled.extend(spec_filled)
            if prod_patch:
                actions.append({
                    "tipo": "ATUALIZAR_PRODUTO_CAMPOS_VAZIOS",
                    "metodo": "PATCH",
                    "rota": f"/admin/produtos/{prod_record.get('id')}",
                    "payload": prod_patch,
                    "automaticamenteSeguro": True,
                })

        product_id_for_offer = prod_record.get("id") if isinstance(prod_record, dict) else None
        hardware_id = hw_record.get("id") if isinstance(hw_record, dict) else None

        # Criação: o backend exige Hardware técnico primeiro, depois Produto comercial.
        if tipo == "HARDWARE" and not hw_record and not blockers:
            hardware_payload = _strip_system(payload)
            required_missing = [x for x in REQUIRED.get(category, []) if _missing((hardware_payload.get(spec_field) or {}).get(x))]
            base_missing = [x for x in ("nome", "marca", "modelo") if _missing(hardware_payload.get(x))]
            if required_missing or base_missing:
                blockers.append({
                    "codigo": "HARDWARE_NOVO_INCOMPLETO",
                    "campos": base_missing + required_missing,
                })
            else:
                actions.append({
                    "tipo": "CRIAR_HARDWARE",
                    "metodo": "POST",
                    "rota": "/hardwares",
                    "payload": hardware_payload,
                    "resultadoId": "hardwareIdCriado",
                    "automaticamenteSeguro": False,
                })
                hardware_id = "{hardwareIdCriado}"

        if tipo == "HARDWARE":
            if hw_record and not linked_product_id and prod_record:
                blockers.append("HARDWARE_E_PRODUTO_EXISTEM_MAS_NAO_ESTAO_VINCULADOS")
            elif not prod_record and not blockers:
                if hardware_id:
                    actions.append({
                        "tipo": "CRIAR_PRODUTO_DE_HARDWARE",
                        "metodo": "POST",
                        "rota": f"/admin/produtos/de-hardware/{hardware_id}",
                        "payload": {
                            "nome": payload.get("nome"),
                            "descricao": payload.get("descricao"),
                            "imagemUrl": payload.get("imagemUrl"),
                            "publicado": False,
                            "ativo": True,
                        },
                        "resultadoId": "produtoIdCriado",
                        "automaticamenteSeguro": False,
                    })
                    product_id_for_offer = "{produtoIdCriado}"

        if tipo == "PRODUTO" and not prod_record and not blockers:
            slug = CATEGORY_SLUGS.get(category)
            category_row = _category_by_slug(self.state.get("categorias") or [], slug)
            if not category_row:
                blockers.append({"codigo": "CATEGORIA_PRODUTO_NAO_ENCONTRADA", "slug": slug})
            elif _missing(payload.get("nome")):
                blockers.append("PRODUTO_NOVO_SEM_NOME")
            else:
                product_payload = _strip_system(payload)
                product_payload.pop("categoria", None)
                product_payload["categoriaId"] = category_row.get("id")
                product_payload.setdefault("publicado", False)
                product_payload.setdefault("ativo", True)
                actions.append({
                    "tipo": "CRIAR_PRODUTO",
                    "metodo": "POST",
                    "rota": "/admin/produtos",
                    "payload": product_payload,
                    "resultadoId": "produtoIdCriado",
                    "automaticamenteSeguro": False,
                })
                product_id_for_offer = "{produtoIdCriado}"

        if tipo in {"NOTEBOOK", "BUILD"}:
            blockers.append("CADASTRO_ESPECIALIZADO_DEVE_USAR_ROTA_PROPRIA_DO_BACKEND")

        url = collected_offer.get("urlOriginal") or collected_offer.get("urlProduto")
        partner = _find_partner(self.state.get("parceiros") or [], url, source.get("plataforma"))
        offer_record = None
        offer_candidates = []
        if isinstance(product_id_for_offer, int):
            offer_record, offer_candidates = _match_offer(
                self.state.get("ofertas") or [], product_id_for_offer,
                partner.get("id") if partner else None, url,
            )

        if offer_candidates and not offer_record:
            blockers.append("OFERTA_AMBIGUA_NO_CRIABYTE")

        if offer_record:
            patch = _offer_patch(offer_record, collected_offer)
            if patch:
                actions.append({
                    "tipo": "ATUALIZAR_OFERTA",
                    "metodo": "PATCH",
                    "rota": f"/admin/ofertas/{offer_record.get('id')}",
                    "payload": patch,
                    "automaticamenteSeguro": True,
                })
        elif product_id_for_offer and url and partner and not offer_candidates:
            price = collected_offer.get("preco")
            available = collected_offer.get("disponivel")
            if available is False:
                blockers.append("BACKEND_NAO_CRIA_NOVA_OFERTA_JA_INDISPONIVEL")
            elif price is None or float(price) <= 0:
                blockers.append("NOVA_OFERTA_SEM_PRECO_VALIDO")
            else:
                offer_payload = {
                    "produtoId": product_id_for_offer,
                    "parceiroId": partner.get("id"),
                    "urlOriginal": url,
                    "preco": round(float(price), 2),
                }
                if collected_offer.get("precoAnterior") not in (None, ""):
                    offer_payload["precoAnterior"] = round(float(collected_offer.get("precoAnterior")), 2)
                actions.append({
                    "tipo": "CRIAR_OFERTA",
                    "metodo": "POST",
                    "rota": "/admin/ofertas",
                    "payload": offer_payload,
                    "automaticamenteSeguro": False,
                })
        elif url and product_id_for_offer and not partner:
            blockers.append({"codigo": "PARCEIRO_NAO_ENCONTRADO", "host": _host(url)})

        return {
            "versao": 14,
            "modo": "CONSULTA_E_PLANEJAMENTO",
            "aplicaAlteracoesAutomaticamente": False,
            "identidade": identity,
            "hardware": {
                "aplica": tipo == "HARDWARE",
                "match": _public_match(hardware_match),
                "camposVaziosPreenchiveis": hw_filled,
                "patch": hw_patch,
            },
            "produto": {
                "aplica": tipo in {"HARDWARE", "PRODUTO"},
                "match": _public_match(product_match),
                "camposVaziosPreenchiveis": prod_filled,
                "patch": prod_patch,
            },
            "oferta": {
                "produtoId": product_id_for_offer,
                "parceiro": {"id": partner.get("id"), "nome": partner.get("nome")} if partner else None,
                "existente": {"id": offer_record.get("id"), "status": offer_record.get("status"), "preco": offer_record.get("preco")} if offer_record else None,
            },
            "conflitos": conflicts,
            "bloqueios": blockers,
            "requerRevisao": bool(conflicts or blockers or any(not a.get("automaticamenteSeguro") for a in actions)),
            "acoesSugeridas": actions,
            "politica": {
                "preencherSomenteVazios": True,
                "naoSobrescreverConflitos": True,
                "precoSomenteEmOferta": True,
                "hardwareSemPreco": True,
                "produtoSemPreco": True,
                "cadastroPrincipalUmaUrlPorVez": True,
            },
        }


def plan_with_client(result, client):
    state = client.snapshot()
    preliminary = CriaBytePlanner(state).plan(result)
    hw_id = preliminary.get("hardware", {}).get("match", {}).get("id")
    prod_id = preliminary.get("produto", {}).get("match", {}).get("id")
    hardware_detail = client.buscar_hardware(hw_id) if hw_id else None

    # Se o Hardware apontar para um Produto, buscar o Produto vinculado, mesmo que
    # a busca inicial por identidade não o tenha encontrado na lista resumida.
    linked_product_id = hardware_detail.get("produtoId") if isinstance(hardware_detail, dict) else None
    detail_product_id = linked_product_id or prod_id
    product_detail = client.buscar_produto(detail_product_id) if detail_product_id else None
    return CriaBytePlanner(state).plan(result, hardware_detail=hardware_detail, product_detail=product_detail)
