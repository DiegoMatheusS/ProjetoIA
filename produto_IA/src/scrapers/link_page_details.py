"""Complementa descrições/fichas sem substituir dados comerciais de APIs."""
from .generic_scraper import GenericScraper
from .product_page_crawler import merge_page_details, same_product
from ..utils.product_links import extract_shopee_ids, is_shopee_url


def complement_link_page(raw, url, no_browser=False):
    if raw.get("page_scraping_attempted"):
        return raw
    result = {**raw, "page_scraping_attempted": True}
    if raw.get("description") and raw.get("attributes") and raw.get("image_url"):
        return result
    address = raw.get("url_final") or url
    try:
        page = GenericScraper().collect(address, no_browser=no_browser, crawl=True)
    except Exception as exc:
        result["collection_attempts"] = [*(raw.get("collection_attempts") or []),
            {"modo": "SCRAPING_COMPLEMENTAR", "url": address, "erro": type(exc).__name__}]
        return result
    result["collection_attempts"] = [*(raw.get("collection_attempts") or []), *(page.get("collection_attempts") or [])]
    result["crawl"] = page.get("crawl") or {}
    result["requires_local_capture"] = bool(raw.get("requires_local_capture") or page.get("requires_local_capture") or page.get("blocked"))
    if not page.get("ok") or page.get("blocked"):
        return result
    if is_shopee_url(address):
        expected = extract_shopee_ids(address)
        confirmed = extract_shopee_ids(page.get("url_final") or "")
        matches = bool(all(expected) and expected == confirmed)
    else:
        matches = same_product(raw, page)
    if matches:
        result = merge_page_details(result, page)
    else:
        result["collection_attempts"].append({"modo": "SCRAPING_COMPLEMENTAR", "url": page.get("url_final"), "erro": "PRODUTO_NAO_CONFIRMADO"})
    return result
