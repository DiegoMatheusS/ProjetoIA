import asyncio
import os
from typing import Any
import re
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .main import build_result
from .version import SERVICE_VERSION, INTEGRATION_ID, PROVENANCE_ID
from .scrapers.magazine_scraper import MagazineScraper
from .scrapers.mercadolivre_scraper import MercadoLivreScraper
from .scrapers.generic_scraper import GenericScraper
from .discovery.core import HardwareDiscoveryService, SUPPORTED_DISCOVERY_CATEGORIES
from .extractors.dto_normalizer import normalize_hardware_payload_for_backend, registration_payload_issues
from .extractors.backend_schemas import SCHEMAS
from .enrichment.core import technical_coverage, technical_missing_fields, technical_status
from .extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    fallback_coverage_threshold,
    merge_meta_ai_response_into_payload,
    merge_meta_ai_response_into_payload_detailed,
    should_use_meta_ai_fallback,
)
from .technical_ai.providers import TechnicalAIProviderError, get_technical_ai_provider
from .technical_ai.service import build_technical_ai_prompt, enrich_hardware_with_external_ai


app = FastAPI(
    title="CriaByte Produto IA",
    version=SERVICE_VERSION,
    docs_url="/docs" if os.getenv("PRODUTO_IA_DOCS", "false").lower() in {"1", "true", "yes", "sim"} else None,
    redoc_url=None,
)

# Navegador/Playwright consome muita memória; por padrão processamos uma URL por vez.
_ANALYZE_CONCURRENCY = max(1, int(os.getenv("PRODUTO_IA_CONCURRENCY", "1")))
_analyze_semaphore = asyncio.Semaphore(_ANALYZE_CONCURRENCY)
# Descoberta em lote também pode usar navegador/fontes externas. Mantemos fila
# separada, mas igualmente conservadora para não derrubar a Railway.
_DISCOVERY_CONCURRENCY = max(1, int(os.getenv("PRODUTO_IA_DISCOVERY_CONCURRENCY", "1")))
_discovery_semaphore = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)
_discovery_service = HardwareDiscoveryService()


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)
    enrich: bool = False
    criabytePlan: bool = False
    noBrowser: bool = False


class CaptureAnalyzeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)
    captura: dict[str, Any]
    enrich: bool = False
    criabytePlan: bool = False


class HardwareDiscoveryRequest(BaseModel):
    categoria: str = Field(min_length=3, max_length=80)
    marca: str | None = Field(default=None, max_length=120)
    consulta: str | None = Field(default=None, max_length=240)
    fontes: list[str] | None = None
    pagina: int = Field(default=1, ge=1, le=100)
    limite: int = Field(default=20, ge=1, le=50)
    # v14.20: descoberta prioriza qualidade da ficha. O catálogo encontra os
    # candidatos e, por padrão, cada candidato é detalhado/enriquecido antes de
    # ser devolvido. O cliente ainda pode desligar explicitamente para diagnóstico.
    detalhar: bool = True
    enriquecer: bool = True
    noBrowser: bool = False


class HardwareDiscoveryDetailRequest(BaseModel):
    categoria: str = Field(min_length=3, max_length=80)
    nome: str = Field(min_length=2, max_length=500)
    url: str = Field(min_length=8, max_length=4096)
    fonte: str = Field(min_length=2, max_length=80)
    marca: str | None = Field(default=None, max_length=120)
    enriquecer: bool = True
    noBrowser: bool = False


class MetaAiWhatsappEnrichmentRequest(BaseModel):
    categoria: str = Field(min_length=3, max_length=80)
    nome: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any]
    resposta: str | None = Field(default=None, max_length=30000)
    captura: dict[str, Any] | None = None
    forcar: bool = False


class TechnicalAiEnrichmentRequest(BaseModel):
    provedor: str = Field(default="GEMINI", min_length=2, max_length=40)
    categoria: str = Field(min_length=3, max_length=80)
    nome: str | None = Field(default=None, max_length=500)
    marca: str | None = Field(default=None, max_length=120)
    modelo: str | None = Field(default=None, max_length=240)
    hardwareId: int | str | None = None
    payload: dict[str, Any]
    somentePreencheLacunas: bool = True


