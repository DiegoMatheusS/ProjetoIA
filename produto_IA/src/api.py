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


app = FastAPI(
    title="CriaByte Produto IA",
    version=SERVICE_VERSION,
    docs_url="/docs" if os.getenv("PRODUTO_IA_DOCS", "false").lower() in {"1", "true", "yes", "sim"} else None,
    redoc_url=None,
)

# Navegador/Playwright consome muita memória; por padrão processamos uma URL por vez.
_ANALYZE_CONCURRENCY = max(1, int(os.getenv("PRODUTO_IA_CONCURRENCY", "1")))
_analyze_semaphore = asyncio.Semaphore(_ANALYZE_CONCURRENCY)


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


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


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
        result = apply_enrichment(result)
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
        result = apply_enrichment(result)
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
