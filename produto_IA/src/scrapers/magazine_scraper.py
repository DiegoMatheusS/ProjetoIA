import json
import os
import re
import time
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .generic_scraper import GenericScraper
from ..utils.normalizers import clean_text, to_float
from ..utils.rate_limiter import JsonDiskCache, PoliteRateLimiter


class MagazineScraper:
    """Extrator conservador para Magazine Luiza / Magalu / Magazine Você.

    Trabalha com uma URL individual. Faz no máximo uma tentativa HTTP inicial e,
    quando permitido, um único fallback com navegador. Não pagina nem percorre
    resultados de busca.
    """

    DOMAINS = ("magazineluiza.com.br", "magazinevoce.com.br", "magalu.com")

    def __init__(self):
        self.timeout = int(os.getenv("TIMEOUT", "20"))
        self.max_retries = max(0, min(2, int(os.getenv("MAGAZINE_MAX_RETRIES", "1"))))
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("MAGAZINE_MIN_DELAY_SECONDS", "2.0")),
            jitter=float(os.getenv("MAGAZINE_JITTER_SECONDS", "0.8")),
        )
        self.cache = JsonDiskCache()
        self.cache_ttl = int(os.getenv("MAGAZINE_CACHE_TTL_SECONDS", "600"))
        self.generic = GenericScraper()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        })

    @classmethod
    def is_magazine(cls, url: str):
        host = (urlparse(url or "").hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in cls.DOMAINS)

    @staticmethod
    def product_code_from_url(url: str):
        path = urlparse(url or "").path
        match = re.search(r"/p/([^/]+)/", path, re.I)
        if not match:
            match = re.search(r"/p/([^/?#]+)", path, re.I)
        return clean_text(match.group(1)) if match else None

    @staticmethod
    def seller_slug_from_url(url: str):
        values = parse_qs(urlparse(url or "").query).get("seller_id") or []
        return clean_text(values[0]) if values else None

    @staticmethod
    def _money(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value)
        match = re.search(r"(?:R\$\s*)?([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[0-9]+(?:[.,][0-9]{2})?)", text)
        return to_float(match.group(1)) if match else None

    @classmethod
    def _pix_price_from_text(cls, text: str):
        if not text:
            return None
        patterns = [
            r"R\$\s*([0-9.]+,[0-9]{2})\s*(?:\n|\s){0,30}no\s+Pix",
            r"(?:pre[cç]o\s+no\s+pix|pix)\s*[:\-]?\s*R\$\s*([0-9.]+,[0-9]{2})",
            r"Pre[cç]o\s+R\$\s*([0-9.]+,[0-9]{2})",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.I)
            if matches:
                # Em páginas Magalu o bloco de preço pode repetir o mesmo valor.
                values = [cls._money(v) for v in matches]
                values = [v for v in values if v is not None and v > 0]
                if values:
                    return values[0]
        return None

    @classmethod
    def _explicit_previous_price(cls, text: str):
        if not text:
            return None
        patterns = [
            r"(?:de|era)\s+R\$\s*([0-9.]+,[0-9]{2})\s+(?:por|agora)",
            r"pre[cç]o\s+anterior\s*[:\-]?\s*R\$\s*([0-9.]+,[0-9]{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return cls._money(match.group(1))
        return None

    @staticmethod
    def _seller_from_text(text: str):
        if not text:
            return None
        patterns = [
            r"Vendido\s+por\s+(.+?)\s+e\s+entregue\s+por",
            r"Vendido\s+e\s+entregue\s+por\s+(.+?)(?:\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                value = clean_text(match.group(1))
                if value and len(value) <= 120:
                    return value
        return None

    @staticmethod
    def _description_section(text: str):
        if not text:
            return None
        marker = re.search(r"Descri[cç][aã]o\s+e\s+ficha\s+t[eé]cnica", text, flags=re.I)
        if not marker:
            return None
        section = text[marker.end():]
        end = re.search(
            r"\n(?:Avalia[cç][oõ]es|Perguntas|Produtos\s+similares|Quem\s+viu|Veja\s+tamb[eé]m|Formas\s+de\s+pagamento)\b",
            section,
            flags=re.I,
        )
        if end:
            section = section[:end.start()]
        section = clean_text(section)
        if not section:
            return None
        return section[:12000]

    @staticmethod
    def _json_objects(soup):
        objects = []
        selectors = [
            'script[type="application/ld+json"]',
            'script[type="application/json"]',
            'script#__NEXT_DATA__',
        ]
        seen = set()
        for selector in selectors:
            for script in soup.select(selector):
                raw = (script.string or script.get_text() or "").strip()
                if not raw or len(raw) > 6_000_000:
                    continue
                fingerprint = hash(raw)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                objects.append(data)
        return objects

    @staticmethod
    def _structured_pairs(objects):
        """Extrai pares nome/valor apenas de ramos com semântica técnica."""
        pairs = []
        seen = set()
        context_words = (
            "spec", "attribute", "characteristic", "feature", "technical",
            "ficha", "detail", "property", "properties",
        )

        def add(name, value):
            name = clean_text(name)
            if isinstance(value, (dict, list)):
                return
            value = clean_text(value)
            if not name or not value or len(name) > 160 or len(value) > 1200:
                return
            key = (name.casefold(), value.casefold())
            if key in seen:
                return
            seen.add(key)
            pairs.append({"id": None, "name": name, "value_name": value})

        def walk(value, path=""):
            if isinstance(value, list):
                for item in value:
                    walk(item, path)
                return
            if not isinstance(value, dict):
                return

            path_low = path.casefold()
            in_technical_context = any(word in path_low for word in context_words)

            if in_technical_context:
                name = value.get("name") or value.get("label") or value.get("title") or value.get("key")
                candidate = (
                    value.get("value")
                    if "value" in value else
                    value.get("value_name")
                    if "value_name" in value else
                    value.get("text")
                )
                if name is not None and candidate is not None:
                    add(name, candidate)

            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(child, (dict, list)):
                    walk(child, child_path)

        for obj in objects:
            walk(obj)
        return pairs[:300]

    @staticmethod
    def _merge_attributes(*lists):
        result = []
        seen = set()
        for rows in lists:
            for row in rows or []:
                name = clean_text(row.get("name"))
                value = clean_text(row.get("value_name"))
                if not name or not value:
                    continue
                key = (name.casefold(), value.casefold())
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "id": row.get("id"),
                    "name": name,
                    "value_name": value,
                })
        return result[:350]

    def _parse_magazine_html(self, url, final_url, html, body_text=None, source="MAGALU_PAGINA"):
        generic = self.generic._parse_html(url, final_url, html, source=source)
        soup = BeautifulSoup(html, "html.parser")
        text = body_text or soup.get_text("\n", strip=True)
        objects = self._json_objects(soup)
        structured = self._structured_pairs(objects)

        attributes = self._merge_attributes(generic.get("attributes"), structured)
        attributes_text = "\n".join(
            f"{row['name']}: {row['value_name']}" for row in attributes
        )

        pix_price = self._pix_price_from_text(text)
        previous = self._explicit_previous_price(text)
        seller_name = self._seller_from_text(text)
        product_code = self.product_code_from_url(final_url or url)
        seller_slug = self.seller_slug_from_url(final_url or url) or self.seller_slug_from_url(url)

        page_description = self._description_section(text)
        description = generic.get("description")
        if page_description:
            if description and page_description.casefold() not in description.casefold():
                description = clean_text(f"{description} {page_description}")
            else:
                description = page_description or description

        available = generic.get("available")
        text_low = text.casefold()
        if any(term in text_low for term in ("produto indisponível", "produto indisponivel", "avise-me quando chegar")):
            available = False
        elif any(term in text_low for term in ("adicionar à sacola", "adicionar a sacola", "comprar agora")):
            available = True

        price = pix_price if pix_price is not None else generic.get("price")
        price_source = "MAGALU_PIX" if pix_price is not None else generic.get("price_source")

        # Não tratar o preço parcelado como "preço anterior". Só aceitamos preço
        # anterior quando há rótulo explícito ou dado estruturado já confiável.
        if previous is None:
            previous = generic.get("previous_price")
            if previous is not None and price is not None and previous <= price:
                previous = None

        result = dict(generic)
        result.update({
            "ok": bool(generic.get("title")),
            "source": source,
            "url_original": url,
            "url_final": final_url,
            "description": description,
            "price": price,
            "previous_price": previous,
            "price_source": price_source,
            "available": available,
            "seller_name": seller_name,
            "seller_slug": seller_slug,
            "marketplace_product_code": product_code,
            "attributes": attributes,
            "attributes_text": attributes_text,
            "error": None if generic.get("title") else "MAGALU_SEM_DADOS_DE_PRODUTO",
        })
        return result

    def _http_get(self, url):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait(url)
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code == 429 and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(30.0, max(4.0, float(retry_after)))
                    except (TypeError, ValueError):
                        delay = 5.0
                    time.sleep(delay)
                    continue
                if response.status_code in (500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(4.0)
                    continue
                response.raise_for_status()
                return response, None
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(4.0)
                    continue
        return None, last_error

    def collect(self, url, no_browser=False):
        cached = self.cache.get(
            url,
            namespace="magalu_result_v1",
            ttl_seconds=self.cache_ttl,
        )
        if isinstance(cached, dict):
            cached = dict(cached)
            cached["cache_hit"] = True
            return cached

        response, error = self._http_get(url)
        if response is not None:
            result = self._parse_magazine_html(url, response.url, response.text)
            if result.get("title"):
                result["cache_hit"] = False
                self.cache.set(url, result, namespace="magalu_result_v1")
                return result

        if no_browser:
            return {
                "ok": False,
                "source": "MAGALU_HTTP",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "marketplace_product_code": self.product_code_from_url(url),
                "seller_slug": self.seller_slug_from_url(url),
                "cache_hit": False,
                "error": f"MAGALU_ERRO_HTTP: {error}" if error else "MAGALU_SEM_DADOS_DE_PRODUTO",
            }

        # Somente um fallback de navegador para a mesma URL.
        try:
            from .browser_scraper import BrowserScraper
            browser = BrowserScraper().fetch(url)
            if browser.get("error"):
                raise RuntimeError(browser["error"])
            result = self._parse_magazine_html(
                url,
                browser.get("final_url") or url,
                browser.get("html") or "",
                body_text=browser.get("text") or "",
                source="MAGALU_NAVEGADOR",
            )
            result["blocked"] = bool(browser.get("blocked"))
            result["cache_hit"] = False
            if result.get("title"):
                self.cache.set(url, result, namespace="magalu_result_v1")
            return result
        except Exception as exc:
            return {
                "ok": False,
                "source": "MAGALU_NAVEGADOR",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "marketplace_product_code": self.product_code_from_url(url),
                "seller_slug": self.seller_slug_from_url(url),
                "cache_hit": False,
                "error": f"MAGALU_ERRO_FALLBACK_NAVEGADOR: {exc}",
            }
