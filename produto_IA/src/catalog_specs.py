"""Separa características do produto dos dados comerciais e scripts da loja."""
import re
import unicodedata
from html import unescape

NON_TECHNICAL = r"avaliac|customer\s*reviews?|^\s*ratings?\s*$|(?:customer|user)\s*ratings?|review\s*count|feedback|ranking|sales\s*rank\b|best\s*seller|mais\s*vendid|classificacao\s*(?:dos|de)\s*mais|parcel|installment|pagamento|payment|preco|price|frete|shipping|entrega|delivery|prazo|vendedor|seller|vendido\s*por|loja\b|estoque|stock|disponibilidade|availability|date\s*first\s*available|disponivel\s*(?:para\s*compra\s*)?desde|devoluc|return\s*policy|compras?\s*no\s*mes"
SCRIPT = r"<\s*(?:script|style)\b|\b(?:var|let|const)\s+\w+\s*[=;]|\bfunction\s*\(|=>\s*\{|\b(?:window|document)\s*[.\[]|\bP\.when\s*\(|\bue\.count\s*\("


def technical_attribute(key, value):
    key = unescape(str(key or ''))
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', key)
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).lower()
    text = re.sub(r'[_\W]+', ' ', text)
    if not text.strip() or re.search(NON_TECHNICAL, text, re.I):
        return False
    if text.strip() in {'proto', 'constructor', 'prototype'}:
        return False
    if isinstance(value, dict):
        return all(technical_attribute(k, v) for k, v in value.items())
    if isinstance(value, list):
        return all(not re.search(SCRIPT, str(v), re.I) for v in value)
    return value is not None and value != '' and not re.search(SCRIPT, unescape(str(value)), re.I)


def technical_attributes(rows):
    return [dict(row) for row in (rows or []) if isinstance(row, dict) and technical_attribute(
        row.get('name') or row.get('nome') or row.get('id'), row.get('value_name', row.get('value', row.get('valor'))))]
