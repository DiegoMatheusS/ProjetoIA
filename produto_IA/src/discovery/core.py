from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from .sources import DiscoveryCandidate, DiscoverySourceCatalog, DEFAULT_SOURCES_BY_CATEGORY
from ..enrichment.core import TechnicalEnricher, technical_coverage, technical_missing_fields, required_missing_fields, essential_missing_fields, technical_status, complete_specs
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

SOURCE_LABELS = {
    "ICECAT": "Icecat",
    "FABRICANTE_OFICIAL": "Fabricante oficial",
    "CPU_MONKEY": "CPU-Monkey",
    "CPU_WORLD": "CPU-World",
    "WIKICHIP": "WikiChip",
    "TECHPOWERUP": "TechPowerUp",
    "PC_KOMBO": "PC-Kombo",
    "GEIZHALS": "Geizhals",
}


def _source_label(value: str | None) -> str | None:
    if not value:
        return None
    key = str(value).strip().upper()
    return SOURCE_LABELS.get(key, str(value).strip())


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
            # Orçamento global da busca. v14.20.1 evita deixar o frontend preso por
            # vários minutos quando uma fonte externa está lenta/bloqueada.
            self.request_budget = max(15.0, float(os.getenv("DISCOVERY_TOTAL_TIMEOUT_SECONDS", "45")))
        except ValueError:
            self.request_budget = 45.0
        try:
            self.detail_enrichment_timeout = max(2.0, float(os.getenv("DISCOVERY_ENRICHMENT_TIMEOUT_SECONDS", "6")))
        except ValueError:
            self.detail_enrichment_timeout = 6.0
        try:
            self.detail_enrichment_sources = max(1, int(os.getenv("DISCOVERY_ENRICHMENT_MAX_SOURCES", "2")))
        except ValueError:
            self.detail_enrichment_sources = 2
        try:
            self.detail_workers = min(10, max(1, int(os.getenv("DISCOVERY_DETAIL_WORKERS", "8"))))
        except ValueError:
            self.detail_workers = 8
        try:
            self.detail_source_timeout = max(2, int(os.getenv("DISCOVERY_DETAIL_SOURCE_TIMEOUT_SECONDS", "4")))
        except ValueError:
            self.detail_source_timeout = 4
        try:
            self.bulk_target_coverage = float(os.getenv("DISCOVERY_BULK_TARGET_COVERAGE", "0.82"))
        except ValueError:
            self.bulk_target_coverage = 0.82
        self.bulk_target_coverage = min(1.0, max(0.60, self.bulk_target_coverage))
        self.bulk_browser_fallback = os.getenv(
            "DISCOVERY_BULK_BROWSER_FALLBACK", "false"
        ).strip().casefold() in {"1", "true", "sim", "yes"}

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
                "detalhamentoPorPadrao": True,
                "enriquecimentoPorPadrao": True,
                "prioridade": "QUALIDADE_DA_FICHA",
                "buscaGenericaNaoEhFontePrimaria": True,
                "retornaTodosCamposDoSchema": True,
                "enriquecimentoSeletivo": True,
                "metaCoberturaBuscaLote": 0.82,
            },
        }

    def _detail_candidate(self, candidate: DiscoveryCandidate, categoria: str, enrich: bool, no_browser: bool = False, bulk_mode: bool = False):
        inferred = infer_identity(candidate.nome, categoria, candidate.marca)
        provider = _provider_for_candidate(candidate)
        detail = {"ok": False, "fonte": candidate.fonte, "url": candidate.url, "erro": "SEM_PROVEDOR"}

        if provider and bulk_mode:
            # Busca em lote usa timeout curto por candidato; o detalhe individual
            # continua com os limites completos.
            if hasattr(provider, "timeout"):
                provider.timeout = min(int(provider.timeout), self.detail_source_timeout)
            limiter = getattr(provider, "rate_limiter", None)
            if limiter is not None:
                limiter.min_delay = min(limiter.min_delay, 0.20)
                limiter.jitter = min(limiter.jitter, 0.08)
            resolver = getattr(provider, "resolver", None)
            if resolver is not None:
                if hasattr(resolver, "timeout"):
                    resolver.timeout = min(int(resolver.timeout), self.detail_source_timeout)
                resolver_limiter = getattr(resolver, "rate_limiter", None)
                if resolver_limiter is not None:
                    resolver_limiter.min_delay = min(resolver_limiter.min_delay, 0.20)
                    resolver_limiter.jitter = min(resolver_limiter.jitter, 0.08)

        if provider and identity_is_strong(inferred):
            # Em descoberta em lote, não abrimos uma sessão Surfsky para cada
            # candidato por padrão. Isso era capaz de manter a requisição aberta
            # por vários minutos. O detalhe individual continua podendo usar
            # fallback cloud completo.
            disable_browser = bool(no_browser) or (bool(bulk_mode) and not self.bulk_browser_fallback)
            if disable_browser:
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
                target_coverage_override=self.bulk_target_coverage if bulk_mode else 1.0,
                excluded_sources={candidate.fonte} if bulk_mode else None,
            )
            if bool(bulk_mode) and not self.bulk_browser_fallback:
                for source_provider in enricher.providers:
                    source_provider.allow_browser_fallback = False
                    resolver = getattr(source_provider, "resolver", None)
                    if resolver is not None:
                        resolver.allow_browser_fallback = False
            result = enricher.enrich(result)

        specs = complete_specs(categoria, result.get("especificacoesEncontradas") or {})
        result["especificacoesEncontradas"] = specs
        payload = result.get("payloadParcialBackend") or payload
        if spec_field:
            payload[spec_field] = specs
        identity_final = _identity_from_detail({
            "brand": payload.get("marca"), "model": payload.get("modelo"), "mpn": payload.get("mpn"), "gtin": payload.get("gtin")
        }, identity)
        info = result.get("enriquecimentoTecnico") or {}
        source_list = [{
            "fonte": candidate.fonte,
            "url": detail.get("url") or candidate.url,
            # A fonte de catálogo foi usada mesmo quando a abertura da ficha
            # individual falhou. Mantemos o diagnóstico separado.
            "ok": True,
            "detalheOk": bool(detail.get("ok")),
            "erro": detail.get("erro"),
            "modoColeta": detail.get("modoColeta") or "CATALOGO",
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
            "camposEssenciaisAusentes": essential_missing_fields(result),
            "coberturaTecnica": round(technical_coverage(result), 4),
            "fontes": list(dict.fromkeys(
                label
                for source in unique_sources
                if source.get("ok") is not False
                for label in [_source_label(source.get("fonte"))]
                if label
            )),
            "fontesDetalhadas": unique_sources,
            "fonte": _source_label(candidate.fonte),
            "fonteCatalogo": candidate.fonte,
            "origem": candidate.fonte,
            "urlOrigem": candidate.url,
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
        detailed_items = {}

        # v14.20.1: a v14.20 detalhava cada candidato em sequência. Com 20
        # candidatos e múltiplas fontes isso podia segurar a resposta por muitos
        # minutos. Agora os detalhes são consultados em paralelo, com concorrência
        # limitada e orçamento global. Qualidade continua sendo a prioridade, mas
        # uma fonte lenta não bloqueia toda a página indefinidamente.
        if detalhar and page_candidates:
            workers = min(self.detail_workers, len(page_candidates))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hardware-discovery") as executor:
                # Trabalha em lotes do tamanho da concorrência. Assim, quando o
                # orçamento global termina, não ficam dezenas de tarefas pendentes
                # rodando depois que a resposta já foi devolvida.
                for batch_start in range(0, len(page_candidates), workers):
                    if (time.monotonic() - started) >= self.request_budget:
                        interrupted = True
                        break
                    batch = page_candidates[batch_start:batch_start + workers]
                    futures = {
                        executor.submit(
                            self._detail_candidate, candidate, categoria, bool(enriquecer), no_browser, True
                        ): batch_start + offset
                        for offset, candidate in enumerate(batch)
                    }
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            detailed_items[idx] = future.result()
                        except Exception as exc:
                            detailed_items[idx] = {"erroDetalhamento": f"ERRO_DETALHE: {type(exc).__name__}: {exc}"}
                    if (time.monotonic() - started) >= self.request_budget and batch_start + workers < len(page_candidates):
                        interrupted = True
                        break

        for idx, candidate in enumerate(page_candidates):
            if detalhar and idx in detailed_items and detailed_items[idx].get("payloadHardware"):
                item = detailed_items[idx]
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
                specs = complete_specs(categoria, specs)
                if schema[1]:
                    payload[schema[1]] = specs
                expected_fields = schema[2] or []
                missing = [f for f in expected_fields if specs.get(f) in (None, "", [])]
                required_missing = [f for f in REQUIRED.get(categoria, []) if specs.get(f) in (None, "", [])]
                coverage_input = {"categoriaDetectada": categoria, "especificacoesEncontradas": specs}
                coverage = technical_coverage(coverage_input)
                item = {
                    "identidade": identity,
                    "chaveComparacao": identity.get("chave"),
                    "payloadHardware": payload,
                    "especificacoesEncontradas": specs,
                    "camposEsperados": expected_fields,
                    "camposAusentes": missing,
                    "camposObrigatoriosAusentes": required_missing,
                    "camposEssenciaisAusentes": essential_missing_fields(coverage_input),
                    "coberturaTecnica": round(coverage, 4),
                    "fontes": [_source_label(candidate.fonte)],
                    "fontesDetalhadas": [{"fonte": candidate.fonte, "url": candidate.url, "ok": True, "erro": None}],
                    "fonte": _source_label(candidate.fonte),
                    "fonteCatalogo": candidate.fonte,
                    "origem": candidate.fonte,
                    "urlOrigem": candidate.url,
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
            schema = SCHEMAS[categoria]
            spec_field = schema[1]
            completed_specs = complete_specs(categoria, item.get("especificacoesEncontradas") or {})
            item["especificacoesEncontradas"] = completed_specs
            if spec_field:
                payload_for_backend[spec_field] = completed_specs
            item["payloadHardware"] = payload_for_backend
            missing_input = {
                "categoriaDetectada": categoria,
                "especificacoesEncontradas": completed_specs,
            }
            item["camposAusentes"] = technical_missing_fields(missing_input)
            item["camposObrigatoriosAusentes"] = required_missing_fields(missing_input)
            required_missing = item["camposObrigatoriosAusentes"]
            conflicts = item.get("conflitos") or []
            status_input = {
                "categoriaDetectada": categoria,
                "especificacoesEncontradas": completed_specs,
                "conflitos": conflicts,
            }
            item["coberturaTecnica"] = round(technical_coverage(status_input), 4)
            item["camposEssenciaisAusentes"] = essential_missing_fields(status_input)
            item["statusFicha"] = technical_status(status_input, conflicts=conflicts)
            item["qualidade"] = int(round(float(item.get("coberturaTecnica") or 0) * 100))
            item["payload"] = payload_for_backend
            base_temp = item.get("chaveComparacao") or str(payload_for_backend.get("nome") or candidate.nome)
            temp_slug = re.sub(r"[^a-z0-9]+", "-", str(base_temp).casefold()).strip("-")[:100]
            item["idTemporario"] = f"{categoria.casefold()}-{temp_slug}"
            item["avisos"] = list(item.get("avisos") or [])
            if detalhar and not item.get("detalhesColetados"):
                if interrupted or idx not in detailed_items:
                    item["avisos"].append("Detalhamento técnico não concluiu dentro do orçamento desta busca; tente detalhar este item individualmente.")
            if required_missing:
                item["avisos"].append("Ficha técnica ainda parcial após as consultas disponíveis; revise os campos ausentes antes do cadastro.")
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
                "consultaTecnicaDuranteDescoberta": bool(detalhar and enriquecer),
                "prioridade": "QUALIDADE_DA_FICHA_COM_LATENCIA_CONTROLADA",
                "retornaTodosCamposDoSchema": True,
                "metaCoberturaBuscaLote": self.bulk_target_coverage,
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
        return self._detail_candidate(candidate, categoria, bool(enriquecer), no_browser=no_browser, bulk_mode=False)
