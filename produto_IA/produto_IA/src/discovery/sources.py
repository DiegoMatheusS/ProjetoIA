from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..enrichment.search import WebSearchResolver
from ..scrapers.browser_scraper import BrowserScraper
from ..utils.rate_limiter import PoliteRateLimiter
from ..utils.normalizers import clean_text


@dataclass
class DiscoveryCandidate:
    nome: str
    url: str
    fonte: str
    marca: str | None = None
    modelo: str | None = None
    resumo: dict = field(default_factory=dict)


CATEGORY_SEARCH_LABELS = {
    "PROCESSADOR": "processor CPU specifications",
    "PLACA_MAE": "motherboard specifications",
    "MEMORIA_RAM": "desktop memory RAM specifications",
    "PLACA_VIDEO": "graphics card GPU specifications",
    "ARMAZENAMENTO": "SSD NVMe storage specifications",
    "FONTE": "power supply PSU specifications",
    "GABINETE": "PC case specifications",
    "COOLER": "CPU cooler specifications",
    "VENTOINHA": "PC cooling fan specifications",
}

# Fontes usadas para DESCOBRIR modelos. O enriquecimento posterior pode consultar
# outras fontes já existentes no Projeto IA.
DEFAULT_SOURCES_BY_CATEGORY = {
    "PROCESSADOR": ["CPU_MONKEY", "CPU_WORLD", "WIKICHIP"],
    "PLACA_VIDEO": ["TECHPOWERUP", "PC_KOMBO", "GEIZHALS"],
    "PLACA_MAE": ["PC_KOMBO", "GEIZHALS"],
    "MEMORIA_RAM": ["PC_KOMBO", "GEIZHALS"],
    "ARMAZENAMENTO": ["PC_KOMBO", "GEIZHALS"],
    "FONTE": ["PC_KOMBO", "GEIZHALS"],
    "GABINETE": ["PC_KOMBO", "GEIZHALS"],
    "COOLER": ["PC_KOMBO", "GEIZHALS"],
    "VENTOINHA": ["PC_KOMBO", "GEIZHALS"],
}

SOURCE_DOMAINS = {
    "CPU_MONKEY": ["cpu-monkey.com"],
    "CPU_WORLD": ["cpu-world.com"],
    "WIKICHIP": ["en.wikichip.org", "wikichip.org"],
    "TECHPOWERUP": ["techpowerup.com"],
    "PC_KOMBO": ["pc-kombo.com"],
    "GEIZHALS": ["geizhals.eu", "geizhals.de", "geizhals.at"],
}