class TechnicalAiPromptRequest(BaseModel):
    categoria: str = Field(min_length=3, max_length=80)
    nome: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any]


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _sanitize_discovery_result(category: str, result: dict[str, Any]) -> dict[str, Any]:
    """Última barreira HTTP da descoberta.

    O hardware deve continuar visível mesmo quando a geração da memória não foi
    confirmada. O payload nunca serializa ``tiposMemoriaSuportados: null`` nem
    string/array composto: quando não informado, envia ``[]``. O backend atual
    aceita esse array vazio como "não informado".
    """
    items = result.get("itens")
    if not isinstance(items, list):
        return result

    safe_items = []
    registerable = 0
    incomplete = 0
    try:
        technical_provider = get_technical_ai_provider(os.getenv("IA_TECNICA_PROVIDER", "GEMINI"))
        technical_provider_name = technical_provider.name
        technical_provider_configured = bool(technical_provider.configured)
    except TechnicalAIProviderError:
        technical_provider = None
        technical_provider_name = (os.getenv("IA_TECNICA_PROVIDER", "GEMINI") or "GEMINI").strip().upper()
        technical_provider_configured = False

    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get("payload") if isinstance(item.get("payload"), dict) else item.get("payloadHardware")
        safe = normalize_hardware_payload_for_backend(category, raw if isinstance(raw, dict) else {})
        issues = registration_payload_issues(category, safe)

        item["payload"] = safe
        item["payloadHardware"] = safe
        item["cadastravel"] = not bool(issues)
        item["cadastroBloqueado"] = bool(issues)
        item["motivosNaoCadastravel"] = list(issues)

        avisos = list(item.get("avisos") or [])
        if issues:
            incomplete += 1
            aviso = (
                "Cadastro bloqueado: falta confirmar campo obrigatório da ficha técnica. "
                "O hardware continua visível para revisão e nova tentativa de enriquecimento."
            )
            if aviso not in avisos:
                avisos.append(aviso)
        else:
            registerable += 1
        item["avisos"] = avisos

        spec_field = {
            "PROCESSADOR": "especificacaoProcessador",
            "PLACA_MAE": "especificacaoPlacaMae",
            "MEMORIA_RAM": "especificacaoMemoriaRam",
            "PLACA_VIDEO": "especificacaoPlacaVideo",
            "ARMAZENAMENTO": "especificacaoArmazenamento",
            "FONTE": "especificacaoFonte",
            "GABINETE": "especificacaoGabinete",
            "COOLER": "especificacaoCooler",
            "VENTOINHA": "especificacaoVentoinha",
        }.get(category)
        if spec_field and isinstance(safe.get(spec_field), dict):
            item["especificacoesEncontradas"] = safe[spec_field]
            coverage_input = {
                "categoriaDetectada": category,
                "especificacoesEncontradas": safe[spec_field],
            }
            current_coverage = technical_coverage(coverage_input)
            missing_fields = technical_missing_fields(coverage_input)
            fallback_recommended = should_use_meta_ai_fallback(current_coverage)
            item["iaTecnicaFallback"] = {
                "recomendado": bool(fallback_recommended),
                "provedor": technical_provider_name,
                "provedorConfigurado": technical_provider_configured,
                "somentePreencheLacunas": True,
                "coberturaAtual": round(current_coverage, 4),
                "limiarCobertura": round(fallback_coverage_threshold(), 4),
                "camposAusentes": missing_fields,
                "endpoint": "/ia-tecnica/enriquecer",
                "promptGeradoAutomaticamente": True,
            }
            item["metaAiWhatsappFallback"] = {
                "recomendado": bool(fallback_recommended),
                "fonte": "META_AI_WHATSAPP",
                "somenteQuandoPoucosDados": True,
                "coberturaAtual": round(current_coverage, 4),
                "limiarCobertura": round(fallback_coverage_threshold(), 4),
                "camposAusentes": missing_fields,
                "promptSugerido": build_meta_ai_prompt(
                    category,
                    str(safe.get("nome") or item.get("nome") or "hardware"),
                    missing_fields,
                ) if fallback_recommended else None,
            }
        safe_items.append(item)

    result["itens"] = safe_items
    result["quantidadeRetornada"] = len(safe_items)
    result["quantidadeCadastravel"] = registerable
    result["quantidadeComCadastroBloqueado"] = incomplete
    # Mantém o campo antigo apenas como diagnóstico de compatibilidade, mas não
    # v14.20.9: [] representa tipo de memória não informado; não há bloqueio por ausência.
    result["descartadosPayloadObrigatorio"] = 0
    return result


