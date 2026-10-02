import json
import os
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils.normalizers import clean_text, to_float
from ..utils.rate_limiter import JsonDiskCache, PoliteRateLimiter
from ..utils.public_http import get_public_page
from .product_page_crawler import ProductPageCrawler, merge_page_details, same_product


class GenericScraper:
    """Coletor conservador para uma URL individual de loja.

    Prioriza JSON-LD, descrição e ficha visíveis. Na importação administrativa
    pode seguir até duas páginas de detalhe do mesmo produto; guarda URLs de imagens.
    """

    def __init__(self):
        self.timeout = int(os.getenv("TIMEOUT", "20"))
        self.max_retries = max(0, int(os.getenv("HTTP_MAX_RETRIES", "2")))
        self.rate_limiter = PoliteRateLimiter()
        self.cache = JsonDiskCache()
        self._deadline = None
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
        products = []
        def find_products(value, depth=0):
            if depth > 10:
                return
            if isinstance(value, list):
                for item in value:
                    find_products(item, depth + 1)
            elif isinstance(value, dict):
                kind = value.get("@type")
                if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
                    products.append(value)
                    return
                for key in ("@graph", "mainEntity"):
                    find_products(value.get(key), depth + 1)

        for script in soup.select('script[type="application/ld+json"]'):
            try:
                find_products(json.loads(script.string or script.get_text()))
            except (ValueError, TypeError):
                continue
        canonical = soup.select_one('link[rel="canonical"]')
        if len(products) > 1 and canonical and canonical.get("href"):
            target = urlparse(canonical["href"])
            matches = []
            for product in products:
                address = product.get("url") or product.get("@id")
                if not isinstance(address, str):
                    continue
                parsed = urlparse(urljoin(canonical["href"], address))
                if (parsed.netloc, parsed.path.rstrip("/")) == (target.netloc, target.path.rstrip("/")):
                    matches.append(product)
            products = matches
        return products[0] if len(products) == 1 else {}

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
                value = item.get("value")
                if value is None:
                    value = item.get("valueReference")
                if isinstance(value, dict):
                    unit = value.get("unitText") or value.get("unitCode") or ""
                    value = f"{value.get('value', '')} {unit}".strip()
                elif value is not None and (item.get("unitText") or item.get("unitCode")):
                    value = f"{value} {item.get('unitText') or item.get('unitCode')}"
                if isinstance(value, bool):
                    value = "Yes" if value else "No"
                add(item.get("name"), str(value) if value is not None else None)

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
                    children = node.find_all(["span", "div", "strong", "b"], recursive=False)
                    if len(children) == 2 and not any(child.find(["div", "li", "p"]) for child in children):
                        add(children[0].get_text(" ", strip=True), children[1].get_text(" ", strip=True))
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

    def _http_get(self, url, same_origin=None):
        last_error = None
        deadline = self._deadline or time.monotonic() + min(30, self.timeout)
        for attempt in range(self.max_retries + 1):
            try:
                response = get_public_page(self.session, url, timeout=self.timeout,
                    deadline=deadline, rate_limiter=self.rate_limiter, same_origin=same_origin)
                return response, None
            except (requests.RequestException, ValueError, OSError, TimeoutError) as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if isinstance(exc, ValueError) or (status and status not in {429, 500, 502, 503, 504}):
                    break
                remaining = deadline - time.monotonic()
                if attempt >= self.max_retries or remaining < 3:
                    break
                time.sleep(min(2.5 * (2 ** attempt), 5, remaining))
        return None, last_error

    def _parse_html(self, url, final_url, html, source="HTTP_GENERICO", blocked=False):
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.select("nav, footer, aside, [class*='related'], [class*='recommend']"):
            node.decompose()
        product = self._product_json_ld(soup)
        heading = soup.select_one("h1, title")
        heading_text = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        blocked = blocked or (not product and any(marker in (heading_text or "").casefold() for marker in (
            "captcha", "access denied", "acesso negado", "robot check", "verify you are human",
            "verifique se", "verificação de segurança", "verificacao de seguranca",
        )))
        if blocked:
            return {"ok": False, "source": source, "api_used": False, "url_original": url,
                    "url_final": final_url, "blocked": True, "requires_local_capture": True,
                    "error": "PAGINA_BLOQUEADA", "attributes": [], "attributes_text": ""}
        offers = product.get("offers") if isinstance(product, dict) else None
        if isinstance(offers, list):
            valid = [offer for offer in offers if isinstance(offer, dict)]
            prices = {to_float(offer.get("price")) for offer in valid}
            offers = valid[0] if valid and len(prices) == 1 else {}
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
            h1 = soup.select_one('[itemprop="name"], h1')
            title = clean_text(h1.get_text(" ", strip=True)) if h1 else None

        image = clean_text(image) or self._meta(soup, 'meta[property="og:image"]', 'meta[name="twitter:image"]')
        if not image:
            element = soup.select_one('[itemprop="image"]')
            if element:
                image = clean_text(element.get("content") or element.get("src") or element.get("data-src"))
        if image:
            image = urljoin(final_url, image)

        price = to_float(offers.get("price")) or to_float(self._meta(
            soup, 'meta[property="product:price:amount"]', 'meta[property="og:price:amount"]'
        ))
        if price is None:
            element = soup.select_one('[itemprop="price"]')
            if element:
                price = to_float(element.get("content") or element.get_text(" ", strip=True))
        previous = None  # highPrice is an offer range, not a historical price.

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
        brand = brand or by_name.get("marca") or by_name.get("brand") or by_name.get("producer") or by_name.get("manufacturer")
        model = clean_text(product.get("model") if isinstance(product, dict) else None) or by_name.get("modelo") or by_name.get("model")
        mpn = clean_text(product.get("mpn") if isinstance(product, dict) else None) or by_name.get("mpn") or by_name.get("part number")

        descriptions = []
        if clean_text(product.get("description")):
            descriptions.append(BeautifulSoup(str(product["description"]), "html.parser").get_text(" ", strip=True))
        for element in soup.select('[itemprop="description"], #description, #descricao, #product-description, '
                '[data-testid="product-description"], [data-testid="description"], '
                '[class*="product-description"], [class*="description__content"]')[:20]:
            for node in element.select("script, style"):
                node.decompose()
            if text := clean_text(element.get_text(" ", strip=True)):
                descriptions.append(text)
        description = max(descriptions, key=len) if descriptions else self._meta(soup, 'meta[name="description"]', 'meta[property="og:description"]')
        description = description[:12000] if description else None

        gtin = None
        if isinstance(product, dict):
            gtin = product.get("gtin13") or product.get("gtin12") or product.get("gtin14") or product.get("gtin")
        gtin = clean_text(gtin) or by_name.get("ean") or by_name.get("gtin") or by_name.get("upc")

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
            "canonical_url": urljoin(final_url, soup.select_one('link[rel="canonical"]').get("href"))
                if soup.select_one('link[rel="canonical"][href]') else None,
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

    def collect(self, url, no_browser=False, crawl=False):
        budget = max(5, min(45, float(os.getenv("PAGE_COLLECTION_BUDGET_SECONDS", "30"))))
        self._deadline = time.monotonic() + budget
        params = {"no_browser": no_browser, "crawl": crawl}
        cached = self.cache.get(url, params=params, namespace="product-pages-v3", ttl_seconds=300)
        if cached:
            return {**cached, "cache_hit": True}
        attempts, html, result = [], "", None
        response, error = self._http_get(url)
        if response is not None:
            html = response.text
            result = self._parse_html(url, response.url, response.text)
        attempts.append({"modo": "HTTP_GENERICO", "url": url,
                         "bloqueado": bool((result or {}).get("blocked")), "erro": type(error).__name__ if error else (result or {}).get("error")})
        needs_browser = not (result or {}).get("ok") or (crawl and (not result.get("description") or not result.get("attributes")))
        if needs_browser and not no_browser and time.monotonic() + 3 < self._deadline:
            try:
                from .browser_scraper import BrowserScraper
                collector = BrowserScraper()
                collector.timeout_ms = min(collector.timeout_ms, int((self._deadline - time.monotonic() - 3) * 1000))
                browser = collector.fetch(url, public_only=True, product_details=crawl)
                parsed = self._parse_html(url, browser.get("final_url") or url,
                    browser.get("html") or "", source="NAVEGADOR_GENERICO", blocked=bool(browser.get("blocked")))
                attempts.append({"modo": "NAVEGADOR_GENERICO", "url": browser.get("final_url") or url,
                                 "bloqueado": bool(parsed.get("blocked")), "erro": browser.get("error") or parsed.get("error")})
                if not browser.get("error") and parsed.get("ok") and (not (result or {}).get("ok") or same_product(result, parsed)):
                    result = merge_page_details(result, parsed) if (result or {}).get("ok") else parsed
                    html = browser.get("html") or html
                elif parsed.get("blocked"):
                    if not result or not result.get("ok"):
                        result = parsed
                    else:
                        result["requires_local_capture"] = True
            except Exception as exc:
                attempts.append({"modo": "NAVEGADOR_GENERICO", "url": url, "bloqueado": False, "erro": type(exc).__name__})
        if not result:
            result = {"ok": False, "source": "HTTP_GENERICO", "api_used": False, "url_original": url,
                      "url_final": url, "error": type(error).__name__ if error else "PAGINA_SEM_DADOS_DE_PRODUTO"}
        if crawl and result.get("ok"):
            crawler = ProductPageCrawler(self._http_get, self._parse_html, self._deadline,
                max_pages=int(os.getenv("PAGE_CRAWL_MAX_EXTRA_PAGES", "2")))
            result = crawler.collect(result, html)
        result["collection_attempts"] = attempts
        result["page_scraping_attempted"] = bool(crawl)
        result["cache_hit"] = False
        if result.get("ok") and not result.get("blocked"):
            self.cache.set(url, result, params=params, namespace="product-pages-v3")
        return result
