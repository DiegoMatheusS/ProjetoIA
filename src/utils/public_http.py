"""Leitura limitada de páginas públicas, validando também redirecionamentos."""
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit

def validate_public_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
        raise ValueError("URL_PUBLICA_INVALIDA")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("ENDERECO_NAO_PUBLICO")
    addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0].split("%")[0]).is_global for item in addresses):
        raise ValueError("ENDERECO_NAO_PUBLICO")
    return url


def origin(url):
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or (443 if parsed.scheme == "https" else 80))


def get_public_page(session, url, *, timeout, deadline, rate_limiter, same_origin=None, max_bytes=2 * 1024 * 1024):
    for _ in range(5):
        validate_public_url(url)
        if same_origin is not None and origin(url) != same_origin:
            raise ValueError("REDIRECIONAMENTO_FORA_DA_ORIGEM")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("ORCAMENTO_COLETA_ESGOTADO")
        rate_limiter.wait(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("ORCAMENTO_COLETA_ESGOTADO")
        response = session.get(url, timeout=min(timeout, remaining), allow_redirects=False, stream=True)
        try:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("REDIRECIONAMENTO_SEM_DESTINO")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError("CONTEUDO_NAO_HTML")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                if time.monotonic() >= deadline:
                    raise TimeoutError("ORCAMENTO_COLETA_ESGOTADO")
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("PAGINA_MUITO_GRANDE")
                chunks.append(chunk)
            response._content = b"".join(chunks)
            response._content_consumed = True
            return response
        finally:
            response.close()
    raise ValueError("REDIRECIONAMENTOS_EM_EXCESSO")
