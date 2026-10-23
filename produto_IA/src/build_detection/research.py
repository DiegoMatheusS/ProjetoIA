"""Pesquisa independente dos modelos presentes em um anúncio de computador."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from .analyzer import analyze_listing, _isolated_for_category
from ..research_agent.intake import identity_from_name, research_verified_hardware
from ..enrichment.identity import build_identity, identity_is_strong
from ..extractors.backend_schemas import SCHEMAS


def _component_seed(component, catalog):
    category = component["categoria"]
    if any(re.search(r"\b(?:ou|opcional|opcionais|varia|variam|alternativas?)\b", passage, re.I) for passage in component.get("trechos") or []):
        return None
    chosen = next((c for c in catalog if c.get("id") == component.get("hardwareId")), None)
    if chosen:
        return {"categoria": category, "nome": chosen.get("nome"), "marca": chosen.get("marca"), "modelo": chosen.get("modelo")}
    passages = component.get("trechos") or []
    # CPU possui código próprio. Outros componentes precisam de trecho isolado:
    # uma marca de placa-mãe no título do PC não identifica a RAM/SSD.
    if category == "PROCESSADOR":
        hints = []
        for passage in passages:
            hint = identity_from_name(category, passage)
            if hint.get("marca") and hint.get("modelo") and re.search(r"\b(?:Ryzen|Core|i[3579])\b", hint["modelo"], re.I):
                hints.append(hint)
        if len({h["modelo"].casefold() for h in hints}) != 1:
            return None
        if hints:
            hint = hints[0]
            return {"categoria": category, "nome": f'{hint["marca"]} {hint["modelo"]}', "marca": hint["marca"], "modelo": hint["modelo"]}
    for passage in passages:
        if not _isolated_for_category(passage, category):
            continue
        clean = re.sub(r"^[^:]{1,40}:\s*", "", passage).strip()
        hint = identity_from_name(category, clean)
        if not hint.get("marca") or not hint.get("modelo"):
            continue
        # Capacidades, potência ou chipset isolado não são SKU de uma peça.
        if category in {"MEMORIA_RAM", "ARMAZENAMENTO", "FONTE", "PLACA_MAE"} and re.fullmatch(r"(?:\d+\s*(?:GB|TB|W)|DDR[345]|[ABHXZ]\d{3}M?)(?:\s+.*)?", hint["modelo"], re.I):
            continue
        seed = {"categoria": category, "nome": clean, "marca": hint["marca"], "modelo": hint["modelo"]}
        if identity_is_strong(build_identity({"payloadParcialBackend": seed})):
            return seed
    return None


def research_pc_listing(title, description, catalog=None):
    catalog = catalog or []
    analysis = analyze_listing(title, description, catalog)

    def research(component):
        seed = _component_seed(component, catalog)
        if not seed:
            return {**component, "statusPesquisa": "MODELO_EXATO_NAO_IDENTIFICADO", "especificacoesConfirmadas": {}, "origemPorCampo": {}}
        try:
            # Dois workers e orçamento do agente por peça; não dispara LLMs pagos
            # em lote nem usa a ficha de um PC parecido como configuração instalada.
            found = research_verified_hardware(category=component["categoria"], payload=seed, name=seed["nome"], local_only=True, time_budget_seconds=10)
            spec_key = SCHEMAS[component["categoria"]][1]
            return {**component, "nome": seed["nome"], "marca": seed["marca"], "modelo": seed["modelo"],
                    "statusPesquisa": found["motivo"], "pesquisaTecnica": found,
                    "especificacoesConfirmadas": found["payload"].get(spec_key) or {},
                    "origemPorCampo": found["origemPorCampo"],
                    "cadastroHardwareSugerido": found["payload"] if found["utilizado"] and found["escopoIdentidade"] != "CHIP_GRAFICO" else None}
        except Exception:
            return {**component, "marca": seed["marca"], "modelo": seed["modelo"], "nome": seed["nome"], "statusPesquisa": "FONTE_INDISPONIVEL", "especificacoesConfirmadas": {}, "origemPorCampo": {}}

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="pc-specs") as pool:
        analysis["componentesDetectados"] = list(pool.map(research, analysis["componentesDetectados"][:9]))
    analysis["pesquisaTecnicaExecutada"] = True
    analysis["nenhumRegistroCriado"] = True
    return analysis


def research_imported_pc(result):
    payload = result.get("payloadParcialBackend") or {}
    specs = dict(result.get("especificacoesEncontradas") or {})
    labels = {"PROCESSADOR": "Processador", "PLACA_MAE": "Placa-mãe", "MEMORIA_RAM": "Memória RAM", "PLACA_VIDEO": "Placa de vídeo",
              "ARMAZENAMENTO": "Armazenamento", "FONTE": "Fonte", "GABINETE": "Gabinete", "COOLER": "Cooler processador", "VENTOINHA": "Ventoinha"}
    attributes = [f'{labels[c["categoria"]]}: {str(c["nome"])[:350]}' for c in specs.get("componentes") or []
                  if isinstance(c, dict) and c.get("categoria") in labels and c.get("nome")][:9]
    description = payload.get("descricao") or ""
    analysis = research_pc_listing(payload.get("nome") or "", "\n".join([description, *attributes]))
    analysis["descricaoOriginal"] = description
    result["analiseComputador"] = analysis
    specs["componentes"] = analysis["componentesDetectados"]
    result["especificacoesEncontradas"] = specs
    return result
