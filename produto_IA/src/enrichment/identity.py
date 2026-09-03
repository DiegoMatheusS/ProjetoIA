import re
import unicodedata

from ..utils.normalizers import clean_text


def _norm(value):
    value = clean_text(value)
    if not value:
        return None
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value or None


def _model_is_specific(model):
    value = clean_text(model)
    if not value or len(value) < 3:
        return False
    low = value.casefold().strip()
    generic = {
        "gaming", "gamer", "pro", "plus", "ultra", "series", "serie",
        "desktop", "notebook", "monitor", "mouse", "teclado", "headset",
        "ssd", "hdd", "ram", "memoria", "fonte", "gabinete", "cooler",
    }
    if low in generic:
        return False
    # Um modelo forte costuma trazer ao menos um dígito ou um código composto.
    return bool(re.search(r"\d", value) or re.search(r"[-_/]", value))


def build_identity(result):
    payload = result.get("payloadParcialBackend") or {}
    brand = clean_text(payload.get("marca"))
    model = clean_text(payload.get("modelo"))
    mpn = clean_text(payload.get("mpn"))
    gtin = re.sub(r"\D", "", str(payload.get("gtin") or "")) or None

    method = None
    confidence = "INSUFICIENTE"
    key = None
    if gtin and len(gtin) in (8, 12, 13, 14):
        method = "GTIN"
        confidence = "MUITO_ALTA"
        key = gtin
    elif brand and mpn:
        method = "MARCA_MPN"
        confidence = "MUITO_ALTA"
        key = f"{_norm(brand)}|{_norm(mpn)}"
    elif brand and model and _model_is_specific(model):
        method = "MARCA_MODELO"
        confidence = "ALTA"
        key = f"{_norm(brand)}|{_norm(model)}"

    return {
        "metodo": method,
        "confianca": confidence,
        "chave": key,
        "marca": brand,
        "modelo": model,
        "mpn": mpn,
        "gtin": gtin,
    }


def identity_is_strong(identity):
    return bool(identity and identity.get("metodo") in {"GTIN", "MARCA_MPN", "MARCA_MODELO"})


def identity_query(identity):
    if not identity_is_strong(identity):
        return None
    parts = [identity.get("marca")]
    if identity.get("mpn"):
        parts.append(identity["mpn"])
    elif identity.get("gtin"):
        parts.append(identity["gtin"])
    else:
        parts.append(identity.get("modelo"))
    return " ".join(filter(None, parts))


def text_matches_identity(identity, text):
    """Validação conservadora do candidato externo.

    Não considera uma página válida apenas por falar do mesmo chipset/família.
    Exige o identificador forte que justificou o enriquecimento.
    """
    if not identity_is_strong(identity):
        return False
    raw = clean_text(text) or ""
    norm_text = _norm(raw) or ""

    gtin = identity.get("gtin")
    if identity.get("metodo") == "GTIN":
        return bool(gtin and gtin in re.sub(r"\D", "", raw))

    brand = _norm(identity.get("marca"))
    if brand and brand not in norm_text:
        return False

    if identity.get("metodo") == "MARCA_MPN":
        mpn = _norm(identity.get("mpn"))
        return bool(mpn and mpn in norm_text)

    model_value = clean_text(identity.get("modelo"))
    model = _norm(model_value)
    if model and model in norm_text:
        return True

    # Catálogos técnicos às vezes acrescentam capacidade/frequência/"Kit of 2"
    # ao nome, enquanto a ficha individual usa apenas o modelo comercial.
    # Mantemos a validação conservadora por marca, mas aceitamos correspondência
    # por tokens distintivos para não descartar a própria ficha do SKU.
    model_tokens = [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", model_value or "")
    ]
    noise = {
        "spec", "specs", "rebrand", "series", "serie", "kit", "of", "the",
        "memory", "ram", "graphics", "card", "gpu", "processor", "cpu",
        "desktop", "notebook", "gaming", "gamer",
    }
    filtered = []
    for token in model_tokens:
        if token in noise or len(token) < 2:
            continue
        if token.isdigit() and int(token) <= 8:
            # Quantidades de kit/contagens pequenas não definem identidade.
            continue
        filtered.append(token)
    if not filtered:
        return False

    page_tokens = set(token.casefold() for token in re.findall(r"[A-Za-z0-9]+", raw))
    matched = sum(1 for token in filtered if token in page_tokens)
    ratio = matched / len(filtered)
    strong_tokens = [
        token for token in filtered
        if any(ch.isdigit() for ch in token) or len(token) >= 5
    ]
    strong_match = any(token in page_tokens for token in strong_tokens)
    return bool(ratio >= 0.70 and strong_match)