class DiscoverySourceCatalog:
    """Descobre páginas de modelos sem fazer crawler em massa.

    - CPU-Monkey e TechPowerUp possuem páginas de catálogo conhecidas.
    - Demais fontes usam uma busca pública limitada, sem paginação infinita.
    - Surfsky é fallback de página/buscador, nunca um crawler irrestrito.
    """

    def __init__(self, session=None, resolver=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        try:
            self.timeout = max(3, int(os.getenv("DISCOVERY_SOURCE_TIMEOUT_SECONDS", "8")))
        except ValueError:
            self.timeout = 8
        self.resolver = resolver or WebSearchResolver(session=self.session)
        self.resolver.timeout = min(self.resolver.timeout, self.timeout)
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("DISCOVERY_SOURCE_MIN_DELAY_SECONDS", "0.6")),
            jitter=float(os.getenv("DISCOVERY_SOURCE_JITTER_SECONDS", "0.2")),
        )
        self.browser = BrowserScraper()
        self.allow_browser_fallback = True
        config_path = Path(__file__).resolve().parents[2] / "config" / "manufacturer_domains.json"
        try:
            self.brand_domains = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            self.brand_domains = {}

    @staticmethod
    def _host_allowed(url: str, domains: list[str]) -> bool:
        host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in domains)

    def _fetch_html(self, url: str, allowed_domains: list[str]) -> tuple[str | None, str, str | None]:
        http_error = None
        try:
            self.rate_limiter.wait(url)
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code not in {401, 403, 429}:
                response.raise_for_status()
                final = response.url
                if not allowed_domains or self._host_allowed(final, allowed_domains):
                    return response.text, final, None
            http_error = f"HTTP_{response.status_code}"
        except requests.RequestException as exc:
            http_error = f"ERRO_HTTP: {type(exc).__name__}"

        if self.allow_browser_fallback and self.browser.surfsky_configured():
            remote = self.browser.fetch_surfsky(url)
            if not remote.get("error") and not remote.get("blocked"):
                final = remote.get("final_url") or url
                if not allowed_domains or self._host_allowed(final, allowed_domains):
                    return remote.get("html") or "", final, None
            return None, remote.get("final_url") or url, remote.get("error") or "SURFSKY_BLOQUEADO"
        return None, url, http_error or "FALHA_COLETA"

    @staticmethod
    def _norm(value: str | None) -> str:
        text = clean_text(value) or ""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _matches_filters(name: str, marca: str | None, consulta: str | None) -> bool:
        low = (name or "").casefold()
        if marca:
            brand = marca.casefold().strip()
            aliases = {
                "nvidia": ("nvidia", "geforce", "quadro", "tesla"),
                "amd": ("amd", "radeon", "firepro", "ryzen"),
                "intel": ("intel", "core", "xeon", "pentium", "celeron", "arc"),
            }.get(brand, (brand,))
            if not any(alias in low for alias in aliases):
                return False
        if consulta:
            tokens = [x for x in re.split(r"\s+", consulta.casefold().strip()) if x]
            if tokens and not all(token in low for token in tokens):
                return False
        return True

    @staticmethod
    def _dedupe(candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
        output = []
        seen_urls = set()
        seen_names = set()
        for item in candidates:
            url_key = item.url.split("#", 1)[0].rstrip("/").casefold()
            name_key = re.sub(r"[^a-z0-9]+", "", item.nome.casefold())
            if url_key in seen_urls or (name_key and name_key in seen_names):
                continue
            seen_urls.add(url_key)
            if name_key:
                seen_names.add(name_key)
            output.append(item)
        return output

    def _cpu_monkey(self, marca=None, consulta=None, limit=50):
        url = "https://www.cpu-monkey.com/en/search"
        html, final, error = self._fetch_html(url, ["cpu-monkey.com"])
        if not html:
            return [], error
        soup = BeautifulSoup(html, "html.parser")
        found = []
        for link in soup.select('a[href*="/en/cpu-"]'):
            href = link.get("href") or ""
            if not re.search(r"/en/cpu-[a-z0-9_]", href, re.I):
                continue
            name = self._norm(link.get_text(" ", strip=True))
            if not name:
                # Alguns cards colocam o nome no pai imediato.
                name = self._norm(link.parent.get_text(" ", strip=True) if link.parent else "")
            # Remove resumo de cores/clocks que pode vir junto no card.
            name = re.split(r"\s+\d+C\s+\d+T\s+@", name, maxsplit=1, flags=re.I)[0].strip()
            if len(name) < 4 or not self._matches_filters(name, marca, consulta):
                continue
            found.append(DiscoveryCandidate(nome=name, url=urljoin(final, href), fonte="CPU_MONKEY"))
            if len(found) >= limit:
                break
        return self._dedupe(found), None

    def _techpowerup(self, marca=None, consulta=None, limit=50):
        url = "https://www.techpowerup.com/gpu-specs/"
        html, final, error = self._fetch_html(url, ["techpowerup.com"])
        if not html:
            return [], error
        soup = BeautifulSoup(html, "html.parser")
        found = []
        for link in soup.select('a[href*="/gpu-specs/"]'):
            href = link.get("href") or ""
            # Páginas reais do banco usam .cNNNN no final.
            if not re.search(r"/gpu-specs/[^/?#]+\.c\d+", href, re.I):
                continue
            name = self._norm(link.get_text(" ", strip=True))
            if len(name) < 3 or not self._matches_filters(name, marca, consulta):
                continue
            found.append(DiscoveryCandidate(nome=name, url=urljoin(final, href), fonte="TECHPOWERUP"))
            if len(found) >= limit:
                break
        return self._dedupe(found), None

    def _search_source(self, source: str, categoria: str, marca=None, consulta=None, limit=20):
        domains = list(SOURCE_DOMAINS.get(source) or [])
        if source == "FABRICANTE_OFICIAL":
            if not marca:
                return [], "MARCA_OBRIGATORIA_PARA_FABRICANTE"
            domains = list(self.brand_domains.get(marca.casefold()) or [])
            if not domains:
                for key, value in self.brand_domains.items():
                    if marca.casefold().startswith(key + " ") or key.startswith(marca.casefold() + " "):
                        domains = list(value)
                        break
        if not domains:
            return [], "FONTE_SEM_DOMINIOS"

        label = CATEGORY_SEARCH_LABELS.get(categoria, categoria)
        parts = [marca, consulta, label]
        query = " ".join(x.strip() for x in parts if x and x.strip())
        results = self.resolver.results(query, domains, limit=limit)
        found = []
        for result in results:
            name = self._norm(result.get("title"))
            url = result.get("url")
            if not name or not url or not self._matches_filters(name, marca, consulta):
                continue
            found.append(DiscoveryCandidate(nome=name, url=url, fonte=source, marca=marca))
        return self._dedupe(found), None if found else "NAO_ENCONTRADO"

    def discover(self, categoria: str, marca=None, consulta=None, fontes=None, limit=50):
        selected = list(fontes or DEFAULT_SOURCES_BY_CATEGORY.get(categoria) or [])
        # Se o ADMIN informou marca e existe domínio oficial, a fonte oficial entra
        # primeiro por padrão sem obrigar o frontend a conhecê-la.
        if marca and self.brand_domains.get(marca.casefold()) and "FABRICANTE_OFICIAL" not in selected:
            selected.insert(0, "FABRICANTE_OFICIAL")

        all_candidates = []
        diagnostics = []
        per_source_limit = max(limit, min(80, limit * 2))
        for source in selected:
            source = str(source or "").strip().upper()
            try:
                if source == "CPU_MONKEY" and categoria == "PROCESSADOR":
                    items, error = self._cpu_monkey(marca, consulta, per_source_limit)
                elif source == "TECHPOWERUP" and categoria == "PLACA_VIDEO":
                    items, error = self._techpowerup(marca, consulta, per_source_limit)
                else:
                    items, error = self._search_source(source, categoria, marca, consulta, per_source_limit)
            except Exception as exc:
                items, error = [], f"ERRO_FONTE: {type(exc).__name__}: {exc}"
            diagnostics.append({"fonte": source, "encontrados": len(items), "erro": error})
            all_candidates.extend(items)
            if len(self._dedupe(all_candidates)) >= limit:
                # Não faz crawling adicional se já temos candidatos suficientes.
                break
        return self._dedupe(all_candidates)[:limit], diagnostics
