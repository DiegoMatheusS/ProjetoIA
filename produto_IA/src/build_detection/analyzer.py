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
    "PROCESSADOR": r"\b(?:processador|cpu|ryzen\s*[3579]|core\s*i[3579]|intel\s+core|xeon)\b",
    "PLACA_MAE": (
        r"\b(?:placa[ -]?m[aã]e|motherboard|"
        r"a320\w*|b350\w*|x370\w*|b450\w*|x470\w*|a520\w*|b550\w*|x570\w*|"
        r"a620\w*|b650e?\w*|x670e?\w*|b840\w*|b850\w*|x870e?\w*|"
        r"h410\w*|b460\w*|h470\w*|z490\w*|h510\w*|b560\w*|h570\w*|z590\w*|"
        r"h610\w*|b660\w*|h670\w*|z690\w*|h710\w*|b760\w*|h770\w*|z790\w*|"
        r"h810\w*|b860\w*|z890\w*)\b"
    ),
    "MEMORIA_RAM": (
        r"\b(?:mem[oó]ria(?:\s*ram)?|ram|ddr[345])\b|"
        r"\b(?:4|8|12|16|24|32|48|64|96|128)\s*gb\s+(?:de\s+)?(?:ram|ddr[345])\b"
    ),
    "PLACA_VIDEO": r"\b(?:placa\s*de\s*v[ií]deo|gpu|geforce|radeon\s*(?:rx)?|(?:rtx|gtx|rx)\s*\d{3,4}(?:\s*(?:ti|super|xt|xtx))?)\b",
    "ARMAZENAMENTO": r"\b(?:ssd|hdd|hd\s+\d|disco\s*r[ií]gido|armazenamento|nvme)\b",
    "FONTE": r"\bfonte\b(?:\s*[:\-]?\s*(?:atx|de\s*alimenta[cç][aã]o|\d{3,4}\s*w))?|\bpsu\b",
    "GABINETE": r"\b(?:gabinete|chassi\s*(?:atx|gamer))\b",
    "COOLER": r"\b(?:water\s*cooler|air\s*cooler|cooler\s*(?:para\s*cpu|processador))\b",
    "VENTOINHA": r"\b(?:ventoinha|fans?\s*(?:rgb|argb|\d{2,3}\s*mm))\b",
}
_SPLIT_COMPONENTS = re.compile(
    r"[\n;|]+|,\s*(?=(?:processador|cpu|placa[ -]?m[aã]e|mem[oó]ria|ram\b|"
    r"placa\s*de\s*v[ií]deo|gpu\b|ssd\b|hdd\b|armazenamento|fonte\b|gabinete\b|"
    r"cooler\b|water\s*cooler|ventoinha\b)\b)", re.I,
)
PERIPHERALS = re.compile(r"\b(?:teclado|mouse|mousepad|headset|brinde|monitor)\b", re.I)
KIT_WORDS = re.compile(r"\b(?:kit\s*(?:de\s*)?(?:upgrade|atualiza[cç][aã]o|processador|placa[ -]?m[aã]e)|combo\s*(?:upgrade|processador))\b", re.I)
PC_WORDS = re.compile(r"\b(?:pc\s+computador|computador\s*(?:completo|gamer|montado)?|pc\s*(?:montado|completo|gamer)|desktop\s*(?:completo|gamer|montado)?|setup\s*completo)\b", re.I)
NEGATIVE_PC = re.compile(r"\b(?:sem\s*gabinete|n[aã]o\s*(?:inclui|acompanha)\s*(?:gabinete|fonte)|somente\s*(?:placa[ -]?m[aã]e|processador))\b", re.I)


def norm(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", "".join(c for c in value.lower() if not unicodedata.combining(c))).split())


def contains_model(text: str, model: str) -> bool:
    """Evita vincular Ryzen 5600 quando o anúncio informa Ryzen 5600G."""
    target = norm(model)
    if len(target) < 3 or not re.search(r"[0-9]", target):
        return False
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(target).replace(r"\ ", r"\s+")
                          + r"(?![a-z0-9]|\s+(?:ti|super|xt|xtx)\b)", text))


