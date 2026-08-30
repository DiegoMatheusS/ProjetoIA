import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .identity import identity_query, text_matches_identity
from .search import WebSearchResolver
from ..scrapers.generic_scraper import GenericScraper
from ..utils.normalizers import clean_text
from ..utils.rate_limiter import PoliteRateLimiter


class ExternalTechnicalProvider:
    name = "EXTERNO"
    domains = ()
    categories = None

    def __init__(self, resolver=None, session=None):
        self.resolver = resolver or WebSearchResolver(session=session)
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        self.timeout = int(os.getenv("ENRICHMENT_TIMEOUT", "15"))
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("ENRICHMENT_SOURCE_MIN_DELAY_SECONDS", "2.0")),
            jitter=float(os.getenv("ENRICHMENT_SOURCE_JITTER_SECONDS", "0.8")),
        )
        self.generic = GenericScraper()

    def supports(self, category, identity):
        return not self.categories or category in self.categories

    def search_domains(self, identity):
        return list(self.domains)

    def discover(self, identity, category):
        domains = self.search_domains(identity)
        query = identity_query(identity)
        if not domains or not query:
            return None
        return self.resolver.first_result(query, domains)

    def _page_text(self, soup, parsed):
        attrs = parsed.get("attributes") or []
        attr_text = "\n".join(f"{x.get('name')}: {x.get('value_name')}" for x in attrs)
        visible = clean_text(soup.get_text(" ", strip=True)) or ""
        return "\n".join(filter(None, [parsed.get("title"), parsed.get("brand"), parsed.get("model"), parsed.get("mpn"), parsed.get("gtin"), attr_text, visible[:40000]]))

    def fetch_candidate(self, url, identity):
        try:
            self.rate_limiter.wait(url)
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code in {401, 403, 429}:
                return {"ok": False, "url": url, "erro": f"HTTP_{response.status_code}"}
            response.raise_for_status()
        except requests.RequestException as exc:
            return {"ok": False, "url": url, "erro": f"ERRO_HTTP: {exc}"}

        final = response.url
        host = (urlparse(final).hostname or "").casefold().removeprefix("www.")
        domains = [d.casefold().removeprefix("www.") for d in self.search_domains(identity)]
        if domains and not any(host == d or host.endswith("." + d) for d in domains):
            return {"ok": False, "url": final, "erro": "REDIRECIONAMENTO_FORA_DA_FONTE"}

        parsed = self.generic._parse_html(url, final, response.text, source=self.name)
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = self._page_text(soup, parsed)
        if not text_matches_identity(identity, page_text):
            return {"ok": False, "url": final, "erro": "IDENTIDADE_NAO_CONFIRMADA"}

        return {
            "ok": True,
            "fonte": self.name,
            "url": final,
            "attributes": parsed.get("attributes") or [],
            "context_text": page_text,
        }

    def collect(self, identity, category):
        if not self.supports(category, identity):
            return {"ok": False, "fonte": self.name, "erro": "CATEGORIA_NAO_SUPORTADA"}
        url = self.discover(identity, category)
        if not url:
            return {"ok": False, "fonte": self.name, "erro": "NAO_ENCONTRADO"}
        result = self.fetch_candidate(url, identity)
        result.setdefault("fonte", self.name)
        return result


class ManufacturerProvider(ExternalTechnicalProvider):
    name = "FABRICANTE_OFICIAL"

    def __init__(self, resolver=None, session=None, config_path=None):
        super().__init__(resolver=resolver, session=session)
        if config_path is None:
            config_path = Path(__file__).resolve().parents[2] / "config" / "manufacturer_domains.json"
        try:
            self.brand_domains = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except Exception:
            self.brand_domains = {}

    def search_domains(self, identity):
        brand = (identity.get("marca") or "").strip().casefold()
        if brand in self.brand_domains:
            return self.brand_domains[brand]
        # Tenta correspondência conservadora para nomes com sufixos.
        for key, domains in self.brand_domains.items():
            if key and (brand.startswith(key + " ") or key.startswith(brand + " ")):
                return domains
        return []


class TechPowerUpProvider(ExternalTechnicalProvider):
    name = "TECHPOWERUP"
    domains = ("techpowerup.com",)
    categories = {"PLACA_VIDEO"}


class PCKomboProvider(ExternalTechnicalProvider):
    name = "PC_KOMBO"
    domains = ("pc-kombo.com",)
    categories = {
        "PROCESSADOR", "PLACA_MAE", "MEMORIA_RAM", "PLACA_VIDEO", "ARMAZENAMENTO",
        "FONTE", "GABINETE", "COOLER", "VENTOINHA", "MONITOR",
    }


class GeizhalsProvider(ExternalTechnicalProvider):
    name = "GEIZHALS"
    domains = ("geizhals.eu", "geizhals.de", "geizhals.at")