def _meta_ai_whatsapp_enrich_sync(payload: MetaAiWhatsappEnrichmentRequest) -> dict[str, Any]:
    category = payload.categoria.strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise HTTPException(status_code=400, detail="Categoria sem ficha técnica estruturada para enriquecimento")

    safe_before = normalize_hardware_payload_for_backend(category, payload.payload)
    spec_field = schema[1]
    specs_before = safe_before.get(spec_field) if isinstance(safe_before.get(spec_field), dict) else {}
    coverage_input_before = {"categoriaDetectada": category, "especificacoesEncontradas": specs_before}
    coverage_before = technical_coverage(coverage_input_before)
    missing_before = technical_missing_fields(coverage_input_before)
    status_before = technical_status(coverage_input_before)
    threshold = fallback_coverage_threshold()

    response_text = str(payload.resposta or "").strip()
    if not response_text and isinstance(payload.captura, dict):
        response_text = str(
            payload.captura.get("response_text")
            or payload.captura.get("responseText")
            or payload.captura.get("text")
            or ""
        ).strip()
    if not response_text:
        raise HTTPException(status_code=400, detail="Resposta do Meta AI vazia")

    if not payload.forcar and not should_use_meta_ai_fallback(coverage_before, threshold=threshold):
        fallback = {
            "recomendado": False,
            "fonte": "META_AI_WHATSAPP",
            "somenteQuandoPoucosDados": True,
            "coberturaAtual": round(coverage_before, 4),
            "limiarCobertura": round(threshold, 4),
            "camposAusentes": missing_before,
            "promptSugerido": None,
        }
        return {
            "utilizado": False,
            "motivo": "COBERTURA_NORMAL_SUFICIENTE",
            "fonte": "META_AI_WHATSAPP",
            "somentePreencheLacunas": True,
            "categoria": category,
            "nome": payload.nome or safe_before.get("nome"),
            "coberturaAntes": round(coverage_before, 4),
            "coberturaDepois": round(coverage_before, 4),
            "limiarCobertura": round(threshold, 4),
            "camposPreenchidos": [],
            "camposAusentes": missing_before,
            "statusFicha": status_before,
            "especificacoesInterpretadas": {},
            "payload": safe_before,
            "metaAiWhatsappFallback": fallback,
        }

    safe_after, filled, parsed_specs, conflicts = merge_meta_ai_response_into_payload_detailed(
        category, safe_before, response_text
    )
    # Última barreira DTO-safe antes de responder ao CriaByte.
    safe_after = normalize_hardware_payload_for_backend(category, safe_after)
    specs_after = safe_after.get(spec_field) if isinstance(safe_after.get(spec_field), dict) else {}
    coverage_input_after = {"categoriaDetectada": category, "especificacoesEncontradas": specs_after}
    coverage_after = technical_coverage(coverage_input_after)
    missing_after = technical_missing_fields(coverage_input_after)
    status_after = technical_status(coverage_input_after, conflicts=conflicts)
    fallback_recommended = should_use_meta_ai_fallback(coverage_after, threshold=threshold)
    fallback = {
        "recomendado": bool(fallback_recommended),
        "fonte": "META_AI_WHATSAPP",
        "somenteQuandoPoucosDados": True,
        "coberturaAtual": round(coverage_after, 4),
        "limiarCobertura": round(threshold, 4),
        "camposAusentes": missing_after,
        "promptSugerido": build_meta_ai_prompt(
            category,
            str(payload.nome or safe_after.get("nome") or "hardware"),
            missing_after,
        ) if fallback_recommended and missing_after else None,
    }
    response = {
        "utilizado": True,
        "fonte": "META_AI_WHATSAPP",
        "somentePreencheLacunas": True,
        "categoria": category,
        "nome": payload.nome or safe_after.get("nome"),
        "coberturaAntes": round(coverage_before, 4),
        "coberturaDepois": round(coverage_after, 4),
        "limiarCobertura": round(threshold, 4),
        "camposPreenchidos": filled,
        "camposAusentes": missing_after,
        "statusFicha": status_after,
        "especificacoesInterpretadas": parsed_specs,
        "payload": safe_after,
        "metaAiWhatsappFallback": fallback,
    }
    if conflicts:
        response["conflitosMetaAi"] = conflicts
    return response


