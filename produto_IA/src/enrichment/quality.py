"""Evidence and conservative consistency checks shared by discovery and enrichment."""
import math
import re

from ..extractors.dto_normalizer import normalize_specs_for_backend
from ..extractors.ml_specs import extract_specs


def validate_specs(category, specs, attributes=None):
    safe = normalize_specs_for_backend(category, specs)
    issues = []

    def reject(field, reason):
        if safe.get(field) is not None:
            issues.append({"campo": field, "valor": safe[field], "motivo": reason})
            safe[field] = None

    for field, value in list(safe.items()):
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            if not math.isfinite(value) or value < 0:
                reject(field, "VALOR_NUMERICO_INVALIDO")
            elif field.endswith(('alturaMm', 'larguraMm', 'profundidadeMm', 'comprimentoMm')) and value == 0:
                reject(field, "DIMENSAO_NULA")
    pairs = {
        "PROCESSADOR": [("frequenciaBaseMhz", "frequenciaTurboMhz"), ("nucleos", "threads")],
        "PLACA_VIDEO": [("clockBaseMhz", "clockBoostMhz")],
        "VENTOINHA": [("rpmMinima", "rpmMaxima")],
    }
    for low, high in pairs.get(category, []):
        a, b = safe.get(low), safe.get(high)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > b:
            reject(low, "INTERVALO_INCONSISTENTE")
            reject(high, "INTERVALO_INCONSISTENTE")
    if category == "PLACA_MAE":
        form = safe.get("formato")
        slots = safe.get("slotsMemoria")
        if form == "MINI_ITX" and isinstance(slots, (int, float)) and slots > 2:
            reject("slotsMemoria", "SLOTS_INCOMPATIVEIS_COM_FORMATO")
    if category == "MEMORIA_RAM":
        # A kit's module count must be an integer, never a capacity or frequency.
        count = safe.get("quantidadeModulos")
        if count is not None and (not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 16):
            reject("quantidadeModulos", "QUANTIDADE_MODULOS_INVALIDA")
        per_module = safe.get("capacidadePorModuloGb")
        for attr in attributes or []:
            label = str(attr.get("name") or "").strip().casefold()
            if label not in {"total capacity", "kit capacity", "capacidade total", "capacidade do kit"}:
                continue
            match = re.fullmatch(r"\s*(\d+)\s*GB\s*", str(attr.get("value_name") or ""), re.I)
            if match and isinstance(per_module, (int, float)) and isinstance(count, int) and per_module * count != int(match[1]):
                reject("capacidadePorModuloGb", "CAPACIDADE_KIT_INCONSISTENTE")
                reject("quantidadeModulos", "CAPACIDADE_KIT_INCONSISTENTE")
    return safe, issues


def evidence_for_specs(category, source, specs):
    """Re-extract each row to associate an actual supporting passage with its field."""
    evidence = {}
    rows = source.get("attributes") or []
    passages = [( [row], f"{row.get('name', '')}: {row.get('value_name', '')}")
                for row in rows[:250] if isinstance(row, dict)]
    context = str(source.get("context_text") or "")[:40000]
    # Line evidence also supports text-only datasheets, without copying an entire page.
    passages.extend(([], line.strip()) for line in context.splitlines()[:400] if line.strip())
    for attrs, passage in passages:
        if not passage or len(passage) > 1200:
            continue
        found = normalize_specs_for_backend(category, extract_specs(category, attrs, context_text=passage))
        for field, value in specs.items():
            if value not in (None, "", []) and field not in evidence and found.get(field) == value:
                evidence[field] = {"fonte": source.get("fonte"), "url": source.get("url"),
                                   "trecho": passage, "valor": value, "metodo": "EXTRACAO_DETERMINISTICA"}
    return evidence


def source_diagnostic(source):
    error = str(source.get("erro") or "").upper()
    if source.get("ok"):
        return "COLETADO" if source.get("attributes") or source.get("context_text") else "SEM_DADOS"
    if any(code in error for code in ("403", "401", "429", "BLOQUEADO", "CAPTCHA")):
        return "BLOQUEADO"
    if any(code in error for code in ("TIMEOUT", "CONNECTION", "HTTP_502", "HTTP_503", "HTTP_504")):
        return "FALHA_TEMPORARIA"
    if "IDENTIDADE" in error or "DIVERGENTE" in error:
        return "MODELO_DIVERGENTE"
    if "NAO_ENCONTRADO" in error or "404" in error:
        return "NAO_ENCONTRADO"
    if "SEM_DADOS" in error:
        return "SEM_DADOS"
    return "ERRO_COLETA"
