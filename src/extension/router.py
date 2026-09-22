from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..api import AnalyzeRequest, _analyze_sync
from ..criabyte.client import CriaByteApiError, CriaByteClient
from ..extractors.dto_normalizer import (
    normalize_hardware_payload_for_backend,
    registration_payload_issues,
)


router = APIRouter(prefix="/extensao", tags=["Extensão administrativa"])


class ImportAffiliateOfferRequest(BaseModel):
    urlProduto: str = Field(min_length=8, max_length=4096)
    urlAfiliada: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)


_MARKETPLACE_PARTNERS: dict[str, tuple[str, str | None]] = {
    "MERCADO_LIVRE": ("Mercado Livre", "mercadolivre.com.br"),
    "SHOPEE": ("Shopee", "shopee.com.br"),
    "MAGALU": ("Magazine Luiza", "magazineluiza.com.br"),
    "KABUM": ("KaBuM!", "kabum.com.br"),
    "PICHAU": ("Pichau", "pichau.com.br"),
    "TERABYTE": ("TerabyteShop", "terabyteshop.com.br"),
    "AMAZON": ("Amazon", "amazon.com.br"),
    "ALIEXPRESS": ("AliExpress", "aliexpress.com"),
}


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _canonical_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    # Fragmentos nunca identificam outro anúncio e só atrapalham a deduplicação.
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") or "/", parsed.params, parsed.query, ""))


def _partner_from_analysis(analysis: dict[str, Any], product_url: str) -> dict[str, Any]:
    source = analysis.get("origemColeta") if isinstance(analysis.get("origemColeta"), dict) else {}
    platform = str(source.get("plataforma") or "OUTRO_SITE").strip().upper()
    host = str(source.get("host") or urlparse(product_url).hostname or "").strip().lower() or None

    partner_name, default_domain = _MARKETPLACE_PARTNERS.get(
        platform,
        ((host.split(".")[-2].title() if host and "." in host else (host or "Loja")), host),
    )
    return {
        "plataforma": platform,
        "nome": partner_name,
        "dominio": default_domain or host,
        "host": host,
    }


def _find_partner(partners: list[dict[str, Any]], expected: dict[str, Any]) -> dict[str, Any] | None:
    wanted_name = _norm(expected.get("nome"))
    wanted_domain = _norm(expected.get("dominio"))
    for partner in partners:
        if not isinstance(partner, dict):
            continue
        if wanted_name and _norm(partner.get("nome")) == wanted_name:
            return partner
        if wanted_domain and _norm(partner.get("dominio")) == wanted_domain:
            return partner
    return None


def _offer_payload(
    analysis: dict[str, Any],
    *,
    hardware_id: int,
    partner_id: int,
    affiliate_url: str,
) -> dict[str, Any]:
    collected = analysis.get("ofertaColetada") if isinstance(analysis.get("ofertaColetada"), dict) else {}
    price = collected.get("preco")
    try:
        price_value = round(float(price), 2)
    except (TypeError, ValueError):
        price_value = 0.0
    if price_value <= 0:
        raise ValueError("Preço do anúncio não foi identificado.")

    previous = collected.get("precoAnterior")
    try:
        previous_value = round(float(previous), 2) if previous is not None else None
    except (TypeError, ValueError):
        previous_value = None
    if previous_value is not None and previous_value <= price_value:
        previous_value = None

    original = _canonical_url(
        collected.get("urlProduto")
        or collected.get("urlOriginal")
    )
    if not original:
        raise ValueError("URL original do anúncio não foi identificada.")

    payload: dict[str, Any] = {
        "hardwareId": hardware_id,
        "parceiroId": partner_id,
        "urlOriginal": original,
        "urlAfiliada": affiliate_url,
        "preco": price_value,
    }
    if previous_value is not None:
        payload["precoAnterior"] = previous_value

    code = str(collected.get("codigoMarketplace") or "").strip()
    if code:
        payload["codigoMarketplace"] = code[:160]

    return payload


def _offer_hardware_id(offer: dict[str, Any]) -> int | None:
    value = offer.get("hardwareId")
    if isinstance(value, int):
        return value
    nested = offer.get("hardware")
    if isinstance(nested, dict) and isinstance(nested.get("id"), int):
        return nested["id"]
    return None


def _same_offer(
    offer: dict[str, Any],
    *,
    hardware_id: int,
    partner_id: int,
    original_url: str,
    marketplace_code: str | None,
) -> bool:
    partner = offer.get("parceiro")
    offer_partner_id = offer.get("parceiroId")
    if not isinstance(offer_partner_id, int) and isinstance(partner, dict):
        offer_partner_id = partner.get("id")
    if offer_partner_id != partner_id:
        return False
    if _offer_hardware_id(offer) not in {None, hardware_id}:
        return False

    existing_url = _canonical_url(offer.get("urlOriginal"))
    if existing_url and existing_url == _canonical_url(original_url):
        return True

    existing_code = str(offer.get("codigoMarketplace") or "").strip()
    return bool(marketplace_code and existing_code and _norm(existing_code) == _norm(marketplace_code))


