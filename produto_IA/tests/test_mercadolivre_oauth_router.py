from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.auth.mercadolivre_router import (
    mercadolivre_oauth_authorize,
    mercadolivre_oauth_callback,
    mercadolivre_oauth_status,
)


class MercadoLivreOauthRouterTest(unittest.TestCase):
    def test_callback_rejeita_quando_code_nao_foi_enviado(self):
        response = mercadolivre_oauth_callback()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Código não recebido".encode("utf-8"), response.body)

    def test_status_nao_expoe_secret_ou_tokens(self):
        with patch.dict(
            os.environ,
            {
                "ML_CLIENT_ID": "123",
                "ML_CLIENT_SECRET": "segredo",
                "ML_REDIRECT_URI": "https://projetoia-production.up.railway.app/mercadolivre/oauth/callback",
                "ML_ACCESS_TOKEN": "access",
                "ML_REFRESH_TOKEN": "refresh",
                "ML_USE_PKCE": "false",
            },
            clear=False,
        ):
            payload = mercadolivre_oauth_status()

        self.assertTrue(payload["configurado"])
        self.assertTrue(payload["clientSecretConfigurado"])
        self.assertTrue(payload["accessTokenConfigurado"])
        self.assertNotIn("clientSecret", payload)
        self.assertNotIn("accessToken", payload)
        self.assertNotIn("refreshToken", payload)

    def test_authorize_redireciona_para_url_gerada(self):
        expected = "https://auth.mercadolivre.com.br/authorization?response_type=code"
        with patch(
            "src.auth.mercadolivre_router.build_authorization_url",
            return_value=expected,
        ):
            response = mercadolivre_oauth_authorize()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), expected)

    def test_callback_troca_code_sem_expor_token(self):
        with patch(
            "src.auth.mercadolivre_router.exchange_code",
            return_value={
                "access_token": "nao-deve-aparecer",
                "refresh_token": "tambem-nao",
                "expires_in": 21600,
                "user_id": 42,
            },
        ):
            response = mercadolivre_oauth_callback(code="TG-codigo")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mercado Livre conectado".encode("utf-8"), response.body)
        self.assertNotIn(b"nao-deve-aparecer", response.body)
        self.assertNotIn(b"tambem-nao", response.body)


if __name__ == "__main__":
    unittest.main()
