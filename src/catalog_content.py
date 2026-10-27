"""Conteúdo de cadastro: identidade curta e fatos técnicos, sem texto comercial."""
from __future__ import annotations

from .catalog_specs import technical_attribute, technical_attributes
from copy import deepcopy
from html import unescape
import re


NARRATIVE = re.compile(
    r"\b(?:conhe[cç]a|descubra|aproveite|compre\s+(?:agora|j[aá])|"
    r"experimente|eleve\s+(?:seu|sua)|revoluciona|transforme|"
    r"(?:foi|foram)\s+(?:criad[oa]s?|desenvolvid[oa]s?|projetad[oa]s?|lan[cç]ad[oa]s?)|"
    r"(?:[eé]|[ée]\s+um[ae]?)\s+(?:ideal|perfeit[oa]|a\s+escolha)|"
    r"oferece\s+(?:uma?|o|a)|proporciona|nossa\s+hist[oó]ria|"
    r"hist[oó]ria\s+(?:da|do|de|deste|desta)|desde\s+(?:19|20)\d{2})\b", re.I,
)
COMMERCIAL = re.compile(
    r"\b(?:frete\s+gr[aá]tis|oferta\s+imperd[ií]vel|promo[cç][aã]o|"
    r"melhor\s+pre[cç]o|compre\s+agora|em\s+at[eé]\s+\d+\s*x|"
    r"envio\s+imediato|s[oó]\s+hoje|garantia|parcelamento)\b", re.I,
)
TECHNICAL = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?\s*(?:GB|TB|MB|MHz|GHz|Hz|W|mm|cm|mAh|MP|dpi)|"
    r"DDR[345]|PCIe?|NVMe|SATA|USB|HDMI|DisplayPort|AM[345]|LGA\s*\d+|"
    r"n[uú]cleos|threads|socket|soquete|sensor\s+[oó]ptico|resolu[cç][aã]o)\b", re.I,
)
CATEGORIES = {
    "PROCESSADOR": "Processador", "PLACA_VIDEO": "Placa de vídeo", "PLACA_MAE": "Placa-mãe",
    "MEMORIA_RAM": "Memória RAM", "ARMAZENAMENTO": "Armazenamento", "FONTE": "Fonte",
    "GABINETE": "Gabinete", "COOLER": "Cooler", "VENTOINHA": "Ventoinha",
    "MONITOR": "Monitor", "MOUSE": "Mouse", "TECLADO": "Teclado", "HEADSET": "Headset",
    "FONE": "Fone de ouvido", "CELULAR": "Celular", "NOTEBOOK": "Notebook",
    "PC_MONTADO": "PC montado", "MICROFONE": "Microfone", "WEBCAM": "Webcam",
}
PRIORITIES = {
    "PROCESSADOR": ("socket", "nucleos", "threads", "frequenciaBaseMhz", "frequenciaTurboMhz", "cacheL3Mb", "tdpWatts", "modeloVideoIntegrado"),
    "PLACA_VIDEO": ("gpu", "memoriaVideoGb", "tipoMemoriaVideo", "barramentoBits", "clockBoostMhz", "consumoWatts", "potenciaFonteRecomendadaWatts", "comprimentoMm", "saidasVideo"),
    "PLACA_MAE": ("socket", "chipset", "formato", "tiposMemoriaSuportados", "slotsMemoria", "capacidadeMaximaMemoriaGb", "portasSata", "wifi", "bluetooth"),
    "MEMORIA_RAM": ("tipo", "capacidadePorModuloGb", "quantidadeModulos", "frequenciaMhz", "latenciaCl", "tensaoVolts", "formato", "suportaXmp", "suportaExpo"),
    "ARMAZENAMENTO": ("tipo", "capacidadeGb", "interface", "formato", "leituraSequencialMbps", "escritaSequencialMbps", "tbw", "comprimentoMm"),
    "CELULAR": ("ramGb", "armazenamentoGb", "tamanhoTelaPolegadas", "bateriaMah", "processadorNome", "cameraPrincipalMp"),
    "MONITOR": ("tamanhoPolegadas", "resolucao", "taxaAtualizacaoHz", "tipoPainel", "tempoRespostaMs", "conexoes"),
}
LABELS = {
    "socket": "Soquete", "nucleos": "Núcleos", "threads": "Threads", "tdpWatts": "TDP",
    "frequenciaBaseMhz": "Frequência base", "frequenciaTurboMhz": "Frequência turbo",
    "cacheL2Mb": "Cache L2", "cacheL3Mb": "Cache L3", "gpu": "GPU",
    "memoriaVideoGb": "Memória de vídeo", "tipoMemoriaVideo": "Tipo de memória de vídeo",
    "barramentoBits": "Barramento", "clockBoostMhz": "Clock boost", "consumoWatts": "Consumo",
    "potenciaFonteRecomendadaWatts": "Fonte recomendada", "comprimentoMm": "Comprimento",
    "alturaMm": "Altura", "espessuraMm": "Espessura", "saidasVideo": "Saídas de vídeo",
    "capacidadePorModuloGb": "Capacidade por módulo", "quantidadeModulos": "Módulos",
    "frequenciaMhz": "Frequência", "tensaoVolts": "Tensão", "latenciaCl": "Latência CL",
    "capacidadeGb": "Capacidade", "tipo": "Tipo", "formato": "Formato", "interface": "Interface",
    "ramGb": "Memória RAM", "armazenamentoGb": "Armazenamento", "bateriaMah": "Bateria",
    "tamanhoTelaPolegadas": "Tela", "tamanhoPolegadas": "Tela", "resolucao": "Resolução",
    "taxaAtualizacaoHz": "Taxa de atualização", "tipoPainel": "Painel", "tempoRespostaMs": "Tempo de resposta",
    "processadorNome": "Processador", "modeloVideoIntegrado": "Vídeo integrado",
}


