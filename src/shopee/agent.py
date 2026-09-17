from __future__ import annotations

import math
import re
from typing import Any

from .client import ShopeeAffiliateClient


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").casefold())
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
        result = self.client.search_products(
            keyword=normalized_query or None,
            item_id=item_id,
            shop_id=shop_id,
            limit=max(1, min(100, int(limit))),
            sort_type=sort_type,
            list_type=list_type,
        )
        items = list(result.get("itens") or [])
        if promotions_only:
            items = [item for item in items if item.get("emPromocao")]

        if item_id is not None:
            expected = str(item_id)
            items = [item for item in items if str(item.get("itemId") or "") == expected]
        if shop_id is not None:
            expected_shop = str(shop_id)
            items = [item for item in items if str(item.get("shopId") or "") == expected_shop]

        items.sort(key=lambda item: self._score(item, normalized_query), reverse=True)
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
            "pagina": result.get("pagina") or {},
            "fontePrimaria": "SHOPEE_AFFILIATE_API",
            "scrapingNecessario": False,
        }

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
