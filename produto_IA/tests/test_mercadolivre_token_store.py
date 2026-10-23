from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from src.auth.mercadolivre_oauth import _env, save_token_values
from src.auth.mercadolivre_token_store import (
    load_tokens,
    save_tokens,
    token_storage_status,
)


class MercadoLivreTokenStoreTest(unittest.TestCase):
    def _env_for_store(self, path: Path) -> dict[str, str]:
        return {
            "ML_TOKEN_STORE_PATH": str(path),
            "ML_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        }

    def test_salva_e_le_tokens_criptografados(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mercadolivre_tokens.enc"
            env = self._env_for_store(path)

            with patch.dict(os.environ, env, clear=False):
                save_tokens(
                    access_token="access-super-secreto",
                    refresh_token="refresh-super-secreto",
                )
                tokens = load_tokens()
                status = token_storage_status()

            self.assertEqual(tokens["access_token"], "access-super-secreto")
            self.assertEqual(tokens["refresh_token"], "refresh-super-secreto")
            self.assertTrue(status["configurado"])
            self.assertTrue(status["criptografado"])
            self.assertTrue(status["accessTokenPersistido"])
            self.assertTrue(status["refreshTokenPersistido"])
            raw = path.read_bytes()
            self.assertNotIn(b"access-super-secreto", raw)
            self.assertNotIn(b"refresh-super-secreto", raw)

    def test_env_prioriza_token_persistido_sobre_variavel_legada(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mercadolivre_tokens.enc"
            env = {
                **self._env_for_store(path),
                "ML_ACCESS_TOKEN": "access-legado",
                "ML_REFRESH_TOKEN": "refresh-legado",
            }

            with patch.dict(os.environ, env, clear=False):
                save_tokens(
                    access_token="access-persistido",
                    refresh_token="refresh-persistido",
                )
                self.assertEqual(_env("ML_ACCESS_TOKEN"), "access-persistido")
                self.assertEqual(_env("ML_REFRESH_TOKEN"), "refresh-persistido")

    def test_save_token_values_preserva_refresh_quando_so_access_muda(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mercadolivre_tokens.enc"
            env = self._env_for_store(path)

            with patch.dict(os.environ, env, clear=False):
                save_tokens(
                    access_token="access-1",
                    refresh_token="refresh-1",
                )
                mode = save_token_values(
                    {
                        "ML_ACCESS_TOKEN": "access-2",
                        "ML_REFRESH_TOKEN": None,
                    }
                )
                tokens = load_tokens()

            self.assertEqual(mode, "ARQUIVO_PERSISTENTE_CRIPTOGRAFADO")
            self.assertEqual(tokens["access_token"], "access-2")
            self.assertEqual(tokens["refresh_token"], "refresh-1")

    def test_status_nao_expoe_caminho_chave_ou_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mercadolivre_tokens.enc"
            env = self._env_for_store(path)

            with patch.dict(os.environ, env, clear=False):
                save_tokens(access_token="access", refresh_token="refresh")
                status = token_storage_status()

            serialized = repr(status)
            self.assertNotIn(str(path), serialized)
            self.assertNotIn(env["ML_TOKEN_ENCRYPTION_KEY"], serialized)
            self.assertNotIn("'access'", serialized)
            self.assertNotIn("'refresh'", serialized)


if __name__ == "__main__":
    unittest.main()
