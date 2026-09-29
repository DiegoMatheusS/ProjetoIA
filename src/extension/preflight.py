from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..api import AnalyzeRequest, _analyze_sync
from ..criabyte.client import CriaByteApiError, CriaByteClient
from ..extractors.backend_schemas import CATEGORY_SLUGS, SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..technical_ai.providers import TechnicalAIProviderError
from ..technical_ai.service import enrich_hardware_with_external_ai
from .payload_guard import (
    extension_registration_issues,
    sanitize_extension_hardware_payload,
)


class PrepareAffiliateOfferRequest(BaseModel):
    urlProduto: str = Field(min_length=8, max_length=4096)
    urlAfiliada: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)
    precoManual: float | None = Field(default=None, gt=0, le=100_000_000)
    dadosPagina: dict[str, Any] = Field(default_factory=dict)
    dadosManuais: dict[str, str | int | float | bool] = Field(default_factory=dict)
    provedorComplemento: str | None = Field(default=None, max_length=20)


class ConfirmAffiliateOfferRequest(BaseModel):
    token: str = Field(min_length=32, max_length=200_000)


_MARKETPLACES: tuple[tuple[str, str, str], ...] = (
    ("amazon.", "AMAZON", "Amazon"),
    ("mercadolivre.", "MERCADO_LIVRE", "Mercado Livre"),
    ("mercadolibre.", "MERCADO_LIVRE", "Mercado Livre"),
    ("shopee.", "SHOPEE", "Shopee"),
    ("magazineluiza.", "MAGALU", "Magazine Luiza"),
    ("kabum.", "KABUM", "KaBuM!"),
    ("pichau.", "PICHAU", "Pichau"),
    ("terabyteshop.", "TERABYTE", "TerabyteShop"),
    ("aliexpress.", "ALIEXPRESS", "AliExpress"),
)

_COMMON_PAGE_FIELDS = (
    "nome",
    "marca",
    "modelo",
    "mpn",
    "gtin",
    "asin",
    "imagemUrl",
)

_REQUIRED_PRODUCT_ROOT = ("nome", "marca", "modelo")
_PRODUCT_CORE_SPECS: dict[str, tuple[str, ...]] = {
    "MONITOR": (
        "tamanhoPolegadas",
        "resolucao",
        "taxaAtualizacaoHz",
        "tipoPainel",
    ),
    "MOUSE": ("sensor", "dpiMaximo", "conexao"),
    "TECLADO": ("tipo", "layout", "conexao"),
    "HEADSET": ("tipoConexao", "microfone"),
}

_FIELD_LABELS = {
    "nome": "Nome do produto",
    "marca": "Marca",
    "modelo": "Modelo",
    "especificacaoFonte.formato": "Formato da fonte",
    "especificacaoFonte.potenciaWatts": "Potência da fonte (W)",
    "especificacaoMonitor.tamanhoPolegadas": "Tamanho da tela (pol.)",
    "especificacaoMonitor.resolucao": "Resolução",
    "especificacaoMonitor.taxaAtualizacaoHz": "Taxa de atualização (Hz)",
    "especificacaoMonitor.tipoPainel": "Tipo de painel",
    "especificacaoMouse.sensor": "Sensor",
    "especificacaoMouse.dpiMaximo": "DPI máximo",
    "especificacaoMouse.conexao": "Conexão",
    "especificacaoTeclado.tipo": "Tipo de teclado",
    "especificacaoTeclado.layout": "Layout",
    "especificacaoTeclado.conexao": "Conexão",
    "especificacaoHeadset.tipoConexao": "Tipo de conexão",
    "especificacaoHeadset.microfone": "Possui microfone",
}


def _text(value: Any, max_length: int = 500) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value[:max_length] or None


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _canonical_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/") or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def _asin(value: Any) -> str | None:
    token = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return token if re.fullmatch(r"[A-Z0-9]{10}", token) else None


def _asin_from_url(url: str) -> str | None:
    path = urlparse(url).path
    match = re.search(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:[/?]|$)", path, re.I)
    return _asin(match.group(1)) if match else None


