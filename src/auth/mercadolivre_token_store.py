from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


_LOCK = threading.Lock()


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def token_store_path() -> Path | None:
    raw = _clean(os.getenv("ML_TOKEN_STORE_PATH"))
    return Path(raw).expanduser() if raw else None


def token_store_key() -> str | None:
    return _clean(os.getenv("ML_TOKEN_ENCRYPTION_KEY"))


def persistent_token_store_configured() -> bool:
    return bool(token_store_path() and token_store_key())


def _fernet() -> Fernet:
    key = token_store_key()
    if not key:
        raise RuntimeError(
            "ML_TOKEN_ENCRYPTION_KEY não configurado para o armazenamento persistente do Mercado Livre."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "ML_TOKEN_ENCRYPTION_KEY inválido. Use uma chave Fernet URL-safe base64."
        ) from exc


def _read_payload_unlocked() -> dict[str, Any]:
    path = token_store_path()
    if not path or not path.exists():
        return {}

    try:
        encrypted = path.read_bytes()
        if not encrypted:
            return {}
        raw = _fernet().decrypt(encrypted)
        payload = json.loads(raw.decode("utf-8"))
    except InvalidToken as exc:
        raise RuntimeError(
            "Não foi possível descriptografar o armazenamento de tokens do Mercado Livre. "
            "Confira ML_TOKEN_ENCRYPTION_KEY."
        ) from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Não foi possível ler o armazenamento persistente de tokens do Mercado Livre."
        ) from exc

    return payload if isinstance(payload, dict) else {}


def load_tokens() -> dict[str, str]:
    if not persistent_token_store_configured():
        return {}

    with _LOCK:
        payload = _read_payload_unlocked()

    result: dict[str, str] = {}
    for key in ("access_token", "refresh_token"):
        value = _clean(payload.get(key))
        if value:
            result[key] = value
    return result


def save_tokens(
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> None:
    if not persistent_token_store_configured():
        raise RuntimeError(
            "Armazenamento persistente de tokens não configurado. "
            "Defina ML_TOKEN_STORE_PATH e ML_TOKEN_ENCRYPTION_KEY."
        )

    path = token_store_path()
    assert path is not None

    with _LOCK:
        current = _read_payload_unlocked()
        if _clean(access_token):
            current["access_token"] = _clean(access_token)
        if _clean(refresh_token):
            current["refresh_token"] = _clean(refresh_token)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()

        raw = json.dumps(
            current,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = _fernet().encrypt(raw)

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(encrypted)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def token_storage_status() -> dict[str, Any]:
    path = token_store_path()
    configured = persistent_token_store_configured()
    exists = bool(path and path.exists())
    readable = False
    access = False
    refresh = False
    error = None

    if configured and exists:
        try:
            tokens = load_tokens()
            readable = True
            access = bool(tokens.get("access_token"))
            refresh = bool(tokens.get("refresh_token"))
        except RuntimeError as exc:
            error = str(exc)

    return {
        "modo": "ARQUIVO_PERSISTENTE_CRIPTOGRAFADO" if configured else "AMBIENTE_LEGADO",
        "configurado": configured,
        "arquivoExiste": exists,
        "legivel": readable,
        "accessTokenPersistido": access,
        "refreshTokenPersistido": refresh,
        "criptografado": configured,
        "erro": error,
    }
