"""Categoria principal: primeiro identifica o item vendido, depois as peças citadas.

As regras existentes ficam em category_rules.py. Este módulo antecipa apenas
os títulos inequívocos de computadores completos, para que `Intel Core` ou
`Ryzen` dentro deles não transformem o anúncio em PROCESSADOR.
"""

import re

from .category_rules import ALIASES, _clean, normalize_forced
from .category_rules import detect_category as _detect_category_rules


def assembled_computer_title(text: str) -> bool:
    """Detecta anúncios cujo item principal é um desktop, não um componente.

    Exige que o título comece pelo nome do equipamento, seguido de uma pista
    de configuração. Evita casar `kit upgrade`, gabinetes, CPUs e acessórios
    que apenas mencionam PC/computador no restante do texto.
    """
    headline = _clean(text)[:320]
    if re.search(r"^\s*(?:mini[- ]?pc|mini\s+computador)\b", headline):
        return False  # categoria própria: MINI_COMPUTADOR
    if re.search(
        r"^\s*(?:computador|pc|desktop)\s+(?:de\s+bordo|portatil|notebook|"
        r"laptop|gabinete|case|processador|cpu|placa|memoria|fonte|ssd)\b",
        headline,
    ):
        return False
    return bool(re.search(
        r"^\s*(?:computador|pc|desktop)\s+(?:de\s+mesa\b|"
        r"gamer\b|montado\b|completo\b|all[- ]?in[- ]?one\b|"
        r"intel\b|amd\b|core\b|ryzen\b|celeron\b|pentium\b|"
        r"(?:i[3579])\s*[- ]?\d{3,5}\b)",
        headline,
    ))


def detect_category(text: str, forced: str | None = None):
    if forced:
        return normalize_forced(forced)
    if assembled_computer_title(text):
        return "PC_MONTADO"
    return _detect_category_rules(text)