def _page_data(raw: dict[str, Any], url: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in _COMMON_PAGE_FIELDS:
        value = raw.get(field)
        if field == "asin":
            normalized = _asin(value) or _asin_from_url(url)
            if normalized:
                data[field] = normalized
            continue
        if field == "imagemUrl":
            image = _canonical_url(_text(value, 2000)) if value else None
            if image:
                data[field] = image
            continue
        clean = _text(value, 250)
        if clean:
            data[field] = clean

    price = raw.get("preco")
    try:
        numeric = round(float(price), 2)
    except (TypeError, ValueError):
        numeric = 0.0
    if 0 < numeric <= 100_000_000:
        data["preco"] = numeric
    return data


def _identity(data: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in ("asin", "gtin", "mpn", "marca", "modelo", "nome"):
        value = _text(data.get(field), 250)
        if value:
            result[field] = value
    return result


def _partner(url: str, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    platform = None
    if analysis:
        origin = analysis.get("origemColeta")
        if isinstance(origin, dict):
            platform = _text(origin.get("plataforma"), 40)
            platform = platform.upper() if platform else None
    name = None
    for fragment, candidate_platform, candidate_name in _MARKETPLACES:
        if fragment in host:
            platform = platform or candidate_platform
            name = candidate_name
            break
    if not name:
        name = host.split(".")[-2].title() if "." in host else (host or "Loja")
    return {
        "plataforma": platform or "OUTRO_SITE",
        "nome": name,
        "dominio": host or None,
        "host": host or None,
    }


def _price(
    request: PrepareAffiliateOfferRequest,
    page: dict[str, Any],
    analysis: dict[str, Any] | None = None,
) -> float | None:
    candidates = [request.precoManual, page.get("preco")]
    if analysis:
        offer = analysis.get("ofertaColetada")
        if isinstance(offer, dict):
            candidates.append(offer.get("preco"))
    for candidate in candidates:
        try:
            value = round(float(candidate), 2)
        except (TypeError, ValueError):
            continue
        if 0 < value <= 100_000_000:
            return value
    return None


def _offer(
    request: PrepareAffiliateOfferRequest,
    page: dict[str, Any],
    price: float,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    original = _canonical_url(request.urlProduto)
    affiliate = _canonical_url(request.urlAfiliada)
    if not original:
        raise ValueError("URL do produto inválida.")
    if not affiliate:
        raise ValueError("Link afiliado inválido.")
    result: dict[str, Any] = {
        "urlOriginal": original,
        "urlAfiliada": affiliate,
        "preco": price,
    }
    if page.get("asin"):
        result["asin"] = page["asin"]
        result["codigoMarketplace"] = page["asin"]
    elif analysis:
        collected = analysis.get("ofertaColetada")
        if isinstance(collected, dict):
            code = _text(collected.get("codigoMarketplace"), 160)
            if code:
                result["codigoMarketplace"] = code
            previous = collected.get("precoAnterior")
            try:
                previous_value = round(float(previous), 2)
            except (TypeError, ValueError):
                previous_value = 0
            if previous_value > price:
                result["precoAnterior"] = previous_value
    return result


def _merge_page_identity(raw_payload: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    output = dict(raw_payload or {})
    for field in ("nome", "marca", "modelo", "mpn", "gtin", "imagemUrl"):
        if _present(page.get(field)):
            output[field] = page[field]
    return output


def _set_nested(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if len(parts) == 1:
        payload[parts[0]] = value
    elif len(parts) == 2:
        nested = payload.get(parts[0])
        if not isinstance(nested, dict):
            nested = {}
            payload[parts[0]] = nested
        nested[parts[1]] = value


def _apply_manual(
    category: str,
    raw_payload: dict[str, Any],
    manual: dict[str, str | int | float | bool],
) -> dict[str, Any]:
    output = dict(raw_payload)
    allowed = {"nome", "marca", "modelo", "mpn", "gtin"}
    schema = SCHEMAS.get(category)
    if schema and schema[1]:
        for field in schema[2] or []:
            allowed.add(f"{schema[1]}.{field}")
    for path, value in list(manual.items())[:48]:
        path = str(path or "").strip()
        if path in allowed and _present(value):
            _set_nested(output, path, value)
    return output


def _issue_path(issue: str) -> str | None:
    match = re.match(
        r"\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)",
        issue,
    )
    return match.group(1) if match else None


def _field_descriptor(path: str) -> dict[str, Any]:
    name = path.rsplit(".", 1)[-1]
    lower = name.lower()
    kind = "text"
    if lower in {"microfone", "wireless", "bluetooth", "nfc", "hdr", "rgb"}:
        kind = "boolean"
    elif any(token in lower for token in ("watts", "mhz", "hz", "gb", "dpi", "nits")):
        kind = "integer"
    elif any(token in lower for token in ("polegadas", "ms", "percentual")):
        kind = "number"
    result: dict[str, Any] = {
        "campo": path,
        "label": _FIELD_LABELS.get(path, path.replace(".", " › ")),
        "tipo": kind,
    }
    if path == "especificacaoFonte.formato":
        result["opcoes"] = ["ATX", "SFX", "SFX_L", "TFX", "FLEX_ATX"]
    return result


def _missing_product_paths(category: str, payload: dict[str, Any]) -> list[str]:
    missing = [field for field in _REQUIRED_PRODUCT_ROOT if not _present(payload.get(field))]
    schema = SCHEMAS.get(category)
    if schema and schema[1]:
        specs = payload.get(schema[1])
        specs = specs if isinstance(specs, dict) else {}
        for field in _PRODUCT_CORE_SPECS.get(category, ()):
            if not _present(specs.get(field)):
                missing.append(f"{schema[1]}.{field}")
    return missing


def _product_payload(
    category: str,
    analysis: dict[str, Any],
    raw_payload: dict[str, Any],
    page: dict[str, Any],
) -> dict[str, Any]:
    schema = SCHEMAS.get(category)
    if not schema or schema[0] != "PRODUTO":
        raise ValueError(f"Categoria {category} não usa cadastro de Produto.")
    slug = str(
        analysis.get("categoriaSlugSugerida") or CATEGORY_SLUGS.get(category) or ""
    ).strip().lower()
    if not slug:
        raise ValueError("Categoria comercial do Produto não foi identificada.")
    result: dict[str, Any] = {"categoriaSlug": slug}
    for field in (
        "nome",
        "marca",
        "modelo",
        "descricao",
        "mpn",
        "gtin",
        "imagemUrl",
        "imagemHoverUrl",
        "metadados",
    ):
        if _present(raw_payload.get(field)):
            result[field] = raw_payload[field]
    if page.get("asin"):
        result["asin"] = page["asin"]
    spec_field = schema[1]
    expected = set(schema[2] or [])
    if spec_field and isinstance(raw_payload.get(spec_field), dict):
        specs = {
            key: value
            for key, value in raw_payload[spec_field].items()
            if key in expected and _present(value)
        }
        if specs:
            result[spec_field] = specs
    return result


def _spec_preview(category: str, payload: dict[str, Any]) -> dict[str, Any]:
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return {}
    specs = payload.get(schema[1])
    if not isinstance(specs, dict):
        return {}
    result: dict[str, Any] = {}
    for key in schema[2] or []:
        if _present(specs.get(key)):
            result[key] = specs[key]
        if len(result) >= 16:
            break
    return result


def _preview(
    *,
    category: str | None,
    registration_type: str,
    payload: dict[str, Any],
    page: dict[str, Any],
    partner: dict[str, Any],
    offer: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing_product = (existing or {}).get("produto") or {}
    existing_hardware = (existing or {}).get("hardware") or {}
    return {
        "acao": "SOMENTE_OFERTA" if existing and existing.get("encontrado") else "CRIAR_ITEM_E_OFERTA",
        "existente": bool(existing and existing.get("encontrado")),
        "criterioCorrespondencia": (existing or {}).get("criterio"),
        "categoria": category or existing_product.get("categoria", {}).get("slug") or existing_hardware.get("categoria"),
        "tipoCadastro": registration_type,
        "nome": payload.get("nome") or existing_product.get("nome") or existing_hardware.get("nome") or page.get("nome"),
        "marca": payload.get("marca") or existing_product.get("marca") or existing_hardware.get("marca") or page.get("marca"),
        "modelo": payload.get("modelo") or existing_product.get("modelo") or existing_hardware.get("modelo") or page.get("modelo"),
        "asin": page.get("asin"),
        "gtin": payload.get("gtin") or existing_product.get("gtin") or page.get("gtin"),
        "mpn": payload.get("mpn") or existing_product.get("mpn") or page.get("mpn"),
        "preco": offer.get("preco"),
        "parceiro": partner.get("nome"),
        "fornecedor": partner.get("nome"),
        "publicar": True,
        "especificacoes": _spec_preview(category or "", payload),
    }


def _token_secret() -> bytes:
    secret = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if not secret:
        raise RuntimeError("PRODUTO_IA_API_KEY não configurada para assinar a confirmação.")
    return secret.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_preparation(internal_payload: dict[str, Any], preview: dict[str, Any]) -> str:
    envelope = {
        "v": 1,
        "exp": int(time.time()) + 600,
        "payload": internal_payload,
        "previa": preview,
    }
    raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64encode(raw)
    signature = hmac.new(_token_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def verify_preparation(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(_token_secret(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            raise ValueError("assinatura inválida")
        envelope = json.loads(_b64decode(body).decode("utf-8"))
        if int(envelope.get("exp") or 0) < int(time.time()):
            raise ValueError("confirmação expirada")
        if not isinstance(envelope.get("payload"), dict):
            raise ValueError("payload inválido")
        return envelope
    except Exception as exc:
        raise ValueError(f"Token de confirmação inválido: {exc}") from exc


def _existing_internal_payload(
    existing: dict[str, Any],
    partner: dict[str, Any],
    offer: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "parceiro": {
            "nome": partner["nome"],
            "dominio": partner.get("dominio"),
            "site": f"https://{partner['host']}" if partner.get("host") else None,
        },
        "oferta": offer,
    }
    if existing.get("tipo") == "HARDWARE" and (existing.get("hardware") or {}).get("id"):
        result["hardwareExistenteId"] = int(existing["hardware"]["id"])
    elif (existing.get("produto") or {}).get("id"):
        result["produtoExistenteId"] = int(existing["produto"]["id"])
    else:
        raise ValueError("Item existente retornou sem ID utilizável.")
    return result


def prepare_offer_sync(request: PrepareAffiliateOfferRequest) -> dict[str, Any]:
    product_url = _canonical_url(request.urlProduto)
    affiliate_url = _canonical_url(request.urlAfiliada)
    if not product_url:
        raise ValueError("Página do produto inválida.")
    if not affiliate_url:
        raise ValueError("Link afiliado inválido.")

    page = _page_data(request.dadosPagina, product_url)
    identity = _identity(page)
    client = CriaByteClient()
    existing = client.localizar_item_extensao(
        identity,
        api_key=os.getenv("PRODUTO_IA_API_KEY"),
    ) if identity else {"encontrado": False, "motivo": "IDENTIDADE_INSUFICIENTE"}

    partner = _partner(product_url)
    price = _price(request, page)

    if isinstance(existing, dict) and existing.get("encontrado"):
        if price is None:
            return {
                "status": "PRECISA_PRECO",
                "motivo": "Item já existe no Criabyte, mas o preço do anúncio não foi identificado.",
                "itemExistente": existing,
                "requerPrecoManual": True,
            }
        offer = _offer(request, page, price)
        registration_type = str(existing.get("tipo") or "PRODUTO").upper()
        preview_payload = {
            "nome": (existing.get("produto") or {}).get("nome") or (existing.get("hardware") or {}).get("nome"),
            "marca": (existing.get("produto") or {}).get("marca") or page.get("marca"),
            "modelo": (existing.get("produto") or {}).get("modelo") or page.get("modelo"),
            "gtin": (existing.get("produto") or {}).get("gtin") or page.get("gtin"),
            "mpn": (existing.get("produto") or {}).get("mpn") or page.get("mpn"),
        }
        preview = _preview(
            category=None,
            registration_type=registration_type,
            payload=preview_payload,
            page=page,
            partner=partner,
            offer=offer,
            existing=existing,
        )
        internal = _existing_internal_payload(existing, partner, offer)
        return {
            "status": "PRONTO_PARA_CONFIRMAR",
            "acao": "SOMENTE_OFERTA",
            "itemExistente": existing,
            "previa": preview,
            "token": sign_preparation(internal, preview),
        }

    analysis = _analyze_sync(
        AnalyzeRequest(
            url=product_url,
            urlAfiliada=affiliate_url,
            categoria=request.categoria,
            enrich=True,
            criabytePlan=False,
            noBrowser=False,
        )
    )
    category = str(analysis.get("categoriaDetectada") or "").strip().upper()
    raw_payload = analysis.get("payloadParcialBackend")
    if not category or not isinstance(raw_payload, dict):
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": "Não foi possível identificar uma categoria suportada para cadastro.",
            "previa": {"nome": page.get("nome"), "asin": page.get("asin")},
        }

    raw_payload = _merge_page_identity(raw_payload, page)
    raw_payload = _apply_manual(category, raw_payload, request.dadosManuais)
    schema = SCHEMAS.get(category)
    registration_type = str(analysis.get("tipoCadastro") or (schema[0] if schema else "")).upper()

    provider = str(request.provedorComplemento or "").strip().upper()
    if provider and provider not in {"OPENAI", "META_AI"}:
        raise ValueError("provedorComplemento deve ser OPENAI ou META_AI.")

    if registration_type == "HARDWARE" and provider:
        try:
            enriched = enrich_hardware_with_external_ai(
                provider_name=provider,
                category=category,
                name=_text(raw_payload.get("nome"), 200),
                payload=raw_payload,
                only_fill_gaps=True,
            )
            candidate = enriched.get("payload") if isinstance(enriched, dict) else None
            if isinstance(candidate, dict):
                raw_payload = candidate
        except TechnicalAIProviderError as exc:
            return {
                "status": "REVISAO_NECESSARIA",
                "motivo": f"Não foi possível completar com {provider}: {exc.message}",
                "codigo": exc.code,
                "provedor": provider,
            }

    partner = _partner(product_url, analysis)
    price = _price(request, page, analysis)
    if price is None:
        return {
            "status": "PRECISA_PRECO",
            "motivo": "Preço do anúncio não foi identificado.",
            "requerPrecoManual": True,
        }
    offer = _offer(request, page, price, analysis)

    if registration_type == "HARDWARE":
        hardware_payload = normalize_hardware_payload_for_backend(category, raw_payload)
        hardware_payload = sanitize_extension_hardware_payload(category, hardware_payload)
        issues = extension_registration_issues(category, hardware_payload)
        if issues and not provider:
            preview = _preview(
                category=category,
                registration_type=registration_type,
                payload=hardware_payload,
                page=page,
                partner=partner,
                offer=offer,
            )
            return {
                "status": "COMPLETAR_COM_IA",
                "motivo": "O item ainda não existe no Criabyte e a ficha técnica possui lacunas.",
                "provedoresDisponiveis": ["OPENAI", "META_AI"],
                "pendencias": issues,
                "previa": preview,
            }
        if issues:
            paths = list(dict.fromkeys(path for issue in issues if (path := _issue_path(issue))))
            return {
                "status": "REVISAO_NECESSARIA",
                "motivo": "A IA ainda não conseguiu confirmar todos os dados obrigatórios. Complete os campos abaixo.",
                "pendencias": issues,
                "camposFaltantes": [_field_descriptor(path) for path in paths],
                "previa": _preview(
                    category=category,
                    registration_type=registration_type,
                    payload=hardware_payload,
                    page=page,
                    partner=partner,
                    offer=offer,
                ),
            }
        registration = {"hardwarePayload": hardware_payload}
        preview_source = hardware_payload
    elif registration_type == "PRODUTO":
        missing = _missing_product_paths(category, raw_payload)
        if missing:
            return {
                "status": "REVISAO_NECESSARIA",
                "motivo": "Alguns dados do Produto não foram encontrados. Complete os campos abaixo.",
                "pendencias": [f"{path} ausente" for path in missing],
                "camposFaltantes": [_field_descriptor(path) for path in missing],
                "previa": _preview(
                    category=category,
                    registration_type=registration_type,
                    payload=raw_payload,
                    page=page,
                    partner=partner,
                    offer=offer,
                ),
            }
        registration = {
            "produtoPayload": _product_payload(category, analysis, raw_payload, page)
        }
        preview_source = raw_payload
    else:
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": f"A categoria {category} usa o fluxo {registration_type or 'desconhecido'}, ainda não confirmado para esta extensão.",
            "categoria": category,
        }

    internal = {
        **registration,
        "parceiro": {
            "nome": partner["nome"],
            "dominio": partner.get("dominio"),
            "site": f"https://{partner['host']}" if partner.get("host") else None,
        },
        "oferta": offer,
    }
    preview = _preview(
        category=category,
        registration_type=registration_type,
        payload=preview_source,
        page=page,
        partner=partner,
        offer=offer,
    )
    return {
        "status": "PRONTO_PARA_CONFIRMAR",
        "acao": "CRIAR_ITEM_E_OFERTA",
        "previa": preview,
        "token": sign_preparation(internal, preview),
    }


def confirm_offer_sync(request: ConfirmAffiliateOfferRequest) -> dict[str, Any]:
    envelope = verify_preparation(request.token)
    result = CriaByteClient().importar_oferta_extensao(
        envelope["payload"],
        api_key=os.getenv("PRODUTO_IA_API_KEY"),
    )
    if not isinstance(result, dict):
        result = {"status": "CONCLUIDO", "resultado": result}
    result["previa"] = envelope.get("previa")
    result["confirmado"] = True
    return result
