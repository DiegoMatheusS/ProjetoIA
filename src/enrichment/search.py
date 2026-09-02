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
        self.allow_browser_fallback = True
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

    def _candidates_from_html(self, html, domains, limit=10):
        soup = BeautifulSoup(html or "", "html.parser")
        links = soup.select("a.result__a, .result a[href], li.b_algo h2 a[href], a[href]")[:240]
        output = []
        seen = set()
        for link in links:
            candidate = self._decode_ddg_url(link.get("href"))
            if not candidate:
                continue
            host = (urlparse(candidate).hostname or "").casefold().removeprefix("www.")
            if not any(host == d or host.endswith("." + d) for d in domains):
                continue
            key = candidate.split("#", 1)[0].rstrip("/").casefold()
            if key in seen:
                continue
            seen.add(key)
            title = " ".join(link.stripped_strings).strip() or candidate
            output.append({"url": candidate, "title": title})
            if len(output) >= max(1, int(limit)):
                break
        return output

    def _candidate_from_html(self, html, domains):
        candidates = self._candidates_from_html(html, domains, limit=1)
        return candidates[0]["url"] if candidates else None

    def results(self, query, allowed_domains, limit=10):
        if not query or not allowed_domains:
            return []
        domains = [d.casefold().removeprefix("www.") for d in allowed_domains]
        q = f"{query} " + " OR ".join(f"site:{d}" for d in domains)
        search_urls = [
            "https://html.duckduckgo.com/html/?q=" + quote_plus(q),
            "https://www.bing.com/search?q=" + quote_plus(q),
        ]
        merged = []
        seen = set()

        def add(items):
            for item in items:
                key = item["url"].split("#", 1)[0].rstrip("/").casefold()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                if len(merged) >= limit:
                    return True
            return False

        for url in search_urls:
            try:
                self.rate_limiter.wait(url)
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code in {403, 429}:
                    continue
                response.raise_for_status()
                if add(self._candidates_from_html(response.text, domains, limit=limit)):
                    return merged[:limit]
            except requests.RequestException:
                continue

        browser = BrowserScraper()
        if self.allow_browser_fallback and browser.surfsky_configured():
            for url in search_urls:
                remote = browser.fetch_surfsky(url)
                if remote.get("error") or remote.get("blocked"):
                    continue
                if add(self._candidates_from_html(remote.get("html") or "", domains, limit=limit)):
                    break
        return merged[:limit]

    def first_result(self, query, allowed_domains):
        results = self.results(query, allowed_domains, limit=1)
        return results[0]["url"] if results else None
