import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..utils.normalizers import clean_text, to_float


class GenericScraper:
    """Coletor HTTP simples para lojas que não possuem integração específica.

    Não inventa especificações: coleta somente dados estruturados/metatags
    claramente presentes na página.
    """

    def __init__(self):
        self.timeout = 20
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })

    @staticmethod
    def _product_json_ld(soup):
        def find_product(value):
            if isinstance(value, list):
                for item in value:
                    found = find_product(item)
                    if found:
                        return found
                return None

            if not isinstance(value, dict):
                return None

            kind = value.get("@type")
            if kind == "Product" or (
                isinstance(kind, list) and "Product" in kind
            ):
                return value

            graph = value.get("@graph")
            if graph:
                found = find_product(graph)
                if found:
                    return found

            for child in value.values():
                if isinstance(child, (dict, list)):
                    found = find_product(child)
                    if found:
                        return found

            return None

        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue

            product = find_product(data)
            if product:
                return product

        return {}

    @staticmethod
    def _meta(soup, *selectors):
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                value = clean_text(element.get("content"))
                if value:
                    return value
        return None

    def collect(self, url):
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return {
                "ok": False,
                "source": "HTTP_GENERICO",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "error": f"ERRO_HTTP_GENERICO: {exc}",
            }

        soup = BeautifulSoup(response.text, "html.parser")
        product = self._product_json_ld(soup)

        offers = product.get("offers") if isinstance(product, dict) else None
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            offers = {}

        brand = product.get("brand") if isinstance(product, dict) else None
        if isinstance(brand, dict):
            brand = brand.get("name")

        image = product.get("image") if isinstance(product, dict) else None
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")

        title = (
            clean_text(product.get("name") if isinstance(product, dict) else None)
            or self._meta(
                soup,
                'meta[property="og:title"]',
                'meta[name="twitter:title"]',
            )
        )

        if not title:
            h1 = soup.select_one("h1")
            title = clean_text(h1.get_text(" ", strip=True)) if h1 else None

        image = (
            clean_text(image)
            or self._meta(
                soup,
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
            )
        )
        if image:
            image = urljoin(response.url, image)

        price = (
            to_float(offers.get("price"))
            or to_float(
                self._meta(
                    soup,
                    'meta[property="product:price:amount"]',
                    'meta[itemprop="price"]',
                )
            )
        )

        availability = clean_text(offers.get("availability"))
        available = None
        if availability:
            low = availability.casefold()
            if "instock" in low or "in_stock" in low:
                available = True
            elif "outofstock" in low or "out_of_stock" in low:
                available = False

        sku = clean_text(
            product.get("sku") if isinstance(product, dict) else None
        )
        mpn = clean_text(
            product.get("mpn") if isinstance(product, dict) else None
        )

        return {
            "ok": True,
            "source": "HTTP_GENERICO",
            "api_used": False,
            "url_original": url,
            "url_final": response.url,
            "title": title,
            "brand": clean_text(brand),
            "model": None,
            "mpn": mpn,
            "gtin": clean_text(
                product.get("gtin13")
                or product.get("gtin12")
                or product.get("gtin")
                if isinstance(product, dict)
                else None
            ),
            "description": clean_text(
                product.get("description")
                if isinstance(product, dict)
                else None
            ),
            "image_url": image,
            "price": price,
            "previous_price": None,
            "price_source": "JSON_LD" if price is not None else None,
            "currency": clean_text(offers.get("priceCurrency")) or "BRL",
            "available": available,
            "seller_id": None,
            "category_id": None,
            "attributes": [],
            "attributes_text": "",
            "sku": sku,
            "blocked": False,
            "error": None,
        }
