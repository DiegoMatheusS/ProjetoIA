from __future__ import annotations

import math
import re
import time
from typing import Any
from .client import ShopeeAffiliateClient, ShopeeAffiliateError
from .relevance import normalized, search_intent, relevant_item
from ..utils.product_links import extract_shopee_ids, is_shopee_url


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized(text))
        if len(token) >= 2
    }


class ShopeeAffiliateAgent:
    """Agente comercial para preços e promoções usando a API oficial da Shopee.

    A API oficial é sempre a primeira fonte para Shopee. O agente não usa scraping
    quando o cliente está configurado e a consulta pode ser atendida pela API.
    """

    def __init__(self, client: ShopeeAffiliateClient | None = None) -> None:
        self.client = client or ShopeeAffiliateClient()

    @property
    def configured(self) -> bool:
        return self.client.configured

    @staticmethod
    def _score(item: dict[str, Any], query: str) -> float:
        wanted = _tokens(query)
        found = _tokens(item.get("nome") or "")
        overlap = len(wanted & found) / max(1, len(wanted)) if wanted else 0.0
        sales = max(0, int(item.get("vendas") or 0))
        rating = float(item.get("avaliacao") or 0)
        discount = float(item.get("descontoPercentual") or 0)
        return (
            overlap * 100
            + (100 if search_intent(query) and relevant_item(item, query, search_intent(query)) else 0)
            + min(20.0, math.log10(sales + 1) * 5)
            + min(10.0, rating * 2)
            + min(15.0, discount / 4)
        )

    def find_products(
        self,
        *,
        query: str | None = None,
        item_id: int | None = None,
        shop_id: int | None = None,
        limit: int = 20,
        promotions_only: bool = False,
        sort_type: int = 1,
        list_type: int = 0,
    ) -> dict[str, Any]:
        normalized_query = str(query or "").strip()
        requested_limit = max(1, min(100, int(limit)))
        intent = search_intent(normalized_query) if item_id is None else None
        page_size = min(50, max(requested_limit, 50 if intent or promotions_only else requested_limit))
        deadline = time.monotonic() + 24
        items, seen, warnings = [], set(), []
        page_info, pages, discarded = {}, 0, 0
        generic_aliases = {
            'placa de video': ['RTX', 'Radeon RX'], 'placas de video': ['RTX', 'Radeon RX'], 'gpu': ['RTX', 'Radeon RX'],
            'processador': ['AMD Ryzen', 'Intel Core'], 'processadores': ['AMD Ryzen', 'Intel Core'],
            'placa mae': ['motherboard'], 'placa-mae': ['motherboard'],
            'memoria ram': ['DDR4', 'DDR5'], 'memoria': ['DDR4', 'DDR5'],
            'fonte': ['fonte ATX', 'power supply'], 'gabinete': ['gabinete gamer'],
            'ventoinha': ['fan 120mm'], 'pc montado': ['computador gamer'],
        }
        queries = [normalized_query or None] + generic_aliases.get(normalized(normalized_query), [])
        expanded = len(queries) > 1
        stopped = False
        for keyword in queries:
            if stopped or len(items) >= requested_limit:
                break
            for page in range(1, 3 if expanded else 7):
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    warnings.append('Busca encerrada no tempo disponível; mostrando os resultados encontrados.')
                    stopped = True
                    break
                try:
                    result = self.client.search_products(
                        keyword=keyword, item_id=item_id, shop_id=shop_id,
                        limit=page_size, page=page, sort_type=sort_type, list_type=list_type,
                        timeout_seconds=remaining,
                    )
                except ShopeeAffiliateError:
                    if not pages:
                        raise
                    warnings.append('A Shopee não liberou a próxima página; mostrando os resultados encontrados.')
                    stopped = True
                    break
                pages += 1
                page_info = result.get('pagina') or {}
                batch = list(result.get('itens') or [])
                new_items = 0
                for item in batch:
                    identity = (str(item.get('shopId') or ''), str(item.get('itemId') or item.get('urlOriginal') or item.get('nome') or ''))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    new_items += 1
                    if (promotions_only and not item.get('emPromocao')) or not relevant_item(item, normalized_query, intent):
                        discarded += 1
                        continue
                    if item_id is not None and str(item.get('itemId') or '') != str(item_id):
                        continue
                    if shop_id is not None and str(item.get('shopId') or '') != str(shop_id):
                        continue
                    items.append(item)
                if len(items) >= requested_limit or not batch or not new_items or not page_info.get('hasNextPage'):
                    break
        if pages == 6 and len(items) < requested_limit and page_info.get('hasNextPage'):
            warnings.append('Há mais resultados na Shopee. Refine a pesquisa pelo modelo para encontrar ofertas mais precisas.')

        items.sort(key=lambda item: self._score(item, normalized_query), reverse=True)
        items = items[:requested_limit]
        for index, item in enumerate(items, start=1):
            item["relevanciaAgente"] = round(self._score(item, normalized_query), 4)
            item["ordemAgente"] = index
        return {
            "agente": "SHOPEE_AFFILIATE",
            "modo": "API_OFICIAL_PRIMEIRO",
            "consulta": normalized_query or None,
            "itemId": str(item_id) if item_id is not None else None,
            "shopId": str(shop_id) if shop_id is not None else None,
            "quantidade": len(items),
            "itens": items,
            "pagina": {**page_info, "paginasConsultadas": pages, "limitePorPagina": page_size},
            "limiteSolicitado": requested_limit,
            "itensDescartados": discarded,
            "categoriaBusca": intent,
            "consultasAplicadas": queries,
            "avisos": warnings,
            "fontePrimaria": "SHOPEE_AFFILIATE_API",
            "scrapingNecessario": False,
        }

    def find_product_by_url(self, url: str) -> dict[str, Any] | None:
        """Resolve um anúncio exato da Shopee pela API oficial quando a URL contém IDs."""
        shop_id, item_id = extract_shopee_ids(url)
        if item_id is None:
            return None
        result = self.find_products(item_id=item_id, shop_id=shop_id, limit=20)
        items = list(result.get("itens") or [])
        expected_item = str(item_id)
        expected_shop = str(shop_id) if shop_id is not None else None
        for item in items:
            if str(item.get("itemId") or "") != expected_item:
                continue
            if expected_shop is not None and str(item.get("shopId") or "") != expected_shop:
                continue
            return item
        return None

    def find_promotions(self, *, query: str | None = None, limit: int = 20) -> dict[str, Any]:
        campaigns = self.client.list_campaigns(keyword=query, limit=limit)
        return {
            "agente": "SHOPEE_AFFILIATE",
            "modo": "PROMOCOES_API_OFICIAL",
            "consulta": query,
            "quantidade": len(campaigns.get("itens") or []),
            "itens": campaigns.get("itens") or [],
            "pagina": campaigns.get("pagina") or {},
            "fontePrimaria": "SHOPEE_AFFILIATE_API",
            "scrapingNecessario": False,
        }
