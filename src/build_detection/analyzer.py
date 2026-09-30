"""Análise conservadora de anúncios de PC montado e kits de upgrade.

A classificação é uma sugestão: nunca cria hardware nem presume marca/modelo.
Somente peças explicitamente identificadas são candidatas a vínculos.
Periféricos inclusos, como teclado/mouse, permanecem na descrição original.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

CORE_CATEGORIES = (
    "PROCESSADOR", "PLACA_MAE", "MEMORIA_RAM", "PLACA_VIDEO", "ARMAZENAMENTO",
    "FONTE", "GABINETE", "COOLER", "VENTOINHA",
)
PATTERNS = {
    "PROCESSADOR": r"\b(?:processador|ryzen\s*[3579]|core\s*i[3579]|xeon)\b",
    "PLACA_MAE": r"\b(?:placa[ -]?m[aã]e|motherboard)\b",
    "MEMORIA_RAM": r"\b(?:mem[oó]ria(?:\s*ram)?|ram|ddr[345])\b",
    "PLACA_VIDEO": r"\b(?:placa\s*de\s*v[ií]deo|geforce|radeon\s*rx|rtx\s*\d|gtx\s*\d)\b",
    "ARMAZENAMENTO": r"\b(?:ssd|hdd|disco\s*r[ií]gido|armazenamento|nvme)\b",
    "FONTE": r"\bfonte\b(?:\s*[:\-]?\s*(?:atx|de\s*alimenta[cç][aã]o|\d{3,4}\s*w))?",
    "GABINETE": r"\b(?:gabinete|chassi\s*(?:atx|gamer))\b",
    "COOLER": r"\b(?:water\s*cooler|air\s*cooler|cooler\s*(?:para\s*cpu|processador))\b",
    "VENTOINHA": r"\b(?:ventoinha|fans?\s*(?:rgb|argb|\d{2,3}\s*mm))\b",
}
# Quebra anúncios com campos em linhas separadas e listas separadas por
# vírgulas; a marca da placa-mãe não deve contaminar o trecho da memória RAM.
_SPLIT_COMPONENTS = re.compile(
    r"[\n;|]+|,\s*(?=(?:processador|placa[ -]?m[aã]e|mem[oó]ria|ram\b|"
    r"placa\s*de\s*v[ií]deo|ssd\b|hdd\b|armazenamento|fonte\b|gabinete\b|"
    r"cooler\b|water\s*cooler|ventoinha\b)\b)", re.I,
)
PERIPHERALS = re.compile(r"\b(?:teclado|mouse|mousepad|headset|brinde|monitor)\b", re.I)
KIT_WORDS = re.compile(r"\b(?:kit\s*(?:de\s*)?(?:upgrade|atualiza[cç][aã]o|processador|placa[ -]?m[aã]e)|combo\s*(?:upgrade|processador))\b", re.I)
PC_WORDS = re.compile(r"\b(?:computador\s*(?:completo|gamer|montado)?|pc\s*(?:montado|completo|gamer)|desktop\s*(?:completo|gamer)|setup\s*completo)\b", re.I)
NEGATIVE_PC = re.compile(r"\b(?:sem\s*gabinete|n[aã]o\s*(?:inclui|acompanha)\s*(?:gabinete|fonte)|somente\s*(?:placa[ -]?m[aã]e|processador))\b", re.I)


def norm(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", "".join(c for c in value.lower() if not unicodedata.combining(c))).split())


def contains_model(text: str, model: str) -> bool:
    """Evita vincular Ryzen 5600 quando o anúncio informa Ryzen 5600G."""
    target = norm(model)
    if len(target) < 5 or not re.search(r"[0-9]", target):
        return False
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(target).replace(r"\ ", r"\s+") + r"(?![a-z0-9])", text))


def _extract_components(description: str) -> list[dict[str, Any]]:
    segments = [part.strip(" :\n;-|") for part in _SPLIT_COMPONENTS.split(description) if part.strip(" :\n;-|")]
    detected: list[dict[str, Any]] = []
    for category, pattern in PATTERNS.items():
        excerpts = [segment[:300] for segment in segments if re.search(pattern, segment, re.I)]
        if excerpts:
            detected.append({"categoria": category, "trechos": excerpts[:5], "hardwareId": None})
    return detected


def _brand_found(passage: str, brand: str) -> bool:
    return bool(brand and re.search(r"(?<![a-z0-9])" + re.escape(brand) + r"(?![a-z0-9])", passage))


def _isolated_for_category(passage: str, category: str) -> bool:
    # Uma linha longa que mistura várias peças pode informar a marca de uma
    # placa-mãe e a RAM sem marca. Nesse caso não sugerir vínculos automáticos.
    original_categories = [item for item, pattern in PATTERNS.items() if re.search(pattern, passage, re.I)]
    return original_categories == [category]


def _catalog_matches(component: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    passages = [(p, norm(p)) for p in component["trechos"] if _isolated_for_category(p, component["categoria"])]
    matches = []
    for item in catalog:
        if str(item.get("categoria", "")).upper() != component["categoria"]:
            continue
        brand, model = norm(item.get("marca")), norm(item.get("modelo"))
        matching_passages = [p for _, p in passages if contains_model(p, model)] if model else []
        if not matching_passages:
            continue
        # Um chip RTX ou 16 GB DDR4 NÃO indica o fabricante nem o SKU da peça.
        if component["categoria"] in {"PLACA_VIDEO", "MEMORIA_RAM", "ARMAZENAMENTO"}:
            if not brand or not any(_brand_found(p, brand) for p in matching_passages):
                continue
        score = 2 if brand and any(_brand_found(p, brand) for p in matching_passages) else 1
        matches.append((score, item))
    # Só sugerir ID diretamente com correspondência única e inequívoca.
    matches.sort(key=lambda pair: pair[0], reverse=True)
    if not matches or (len(matches) > 1 and matches[0][0] == matches[1][0]):
        return {"hardwareId": None, "candidatos": [{"id": m.get("id"), "nome": m.get("nome")} for _, m in matches[:5]], "revisaoNecessaria": bool(matches)}
    chosen = matches[0][1]
    return {"hardwareId": chosen.get("id"), "candidatos": [], "revisaoNecessaria": False}


def analyze_listing(title: str, description: str, catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    original = str(description or "")[:30000]
    title = str(title or "")[:500]
    if not title and not original.strip():
        raise ValueError("Informe título ou descrição do anúncio.")
    components = _extract_components(original)
    categories = {c["categoria"] for c in components}
    combined = title + "\n" + original
    explicitly_kit = bool(KIT_WORDS.search(combined))
    explicitly_pc = bool(PC_WORDS.search(combined)) and (
        len(categories) >= 2 or bool(re.search(r"\b(?:computador|pc|desktop)\s+(?:completo|montado|gamer)\b", combined, re.I))
    )
    negative_pc = bool(NEGATIVE_PC.search(combined))
    if explicitly_kit:
        listing_type, reason = "KIT_UPGRADE", "O anúncio informa um kit de componentes."
    elif explicitly_pc and not negative_pc:
        listing_type, reason = "PC_MONTADO", "O anúncio apresenta um computador completo ou montado."
    elif {"PROCESSADOR", "PLACA_MAE"}.issubset(categories) and len(categories) >= 3 and not {"GABINETE", "FONTE"}.intersection(categories):
        listing_type, reason = "KIT_UPGRADE", "Há um conjunto de peças, sem confirmação de um PC completo."
    elif {"PROCESSADOR", "PLACA_MAE", "GABINETE"}.issubset(categories) and ("FONTE" in categories):
        listing_type, reason = "PC_MONTADO", "A descrição informa conjunto com gabinete e fonte."
    elif len(categories) <= 1:
        listing_type, reason = "HARDWARE_INDIVIDUAL", "Somente uma categoria técnica identificada."
    else:
        listing_type, reason = "INDEFINIDO", "Revisar: a descrição não comprova se é PC ou kit."
    catalog = catalog or []
    for component in components:
        component.update(_catalog_matches(component, catalog))
    return {
        "tipoSugerido": listing_type,
        "confirmacaoObrigatoria": not (explicitly_kit or (explicitly_pc and not negative_pc)),
        "motivo": reason,
        "tituloOriginal": title,
        "descricaoOriginal": original,
        "componentesDetectados": components,
        "acessoriosNaDescricao": sorted(set(m.group(0).lower() for m in PERIPHERALS.finditer(original))),
        "componentesObrigatorios": False,
        "ofertasIndividuaisObrigatorias": False,
        "avisos": ["Vincule somente componentes cuja marca e modelo estejam comprovados no anúncio; os demais permanecem na descrição."],
    }
