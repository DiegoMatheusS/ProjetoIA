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
    "PROCESSADOR": ["PC_KOMBO", "CPU_MONKEY", "CPU_WORLD", "WIKICHIP"],
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

# Catálogos públicos conhecidos. A descoberta usa essas páginas diretamente
# em vez de depender de um buscador genérico. CPU-World/WikiChip/Geizhals
# continuam como fontes de confirmação/enriquecimento quando não oferecem um
# catálogo simples e estável para a categoria.
PC_KOMBO_CATALOGS = {
    "PROCESSADOR": ("https://www.pc-kombo.com/us/components/cpus", "/us/product/cpu/"),
    "PLACA_VIDEO": ("https://www.pc-kombo.com/us/components/gpus", "/us/product/gpu/"),
    "PLACA_MAE": ("https://www.pc-kombo.com/us/components/motherboards", "/us/product/mainboard/"),
    "ARMAZENAMENTO": ("https://www.pc-kombo.com/us/components/ssds", "/us/product/ssd/"),
    "FONTE": ("https://www.pc-kombo.com/us/components/psus", "/us/product/psu/"),
    "GABINETE": ("https://www.pc-kombo.com/us/components/cases", "/us/product/case/"),
    "COOLER": ("https://www.pc-kombo.com/us/components/cpucoolers", "/us/product/cpucooler/"),
}