def _technical_ai_enrich_sync(payload: TechnicalAiEnrichmentRequest) -> dict[str, Any]:
    category = payload.categoria.strip().upper()
    base_payload = dict(payload.payload or {})
    if payload.marca and not base_payload.get("marca"):
        base_payload["marca"] = payload.marca
    if payload.modelo and not base_payload.get("modelo"):
        base_payload["modelo"] = payload.modelo
    if payload.nome and not base_payload.get("nome"):
        base_payload["nome"] = payload.nome
    return enrich_hardware_with_external_ai(
        provider_name=payload.provedor,
        category=category,
        name=payload.nome,
        payload=base_payload,
        hardware_id=payload.hardwareId,
        only_fill_gaps=payload.somentePreencheLacunas,
    )


def _technical_ai_prompt_sync(payload: TechnicalAiPromptRequest) -> dict[str, Any]:
    category = payload.categoria.strip().upper()
    safe = normalize_hardware_payload_for_backend(category, payload.payload or {})
    prompt, missing = build_technical_ai_prompt(category, payload.nome, safe)
    provider = get_technical_ai_provider(os.getenv("IA_TECNICA_PROVIDER", "GEMINI"))
    return {
        "categoria": category,
        "nome": payload.nome or safe.get("nome"),
        "provedor": provider.name,
        "provedorConfigurado": provider.configured,
        "camposAusentes": missing,
        "prompt": prompt,
    }


def _validate_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL de produto inválida")
    return value


def _analyze_sync(payload: AnalyzeRequest) -> dict[str, Any]:
    url = _validate_url(payload.url)

    if MercadoLivreScraper.is_mercadolivre(url):
        raw = MercadoLivreScraper().collect(url, no_browser=payload.noBrowser)
    elif MagazineScraper.is_magazine(url):
        raw = MagazineScraper().collect(url, no_browser=payload.noBrowser)
    else:
        raw = GenericScraper().collect(url, no_browser=payload.noBrowser)
        raw.setdefault("source", "NAVEGADOR_GENERICO")
        raw.setdefault("api_used", False)

    result = build_result(raw, payload.categoria)

    auto_enrich = os.getenv("ENRICHMENT_AUTO", "false").strip().casefold() in {
        "1", "true", "sim", "yes"
    }
    enrichment_disabled = os.getenv("ENRICHMENT_DISABLE", "false").strip().casefold() in {
        "1", "true", "sim", "yes"
    }
    from .enrichment.core import apply_enrichment, should_auto_enrich
    mandatory_missing_enrichment = should_auto_enrich(result) and not enrichment_disabled
    if payload.enrich or auto_enrich or mandatory_missing_enrichment:
        result = apply_enrichment(result, auto_mode=not bool(payload.enrich))
        result.setdefault("enriquecimentoTecnico", {})["disparoAutomaticoPorLacunas"] = bool(mandatory_missing_enrichment)

    if payload.criabytePlan:
        from .criabyte.client import CriaByteApiError, CriaByteClient
        from .criabyte.planner import plan_with_client

        try:
            result["integracaoCriaByte"] = plan_with_client(result, CriaByteClient())
        except CriaByteApiError as exc:
            result["integracaoCriaByte"] = {
                "versao": 14,
                "modo": "CONSULTA_E_PLANEJAMENTO",
                "erro": str(exc),
                "acoesSugeridas": [],
                "aplicaAlteracoesAutomaticamente": False,
            }

    result["servicoProdutoIa"] = {
        "versao": SERVICE_VERSION,
        "modo": "HTTP_API",
        "integracao": INTEGRATION_ID,
        "proveniencia": PROVENANCE_ID,
    }
    return result


