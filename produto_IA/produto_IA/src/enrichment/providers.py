import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .identity import identity_query, text_matches_identity
from .search import WebSearchResolver
from ..scrapers.generic_scraper import GenericScraper
from ..scrapers.browser_scraper import BrowserScraper
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
        self.allow_browser_fallback = True

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

    def _parse_candidate_html(self, requested_url, final_url, html, identity):
        parsed = self.generic._parse_html(requested_url, final_url, html, source=self.name)
        soup = BeautifulSoup(html, "html.parser")
        page_text = self._page_text(soup, parsed)
        if not text_matches_identity(identity, page_text):
            return {"ok": False, "url": final_url, "erro": "IDENTIDADE_NAO_CONFIRMADA"}
        return {
            "ok": True,
            "fonte": self.name,
            "url": final_url,
            "attributes": parsed.get("attributes") or [],
            "context_text": page_text,
        }

    def _fetch_candidate_surfsky(self, url, identity):
        if not getattr(self, "allow_browser_fallback", True):
            return None
        browser = BrowserScraper()
        if not browser.surfsky_configured():
            return None
        remote = browser.fetch_surfsky(url)
        if remote.get("error"):
            return {"ok": False, "url": remote.get("final_url") or url, "erro": remote.get("error")}
        if remote.get("blocked"):
            return {"ok": False, "url": remote.get("final_url") or url, "erro": "SURFSKY_BLOQUEADO"}
        final = remote.get("final_url") or url
        host = (urlparse(final).hostname or "").casefold().removeprefix("www.")
        domains = [d.casefold().removeprefix("www.") for d in self.search_domains(identity)]
        if domains and not any(host == d or host.endswith("." + d) for d in domains):
            return {"ok": False, "url": final, "erro": "REDIRECIONAMENTO_FORA_DA_FONTE"}
        parsed = self._parse_candidate_html(url, final, remote.get("html") or "", identity)
        if parsed.get("ok"):
            parsed["modoColeta"] = "SURFSKY"
        return parsed

    def fetch_candidate(self, url, identity):
        http_error = None
        try:
            self.rate_limiter.wait(url)
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code in {401, 403, 429}:
                http_error = f"HTTP_{response.status_code}"
            else:
                response.raise_for_status()
                final = response.url
                host = (urlparse(final).hostname or "").casefold().removeprefix("www.")
                domains = [d.casefold().removeprefix("www.") for d in self.search_domains(identity)]
                if domains and not any(host == d or host.endswith("." + d) for d in domains):
                    return {"ok": False, "url": final, "erro": "REDIRECIONAMENTO_FORA_DA_FONTE"}
                parsed = self._parse_candidate_html(url, final, response.text, identity)
                if parsed.get("ok"):
                    parsed["modoColeta"] = "HTTP"
                    return parsed
                http_error = parsed.get("erro")
        except requests.RequestException as exc:
            http_error = f"ERRO_HTTP: {exc}"

        # Algumas páginas técnicas também usam JS/WAF. Como o CriaByte já tem
        # Surfsky configurado para coleta cloud, reaproveitamos o mesmo browser
        # somente quando a tentativa HTTP não foi suficiente.
        surf = self._fetch_candidate_surfsky(url, identity)
        if surf is not None:
            if surf.get("ok"):
                return surf
            if surf.get("erro"):
                return surf
        return {"ok": False, "url": url, "erro": http_error or "FALHA_COLETA_FONTE"}

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


class CPUWorldProvider(ExternalTechnicalProvider):
    name = "CPU_WORLD"
    domains = ("cpu-world.com",)
    categories = {"PROCESSADOR"}


class CPUMonkeyProvider(ExternalTechnicalProvider):
    name = "CPU_MONKEY"
    domains = ("cpu-monkey.com",)
    categories = {"PROCESSADOR"}

    @staticmethod
    def _direct_url(identity):
        # CPU-Monkey usa URLs estáveis como:
        # /en/cpu-intel_core_i5_9400f e /en/cpu-amd_ryzen_7_7800x3d.
        # Tentamos esse caminho antes de gastar uma sessão de busca.
        brand = str(identity.get("marca") or "").strip()
        model = str(identity.get("modelo") or "").strip()
        if not brand or not model:
            return None
        import re
        if brand.casefold() == "intel" and re.match(r"^i[3579][ -]?\d", model, re.I):
            model = f"Core {model}"
        # Um SKU AMD isolado (ex.: "7600") não informa se é Ryzen 5/7/9;
        # nesse caso não adivinhamos o slug e usamos a busca pública.
        if brand.casefold() == "amd" and re.fullmatch(r"\d{4}[A-Za-z0-9]*", model):
            return None
        raw = f"{brand} {model}"
        slug = raw.casefold().replace("®", "").replace("™", "")
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        return f"https://www.cpu-monkey.com/en/cpu-{slug}" if slug else None

    def collect(self, identity, category):
        if not self.supports(category, identity):
            return {"ok": False, "fonte": self.name, "erro": "CATEGORIA_NAO_SUPORTADA"}

        direct = self._direct_url(identity)
        if direct:
            result = self.fetch_candidate(direct, identity)
            result.setdefault("fonte", self.name)
            if result.get("ok"):
                self._normalize_cpu_monkey(result)
                return result

        # Fallback para busca pública caso o slug direto não exista.
        url = ExternalTechnicalProvider.discover(self, identity, category)
        if not url or url == direct:
            return {"ok": False, "fonte": self.name, "url": direct, "erro": (result.get("erro") if direct else "NAO_ENCONTRADO")}
        result = self.fetch_candidate(url, identity)
        result.setdefault("fonte", self.name)
        if result.get("ok"):
            self._normalize_cpu_monkey(result)
        return result

    @staticmethod
    def _normalize_cpu_monkey(result):
        # A tabela "Memory type | Memory bandwidth" do CPU-Monkey coloca
        # DDR4-2666/DDR5-5600 na primeira célula da linha seguinte. Convertemos
        # isso para um par explícito que o extrator técnico entende.
        import re
        attrs = list(result.get("attributes") or [])
        has_memory_type = any(str(x.get("name") or "").casefold() in {"memory type", "memory types"} for x in attrs)
        if not has_memory_type:
            for item in attrs:
                name = str(item.get("name") or "").strip()
                m = re.fullmatch(r"(DDR[345])\s*[- ]\s*(\d{3,5})", name, re.I)
                if m:
                    attrs.append({"id": None, "name": "Memory Types", "value_name": f"{m.group(1).upper()}-{m.group(2)}"})
                    break
        result["attributes"] = attrs


class WikiChipProvider(ExternalTechnicalProvider):
    name = "WIKICHIP"
    domains = ("en.wikichip.org", "wikichip.org")
    categories = {"PROCESSADOR", "PLACA_VIDEO"}


class GeizhalsProvider(ExternalTechnicalProvider):
    name = "GEIZHALS"
    domains = ("geizhals.eu", "geizhals.de", "geizhals.at")
