from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..api import AnalyzeRequest, _analyze_sync
from ..criabyte.client import CriaByteApiError, CriaByteClient
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .amazon_fallback import amazon_browser_minimum_issues, hydrate_amazon_analysis
from .payload_guard import (
    extension_registration_issues,
    sanitize_extension_hardware_payload,
)
from .router import (
    ImportAffiliateOfferRequest,
    MissingPriceError,
    _analysis_product_url,
    _apply_manual_fields,
    _canonical_url,
    _field_descriptor,
    _import_sync,
    _missing_product_paths,
    _partner_from_analysis,
    _preview_payload,
    _product_payload_for_backend,
    _review_response,
    _spec_preview,
    _validate_api_key,
)

router = APIRouter(prefix="/extensao", tags=["Extensão administrativa v2"])


class PageCapture(BaseModel):
    nome: str | None = Field(default=None, max_length=300)
    marca: str | None = Field(default=None, max_length=100)
    modelo: str | None = Field(default=None, max_length=150)
    mpn: str | None = Field(default=None, max_length=150)
    gtin: str | None = Field(default=None, max_length=32)
    asin: str | None = Field(default=None, max_length=20)
    codigoMarketplace: str | None = Field(default=None, max_length=160)
    preco: float | None = Field(default=None, gt=0, le=100_000_000)


class ImportAffiliateOfferV2Request(BaseModel):
    urlProduto: str = Field(min_length=8, max_length=4096)
    urlAfiliada: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)
    precoManual: float | None = Field(default=None, gt=0, le=100_000_000)
    dadosManuais: dict[str, str | int | float | bool] = Field(default_factory=dict)
    dadosPagina: PageCapture = Field(default_factory=PageCapture)