def plain_text(value):
    text = unescape(str(value if value is not None else ""))
    text = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", "", text, flags=re.I | re.S)
    text = re.sub(r"<(?:br\s*/?|/p|/div|/h[1-6])\s*>", "\n", text, flags=re.I)
    return re.sub(r"<[^>]+>", "", text).strip()


def _clean_title(value):
    text = plain_text(value)
    text = re.sub(r"^\s*(?:nome(?:\s+(?:t[eé]cnico|do\s+produto))?|produto|t[ií]tulo)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^(?:conhe[cç]a|descubra|apresentamos)\s+(?:(?:o|a|os|as)\s+)?", "", text, flags=re.I)
    text = re.sub(r"[\[(][^\])]*(?:frete\s+gr[aá]tis|promo[cç][aã]o|oferta)[^\])]*[\])]", "", text, flags=re.I)
    text = re.sub(r"\s+\|\s+(?:amazon(?:\.com\.br)?|kabum|pichau|terabyte|mercado\s*livre|shopee|magalu|loja\b).*$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -–—|,;:")


def technical_name(value, brand=None, model=None, category=None):
    """Mantém códigos, variantes e unidades; nunca usa um parágrafo como título."""
    original = plain_text(value)
    lines = [line.strip() for line in original.splitlines() if line.strip()]
    name = _clean_title(lines[0] if lines else original)
    cut = NARRATIVE.search(name) or COMMERCIAL.search(name)
    if cut:
        name = name[:cut.start()].rstrip(" -–—|,;:.!")
    name = re.split(r"[.!?]\s+(?=[A-ZÀ-Ý])", name, maxsplit=1)[0].strip()
    name = re.sub(r"\s*[-–—:]?\s*R\$.*$", "", name).strip(" -–—|,;:")
    if name and len(name) <= 200 and len(name.split()) <= 28:
        return name
    clean_brand, clean_model = _clean_title(brand), _clean_title(model)
    if clean_model and len(clean_model) <= 100 and not NARRATIVE.search(clean_model) and not COMMERCIAL.search(clean_model):
        prefix = CATEGORIES.get(str(category or "").upper(), "")
        parts = [prefix, clean_brand, clean_model]
        combined = " ".join(part for i, part in enumerate(parts) if part and not any(part.casefold() in previous.casefold() for previous in parts[i+1:] if previous))
        return combined[:200].rstrip()
    # Um título técnico longo pode conter toda a configuração. Corta em palavra,
    # mantendo o relato completo somente no campo de anúncio original.
    if name and not NARRATIVE.search(name):
        return name[:200].rsplit(" ", 1)[0].rstrip(" -–—|,;:") if " " in name[:200] else ""
    return ""


