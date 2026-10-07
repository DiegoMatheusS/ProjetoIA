"""Descoberta nas lojas e coleta limitada, sem preços de snippets de busca."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..scrapers.generic_scraper import GenericScraper
from ..scrapers.magazine_scraper import MagazineScraper
from ..scrapers.mercadolivre_scraper import MercadoLivreScraper
from ..utils.public_http import get_public_page
from ..utils.product_links import extract_shopee_ids, is_shopee_url


def is_product_url(store, url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if store == "MAGALU":
        return MagazineScraper.is_product_url(url)
    if store == "SHOPEE":
        shop_id, item_id = extract_shopee_ids(url)
        return is_shopee_url(url) and bool(shop_id and item_id)
    return (MercadoLivreScraper.is_mercadolivre(url)
            and bool(re.search(r"/(?:p/MLB\d+|MLB-?\d{6,})(?:[-/]|$)", parsed.path, re.I)))


def listing_candidates(html, base_url, store, limit):
    soup = BeautifulSoup(html or "", "html.parser")
    urls = [a.get("href") for a in soup.select("a[href]")[:1000]]

    def visit(value, depth=0):
        if depth > 12 or len(urls) > 1500:
            return
        if isinstance(value, list):
            for row in value:
                visit(row, depth + 1)
        elif isinstance(value, dict):
            for key, row in value.items():
                if key in {"url", "permalink"} and isinstance(row, str):
                    urls.append(row)
                elif isinstance(row, (dict, list)):
                    visit(row, depth + 1)

    for script in soup.select('script[type="application/ld+json"], script#__NEXT_DATA__'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
    found, seen = [], set()
    for href in urls:
        if not href:
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        if not is_product_url(store, url) or url in seen:
            continue
        seen.add(url)
        found.append({"url": url})
        if len(found) >= limit:
            break
    return found


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
            attrs = {a.get("id"): self.ml._attribute_value(a) for a in row.get("attributes") or [] if isinstance(a, dict)}
            try:
                available = float(row.get("available_quantity", 1) or 0) > 0
            except (ValueError, TypeError):
                available = False
            raw = {
                "ok": True, "title": row.get("title"), "brand": attrs.get("BRAND"),
                "model": attrs.get("MODEL"), "mpn": attrs.get("MPN"),
                "gtin": attrs.get("GTIN") or attrs.get("EAN"), "price": row.get("price"),
                "currency": row.get("currency_id"), "previous_price": row.get("original_price"),
                "available": available and row.get("status", "active") == "active",
                "url_final": row["permalink"], "item_id": row.get("id"),
                "seller_id": (row.get("seller") or {}).get("id"),
                "image_url": row.get("thumbnail"), "api_used": True, "source": "MERCADO_LIVRE_API_BUSCA",
            }
            candidates.append({"url": row["permalink"], "raw": raw})
        return candidates, "ENCONTRADO" if candidates else "NAO_ENCONTRADO"

    def _page(self, url):
        return get_public_page(self.public.session, url, timeout=6,
            deadline=min(self.deadline, time.monotonic() + 8), rate_limiter=self.public.rate_limiter)

    def listing_results(self, query, limit):
        if self.store == "MAGALU":
            url = "https://www.magazineluiza.com.br/busca/" + quote(query, safe="") + "/"
        elif self.store == "SHOPEE":
            url = "https://shopee.com.br/search?keyword=" + quote(query, safe="")
        else:
            url = "https://lista.mercadolivre.com.br/" + quote(query.replace(" ", "-"), safe="")
        try:
            page = self._page(url)
            candidates = listing_candidates(page.text, page.url, self.store, limit)
            title = BeautifulSoup(page.text, "html.parser").select_one("title")
            if not candidates and title and any(term in title.get_text().casefold() for term in ("captcha", "access denied", "acesso negado", "verificação de segurança")):
                return [], "BLOQUEADO"
            return candidates, "ENCONTRADO" if candidates else "NAO_ENCONTRADO"
        except requests.HTTPError as exc:
            return [], "BLOQUEADO" if exc.response.status_code in {401, 403, 429} else "FALHA_TEMPORARIA"
        except (requests.RequestException, ValueError, TimeoutError, OSError):
            return [], "TEMPO_LIMITE" if time.monotonic() >= self.deadline else "FALHA_TEMPORARIA"

    def collect(self, url):
        if self.ml and self.ml.token:
            return self.ml.collect(url, no_browser=True)
        try:
            page = self._page(url)
            if not is_product_url(self.store, page.url):
                return {"ok": False, "error": "REDIRECIONAMENTO_FORA_DO_PRODUTO"}
            if self.store == "MAGALU":
                return MagazineScraper()._parse_magazine_html(url, page.url, page.text)
            source = "SHOPEE_PAGINA_FALLBACK" if self.store == "SHOPEE" else "MERCADO_LIVRE_PAGINA"
            return self.public._parse_html(url, page.url, page.text, source=source)
        except requests.HTTPError as exc:
            return {"ok": False, "blocked": exc.response.status_code in {401, 403, 429}, "error": "FALHA_HTTP"}
        except (requests.RequestException, ValueError, TimeoutError, OSError):
            return {"ok": False, "error": "FALHA_COLETA"}
