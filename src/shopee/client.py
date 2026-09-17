from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import requests


DEFAULT_ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"


class ShopeeAffiliateError(RuntimeError):
    pass


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ShopeeAffiliateClient:
    """Cliente GraphQL da Shopee Open Affiliate Platform.

    Credenciais nunca ficam no código. O App ID e o Secret são lidos apenas do
    ambiente do ProjetoIA/Railway. A assinatura usa o payload JSON exato enviado
    no POST para evitar divergência de hash.
    """

    def __init__(
        self,
        *,
        app_id: str | None = None,
        secret: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.app_id = str(app_id or os.getenv("SHOPEE_AFFILIATE_APP_ID", "")).strip()
        self.secret = str(secret or os.getenv("SHOPEE_AFFILIATE_SECRET", "")).strip()
        self.endpoint = str(endpoint or os.getenv("SHOPEE_AFFILIATE_API_URL", DEFAULT_ENDPOINT)).strip()
        self.timeout_seconds = max(3, int(timeout_seconds or os.getenv("SHOPEE_AFFILIATE_TIMEOUT_SECONDS", "15")))
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.secret and self.endpoint)

    @staticmethod
    def serialize_payload(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def signature(self, timestamp: int, payload_json: str) -> str:
        raw = f"{self.app_id}{int(timestamp)}{payload_json}{self.secret}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def authorization_header(self, timestamp: int, payload_json: str) -> str:
        signature = self.signature(timestamp, payload_json)
        return (
            f"SHA256 Credential={self.app_id}, "
            f"Timestamp={int(timestamp)}, Signature={signature}"
        )

    def graphql(
        self,
        query: str,
        *,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise ShopeeAffiliateError(
                "Shopee Affiliate API não configurada. Defina SHOPEE_AFFILIATE_APP_ID e SHOPEE_AFFILIATE_SECRET."
            )

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        payload_json = self.serialize_payload(payload)
        timestamp = int(time.time())
        headers = {
            "Authorization": self.authorization_header(timestamp, payload_json),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": os.getenv("USER_AGENT", "CriaByte-ProjetoIA/1.0"),
        }

        try:
            response = self.session.post(
                self.endpoint,
                data=payload_json.encode("utf-8"),
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ShopeeAffiliateError(f"Falha de rede na Shopee Affiliate API: {exc}") from exc

        if response.status_code >= 400:
            raise ShopeeAffiliateError(
                f"Shopee Affiliate API respondeu HTTP {response.status_code}."
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ShopeeAffiliateError("Resposta inválida da Shopee Affiliate API.") from exc

        errors = body.get("errors") if isinstance(body, dict) else None
        if errors:
            messages = []
            for item in errors:
                if not isinstance(item, dict):
                    continue
                extension = item.get("extensions") if isinstance(item.get("extensions"), dict) else {}
                code = extension.get("code")
                message = item.get("message") or extension.get("message") or "Erro GraphQL"
                messages.append(f"{code}: {message}" if code is not None else str(message))
            raise ShopeeAffiliateError("Shopee Affiliate API: " + "; ".join(messages or ["erro desconhecido"]))

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise ShopeeAffiliateError("Shopee Affiliate API não retornou data.")
        return data

    @staticmethod
    def normalize_product(node: dict[str, Any]) -> dict[str, Any]:
        price_min = _as_float(node.get("priceMin"))
        price_max = _as_float(node.get("priceMax"))
        discount = _as_float(node.get("priceDiscountRate"))
        if discount is not None and 0 < discount <= 1:
            discount *= 100

        return {
            "fonte": "SHOPEE_AFFILIATE_API",
            "marketplace": "SHOPEE",
            "itemId": str(node.get("itemId")) if node.get("itemId") is not None else None,
            "shopId": str(node.get("shopId")) if node.get("shopId") is not None else None,
            "nome": node.get("productName"),
            "loja": node.get("shopName"),
            "tipoLoja": _as_int(node.get("shopType")),
            "urlOriginal": node.get("productLink"),
            "urlAfiliada": node.get("offerLink"),
            "imagemUrl": node.get("imageUrl"),
            "preco": price_min,
            "precoMin": price_min,
            "precoMax": price_max,
            "descontoPercentual": discount,
            "emPromocao": bool(discount and discount > 0),
            "vendas": _as_int(node.get("sales")),
            "avaliacao": _as_float(node.get("ratingStar")),
            "comissaoPercentual": _as_float(node.get("commissionRate")),
            "comissaoSellerPercentual": _as_float(node.get("sellerCommissionRate")),
            "comissaoShopeePercentual": _as_float(node.get("shopeeCommissionRate")),
            "comissaoEstimada": _as_float(node.get("commission")),
            "promocaoInicio": _as_int(node.get("periodStartTime")),
            "promocaoFim": _as_int(node.get("periodEndTime")),
            "apiOficial": True,
        }

    def search_products(
        self,
        *,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 20,
        list_type: int = 0,
        sort_type: int = 1,
        shop_id: int | None = None,
        item_id: int | None = None,
        seller_offer_only: bool | None = None,
        key_seller_only: bool | None = None,
    ) -> dict[str, Any]:
        args: list[str] = [f"page: {max(1, int(page))}", f"limit: {max(1, min(100, int(limit)))}"]
        if keyword:
            args.append(f"keyword: {json.dumps(str(keyword), ensure_ascii=False)}")
        args.append(f"listType: {int(list_type)}")
        args.append(f"sortType: {int(sort_type)}")
        if shop_id is not None:
            args.append(f"shopId: {int(shop_id)}")
        if item_id is not None:
            args.append(f"itemId: {int(item_id)}")
        if seller_offer_only is not None:
            args.append(f"isAMSOffer: {'true' if seller_offer_only else 'false'}")
        if key_seller_only is not None:
            args.append(f"isKeySeller: {'true' if key_seller_only else 'false'}")

        query = """
        query {
          productOfferV2(%s) {
            nodes {
              itemId productName productLink offerLink imageUrl
              priceMin priceMax priceDiscountRate sales ratingStar
              commissionRate sellerCommissionRate shopeeCommissionRate commission
              shopId shopName shopType periodStartTime periodEndTime
            }
            pageInfo { page limit hasNextPage }
          }
        }
        """ % ", ".join(args)
        data = self.graphql(query)
        result = data.get("productOfferV2") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            result = {}
        nodes = result.get("nodes") if isinstance(result.get("nodes"), list) else []
        return {
            "itens": [self.normalize_product(node) for node in nodes if isinstance(node, dict)],
            "pagina": result.get("pageInfo") if isinstance(result.get("pageInfo"), dict) else {},
            "fonte": "SHOPEE_AFFILIATE_API",
            "apiOficial": True,
        }

    def list_campaigns(
        self,
        *,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 20,
        sort_type: int = 1,
    ) -> dict[str, Any]:
        args = [f"page: {max(1, int(page))}", f"limit: {max(1, min(100, int(limit)))}", f"sortType: {int(sort_type)}"]
        if keyword:
            args.append(f"keyword: {json.dumps(str(keyword), ensure_ascii=False)}")
        query = """
        query {
          shopeeOfferV2(%s) {
            nodes {
              commissionRate imageUrl offerLink originalLink offerName offerType
              categoryId collectionId periodStartTime periodEndTime
            }
            pageInfo { page limit hasNextPage }
          }
        }
        """ % ", ".join(args)
        data = self.graphql(query)
        result = data.get("shopeeOfferV2") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            result = {}
        nodes = result.get("nodes") if isinstance(result.get("nodes"), list) else []
        itens = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            itens.append(
                {
                    "fonte": "SHOPEE_AFFILIATE_API",
                    "marketplace": "SHOPEE",
                    "nome": node.get("offerName"),
                    "tipoOferta": _as_int(node.get("offerType")),
                    "categoriaId": node.get("categoryId"),
                    "colecaoId": node.get("collectionId"),
                    "imagemUrl": node.get("imageUrl"),
                    "urlOriginal": node.get("originalLink"),
                    "urlAfiliada": node.get("offerLink"),
                    "comissaoPercentual": _as_float(node.get("commissionRate")),
                    "promocaoInicio": _as_int(node.get("periodStartTime")),
                    "promocaoFim": _as_int(node.get("periodEndTime")),
                    "apiOficial": True,
                }
            )
        return {
            "itens": itens,
            "pagina": result.get("pageInfo") if isinstance(result.get("pageInfo"), dict) else {},
            "fonte": "SHOPEE_AFFILIATE_API",
            "apiOficial": True,
        }

    def generate_short_link(self, origin_url: str, *, sub_ids: list[str] | None = None) -> str:
        origin_url = str(origin_url or "").strip()
        if not origin_url:
            raise ShopeeAffiliateError("URL da Shopee vazia.")
        safe_sub_ids = [str(value).strip() for value in (sub_ids or []) if str(value).strip()][:5]
        sub_ids_graphql = ", ".join(json.dumps(value, ensure_ascii=False) for value in safe_sub_ids)
        input_fields = [f"originUrl: {json.dumps(origin_url, ensure_ascii=False)}"]
        if safe_sub_ids:
            input_fields.append(f"subIds: [{sub_ids_graphql}]")
        query = """
        mutation {
          generateShortLink(input: { %s }) { shortLink }
        }
        """ % ", ".join(input_fields)
        data = self.graphql(query)
        result = data.get("generateShortLink") if isinstance(data, dict) else None
        short_link = result.get("shortLink") if isinstance(result, dict) else None
        if not short_link:
            raise ShopeeAffiliateError("Shopee não retornou o link de afiliado.")
        return str(short_link)
