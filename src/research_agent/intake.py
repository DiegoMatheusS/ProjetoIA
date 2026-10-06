"""Pesquisa para preencher cadastros somente com especificações documentadas."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from urllib.parse import urlparse

from ..enrichment.identity import build_identity, identity_is_strong
from ..enrichment.core import technical_coverage, technical_missing_fields, required_missing_fields
from ..enrichment.providers import ManufacturerProvider
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_specs_for_backend
from .agent import research_hardware_locally
from .confidence import annotate_field_confidence

TECHNICAL_DOMAINS = {
    "TECHPOWERUP": ("techpowerup.com",), "CPU_WORLD": ("cpu-world.com",),
    "CPU_MONKEY": ("cpu-monkey.com",), "WIKICHIP": ("wikichip.org",),
    "ICECAT": ("icecat.biz", "icecat.com"), "GEIZHALS": ("geizhals.eu", "geizhals.de", "geizhals.at"),
    "PC_KOMBO": ("pc-kombo.com",), "PANGOLY": ("pangoly.com",),
}
# Uma GPU genérica identifica o chip, não uma placa ASUS/MSI/Sapphire específica.
GPU_CHIP_FIELDS = {"gpu", "chipset", "arquitetura", "memoriaVideoGb", "tipoMemoriaVideo", "barramentoBits", "geracaoPcie", "larguraPcie"}


def missing(value):
    return value is None or value == "" or value == []


def identity_from_name(category, name, brand=None, model=None):
    """Usa o nome como consulta; nenhuma especificação vem desta inferência."""
    name = str(name or "").strip()
    if category == "PROCESSADOR":
        match = re.search(r"\bRyzen\s+(?:[3579]\s+)?(?:PRO\s+)?\d{4,5}[A-Z0-9]*\b", name, re.I)
        if match:
            return {"marca": brand or "AMD", "modelo": model or match.group(0), "escopo": "MODELO_EXATO"}
        match = re.search(r"\b(?:Core\s+)?(?:i[3579][ -]+\d{4,5}[A-Z]*|Core\s+Ultra\s+[579]\s+\d{3}[A-Z]*)\b", name, re.I)
        if match:
            cpu = match.group(0)
            return {"marca": brand or "Intel", "modelo": model or (cpu if cpu.lower().startswith("core") else "Core " + cpu), "escopo": "MODELO_EXATO"}
    from ..discovery.core import infer_identity, KNOWN_BRANDS
    if not brand:
        brand = next((candidate for candidate in KNOWN_BRANDS
                      if re.search(r"(?<![a-z0-9])" + re.escape(candidate) + r"(?![a-z0-9])", name, re.I)), None)
    if not brand and category == "PLACA_VIDEO":
        brand = "AMD" if re.search(r"\bRX\s*\d{3,4}", name, re.I) else "NVIDIA" if re.search(r"\b(?:RTX|GTX)\s*\d{3,4}", name, re.I) else None
    hint = infer_identity(model or name, category, brand)
    if model:
        hint["modelo"] = model
    hint["escopo"] = "MODELO_EXATO"
    if category == "PLACA_VIDEO" and str(hint.get("marca") or "").upper() in {"AMD", "NVIDIA", "INTEL"}:
        match = re.search(r"\b(?:(?:GeForce\s+)?(?:RTX|GTX)\s+\d{3,4}(?:\s+(?:Ti|SUPER))?\b|(?:Radeon\s+)?RX\s+\d{3,4}(?:\s+(?:XT|XTX))?\b|Arc\s+[AB]\d{3}\b)", name, re.I)
        if match:
            hint["modelo"] = model or match.group(0)
            hint["escopo"] = "CHIP_GRAFICO"
    return hint


def trusted_origin(origin, identity):
    if not isinstance(origin, dict) or not origin.get("trecho") or not origin.get("url"):
        return False
    if origin.get("metodo") != "EXTRACAO_DETERMINISTICA" and not origin.get("evidenciaCampoConfirmada"):
        return False
    parsed = urlparse(str(origin["url"]))
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    source = str(origin.get("fonte") or "").upper()
    domains = ManufacturerProvider().search_domains(identity) if source == "FABRICANTE_OFICIAL" else TECHNICAL_DOMAINS.get(source, ())
    host = (parsed.hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def specific_model(category, identity):
    if identity.get("metodo") in {"GTIN", "MARCA_MPN"}:
        return True
    model = str(identity.get("modelo") or "")
    if category == "PLACA_MAE" and re.fullmatch(r"[ABHXZ]\d{3}[ME]?", model, re.I):
        return False
    if category in {"MEMORIA_RAM", "ARMAZENAMENTO", "FONTE"}:
        code = re.sub(r"\bDDR[345]\b|\b\d+(?:[.,]\d+)?\s*(?:GB|TB|W|MHz|MT/s)\b", "", model, flags=re.I)
        return bool(re.search(r"[A-Za-z]+[0-9]|[0-9]+[A-Za-z]|[A-Za-z]+[-_/][A-Za-z0-9]+", code))
    return True


def research_verified_hardware(*, category, payload, name=None, provider_name=None, local_only=False, hardware_id=None, only_fill_gaps=True, time_budget_seconds=None):
    """Pesquisa real, com filtro por campo e sem depender de chave de LLM."""
    category = str(category or "").upper()
    if only_fill_gaps is not True:
        raise ValueError("A pesquisa só preenche lacunas")
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise ValueError("Categoria sem ficha técnica estruturada")
    spec_key = schema[1]
    original = deepcopy(payload or {})
    if not original.get("nome"):
        original["nome"] = name
    before = normalize_specs_for_backend(category, original.get(spec_key) or {})
    seed = deepcopy(original)
    seed[spec_key] = before
    hint = identity_from_name(category, name or original.get("nome"), original.get("marca"), original.get("modelo"))
    for key in ("marca", "modelo"):
        if missing(seed.get(key)):
            seed[key] = hint.get(key)
    identity = build_identity({"payloadParcialBackend": seed})
    state = {"categoriaDetectada": category, "especificacoesEncontradas": before}
    outcome = {"payload": seed, "origemPorCampo": {}, "conflitos": []}
    identifiable = identity_is_strong(identity) and specific_model(category, identity)
    if identifiable and technical_missing_fields(state):
        if local_only:
            options = {"time_budget_seconds": time_budget_seconds} if time_budget_seconds is not None else {}
            found, info = research_hardware_locally(category, seed, name=name or seed.get("nome"), **options)
            outcome = {"payload": found, "origemPorCampo": info.get("origemPorCampo") or {}, "conflitos": info.get("conflitos") or [], "enriquecimentoProprio": info}
        else:
            from ..technical_ai.service import enrich_hardware_with_external_ai
            outcome = enrich_hardware_with_external_ai(provider_name=provider_name or "OPENAI", category=category, name=name or seed.get("nome"), payload=seed)

    proposed = (outcome.get("payload") or {}).get(spec_key) or {}
    origins = outcome.get("origemPorCampo") or {}
    after, accepted, rejected = dict(before), {}, []
    conflicts = [c for c in outcome.get("conflitos") or [] if isinstance(c, dict)]
    conflict_fields = {c.get("campo") for c in conflicts}
    collected = datetime.now(timezone.utc).isoformat()
    for field in schema[2]:
        value = proposed.get(field)
        if not missing(before.get(field)) or missing(value):
            continue
        origin = origins.get(field)
        chip_variant = hint.get("escopo") == "CHIP_GRAFICO" and field not in GPU_CHIP_FIELDS
        wrong_value = isinstance(origin, dict) and not missing(origin.get("valor")) and origin["valor"] != value
        notebook_variant = category == "NOTEBOOK" and identity.get("metodo") == "MARCA_MODELO" and field in {
            "processadorNome", "processadorMarca", "processadorGeracao", "nucleos", "threads", "clockBaseMhz", "clockTurboMhz", "tdpWatts",
            "gpuNome", "gpuIntegrada", "gpuDedicada", "vramGb", "tgpWatts", "ramInstaladaGb", "ramSoldadaGb", "armazenamentoGb", "sistemaOperacional",
        }
        if field in conflict_fields or chip_variant or notebook_variant or wrong_value or not trusted_origin(origin, identity):
            rejected.append({"campo": field, "motivo": "VARIANTE_DA_PLACA_NAO_CONFIRMADA" if chip_variant else "CONFLITO_OU_EVIDENCIA_NAO_CONFIRMADA"})
            continue
        after[field] = value
        accepted[field] = {**origin, "valor": value, "coletadoEm": collected, "evidenciaCampoConfirmada": True}
    final = deepcopy(original)
    final[spec_key] = {key: value for key, value in after.items() if key in schema[2] and value is not None}
    if accepted:
        for key in ("marca", "modelo"):
            if missing(final.get(key)):
                final[key] = seed.get(key)
    final_state = {"categoriaDetectada": category, "especificacoesEncontradas": final[spec_key]}
    confidence = annotate_field_confidence({"origemPorCampo": accepted, "conflitos": conflicts})
    return {
        **({"hardwareId": hardware_id} if hardware_id is not None else {}),
        "utilizado": bool(accepted), "provedor": "PROJETO_IA", "categoria": category,
        "nome": final.get("nome"), "payload": final, "somentePreencheLacunas": True,
        "escopoIdentidade": hint.get("escopo"), "identidadeConsulta": identity,
        "camposPreenchidos": list(accepted), "origemPorCampo": accepted,
        "confiancaPorCampo": confidence["confiancaPorCampo"], "conflitos": conflicts,
        "camposNaoConfirmados": rejected, "camposAusentes": technical_missing_fields(final_state),
        "camposObrigatoriosAusentes": required_missing_fields(final_state),
        "coberturaAntes": round(technical_coverage(state), 4), "coberturaDepois": round(technical_coverage(final_state), 4),
        "statusFicha": "PRECISA_REVISAO" if technical_missing_fields(final_state) or conflicts else "PRONTO",
        "motivo": "ESPECIFICACOES_DOCUMENTADAS" if accepted else "SEM_DADOS_CONFIRMADOS" if identifiable else "MODELO_EXATO_NAO_IDENTIFICADO",
        "fontesConsultadas": (outcome.get("enriquecimentoProprio") or {}).get("fontesConsultadas") or [],
    }
