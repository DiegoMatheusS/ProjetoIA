import os
import re
from urllib.parse import urlparse, parse_qs, unquote

import requests
from loguru import logger

from .generic_scraper import GenericScraper
from ..utils.normalizers import clean_text, first_attr, to_float
from ..auth.mercadolivre_oauth import refresh_access_token


class MercadoLivreScraper:
    API_BASE = "https://api.mercadolibre.com"

    def __init__(self):
        self.token = clean_text(os.getenv("ML_ACCESS_TOKEN"))
        self.timeout = int(os.getenv("TIMEOUT", "20"))
        self.generic = GenericScraper()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Accept-Language": "pt-BR",
            "User-Agent": "CriaByte-ProdutoIA/1.0",
        })
        self.api_debug = []

    @staticmethod
    def is_mercadolivre(url: str):
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("mercadolivre.com.br") or host.endswith("mercadolibre.com")

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

    def _request_get(self, path: str, params=None, use_auth=True):
        url = f"{self.API_BASE}{path}"
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._headers(use_auth=use_auth),
                timeout=self.timeout,
            )

            if response.status_code == 401 and use_auth and self._refresh_token_if_possible():
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

            if response.status_code in (401, 403):
                suffix = f": {detail}" if detail else ""
                return None, f"{path} -> HTTP {response.status_code}{suffix}"

            response.raise_for_status()
            return response.json(), None

        except requests.RequestException as exc:
            self.api_debug.append({
                "endpoint": path,
                "status": None,
                "modo": "AUTH" if use_auth else "PUBLICO",
                "detalhe": str(exc)[:300],
            })
            return None, f"{path} -> ML_API_ERRO: {exc}"
        except ValueError:
            return None, f"{path} -> ML_API_RESPOSTA_NAO_JSON"

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

    def collect(self, url: str, no_browser: bool = False):
        ids = self.extract_ids(url)
        item_id = ids["item_id"]
        catalog_product_id = ids["catalog_product_id"]

        api_errors = []
        item = sale_price = prices = catalog = None

        # Detalhe do anúncio: primeiro autenticado, depois público se o token
        # não tiver escopo de leitura daquele recurso.
        if item_id:
            item, err = self._api_get(
                f"/items/{item_id}",
                params={"include_attributes": "all"},
                allow_public_fallback=True,
            )
            if err:
                api_errors.append(err)

            if item:
                # APIs novas de preço são preferidas. Se não houver permissão,
                # o item/catalog continua útil e o coletor aplica fallbacks seguros.
                sale_price, err = self._api_get(
                    f"/items/{item_id}/sale_price",
                    params={"context": "channel_marketplace"},
                )
                if err:
                    api_errors.append(err)

                prices, err = self._api_get(f"/items/{item_id}/prices")
                if err:
                    api_errors.append(err)

                catalog_product_id = (
                    clean_text(item.get("catalog_product_id"))
                    or catalog_product_id
                )

        # Produto de catálogo costuma ter a ficha técnica mais completa.
        if catalog_product_id:
            catalog, err = self._api_get(
                f"/products/{catalog_product_id}",
                allow_public_fallback=True,
            )
            if err:
                api_errors.append(err)

        if item or catalog:
            catalog_attrs = (catalog or {}).get("attributes") or []
            item_attrs = (item or {}).get("attributes") or []
            attrs = self._merge_attributes(catalog_attrs, item_attrs)

            pictures = (catalog or {}).get("pictures") or (item or {}).get("pictures") or []
            picture = pictures[0] if pictures else {}
            image = clean_text(picture.get("secure_url") or picture.get("url"))

            price, previous, currency, price_source = self._pick_price(
                item, sale_price, prices, catalog, item_id
            )

            winner = self._buy_box(catalog)
            winner_item_id = clean_text(winner.get("item_id"))
            winner_matches = bool(
                winner and (
                    not item_id
                    or not winner_item_id
                    or winner_item_id == item_id
                )
            )

            available_quantity = (item or {}).get("available_quantity")
            item_status = clean_text((item or {}).get("status"))
            if isinstance(available_quantity, (int, float)):
                available = available_quantity > 0
            elif item_status:
                available = item_status == "active"
            elif winner_matches:
                available = True
            else:
                available = None

            brand = first_attr(attrs, ["BRAND", "Marca", "Marca do produto"])
            model = first_attr(attrs, [
                "MODEL", "Modelo", "Modelo alfanumérico", "PROCESSOR_MODEL"
            ])
            mpn = first_attr(attrs, [
                "MPN",
                "MANUFACTURER_PART_NUMBER",
                "PART_NUMBER",
                "Número de peça",
                "Número de parte",
                "Part number",
            ])
            gtin = first_attr(attrs, [
                "GTIN", "EAN", "UPC", "Código universal de produto"
            ])

            seller_id = (item or {}).get("seller_id")
            if seller_id is None and winner_matches:
                seller_id = winner.get("seller_id")

            item_permalink = clean_text((item or {}).get("permalink"))
            catalog_permalink = clean_text((catalog or {}).get("permalink"))

            return {
                "ok": True,
                "source": "MERCADO_LIVRE_API",
                "api_used": True,
                "url_original": url,
                "url_final": item_permalink or catalog_permalink or url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "title": clean_text(
                    (catalog or {}).get("name") or (item or {}).get("title")
                ),
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
                    (item or {}).get("category_id") or (catalog or {}).get("domain_id")
                ),
                "attributes": attrs,
                "attributes_text": self._attributes_text(attrs),
                "api_errors": list(dict.fromkeys(api_errors)),
                "api_debug": self.api_debug,
                "buy_box_item_id": winner_item_id,
            }

        if no_browser:
            return {
                "ok": False,
                "source": "MERCADO_LIVRE",
                "api_used": False,
                "url_original": url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "api_errors": list(dict.fromkeys(api_errors)),
                "api_debug": self.api_debug,
                "error": (
                    api_errors[0]
                    if api_errors
                    else (
                        "ML_ACCESS_TOKEN_NAO_CONFIGURADO"
                        if not self.token
                        else "ML_API_SEM_DADOS"
                    )
                ),
            }

        logger.warning("API do Mercado Livre indisponível; usando navegador como fallback.")
        browser_result = self.generic.collect(url)
        browser_result.update({
            "source": "MERCADO_LIVRE_BROWSER",
            "api_used": False,
            "item_id": item_id,
            "catalog_product_id": catalog_product_id,
            "api_errors": api_errors or (
                ["ML_ACCESS_TOKEN_NAO_CONFIGURADO"] if not self.token else []
            ),
            "api_debug": self.api_debug,
        })
        if browser_result.get("blocked"):
            browser_result["error"] = (
                "Mercado Livre redirecionou para verificação de conta. "
                "A API oficial também não forneceu os dados necessários."
            )
        return browser_result
