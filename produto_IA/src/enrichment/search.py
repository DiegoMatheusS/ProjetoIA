import os
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils.rate_limiter import PoliteRateLimiter


class WebSearchResolver:
    """Descobre UMA página candidata por fonte usando busca pública.

    É propositalmente conservador: não pagina resultados e não tenta contornar
    CAPTCHA/403/bloqueios. Se a busca não responder, o enriquecimento apenas segue
    para a próxima fonte.
    """

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        self.timeout = int(os.getenv("ENRICHMENT_TIMEOUT", "15"))
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("ENRICHMENT_SEARCH_MIN_DELAY_SECONDS", "2.0")),
            jitter=float(os.getenv("ENRICHMENT_SEARCH_JITTER_SECONDS", "0.8")),
        )

    @staticmethod
    def _decode_ddg_url(href):
        if not href:
            return None
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or ""):
            uddg = (parse_qs(parsed.query).get("uddg") or [None])[0]
            return unquote(uddg) if uddg else None
        return href if parsed.scheme in {"http", "https"} else None

    def first_result(self, query, allowed_domains):
        if not query or not allowed_domains:
            return None
        domains = [d.casefold().removeprefix("www.") for d in allowed_domains]
        q = f"{query} " + " OR ".join(f"site:{d}" for d in domains)
        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(q)
        try:
            self.rate_limiter.wait(url)
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code in {403, 429}:
                return None
            response.raise_for_status()
        except requests.RequestException:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        links = soup.select("a.result__a, .result a[href]")[:20]
        for link in links:
            candidate = self._decode_ddg_url(link.get("href"))
            if not candidate:
                continue
            host = (urlparse(candidate).hostname or "").casefold().removeprefix("www.")
            if any(host == d or host.endswith("." + d) for d in domains):
                return candidate
        return None
