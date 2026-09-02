from __future__ import annotations

from copy import deepcopy
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from .sources import DiscoveryCandidate, DiscoverySourceCatalog, DEFAULT_SOURCES_BY_CATEGORY
from ..enrichment.core import TechnicalEnricher, technical_coverage, technical_missing_fields, required_missing_fields
from ..enrichment.identity import identity_is_strong
from ..enrichment.providers import (
    ManufacturerProvider, TechPowerUpProvider, PCKomboProvider, GeizhalsProvider,
    CPUWorldProvider, WikiChipProvider, CPUMonkeyProvider, IcecatProvider,
)
from ..extractors.backend_schemas import SCHEMAS, REQUIRED, HARDWARE_CATEGORIES
from ..extractors.ml_specs import extract_specs
from ..utils.normalizers import clean_text


SUPPORTED_DISCOVERY_CATEGORIES = tuple(sorted(HARDWARE_CATEGORIES))

PROVIDER_BY_SOURCE = {
    "ICECAT": IcecatProvider,
    "FABRICANTE_OFICIAL": ManufacturerProvider,
    "CPU_MONKEY": CPUMonkeyProvider,
    "CPU_WORLD": CPUWorldProvider,
    "WIKICHIP": WikiChipProvider,
    "TECHPOWERUP": TechPowerUpProvider,
    "PC_KOMBO": PCKomboProvider,
    "GEIZHALS": GeizhalsProvider,
}

GPU_VENDOR_HINTS = {
    "geforce": "NVIDIA", "quadro": "NVIDIA", "tesla": "NVIDIA", "nvidia": "NVIDIA",
    "radeon": "AMD", "firepro": "AMD", "amd": "AMD", "intel arc": "Intel", "arc ": "Intel",
}

CATEGORY_NOISE = {
    "PROCESSADOR": ["processor", "processador", "cpu", "specifications", "specs", "review"],
    "PLACA_VIDEO": ["graphics card", "video card", "placa de video", "gpu", "specifications", "specs", "review"],
    "PLACA_MAE": ["motherboard", "placa mae", "specifications", "specs", "review"],
    "MEMORIA_RAM": ["memory", "memoria ram", "ram", "specifications", "specs", "review"],
    "ARMAZENAMENTO": ["ssd", "nvme", "storage", "specifications", "specs", "review"],
    "FONTE": ["power supply", "psu", "fonte", "specifications", "specs", "review"],
    "GABINETE": ["pc case", "case", "gabinete", "specifications", "specs", "review"],
    "COOLER": ["cpu cooler", "cooler", "specifications", "specs", "review"],
    "VENTOINHA": ["pc fan", "fan", "ventoinha", "specifications", "specs", "review"],
}