CPU_MONKEY_FAMILY_PAGES = {
    "intel": [
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_i3",
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_i5",
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_i7",
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_i9",
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_ultra_5",
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_ultra_7",
        "https://www.cpu-monkey.com/en/cpu_family-intel_core_ultra_9",
    ],
    "amd": [
        "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_3",
        "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_5",
        "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_7",
        "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_9",
        "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_threadripper",
    ],
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

    def _fetch_rendered_catalog(self, url: str, allowed_domains: list[str]):
        """Renderiza um catálogo via Surfsky quando o HTTP 200 veio parcial.

        Diferente de _fetch_html, este método é chamado mesmo após HTTP bem-sucedido
        quando o parser encontrou poucos SKUs. É o equivalente do fallback cloud do
        Magazine, mas limitado a UMA página de catálogo.
        """
        if not self.allow_browser_fallback or not self.browser.surfsky_configured():
            return None, url, "SURFSKY_NAO_CONFIGURADO"
        remote = self.browser.fetch_surfsky(url)
        if remote.get("error") or remote.get("blocked"):
            return None, remote.get("final_url") or url, remote.get("error") or "SURFSKY_BLOQUEADO"
        final = remote.get("final_url") or url
        if allowed_domains and not self._host_allowed(final, allowed_domains):
            return None, final, "REDIRECIONAMENTO_FORA_DA_FONTE"
        return remote.get("html") or "", final, None

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

    @staticmethod
    def _cpu_monkey_pages(marca=None, consulta=None):
        brand = (marca or "").strip().casefold()
        query = (consulta or "").strip().casefold()

        # Quando o SKU revela a geração Intel, o grupo da geração é a melhor
        # página para encontrar também modelos antigos (ex.: i5-9500).
        m = re.search(r"\bi[3579][ -]?(\d{4,5})[a-z]*\b", query, re.I)
        if m:
            digits = m.group(1)
            if len(digits) == 4:
                gen = digits[0]
            else:
                gen = digits[:2]
            return [f"https://www.cpu-monkey.com/en/cpu_group-intel_core_i_{gen}000"]

        # Consulta por família: evita abrir várias páginas desnecessariamente.
        family_patterns = [
            (r"core\s*i3|\bi3\b", "https://www.cpu-monkey.com/en/cpu_family-intel_core_i3"),
            (r"core\s*i5|\bi5\b", "https://www.cpu-monkey.com/en/cpu_family-intel_core_i5"),
            (r"core\s*i7|\bi7\b", "https://www.cpu-monkey.com/en/cpu_family-intel_core_i7"),
            (r"core\s*i9|\bi9\b", "https://www.cpu-monkey.com/en/cpu_family-intel_core_i9"),
            (r"ryzen\s*3", "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_3"),
            (r"ryzen\s*5", "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_5"),
            (r"ryzen\s*7", "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_7"),
            (r"ryzen\s*9", "https://www.cpu-monkey.com/en/cpu_family-amd_ryzen_9"),
        ]
        for pattern, url in family_patterns:
            if re.search(pattern, query, re.I):
                return [url]

        if brand in CPU_MONKEY_FAMILY_PAGES:
            return list(CPU_MONKEY_FAMILY_PAGES[brand])

        # Sem marca: alterna Intel e AMD para não devolver um catálogo enviesado.
        intel = CPU_MONKEY_FAMILY_PAGES["intel"]
        amd = CPU_MONKEY_FAMILY_PAGES["amd"]
        pages = []
        for i in range(max(len(intel), len(amd))):
            if i < len(intel):
                pages.append(intel[i])
            if i < len(amd):
                pages.append(amd[i])
        return pages

    def _cpu_monkey(self, marca=None, consulta=None, limit=50):
        found = []
        last_error = None

        def parse_page(html, final):
            local = []
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.select('a[href*="/en/cpu-"]'):
                href = link.get("href") or ""
                if not re.search(r"/en/cpu-[a-z0-9_]", href, re.I):
                    continue
                name = self._norm(link.get_text(" ", strip=True))
                if not name:
                    name = self._norm(link.parent.get_text(" ", strip=True) if link.parent else "")
                name = re.split(r"\s+\d+C\s+\d+T\s+@", name, maxsplit=1, flags=re.I)[0].strip()
                if len(name) < 4 or not re.search(r"\d", name) or not self._matches_filters(name, marca, consulta):
                    continue
                local.append(DiscoveryCandidate(nome=name, url=urljoin(final, href), fonte="CPU_MONKEY"))
            return self._dedupe(local)

        for page_index, url in enumerate(self._cpu_monkey_pages(marca, consulta)):
            html, final, error = self._fetch_html(url, ["cpu-monkey.com"])
            page_items = parse_page(html, final) if html else []
            if not page_items:
                last_error = error or last_error

            # HTTP de catálogo pode responder 200 com HTML reduzido. Em vez de
            # aceitar 1-3 modelos, renderizamos a primeira página pobre via Surfsky.
            sparse_threshold = min(8, max(3, int(limit)))
            if len(page_items) < sparse_threshold and page_index < 2:
                rendered, rendered_final, render_error = self._fetch_rendered_catalog(url, ["cpu-monkey.com"])
                if rendered:
                    page_items = self._dedupe(page_items + parse_page(rendered, rendered_final))
                elif render_error:
                    last_error = render_error or last_error

            found.extend(page_items)
            found = self._dedupe(found)
            if len(found) >= limit:
                return found[:limit], None

        result = self._dedupe(found)[:limit]
        return result, None if result else (last_error or "NAO_ENCONTRADO")

    @staticmethod
    def _pc_kombo_name(text: str, categoria: str) -> str:
        value = re.sub(r"^\s*\d+\.\s*", "", text or "").strip()
        # O catálogo concatena um resumo técnico ao nome. Removemos apenas os
        # sufixos estruturados para preservar o modelo comercial.
        patterns = {
            "PROCESSADOR": r"\s+Socket\s+.+$",
            "PLACA_MAE": r"\s+(?:E-ATX|ATX|Micro-ATX|Mini-ITX)\s+Socket\s+.+$",
            "FONTE": r"\s+(?:ATX|SFX|SFX-L|TFX|Flex ATX|PS/2)(?:[, ]+[^0-9]+)?\s+\d{2,4}W\s*$",
            "COOLER": r"\s+For socket\s+.+$",
        }
        pattern = patterns.get(categoria)
        if pattern:
            value = re.sub(pattern, "", value, flags=re.I).strip(" -,")
        return value

    def _pc_kombo(self, categoria: str, marca=None, consulta=None, limit=50):
        config = PC_KOMBO_CATALOGS.get(categoria)
        if not config:
            return self._search_source("PC_KOMBO", categoria, marca, consulta, limit)
        url, product_path = config

        def parse_page(html, final):
            found = []
            soup = BeautifulSoup(html or "", "html.parser")
            selectors = [
                f'a[href*="{product_path}"]',
                f'a[href*="/product/{product_path.strip("/").split("/")[-1]}/"]',
            ]
            links = []
            for selector in selectors:
                links.extend(soup.select(selector))
            for link in links:
                href = link.get("href") or ""
                name = self._pc_kombo_name(self._norm(link.get_text(" ", strip=True)), categoria)
                if len(name) < 3 or not re.search(r"[A-Za-z]", name):
                    continue
                if not self._matches_filters(name, marca, consulta):
                    continue
                found.append(DiscoveryCandidate(nome=name, url=urljoin(final, href), fonte="PC_KOMBO", marca=marca))
            return self._dedupe(found)

        html, final, error = self._fetch_html(url, ["pc-kombo.com"])
        found = parse_page(html, final) if html else []

        # Mesma estratégia do Magazine: se a resposta HTTP parece parcial, usa o
        # navegador cloud na MESMA página e mescla os links renderizados.
        sparse_threshold = min(12, max(4, int(limit)))
        if len(found) < sparse_threshold:
            rendered, rendered_final, render_error = self._fetch_rendered_catalog(url, ["pc-kombo.com"])
            if rendered:
                found = self._dedupe(found + parse_page(rendered, rendered_final))
                error = None if found else (render_error or error)
            elif render_error and not found:
                error = render_error

        result = self._dedupe(found)[:limit]
        return result, None if result else (error or "NAO_ENCONTRADO")

    def _techpowerup(self, marca=None, consulta=None, limit=50):
        url = "https://www.techpowerup.com/gpu-specs/"

        def parse_page(html, final):
            found = []
            soup = BeautifulSoup(html or "", "html.parser")
            for link in soup.select('a[href*="/gpu-specs/"]'):
                href = link.get("href") or ""
                if not re.search(r"/gpu-specs/[^/?#]+\.c\d+", href, re.I):
                    continue
                name = self._norm(link.get_text(" ", strip=True))
                if len(name) < 3 or not self._matches_filters(name, marca, consulta):
                    continue
                found.append(DiscoveryCandidate(nome=name, url=urljoin(final, href), fonte="TECHPOWERUP"))
            return self._dedupe(found)

        html, final, error = self._fetch_html(url, ["techpowerup.com"])
        found = parse_page(html, final) if html else []
        sparse_threshold = min(10, max(4, int(limit)))
        if len(found) < sparse_threshold:
            rendered, rendered_final, render_error = self._fetch_rendered_catalog(url, ["techpowerup.com"])
            if rendered:
                found = self._dedupe(found + parse_page(rendered, rendered_final))
                error = None if found else (render_error or error)
            elif render_error and not found:
                error = render_error
        return self._dedupe(found)[:limit], None if found else (error or "NAO_ENCONTRADO")

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
                handlers = {
                    "PC_KOMBO": lambda: self._pc_kombo(categoria, marca, consulta, per_source_limit),
                    "CPU_MONKEY": lambda: self._cpu_monkey(marca, consulta, per_source_limit) if categoria == "PROCESSADOR" else ([], "CATEGORIA_NAO_SUPORTADA"),
                    "TECHPOWERUP": lambda: self._techpowerup(marca, consulta, per_source_limit) if categoria == "PLACA_VIDEO" else ([], "CATEGORIA_NAO_SUPORTADA"),
                }
                handler = handlers.get(source)
                if handler:
                    items, error = handler()
                else:
                    # CPU-World, WikiChip, Geizhals e fabricante não possuem um
                    # catálogo simples único para todas as categorias. Eles ficam
                    # como descoberta limitada/busca e principalmente confirmação.
                    items, error = self._search_source(source, categoria, marca, consulta, per_source_limit)
            except Exception as exc:
                items, error = [], f"ERRO_FONTE: {type(exc).__name__}: {exc}"
            diagnostics.append({"fonte": source, "encontrados": len(items), "erro": error})
            all_candidates.extend(items)
            if len(self._dedupe(all_candidates)) >= limit:
                # Não faz crawling adicional se já temos candidatos suficientes.
                break
        return self._dedupe(all_candidates)[:limit], diagnostics
