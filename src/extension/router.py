from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..api import AnalyzeRequest, _analyze_sync
from ..criabyte.client import CriaByteApiError, CriaByteClient
from ..extractors.backend_schemas import CATEGORY_SLUGS, SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .payload_guard import (
    extension_registration_issues,
    sanitize_extension_hardware_payload,
)


router = APIRouter(prefix="/extensao", tags=["Extensão administrativa"])


class ImportAffiliateOfferRequest(BaseModel):
    urlProduto: str = Field(min_length=8, max_length=4096)
    urlAfiliada: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)
    precoManual: float | None = Field(
        default=None,
        gt=0,
        le=100_000_000,
    )
    dadosManuais: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MissingPriceError(ValueError):
    pass


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

_PRODUCT_FIELDS = (
    "nome",
    "marca",
    "modelo",
    "descricao",
    "mpn",
    "gtin",
    "imagemUrl",
    "imagemHoverUrl",
    "metadados",
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

_BOOLEAN_FIELD_NAMES = {
    "hdr",
    "adaptiveSync",
    "gSync",
    "freeSync",
    "bluetooth",
    "wireless",
    "cabo",
    "rgb",
    "abnt2",
    "usb",
    "hotSwap",
    "microfone",
    "cincoG",
    "nfc",
    "dualSim",
    "esim",
}

_INTEGER_HINTS = (
    "Watts",
    "Mhz",
    "Hz",
    "Gb",
    "Mb",
    "Mm",
    "Nits",
    "Gramas",
    "Dpi",
    "Portas",
    "Slots",
    "Quantidade",
)

_FLOAT_HINTS = ("Polegadas", "Ms", "Volts", "Amperes", "Percentual", "Kg", "Cm")


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _ml_item_id(value: Any) -> str | None:
    match = re.search(r"\bMLB-?(\d{6,})\b", str(value or ""), re.I)
    if not match:
        return None
    return f"MLB{match.group(1)}"


def _item_id_from_params(params: dict[str, list[str]]) -> str | None:
    for key in ("item_id", "wid"):
        for value in params.get(key, []):
            item_id = _ml_item_id(value)
            if item_id:
                return item_id

    for value in params.get("pdp_filters", []):
        match = re.search(r"item_id\s*:\s*(MLB-?\d+)", str(value), re.I)
        if match:
            return _ml_item_id(match.group(1))
    return None


def _analysis_product_url(value: str) -> str:
    """Expõe ao scraper o anúncio exato escondido no fragmento do Mercado Livre."""
    text = str(value or "").strip()
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if not (
        host == "mercadolivre.com.br"
        or host.endswith(".mercadolivre.com.br")
        or host == "mercadolivre.com"
        or host.endswith(".mercadolivre.com")
        or host == "mercadolibre.com"
        or host.endswith(".mercadolibre.com")
    ):
        return text

    query = parse_qs(parsed.query, keep_blank_values=True)
    query_item_id = _item_id_from_params(query)
    if query_item_id:
        return text

    fragment = parse_qs(parsed.fragment, keep_blank_values=True)
    fragment_item_id = _item_id_from_params(fragment)
    if not fragment_item_id:
        return text

    query["item_id"] = [fragment_item_id]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


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


def _partner_from_analysis(
    analysis: dict[str, Any],
    product_url: str,
) -> dict[str, Any]:
    source = (
        analysis.get("origemColeta")
        if isinstance(analysis.get("origemColeta"), dict)
        else {}
    )
    platform = str(source.get("plataforma") or "OUTRO_SITE").strip().upper()
    host = (
        str(source.get("host") or urlparse(product_url).hostname or "")
        .strip()
        .lower()
        or None
    )

    partner_name, default_domain = _MARKETPLACE_PARTNERS.get(
        platform,
        (
            (
                host.split(".")[-2].title()
                if host and "." in host
                else (host or "Loja")
            ),
            host,
        ),
    )
    return {
        "plataforma": platform,
        "nome": partner_name,
        "dominio": default_domain or host,
        "host": host,
    }


def _offer_payload(
    analysis: dict[str, Any],
    *,
    affiliate_url: str,
    manual_price: float | None = None,
) -> dict[str, Any]:
    collected = (
        analysis.get("ofertaColetada")
        if isinstance(analysis.get("ofertaColetada"), dict)
        else {}
    )
    price = manual_price if manual_price is not None else collected.get("preco")
    try:
        price_value = round(float(price), 2)
    except (TypeError, ValueError):
        price_value = 0.0
    if price_value <= 0:
        raise MissingPriceError("Preço do anúncio não foi identificado.")

    previous = collected.get("precoAnterior")
    try:
        previous_value = round(float(previous), 2) if previous is not None else None
    except (TypeError, ValueError):
        previous_value = None
    if previous_value is not None and previous_value <= price_value:
        previous_value = None

    original = _canonical_url(
        collected.get("urlProduto") or collected.get("urlOriginal")
    )
    if not original:
        raise ValueError("URL original do anúncio não foi identificada.")

    payload: dict[str, Any] = {
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


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _set_nested_value(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts or len(parts) > 2:
        return
    if len(parts) == 1:
        payload[parts[0]] = value
        return
    parent, child = parts
    current = payload.get(parent)
    if not isinstance(current, dict):
        current = {}
        payload[parent] = current
    current[child] = value


def _apply_manual_fields(
    category: str,
    raw_payload: dict[str, Any],
    manual_fields: dict[str, str | int | float | bool],
) -> dict[str, Any]:
    output = dict(raw_payload)
    allowed = {"nome", "marca", "modelo"}
    schema = SCHEMAS.get(category)
    if schema:
        spec_field = schema[1]
        for field in schema[2] or []:
            if spec_field:
                allowed.add(f"{spec_field}.{field}")

    for path, value in list(manual_fields.items())[:48]:
        clean_path = str(path or "").strip()
        if clean_path not in allowed or not _present(value):
            continue
        if isinstance(value, str):
            value = value.strip()[:500]
        _set_nested_value(output, clean_path, value)
    return output


def _field_type(path: str) -> str:
    name = path.rsplit(".", 1)[-1]
    if name in _BOOLEAN_FIELD_NAMES:
        return "boolean"
    if any(hint.lower() in name.lower() for hint in _INTEGER_HINTS):
        return "integer"
    if any(hint.lower() in name.lower() for hint in _FLOAT_HINTS):
        return "number"
    return "text"


def _field_descriptor(path: str) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "campo": path,
        "label": _FIELD_LABELS.get(path, path.replace(".", " › ")),
        "tipo": _field_type(path),
    }
    if path == "especificacaoFonte.formato":
        descriptor["opcoes"] = ["ATX", "SFX", "SFX_L", "TFX", "FLEX_ATX"]
    return descriptor


def _issue_path(issue: str) -> str | None:
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)", issue)
    return match.group(1) if match else None


def _missing_product_paths(
    category: str,
    raw_payload: dict[str, Any],
) -> list[str]:
    missing: list[str] = []
    for field in _REQUIRED_PRODUCT_ROOT:
        if not _present(raw_payload.get(field)):
            missing.append(field)

    schema = SCHEMAS.get(category)
    core_fields = _PRODUCT_CORE_SPECS.get(category, ())
    if schema and schema[1] and core_fields:
        spec_field = schema[1]
        specs = raw_payload.get(spec_field)
        specs = specs if isinstance(specs, dict) else {}
        for field in core_fields:
            if not _present(specs.get(field)):
                missing.append(f"{spec_field}.{field}")
    return missing


def _spec_preview(category: str, raw_payload: dict[str, Any]) -> dict[str, Any]:
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return {}
    specs = raw_payload.get(schema[1])
    if not isinstance(specs, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in schema[2] or []:
        value = specs.get(key)
        if _present(value):
            safe[key] = value
        if len(safe) >= 12:
            break
    return safe


def _preview_payload(
    category: str,
    registration_type: str,
    raw_payload: dict[str, Any],
    analysis: dict[str, Any],
    partner: dict[str, Any] | None = None,
    offer: dict[str, Any] | None = None,
    published: bool | None = None,
) -> dict[str, Any]:
    collected = (
        analysis.get("ofertaColetada")
        if isinstance(analysis.get("ofertaColetada"), dict)
        else {}
    )
    return {
        "categoria": category,
        "tipoCadastro": registration_type,
        "nome": raw_payload.get("nome"),
        "marca": raw_payload.get("marca"),
        "modelo": raw_payload.get("modelo"),
        "imagemUrl": raw_payload.get("imagemUrl"),
        "preco": (offer or {}).get("preco", collected.get("preco")),
        "precoAnterior": (offer or {}).get(
            "precoAnterior",
            collected.get("precoAnterior"),
        ),
        "parceiro": (partner or {}).get("nome"),
        "publicado": published,
        "especificacoes": _spec_preview(category, raw_payload),
    }


def _product_payload_for_backend(
    category: str,
    analysis: dict[str, Any],
    raw_payload: dict[str, Any],
) -> dict[str, Any]:
    """Monta somente campos aceitos pelo cadastro de Produto genérico."""
    schema = SCHEMAS.get(category)
    if not schema or schema[0] != "PRODUTO":
        raise ValueError(f"Categoria {category} não usa o cadastro genérico de Produto.")

    category_slug = str(
        analysis.get("categoriaSlugSugerida") or CATEGORY_SLUGS.get(category) or ""
    ).strip().lower()
    if not category_slug:
        raise ValueError("Categoria comercial do Produto não foi identificada.")

    output: dict[str, Any] = {"categoriaSlug": category_slug}
    for field in _PRODUCT_FIELDS:
        value = raw_payload.get(field)
        if _present(value):
            output[field] = value

    if not str(output.get("nome") or "").strip():
        raise ValueError("Nome do Produto não foi identificado.")

    spec_field = schema[1]
    expected_fields = set(schema[2] or [])
    if spec_field and isinstance(raw_payload.get(spec_field), dict):
        raw_specs = raw_payload[spec_field]
        safe_specs = {
            key: value
            for key, value in raw_specs.items()
            if key in expected_fields and _present(value)
        }
        if safe_specs:
            output[spec_field] = safe_specs

    return output


def _review_response(
    category: str,
    hardware_payload: dict[str, Any],
    issues: list[str],
    *,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = [path for issue in issues if (path := _issue_path(issue))]
    unique_paths = list(dict.fromkeys(paths))
    return {
        "status": "REVISAO_NECESSARIA",
        "motivo": "Alguns dados não foram identificados. Preencha os campos abaixo para continuar.",
        "pendencias": list(issues),
        "camposFaltantes": [_field_descriptor(path) for path in unique_paths],
        "categoria": category,
        "hardware": {
            "nome": hardware_payload.get("nome"),
            "marca": hardware_payload.get("marca"),
            "modelo": hardware_payload.get("modelo"),
        },
        "previa": _preview_payload(
            category,
            "HARDWARE",
            hardware_payload,
            analysis or {},
        ),
    }


def _import_sync(payload: ImportAffiliateOfferRequest) -> dict[str, Any]:
    analysis_url = _analysis_product_url(payload.urlProduto)
    analysis = _analyze_sync(
        AnalyzeRequest(
            url=analysis_url,
            urlAfiliada=payload.urlAfiliada,
            categoria=payload.categoria,
            enrich=True,
            criabytePlan=False,
            noBrowser=False,
            detalharPagina=True,
        )
    )

    category = str(analysis.get("categoriaDetectada") or "").strip().upper()
    raw_payload = analysis.get("payloadParcialBackend")
    if not category or not isinstance(raw_payload, dict):
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": "Não foi possível identificar uma categoria suportada para cadastro.",
            "analise": analysis,
        }

    raw_payload = _apply_manual_fields(category, raw_payload, payload.dadosManuais)

    registration_type = str(analysis.get("tipoCadastro") or "").strip().upper()
    if not registration_type:
        schema = SCHEMAS.get(category)
        registration_type = str(schema[0] if schema else "").upper()

    if registration_type == "HARDWARE":
        hardware_payload = normalize_hardware_payload_for_backend(
            category,
            raw_payload,
        )
        hardware_payload = sanitize_extension_hardware_payload(
            category,
            hardware_payload,
        )
        issues = extension_registration_issues(category, hardware_payload)
        if issues:
            return _review_response(
                category,
                hardware_payload,
                issues,
                analysis=analysis,
            )
        registration_payload = {"hardwarePayload": hardware_payload}
        preview_source = hardware_payload
    elif registration_type == "PRODUTO":
        missing_paths = _missing_product_paths(category, raw_payload)
        if missing_paths:
            return {
                "status": "REVISAO_NECESSARIA",
                "motivo": "Alguns dados do Produto não foram identificados. Preencha os campos abaixo para continuar.",
                "pendencias": [f"{path} ausente" for path in missing_paths],
                "camposFaltantes": [
                    _field_descriptor(path) for path in missing_paths
                ],
                "categoria": category,
                "previa": _preview_payload(
                    category,
                    registration_type,
                    raw_payload,
                    analysis,
                ),
            }
        registration_payload = {
            "produtoPayload": _product_payload_for_backend(
                category,
                analysis,
                raw_payload,
            )
        }
        preview_source = raw_payload
    else:
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": (
                f"A categoria {category} usa o fluxo {registration_type or 'desconhecido'}, "
                "que ainda não é cadastrado automaticamente por esta extensão."
            ),
            "categoria": category,
            "analise": analysis,
        }

    affiliate_url = _canonical_url(payload.urlAfiliada)
    if not affiliate_url:
        raise HTTPException(status_code=400, detail="Link afiliado inválido.")

    partner = _partner_from_analysis(analysis, payload.urlProduto)
    offer = _offer_payload(
        analysis,
        affiliate_url=affiliate_url,
        manual_price=payload.precoManual,
    )

    internal_payload = {
        **registration_payload,
        "parceiro": {
            "nome": partner["nome"],
            "dominio": partner.get("dominio"),
            "site": (
                f"https://{partner['host']}"
                if partner.get("host")
                else None
            ),
        },
        "oferta": offer,
    }

    result = CriaByteClient().importar_oferta_extensao(
        internal_payload,
        api_key=os.getenv("PRODUTO_IA_API_KEY"),
    )
    if isinstance(result, dict):
        result["previa"] = _preview_payload(
            category,
            registration_type,
            preview_source,
            analysis,
            partner=partner,
            offer=offer,
            published=bool(result.get("publicado", True)),
        )
    return result


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
            detail=f"Falha ao importar oferta pela extensão: {exc}",
        ) from exc