def _clean_candidate_name(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    # Remove sufixos comuns de título SEO sem apagar o modelo.
    text = re.split(r"\s+[|–—]\s+", text, maxsplit=1)[0].strip()
    text = re.sub(r"\s+-\s+(?:Specs?|Specifications?|TechPowerUp|CPU[- ]Monkey|CPU[- ]World).*$", "", text, flags=re.I)
    return text.strip() or None


def _load_known_brands():
    path = Path(__file__).resolve().parents[2] / "config" / "manufacturer_domains.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    preferred = ["Intel", "AMD", "NVIDIA", "ASUS", "MSI", "Gigabyte", "ASRock", "XFX", "Sapphire", "Zotac", "PNY", "PowerColor"]
    canonical = {name.casefold(): name for name in preferred}
    for key in data:
        value = str(key).strip()
        if value:
            canonical.setdefault(value.casefold(), value)
    return sorted(canonical.values(), key=len, reverse=True)


KNOWN_BRANDS = _load_known_brands()


def infer_identity(name: str, categoria: str, brand_hint: str | None = None) -> dict:
    clean = _clean_candidate_name(name) or name
    brand = clean_text(brand_hint)
    low = clean.casefold()

    if not brand and categoria == "PLACA_VIDEO":
        for token, vendor in GPU_VENDOR_HINTS.items():
            if token in low:
                brand = vendor
                break
    if not brand:
        for candidate in KNOWN_BRANDS:
            c = candidate.casefold()
            if low.startswith(c + " ") or low == c or re.search(rf"\b{re.escape(c)}\b", low):
                brand = candidate
                break

    model = clean
    if brand:
        model = re.sub(rf"^\s*{re.escape(brand)}\s+", "", model, flags=re.I).strip()
    for noise in CATEGORY_NOISE.get(categoria, []):
        model = re.sub(rf"\b{re.escape(noise)}\b", " ", model, flags=re.I)
    model = re.sub(r"\s+", " ", model).strip(" -|–—")
    if not model:
        model = clean

    method = "MARCA_MODELO" if brand and model and re.search(r"\d", model) else None
    key = None
    if method:
        norm_brand = re.sub(r"[^a-z0-9]+", "", brand.casefold())
        norm_model = re.sub(r"[^a-z0-9]+", "", model.casefold())
        key = f"{norm_brand}|{norm_model}"
    return {
        "metodo": method,
        "confianca": "ALTA" if method else "INSUFICIENTE",
        "chave": key,
        "marca": brand,
        "modelo": model or None,
        "mpn": None,
        "gtin": None,
    }


def _identity_from_detail(detail: dict, fallback: dict) -> dict:
    brand = clean_text(detail.get("brand")) or fallback.get("marca")
    model = clean_text(detail.get("model")) or fallback.get("modelo")
    mpn = clean_text(detail.get("mpn"))
    gtin = re.sub(r"\D", "", str(detail.get("gtin") or "")) or None
    method = None
    confidence = "INSUFICIENTE"
    key = None
    if gtin and len(gtin) in {8, 12, 13, 14}:
        method, confidence, key = "GTIN", "MUITO_ALTA", gtin
    elif brand and mpn:
        method, confidence = "MARCA_MPN", "MUITO_ALTA"
        key = f"{re.sub(r'[^a-z0-9]+','',brand.casefold())}|{re.sub(r'[^a-z0-9]+','',mpn.casefold())}"
    elif brand and model and re.search(r"\d", model):
        method, confidence = "MARCA_MODELO", "ALTA"
        key = f"{re.sub(r'[^a-z0-9]+','',brand.casefold())}|{re.sub(r'[^a-z0-9]+','',model.casefold())}"
    return {"metodo": method, "confianca": confidence, "chave": key, "marca": brand, "modelo": model, "mpn": mpn, "gtin": gtin}


def _provider_for_candidate(candidate: DiscoveryCandidate):
    cls = PROVIDER_BY_SOURCE.get(candidate.fonte)
    return cls() if cls else None


class HardwareDiscoveryService:
    def __init__(self, catalog=None):
        self.catalog = catalog or DiscoverySourceCatalog()
        try:
            self.request_budget = max(10.0, float(os.getenv("DISCOVERY_TOTAL_TIMEOUT_SECONDS", "75")))
        except ValueError:
            self.request_budget = 75.0
        try:
            self.detail_enrichment_timeout = max(2.0, float(os.getenv("DISCOVERY_ENRICHMENT_TIMEOUT_SECONDS", "6")))
        except ValueError:
            self.detail_enrichment_timeout = 6.0
        try:
            self.detail_enrichment_sources = max(1, int(os.getenv("DISCOVERY_ENRICHMENT_MAX_SOURCES", "2")))
        except ValueError:
            self.detail_enrichment_sources = 2

    @staticmethod
    def source_capabilities():
        return {
            "categorias": list(SUPPORTED_DISCOVERY_CATEGORIES),
            "fontesPadraoPorCategoria": deepcopy(DEFAULT_SOURCES_BY_CATEGORY),
            "fontesTecnicas": [
                {"id": "ICECAT", "papel": ["ENRIQUECIMENTO_API"], "categorias": list(SUPPORTED_DISCOVERY_CATEGORIES), "configuracaoOpcional": ["ICECAT_USERNAME", "ICECAT_API_TOKEN", "ICECAT_CONTENT_TOKEN"]},
                {"id": "PC_KOMBO", "papel": ["DESCOBERTA", "DETALHE"], "categorias": ["PROCESSADOR", "PLACA_MAE", "MEMORIA_RAM", "PLACA_VIDEO", "ARMAZENAMENTO", "FONTE", "GABINETE", "COOLER", "VENTOINHA"]},
                {"id": "CPU_MONKEY", "papel": ["DESCOBERTA", "DETALHE"], "categorias": ["PROCESSADOR"]},
                {"id": "CPU_WORLD", "papel": ["CONFIRMACAO", "ENRIQUECIMENTO"], "categorias": ["PROCESSADOR"]},
                {"id": "WIKICHIP", "papel": ["CONFIRMACAO", "ENRIQUECIMENTO"], "categorias": ["PROCESSADOR", "PLACA_VIDEO"]},
                {"id": "TECHPOWERUP", "papel": ["DESCOBERTA", "DETALHE", "ENRIQUECIMENTO"], "categorias": ["PLACA_VIDEO"]},
                {"id": "GEIZHALS", "papel": ["CONFIRMACAO", "ENRIQUECIMENTO"], "categorias": list(SUPPORTED_DISCOVERY_CATEGORIES)},
                {"id": "FABRICANTE_OFICIAL", "papel": ["CONFIRMACAO", "ENRIQUECIMENTO"], "categorias": list(SUPPORTED_DISCOVERY_CATEGORIES)},
            ],
            "regras": {
                "somenteHardware": True,
                "incluiPreco": False,
                "backendDeveFiltrarJaCadastrados": True,
                "deduplicacaoSugerida": ["GTIN", "MARCA_MPN", "MARCA_MODELO", "NOME_NORMALIZADO"],
                "cadastroAutomatico": False,
                "descobertaUsaCatalogoQuandoDisponivel": True,
                "buscaGenericaNaoEhFontePrimaria": True,
            },
        }

    def _detail_candidate(self, candidate: DiscoveryCandidate, categoria: str, enrich: bool, no_browser: bool = False):
        inferred = infer_identity(candidate.nome, categoria, candidate.marca)
        provider = _provider_for_candidate(candidate)
        detail = {"ok": False, "fonte": candidate.fonte, "url": candidate.url, "erro": "SEM_PROVEDOR"}

        if provider and identity_is_strong(inferred):
            # Em descoberta, noBrowser também impede fallback cloud das fontes técnicas.
            if no_browser:
                provider.allow_browser_fallback = False
                if getattr(provider, "resolver", None) is not None:
                    provider.resolver.allow_browser_fallback = False
            try:
                detail = provider.fetch_candidate(candidate.url, inferred)
                detail.setdefault("fonte", candidate.fonte)
                if detail.get("ok") and candidate.fonte == "CPU_MONKEY":
                    CPUMonkeyProvider._normalize_cpu_monkey(detail)
            except Exception as exc:
                detail = {"ok": False, "fonte": candidate.fonte, "url": candidate.url, "erro": f"ERRO_DETALHE: {type(exc).__name__}: {exc}"}

        identity = _identity_from_detail(detail, inferred) if detail.get("ok") else inferred
        attrs = detail.get("attributes") or []
        catalog_text = (candidate.resumo or {}).get("catalog_text") or candidate.nome
        context = detail.get("context_text") or catalog_text
        specs = dict((candidate.resumo or {}).get("specs") or {})
        extracted = extract_specs(categoria, attrs, context_text=context)
        for key, value in (extracted or {}).items():
            if value not in (None, "", []):
                specs[key] = value
        schema = SCHEMAS[categoria]
        spec_field = schema[1]
        expected = schema[2] or []
        nome = _clean_candidate_name(detail.get("title")) or _clean_candidate_name(candidate.nome) or candidate.nome
        payload = {
            "nome": nome,
            "marca": identity.get("marca"),
            "modelo": identity.get("modelo"),
            "descricao": None,
            "mpn": identity.get("mpn"),
            "gtin": identity.get("gtin"),
            "imagemUrl": detail.get("image_url"),
            "categoria": categoria,
        }
        if spec_field:
            payload[spec_field] = specs

        result = {
            "categoriaDetectada": categoria,
            "tipoCadastro": "HARDWARE",
            "payloadParcialBackend": payload,
            "especificacoesEncontradas": specs,
            "camposEspecificacaoEsperados": expected,
            "camposObrigatoriosAusentes": [f for f in REQUIRED.get(categoria, []) if specs.get(f) in (None, "", [])],
        }

        enrichment_disabled = os.getenv("ENRICHMENT_DISABLE", "false").strip().casefold() in {"1", "true", "sim", "yes"}
        if enrich and not enrichment_disabled and identity_is_strong(identity) and technical_missing_fields(result):
            enricher = TechnicalEnricher(
                auto_mode=True,
                total_timeout_override=self.detail_enrichment_timeout,
                max_sources_override=self.detail_enrichment_sources,
                source_timeout_override=max(2, int(self.detail_enrichment_timeout / max(1, self.detail_enrichment_sources))),
            )
            result = enricher.enrich(result)

        specs = result.get("especificacoesEncontradas") or {}
        payload = result.get("payloadParcialBackend") or payload
        identity_final = _identity_from_detail({
            "brand": payload.get("marca"), "model": payload.get("modelo"), "mpn": payload.get("mpn"), "gtin": payload.get("gtin")
        }, identity)
        info = result.get("enriquecimentoTecnico") or {}
        source_list = [{
            "fonte": candidate.fonte,
            "url": detail.get("url") or candidate.url,
            "ok": bool(detail.get("ok")),
            "erro": detail.get("erro"),
            "modoColeta": detail.get("modoColeta"),
        }]
        source_list.extend(info.get("fontesConsultadas") or [])
        # Remove repetições de fonte/url preservando ordem.
        unique_sources = []
        seen = set()
        for source in source_list:
            key = (source.get("fonte"), source.get("url"))
            if key in seen:
                continue
            seen.add(key)
            unique_sources.append(source)

        return {
            "identidade": identity_final,
            "chaveComparacao": identity_final.get("chave"),
            "payloadHardware": payload,
            "especificacoesEncontradas": specs,
            "camposEsperados": result.get("camposEspecificacaoEsperados") or expected,
            "camposAusentes": technical_missing_fields(result),
            "camposObrigatoriosAusentes": required_missing_fields(result),
            "coberturaTecnica": round(technical_coverage(result), 4),
            "fontes": unique_sources,
            "origemPorCampo": info.get("origemPorCampo") or {},
            "conflitos": info.get("conflitos") or [],
            "urlFontePrincipal": detail.get("url") or candidate.url,
            "fontePrincipal": candidate.fonte,
            "detalhesColetados": bool(detail.get("ok")),
            "erroDetalhamento": detail.get("erro"),
            "preco": None,
        }

    @staticmethod
    def _dedupe_items(items):
        output = []
        seen = set()
        for item in items:
            ident = item.get("identidade") or {}
            key = item.get("chaveComparacao")
            if not key:
                payload = item.get("payloadHardware") or {}
                name = re.sub(r"[^a-z0-9]+", "", str(payload.get("nome") or "").casefold())
                key = f"nome:{name}" if name else None
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            output.append(item)
        return output

    def discover(self, categoria: str, marca=None, consulta=None, fontes=None, pagina=1, limite=20, detalhar=True, enriquecer=True, no_browser=False):
        categoria = str(categoria or "").strip().upper()
        if categoria not in HARDWARE_CATEGORIES:
            raise ValueError(f"Categoria não suportada para descoberta de Hardware: {categoria}")
        pagina = max(1, int(pagina))
        limite = min(50, max(1, int(limite)))
        # Busca candidatos suficientes para preencher a página solicitada.
        needed = min(200, pagina * limite + limite)
        started = time.monotonic()
        old_browser_policy = getattr(self.catalog, "allow_browser_fallback", True)
        resolver = getattr(self.catalog, "resolver", None)
        old_resolver_policy = getattr(resolver, "allow_browser_fallback", True) if resolver is not None else None
        if hasattr(self.catalog, "allow_browser_fallback"):
            self.catalog.allow_browser_fallback = not bool(no_browser)
        if resolver is not None and hasattr(resolver, "allow_browser_fallback"):
            resolver.allow_browser_fallback = not bool(no_browser)
        try:
            candidates, diagnostics = self.catalog.discover(
                categoria=categoria, marca=marca, consulta=consulta, fontes=fontes, limit=needed,
            )
        finally:
            if hasattr(self.catalog, "allow_browser_fallback"):
                self.catalog.allow_browser_fallback = old_browser_policy
            if resolver is not None and hasattr(resolver, "allow_browser_fallback") and old_resolver_policy is not None:
                resolver.allow_browser_fallback = old_resolver_policy
        start = (pagina - 1) * limite
        page_candidates = candidates[start:start + limite]
        items = []
        interrupted = False
        for candidate in page_candidates:
            if (time.monotonic() - started) >= self.request_budget:
                interrupted = True
                break
            if detalhar:
                item = self._detail_candidate(candidate, categoria, bool(enriquecer), no_browser=no_browser)
            else:
                identity = infer_identity(candidate.nome, categoria, candidate.marca)
                schema = SCHEMAS[categoria]
                payload = {
                    "nome": _clean_candidate_name(candidate.nome) or candidate.nome,
                    "marca": identity.get("marca"),
                    "modelo": identity.get("modelo"),
                    "descricao": None,
                    "mpn": None,
                    "gtin": None,
                    "imagemUrl": None,
                    "categoria": categoria,
                }
                catalog_text = (candidate.resumo or {}).get("catalog_text") or candidate.nome
                specs = dict((candidate.resumo or {}).get("specs") or {})
                extracted = extract_specs(categoria, [], context_text=catalog_text)
                for key, value in (extracted or {}).items():
                    if value not in (None, "", []):
                        specs[key] = value
                if schema[1]:
                    payload[schema[1]] = specs
                expected_fields = schema[2] or []
                missing = [f for f in expected_fields if specs.get(f) in (None, "", [])]
                required_missing = [f for f in REQUIRED.get(categoria, []) if specs.get(f) in (None, "", [])]
                coverage = (len(expected_fields) - len(missing)) / len(expected_fields) if expected_fields else 0.0
                item = {
                    "identidade": identity,
                    "chaveComparacao": identity.get("chave"),
                    "payloadHardware": payload,
                    "especificacoesEncontradas": specs,
                    "camposEsperados": expected_fields,
                    "camposAusentes": missing,
                    "camposObrigatoriosAusentes": required_missing,
                    "coberturaTecnica": round(coverage, 4),
                    "fontes": [{"fonte": candidate.fonte, "url": candidate.url, "ok": True, "erro": None}],
                    "origemPorCampo": {},
                    "conflitos": [],
                    "urlFontePrincipal": candidate.url,
                    "fontePrincipal": candidate.fonte,
                    "detalhesColetados": False,
                    "erroDetalhamento": None,
                    "preco": None,
                }
            # Contrato amigável ao backend: além do payloadHardware histórico,
            # expõe payload/statusFicha/qualidade/idTemporario diretamente.
            payload_for_backend = item.get("payloadHardware") or {}
            required_missing = item.get("camposObrigatoriosAusentes") or []
            conflicts = item.get("conflitos") or []
            if conflicts:
                status_ficha = "PRECISA_REVISAO"
            elif required_missing:
                status_ficha = "FICHA_INCOMPLETA"
            else:
                status_ficha = "PRONTO"
            quality = int(round(float(item.get("coberturaTecnica") or 0) * 100))
            identity_bonus = 10 if (item.get("identidade") or {}).get("metodo") else 0
            item["qualidade"] = min(100, quality + identity_bonus)
            item["statusFicha"] = status_ficha
            item["payload"] = payload_for_backend
            base_temp = item.get("chaveComparacao") or str(payload_for_backend.get("nome") or candidate.nome)
            temp_slug = re.sub(r"[^a-z0-9]+", "-", str(base_temp).casefold()).strip("-")[:100]
            item["idTemporario"] = f"{categoria.casefold()}-{temp_slug}"
            item["avisos"] = list(item.get("avisos") or [])
            if required_missing:
                item["avisos"].append("Ficha técnica parcial; campos ausentes podem ser detalhados/enriquecidos antes do cadastro.")
            items.append(item)

        items = self._dedupe_items(items)
        return {
            "modo": "DESCOBERTA_HARDWARES",
            "categoria": categoria,
            "marcaFiltro": clean_text(marca),
            "consulta": clean_text(consulta),
            "pagina": pagina,
            "limite": limite,
            "totalCandidatosDescobertos": len(candidates),
            "quantidadeRetornada": len(items),
            "temMais": (start + limite) < len(candidates),
            "interrompidoPorTimeout": interrupted,
            "itens": items,
            "fontesConsultadas": diagnostics,
            "politica": {
                "somenteHardware": True,
                "precoNaoColetado": True,
                "cadastroAutomatico": False,
                "backendDeveOcultarJaCadastrados": True,
                "backendDeveConfirmarAntesDeCadastrar": True,
                "semCrawlerEmMassa": True,
            },
            "duracaoMs": int((time.monotonic() - started) * 1000),
        }

    def detail(self, categoria: str, nome: str, url: str, fonte: str, marca=None, enriquecer=True, no_browser=False):
        categoria = str(categoria or "").strip().upper()
        if categoria not in HARDWARE_CATEGORIES:
            raise ValueError(f"Categoria não suportada para descoberta de Hardware: {categoria}")
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL técnica inválida")
        candidate = DiscoveryCandidate(nome=nome, url=url, fonte=str(fonte or "").strip().upper(), marca=marca)
        return self._detail_candidate(candidate, categoria, bool(enriquecer), no_browser=no_browser)
