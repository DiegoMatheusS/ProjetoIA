"""Enriquecimento técnico complementar com resposta do Meta AI / WhatsApp.

A Meta AI é usada somente como fallback quando a ficha normal está com baixa
cobertura. Este módulo não confia no formato da resposta: interpreta aliases,
normaliza tipos/unidades e preenche apenas lacunas do payload CriaByte.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from .backend_schemas import SCHEMAS
from .dto_normalizer import normalize_hardware_payload_for_backend, normalize_specs_for_backend


DEFAULT_FALLBACK_COVERAGE = 0.60


def fallback_coverage_threshold() -> float:
    raw = os.getenv("META_AI_WHATSAPP_FALLBACK_COVERAGE", str(DEFAULT_FALLBACK_COVERAGE))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = DEFAULT_FALLBACK_COVERAGE
    return min(0.95, max(0.20, value))


def should_use_meta_ai_fallback(coverage: float | int | None, *, threshold: float | None = None) -> bool:
    try:
        current = float(coverage or 0.0)
    except (TypeError, ValueError):
        current = 0.0
    limit = fallback_coverage_threshold() if threshold is None else min(0.95, max(0.20, float(threshold)))
    return current < limit


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _aliases(*values: str) -> tuple[str, ...]:
    return tuple(values)


# Aliases explícitos que não são apenas uma forma humanizada do nome canônico.
# O nome canônico, com/sem espaços/acentos/hífen/underscore, é aceito
# automaticamente para todas as categorias pelo índice gerado abaixo.
CATEGORY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "PROCESSADOR": {
        "linha": _aliases("Linha", "Série", "Serie", "Product Line", "Line"),
        "geracao": _aliases("Geração", "Geracao", "Generation", "CPU Generation"),
        "arquitetura": _aliases("Arquitetura", "Microarquitetura", "Architecture", "Microarchitecture"),
        "litografiaNm": _aliases("Litografia", "Processo", "Processo de fabricação", "Processo de fabricacao", "Process Node", "Node", "Manufacturing Process", "Lithography"),
        "cacheL2Mb": _aliases("Cache L2", "L2 Cache", "L2-Cache"),
        "cacheL3Mb": _aliases("Cache L3", "L3 Cache", "L3-Cache", "Smart Cache", "Intel Smart Cache"),
        "tdpWatts": _aliases("TDP", "TDP W", "Thermal Design Power", "Processor Base Power"),
        "possuiVideoIntegrado": _aliases("Possui vídeo integrado", "Possui video integrado", "Vídeo integrado", "Video integrado", "Integrated Graphics Available", "Has Integrated Graphics"),
        "modeloVideoIntegrado": _aliases("Vídeo integrado", "Video integrado", "GPU integrada", "iGPU", "Integrated Graphics", "Processor Graphics", "GPU name"),
        "tiposMemoriaSuportados": _aliases("Tipo de memória", "Tipo de memoria", "Memória suportada", "Memoria suportada", "Supported Memory", "Supported Memory Types", "Memory Type", "Memory Types"),
        "frequenciaMemoriaMaximaMhz": _aliases("Frequência máxima da memória", "Frequencia maxima da memoria", "Velocidade da memória", "Velocidade da memoria", "Memory Speed", "Max Memory Speed", "Maximum Memory Speed", "Max Memory Frequency"),
        "capacidadeMemoriaMaximaGb": _aliases("Memória máxima", "Memoria maxima", "Capacidade máxima de memória", "Capacidade maxima de memoria", "Max Memory", "Maximum Memory", "Max Memory Size"),
        "canaisMemoria": _aliases("Canais de memória", "Canais de memoria", "Memory Channels", "Max # of Memory Channels"),
        "suportaEcc": _aliases("Suporta ECC", "ECC", "ECC Support", "ECC Memory Supported"),
        "temperaturaMaximaC": _aliases("Temperatura máxima", "Temperatura maxima", "Tjmax", "Tjunction Max", "Max Temperature", "T. junction max."),
        "versaoPcie": _aliases("Versão PCIe", "Versao PCIe", "PCIe", "PCI Express", "PCI Express Version", "PCI Express Revision"),
        "lanesPcie": _aliases("PCIe Lanes", "Pistas PCIe", "Linhas PCIe", "Max # of PCI Express Lanes"),
        "dataLancamento": _aliases("Data de lançamento", "Data de lancamento", "Launch Date", "Release Date"),
        "coolerIncluso": _aliases("Cooler incluso", "Cooler incluído", "Cooler incluido", "Includes CPU Cooler"),
        "multiplicadorDesbloqueado": _aliases("Multiplicador desbloqueado", "Unlocked Multiplier", "Multiplier unlocked"),
        "suporteOverclock": _aliases("Suporta overclock", "Suporte a overclock", "Overclock Support", "Overclocking"),
        "nucleos": _aliases("Núcleos", "Nucleos", "Cores", "Core Count", "Total Cores"),
        "threads": _aliases("Threads", "Thread Count", "Total Threads"),
        "frequenciaBaseMhz": _aliases("Clock base", "Frequência base", "Frequencia base", "Base Clock", "Base Frequency", "Processor Base Frequency"),
        "frequenciaTurboMhz": _aliases("Clock boost", "Clock turbo", "Frequência turbo", "Frequencia turbo", "Boost Clock", "Max Turbo Frequency", "Turbo Frequency"),
        "socket": _aliases("Socket", "Soquete", "CPU Socket"),
        "familia": _aliases("Família", "Familia", "Family", "CPU Family", "Processor Family"),
    },
    "PLACA_MAE": {
        "socket": _aliases("Socket", "CPU Socket", "Soquete"),
        "chipset": _aliases("Chipset", "Chipset da placa mãe", "Chipset da placa mae"),
        "formato": _aliases("Formato", "Form factor", "Motherboard Form Factor"),
        "revisao": _aliases("Revisão", "Revisao", "Revision"),
        "biosInicial": _aliases("BIOS inicial", "Initial BIOS", "BIOS Version"),
        "tiposMemoriaSuportados": _aliases("Memória suportada", "Memoria suportada", "Supported Memory", "Memory Type", "RAM Type"),
        "formatosMemoriaSuportados": _aliases("Formato da memória", "Formato da memoria", "Memory Form Factor", "DIMM Type"),
        "frequenciasMemoriaJedecMhz": _aliases("Frequências JEDEC", "Frequencias JEDEC", "JEDEC Memory Speed", "JEDEC Speeds"),
        "frequenciasMemoriaOverclockMhz": _aliases("Frequências OC", "Frequencias OC", "OC Memory Speed", "Memory OC"),
        "slotsMemoria": _aliases("Slots de memória", "Slots de memoria", "Memory Slots", "DIMM Slots"),
        "capacidadeMaximaMemoriaGb": _aliases("Memória máxima", "Memoria maxima", "Max Memory", "Maximum Memory"),
        "capacidadeMaximaPorSlotGb": _aliases("Memória máxima por slot", "Memoria maxima por slot", "Max Memory Per Slot"),
        "suportaXmp": _aliases("XMP", "Suporta XMP", "XMP Support"),
        "suportaExpo": _aliases("EXPO", "Suporta EXPO", "EXPO Support"),
        "suportaEcc": _aliases("ECC", "Suporta ECC", "ECC Support"),
        "suportaMemoriaRegistrada": _aliases("Memória registrada", "Memoria registrada", "Registered Memory", "RDIMM Support"),
        "saidasVideo": _aliases("Saídas de vídeo", "Saidas de video", "Video Outputs", "Display Outputs"),
        "portasSata": _aliases("Portas SATA", "SATA Ports", "SATA Connectors"),
        "versaoPcie": _aliases("PCIe", "PCI Express", "Versão PCIe", "Versao PCIe", "PCI Express Version"),
        "wifi": _aliases("Wi-Fi", "WiFi", "Wireless LAN"),
        "bluetooth": _aliases("Bluetooth", "BT"),
        "ethernet": _aliases("Ethernet", "LAN", "Rede cabeada"),
        "biosFlashback": _aliases("BIOS Flashback", "Flash BIOS Button", "Q-Flash Plus"),
        "slotsM2": _aliases("Slots M.2", "M.2 Slots", "M2 Slots", "M.2"),
    },
    "MEMORIA_RAM": {
        "tipo": _aliases("Tipo DDR", "Memory Type", "Tipo de memória", "Tipo de memoria", "RAM Type"),
        "formato": _aliases("Formato", "Form Factor", "Memory Form Factor"),
        "capacidadePorModuloGb": _aliases("Capacidade por módulo", "Capacidade por modulo", "Capacity Per Module", "Module Capacity"),
        "quantidadeModulos": _aliases("Quantidade de módulos", "Quantidade de modulos", "Modules", "Kit", "Module Count"),
        "frequenciaMhz": _aliases("Frequência", "Frequencia", "Memory Speed", "Speed", "Data Rate"),
        "frequenciaJedecMhz": _aliases("Frequência JEDEC", "Frequencia JEDEC", "JEDEC Speed"),
        "latenciaCl": _aliases("Latência", "Latencia", "CAS Latency", "CL"),
        "tensaoVolts": _aliases("Tensão", "Tensao", "Voltage"),
        "ecc": _aliases("ECC", "ECC Memory"),
        "registrada": _aliases("Registrada", "Registered", "Registered Memory", "RDIMM"),
        "suportaXmp": _aliases("XMP", "XMP Support"),
        "suportaExpo": _aliases("EXPO", "EXPO Support"),
        "alturaMm": _aliases("Altura", "Height"),
        "rgb": _aliases("RGB", "LED RGB"),
        "consumoWatts": _aliases("Consumo", "Power Consumption", "Power"),
    },
    "PLACA_VIDEO": {
        "chipset": _aliases("Chipset", "Graphics Chipset"),
        "gpu": _aliases("GPU", "Graphics Processor", "Graphics Processor Unit"),
        "arquitetura": _aliases("Arquitetura", "Architecture", "GPU Architecture"),
        "memoriaVideoGb": _aliases("Memória de vídeo", "Memoria de video", "VRAM", "Video Memory", "Memory Size"),
        "tipoMemoriaVideo": _aliases("Tipo de memória", "Tipo de memoria", "Memory Type", "VRAM Type"),
        "barramentoBits": _aliases("Barramento", "Memory Bus", "Bus Width", "Memory Bus Width"),
        "clockBaseMhz": _aliases("Clock base", "Base Clock", "GPU Clock"),
        "clockBoostMhz": _aliases("Clock boost", "Boost Clock", "Boost"),
        "geracaoPcie": _aliases("PCIe", "PCI Express", "PCIe Generation", "PCI Express Version"),
        "larguraPcie": _aliases("Largura PCIe", "PCIe Width", "Bus Interface Width"),
        "comprimentoMm": _aliases("Comprimento", "Length", "Card Length"),
        "alturaMm": _aliases("Altura", "Height", "Card Height"),
        "espessuraMm": _aliases("Espessura", "Thickness", "Card Thickness"),
        "slotsOcupados": _aliases("Slots", "Slots ocupados", "Slot Width", "Card Slots"),
        "consumoWatts": _aliases("TDP", "TGP", "TBP", "Board Power", "Power Consumption"),
        "potenciaFonteRecomendadaWatts": _aliases("Fonte recomendada", "Recommended PSU", "Recommended Power Supply"),
        "conectoresPcie6Pinos": _aliases("PCIe 6-pin", "6-pin connectors", "6 pin power connectors"),
        "conectoresPcie8Pinos": _aliases("PCIe 8-pin", "8-pin connectors", "8 pin power connectors"),
        "conectores12vhpwr": _aliases("12VHPWR", "12VHPWR connectors"),
        "conectores12v2x6": _aliases("12V-2x6", "12V2x6", "12V-2x6 connectors"),
        "saidasVideo": _aliases("Saídas de vídeo", "Saidas de video", "Display Outputs", "Video Outputs"),
        "hdmi": _aliases("HDMI", "HDMI Ports"),
        "displayPort": _aliases("DisplayPort", "DisplayPort Ports", "DP Ports"),
    },
    "ARMAZENAMENTO": {
        "tipo": _aliases("Tipo", "Storage Type", "Drive Type"),
        "formato": _aliases("Formato", "Form Factor"),
        "interface": _aliases("Interface", "Storage Interface", "Bus Interface"),
        "capacidadeGb": _aliases("Capacidade", "Capacity", "Storage Capacity"),
        "tamanhoM2Mm": _aliases("Tamanho M.2", "M.2 Size", "M2 Size"),
        "chaveM2": _aliases("Chave M.2", "M.2 Key", "M2 Key"),
        "geracaoPcie": _aliases("PCIe", "PCIe Generation", "PCI Express Generation"),
        "pistasPcie": _aliases("Pistas PCIe", "PCIe Lanes", "Lane Count"),
        "leituraSequencialMbps": _aliases("Leitura sequencial", "Sequential Read", "Read Speed"),
        "escritaSequencialMbps": _aliases("Gravação sequencial", "Gravacao sequencial", "Sequential Write", "Write Speed"),
        "alturaMm": _aliases("Altura", "Height"),
        "larguraMm": _aliases("Largura", "Width"),
        "profundidadeMm": _aliases("Profundidade", "Depth", "Length"),
        "espessuraMm": _aliases("Espessura", "Thickness"),
        "consumoWatts": _aliases("Consumo", "Power Consumption", "Power"),
        "possuiDissipador": _aliases("Dissipador", "Heatsink", "Includes Heatsink"),
    },
    "FONTE": {
        "formato": _aliases("Formato", "Form Factor", "PSU Form Factor"),
        "potenciaWatts": _aliases("Potência", "Potencia", "Wattage", "Power", "Rated Power"),
        "certificacao": _aliases("Certificação", "Certificacao", "80 Plus", "Efficiency Certification"),
        "modularidade": _aliases("Modularidade", "Modularity", "Cable Management"),
        "comprimentoMm": _aliases("Comprimento", "Length"),
        "larguraMm": _aliases("Largura", "Width"),
        "alturaMm": _aliases("Altura", "Height"),
        "padraoAtx": _aliases("Padrão ATX", "Padrao ATX", "ATX Standard", "ATX Version"),
        "eficienciaPercentual": _aliases("Eficiência", "Eficiencia", "Efficiency"),
        "correnteLinha12vAmperes": _aliases("Corrente 12V", "12V Current", "+12V Current"),
        "conectoresAtx24Pinos": _aliases("ATX 24-pin", "24-pin ATX", "Motherboard Connector"),
        "conectoresEpsCpu": _aliases("EPS CPU", "CPU EPS", "EPS Connectors"),
        "conectoresPcie6Pinos": _aliases("PCIe 6-pin", "6-pin PCIe"),
        "conectoresPcie8Pinos": _aliases("PCIe 8-pin", "8-pin PCIe"),
        "conectores12vhpwr": _aliases("12VHPWR", "12VHPWR Connectors"),
        "conectores12v2x6": _aliases("12V-2x6", "12V2x6"),
        "conectoresSata": _aliases("SATA", "SATA Connectors"),
        "conectoresMolex": _aliases("Molex", "Molex Connectors", "Peripheral Connectors"),
        "protecoes": _aliases("Proteções", "Protecoes", "Protections", "Safety Protections"),
        "tensaoEntrada": _aliases("Tensão de entrada", "Tensao de entrada", "Input Voltage", "AC Input"),
    },
    "GABINETE": {
        "tamanho": _aliases("Tamanho", "Tipo", "Case Type", "Case Size", "Form Factor"),
        "alturaMm": _aliases("Altura", "Height"),
        "larguraMm": _aliases("Largura", "Width"),
        "profundidadeMm": _aliases("Profundidade", "Depth", "Length"),
        "formatosPlacaMaeSuportados": _aliases("Placas-mãe suportadas", "Placas mae suportadas", "Motherboard Support", "Motherboard Form Factors"),
        "formatosFonteSuportados": _aliases("Fontes suportadas", "PSU Support", "Power Supply Form Factor"),
        "comprimentoMaximoFonteMm": _aliases("Comprimento máximo da fonte", "Comprimento maximo da fonte", "Max PSU Length"),
        "comprimentoMaximoGpuMm": _aliases("Comprimento máximo da GPU", "Comprimento maximo da GPU", "Max GPU Length", "GPU Clearance"),
        "alturaMaximaGpuMm": _aliases("Altura máxima da GPU", "Altura maxima da GPU", "Max GPU Height"),
        "slotsMaximosGpu": _aliases("Slots máximos da GPU", "Slots maximos da GPU", "Max GPU Slots"),
        "alturaMaximaCoolerCpuMm": _aliases("Altura máxima do cooler", "Altura maxima do cooler", "Max CPU Cooler Height", "CPU Cooler Clearance"),
        "baias25": _aliases("Baias 2.5", "2.5 Bays", "2.5 Drive Bays"),
        "baias35": _aliases("Baias 3.5", "3.5 Bays", "3.5 Drive Bays"),
        "slotsTraseiros": _aliases("Slots traseiros", "Expansion Slots", "Rear Slots"),
        "suportaGpuVertical": _aliases("GPU vertical", "Vertical GPU", "Vertical GPU Support"),
        "espacoGerenciamentoCabosMm": _aliases("Espaço para cabos", "Espaco para cabos", "Cable Management Space", "Cable Clearance"),
        "suportesFans": _aliases("Ventoinhas suportadas", "Fans suportados", "Fan Support"),
        "suportesRadiador": _aliases("Radiadores suportados", "Radiator Support"),
    },
    "COOLER": {
        "tipo": _aliases("Tipo", "Cooler Type", "Cooling Type"),
        "socketsSuportados": _aliases("Sockets", "Sockets suportados", "Socket Support", "CPU Socket Support"),
        "capacidadeTermicaWatts": _aliases("TDP suportado", "TDP Support", "Thermal Capacity", "Cooling Capacity"),
        "alturaMm": _aliases("Altura", "Height"),
        "larguraMm": _aliases("Largura", "Width"),
        "profundidadeMm": _aliases("Profundidade", "Depth"),
        "alturaLivreRamMm": _aliases("Folga para RAM", "RAM Clearance", "Memory Clearance"),
        "tamanhoRadiadorMm": _aliases("Tamanho do radiador", "Radiator Size"),
        "espessuraRadiadorMm": _aliases("Espessura do radiador", "Radiator Thickness"),
        "quantidadeVentoinhas": _aliases("Quantidade de ventoinhas", "Fan Count", "Fans Included"),
        "tamanhoVentoinhaMm": _aliases("Tamanho da ventoinha", "Fan Size"),
        "espessuraVentoinhaMm": _aliases("Espessura da ventoinha", "Fan Thickness"),
        "comprimentoMangueirasMm": _aliases("Comprimento das mangueiras", "Tube Length", "Hose Length"),
        "conectorBomba": _aliases("Conector da bomba", "Pump Connector"),
        "consumoBombaWatts": _aliases("Consumo da bomba", "Pump Power", "Pump Power Consumption"),
        "consumoWatts": _aliases("Consumo", "Power Consumption", "Power"),
        "ruidoDb": _aliases("Ruído", "Ruido", "Noise", "Noise Level"),
        "vidaUtilHoras": _aliases("Vida útil", "Vida util", "Lifespan", "MTBF"),
        "pesoGramas": _aliases("Peso", "Weight"),
        "velocidadeMaxRpm": _aliases("RPM", "RPM máximo", "RPM maximo", "Max RPM", "Fan Speed"),
        "fluxoArCfm": _aliases("Fluxo de ar", "Airflow", "Air Flow"),
        "rgb": _aliases("RGB", "RGB Lighting"),
        "argb": _aliases("ARGB", "Addressable RGB"),
    },
    "VENTOINHA": {
        "tamanhoMm": _aliases("Tamanho", "Fan Size", "Size"),
        "espessuraMm": _aliases("Espessura", "Thickness"),
        "rpmMinima": _aliases("RPM mínimo", "RPM minimo", "Min RPM", "Minimum Speed"),
        "rpmMaxima": _aliases("RPM máximo", "RPM maximo", "Max RPM", "Maximum Speed", "Fan Speed"),
        "fluxoArCfm": _aliases("Fluxo de ar", "Airflow", "Air Flow"),
        "pressaoEstaticaMmH2o": _aliases("Pressão estática", "Pressao estatica", "Static Pressure"),
        "ruidoDb": _aliases("Ruído", "Ruido", "Noise", "Noise Level"),
        "conector": _aliases("Conector", "Connector", "Fan Connector"),
        "tensaoVolts": _aliases("Tensão", "Tensao", "Voltage"),
        "correnteAmperes": _aliases("Corrente", "Current", "Rated Current"),
        "pwm": _aliases("PWM", "PWM Support"),
        "rgb": _aliases("RGB", "RGB Lighting"),
        "argb": _aliases("ARGB", "Addressable RGB"),
        "fluxoReverso": _aliases("Fluxo reverso", "Reverse Airflow", "Reverse Blade"),
    },
}


CATEGORY_PROMPT_NOTES = {
    "PROCESSADOR": (
        "TiposMemoriaSuportados: use somente DDR3, DDR4 e/ou DDR5; "
        "FrequenciaMemoriaMaximaMhz, LitografiaNm, CacheL2Mb, CacheL3Mb, TdpWatts, "
        "CapacidadeMemoriaMaximaGb, TemperaturaMaximaC e LanesPcie: somente números; "
        "VersaoPcie: somente a versão (ex.: 5.0); booleanos: Sim ou Nao; "
        "DataLancamento: YYYY-MM-DD somente se a data completa for confirmada."
    ),
    "PLACA_MAE": "Informe apenas dados da placa-mãe: socket, chipset, formato, memória, slots, PCIe, armazenamento, rede, áudio/conectores quando solicitados.",
    "MEMORIA_RAM": "Informe apenas dados da memória RAM: DDR, formato, capacidade, frequência, latência, tensão, módulos, ECC, XMP/EXPO e RGB quando solicitados.",
    "PLACA_VIDEO": "Informe apenas dados da placa de vídeo: GPU/chipset, VRAM, tipo de memória, barramento, clocks, consumo/TDP, PCIe, conectores, saídas e dimensões quando solicitados.",
    "ARMAZENAMENTO": "Informe apenas dados do armazenamento: tipo, formato, interface, capacidade, leitura, gravação, NVMe/SATA, PCIe, dimensões, TBW somente se o campo solicitado existir.",
    "FONTE": "Informe apenas dados da fonte: potência, eficiência/certificação, modularidade, dimensões, padrão ATX, conectores e proteções quando solicitados.",
    "GABINETE": "Informe apenas dados do gabinete: formato/tamanho, placas-mãe e fontes suportadas, dimensões, baias, fans/radiadores e limites de GPU/cooler quando solicitados.",
    "COOLER": "Informe apenas dados do cooler: tipo, sockets, TDP, dimensões, radiador, fans, RPM, ruído, fluxo de ar, RGB/ARGB, vida útil e peso quando solicitados.",
    "VENTOINHA": "Informe apenas dados da ventoinha: tamanho, espessura, RPM, fluxo de ar, pressão, ruído, conector, tensão/corrente, PWM, RGB/ARGB e fluxo reverso quando solicitados.",
}


def _build_alias_index(category: str) -> dict[str, str]:
    schema = SCHEMAS.get(category)
    expected = (schema[2] if schema else None) or []
    index: dict[str, str] = {}
    for field in expected:
        index[_key(field)] = field
    for field, aliases in CATEGORY_ALIASES.get(category, {}).items():
        if field not in expected:
            continue
        for alias in aliases:
            index[_key(alias)] = field
    return index


def build_meta_ai_prompt(category: str, name: str, missing_fields: list[str] | None = None) -> str:
    """Gera pergunta específica da categoria e apenas para lacunas atuais."""
    category = str(category or "HARDWARE").strip().upper()
    name = str(name or "hardware").strip()
    schema = SCHEMAS.get(category)
    expected = list((schema[2] if schema else None) or [])
    requested = [str(field).strip() for field in (missing_fields or expected) if str(field).strip()]
    if expected:
        allowed = set(expected)
        requested = [field for field in requested if field in allowed]
    # preserva ordem sem duplicatas
    requested = list(dict.fromkeys(requested))
    fields_block = "\n".join(f"- {field}" for field in requested) or "- Nenhum campo técnico pendente"
    note = CATEGORY_PROMPT_NOTES.get(category, "Informe apenas os campos técnicos solicitados.")
    return (
        f"Pesquise e informe somente as especificações técnicas CONFIRMADAS de {name}, categoria {category}, "
        "que estão faltando abaixo.\n\n"
        "Responda exatamente no formato Campo: valor, uma por linha (uma linha por campo).\n\n"
        f"Campos necessários:\n{fields_block}\n\n"
        "Regras obrigatórias:\n"
        "- Não invente informações.\n"
        "- Se não conseguir confirmar um campo, escreva null.\n"
        "- Não informe campos que não foram pedidos.\n"
        "- Não informe preço, loja, promoção, link de compra, opinião ou recomendação.\n"
        f"- {note}\n"
        "- Não substitua informação técnica já confirmada por outra conflitante."
    )


def _line_attributes(text: str) -> list[tuple[str, str]]:
    """Extrai pares Campo/valor de lista, markdown simples e tabela markdown."""
    attrs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Tabela markdown: | Campo | Valor |
        if line.startswith("|") and line.endswith("|"):
            cells = [re.sub(r"[*_`]", "", cell).strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 2 and not all(re.fullmatch(r":?-{2,}:?", cell or "-") for cell in cells[:2]):
                if _key(cells[0]) not in {"campo", "field", "especificacao", "specification"}:
                    pair = (cells[0], cells[1])
                else:
                    continue
            else:
                continue
        else:
            line = re.sub(r"^[\s\-–—•*▪◦·>\d.)]+", "", line).strip()
            line = line.strip("` ")
            if not line or len(line) > 800:
                continue
            # Remove negrito markdown do rótulo/valor.
            line = line.replace("**", "").replace("__", "")
            match = re.match(r"^([^:]{1,140})\s*:\s*(.{1,600})$", line)
            if not match:
                match = re.match(r"^([^–—]{1,140})\s+[–—]\s+(.{1,600})$", line)
            if not match:
                match = re.match(r"^(.{1,140}?)\s+-\s+(.{1,600})$", line)
            if not match:
                continue
            pair = (match.group(1).strip(), match.group(2).strip())
        name = pair[0].strip().strip("*_` ")
        value = pair[1].strip().strip("*_` ")
        if not name or not value:
            continue
        marker = (_key(name), value.casefold())
        if marker in seen:
            continue
        seen.add(marker)
        attrs.append((name, value))
    return attrs


def _nullish_text(value: Any) -> bool:
    key = _key(value)
    return key in {
        "", "null", "none", "na", "n_a", "naoinformado", "naodisponivel", "desconhecido",
        "unknown", "notavailable", "notinformed", "semconfirmacao",
    }


def _memory_frequency_from_value(value: Any) -> int | None:
    text = str(value or "")
    matches = [int(x) for x in re.findall(r"\bDDR\s*[345]\s*[- ]\s*(\d{3,5})\b", text, re.I)]
    return max(matches) if matches else None


def parse_meta_ai_response(category: str, response_text: str) -> dict[str, Any]:
    """Interpreta aliases humanos/canônicos e devolve somente campos válidos do schema."""
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return {}
    text = str(response_text or "").strip()
    if not text:
        return {}

    alias_index = _build_alias_index(category)
    raw_specs: dict[str, Any] = {}
    memory_frequency: int | None = None
    for label, value in _line_attributes(text):
        field = alias_index.get(_key(label))
        if not field or _nullish_text(value):
            continue
        # Primeiro valor explícito vence dentro da própria resposta para evitar
        # que uma lista repetida reescreva um dado anterior sem contexto.
        raw_specs.setdefault(field, value)
        if field == "tiposMemoriaSuportados":
            memory_frequency = memory_frequency or _memory_frequency_from_value(value)

    normalized = normalize_specs_for_backend(category, raw_specs)
    if (
        category == "PROCESSADOR"
        and memory_frequency
        and not normalized.get("frequenciaMemoriaMaximaMhz")
    ):
        normalized["frequenciaMemoriaMaximaMhz"] = memory_frequency

    expected = set(schema[2] or [])
    # especificacoesInterpretadas contém somente valores efetivamente válidos.
    return {
        field: value
        for field, value in normalized.items()
        if field in expected and not _missing(value)
    }


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalized_for_compare(value: Any) -> Any:
    if isinstance(value, list):
        return sorted(str(item).strip().casefold() for item in value)
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def merge_meta_ai_response_into_payload_detailed(
    category: str,
    payload: dict[str, Any] | None,
    response_text: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any], list[dict[str, Any]]]:
    """Preenche apenas lacunas e registra conflitos sem sobrescrever o payload."""
    category = str(category or (payload or {}).get("categoria") or "").strip().upper()
    current_payload = normalize_hardware_payload_for_backend(category, payload or {})
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return current_payload, [], {}, []

    spec_field = schema[1]
    current_specs = dict(current_payload.get(spec_field) or {})
    meta_specs = parse_meta_ai_response(category, response_text)

    filled: list[str] = []
    conflicts: list[dict[str, Any]] = []
    for field, value in meta_specs.items():
        if _missing(value):
            continue
        current = current_specs.get(field)
        if _missing(current):
            current_specs[field] = value
            filled.append(field)
        elif _normalized_for_compare(current) != _normalized_for_compare(value):
            conflicts.append({"campo": field, "atual": current, "metaAi": value})

    current_payload[spec_field] = current_specs
    current_payload = normalize_hardware_payload_for_backend(category, current_payload)
    return current_payload, filled, meta_specs, conflicts


def merge_meta_ai_response_into_payload(
    category: str,
    payload: dict[str, Any] | None,
    response_text: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """Compatibilidade v14.20.11: devolve payload, preenchidos e interpretados."""
    current_payload, filled, meta_specs, _ = merge_meta_ai_response_into_payload_detailed(
        category, payload, response_text
    )
    return current_payload, filled, meta_specs
