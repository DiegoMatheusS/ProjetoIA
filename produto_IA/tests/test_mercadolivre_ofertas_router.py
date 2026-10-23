from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.mercadolivre.router import (
    MercadoLivreProductRequest,
    mercadolivre_agent_product,
    mercadolivre_api_status,
)


class MercadoLivreOfertasRouterTest(unittest.TestCase):
    def test_status_nao_expoe_tokens(self):
        with patch.dict(
            os.environ,
            {
                "ML_CLIENT_ID": "123",
                "ML_CLIENT_SECRET": "segredo",
                "ML_ACCESS_TOKEN": "access",
                "ML_REFRESH_TOKEN": "refresh",
                "ML_USE_PKCE": "true",
                "PRODUTO_IA_API_KEY": "interno",
            },
            clear=False,
        ):
            payload = mercadolivre_api_status(x_api_key="interno")

        self.assertTrue(payload["apiOficial"])
        self.assertTrue(payload["accessTokenConfigurado"])
        self.assertTrue(payload["refreshTokenConfigurado"])
        self.assertTrue(payload["pkce"])
        self.assertNotIn("accessToken", payload)
        self.assertNotIn("refreshToken", payload)
        self.assertNotIn("clientSecret", payload)

    @patch("src.mercadolivre.router.MercadoLivreScraper.collect")
    def test_produto_normaliza_preco_promocional_da_api(self, collect):
        collect.return_value = {
            "ok": True,
            "source": "MERCADO_LIVRE_API",
            "api_used": True,
            "item_id": "MLB123456789",
            "marketplace_product_code": "MLB123456789",
            "title": "RTX 5070",
            "price": 3999.90,
            "previous_price": 4499.90,
            "price_source": "SALE_PRICE",
            "currency": "BRL",
            "available": True,
            "seller_id": 99,
            "url_final": "https://produto.mercadolivre.com.br/MLB-123456789",
            "api_errors": [],
        }

        with patch.dict(os.environ, {"PRODUTO_IA_API_KEY": "interno"}, clear=False):
            result = mercadolivre_agent_product(
                MercadoLivreProductRequest(itemId="MLB123456789", permitirFallback=True),
                x_api_key="interno",
            )

        item = result["item"]
        self.assertEqual(item["itemId"], "MLB123456789")
        self.assertEqual(item["preco"], 3999.90)
        self.assertEqual(item["precoAnterior"], 4499.90)
        self.assertEqual(item["descontoPercentual"], 11.11)
        self.assertTrue(item["emPromocao"])
        self.assertTrue(item["apiOficial"])
        self.assertFalse(item["fallbackUsado"])

    @patch("src.mercadolivre.router.MercadoLivreScraper.collect")
    def test_produto_marca_fallback_sem_perder_api_oficial(self, collect):
        collect.return_value = {
            "ok": True,
            "source": "MERCADO_LIVRE_API_SURFSKY",
            "api_used": True,
            "item_id": "MLB123456789",
            "title": "Produto",
            "price": 100.0,
            "previous_price": None,
            "currency": "BRL",
            "available": True,
        }

        with patch.dict(os.environ, {"PRODUTO_IA_API_KEY": "interno"}, clear=False):
            result = mercadolivre_agent_product(
                MercadoLivreProductRequest(
                    url="https://produto.mercadolivre.com.br/MLB-123456789-produto",
                    permitirFallback=True,
                ),
                x_api_key="interno",
            )

        self.assertTrue(result["item"]["apiOficial"])
        self.assertTrue(result["item"]["fallbackUsado"])


if __name__ == "__main__":
    unittest.main()
