"""Crawling de um nível, somente dos detalhes do produto na mesma origem."""
import re
import time
import unicodedata
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from ..utils.public_http import origin


def _token(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(char for char in value if not unicodedata.combining(char))


def _page_key(url):
    parsed = urlsplit(url)
    return (*origin(url), parsed.path.rstrip("/"), parsed.query)


def same_product(seed, candidate):
    from ..enrichment.identity import build_identity, candidate_matches_identity, identity_is_strong

    for key in ("mpn", "gtin", "model"):
        if seed.get(key) and candidate.get(key) and _token(seed[key]) != _token(candidate[key]):
            return False
    canonical = candidate.get("canonical_url")
    if canonical:
        try:
            if _page_key(canonical) == _page_key(seed.get("canonical_url") or seed["url_final"]):
                return True
        except (ValueError, KeyError):
            return False
    identity = build_identity({"payloadParcialBackend": {
        "marca": seed.get("brand"), "modelo": seed.get("model"),
        "mpn": seed.get("mpn"), "gtin": seed.get("gtin"),
    }})
    if identity_is_strong(identity):
        return candidate_matches_identity(identity, candidate, " ".join(str(candidate.get(key) or "") for key in ("title", "brand", "model", "mpn", "gtin")))
    return bool(seed.get("title") and _token(seed["title"]) == _token(candidate.get("title")))


def merge_page_details(seed, details):
    result = dict(seed)
    # Dados comerciais continuam sendo os da página/API original.
    for key in ("title", "brand", "model", "mpn", "gtin", "description", "image_url"):
        if not result.get(key) and details.get(key):
            result[key] = details[key]
    if len(details.get("description") or "") > len(result.get("description") or ""):
        result["description"] = details["description"]
    pairs = list(seed.get("attributes") or [])
    names = {_token(item.get("name")) for item in pairs}
    for item in details.get("attributes") or []:
        if _token(item.get("name")) not in names:
            pairs.append(item)
            names.add(_token(item.get("name")))
    result["attributes"] = pairs[:250]
    result["attributes_text"] = "\n".join(f"{item.get('name')}: {item.get('value_name')}" for item in result["attributes"])
    result["ok"] = bool(result.get("title"))
    return result


class ProductPageCrawler:
    def __init__(self, fetch, parse, deadline, max_pages=2):
        self.fetch, self.parse, self.deadline = fetch, parse, deadline
        self.max_pages = max(0, min(3, max_pages))

    def candidates(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.select("nav, footer, aside, [class*='related'], [class*='recommend']"):
            node.decompose()
        found, seen = [], {_page_key(base_url)}
        for anchor in soup.select("a[href]")[:600]:
            label = _token(" ".join([anchor.get_text(" ", strip=True), anchor.get("title", ""), anchor.get("aria-label", "")]))
            if not re.search(r"\b(?:descricao|description|especificacoes|specifications|specs|ficha tecnica|caracteristicas|technical details)\b", label):
                continue
            address, _ = urldefrag(urljoin(base_url, anchor["href"]))
            parsed = urlsplit(address)
            try:
                allowed_origin = origin(address) == origin(base_url)
            except ValueError:
                continue
            if not allowed_origin or parsed.username or parsed.password:
                continue
            if re.search(r"/(?:cart|checkout|login|search|busca|carrinho|account)(?:/|$)", parsed.path, re.I):
                continue
            key = _page_key(address)
            if key in seen:
                continue
            seen.add(key)
            found.append(address)
            if len(found) >= self.max_pages:
                break
        return found if self.max_pages else []

    def collect(self, seed, html):
        base_url = seed["url_final"]
        report = {"profundidadeMaxima": 1, "limitePaginasExtras": self.max_pages,
                  "urlsVisitadas": [], "urlsAproveitadas": [], "erros": [], "robotsRespeitado": True}
        result = dict(seed)
        result["crawl"] = report
        candidates = self.candidates(html, base_url)
        if not candidates or time.monotonic() >= self.deadline:
            return result
        parsed = urlsplit(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        response, error = self.fetch(robots_url, origin(base_url))
        robots = RobotFileParser()
        if response is not None:
            if "<html" in response.text[:1000].lower() or "<!doctype" in response.text[:1000].lower():
                report["erros"].append({"url": robots_url, "motivo": "ROBOTS_INVALIDO"})
                return result
            robots.parse(response.text.splitlines())
        elif getattr(getattr(error, "response", None), "status_code", None) == 404:
            robots.parse([])
        else:
            report["erros"].append({"url": robots_url, "motivo": "ROBOTS_INDISPONIVEL"})
            return result
        for address in candidates:
            if time.monotonic() >= self.deadline:
                report["erros"].append({"url": address, "motivo": "ORCAMENTO_COLETA_ESGOTADO"})
                break
            if not robots.can_fetch("CriaByteProductCollector", address):
                report["erros"].append({"url": address, "motivo": "ROBOTS_NAO_PERMITE"})
                continue
            report["urlsVisitadas"].append(address)
            response, error = self.fetch(address, origin(base_url))
            if response is None:
                report["erros"].append({"url": address, "motivo": type(error).__name__})
                continue
            candidate = self.parse(address, response.url, response.text)
            if candidate.get("blocked") or not same_product(seed, candidate):
                report["erros"].append({"url": address, "motivo": "PRODUTO_NAO_CONFIRMADO"})
                continue
            candidate["attributes"] = [{**row, "source_url": response.url}
                                       for row in candidate.get("attributes") or []]
            result = merge_page_details(result, candidate)
            result["crawl"] = report
            report["urlsAproveitadas"].append(response.url)
        return result