def field_label(field):
    if field in LABELS:
        return LABELS[field]
    text = re.sub(r"(?:Gb|Mb|Mhz|Hz|Watts|Mm|Ms|Volts|Mah|Mp|Polegadas|Gramas)$", "", field)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).strip().capitalize()


def field_value(field, value):
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if isinstance(item, (str, int, float)))
    if isinstance(value, dict):
        return ""
    rendered = plain_text(value)
    if not rendered or len(rendered) > 180 or NARRATIVE.search(rendered) or COMMERCIAL.search(rendered):
        return ""
    if isinstance(value, (int, float)):
        units = {"Gb": "GB", "Mb": "MB", "Mhz": "MHz", "Hz": "Hz", "Watts": "W", "Mm": "mm", "Ms": "ms", "Volts": "V", "Mah": "mAh", "Mp": "MP", "Polegadas": 'pol.', "Gramas": "g", "Bits": "bits"}
        suffix = next((unit for ending, unit in units.items() if field.endswith(ending)), "")
        number = str(value).removesuffix('.0')
        return f"{number} {suffix}".strip()
    return rendered


def technical_description(category, name, specs, original=None):
    category = str(category or "").upper()
    # No PC comercial, preservar configuração, acessórios e garantia informados
    # pelo anúncio: não reconstruir a máquina a partir de peças presumidas.
    if category == "PC_MONTADO" and plain_text(original):
        return plain_text(original)
    specs = specs if isinstance(specs, dict) else {}
    keys = list(dict.fromkeys([*PRIORITIES.get(category, ()), *specs.keys()]))
    facts = []
    for field in keys:
        if re.search(r"^(?:id|produtoId|hardwareId|criadoEm|atualizadoEm|nome|descricao|origem|fontes|url|metodo|__proto__|constructor|prototype)$|pre[cç]o|price|frete|shipping|hist[oó]ria|history", field, re.I):
            continue
        value = specs.get(field)
        if not technical_attribute(field, value):
            continue
        if value is None or value == "" or value == []:
            continue
        rendered = field_value(field, value)
        if rendered:
            facts.append(f"{field_label(field)}: {rendered}")
        if len(facts) >= (4 if category == "CELULAR" else 12):
            break
    if facts:
        if category == "CELULAR":
            return " · ".join(facts)
        return "\n".join([name, *facts]) if name else "\n".join(facts)
    paragraphs = re.split(r"\n+|(?<=[.!?])\s+", plain_text(original))
    facts = [p.strip() for p in paragraphs if TECHNICAL.search(p) and not NARRATIVE.search(p) and not COMMERCIAL.search(p)]
    return "\n".join(facts[:8])[:4000] or None


def refine_catalog_result(result):
    if not isinstance(result, dict) or not isinstance(result.get("payloadParcialBackend"), dict):
        return result
    result = deepcopy(result)
    payload = result["payloadParcialBackend"]
    for key in ('especificacoesEncontradas',):
        if isinstance(result.get(key), dict):
            result[key] = {k: v for k, v in result[key].items() if technical_attribute(k, v)}
    if isinstance(result.get('informacoesProdutoEncontradas'), list):
        result['informacoesProdutoEncontradas'] = technical_attributes(result['informacoesProdutoEncontradas'])
    metadata = payload.get('metadados')
    if isinstance(metadata, dict):
        for key in ('atributosColetados', 'informacoesProdutoEncontradas'):
            if isinstance(metadata.get(key), list):
                metadata[key] = technical_attributes(metadata[key])
        for key in ('especificacoes', 'especificacoesEncontradas'):
            if isinstance(metadata.get(key), dict):
                metadata[key] = {k: v for k, v in metadata[key].items() if technical_attribute(k, v)}
    if not payload.get("nome"):
        return result
    category = str(result.get("categoriaDetectada") or payload.get("categoria") or "").upper()
    payload["nome"] = technical_name(payload.get("nome"), payload.get("marca"), payload.get("modelo"), category)
    # O anúncio é preservado para auditoria e análise da composição de PCs.
    result.setdefault("descricaoAnuncio", payload.get("descricao"))
    specs = result.get("especificacoesEncontradas") or {}
    payload["descricao"] = technical_description(category, payload["nome"], specs, payload.get("descricao"))
    return result
