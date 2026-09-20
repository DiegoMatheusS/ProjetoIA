from __future__ import annotations

import html
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from .mercadolivre_token_store import token_storage_status
from .mercadolivre_oauth import (
    PENDING_FILE,
    build_authorization_url,
    configured_redirect_uri,
    exchange_code,
    _env,
    _truthy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mercadolivre", tags=["Mercado Livre OAuth"])


def _html_page(title: str, message: str, *, ok: bool) -> HTMLResponse:
    status = 200 if ok else 400
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    body = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{safe_title}</title>
</head>
<body style="font-family:Arial,sans-serif;max-width:720px;margin:60px auto;padding:0 24px;line-height:1.5">
  <h1>{safe_title}</h1>
  <p>{safe_message}</p>
  <p>Você pode fechar esta aba.</p>
</body>
</html>"""
    return HTMLResponse(content=body, status_code=status)


def _pending_state() -> str | None:
    if not PENDING_FILE.exists():
        return None
    try:
        payload: Any = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("state")
    return str(value).strip() if value else None


@router.get("/oauth/status")
def mercadolivre_oauth_status() -> dict[str, Any]:
    """Status seguro da configuração, sem retornar tokens ou Client Secret."""
    return {
        "ok": True,
        "configurado": bool(
            _env("ML_CLIENT_ID")
            and _env("ML_CLIENT_SECRET")
            and configured_redirect_uri()
        ),
        "clientIdConfigurado": bool(_env("ML_CLIENT_ID")),
        "clientSecretConfigurado": bool(_env("ML_CLIENT_SECRET")),
        "redirectUri": configured_redirect_uri(),
        "accessTokenConfigurado": bool(_env("ML_ACCESS_TOKEN")),
        "refreshTokenConfigurado": bool(_env("ML_REFRESH_TOKEN")),
        "pkce": _truthy(_env("ML_USE_PKCE")),
        "armazenamentoTokens": token_storage_status(),
    }


@router.get("/oauth/autorizar")
def mercadolivre_oauth_authorize() -> RedirectResponse:
    """Inicia o Authorization Code Grant no domínio brasileiro do Mercado Livre."""
    try:
        authorization_url = build_authorization_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/oauth/callback", response_class=HTMLResponse)
def mercadolivre_oauth_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Recebe o code do Mercado Livre e troca por access/refresh token no servidor."""
    if error:
        description = error_description or "A autorização foi cancelada ou recusada."
        return _html_page("Autorização não concluída", description, ok=False)

    if not code or not code.strip():
        return _html_page(
            "Código não recebido",
            "O Mercado Livre não enviou o código de autorização.",
            ok=False,
        )

    expected_state = _pending_state()
    if expected_state and state != expected_state:
        return _html_page(
            "Autorização inválida",
            "O parâmetro de segurança state não corresponde à autorização iniciada.",
            ok=False,
        )

    try:
        token_data = exchange_code(code.strip(), save=True)
    except Exception:
        logger.exception("Falha ao trocar o código OAuth do Mercado Livre por token")
        return HTMLResponse(
            content=_html_page(
                "Falha ao conectar Mercado Livre",
                "O código foi recebido, mas não foi possível concluir a troca por token. Confira as variáveis ML_CLIENT_ID, ML_CLIENT_SECRET e ML_REDIRECT_URI na Railway.",
                ok=False,
            ).body,
            status_code=502,
            media_type="text/html",
        )

    expires_in = token_data.get("expires_in")
    user_id = token_data.get("user_id")
    storage = token_storage_status()
    details = "A conta foi autorizada e os tokens foram recebidos pelo ProjetoIA."
    if storage.get("configurado"):
        details += " Os tokens foram salvos no armazenamento persistente criptografado."
    else:
        details += " Atenção: o armazenamento persistente ainda não está configurado; um redeploy pode exigir nova autorização."
    if expires_in:
        details += f" Access token válido por aproximadamente {expires_in} segundos."
    if user_id:
        details += f" Usuário Mercado Livre conectado: {user_id}."

    return _html_page("Mercado Livre conectado", details, ok=True)
