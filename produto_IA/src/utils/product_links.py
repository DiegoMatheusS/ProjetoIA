"""Identificação de links públicos de produto, sem dependência do cliente de API."""
import re
from urllib.parse import urlparse


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
