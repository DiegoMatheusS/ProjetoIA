import os
import re
from urllib.parse import urlparse, parse_qs, unquote, urljoin

from bs4 import BeautifulSoup

import requests
from loguru import logger

from ..utils.normalizers import clean_text, first_attr, to_float
from ..auth.mercadolivre_oauth import refresh_access_token
from ..utils.rate_limiter import PoliteRateLimiter, JsonDiskCache


class MercadoLivreScraper:
    API_BASE = "https://api.mercadolibre.com"

    def __init__(self):
        self.token = clean_text(os.getenv("ML_ACCESS_TOKEN"))
        self.timeout = int(os.getenv("TIMEOUT", "20"))
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Accept-Language": "pt-BR",
            "User-Agent": "CriaByte-ProdutoIA/1.0",
        })
        self.api_debug = []
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("ML_MIN_DELAY_SECONDS", "1.0")),
            jitter=float(os.getenv("ML_JITTER_SECONDS", "0.35")),
        )
        self.cache = JsonDiskCache()
        self.max_retries = max(0, int(os.getenv("HTTP_MAX_RETRIES", "2")))

    @staticmethod
    def is_mercadolivre(url: str):
        host = (urlparse(url).hostname or "").lower().split(":", 1)[0]
        return (
            host == "meli.la"
            or host.endswith(".meli.la")
            or host == "mercadolivre.com.br"
            or host.endswith(".mercadolivre.com.br")
            or host == "mercadolivre.com"
            or host.endswith(".mercadolivre.com")
            or host == "mercadolibre.com"
            or host.endswith(".mercadolibre.com")
        )

    @staticmethod
    def extract_ids(url: str):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        item_id = None
        catalog_product_id = None

        # PDP de catálogo: o anúncio específico normalmente vem em pdp_filters=item_id:MLB...
        for value in query.get("pdp_filters", []):
            value = unquote(value)
            match = re.search(r"item_id\s*:\s*(MLB\d+)", value, re.I)
            if match:
                item_id = match.group(1).upper()
                break

        direct = query.get("item_id", [])
        if not item_id and direct:
            match = re.search(r"MLB\d+", unquote(direct[0]), re.I)
            if match:
                item_id = match.group(0).upper()

        # Página de produto de catálogo: /p/MLB21728506
        m_catalog = re.search(r"/p/(MLB\d+)", parsed.path, re.I)
        if m_catalog:
            catalog_product_id = m_catalog.group(1).upper()

        # Anúncio tradicional: /MLB-6740306774-...
        m_item = re.search(r"/(MLB)-?(\d{6,})(?:-|/|$)", parsed.path, re.I)
        if m_item and not item_id:
            candidate = f"{m_item.group(1).upper()}{m_item.group(2)}"
            if candidate != catalog_product_id:
                item_id = candidate

        if not item_id and not catalog_product_id:
            match = re.search(r"MLB-?(\d{6,})", url, re.I)
            if match:
                item_id = f"MLB{match.group(1)}"

        return {"item_id": item_id, "catalog_product_id": catalog_product_id}

    @staticmethod
    def _safe_error_detail(response):
        try:
            body = response.json()
            if isinstance(body, dict):
                parts = [
                    clean_text(body.get("error")),
                    clean_text(body.get("message")),
                ]
                return " - ".join(p for p in parts if p)[:300] or None
        except Exception:
            pass
        text = clean_text(response.text)
        return text[:300] if text else None

    def _headers(self, use_auth=True):
        headers = {
            "Accept": "application/json",
            "Accept-Language": "pt-BR",
            "User-Agent": "CriaByte-ProdutoIA/1.0",
        }
        if use_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _refresh_token_if_possible(self):
        if not (
            os.getenv("ML_REFRESH_TOKEN")
            and os.getenv("ML_CLIENT_ID")
            and os.getenv("ML_CLIENT_SECRET")
        ):
            return False
        try:
            refresh_access_token(save=True)
            self.token = clean_text(os.getenv("ML_ACCESS_TOKEN"))
            return bool(self.token)
        except Exception as exc:
            logger.warning(f"Não foi possível renovar o token do Mercado Livre: {exc}")
            return False

    @staticmethod
    def _cache_ttl(path: str):
        if path.endswith("/sale_price") or path.endswith("/prices"):
            return 60
        if re.search(r"/products/[^/]+/items$", path):
            return 120
        if re.search(r"/products/[^/]+$", path):
            return 3600
        return 300

    def _request_get(self, path: str, params=None, use_auth=True):
        url = f"{self.API_BASE}{path}"
        namespace = "ml_auth" if use_auth else "ml_public"
        cached = self.cache.get(
            url, params=params, namespace=namespace, ttl_seconds=self._cache_ttl(path)
        )
        if cached is not None:
            self.api_debug.append({
                "endpoint": path,
                "status": 200,
                "modo": "CACHE_AUTH" if use_auth else "CACHE_PUBLICO",
                "detalhe": None,
            })
            return cached, None

        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait(url)
                response = self.session.get(
                    url,
                    params=params,
                    headers=self._headers(use_auth=use_auth),
                    timeout=self.timeout,
                )

                if response.status_code == 401 and use_auth and self._refresh_token_if_possible():
                    self.rate_limiter.wait(url)
                    response = self.session.get(
                        url,
                        params=params,
                        headers=self._headers(use_auth=True),
                        timeout=self.timeout,
                    )

                detail = self._safe_error_detail(response)
                self.api_debug.append({
                    "endpoint": path,
                    "status": response.status_code,
                    "modo": "AUTH" if use_auth else "PUBLICO",
                    "detalhe": detail if response.status_code >= 400 else None,
                })

                if response.status_code == 429:
                    if attempt < self.max_retries:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            wait_seconds = min(60.0, max(2.0, float(retry_after)))
                        except (TypeError, ValueError):
                            wait_seconds = min(20.0, 3.0 * (2 ** attempt))
                        logger.warning(f"Mercado Livre limitou a requisição; aguardando {wait_seconds:.1f}s.")
                        import time
                        time.sleep(wait_seconds)
                        continue
                    return None, f"{path} -> HTTP 429: limite de requisições"

                if response.status_code in (500, 502, 503, 504) and attempt < self.max_retries:
                    import time
                    time.sleep(min(12.0, 2.5 * (2 ** attempt)))
                    continue

                if response.status_code in (401, 403):
                    suffix = f": {detail}" if detail else ""
                    return None, f"{path} -> HTTP {response.status_code}{suffix}"

                response.raise_for_status()
                payload = response.json()
                self.cache.set(url, payload, params=params, namespace=namespace)
                return payload, None

            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    import time
                    time.sleep(min(12.0, 2.5 * (2 ** attempt)))
                    continue
                self.api_debug.append({
                    "endpoint": path,
                    "status": None,
                    "modo": "AUTH" if use_auth else "PUBLICO",
                    "detalhe": str(exc)[:300],
                })
                return None, f"{path} -> ML_API_ERRO: {exc}"
            except ValueError:
                return None, f"{path} -> ML_API_RESPOSTA_NAO_JSON"

        return None, f"{path} -> ML_API_SEM_RESPOSTA"

    def _api_get(self, path: str, params=None, allow_public_fallback=False):
        if self.token:
            data, err = self._request_get(path, params=params, use_auth=True)
            if data is not None:
                return data, None

            # Alguns recursos de leitura pública podem responder 403 para o token
            # conforme scopes da aplicação. Para detalhe de item, tentamos leitura
            # pública antes de desistir.
            if allow_public_fallback and err and "HTTP 403" in err:
                public_data, public_err = self._request_get(
                    path, params=params, use_auth=False
                )
                if public_data is not None:
                    return public_data, None
                return None, public_err or err

            return None, err

        if allow_public_fallback:
            return self._request_get(path, params=params, use_auth=False)

        return None, "ML_ACCESS_TOKEN_NAO_CONFIGURADO"

    @staticmethod
    def _attribute_value(attr):
        value = clean_text(attr.get("value_name"))
        if value:
            return value
        values = attr.get("values") or []
        for row in values:
            value = clean_text(row.get("name") or row.get("value_name"))
            if value:
                return value
        return None

    @classmethod
    def _attributes_text(cls, attributes):
        lines = []
        for attr in attributes or []:
            name = clean_text(attr.get("name"))
            value = cls._attribute_value(attr)
            if name and value:
                lines.append(f"{name}: {value}")
        return "\n".join(lines)

    @classmethod
    def _merge_attributes(cls, *attribute_lists):
        merged = {}
        anonymous = []
        for attributes in attribute_lists:
            for attr in attributes or []:
                key = clean_text(attr.get("id")) or clean_text(attr.get("name"))
                if key:
                    # O catálogo tende a ser tecnicamente mais completo. O primeiro
                    # valor válido vence; listas seguintes apenas preenchem ausências.
                    normalized = key.casefold()
                    if normalized not in merged or not cls._attribute_value(merged[normalized]):
                        merged[normalized] = attr
                else:
                    anonymous.append(attr)
        return list(merged.values()) + anonymous

    @staticmethod
    def _catalog_description(catalog):
        short = (catalog or {}).get("short_description")
        if isinstance(short, dict):
            return clean_text(short.get("content"))
        return clean_text(short)

    @staticmethod
    def _buy_box(catalog):
        winner = (catalog or {}).get("buy_box_winner")
        return winner if isinstance(winner, dict) else {}

    @classmethod
    def _pick_price(cls, item, sale_price, prices, catalog, requested_item_id):
        current = None
        previous = None
        currency = None
        source = None

        if isinstance(sale_price, dict):
            current = to_float(sale_price.get("amount"))
            previous = to_float(sale_price.get("regular_amount"))
            currency = clean_text(sale_price.get("currency_id"))
            if current is not None:
                source = "SALE_PRICE"

        if current is None and isinstance(prices, dict):
            rows = prices.get("prices") or []
            promotions = [
                p for p in rows
                if p.get("type") == "promotion" and to_float(p.get("amount")) is not None
            ]
            standards = [
                p for p in rows
                if p.get("type") == "standard" and to_float(p.get("amount")) is not None
            ]
            if promotions:
                p = promotions[0]
                current = to_float(p.get("amount"))
                previous = to_float(p.get("regular_amount"))
                currency = clean_text(p.get("currency_id"))
                source = "PRICES_PROMOTION"
            elif standards:
                p = standards[0]
                current = to_float(p.get("amount"))
                currency = clean_text(p.get("currency_id"))
                source = "PRICES_STANDARD"

        # Fallback temporário enquanto o Mercado Livre conclui a migração dos
        # campos antigos de /items.
        if current is None and isinstance(item, dict):
            current = to_float(item.get("price"))
            previous = to_float(item.get("original_price"))
            currency = clean_text(item.get("currency_id")) or currency
            if current is not None:
                source = "ITEM_LEGACY_PRICE"

        # PDP de catálogo contém o buy_box_winner. Só usamos o preço quando o
        # winner corresponde ao anúncio solicitado, evitando trocar silenciosamente
        # o preço de um vendedor pelo de outro.
        if current is None and isinstance(catalog, dict):
            winner = cls._buy_box(catalog)
            winner_item_id = clean_text(winner.get("item_id"))
            if winner and (
                not requested_item_id
                or not winner_item_id
                or winner_item_id == requested_item_id
            ):
                current = to_float(winner.get("price"))
                previous = to_float(winner.get("original_price"))
                currency = clean_text(winner.get("currency_id")) or currency
                if current is not None:
                    source = "CATALOG_BUY_BOX"

        return current, previous, currency or "BRL", source

    @staticmethod
    def _brl_money(value):
        """Converte texto monetário brasileiro sem confundir milhar com decimal.

        Ex.: ``R$ 5.699,10`` -> 5699.10 e ``5.699`` -> 5699.00.
        """
        text = clean_text(value)
        if not text:
            return None
        text = text.replace("\xa0", " ")
        match = re.search(r"(?:R\$\s*)?([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:[,.\s]([0-9]{2}))?", text)
        if not match:
            return to_float(text)
        integer = match.group(1).replace(".", "")
        cents = match.group(2)
        try:
            return float(integer) + (int(cents) / 100 if cents else 0.0)
        except ValueError:
            return None

    @classmethod
    def _money_from_element(cls, element):
        if element is None:
            return None
        fraction = element.select_one(".andes-money-amount__fraction")
        cents = element.select_one(".andes-money-amount__cents")
        if fraction:
            raw_fraction = clean_text(fraction.get_text(" ", strip=True))
            if raw_fraction:
                digits = re.sub(r"\D", "", raw_fraction)
                if digits:
                    amount = float(int(digits))
                    cents_text = re.sub(r"\D", "", clean_text(cents.get_text(" ", strip=True)) if cents else "")
                    if cents_text:
                        amount += int(cents_text[:2].ljust(2, "0")) / 100
                    return amount
        return cls._brl_money(element.get_text(" ", strip=True))

    @classmethod
    def _ml_prices_from_html(cls, soup):
        current = None
        previous = None

        current_selectors = [
            ".ui-pdp-price__second-line .andes-money-amount:not(.andes-money-amount--previous)",
            ".ui-pdp-price__main-container .andes-money-amount:not(.andes-money-amount--previous)",
            "[data-testid='price-part'] .andes-money-amount",
            "meta[itemprop='price']",
        ]
        for selector in current_selectors:
            element = soup.select_one(selector)
            if not element:
                continue
            if element.name == "meta":
                current = cls._brl_money(element.get("content"))
            else:
                # Evita preço de parcela quando a estrutura da página mudar.
                parent_text = clean_text(element.parent.get_text(" ", strip=True) if element.parent else "") or ""
                if re.search(r"\b\d{1,2}\s*x\b|parcela|sem\s+juros", parent_text, re.I):
                    continue
                current = cls._money_from_element(element)
            if current is not None:
                break

        previous_selectors = [
            ".ui-pdp-price__original-value .andes-money-amount",
            ".ui-pdp-price__main-container .andes-money-amount--previous",
            ".andes-money-amount--previous",
        ]
        for selector in previous_selectors:
            element = soup.select_one(selector)
            if element:
                previous = cls._money_from_element(element)
                if previous is not None:
                    break

        if previous is not None and current is not None and previous <= current:
            previous = None
        return current, previous

    @classmethod
    def _ml_visible_attributes(cls, soup):
        pairs = []
        seen = set()

        def add(name, value):
            name = clean_text(name)
            value = clean_text(value)
            if not name or not value or len(name) > 180 or len(value) > 1500:
                return
            if name.casefold() == value.casefold():
                return
            key = (name.casefold(), value.casefold())
            if key in seen:
                return
            seen.add(key)
            pairs.append({"id": None, "name": name, "value_name": value})

        # Tabelas tradicionais do ML.
        for row in soup.select("tr")[:500]:
            cells = row.find_all(["th", "td"])
            texts = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
            texts = [x for x in texts if x]
            if len(texts) >= 2:
                add(texts[0], texts[1])
            if len(pairs) >= 300:
                break

        # Layout novo de ficha técnica (divs listradas/colunas).
        row_selectors = (
            ".ui-vpp-striped-specs__row, "
            ".ui-pdp-specs__table__row, "
            "[class*='striped-specs__row'], "
            "[class*='specs__table__row']"
        )
        for row in soup.select(row_selectors)[:500]:
            direct = []
            for child in row.find_all(recursive=False):
                text = clean_text(child.get_text(" ", strip=True))
                if text and text not in direct:
                    direct.append(text)
            if len(direct) >= 2:
                add(direct[0], direct[1])
                continue

            label = row.select_one(
                "th, [class*='header'], [class*='title'], [class*='label'], [class*='name']"
            )
            value = row.select_one(
                "td, [class*='column'], [class*='value'], [class*='description']"
            )
            if label and value and label is not value:
                add(label.get_text(" ", strip=True), value.get_text(" ", strip=True))

        # Pares dt/dd usados em algumas versões da página.
        for dt in soup.select("dt")[:300]:
            dd = dt.find_next_sibling("dd")
            if dd:
                add(dt.get_text(" ", strip=True), dd.get_text(" ", strip=True))

        return pairs[:300]

    @classmethod
    def _parse_ml_browser_page(cls, url, browser_payload):
        """Parser dedicado à PDP renderizada do Mercado Livre.

        O parser genérico continua como base, mas esta camada entende preço em
        ``andes-money-amount`` e a ficha técnica em ``ui-*-specs``.
        """
        from .generic_scraper import GenericScraper

        final_url = browser_payload.get("final_url") or url
        html = browser_payload.get("html") or ""
        parsed = GenericScraper()._parse_html(
            url,
            final_url,
            html,
            source="MERCADO_LIVRE_SURFSKY_CLOUD",
            blocked=bool(browser_payload.get("blocked")),
        )
        soup = BeautifulSoup(html, "html.parser")

        ml_attrs = cls._ml_visible_attributes(soup)
        attrs = cls._merge_attributes(parsed.get("attributes") or [], ml_attrs)
        attrs_text = cls._attributes_text(attrs)

        h1 = soup.select_one("h1.ui-pdp-title, h1")
        title = parsed.get("title") or (clean_text(h1.get_text(" ", strip=True)) if h1 else None)

        current, previous = cls._ml_prices_from_html(soup)
        price = current if current is not None else parsed.get("price")
        if previous is None:
            previous = parsed.get("previous_price")
        if previous is not None and price is not None and previous <= price:
            previous = None

        brand = parsed.get("brand") or first_attr(attrs, ["BRAND", "Marca", "Marca do produto"])
        model = parsed.get("model") or first_attr(attrs, [
            "MODEL", "Modelo", "Modelo alfanumérico", "Modelo alfanumerico", "PROCESSOR_MODEL"
        ])
        mpn = parsed.get("mpn") or first_attr(attrs, [
            "MPN", "MANUFACTURER_PART_NUMBER", "PART_NUMBER", "Número de peça",
            "Numero de peca", "Número de parte", "Numero de parte", "Part number"
        ])
        gtin = parsed.get("gtin") or first_attr(attrs, [
            "GTIN", "EAN", "UPC", "Código universal de produto", "Codigo universal de produto"
        ])

        description = parsed.get("description")
        desc_node = soup.select_one(
            ".ui-pdp-description__content, .ui-pdp-description p, [data-testid='description-content']"
        )
        visible_description = clean_text(desc_node.get_text(" ", strip=True)) if desc_node else None
        if visible_description and (not description or len(visible_description) > len(description)):
            description = visible_description

        image = parsed.get("image_url")
        if not image:
            image_node = soup.select_one(
                "figure img[data-zoom], .ui-pdp-gallery img, img.ui-pdp-image"
            )
            if image_node:
                image = clean_text(
                    image_node.get("data-zoom") or image_node.get("data-src") or image_node.get("src")
                )
                if image:
                    image = urljoin(final_url, image)

        body_text = clean_text(browser_payload.get("text")) or clean_text(soup.get_text(" ", strip=True)) or ""
        available = parsed.get("available")
        if available is None:
            if re.search(
                r"produto\s+indispon[ií]vel|an[uú]ncio\s+pausado|publica[cç][aã]o\s+pausada|sem\s+estoque",
                body_text,
                re.I,
            ):
                available = False
            elif re.search(
                r"adicionar\s+ao\s+carrinho|comprar\s+agora|estoque\s+dispon[ií]vel",
                body_text,
                re.I,
            ):
                available = True

        product_attributes = [
            {"nome": row.get("name"), "valor": row.get("value_name")}
            for row in attrs
            if row.get("name") and row.get("value_name")
        ]

        return {
            **parsed,
            "ok": bool(title),
            "source": "MERCADO_LIVRE_SURFSKY_CLOUD",
            "url_final": final_url,
            "title": title,
            "brand": brand,
            "model": model,
            "mpn": mpn,
            "gtin": gtin,
            "description": description,
            "image_url": image,
            "price": price,
            "previous_price": previous,
            "price_source": "MERCADO_LIVRE_PDP" if current is not None else parsed.get("price_source"),
            "currency": parsed.get("currency") or "BRL",
            "available": available,
            "attributes": attrs,
            "attributes_text": attrs_text,
            "product_attributes": product_attributes,
            "blocked": bool(browser_payload.get("blocked")),
            "error": None if title else (parsed.get("error") or "MERCADO_LIVRE_PDP_SEM_DADOS"),
        }

    @staticmethod
    def _needs_browser_enrichment(raw):
        if not raw:
            return True
        attrs = raw.get("attributes") or []
        identity_ok = bool(raw.get("brand") and (raw.get("model") or raw.get("mpn")))
        return bool(
            not raw.get("title")
            or not raw.get("image_url")
            or raw.get("price") is None
            or not identity_ok
            or len(attrs) < 6
        )

    @classmethod
    def _merge_raw_sources(cls, primary, secondary, source):
        if not primary:
            out = dict(secondary or {})
            out["source"] = source
            return out
        if not secondary:
            return dict(primary)

        out = dict(primary)
        for key in (
            "title", "brand", "model", "mpn", "gtin", "description", "image_url",
            "price", "previous_price", "price_source", "currency", "available",
            "seller_id", "category_id", "url_final",
        ):
            if out.get(key) in (None, "", []):
                value = secondary.get(key)
                if value not in (None, "", []):
                    out[key] = value

        # Uma descrição pública renderizada costuma ser mais completa que o
        # short_description do catálogo; só substituímos quando for claramente maior.
        if secondary.get("description") and len(str(secondary.get("description"))) > len(str(out.get("description") or "")):
            out["description"] = secondary.get("description")

        attrs = cls._merge_attributes(primary.get("attributes") or [], secondary.get("attributes") or [])
        out["attributes"] = attrs
        out["attributes_text"] = cls._attributes_text(attrs)
        out["product_attributes"] = [
            {"nome": row.get("name"), "valor": row.get("value_name")}
            for row in attrs
            if row.get("name") and row.get("value_name")
        ]
        out["ok"] = bool(out.get("title"))
        out["source"] = source
        out["error"] = None if out.get("title") else (secondary.get("error") or primary.get("error"))
        return out

    def collect(self, url: str, no_browser: bool = False):
        ids = self.extract_ids(url)
        item_id = ids["item_id"]
        catalog_product_id = ids["catalog_product_id"]

        # v14.14: sem ML_ACCESS_TOKEN, não gastar vários endpoints da API antes
        # de chegar ao Surfsky. A PDP pública renderizada passa a ser o caminho
        # cloud principal. Se Surfsky falhar, o fluxo antigo da API pública e
        # fallback genérico ainda continua abaixo.
        if not self.token and not no_browser:
            try:
                from .browser_scraper import BrowserScraper
                cloud_browser = BrowserScraper()
                if cloud_browser.surfsky_configured():
                    surfsky = cloud_browser.fetch_surfsky(url, interaction_profile="mercadolivre")
                    early_attempt = {
                        "modo": "SURFSKY_ORIGINAL",
                        "url": url,
                        "urlFinal": surfsky.get("final_url"),
                        "bloqueado": bool(surfsky.get("blocked")),
                        "erro": surfsky.get("error"),
                    }
                    if not surfsky.get("error") and not surfsky.get("blocked"):
                        parsed = self._parse_ml_browser_page(url, surfsky)
                        if parsed.get("title"):
                            final_ids = self.extract_ids(parsed.get("url_final") or url)
                            final_item = final_ids.get("item_id") or item_id
                            final_catalog = final_ids.get("catalog_product_id") or catalog_product_id
                            parsed.update({
                                "source": "MERCADO_LIVRE_SURFSKY_CLOUD",
                                "api_used": False,
                                "item_id": final_item,
                                "catalog_product_id": final_catalog,
                                "marketplace_product_code": final_item or final_catalog,
                                "api_errors": ["ML_ACCESS_TOKEN_NAO_CONFIGURADO"],
                                "api_debug": self.api_debug,
                                "collection_attempts": [early_attempt],
                                "surfsky": True,
                                "requires_local_capture": False,
                            })
                            return parsed
            except Exception as exc:
                logger.warning(f"Surfsky prioritário do Mercado Livre falhou: {exc}")

        api_errors = []
        item = sale_price = prices = catalog = catalog_items = catalog_offer = None

        if item_id:
            item, err = self._api_get(
                f"/items/{item_id}",
                params={"include_attributes": "all"},
                allow_public_fallback=True,
            )
            if err:
                api_errors.append(err)

            try_restricted_prices = (
                item is not None
                or os.getenv("ML_TRY_RESTRICTED_PRICE_ENDPOINTS", "false").lower() == "true"
            )
            if try_restricted_prices:
                sale_price, err = self._api_get(
                    f"/items/{item_id}/sale_price",
                    params={"context": "channel_marketplace"},
                )
                if err:
                    api_errors.append(err)

                prices, err = self._api_get(f"/items/{item_id}/prices")
                if err:
                    api_errors.append(err)

            if item:
                catalog_product_id = clean_text(item.get("catalog_product_id")) or catalog_product_id

        if catalog_product_id:
            catalog, err = self._api_get(
                f"/products/{catalog_product_id}",
                allow_public_fallback=True,
            )
            if err:
                api_errors.append(err)

            catalog_items, err = self._api_get(f"/products/{catalog_product_id}/items")
            if err:
                api_errors.append(err)
            elif isinstance(catalog_items, dict):
                rows = catalog_items.get("results") or []
                if item_id:
                    catalog_offer = next(
                        (row for row in rows if clean_text(row.get("item_id")) == item_id),
                        None,
                    )

        api_result = None
        if item or catalog or catalog_offer:
            catalog_attrs = (catalog or {}).get("attributes") or []
            item_attrs = (item or {}).get("attributes") or []
            attrs = self._merge_attributes(catalog_attrs, item_attrs)

            pictures = (catalog or {}).get("pictures") or (item or {}).get("pictures") or []
            picture = pictures[0] if pictures else {}
            image = clean_text(picture.get("secure_url") or picture.get("url"))

            price, previous, currency, price_source = self._pick_price(
                item or catalog_offer, sale_price, prices, catalog, item_id
            )
            if price_source == "ITEM_LEGACY_PRICE" and not item and catalog_offer:
                price_source = "CATALOG_ITEMS"

            winner = self._buy_box(catalog)
            winner_item_id = clean_text(winner.get("item_id"))
            winner_matches = bool(
                winner and (not item_id or not winner_item_id or winner_item_id == item_id)
            )

            commercial = item or catalog_offer or {}
            available_quantity = commercial.get("available_quantity")
            item_status = clean_text(commercial.get("status"))
            if isinstance(available_quantity, (int, float)):
                available = available_quantity > 0
            elif item_status:
                available = item_status == "active"
            elif catalog_offer:
                available = True
            elif winner_matches:
                available = True
            else:
                available = None

            brand = first_attr(attrs, ["BRAND", "Marca", "Marca do produto"])
            model = first_attr(attrs, ["MODEL", "Modelo", "Modelo alfanumérico", "PROCESSOR_MODEL"])
            mpn = first_attr(attrs, [
                "MPN", "MANUFACTURER_PART_NUMBER", "PART_NUMBER", "Número de peça",
                "Número de parte", "Part number",
            ])
            gtin = first_attr(attrs, ["GTIN", "EAN", "UPC", "Código universal de produto"])

            seller_id = (item or catalog_offer or {}).get("seller_id")
            if seller_id is None and winner_matches:
                seller_id = winner.get("seller_id")

            item_permalink = clean_text((item or catalog_offer or {}).get("permalink"))
            catalog_permalink = clean_text((catalog or {}).get("permalink"))

            api_result = {
                "ok": True,
                "source": "MERCADO_LIVRE_API",
                "api_used": True,
                "url_original": url,
                "url_final": item_permalink or catalog_permalink or url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "marketplace_product_code": item_id or catalog_product_id,
                "title": clean_text((catalog or {}).get("name") or (item or {}).get("title")),
                "brand": brand,
                "model": model,
                "mpn": mpn,
                "gtin": gtin,
                "description": self._catalog_description(catalog),
                "image_url": image,
                "price": price,
                "previous_price": previous,
                "price_source": price_source,
                "currency": currency,
                "available": available,
                "seller_id": seller_id,
                "category_id": clean_text(
                    (item or catalog_offer or {}).get("category_id") or (catalog or {}).get("domain_id")
                ),
                "attributes": attrs,
                "attributes_text": self._attributes_text(attrs),
                "product_attributes": [
                    {"nome": row.get("name"), "valor": row.get("value_name")}
                    for row in attrs if row.get("name") and row.get("value_name")
                ],
                "api_errors": list(dict.fromkeys(api_errors)),
                "api_debug": self.api_debug,
                "buy_box_item_id": winner_item_id,
                "catalog_offer_found": bool(catalog_offer),
            }

        # v14.13: não considerar "API respondeu" como sinônimo de "produto completo".
        # Se a API vier sem preço, imagem, identidade ou ficha técnica, Surfsky
        # complementa a MESMA PDP antes de devolver o resultado ao normalizador.
        if api_result and not self._needs_browser_enrichment(api_result):
            return api_result

        if no_browser:
            if api_result:
                return api_result
            return {
                "ok": False,
                "source": "MERCADO_LIVRE",
                "api_used": False,
                "url_original": url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "marketplace_product_code": item_id or catalog_product_id,
                "api_errors": list(dict.fromkeys(api_errors)),
                "api_debug": self.api_debug,
                "error": api_errors[0] if api_errors else (
                    "ML_ACCESS_TOKEN_NAO_CONFIGURADO" if not self.token else "ML_API_SEM_DADOS"
                ),
            }

        attempts = []
        surfsky_parsed = None
        try:
            from .browser_scraper import BrowserScraper

            cloud_browser = BrowserScraper()
            if cloud_browser.surfsky_configured():
                surfsky = cloud_browser.fetch_surfsky(url, interaction_profile="mercadolivre")
                attempts.append({
                    "modo": "SURFSKY_ORIGINAL",
                    "url": url,
                    "urlFinal": surfsky.get("final_url"),
                    "bloqueado": bool(surfsky.get("blocked")),
                    "erro": surfsky.get("error"),
                })

                if not surfsky.get("error") and not surfsky.get("blocked"):
                    surfsky_parsed = self._parse_ml_browser_page(url, surfsky)
                    surfsky_parsed.update({
                        "api_used": bool(api_result),
                        "item_id": item_id,
                        "catalog_product_id": catalog_product_id,
                        "marketplace_product_code": item_id or catalog_product_id,
                        "api_errors": list(dict.fromkeys(api_errors or (
                            ["ML_ACCESS_TOKEN_NAO_CONFIGURADO"] if not self.token else []
                        ))),
                        "api_debug": self.api_debug,
                        "collection_attempts": attempts,
                        "surfsky": True,
                        "requires_local_capture": False,
                    })
                    if surfsky_parsed.get("title"):
                        merged = self._merge_raw_sources(
                            api_result,
                            surfsky_parsed,
                            "MERCADO_LIVRE_API_SURFSKY" if api_result else "MERCADO_LIVRE_SURFSKY_CLOUD",
                        )
                        merged.update({
                            "api_used": bool(api_result),
                            "item_id": item_id,
                            "catalog_product_id": catalog_product_id,
                            "marketplace_product_code": item_id or catalog_product_id,
                            "api_errors": list(dict.fromkeys(api_errors or (
                                ["ML_ACCESS_TOKEN_NAO_CONFIGURADO"] if not self.token else []
                            ))),
                            "api_debug": self.api_debug,
                            "collection_attempts": attempts,
                            "surfsky": True,
                            "requires_local_capture": False,
                            "buy_box_item_id": (api_result or {}).get("buy_box_item_id"),
                            "catalog_offer_found": bool((api_result or {}).get("catalog_offer_found")),
                        })
                        return merged
            else:
                attempts.append({
                    "modo": "SURFSKY_CONFIG",
                    "url": url,
                    "bloqueado": False,
                    "erro": "SURFSKY_NAO_CONFIGURADO",
                })
        except Exception as exc:
            attempts.append({
                "modo": "SURFSKY_ORIGINAL",
                "url": url,
                "bloqueado": False,
                "erro": f"FALHA_SURFSKY_ML: {type(exc).__name__}: {exc}",
            })

        # Se a API trouxe algo utilizável, não jogamos os dados fora só porque
        # o navegador cloud falhou. O fallback genérico ainda pode preencher lacunas.
        logger.warning("Mercado Livre ainda incompleto; usando coletor genérico como último fallback.")
        try:
            from .generic_scraper import GenericScraper
            browser_result = GenericScraper().collect(url)
        except Exception as exc:
            if api_result:
                api_result["collection_attempts"] = attempts
                api_result["requires_local_capture"] = False
                return api_result
            return {
                "ok": False,
                "source": "MERCADO_LIVRE",
                "api_used": bool(self.token),
                "url_original": url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "marketplace_product_code": item_id or catalog_product_id,
                "api_errors": api_errors,
                "api_debug": self.api_debug,
                "collection_attempts": attempts,
                "error": f"FALLBACK_GENERICO_INDISPONIVEL: {exc}",
            }

        attempts.append({
            "modo": "NAVEGADOR_GENERICO",
            "url": url,
            "urlFinal": browser_result.get("url_final"),
            "bloqueado": bool(browser_result.get("blocked")),
            "erro": browser_result.get("error"),
        })

        if browser_result.get("title"):
            browser_result["marketplace_product_code"] = item_id or catalog_product_id
            merged = self._merge_raw_sources(
                api_result,
                browser_result,
                "MERCADO_LIVRE_API_BROWSER" if api_result else "MERCADO_LIVRE_BROWSER",
            )
            merged.update({
                "api_used": bool(api_result),
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "marketplace_product_code": item_id or catalog_product_id,
                "api_errors": api_errors or (["ML_ACCESS_TOKEN_NAO_CONFIGURADO"] if not self.token else []),
                "api_debug": self.api_debug,
                "collection_attempts": attempts,
                "requires_local_capture": bool(browser_result.get("blocked")),
            })
            return merged

        if api_result:
            api_result["collection_attempts"] = attempts
            api_result["requires_local_capture"] = False
            return api_result

        browser_result.update({
            "source": "MERCADO_LIVRE_BROWSER",
            "api_used": False,
            "item_id": item_id,
            "catalog_product_id": catalog_product_id,
            "marketplace_product_code": item_id or catalog_product_id,
            "api_errors": api_errors or (["ML_ACCESS_TOKEN_NAO_CONFIGURADO"] if not self.token else []),
            "api_debug": self.api_debug,
            "collection_attempts": attempts,
            "requires_local_capture": bool(browser_result.get("blocked")),
        })
        if browser_result.get("blocked"):
            browser_result["error"] = (
                "Mercado Livre redirecionou para verificação. "
                "A API oficial e os fallbacks cloud não forneceram os dados necessários."
            )
        return browser_result
