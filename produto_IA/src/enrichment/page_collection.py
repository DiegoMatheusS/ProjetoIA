"""Coleta complementar da ficha técnica, preservando a fonte e a identidade."""
import time
from urllib.parse import urlparse

from .identity import candidate_matches_identity
from ..scrapers.product_page_crawler import merge_page_details


def complement_candidate_page(provider, url, identity, result, deadline):
    result = dict(result)
    report = {"executado": False, "crawlingLimitado": {}, "tentativas": []}
    result["coletaPagina"] = report
    # PDFs e APIs técnicas continuam nos respectivos parsers.
    if provider.name == "ICECAT" or result.get("modoColeta") == "PDF_TEXTO":
        report["motivo"] = "FONTE_ESTRUTURADA_OU_PDF"
        return result
    if result.get("ok") and all(result.get(key) for key in ("description", "image_url", "attributes")):
        report["motivo"] = "FICHA_JA_COLETADA"
        return result
    remaining = deadline - time.monotonic()
    if remaining < 0.25:
        report["motivo"] = "ORCAMENTO_COLETA_ESGOTADO"
        return result
    report["executado"] = True
    try:
        provider.generic.rate_limiter = provider.rate_limiter
        provider.generic.timeout = min(provider.timeout, remaining)
        page = provider.generic.collect(
            url, no_browser=provider.page_collection_no_browser, crawl=True,
            budget_seconds=remaining, initial_page=provider._collection_page,
        )
        report["tentativas"] = page.get("collection_attempts") or []
        report["crawlingLimitado"] = page.get("crawl") or {}
        if page.get("blocked") or not page.get("ok"):
            report["motivo"] = page.get("error") or "PAGINA_SEM_DADOS_DE_PRODUTO"
            return result
        final_url = page.get("url_final") or url
        host = (urlparse(final_url).hostname or "").lower().removeprefix("www.")
        domains = provider.search_domains(identity)
        if not domains or not any(host == domain or host.endswith("." + domain) for domain in domains):
            report["motivo"] = "REDIRECIONAMENTO_FORA_DA_FONTE"
            return result
        validation = dict(page)
        if provider.name == "FABRICANTE_OFICIAL":
            validation["brand"] = validation.get("brand") or identity.get("marca")
        heading = " ".join(str(page.get(key) or "") for key in ("title", "brand", "model", "mpn", "gtin"))
        if not candidate_matches_identity(identity, validation, heading):
            report["motivo"] = "IDENTIDADE_NAO_CONFIRMADA"
            return result
        merged = merge_page_details({**result, "url_final": result.get("url") or url}, page)
        for key in ("title", "brand", "model", "mpn", "gtin", "description", "image_url", "attributes"):
            result[key] = merged.get(key)
        result["ok"] = True
        result["erro"] = None
        result["fonte"] = provider.name
        result["url"] = final_url
        result["context_text"] = "\n".join(filter(None, [result.get("context_text"),
            page.get("description"), merged.get("attributes_text")]))[:60000]
        result["modoColeta"] = "HTTP_SCRAPING_COMPLEMENTAR"
        report["motivo"] = "DADOS_DO_MESMO_PRODUTO"
    except Exception as exc:
        report["motivo"] = type(exc).__name__
    return result