def important_description(description: str) -> str:
    """Remove somente chamadas comerciais isoladas, sem resumir especificações."""
    lines, seen = [], set()
    for line in description.splitlines():
        text = line.strip()
        if re.fullmatch(r"(?:compre agora|aproveite a oferta|oferta imperd[ií]vel|"
                        r"clique aqui|siga nossa loja|curta nossa loja)[!.\s]*", text, re.I):
            continue
        # Mantém repetições com valores/condições diferentes e todos os avisos.
        if text and text in seen:
            continue
        if text:
            seen.add(text)
        if text or (lines and lines[-1]):
            lines.append(text)
    return "\n".join(lines).strip()


def _extract_components(text: str) -> list[dict[str, Any]]:
    segments = [part.strip(" :\n;-|") for part in _SPLIT_COMPONENTS.split(text or "") if part.strip(" :\n;-|")]
    detected: list[dict[str, Any]] = []
    for category, pattern in PATTERNS.items():
        excerpts: list[str] = []
        for segment in segments:
            if re.search(pattern, segment, re.I):
                excerpt = segment[:350]
                if excerpt not in excerpts:
                    excerpts.append(excerpt)
        if excerpts:
            detected.append({"categoria": category, "trechos": excerpts[:6], "hardwareId": None})
    return detected