def _hardware_record(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    nested = response.get("hardware")
    if isinstance(nested, dict):
        return nested
    return response


def _import_sync(payload: ImportAffiliateOfferRequest) -> dict[str, Any]:
    analysis = _analyze_sync(
        AnalyzeRequest(
            url=payload.urlProduto,
            urlAfiliada=payload.urlAfiliada,
            categoria=payload.categoria,
            enrich=True,
            criabytePlan=False,
            noBrowser=False,
        )
    )

    category = str(analysis.get("categoriaDetectada") or "").strip().upper()
    raw_hardware = analysis.get("payloadParcialBackend")
    if not category or not isinstance(raw_hardware, dict):
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": "Não foi possível identificar uma categoria de Hardware suportada.",
            "analise": analysis,
        }

    hardware_payload = normalize_hardware_payload_for_backend(category, raw_hardware)
    issues = registration_payload_issues(category, hardware_payload)
    if issues:
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": "A ficha técnica ainda possui campos obrigatórios não confirmados.",
            "pendencias": list(issues),
            "categoria": category,
            "hardware": {
                "nome": hardware_payload.get("nome"),
                "marca": hardware_payload.get("marca"),
                "modelo": hardware_payload.get("modelo"),
            },
        }

    affiliate_url = _canonical_url(payload.urlAfiliada)
    if not affiliate_url:
        raise HTTPException(status_code=400, detail="Link afiliado inválido.")

    client = CriaByteClient()
    client.ensure_authenticated()

    snapshot = client.snapshot()
    expected_partner = _partner_from_analysis(analysis, payload.urlProduto)
    partner = _find_partner(snapshot.get("parceiros") or [], expected_partner)
    if not partner:
        partner = client.criar_parceiro(
            {
                "nome": expected_partner["nome"],
                "dominio": expected_partner.get("dominio"),
                "site": (
                    f"https://{expected_partner['host']}"
                    if expected_partner.get("host")
                    else None
                ),
                "programaAfiliados": True,
                "observacao": "Criado automaticamente pela extensão administrativa do CriaByte.",
            }
        )

    partner_id = partner.get("id") if isinstance(partner, dict) else None
    if not isinstance(partner_id, int):
        raise CriaByteApiError("Não foi possível determinar o parceiro da oferta.")

    registration = client.cadastrar_hardware_descoberto(hardware_payload)
    hardware = _hardware_record(registration)
    hardware_id = hardware.get("id")
    if not isinstance(hardware_id, int):
        raise CriaByteApiError("O backend não retornou o ID do Hardware cadastrado/localizado.")

    offer_data = _offer_payload(
        analysis,
        hardware_id=hardware_id,
        partner_id=partner_id,
        affiliate_url=affiliate_url,
    )

    current_offers = client.listar_ofertas()
    existing_offer = next(
        (
            item
            for item in current_offers
            if isinstance(item, dict)
            and _same_offer(
                item,
                hardware_id=hardware_id,
                partner_id=partner_id,
                original_url=offer_data["urlOriginal"],
                marketplace_code=offer_data.get("codigoMarketplace"),
            )
        ),
        None,
    )

    if existing_offer:
        offer_id = existing_offer.get("id")
        if not isinstance(offer_id, int):
            raise CriaByteApiError("Oferta existente sem ID válido.")
        updated = client.atualizar_oferta(
            offer_id,
            {
                "urlAfiliada": offer_data["urlAfiliada"],
                "preco": offer_data["preco"],
                **(
                    {"precoAnterior": offer_data["precoAnterior"]}
                    if "precoAnterior" in offer_data
                    else {}
                ),
            },
        )
        return {
            "status": "OFERTA_ATUALIZADA",
            "hardwareStatus": registration.get("status"),
            "hardware": {"id": hardware_id, "nome": hardware.get("nome")},
            "parceiro": {"id": partner_id, "nome": partner.get("nome")},
            "oferta": updated,
        }

    full_hardware = _hardware_record(client.buscar_hardware(hardware_id))
    product_id = full_hardware.get("produtoId")

    if isinstance(product_id, int):
        created_offer = client.criar_oferta(offer_data)
        return {
            "status": "NOVA_OFERTA_CRIADA",
            "hardwareStatus": registration.get("status"),
            "hardware": {"id": hardware_id, "nome": full_hardware.get("nome") or hardware.get("nome")},
            "parceiro": {"id": partner_id, "nome": partner.get("nome")},
            "oferta": created_offer,
        }

    # Hardware técnico novo (ou antigo ainda sem Produto de catálogo):
    # cria o Produto e a primeira oferta na mesma transação. Mantemos o Produto
    # como rascunho para revisão antes da publicação pública.
    initial_offer = dict(offer_data)
    initial_offer.pop("hardwareId", None)
    product = client.criar_produto_de_hardware(
        hardware_id,
        {
            "publicado": False,
            "ativo": True,
            "ofertaInicial": initial_offer,
        },
    )
    return {
        "status": "HARDWARE_E_OFERTA_CRIADOS",
        "hardwareStatus": registration.get("status"),
        "hardware": {"id": hardware_id, "nome": hardware.get("nome")},
        "parceiro": {"id": partner_id, "nome": partner.get("nome")},
        "produto": product,
        "publicado": False,
        "observacao": "Novo Hardware/Produto criado como rascunho para revisão.",
    }


@router.post("/importar-oferta")
async def import_affiliate_offer(
    payload: ImportAffiliateOfferRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        return await asyncio.to_thread(_import_sync, payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CriaByteApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao importar oferta pela extensão: {exc}") from exc
