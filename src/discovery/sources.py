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
    "MEMORIA_RAM": ("https://www.pc-kombo.com/us/components/ram", "/us/product/ram/"),
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
            self.timeout = max(3, int(os.getenv("DISCOVERY_SOURCE_TIMEOUT_SECONDS", "5")))
        except ValueError:
            self.timeout = 5
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
            # Com filtro específico, um único match válido já basta. A regra
            # antiga renderizava Surfsky mesmo após achar o SKU e adicionava
            # dezenas de segundos sem melhorar o resultado.
            sparse_threshold = 1 if consulta else min(5, max(3, int(limit)))
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
        if categoria == "ARMAZENAMENTO":
            # Preserva a capacidade no nome (500 GB / 1 TB são SKUs distintos),
            # mas remove a repetição que o catálogo às vezes exibe.
            m = re.match(r"^(.*?)\s+(?:\d+\s+GB\s+)?(\d+)\s+GB\s+(?:NVM|NVME|SATA)\s+Protocol\s+.+?\s+Format\s*$", value, re.I)
            if m:
                return f"{m.group(1).strip()} {m.group(2)} GB".strip()
        # O catálogo concatena um resumo técnico ao nome. Removemos apenas os
        # sufixos estruturados para preservar o modelo comercial.
        patterns = {
            "PROCESSADOR": r"\s+Socket\s+.+$",
            "MEMORIA_RAM": r"\s+Memory\s+\d+(?:\.\d+)?\s+GB(?:,\s*DDR[345][ -]?\d{3,5})?\s*$",
            "PLACA_MAE": r"\s+(?:E-ATX|ATX|Micro-ATX|Mini-ATX|Mini-ITX|Mini-DTX|ITX|CEB|EEB|XL-ATX)\s+Socket\s+.+$",
            "PLACA_VIDEO": r"\s+(?:(?:GeForce\s+(?:RTX|GTX|GT|GTS)\s+\d{3,4}(?:\s+(?:Ti|SUPER|Super))?)|(?:Radeon\s+(?:RX\s+\d{3,4}(?:\s+(?:XT|XTX))?|VII))|(?:Intel\s+Arc\s+[A-Z]\d+))(?:\s*\([^)]*\))?\s+\d+(?:\.\d+)?\s+GB\s+\d+W\s*$",
            "ARMAZENAMENTO": r"\s+(?:\d+\s+GB\s+)?\d+\s+GB\s+(?:NVM|NVME|SATA)\s+Protocol\s+.+?\s+Format\s*$",
            "FONTE": r"\s+(?:(?:80\s+PLUS\s+(?:Bronze|Silver|Gold|Platinum|Titanium))[, ]*)?(?:(?:semi-modular|semi modular|modular)\s+)?(?:ATX(?: PS/2)?|SFX(?:-L)?|TFX|Flex-?ATX|PS/2)\s+\d{2,4}W\s*$",
            "COOLER": r"\s+For socket\s+.+$",
        }
        pattern = patterns.get(categoria)
        if pattern:
            value = re.sub(pattern, "", value, flags=re.I).strip(" -,")
        return value


    @staticmethod
    def _pc_kombo_summary(text: str, categoria: str) -> dict:
        """Extrai os campos que o próprio catálogo do PC-Kombo já exibe.

        A descoberta precisa ser útil mesmo quando a página individual estiver lenta
        ou bloqueada. Por isso preservamos os dados técnicos da listagem.
        """
        raw = re.sub(r"\s+", " ", text or "").strip()
        specs = {}
        if categoria == "PROCESSADOR":
            m = re.search(
                r"\bSocket\s+(.+?)\s+Clock\s+([0-9.]+)\s*GHz(?:\s+Turbo\s+([0-9.]+)\s*GHz)?\s+(\d+)\s+Cores\s+(\d+)\s+Threads\b",
                raw, re.I,
            )
            if m:
                specs["socket"] = m.group(1).strip()
                specs["frequenciaBaseMhz"] = int(round(float(m.group(2)) * 1000))
                if m.group(3):
                    specs["frequenciaTurboMhz"] = int(round(float(m.group(3)) * 1000))
                specs["nucleos"] = int(m.group(4))
                specs["threads"] = int(m.group(5))

        elif categoria == "PLACA_MAE":
            m = re.search(
                r"\b(E-ATX|ATX|Micro-ATX|Mini-ATX|Mini-ITX|Mini-DTX|ITX|CEB|EEB|XL-ATX)\s+Socket\s+(.+?)\s+Chipset\s+([^ ]+)\s+(\d+)\s+Ramslots\b",
                raw, re.I,
            )
            if m:
                specs["formato"] = m.group(1)
                specs["socket"] = m.group(2).strip()
                specs["chipset"] = m.group(3).strip()
                specs["slotsMemoria"] = int(m.group(4))
            mem_types = sorted(set(x.upper() for x in re.findall(r"\bDDR[345]\b", raw, re.I)))
            if mem_types:
                specs["tiposMemoriaSuportados"] = mem_types

        elif categoria == "MEMORIA_RAM":
            ddr = re.search(r"\b(DDR[345])(?:[- ](\d{3,5}))?\b", raw, re.I)
            if ddr:
                specs["tipo"] = ddr.group(1).upper()
                if ddr.group(2):
                    specs["frequenciaMhz"] = int(ddr.group(2))
            kit = re.search(r"\b(\d+)\s*[xX]\s*(\d+(?:\.\d+)?)\s*GB\b", raw, re.I)
            if kit:
                specs["quantidadeModulos"] = int(kit.group(1))
                per = float(kit.group(2))
                specs["capacidadePorModuloGb"] = int(per) if per.is_integer() else per
            if re.search(r"\bSO[- ]?DIMM\b", raw, re.I):
                specs["formato"] = "SO_DIMM"
            elif re.search(r"\b(?:U?DIMM)\b", raw, re.I):
                specs["formato"] = "DIMM"
            cl = re.search(r"\bCL\s*(\d{1,3})\b", raw, re.I)
            if cl:
                specs["latenciaCl"] = int(cl.group(1))
            volt = re.search(r"\b([0-9]+(?:[.,][0-9]+)?)\s*V\b", raw, re.I)
            if volt:
                specs["tensaoVolts"] = float(volt.group(1).replace(",", "."))
            if re.search(r"\bECC\b", raw, re.I):
                specs["ecc"] = True
            if re.search(r"\bXMP\b", raw, re.I):
                specs["suportaXmp"] = True
            if re.search(r"\bEXPO\b", raw, re.I):
                specs["suportaExpo"] = True
            if re.search(r"\b(?:A?RGB)\b", raw, re.I):
                specs["rgb"] = True

        elif categoria == "ARMAZENAMENTO":
            m = re.search(
                r"(?:\b\d+\s+GB\s+)?\b(\d+)\s+GB\s+(NVM|NVME|SATA)\s+Protocol\s+(.+?)\s+Format\s*$",
                raw, re.I,
            )
            if m:
                specs["tipo"] = "SSD"
                specs["capacidadeGb"] = int(m.group(1))
                proto = m.group(2).upper()
                specs["interface"] = "NVMe" if proto in {"NVM", "NVME"} else "SATA"
                specs["formato"] = m.group(3).strip()

        elif categoria == "FONTE":
            m = re.search(r"\b(ATX(?: PS/2)?|SFX(?:-L)?|TFX|Flex-?ATX|PS/2)\s+(\d{2,4})W\s*$", raw, re.I)
            if m:
                specs["formato"] = m.group(1)
                specs["potenciaWatts"] = int(m.group(2))
            cert = re.search(r"\b80\s+PLUS\s+(Bronze|Silver|Gold|Platinum|Titanium)\b", raw, re.I)
            if cert:
                specs["certificacao"] = f"80 PLUS {cert.group(1).title()}"
            low = raw.casefold()
            if "semi-modular" in low or "semi modular" in low:
                specs["modularidade"] = "SEMI_MODULAR"
            elif re.search(r"\bmodular\b", low):
                specs["modularidade"] = "MODULAR"

        elif categoria == "PLACA_VIDEO":
            mem = re.search(r"\b(\d+(?:\.\d+)?)\s+GB\s+(\d+)W\s*$", raw, re.I)
            if mem:
                value = float(mem.group(1))
                specs["memoriaVideoGb"] = int(value) if value.is_integer() else value
                specs["consumoWatts"] = int(mem.group(2))
            # O chipset costuma aparecer imediatamente antes do VRAM/potência.
            gm = re.search(
                r"\b((?:GeForce\s+(?:RTX|GTX|GT|GTS)\s+[^ ]+(?:\s+(?:Ti|SUPER|Super))?(?:\s*\([^)]*\))?)|(?:Radeon\s+(?:RX\s+[^ ]+(?:\s+XT|\s+XTX)?|VII))|(?:Intel\s+Arc\s+[A-Z]\d+))\s+\d+(?:\.\d+)?\s+GB\s+\d+W\s*$",
                raw, re.I,
            )
            if gm:
                specs["gpu"] = re.sub(r"\s*\([^)]*\)", "", gm.group(1)).strip()
                specs["chipset"] = specs["gpu"]
            memory_type = re.search(r"\b(GDDR[3567X]+)\b", raw, re.I)
            if memory_type:
                specs["tipoMemoriaVideo"] = memory_type.group(1).upper()
            bus = re.search(r"\b(\d{2,4})\s*bit\b", raw, re.I)
            if bus:
                specs["barramentoBits"] = int(bus.group(1))

        elif categoria == "COOLER":
            sockets = [re.sub(r"\s+", "", x).upper() for x in re.findall(r"\b(?:AM[2345]|TR4|sTRX4|sTR5|LGA\s*\d{3,4}|\b1[0128]\d{2}\b|2066|2011(?:-V3)?)\b", raw, re.I)]
            if sockets:
                specs["socketsSuportados"] = list(dict.fromkeys(sockets))
            rad = re.search(r"\bRadiator\s+(120|140|240|280|360|420)\s*mm\b", raw, re.I)
            if rad:
                specs["tipo"] = "WATER_COOLER"
                specs["tamanhoRadiadorMm"] = int(rad.group(1))
            elif re.search(r"\b(?:tower|heatpipe|cpu cooler)\b", raw, re.I):
                specs["tipo"] = "AIR_COOLER"
            fan = re.search(r"(?:-|\b)(80|92|100|120|135|140)\s*mm\b", raw, re.I)
            if fan:
                specs["tamanhoVentoinhaMm"] = int(fan.group(1))
            tdp = re.search(r"\bTDP\s*(?:up to\s*)?(\d{2,4})\s*W\b", raw, re.I)
            if tdp:
                specs["capacidadeTermicaWatts"] = int(tdp.group(1))
            height = re.search(r"\bHeight\s*(\d+(?:[.,]\d+)?)\s*mm\b", raw, re.I)
            if height:
                specs["alturaMm"] = float(height.group(1).replace(",", "."))
            rpm = re.search(r"\b(\d{3,5})\s*RPM\b", raw, re.I)
            if rpm:
                specs["velocidadeMaxRpm"] = int(rpm.group(1))
            cfm = re.search(r"\b([0-9]+(?:[.,][0-9]+)?)\s*CFM\b", raw, re.I)
            if cfm:
                specs["fluxoArCfm"] = float(cfm.group(1).replace(",", "."))
            noise = re.search(r"\b([0-9]+(?:[.,][0-9]+)?)\s*dB(?:A)?\b", raw, re.I)
            if noise:
                specs["ruidoDb"] = float(noise.group(1).replace(",", "."))
            if re.search(r"\bARGB\b", raw, re.I):
                specs["argb"] = True
                specs["rgb"] = True
            elif re.search(r"\bRGB\b", raw, re.I):
                specs["rgb"] = True

        elif categoria == "VENTOINHA":
            size = re.search(r"\b(80|92|120|140|200)\s*mm\b", raw, re.I)
            if size:
                specs["tamanhoMm"] = int(size.group(1))
            rpms = [int(x) for x in re.findall(r"\b(\d{3,5})\s*RPM\b", raw, re.I)]
            if rpms:
                specs["rpmMaxima"] = max(rpms)
                if len(rpms) > 1:
                    specs["rpmMinima"] = min(rpms)
            cfm = re.search(r"\b([0-9]+(?:[.,][0-9]+)?)\s*CFM\b", raw, re.I)
            if cfm:
                specs["fluxoArCfm"] = float(cfm.group(1).replace(",", "."))
            pressure = re.search(r"\b([0-9]+(?:[.,][0-9]+)?)\s*mm\s*H2O\b", raw, re.I)
            if pressure:
                specs["pressaoEstaticaMmH2o"] = float(pressure.group(1).replace(",", "."))
            noise = re.search(r"\b([0-9]+(?:[.,][0-9]+)?)\s*dB(?:A)?\b", raw, re.I)
            if noise:
                specs["ruidoDb"] = float(noise.group(1).replace(",", "."))
            if re.search(r"\bPWM\b|4[- ]?pin", raw, re.I):
                specs["pwm"] = True
                specs["conector"] = "PWM_4_PINOS"
            if re.search(r"\bARGB\b", raw, re.I):
                specs["argb"] = True
                specs["rgb"] = True
            elif re.search(r"\bRGB\b", raw, re.I):
                specs["rgb"] = True

        return specs

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
                raw_text = self._norm(link.get_text(" ", strip=True))
                name = self._pc_kombo_name(raw_text, categoria)
                if len(name) < 3 or not re.search(r"[A-Za-z]", name):
                    continue
                if not self._matches_filters(name, marca, consulta):
                    continue
                found.append(DiscoveryCandidate(
                    nome=name,
                    url=urljoin(final, href),
                    fonte="PC_KOMBO",
                    marca=marca,
                    resumo={
                        "catalog_text": raw_text,
                        "specs": self._pc_kombo_summary(raw_text, categoria),
                    },
                ))
            return self._dedupe(found)

        html, final, error = self._fetch_html(url, ["pc-kombo.com"])
        found = parse_page(html, final) if html else []

        # Mesma estratégia do Magazine: se a resposta HTTP parece parcial, usa o
        # navegador cloud na MESMA página e mescla os links renderizados.
        # Em consultas filtradas, não renderiza novamente o catálogo se o HTTP
        # já encontrou ao menos um candidato. Isso corta o principal atraso real.
        sparse_threshold = 1 if consulta else min(6, max(3, int(limit)))
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
        sparse_threshold = 1 if consulta else min(6, max(3, int(limit)))
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
