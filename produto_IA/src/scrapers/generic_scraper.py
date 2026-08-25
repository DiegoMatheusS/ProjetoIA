import json
import os
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils.normalizers import clean_text, to_float
from ..utils.rate_limiter import PoliteRateLimiter


class GenericScraper:
    """Coletor conservador para uma URL individual de loja.

    Prioriza JSON-LD e pares rótulo/valor visíveis. Não faz paginação, busca em massa
    nem baixa imagens; guarda apenas a URL da imagem.
    """

    def __init__(self):
        self.timeout = int(os.getenv("TIMEOUT", "20"))
        self.max_retries = max(0, int(os.getenv("HTTP_MAX_RETRIES", "2")))
        self.rate_limiter = PoliteRateLimiter()
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
            if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
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

    @staticmethod
    def _visible_attributes(soup, product):
        pairs = []
        seen = set()

        def add(name, value):
            name = clean_text(name)
            value = clean_text(value)
            if not name or not value or len(name) > 160 or len(value) > 1000:
                return
            key = (name.casefold(), value.casefold())
            if key in seen:
                return
            seen.add(key)
            pairs.append({"id": None, "name": name, "value_name": value})

        extras = product.get("additionalProperty") or product.get("additionalProperties") or []
        if isinstance(extras, dict):
            extras = [extras]
        for item in extras if isinstance(extras, list) else []:
            if isinstance(item, dict):
                add(item.get("name"), item.get("value") or item.get("valueReference"))

        # Tabelas de ficha técnica.
        for row in soup.select("tr")[:400]:
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                add(cells[0].get_text(" ", strip=True), cells[1].get_text(" ", strip=True))
            if len(pairs) >= 250:
                break

        if len(pairs) < 250:
            for dt in soup.select("dt")[:250]:
                dd = dt.find_next_sibling("dd")
                if dd:
                    add(dt.get_text(" ", strip=True), dd.get_text(" ", strip=True))
                if len(pairs) >= 250:
                    break

        # Algumas lojas renderizam a ficha como lista/divs. Só lemos linhas
        # dentro de contêineres cujo nome sugere especificação técnica e que
        # tenham separador explícito ':'; isso evita transformar texto livre em dado.
        if len(pairs) < 250:
            containers = soup.select(
                '[class*="spec"], [id*="spec"], [class*="technical"], [id*="technical"], '
                '[class*="caracteristic"], [id*="caracteristic"], [class*="ficha"], [id*="ficha"]'
            )[:40]
            for container in containers:
                for node in container.find_all(["li", "p", "div"], recursive=True)[:300]:
                    line = clean_text(node.get_text(" ", strip=True))
                    if not line or ":" not in line or len(line) > 1200:
                        continue
                    name, value = line.split(":", 1)
                    if 1 <= len(name.strip()) <= 160 and value.strip():
                        add(name, value)
                    if len(pairs) >= 250:
                        break
                if len(pairs) >= 250:
                    break

        return pairs[:250]

    def _http_get(self, url):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait(url)
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code == 429 and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(60.0, max(3.0, float(retry_after)))
                    except (TypeError, ValueError):
                        delay = min(20.0, 3.0 * (2 ** attempt))
                    time.sleep(delay)
                    continue
                if response.status_code in (500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(min(12.0, 2.5 * (2 ** attempt)))
                    continue
                response.raise_for_status()
                return response, None
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(12.0, 2.5 * (2 ** attempt)))
                    continue
        return None, last_error

    def _parse_html(self, url, final_url, html, source="HTTP_GENERICO", blocked=False):
        soup = BeautifulSoup(html, "html.parser")
        product = self._product_json_ld(soup)
        offers = product.get("offers") if isinstance(product, dict) else None
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            offers = {}

        brand = product.get("brand") if isinstance(product, dict) else None
        if isinstance(brand, dict):
            brand = brand.get("name")
        brand = clean_text(brand) or self._meta(soup, 'meta[property="product:brand"]')

        image = product.get("image") if isinstance(product, dict) else None
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")

        title = clean_text(product.get("name") if isinstance(product, dict) else None) or self._meta(
            soup, 'meta[property="og:title"]', 'meta[name="twitter:title"]'
        )
        if not title:
            h1 = soup.select_one("h1")
            title = clean_text(h1.get_text(" ", strip=True)) if h1 else None

        image = clean_text(image) or self._meta(soup, 'meta[property="og:image"]', 'meta[name="twitter:image"]')
        if image:
            image = urljoin(final_url, image)

        price = to_float(offers.get("price")) or to_float(self._meta(
            soup, 'meta[property="product:price:amount"]', 'meta[itemprop="price"]'
        ))
        previous = to_float(offers.get("highPrice"))

        availability = clean_text(offers.get("availability"))
        available = None
        if availability:
            low = availability.casefold()
            if "instock" in low or "in_stock" in low:
                available = True
            elif "outofstock" in low or "out_of_stock" in low:
                available = False

        attributes = self._visible_attributes(soup, product)
        attributes_text = "\n".join(
            f"{item['name']}: {item['value_name']}" for item in attributes
            if item.get("name") and item.get("value_name")
        )

        by_name = {
            str(item.get("name") or "").strip().casefold(): clean_text(item.get("value_name"))
            for item in attributes
            if item.get("name") and item.get("value_name")
        }
        brand = brand or by_name.get("marca") or by_name.get("brand")
        model = clean_text(product.get("model") if isinstance(product, dict) else None) or by_name.get("modelo") or by_name.get("model")
        mpn = clean_text(product.get("mpn") if isinstance(product, dict) else None) or by_name.get("mpn") or by_name.get("part number")

        description = clean_text(product.get("description") if isinstance(product, dict) else None) or self._meta(
            soup, 'meta[name="description"]', 'meta[property="og:description"]'
        )

        gtin = None
        if isinstance(product, dict):
            gtin = product.get("gtin13") or product.get("gtin12") or product.get("gtin14") or product.get("gtin")

        return {
            "ok": bool(title),
            "source": source,
            "api_used": False,
            "url_original": url,
            "url_final": final_url,
            "title": title,
            "brand": brand,
            "model": model,
            "mpn": mpn,
            "gtin": clean_text(gtin),
            "description": description,
            "image_url": image,
            "price": price,
            "previous_price": previous,
            "price_source": "JSON_LD" if price is not None else None,
            "currency": clean_text(offers.get("priceCurrency")) or "BRL",
            "available": available,
            "seller_id": None,
            "category_id": None,
            "attributes": attributes,
            "attributes_text": attributes_text,
            "blocked": blocked,
            "error": None if title else "PAGINA_SEM_DADOS_DE_PRODUTO",
        }

    def collect(self, url, no_browser=False):
        response, error = self._http_get(url)
        if response is not None:
            result = self._parse_html(url, response.url, response.text)
            if result.get("title"):
                return result

        if no_browser:
            return {
                "ok": False,
                "source": "HTTP_GENERICO",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "error": f"ERRO_HTTP_GENERICO: {error}" if error else "PAGINA_SEM_DADOS_DE_PRODUTO",
            }

        # Um único fallback de navegador; sem navegação adicional nem paginação.
        try:
            from .browser_scraper import BrowserScraper
            browser = BrowserScraper().fetch(url)
            if browser.get("error"):
                raise RuntimeError(browser["error"])
            return self._parse_html(
                url,
                browser.get("final_url") or url,
                browser.get("html") or "",
                source="NAVEGADOR_GENERICO",
                blocked=bool(browser.get("blocked")),
            )
        except Exception as exc:
            return {
                "ok": False,
                "source": "NAVEGADOR_GENERICO",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "error": f"ERRO_FALLBACK_NAVEGADOR: {exc}",
            }