def _structured_capture_to_raw(url: str, capture: dict[str, Any]) -> dict[str, Any]:
    """Converte a captura estruturada do capturador Windows em raw interno.

    Esse caminho existe para páginas que bloqueiam IPs de datacenter. A página é
    aberta no Chrome do ADMIN, mas toda a normalização continua na Produto IA.
    """
    final_url = str(capture.get("finalUrl") or capture.get("final_url") or url).strip() or url
    title = str(capture.get("productName") or capture.get("h1") or capture.get("title") or "").strip()
    description = capture.get("description")
    brand = capture.get("brand")
    model = capture.get("model")
    mpn = capture.get("mpn")
    gtin = capture.get("gtin")

    rows = []
    for item in capture.get("attributes") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or item.get("value_name") or "").strip()
        if not name or not value:
            continue
        # Parcelamento é informação comercial, não ficha técnica.
        if re.search(r"^(?:\(Produto \+ Frete\)|\d{2}x\s+de\s+R\$|Numero de parcelas|Total$)", name, re.I):
            continue
        rows.append({"name": name, "value_name": value})

    generic_identity = {
        "title": title,
        "brand": brand,
        "model": model,
        "mpn": mpn,
    }
    brand, model, mpn = MagazineScraper._refine_identity(generic_identity, rows)
    gtin = MagazineScraper._gtin_from_attributes(rows, gtin)

    def money(value):
        try:
            if value is None or value == "":
                return None
            return float(str(value).replace("R$", "").strip().replace(".", "").replace(",", ".")) if "," in str(value) else float(value)
        except (TypeError, ValueError):
            return None

    price = money(capture.get("price"))
    previous = money(capture.get("highPrice") or capture.get("previousPrice"))
    if previous is not None and price is not None and previous <= price:
        previous = None

    availability = str(capture.get("availability") or "").casefold()
    available = None
    if availability:
        if "instock" in availability or "in stock" in availability:
            available = True
        elif "outofstock" in availability or "out of stock" in availability:
            available = False

    image = capture.get("metaImage") or capture.get("image") or capture.get("image_url")
    product_code = capture.get("sku") or MagazineScraper.product_code_from_url(final_url) or MagazineScraper.product_code_from_url(url)
    attrs_text = "\n".join(f"{x['name']}: {x['value_name']}" for x in rows)
    selected = []
    for value in capture.get("selectedVariants") or []:
        text = str(value or "").strip()
        if not text or re.search(r"^Selecionar\s+(?:imagem|vídeo|video)$", text, re.I):
            continue
        selected.append(text)

    product_attrs = MagazineScraper._product_attributes_only(rows, brand=brand, model=model, mpn=mpn)
    return {
        "ok": bool(title),
        "source": "NAVEGADOR_LOCAL_ADMIN",
        "api_used": False,
        "url_original": url,
        "url_final": final_url,
        "title": title or None,
        "brand": brand,
        "model": model,
        "mpn": mpn,
        "gtin": gtin,
        "image_url": image,
        "description": description,
        "price": price,
        "previous_price": previous,
        "price_source": "CAPTURA_LOCAL",
        "currency": capture.get("priceCurrency") or "BRL",
        "available": available,
        "marketplace_product_code": product_code,
        "attributes": rows,
        "attributes_text": attrs_text,
        "product_attributes": product_attrs,
        "selected_variants": selected,
        "kit_combo": MagazineScraper._kit_combo_info(title, rows),
        "local_capture": True,
        "blocked": False,
        "requires_local_capture": False,
        "error": None if title else "CAPTURA_LOCAL_SEM_DADOS_DE_PRODUTO",
        "collection_attempts": [{"modo": "NAVEGADOR_LOCAL_ADMIN", "url": final_url, "bloqueado": False, "erro": None}],
    }