_HOST_PLATFORMS = (
    ("amazon.com.br", "AMAZON"),
    ("amazon.com", "AMAZON"),
    ("mercadolivre.com.br", "MERCADO_LIVRE"),
    ("mercadolivre.com", "MERCADO_LIVRE"),
    ("mercadolibre.com", "MERCADO_LIVRE"),
    ("shopee.com.br", "SHOPEE"),
    ("magazineluiza.com.br", "MAGALU"),
    ("kabum.com.br", "KABUM"),
    ("pichau.com.br", "PICHAU"),
    ("terabyteshop.com.br", "TERABYTE"),
    ("aliexpress.com", "ALIEXPRESS"),
)


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_asin(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if re.fullmatch(r"[A-Z0-9]{10}", text) else None


def _platform_from_url(value: str) -> tuple[str, str | None]:
    host = (urlparse(value).hostname or "").lower().removeprefix("www.")
    for domain, platform in _HOST_PLATFORMS:
        if host == domain or host.endswith(f".{domain}"):
            return platform, host
    return "OUTRO_SITE", host or None


def _partner_from_url(value: str) -> dict[str, Any]:
    platform, host = _platform_from_url(value)
    return _partner_from_analysis(
        {"origemColeta": {"plataforma": platform, "host": host}},
        value,
    )


def _identity(payload: ImportAffiliateOfferV2Request) -> dict[str, str]:
    page = payload.dadosPagina
    values = {
        "nome": _clean(page.nome),
        "marca": _clean(page.marca),
        "modelo": _clean(page.modelo),
        "mpn": _clean(page.mpn),
        "gtin": _clean(page.gtin),
        "asin": _clean_asin(page.asin),
    }
    return {key: value for key, value in values.items() if value}


def _affiliate_url(payload: ImportAffiliateOfferV2Request) -> str:
    value = _canonical_url(payload.urlAfiliada)
    if not value:
        raise HTTPException(status_code=400, detail="Link afiliado inválido.")
    return value


def _page_offer(
    payload: ImportAffiliateOfferV2Request,
    affiliate_url: str,
) -> dict[str, Any]:
    original = _canonical_url(payload.urlProduto)
    if not original:
        raise HTTPException(status_code=400, detail="Página do produto inválida.")

    price = payload.precoManual if payload.precoManual is not None else payload.dadosPagina.preco
    if price is None or price <= 0:
        raise MissingPriceError("Preço do anúncio não foi identificado. Informe o valor para continuar.")

    asin = _clean_asin(payload.dadosPagina.asin)
    platform, _host = _platform_from_url(payload.urlProduto)
    marketplace_code = _clean(payload.dadosPagina.codigoMarketplace)
    if not marketplace_code and platform == "AMAZON" and asin:
        marketplace_code = asin

    offer: dict[str, Any] = {
        "urlOriginal": original,
        "urlAfiliada": affiliate_url,
        "preco": round(float(price), 2),
    }
    if marketplace_code:
        offer["codigoMarketplace"] = marketplace_code[:160]
    if asin:
        offer["asin"] = asin
    return offer


def _internal_partner(partner: dict[str, Any]) -> dict[str, Any]:
    return {
        "nome": partner["nome"],
        "dominio": partner.get("dominio"),
        "site": f"https://{partner['host']}" if partner.get("host") else None,
    }


def _existing_preview(
    preflight: dict[str, Any],
    payload: ImportAffiliateOfferV2Request,
    partner: dict[str, Any],
    offer: dict[str, Any],
    published: bool,
) -> dict[str, Any]:
    item = preflight.get("item") if isinstance(preflight.get("item"), dict) else {}
    return {
        "categoria": item.get("categoria"),
        "tipoCadastro": preflight.get("tipo"),
        "nome": item.get("nome") or payload.dadosPagina.nome,
        "marca": item.get("marca") or payload.dadosPagina.marca,
        "modelo": item.get("modelo") or payload.dadosPagina.modelo,
        "mpn": item.get("mpn") or payload.dadosPagina.mpn,
        "gtin": item.get("gtin") or payload.dadosPagina.gtin,
        "asin": item.get("asin") or _clean_asin(payload.dadosPagina.asin),
        "preco": offer.get("preco"),
        "parceiro": partner.get("nome"),
        "publicado": published,
        "especificacoes": {},
        "origem": "ITEM_EXISTENTE",
    }


def _merge_page_identity(raw_payload: dict[str, Any], payload: ImportAffiliateOfferV2Request) -> dict[str, Any]:
    merged = dict(raw_payload)
    page = payload.dadosPagina
    for field in ("nome", "marca", "modelo", "mpn", "gtin"):
        if not merged.get(field):
            value = _clean(getattr(page, field))
            if value:
                merged[field] = value
    return merged


def _import_existing(
    payload: ImportAffiliateOfferV2Request,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    affiliate_url = _affiliate_url(payload)
    partner = _partner_from_url(payload.urlProduto)
    offer = _page_offer(payload, affiliate_url)

    destination: dict[str, Any]
    if preflight.get("tipo") == "PRODUTO" and preflight.get("produtoId"):
        destination = {"produtoExistenteId": int(preflight["produtoId"])}
    elif preflight.get("tipo") == "HARDWARE" and preflight.get("hardwareId"):
        destination = {"hardwareExistenteId": int(preflight["hardwareId"])}
    else:
        raise ValueError("O item existente não trouxe um identificador interno válido.")

    result = CriaByteClient().importar_oferta_extensao(
        {
            **destination,
            "parceiro": _internal_partner(partner),
            "oferta": offer,
        },
        api_key=os.getenv("PRODUTO_IA_API_KEY"),
    )
    if not isinstance(result, dict):
        return {"status": "OPERACAO_CONCLUIDA", "resultado": result}

    result["completouComIa"] = False
    result["buscaCriabyte"] = {
        "status": "EXISTENTE",
        "criterio": preflight.get("criterio"),
        "tipo": preflight.get("tipo"),
    }
    result["previa"] = _existing_preview(
        preflight,
        payload,
        partner,
        offer,
        bool(result.get("publicado", True)),
    )
    return result


def _import_new_with_ai(
    payload: ImportAffiliateOfferV2Request,
    preflight_status: str,
) -> dict[str, Any]:
    analysis_url = _analysis_product_url(payload.urlProduto)
    analysis = _analyze_sync(
        AnalyzeRequest(
            url=analysis_url,
            urlAfiliada=payload.urlAfiliada,
            categoria=payload.categoria,
            enrich=True,
            criabytePlan=False,
            noBrowser=False,
        )
    )
    analysis = hydrate_amazon_analysis(
        analysis,
        url=payload.urlProduto,
        capture=payload.dadosPagina,
        forced_category=payload.categoria,
    )

    category = str(analysis.get("categoriaDetectada") or "").strip().upper()
    raw_payload = analysis.get("payloadParcialBackend")
    if not category or not isinstance(raw_payload, dict):
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": "Não foi possível identificar uma categoria suportada para cadastro. Confira o título capturado na aba do produto.",
            "analise": analysis,
            "buscaCriabyte": {"status": preflight_status},
        }

    raw_payload = _merge_page_identity(raw_payload, payload)
    raw_payload = _apply_manual_fields(category, raw_payload, payload.dadosManuais)

    registration_type = str(analysis.get("tipoCadastro") or "").strip().upper()
    if not registration_type:
        schema = SCHEMAS.get(category)
        registration_type = str(schema[0] if schema else "").upper()

    if registration_type == "HARDWARE":
        hardware_payload = normalize_hardware_payload_for_backend(category, raw_payload)
        hardware_payload = sanitize_extension_hardware_payload(category, hardware_payload)
        issues = extension_registration_issues(category, hardware_payload)
        if analysis.get("fallbackCapturaAmazon"):
            issues.extend(amazon_browser_minimum_issues(category, hardware_payload))
        issues = list(dict.fromkeys(issues))
        if issues:
            response = _review_response(
                category,
                hardware_payload,
                issues,
                analysis=analysis,
            )
            response["buscaCriabyte"] = {"status": preflight_status}
            response["completouComIa"] = True
            return response
        registration_payload = {"hardwarePayload": hardware_payload}
        preview_source = hardware_payload
    elif registration_type == "PRODUTO":
        missing_paths = _missing_product_paths(category, raw_payload)
        if missing_paths:
            return {
                "status": "REVISAO_NECESSARIA",
                "motivo": "Alguns dados do Produto não foram identificados. Preencha os campos abaixo para continuar.",
                "pendencias": [f"{path} ausente" for path in missing_paths],
                "camposFaltantes": [_field_descriptor(path) for path in missing_paths],
                "categoria": category,
                "previa": _preview_payload(
                    category,
                    registration_type,
                    raw_payload,
                    analysis,
                ),
                "buscaCriabyte": {"status": preflight_status},
                "completouComIa": True,
            }
        product_payload = _product_payload_for_backend(category, analysis, raw_payload)
        asin = _clean_asin(payload.dadosPagina.asin)
        if asin:
            product_payload["asin"] = asin
        registration_payload = {"produtoPayload": product_payload}
        preview_source = raw_payload
    else:
        legacy = _import_sync(
            ImportAffiliateOfferRequest(
                urlProduto=payload.urlProduto,
                urlAfiliada=payload.urlAfiliada,
                categoria=payload.categoria,
                precoManual=payload.precoManual,
                dadosManuais=payload.dadosManuais,
            )
        )
        if isinstance(legacy, dict):
            legacy["buscaCriabyte"] = {"status": preflight_status}
            legacy["completouComIa"] = True
        return legacy

    affiliate_url = _affiliate_url(payload)
    partner = _partner_from_analysis(analysis, payload.urlProduto)
    manual_or_page_price = (
        payload.precoManual
        if payload.precoManual is not None
        else payload.dadosPagina.preco
    )
    from .router import _offer_payload

    offer = _offer_payload(
        analysis,
        affiliate_url=affiliate_url,
        manual_price=manual_or_page_price,
    )
    asin = _clean_asin(payload.dadosPagina.asin)
    platform, _host = _platform_from_url(payload.urlProduto)
    if asin:
        offer["asin"] = asin
        if platform == "AMAZON" and not offer.get("codigoMarketplace"):
            offer["codigoMarketplace"] = asin

    result = CriaByteClient().importar_oferta_extensao(
        {
            **registration_payload,
            "parceiro": _internal_partner(partner),
            "oferta": offer,
        },
        api_key=os.getenv("PRODUTO_IA_API_KEY"),
    )
    if not isinstance(result, dict):
        return {"status": "OPERACAO_CONCLUIDA", "resultado": result}

    preview = _preview_payload(
        category,
        registration_type,
        preview_source,
        analysis,
        partner=partner,
        offer=offer,
        published=bool(result.get("publicado", True)),
    )
    preview.update(
        {
            "asin": asin,
            "gtin": raw_payload.get("gtin"),
            "mpn": raw_payload.get("mpn"),
            "origem": "COMPLETAR_COM_IA",
        }
    )
    result["previa"] = preview
    result["completouComIa"] = True
    result["buscaCriabyte"] = {"status": preflight_status}
    return result


def _import_v2_sync(payload: ImportAffiliateOfferV2Request) -> dict[str, Any]:
    identity = _identity(payload)
    client = CriaByteClient()
    preflight: dict[str, Any] = {"status": "DADOS_INSUFICIENTES"}

    if identity:
        response = client.buscar_item_extensao(
            identity,
            api_key=os.getenv("PRODUTO_IA_API_KEY"),
        )
        if isinstance(response, dict):
            preflight = response

    status = str(preflight.get("status") or "DADOS_INSUFICIENTES").upper()
    if status == "EXISTENTE":
        return _import_existing(payload, preflight)

    return _import_new_with_ai(payload, status)


@router.post("/importar-oferta-v2")
async def import_affiliate_offer_v2(
    payload: ImportAffiliateOfferV2Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        return await asyncio.to_thread(_import_v2_sync, payload)
    except HTTPException:
        raise
    except MissingPriceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "codigo": "PRECO_NAO_IDENTIFICADO",
                "mensagem": str(exc),
                "requerPrecoManual": True,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CriaByteApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao importar oferta pela extensão v2: {exc}",
        ) from exc
