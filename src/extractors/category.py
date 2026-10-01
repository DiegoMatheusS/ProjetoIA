"""Categoria principal: identifica primeiro o item vendido, depois as peças citadas.

As regras gerais ficam em ``category_rules.py``. Este módulo antecipa anúncios
claramente referentes a computadores completos para que Ryzen/Core/RTX/SSD do
mesmo título não transformem o produto em uma peça isolada.
"""

import re

from .category_rules import _clean, normalize_forced
from .category_rules import detect_category as _detect_category_rules


_COMPONENT_AT_START = re.compile(
    r"^\s*(?:kit\s+(?:upgrade|de\s+upgrade)|processador|cpu|placa[- ]m[aã]e|motherboard|"
    r"placa\s+de\s+v[ií]deo|gpu|mem[oó]ria(?:\s+ram)?|ram|ssd|hdd|fonte|psu|gabinete|"
    r"case|cooler|water\s*cooler|air\s*cooler|ventoinha|fan)\b",
    re.I,
)
_EQUIPMENT_WORD = re.compile(r"\b(?:computador|pc|desktop)\b", re.I)
_STRONG_PC_PHRASE = re.compile(
    r"\b(?:computador|pc|desktop)\s+(?:de\s+mesa\b|gamer\b|montado\b|completo\b|"
    r"all[- ]?in[- ]?one\b|intel\b|amd\b|core\b|ryzen\b|celeron\b|pentium\b|"
    r"(?:i[3579])\s*[- ]?\d{3,5}\b)",
    re.I,
)
_CONFIG_SIGNALS = (
    re.compile(r"\b(?:ryzen\s*[3579]?\s*\d{3,5}[a-z]{0,2}|(?:intel\s+)?core\s+i[3579][ -]?\d{3,5}[a-z]{0,2}|i[3579][ -]?\d{3,5}[a-z]{0,2}|xeon\s+\w+)\b", re.I),
    re.compile(r"\b(?:4|8|12|16|24|32|48|64|96|128)\s*gb\b.{0,18}\b(?:ram|ddr[345])\b|\b(?:ram|ddr[345])\b.{0,18}\b(?:4|8|12|16|24|32|48|64|96|128)\s*gb\b", re.I),
    re.compile(r"\b(?:ssd|nvme|hdd|hd)\b.{0,18}\b\d+(?:[.,]\d+)?\s*(?:gb|tb)\b|\b\d+(?:[.,]\d+)?\s*(?:gb|tb)\b.{0,18}\b(?:ssd|nvme|hdd|hd)\b", re.I),
    re.compile(r"\b(?:rtx|gtx)\s*\d{3,4}(?:\s*ti|\s*super)?\b|\bradeon\s*(?:rx)?\s*\d{3,4}\b", re.I),
)


def assembled_computer_title(text: str) -> bool:
    """Retorna True quando o item vendido é um desktop completo.

    A prioridade é o tipo do produto. CPU/GPU/RAM/SSD citados depois são
    tratados como componentes do computador e não como a categoria principal.
    """
    headline = _clean(text)[:420]
    if not headline:
        return False

    # Categorias próprias ou anúncios de peças não podem virar PC só porque
    # mencionam "para computador/PC" na compatibilidade.
    if re.search(r"\b(?:mini[- ]?pc|mini\s+computador|notebook|laptop|ultrabook)\b", headline, re.I):
        return False
    if _COMPONENT_AT_START.search(headline):
        return False
    if re.search(r"\b(?:kit\s+(?:de\s+)?upgrade|combo\s+upgrade)\b", headline, re.I):
        return False

    if _STRONG_PC_PHRASE.search(headline):
        return True

    # Alguns marketplaces inserem marca/linha antes de "PC" e depois colocam
    # a configuração inteira no título. Ex.: "Pichau PC Ryzen 5 ... 16GB RAM SSD".
    # Nesses casos exigimos pelo menos duas pistas técnicas independentes.
    if _EQUIPMENT_WORD.search(headline):
        signals = sum(1 for pattern in _CONFIG_SIGNALS if pattern.search(headline))
        if signals >= 2:
            return True

    return False


def detect_category(text: str, forced: str | None = None):
    if forced:
        return normalize_forced(forced)
    if assembled_computer_title(text):
        return "PC_MONTADO"
    return _detect_category_rules(text)
