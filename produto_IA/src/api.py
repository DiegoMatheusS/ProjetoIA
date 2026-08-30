import asyncio
import os
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .main import build_result
from .scrapers.magazine_scraper import MagazineScraper
from .scrapers.mercadolivre_scraper import MercadoLivreScraper
from .scrapers.generic_scraper import GenericScraper


app = FastAPI(
    title="CriaByte Produto IA",
    version="14.3-railway",
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
    if payload.enrich or auto_enrich:
        from .enrichment.core import apply_enrichment
        result = apply_enrichment(result)

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
        "versao": "14.3-railway",
        "modo": "HTTP_API",
    }
    return result


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="criabyte-produto-ia", version="14.3-railway")


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
