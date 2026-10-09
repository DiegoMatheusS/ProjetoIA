"""Identificação de links públicos de produto, sem dependência do cliente de API."""
import re
from urllib.parse import parse_qs, urlparse


def extract_mercadolivre_item_id(url: str) -> str | None:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if not any(host == domain or host.endswith(f".{domain}") for domain in (
        "mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com",
    )):
        return None
    for params in (parse_qs(parsed.query), parse_qs(parsed.fragment)):
        for key in ("item_id", "wid", "pdp_filters"):
            for value in params.get(key, []):
                pattern = r"item_id\s*:\s*MLB-?(\d{6,})\b" if key == "pdp_filters" else r"\bMLB-?(\d{6,})\b"
                match = re.search(pattern, value, re.I)
                if match:
                    return f"MLB{match.group(1)}"
    if re.search(r"/p/MLB\d+", parsed.path, re.I):
        return None  # Código do catálogo compartilhado entre vendedores.
    match = re.search(r"/MLB-?(\d{6,})(?:[-/]|$)", parsed.path, re.I)
    return f"MLB{match.group(1)}" if match else None


def is_shopee_url(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    return host == "shopee.com.br" or host.endswith(".shopee.com.br")


def extract_shopee_ids(url: str) -> tuple[int | None, int | None]:
    if not is_shopee_url(url):
        return None, None
    path = urlparse(str(url or "")).path or ""
    match = re.search(r"/product/(\d+)/(\d+)(?:/|$)", path, re.I)
    if not match:
        match = re.search(r"(?:^|[-/])i\.(\d+)\.(\d+)(?:[/?#.-]|$)", path, re.I)
    if not match:
        match = re.search(r"/(\d+)/(\d+)(?:/|$)", path)
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)