def _analyze_capture_sync(payload: CaptureAnalyzeRequest) -> dict[str, Any]:
    url = _validate_url(payload.url)
    capture = payload.captura or {}

    if capture.get("html"):
        if MagazineScraper.is_magazine(url):
            raw = MagazineScraper().collect_from_local_capture(url, capture)
        else:
            if capture.get("blocked") or capture.get("error"):
                raw = {
                    "ok": False,
                    "source": "NAVEGADOR_LOCAL_ADMIN",
                    "api_used": False,
                    "url_original": url,
                    "url_final": capture.get("final_url") or capture.get("finalUrl") or url,
                    "local_capture": True,
                    "blocked": bool(capture.get("blocked")),
                    "error": capture.get("error") or "CAPTURA_LOCAL_INVALIDA",
                }
            else:
                raw = GenericScraper()._parse_html(
                    url,
                    capture.get("final_url") or capture.get("finalUrl") or url,
                    capture.get("html") or "",
                    source="NAVEGADOR_LOCAL_ADMIN",
                    blocked=False,
                )
                raw["local_capture"] = True
    else:
        raw = _structured_capture_to_raw(url, capture)

    result = build_result(raw, payload.categoria)
    auto_enrich = os.getenv("ENRICHMENT_AUTO", "false").strip().casefold() in {"1", "true", "sim", "yes"}
    enrichment_disabled = os.getenv("ENRICHMENT_DISABLE", "false").strip().casefold() in {"1", "true", "sim", "yes"}
    from .enrichment.core import apply_enrichment, should_auto_enrich
    mandatory_missing_enrichment = should_auto_enrich(result) and not enrichment_disabled
    if payload.enrich or auto_enrich or mandatory_missing_enrichment:
        result = apply_enrichment(result, auto_mode=not bool(payload.enrich))
        result.setdefault("enriquecimentoTecnico", {})["disparoAutomaticoPorLacunas"] = bool(mandatory_missing_enrichment)

    if payload.criabytePlan:
        from .criabyte.client import CriaByteApiError, CriaByteClient
        from .criabyte.planner import plan_with_client
        try:
            result["integracaoCriaByte"] = plan_with_client(result, CriaByteClient())
        except CriaByteApiError as exc:
            result["integracaoCriaByte"] = {
                "versao": 14,
                "modo": "CONSULTA_E_PLANEJAMENTO",
                "erro": str(exc),
                "acoesSugeridas": [],
                "aplicaAlteracoesAutomaticamente": False,
            }

    result["servicoProdutoIa"] = {"versao": SERVICE_VERSION, "modo": "CAPTURA_LOCAL_HTTP_API", "integracao": INTEGRATION_ID, "proveniencia": PROVENANCE_ID}
    return result


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="criabyte-produto-ia", version=SERVICE_VERSION)


