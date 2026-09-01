import os
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils.rate_limiter import PoliteRateLimiter
from ..scrapers.browser_scraper import BrowserScraper


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

    def _candidate_from_html(self, html, domains):
        soup = BeautifulSoup(html or "", "html.parser")
        links = soup.select("a.result__a, .result a[href], li.b_algo h2 a[href], a[href]")[:120]
        for link in links:
            candidate = self._decode_ddg_url(link.get("href"))
            if not candidate:
                continue
            host = (urlparse(candidate).hostname or "").casefold().removeprefix("www.")
            if any(host == d or host.endswith("." + d) for d in domains):
                return candidate
        return None

    def first_result(self, query, allowed_domains):
        if not query or not allowed_domains:
            return None
        domains = [d.casefold().removeprefix("www.") for d in allowed_domains]
        q = f"{query} " + " OR ".join(f"site:{d}" for d in domains)
        search_urls = [
            "https://html.duckduckgo.com/html/?q=" + quote_plus(q),
            "https://www.bing.com/search?q=" + quote_plus(q),
        ]

        # Primeiro tenta busca HTTP barata.
        for url in search_urls:
            try:
                self.rate_limiter.wait(url)
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code in {403, 429}:
                    continue
                response.raise_for_status()
                candidate = self._candidate_from_html(response.text, domains)
                if candidate:
                    return candidate
            except requests.RequestException:
                continue

        # Em cloud, buscadores também podem bloquear IP de datacenter. Se o
        # Surfsky estiver configurado, usa o mesmo Chromium residencial apenas
        # para descobrir uma página técnica candidata.
        browser = BrowserScraper()
        if browser.surfsky_configured():
            for url in search_urls:
                remote = browser.fetch_surfsky(url)
                if remote.get("error") or remote.get("blocked"):
                    continue
                candidate = self._candidate_from_html(remote.get("html") or "", domains)
                if candidate:
                    return candidate
        return None

