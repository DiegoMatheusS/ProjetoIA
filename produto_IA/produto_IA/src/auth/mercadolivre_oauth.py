import argparse
import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
PENDING_FILE = PROJECT_ROOT / ".ml_oauth_pending.json"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
API_BASE = "https://api.mercadolibre.com"

load_dotenv(ENV_FILE)


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _env(name):
    return _clean(os.getenv(name))


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim", "on"}


def codespace_redirect_uri(port=8765):
    name = _env("CODESPACE_NAME")
    domain = _env("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN") or "app.github.dev"
    if not name:
        return None
    return f"https://{name}-{port}.{domain}/callback"


def configured_redirect_uri():
    return _env("ML_REDIRECT_URI") or codespace_redirect_uri()


def save_env_values(values: dict):
    """Atualiza somente chaves ML_* no .env sem apagar outras configurações."""
    existing_lines = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    keys = set(values)
    output = []
    seen = set()

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in keys:
            value = values[key]
            if value is not None:
                output.append(f"{key}={value}")
            seen.add(key)
        else:
            output.append(line)

    if output and output[-1].strip():
        output.append("")
    for key, value in values.items():
        if key not in seen and value is not None:
            output.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    for key, value in values.items():
        if value is not None:
            os.environ[key] = str(value)


def status():
    data = {
        "clientIdConfigurado": bool(_env("ML_CLIENT_ID")),
        "clientSecretConfigurado": bool(_env("ML_CLIENT_SECRET")),
        "redirectUri": configured_redirect_uri(),
        "accessTokenConfigurado": bool(_env("ML_ACCESS_TOKEN")),
        "refreshTokenConfigurado": bool(_env("ML_REFRESH_TOKEN")),
        "pkce": _truthy(_env("ML_USE_PKCE")),
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_authorization_url():
    client_id = _env("ML_CLIENT_ID")
    redirect_uri = configured_redirect_uri()
    if not client_id:
        raise RuntimeError("ML_CLIENT_ID não configurado no .env.")
    if not redirect_uri:
        raise RuntimeError("ML_REDIRECT_URI não configurado e Codespaces não detectado.")

    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    pending = {"state": state, "redirect_uri": redirect_uri}

    if _truthy(_env("ML_USE_PKCE")):
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("utf-8")).digest()
        ).rstrip(b"=").decode("ascii")
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
        pending["code_verifier"] = verifier

    PENDING_FILE.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    return AUTH_URL + "?" + urlencode(params)


def _post_token(payload):
    response = requests.post(
        TOKEN_URL,
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"message": response.text[:500]}
    if not response.ok:
        message = body.get("message") or body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"
        raise RuntimeError(f"Mercado Livre recusou o token: {message}")
    return body


def exchange_code(code: str, save=True):
    client_id = _env("ML_CLIENT_ID")
    client_secret = _env("ML_CLIENT_SECRET")
    redirect_uri = configured_redirect_uri()
    if not all([client_id, client_secret, redirect_uri]):
        raise RuntimeError("Configure ML_CLIENT_ID, ML_CLIENT_SECRET e ML_REDIRECT_URI.")

    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    if PENDING_FILE.exists():
        try:
            pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
            verifier = _clean(pending.get("code_verifier"))
            if verifier:
                payload["code_verifier"] = verifier
        except Exception:
            pass

    body = _post_token(payload)
    if save:
        save_env_values({
            "ML_ACCESS_TOKEN": _clean(body.get("access_token")),
            "ML_REFRESH_TOKEN": _clean(body.get("refresh_token")),
        })
    if PENDING_FILE.exists():
        PENDING_FILE.unlink(missing_ok=True)
    return body


def refresh_access_token(save=True):
    client_id = _env("ML_CLIENT_ID")
    client_secret = _env("ML_CLIENT_SECRET")
    refresh_token = _env("ML_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Configure ML_CLIENT_ID, ML_CLIENT_SECRET e ML_REFRESH_TOKEN.")

    body = _post_token({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    if save:
        # O Mercado Livre invalida o refresh token anterior; sempre persista o novo.
        save_env_values({
            "ML_ACCESS_TOKEN": _clean(body.get("access_token")),
            "ML_REFRESH_TOKEN": _clean(body.get("refresh_token")) or refresh_token,
        })
    return body


def whoami():
    token = _env("ML_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("ML_ACCESS_TOKEN não configurado.")
    response = requests.get(
        f"{API_BASE}/users/me",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=20,
    )
    if response.status_code == 401 and _env("ML_REFRESH_TOKEN"):
        refresh_access_token(save=True)
        token = _env("ML_ACCESS_TOKEN")
        response = requests.get(
            f"{API_BASE}/users/me",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
        )
    response.raise_for_status()
    body = response.json()
    # Nunca imprime token/secret.
    safe = {k: body.get(k) for k in ("id", "nickname", "site_id", "country_id") if k in body}
    print(json.dumps(safe, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="OAuth do Mercado Livre para Produto IA")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("codespace-uri")
    sub.add_parser("auth-url")
    ex = sub.add_parser("exchange")
    ex.add_argument("--code", required=True)
    sub.add_parser("refresh")
    sub.add_parser("whoami")
    args = parser.parse_args()

    if args.command == "status":
        status()
    elif args.command == "codespace-uri":
        uri = codespace_redirect_uri()
        if not uri:
            raise SystemExit("Codespaces não detectado. Configure ML_REDIRECT_URI manualmente.")
        print(uri)
    elif args.command == "auth-url":
        print(build_authorization_url())
    elif args.command == "exchange":
        body = exchange_code(args.code, save=True)
        print(json.dumps({
            "ok": True,
            "expiresIn": body.get("expires_in"),
            "userId": body.get("user_id"),
            "scope": body.get("scope"),
            "salvoEmEnv": True,
        }, ensure_ascii=False, indent=2))
    elif args.command == "refresh":
        body = refresh_access_token(save=True)
        print(json.dumps({
            "ok": True,
            "expiresIn": body.get("expires_in"),
            "userId": body.get("user_id"),
            "salvoEmEnv": True,
        }, ensure_ascii=False, indent=2))
    elif args.command == "whoami":
        whoami()


if __name__ == "__main__":
    main()
