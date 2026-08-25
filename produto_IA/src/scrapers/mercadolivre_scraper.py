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
        self.session.headers.update({"Accept": "application/json"})
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

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

        # Links PDP de catálogo costumam carregar o anúncio em pdp_filters=item_id:MLB...
        for value in query.get("pdp_filters", []):
            value = unquote(value)
            match = re.search(r"item_id\s*:\s*(MLB\d+)", value, re.I)
            if match:
                item_id = match.group(1).upper()
                break

        # Alguns links trazem item_id diretamente.
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

        # Último fallback: se só existir um MLB na URL e não for /p/, trata como item.
        if not item_id and not catalog_product_id:
            match = re.search(r"MLB-?(\d{6,})", url, re.I)
            if match:
                item_id = f"MLB{match.group(1)}"

        return {"item_id": item_id, "catalog_product_id": catalog_product_id}

    def _api_get(self, path: str, params=None):
        if not self.token:
            return None, "ML_ACCESS_TOKEN_NAO_CONFIGURADO"
        url = f"{self.API_BASE}{path}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 401 and os.getenv("ML_REFRESH_TOKEN") and os.getenv("ML_CLIENT_ID") and os.getenv("ML_CLIENT_SECRET"):
                try:
                    refresh_access_token(save=True)
                    self.token = clean_text(os.getenv("ML_ACCESS_TOKEN"))
                    if self.token:
                        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                        response = self.session.get(url, params=params, timeout=self.timeout)
                except Exception as exc:
                    logger.warning(f"Não foi possível renovar o token do Mercado Livre: {exc}")
            if response.status_code in (401, 403):
                return None, f"ML_API_SEM_AUTORIZACAO_{response.status_code}"
            response.raise_for_status()
            return response.json(), None
        except requests.RequestException as exc:
            return None, f"ML_API_ERRO: {exc}"
        except ValueError:
            return None, "ML_API_RESPOSTA_NAO_JSON"

    @staticmethod
    def _attributes_text(attributes):
        lines = []
        for attr in attributes or []:
            name = clean_text(attr.get("name"))
            value = clean_text(attr.get("value_name"))
            if name and value:
                lines.append(f"{name}: {value}")
        return "\n".join(lines)

    @staticmethod
    def _pick_price(item, sale_price, prices):
        current = None
        previous = None
        currency = None

        if isinstance(sale_price, dict):
            current = to_float(sale_price.get("amount"))
            previous = to_float(sale_price.get("regular_amount"))
            currency = clean_text(sale_price.get("currency_id"))

        if current is None and isinstance(prices, dict):
            rows = prices.get("prices") or []
            promotions = [p for p in rows if p.get("type") == "promotion"]
            standards = [p for p in rows if p.get("type") == "standard"]
            if promotions:
                p = promotions[0]
                current = to_float(p.get("amount"))
                previous = to_float(p.get("regular_amount"))
                currency = clean_text(p.get("currency_id"))
            elif standards:
                p = standards[0]
                current = to_float(p.get("amount"))
                currency = clean_text(p.get("currency_id"))

        # price/base_price/original_price são apenas fallback; a API de preços é preferida.
        if current is None and isinstance(item, dict):
            current = to_float(item.get("price"))
            previous = to_float(item.get("original_price"))
            currency = clean_text(item.get("currency_id")) or currency

        return current, previous, currency or "BRL"

    def collect(self, url: str, no_browser: bool = False):
        ids = self.extract_ids(url)
        item_id = ids["item_id"]
        catalog_product_id = ids["catalog_product_id"]

        api_errors = []
        item = sale_price = prices = catalog = None

        if self.token and item_id:
            item, err = self._api_get(f"/items/{item_id}", params={"include_attributes": "all"})
            if err:
                api_errors.append(err)
            if item:
                sale_price, err = self._api_get(f"/items/{item_id}/sale_price", params={"context": "channel_marketplace"})
                if err:
                    api_errors.append(err)
                prices, err = self._api_get(f"/items/{item_id}/prices")
                if err:
                    api_errors.append(err)
                catalog_product_id = clean_text(item.get("catalog_product_id")) or catalog_product_id

        # Catálogo pode ter ficha técnica mais completa que o anúncio.
        if self.token and catalog_product_id:
            catalog, err = self._api_get(f"/products/{catalog_product_id}")
            if err:
                api_errors.append(err)

        if item or catalog:
            base = item or catalog or {}
            catalog_attrs = (catalog or {}).get("attributes") or []
            item_attrs = (item or {}).get("attributes") or []
            attrs = catalog_attrs if len(catalog_attrs) >= len(item_attrs) else item_attrs
            pictures = (catalog or {}).get("pictures") or (item or {}).get("pictures") or []
            picture = pictures[0] if pictures else {}
            image = clean_text(picture.get("secure_url") or picture.get("url"))
            price, previous, currency = self._pick_price(item, sale_price, prices)
            available_quantity = (item or {}).get("available_quantity")
            status = clean_text((item or {}).get("status") or (catalog or {}).get("status"))

            brand = first_attr(attrs, ["BRAND", "Marca", "Marca do produto"])
            model = first_attr(attrs, ["MODEL", "Modelo", "Modelo alfanumérico"])
            gtin = first_attr(attrs, ["GTIN", "EAN", "UPC", "Código universal de produto"])

            return {
                "ok": True,
                "source": "MERCADO_LIVRE_API",
                "api_used": True,
                "url_original": url,
                "url_final": clean_text((item or {}).get("permalink")) or url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "title": clean_text((catalog or {}).get("name") or (item or {}).get("title")),
                "brand": brand,
                "model": model,
                "gtin": gtin,
                "description": None,
                "image_url": image,
                "price": price,
                "previous_price": previous,
                "currency": currency,
                "available": (available_quantity > 0) if isinstance(available_quantity, (int, float)) else (status == "active" if status else None),
                "seller_id": (item or {}).get("seller_id"),
                "category_id": clean_text((item or {}).get("category_id") or (catalog or {}).get("domain_id")),
                "attributes": attrs,
                "attributes_text": self._attributes_text(attrs),
                "api_errors": list(dict.fromkeys(api_errors)),
            }

        if no_browser:
            return {
                "ok": False,
                "source": "MERCADO_LIVRE",
                "api_used": False,
                "url_original": url,
                "item_id": item_id,
                "catalog_product_id": catalog_product_id,
                "error": api_errors[0] if api_errors else ("ML_ACCESS_TOKEN_NAO_CONFIGURADO" if not self.token else "ML_API_SEM_DADOS"),
            }

        logger.warning("API do Mercado Livre indisponível; usando navegador como fallback.")
        browser_result = self.generic.collect(url)
        browser_result.update({
            "source": "MERCADO_LIVRE_BROWSER",
            "api_used": False,
            "item_id": item_id,
            "catalog_product_id": catalog_product_id,
            "api_errors": api_errors or (["ML_ACCESS_TOKEN_NAO_CONFIGURADO"] if not self.token else []),
        })
        if browser_result.get("blocked"):
            browser_result["error"] = (
                "Mercado Livre redirecionou para verificação de conta. "
                "Configure ML_ACCESS_TOKEN para usar a API oficial e evitar esse bloqueio."
            )
        return browser_result
