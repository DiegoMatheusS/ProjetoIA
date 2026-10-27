"""Confere o item vendido e o modelo; referências de compatibilidade não bastam."""

import re
import unicodedata
from ..extractors.category import detect_category

ACCESSORIES = r"adaptador|suporte|cabo|capa|pelicula|carcaca|waterblock|backplate|cooler|ventoinha|dissipador|fan|carregador|estojo|almofadas?|espumas?|earpads?|bolsa|protetor|parafuso|bracket|riser|extensor|teclado|mouse|refil|recarga|pecas?|reposicao|reparo|conector|bateria|fonte|placa\s+logica|kit\s+(?:de\s+)?upgrade"
MAIN = r"placa\s+(?:de\s+video|mae)|processador|memoria(?:\s+ram)?|notebook|computador|pc\s+gamer|ssd|cartucho|toner|impressora|monitor|mouse|teclado|headset|celular|smartphone|fonte|rtx\s*\d|gtx\s*\d|radeon|ryzen|geforce|\brx\s*\d|\bb\d{3}"
STOP = {
    "de",
    "do",
    "da",
    "para",
    "com",
    "e",
    "um",
    "uma",
    "o",
    "a",
    "os",
    "as",
    "em",
    "no",
    "na",
    "novo",
    "nova",
    "original",
    "gamer",
    "gaming",
    "placa",
    "video",
    "memoria",
    "ram",
    "processador",
    "computador",
    "pc",
    "desktop",
}


def normalized(value):
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(c)
    ).lower()
    text = re.sub(r"\b(rtx|gtx|rx|ddr)(?=\d)", r"\1 ", text)
    text = re.sub(r"\b((?:rtx|gtx|rx)\s*\d{3,4})\s*(ti|super|xtx|xt|gre)\b", r"\1 \2", text)
    text = re.sub(r"(\d)\s*(gb|tb|mhz|ghz)\b", r"\1 \2", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def sold_kind(text):
    accessory = re.search(r"\b(" + ACCESSORIES + r")\b", text)
    main = re.search(MAIN, text)
    if accessory and (not main or accessory.start() <= main.start()):
        return accessory.group(1)
    return None


def same_item_kind(query, title):
    q, t = normalized(query), normalized(title)
    if not q or not t:
        return True
    qc, tc = detect_category(q), detect_category(t)
    if not qc and re.search(r"\bpc\b", q):
        qc = "PC_MONTADO"
    if qc and tc and qc != tc:
        return False
    qkind, tkind = sold_kind(q), sold_kind(t)
    if tkind and tkind != qkind:
        return False
    if qkind and qkind != tkind:
        return False
    return True


def matches_search(query, title):
    q, t = normalized(query), normalized(title)
    if not q or not t:
        return False
    if not same_item_kind(q, t):
        return False
    terms = [w for w in q.split() if w not in STOP]
    words = set(t.split())
    if not all(term in words for term in terms):
        return False
    # Ti/Super/XT/XTX/GRE são variantes, não acessórios do mesmo modelo.
    for family, model, suffix in re.findall(
        r"\b(rtx|gtx|rx)\s*(\d{3,4})\s*((?:(?:ti|super|xtx|xt|gre)\b\s*)*)", q
    ):
        candidate = re.search(
            r"\b" + family + r"\s*" + model + r"\s*((?:(?:ti|super|xtx|xt|gre)\b\s*)*)",
            t,
        )
        if not candidate or candidate.group(1).strip() != suffix.strip():
            return False
    return True
