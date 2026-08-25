import json
from bs4 import BeautifulSoup
from .browser_scraper import BrowserScraper
from ..utils.normalizers import clean_text, to_float


class GenericScraper:
    def __init__(self):
        self.browser = BrowserScraper()

    @staticmethod
    def _find_product_jsonld(soup):
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except Exception:
                continue
            stack = payload if isinstance(payload, list) else [payload]
            while stack:
                item = stack.pop(0)
                if isinstance(item, list):
                    stack.extend(item)
                    continue
                if not isinstance(item, dict):
                    continue
                t = item.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return item
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
        return None

    def collect(self, url: str):
        page = self.browser.fetch(url)
        if page.get("error"):
            return {"ok": False, "error": page["error"], "url": url}

        soup = BeautifulSoup(page.get("html") or "", "html.parser")
        product = self._find_product_jsonld(soup) or {}
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        def meta(prop=None, name=None):
            tag = soup.find("meta", attrs={"property": prop}) if prop else soup.find("meta", attrs={"name": name})
            return clean_text(tag.get("content")) if tag else None

        name = clean_text(product.get("name")) or meta(prop="og:title")
        image = product.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")
        image = clean_text(image) or meta(prop="og:image")

        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")

        return {
            "ok": True,
            "blocked": bool(page.get("blocked")),
            "url_original": url,
            "url_final": page.get("final_url"),
            "title": name,
            "brand": clean_text(brand),
            "model": clean_text(product.get("model") or product.get("mpn")),
            "gtin": clean_text(product.get("gtin13") or product.get("gtin") or product.get("sku")),
            "description": clean_text(product.get("description")) or meta(name="description"),
            "image_url": image,
            "price": to_float(offers.get("price")),
            "currency": clean_text(offers.get("priceCurrency")) or "BRL",
            "available": None,
            "attributes": [],
            "browser": {
                "blocked": bool(page.get("blocked")),
                "title": page.get("title"),
                "final_url": page.get("final_url"),
            },
        }