@app.get("/descobrir-hardwares/fontes")
def descobrir_hardwares_fontes(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    return {
        **_discovery_service.source_capabilities(),
        "servicoProdutoIa": {
            "versao": SERVICE_VERSION,
            "integracao": INTEGRATION_ID,
            "proveniencia": PROVENANCE_ID,
        },
    }


@app.post("/descobrir-hardwares")
async def descobrir_hardwares(
    payload: HardwareDiscoveryRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    category = payload.categoria.strip().upper()
    if category not in SUPPORTED_DISCOVERY_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail={
                "erro": "CATEGORIA_NAO_SUPORTADA_PARA_DESCOBERTA",
                "categoria": category,
                "categoriasSuportadas": list(SUPPORTED_DISCOVERY_CATEGORIES),
            },
        )
    async with _discovery_semaphore:
        try:
            result = await asyncio.to_thread(
                _discovery_service.discover,
                category,
                payload.marca,
                payload.consulta,
                payload.fontes,
                payload.pagina,
                payload.limite,
                payload.detalhar,
                payload.enriquecer,
                payload.noBrowser,
            )
            result["servicoProdutoIa"] = {
                "versao": SERVICE_VERSION,
                "modo": "DESCOBERTA_HARDWARES",
                "integracao": INTEGRATION_ID,
                "proveniencia": PROVENANCE_ID,
            }
            return _sanitize_discovery_result(category, result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao descobrir Hardwares: {exc}") from exc


@app.post("/descobrir-hardwares/detalhar")
async def detalhar_hardware_descoberto(
    payload: HardwareDiscoveryDetailRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    category = payload.categoria.strip().upper()
    async with _discovery_semaphore:
        try:
            item = await asyncio.to_thread(
                _discovery_service.detail,
                category,
                payload.nome,
                payload.url,
                payload.fonte,
                payload.marca,
                payload.enriquecer,
                payload.noBrowser,
            )
            safe_payload = normalize_hardware_payload_for_backend(
                category,
                item.get("payload") if isinstance(item.get("payload"), dict) else item.get("payloadHardware"),
            )
            item["payload"] = safe_payload
            item["payloadHardware"] = safe_payload
            return {
                "modo": "DETALHE_HARDWARE_DESCOBERTO",
                "categoria": category,
                "item": item,
                "servicoProdutoIa": {
                    "versao": SERVICE_VERSION,
                    "modo": "DESCOBERTA_HARDWARES",
                    "integracao": INTEGRATION_ID,
                    "proveniencia": PROVENANCE_ID,
                },
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao detalhar Hardware: {exc}") from exc


@app.post("/ia-tecnica/gerar-prompt")
async def gerar_prompt_ia_tecnica(
    payload: TechnicalAiPromptRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    try:
        return await asyncio.to_thread(_technical_ai_prompt_sync, payload)
    except TechnicalAIProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"codigo": exc.code, "mensagem": exc.message}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"codigo": "ERRO_INTERNO", "mensagem": f"Falha ao gerar prompt técnico: {exc}"}) from exc


@app.post("/ia-tecnica/enriquecer")
async def enriquecer_com_ia_tecnica(
    payload: TechnicalAiEnrichmentRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    async with _analyze_semaphore:
        try:
            return await asyncio.to_thread(_technical_ai_enrich_sync, payload)
        except TechnicalAIProviderError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"codigo": exc.code, "mensagem": exc.message}) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"codigo": "ERRO_INTERNO", "mensagem": f"Falha ao enriquecer com IA técnica: {exc}"}) from exc


@app.post("/meta-ai-whatsapp/enriquecer")
async def enriquecer_com_meta_ai_whatsapp(
    payload: MetaAiWhatsappEnrichmentRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    async with _analyze_semaphore:
        try:
            return await asyncio.to_thread(_meta_ai_whatsapp_enrich_sync, payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao enriquecer com Meta AI WhatsApp: {exc}") from exc


@app.post("/analisar")
async def analisar(
    payload: AnalyzeRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    async with _analyze_semaphore:
        try:
            return await asyncio.to_thread(_analyze_sync, payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao analisar produto: {exc}") from exc


@app.post("/analisar-captura")
async def analisar_captura(
    payload: CaptureAnalyzeRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _validate_api_key(x_api_key)
    async with _analyze_semaphore:
        try:
            return await asyncio.to_thread(_analyze_capture_sync, payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao analisar captura local: {exc}") from exc