def _merge_components(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for component in group:
            category = str(component.get("categoria") or "")
            if not category:
                continue
            current = merged.setdefault(category, {"categoria": category, "trechos": [], "hardwareId": None})
            for passage in component.get("trechos") or []:
                if passage not in current["trechos"]:
                    current["trechos"].append(passage)
    return [merged[category] for category in CORE_CATEGORIES if category in merged]


def _brand_found(passage: str, brand: str) -> bool:
    return bool(brand and re.search(r"(?<![a-z0-9])" + re.escape(brand) + r"(?![a-z0-9])", passage))


def _isolated_for_category(passage: str, category: str) -> bool:
    original_categories = [item for item, pattern in PATTERNS.items() if re.search(pattern, passage, re.I)]
    return original_categories == [category]


def _brand_attached_to_model(source: str, brand: str, model: str) -> bool:
    """Exige associação local marca+modelo para itens com muitas variantes.

    Isso impede, por exemplo, que "ASUS B550M ... RAM 16 GB DDR4" seja usado
    para vincular por engano uma memória ASUS apenas porque a marca apareceu
    antes na mesma linha.
    """
    if not brand or not model:
        return False
    brand_rx = re.escape(brand).replace(r"\ ", r"\s+")
    model_rx = re.escape(model).replace(r"\ ", r"\s+")
    between = r"(?:\s+[a-z0-9+.-]+){0,2}\s+"
    return bool(
        re.search(r"(?<![a-z0-9])" + brand_rx + between + model_rx + r"(?![a-z0-9])", source)
        or re.search(r"(?<![a-z0-9])" + model_rx + between + brand_rx + r"(?![a-z0-9])", source)
    )


def _catalog_matches(component: dict[str, Any], catalog: list[dict[str, Any]], source_text: str) -> dict[str, Any]:
    passages = component.get("trechos") or []
    if any(re.search(r"\b(?:ou|opcional|opcionais|varia|variam|alternativas?|compat[ií]vel|suporta|n[aã]o inclui|n[aã]o acompanha)\b", p, re.I) for p in passages):
        return {"hardwareId": None, "candidatos": [], "revisaoNecessaria": True}
    source = norm("\n".join(passages))
    isolated_passages = [
        norm(p) for p in component.get("trechos") or []
        if _isolated_for_category(p, component["categoria"])
    ]
    matches: list[tuple[int, dict[str, Any]]] = []
    brand_required = component["categoria"] != "PROCESSADOR"

    for item in catalog:
        if str(item.get("categoria", "")).upper() != component["categoria"]:
            continue
        brand, model = norm(item.get("marca")), norm(item.get("modelo"))
        if not model or not contains_model(source, model):
            continue

        model_in_isolated = any(contains_model(passage, model) for passage in isolated_passages)
        brand_attached = any(_brand_attached_to_model(norm(p), brand, model) for p in passages)
        if brand_required and not brand_attached:
            continue

        score = 3 if brand_attached else 2 if model_in_isolated else 1
        matches.append((score, item))

    matches.sort(key=lambda pair: pair[0], reverse=True)
    if not matches:
        return {"hardwareId": None, "candidatos": [], "revisaoNecessaria": False}
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        return {
            "hardwareId": None,
            "candidatos": [{"id": m.get("id"), "nome": m.get("nome")} for _, m in matches[:5]],
            "revisaoNecessaria": True,
        }
    chosen = matches[0][1]
    return {
        "hardwareId": chosen.get("id"),
        "hardwareNome": chosen.get("nome"),
        "marca": chosen.get("marca"),
        "modelo": chosen.get("modelo"),
        "vinculoConfirmadoNoAnuncio": True,
        "candidatos": [],
        "revisaoNecessaria": False,
    }


def analyze_listing(title: str, description: str, catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    original = str(description or "")[:30000]
    title = str(title or "")[:500]
    if not title and not original.strip():
        raise ValueError("Informe título ou descrição do anúncio.")

    # O item principal é classificado primeiro. As peças podem estar tanto no
    # título quanto na descrição, algo comum em anúncios de PC completo.
    description_components = _extract_components(original)
    title_components = _extract_components(title)
    components = _merge_components(description_components, title_components)
    context_categories = {c["categoria"] for c in components}
    combined = (title + "\n" + original).strip()

    explicitly_kit = bool(KIT_WORDS.search(combined))
    explicitly_pc = bool(PC_WORDS.search(combined)) and (
        len(context_categories) >= 2
        or bool(re.search(r"\b(?:computador|pc|desktop)\s+(?:completo|montado|gamer)\b", combined, re.I))
    )
    negative_pc = bool(NEGATIVE_PC.search(combined))

    if explicitly_kit:
        listing_type, reason = "KIT_UPGRADE", "O anúncio informa um kit de componentes."
    elif explicitly_pc and not negative_pc:
        listing_type, reason = "PC_MONTADO", "O anúncio apresenta um computador completo ou montado."
    elif {"PROCESSADOR", "PLACA_MAE"}.issubset(context_categories) and len(context_categories) >= 3 and not {"GABINETE", "FONTE"}.intersection(context_categories):
        listing_type, reason = "KIT_UPGRADE", "Há um conjunto de peças, sem confirmação de um PC completo."
    elif {"PROCESSADOR", "PLACA_MAE", "GABINETE", "FONTE"}.issubset(context_categories):
        listing_type, reason = "PC_MONTADO", "A descrição e o título informam conjunto com gabinete e fonte."
    elif len(context_categories) <= 1:
        listing_type, reason = "HARDWARE_INDIVIDUAL", "Somente uma categoria técnica identificada."
    else:
        listing_type, reason = "INDEFINIDO", "Revisar: título e descrição não comprovam se é PC ou kit."

    catalog = catalog or []
    for component in components:
        component.update(_catalog_matches(component, catalog, combined))

    return {
        "tipoSugerido": listing_type,
        "confirmacaoObrigatoria": not (explicitly_kit or (explicitly_pc and not negative_pc)),
        "motivo": reason,
        "tituloOriginal": title,
        "descricaoOriginal": original,
        "descricaoSugerida": important_description(original),
        "componentesDetectados": components,
        "acessoriosNaDescricao": sorted(set(m.group(0).lower() for m in PERIPHERALS.finditer(original))),
        "componentesObrigatorios": False,
        "ofertasIndividuaisObrigatorias": False,
        "avisos": [
            "O tipo do anúncio é identificado antes das peças: CPU/GPU/RAM/SSD dentro de um PC não mudam o produto principal para hardware individual.",
            "Vincule somente componentes cuja marca e modelo estejam comprovados no anúncio; os demais permanecem na descrição.",
        ],
    }
