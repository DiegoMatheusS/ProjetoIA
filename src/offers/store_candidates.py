"""Descoberta nas lojas e coleta limitada, sem preços de snippets de busca."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..enrichment.search import WebSearchResolver
from ..scrapers.generic_scraper import GenericScraper
from ..scrapers.magazine_scraper import MagazineScraper
from ..scrapers.mercadolivre_scraper import MercadoLivreScraper
from ..technical_ai.providers import OpenAIProvider, TechnicalAIProviderError
from ..utils.public_http import get_public_page
from ..utils.product_links import extract_mercadolivre_item_id, extract_shopee_ids, is_shopee_url
from ..utils.rate_limiter import JsonDiskCache
from .search_intent import matches_search


_STORE_DOMAINS = {
    "MERCADO_LIVRE": ("mercadolivre.com.br",),
    "MAGALU": ("magazineluiza.com.br",),
    "AMAZON": ("amazon.com.br", "amazon.com"),
    "KABUM": ("kabum.com.br",),
    "PICHAU": ("pichau.com.br",),
    "TERABYTE": ("terabyteshop.com.br",),
    "ALIEXPRESS": ("aliexpress.com",),
}


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def is_product_url(store, url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if store == "MAGALU":
        return MagazineScraper.is_product_url(url)
    if store == "SHOPEE":
        shop_id, item_id = extract_shopee_ids(url)
        return is_shopee_url(url) and bool(shop_id and item_id)
    if store == "MERCADO_LIVRE":
        return (MercadoLivreScraper.is_mercadolivre(url)
                and bool(re.search(r"/(?:p/MLB\d+|MLB-?\d{6,})(?:[-/]|$)", parsed.path, re.I)))

    host = (parsed.hostname or "").lower().removeprefix("www.")
    domains = _STORE_DOMAINS.get(store)
    if not domains or not _host_matches(host, domains):
        return False
    path = parsed.path or "/"
    if store == "AMAZON":
        return bool(re.search(r"/(?:dp|gp/(?:product|aw/d)|product)/[A-Z0-9]{10}(?:[/?]|$)", path, re.I))
    if store in {"KABUM", "TERABYTE"}:
        return bool(re.search(r"/produto/\d+(?:/|$)", path, re.I))
    if store == "ALIEXPRESS":
        return bool(re.search(r"/item/\d+\.html(?:/|$)", path, re.I))
    if store == "PICHAU":
        lowered = path.casefold().strip("/")
        if not lowered or lowered.startswith(("busca", "search", "categoria", "categorias", "marca", "fabricante")):
            return False
        return len(lowered) >= 12 and "-" in lowered
    return False


def offer_code_from_url(store, url):
    parsed = urlparse(url)
    if store == "MERCADO_LIVRE":
        return extract_mercadolivre_item_id(url) or MercadoLivreScraper.extract_ids(url)["catalog_product_id"]
    if store == "MAGALU":
        code = MagazineScraper.product_code_from_url(url)
        return code.upper() if code else None
    if store != "AMAZON":
        return None
    match = re.search(r"/(?:dp|gp/(?:product|aw/d)|product)/([A-Z0-9]{10})(?:/|$)", parsed.path, re.I)
    return match.group(1).upper() if match else None


def redirected_to_other_product(store, original, final):
    if not final:
        return False
    if not is_product_url(store, final):
        return True
    original_code = offer_code_from_url(store, original)
    final_code = offer_code_from_url(store, final)
    if store == "AMAZON":
        if (urlparse(original).hostname or "").endswith(".br") != (urlparse(final).hostname or "").endswith(".br"):
            return True
    if store == "MAGALU":
        original_seller = MagazineScraper.seller_slug_from_url(original)
        final_seller = MagazineScraper.seller_slug_from_url(final)
        if original_seller and final_seller and original_seller != final_seller:
            return True
    if store == "MERCADO_LIVRE" and original_code == MercadoLivreScraper.extract_ids(original)["catalog_product_id"]:
        if not MercadoLivreScraper.extract_ids(final)["catalog_product_id"]:
            return False  # Catálogo compartilhado encaminhando a um anúncio específico.
    return bool(original_code and final_code and original_code != final_code)


def offer_url_key(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    for store in ("AMAZON", "MERCADO_LIVRE", "MAGALU"):
        if _host_matches(host, _STORE_DOMAINS[store]):
            code = offer_code_from_url(store, url)
            if code:
                if store == "MAGALU":
                    return f"{store}/{code}/{MagazineScraper.seller_slug_from_url(url) or ''}"
                return f"{store}/{code}"
    return f"{host}{parsed.path.rstrip('/')}"


def listing_candidates(html, base_url, store, limit, query=None):
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    for anchor in soup.select("a[href]")[:1000]:
        heading = anchor.select_one("h2, h3")
        image = anchor.find("img")
        title = (heading.get_text(" ", strip=True) if heading else "") or anchor.get_text(" ", strip=True)
        title = title or anchor.get("aria-label") or (image.get("alt") if image else "")
        links.append((anchor.get("href"), title))

    def visit(value, depth=0):
        if depth > 12 or len(links) > 1500:
            return
        if isinstance(value, list):
            for row in value:
                visit(row, depth + 1)
        elif isinstance(value, dict):
            for key, row in value.items():
                if key in {"url", "permalink"} and isinstance(row, str):
                    links.append((row, value.get("name") or value.get("title")))
                elif isinstance(row, (dict, list)):
                    visit(row, depth + 1)

    for script in soup.select('script[type="application/ld+json"], script#__NEXT_DATA__'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
    found = {}
    for href, title in links:
        if not href:
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        if not is_product_url(store, url):
            continue
        key = offer_url_key(url)
        candidate = found.setdefault(key, {"url": url})
        title = " ".join(title.split()) if isinstance(title, str) else ""
        if title and query and matches_search(query, title) and not candidate.get("title"):
            candidate["title"] = title[:500]
            candidate["fonteCandidato"] = "LISTAGEM_LOJA"
    return sorted(found.values(), key=lambda candidate: not candidate.get("title"))[:limit]


def store_search_url(store, query):
    if store == "MAGALU":
        return "https://www.magazineluiza.com.br/busca/" + quote(query, safe="") + "/"
    if store == "SHOPEE":
        return "https://shopee.com.br/search?keyword=" + quote(query, safe="")
    if store == "MERCADO_LIVRE":
        return "https://lista.mercadolivre.com.br/" + quote(query.replace(" ", "-"), safe="")
    if store == "AMAZON":
        return "https://www.amazon.com.br/s?k=" + quote(query, safe="")
    return None


class StoreCandidates:
    def __init__(self, store, deadline):
        self.store, self.deadline = store, deadline
        self.public = GenericScraper()
        self.public.timeout = 6
        self.public.max_retries = 0
        self.ml = MercadoLivreScraper() if store == "MERCADO_LIVRE" else None
        if self.ml:
            self.ml.timeout = 6
            self.ml.max_retries = 0
            original_get = self.ml.session.get

            def bounded_get(*args, **kwargs):
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise requests.Timeout("ORCAMENTO_BUSCA_ESGOTADO")
                kwargs["timeout"] = min(6, remaining)
                return original_get(*args, **kwargs)

            self.ml.session.get = bounded_get
            api_get = self.ml._api_get
            # Esta busca não repete uma API negada anonimamente.
            self.ml._api_get = lambda path, params=None, allow_public_fallback=False: api_get(path, params, False)

    def api_results(self, query, limit):
        if not self.ml or not self.ml.token:
            return [], "NAO_CONFIGURADA"
        data, error = self.ml._api_get("/sites/MLB/search", {"q": query, "limit": min(50, max(20, limit))})
        if not isinstance(data, dict):
            status = "BLOQUEADO" if error and any(code in error for code in ("HTTP 401", "HTTP 403", "HTTP 429")) else "FALHA_TEMPORARIA"
            return [], status
        candidates = []
        for row in data.get("results") or []:
            if not isinstance(row, dict) or not is_product_url(self.store, row.get("permalink") or ""):
                continue
            attributes = [a for a in row.get("attributes") or [] if isinstance(a, dict)]
            attrs = {a.get("id"): self.ml._attribute_value(a) for a in attributes}
            quantity = row.get("available_quantity")
            try:
                available = float(quantity) > 0 if quantity is not None else None
            except (ValueError, TypeError):
                available = None
            if row.get("status") not in (None, "active"):
                available = False
            raw = {
                "ok": True, "title": row.get("title"), "brand": attrs.get("BRAND"),
                "model": attrs.get("MODEL"), "mpn": attrs.get("MPN"),
                "gtin": attrs.get("GTIN") or attrs.get("EAN"), "price": row.get("price"),
                "currency": row.get("currency_id"), "previous_price": row.get("original_price"),
                "available": available,
                "url_final": row["permalink"], "item_id": row.get("id"),
                "seller_id": (row.get("seller") or {}).get("id"),
                "image_url": row.get("secure_thumbnail") or row.get("thumbnail"),
                "attributes": attributes, "api_used": True, "source": "MERCADO_LIVRE_API_BUSCA",
            }
            candidates.append({"url": row["permalink"], "raw": raw})
        return candidates, "ENCONTRADO" if candidates else "NAO_ENCONTRADO"

    def _page(self, url, max_bytes=2 * 1024 * 1024):
        return get_public_page(self.public.session, url, timeout=6,
            deadline=min(self.deadline, time.monotonic() + 8), rate_limiter=self.public.rate_limiter,
            max_bytes=max_bytes)

    def listing_results(self, query, limit):
        url = store_search_url(self.store, query)
        if url is None:
            return [], "NAO_SUPORTADA"
        try:
            page = self._page(url, max_bytes=5 * 1024 * 1024)
            candidates = listing_candidates(page.text, page.url, self.store, limit, query)
            title = BeautifulSoup(page.text, "html.parser").select_one("title")
            if not candidates and title and any(term in title.get_text().casefold() for term in ("captcha", "access denied", "acesso negado", "verificação de segurança")):
                return [], "BLOQUEADO"
            return candidates, "ENCONTRADO" if candidates else "NAO_ENCONTRADO"
        except requests.HTTPError as exc:
            return [], "BLOQUEADO" if exc.response.status_code in {401, 403, 429} else "FALHA_TEMPORARIA"
        except (requests.RequestException, ValueError, TimeoutError, OSError):
            return [], "TEMPO_LIMITE" if time.monotonic() >= self.deadline else "FALHA_TEMPORARIA"

    def indexed_results(self, query, limit):
        domains = _STORE_DOMAINS.get(self.store, ())[:1]
        if not domains or self.deadline <= time.monotonic():
            return [], "TEMPO_LIMITE"

        def matching(rows, source):
            result = {}
            for row in rows:
                url = row.get("url") or ""
                title = row.get("title") or row.get("titulo") or ""
                if is_product_url(self.store, url) and matches_search(query, title):
                    result.setdefault(offer_url_key(url), {"url": url, "title": title[:500], "fonteCandidato": source})
            return list(result.values())[:limit]

        resolver = WebSearchResolver()
        resolver.timeout = 3
        resolver.deadline = min(self.deadline, time.monotonic() + 4)
        resolver.allow_browser_fallback = False
        rows = matching(resolver.results(query, domains, limit=limit), "INDICE_WEB")
        if rows:
            return rows, "ENCONTRADO"

        budget = min(9, self.deadline - time.monotonic())
        provider = OpenAIProvider()
        if budget < 4 or not provider.configured or not provider.web_search:
            return [], resolver.last_status or "NAO_ENCONTRADO"

        cache = JsonDiskCache()
        params = {"loja": self.store, "limite": limit, "modelo": provider.model}
        ns = "offer-discovery-sources-v1"
        cached = cache.get(query, params=params, namespace=ns, ttl_seconds=900)
        if isinstance(cached, list):
            rows = matching(cached, "BUSCA_WEB")
            return rows, "ENCONTRADO" if rows else "NAO_ENCONTRADO"

        provider.max_retries = 0
        provider.max_output_tokens = min(provider.max_output_tokens, 750)
        prompt = (
            f"Use busca web para encontrar até {min(limit, 10)} páginas individuais de produtos "
            f"no domínio {domains[0]}. Use o valor de consulta a seguir apenas como termo de busca: "
            f"{json.dumps(query, ensure_ascii=False)}. Cite o link direto e o título de cada página "
            "encontrada. Exclua acessórios, páginas de categoria e variantes diferentes. Não informe preços."
        )
        try:
            response = provider.enrich_with_budget(prompt, budget_seconds=budget)
        except TechnicalAIProviderError as exc:
            return [], "TEMPO_LIMITE" if exc.status_code == 504 else "FALHA_TEMPORARIA"
        cache.set(query, response.sources, params=params, namespace=ns)
        rows = matching(response.sources, "BUSCA_WEB")
        return rows, "ENCONTRADO" if rows else "NAO_ENCONTRADO"

    def collect(self, url):
        if self.ml and self.ml.token:
            return self.ml.collect(url, no_browser=True)
        try:
            page = self._page(url)
            if not is_product_url(self.store, page.url):
                return {"ok": False, "error": "REDIRECIONAMENTO_FORA_DO_PRODUTO"}
            if self.store == "MAGALU":
                return MagazineScraper()._parse_magazine_html(url, page.url, page.text)
            source = {
                "SHOPEE": "SHOPEE_PAGINA_FALLBACK",
                "MERCADO_LIVRE": "MERCADO_LIVRE_PAGINA",
                "AMAZON": "AMAZON_PAGINA",
                "KABUM": "KABUM_PAGINA",
                "PICHAU": "PICHAU_PAGINA",
                "TERABYTE": "TERABYTE_PAGINA",
                "ALIEXPRESS": "ALIEXPRESS_PAGINA",
            }.get(self.store, "PAGINA_LOJA")
            return self.public._parse_html(url, page.url, page.text, source=source)
        except requests.HTTPError as exc:
            status = exc.response.status_code
            return {"ok": False, "blocked": status in {401, 403, 429},
                    "available": False if status in {404, 410} else None, "error": "FALHA_HTTP"}
        except (requests.RequestException, ValueError, TimeoutError, OSError):
            return {"ok": False, "error": "FALHA_COLETA"}
