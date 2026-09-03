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
            "title": parsed.get("title"),
            "brand": parsed.get("brand"),
            "model": parsed.get("model"),
            "mpn": parsed.get("mpn"),
            "gtin": parsed.get("gtin"),
            "image_url": parsed.get("image_url"),
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

    def supports(self, category, identity):
        # Evita gastar uma das poucas consultas do lote quando a marca não possui
        # domínio oficial configurado.
        return bool(self.search_domains(identity))


class IcecatProvider(ExternalTechnicalProvider):
    """Open Icecat estruturado para completar fichas por GTIN ou marca+MPN.

    O Icecat não é usado como crawler de catálogo aqui. Ele entra depois que uma
    fonte de descoberta já identificou o SKU, o que evita busca genérica e aproveita
    a API estruturada oficial.
    """

    name = "ICECAT"
    domains = ("live.icecat.biz", "icecat.biz", "icecat.com")
    categories = {
        "PROCESSADOR", "PLACA_MAE", "MEMORIA_RAM", "PLACA_VIDEO",
        "ARMAZENAMENTO", "FONTE", "GABINETE", "COOLER",
        "VENTOINHA", "MONITOR", "NOTEBOOK",
    }

    def __init__(self, resolver=None, session=None):
        super().__init__(resolver=resolver, session=session)
        self.api_url = os.getenv("ICECAT_API_URL", "https://live.icecat.biz/api/").strip()
        self.username = os.getenv("ICECAT_USERNAME", "").strip()
        self.api_token = os.getenv("ICECAT_API_TOKEN", "").strip()
        self.content_token = os.getenv("ICECAT_CONTENT_TOKEN", "").strip()
        self.lang = (os.getenv("ICECAT_LANG", "EN").strip() or "EN").upper()
        try:
            self.timeout = max(2, int(os.getenv("ICECAT_TIMEOUT_SECONDS", "8")))
        except ValueError:
            self.timeout = 8
        self.allow_browser_fallback = False

    @property
    def configured(self):
        return bool(self.username)

    def supports(self, category, identity):
        if not self.configured or category not in self.categories:
            return False
        gtin = str((identity or {}).get("gtin") or "").strip()
        brand = str((identity or {}).get("marca") or "").strip()
        mpn = str((identity or {}).get("mpn") or "").strip()
        return bool(gtin or (brand and mpn))

    @staticmethod
    def _feature_attributes(data):
        attrs = []
        seen = set()
        for group in data.get("FeaturesGroups") or data.get("FeatureGroups") or []:
            if not isinstance(group, dict):
                continue
            for item in group.get("Features") or []:
                if not isinstance(item, dict):
                    continue
                feature = item.get("Feature") or {}
                name_obj = feature.get("Name") or {}
                name = name_obj.get("Value") if isinstance(name_obj, dict) else name_obj
                value = item.get("PresentationValue")
                if value in (None, ""):
                    value = item.get("RawValue")
                if value in (None, ""):
                    value = item.get("Value")
                name = clean_text(name)
                value = clean_text(value)
                if not name or not value:
                    continue
                key = (name.casefold(), value.casefold())
                if key in seen:
                    continue
                seen.add(key)
                attrs.append({"id": str(item.get("ID") or feature.get("ID") or "") or None, "name": name, "value_name": value})
                if len(attrs) >= 300:
                    return attrs
        return attrs

    @staticmethod
    def _extract_data(payload):
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        # Algumas integrações/bibliotecas já devolvem apenas o objeto interno.
        if "GeneralInfo" in payload:
            return payload
        return {}

    def collect(self, identity, category):
        if not self.supports(category, identity):
            return {"ok": False, "fonte": self.name, "erro": "ICECAT_NAO_CONFIGURADO_OU_IDENTIDADE_INSUFICIENTE"}

        params = {"lang": self.lang, "shopname": self.username}
        gtin = str(identity.get("gtin") or "").strip()
        brand = str(identity.get("marca") or "").strip()
        mpn = str(identity.get("mpn") or "").strip()
        if gtin:
            params["GTIN"] = gtin
        else:
            params["Brand"] = brand
            params["ProductCode"] = mpn
        params["content"] = "essentialinfo,title,gallery,featuregroups"

        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["api-token"] = self.api_token
        if self.content_token:
            headers["content-token"] = self.content_token

        try:
            self.rate_limiter.wait(self.api_url)
            response = self.session.get(self.api_url, params=params, headers=headers, timeout=self.timeout, allow_redirects=True)
            if response.status_code in {401, 403}:
                return {"ok": False, "fonte": self.name, "url": self.api_url, "erro": f"ICECAT_HTTP_{response.status_code}"}
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "fonte": self.name, "url": self.api_url, "erro": f"ICECAT_API_ERRO: {type(exc).__name__}"}

        data = self._extract_data(payload)
        if not data:
            message = payload.get("message") if isinstance(payload, dict) else None
            return {"ok": False, "fonte": self.name, "url": self.api_url, "erro": clean_text(message) or "ICECAT_PRODUTO_NAO_ENCONTRADO"}

        general = data.get("GeneralInfo") or {}
        brand_info = general.get("BrandInfo") or {}
        returned_brand = clean_text(general.get("Brand")) or clean_text(brand_info.get("BrandName"))
        returned_mpn = clean_text(general.get("BrandPartCode"))
        gtins = general.get("GTIN") or general.get("GTINs") or []
        if isinstance(gtins, str):
            returned_gtin = clean_text(gtins)
        elif isinstance(gtins, list):
            first = gtins[0] if gtins else None
            returned_gtin = clean_text(first.get("GTIN") if isinstance(first, dict) else first)
        else:
            returned_gtin = None

        # A requisição já é por identificador forte, mas validamos a resposta para
        # não misturar uma ficha de outro SKU por erro externo.
        if gtin and returned_gtin and ''.join(filter(str.isdigit, returned_gtin)) != ''.join(filter(str.isdigit, gtin)):
            return {"ok": False, "fonte": self.name, "url": self.api_url, "erro": "ICECAT_IDENTIDADE_DIVERGENTE"}
        if not gtin and brand and returned_brand and returned_brand.casefold() != brand.casefold():
            return {"ok": False, "fonte": self.name, "url": self.api_url, "erro": "ICECAT_MARCA_DIVERGENTE"}

        title = clean_text(general.get("Title")) or clean_text(general.get("ProductName"))
        model = clean_text(general.get("ProductName")) or returned_mpn
        image = data.get("Image") or {}
        image_url = None
        if isinstance(image, dict):
            image_url = clean_text(image.get("HighPic")) or clean_text(image.get("Pic500x500")) or clean_text(image.get("LowPic"))
        attrs = self._feature_attributes(data)
        context = "\n".join(filter(None, [
            title, returned_brand, model, returned_mpn, returned_gtin,
            "\n".join(f"{a['name']}: {a['value_name']}" for a in attrs),
        ]))
        return {
            "ok": bool(title or returned_mpn or returned_gtin),
            "fonte": self.name,
            "url": self.api_url,
            "title": title,
            "brand": returned_brand or brand,
            "model": model,
            "mpn": returned_mpn or mpn or None,
            "gtin": returned_gtin or gtin or None,
            "image_url": image_url,
            "attributes": attrs,
            "context_text": context,
            "modoColeta": "ICECAT_JSON_API",
        }


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
