import json
import os
import re
import time
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .generic_scraper import GenericScraper
from ..utils.normalizers import clean_text, to_float
from ..utils.rate_limiter import JsonDiskCache, PoliteRateLimiter


class MagazineScraper:
    """Extrator conservador para Magazine Luiza / Magalu / Magazine Você.

    Trabalha com uma URL individual. Faz no máximo uma tentativa HTTP inicial e,
    quando permitido, um único fallback com navegador. Não pagina nem percorre
    resultados de busca.
    """

    DOMAINS = ("magazineluiza.com.br", "magazinevoce.com.br", "magalu.com")

    def __init__(self):
        self.timeout = int(os.getenv("TIMEOUT", "20"))
        self.max_retries = max(0, min(2, int(os.getenv("MAGAZINE_MAX_RETRIES", "1"))))
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("MAGAZINE_MIN_DELAY_SECONDS", "2.0")),
            jitter=float(os.getenv("MAGAZINE_JITTER_SECONDS", "0.8")),
        )
        self.cache = JsonDiskCache()
        self.cache_ttl = int(os.getenv("MAGAZINE_CACHE_TTL_SECONDS", "600"))
        # Namespace versionado para nunca reaproveitar capturas de páginas de
        # verificação que versões antigas tenham salvo como se fossem produto.
        self.cache_namespace = "magalu_result_v14_7"
        self.generic = GenericScraper()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        })

    @classmethod
    def is_magazine(cls, url: str):
        host = (urlparse(url or "").hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in cls.DOMAINS)

    @staticmethod
    def product_code_from_url(url: str):
        path = urlparse(url or "").path
        match = re.search(r"/p/([^/]+)/", path, re.I)
        if not match:
            match = re.search(r"/p/([^/?#]+)", path, re.I)
        return clean_text(match.group(1)) if match else None

    @staticmethod
    def seller_slug_from_url(url: str):
        values = parse_qs(urlparse(url or "").query).get("seller_id") or []
        return clean_text(values[0]) if values else None

    @classmethod
    def is_product_url(cls, url: str):
        """Aceita somente URL individual de produto do ecossistema Magalu."""
        return bool(cls.is_magazine(url) and cls.product_code_from_url(url))

    @staticmethod
    def _gtin_check_digit_ok(value: str):
        digits = re.sub(r"\D", "", value or "")
        if len(digits) not in (8, 12, 13, 14):
            return False
        body = digits[:-1]
        check = int(digits[-1])
        total = 0
        # Regra GS1: da direita para a esquerda, pesos 3 e 1 alternados.
        for idx, ch in enumerate(reversed(body)):
            total += int(ch) * (3 if idx % 2 == 0 else 1)
        expected = (10 - (total % 10)) % 10
        return expected == check

    @classmethod
    def _normalize_gtin(cls, value):
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        return digits if cls._gtin_check_digit_ok(digits) else None

    @classmethod
    def _gtin_from_attributes(cls, attributes, fallback=None):
        by_name = cls._attribute_lookup(attributes)
        keys = (
            "gtin", "ean", "ean/gtin", "gtin/ean", "código de barras",
            "codigo de barras", "código ean", "codigo ean", "ean 13", "ean13",
        )
        for key in keys:
            value = by_name.get(key)
            normalized = cls._normalize_gtin(value)
            if normalized:
                return normalized
        return cls._normalize_gtin(fallback)

    @staticmethod
    def _money(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value)
        match = re.search(r"(?:R\$\s*)?([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[0-9]+(?:[.,][0-9]{2})?)", text)
        return to_float(match.group(1)) if match else None

    @classmethod
    def _pix_price_from_text(cls, text: str):
        if not text:
            return None
        patterns = [
            r"R\$\s*([0-9.]+,[0-9]{2})\s*(?:\n|\s){0,30}no\s+Pix",
            r"(?:pre[cç]o\s+no\s+pix|pix)\s*[:\-]?\s*R\$\s*([0-9.]+,[0-9]{2})",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.I)
            if matches:
                # Em páginas Magalu o bloco de preço pode repetir o mesmo valor.
                values = [cls._money(v) for v in matches]
                values = [v for v in values if v is not None and v > 0]
                if values:
                    return values[0]
        return None

    @classmethod
    def _regular_price_from_text(cls, text: str):
        """Preço à vista/normal explícito, sem confundir parcelas com preço."""
        if not text:
            return None
        patterns = [
            r"(?:pre[cç]o|por)\s*[:\-]?\s*R\$\s*([0-9.]+,[0-9]{2})(?!\s*(?:em|x|\/))",
            r"(?:à\s+vista|a\s+vista)\s*[:\-]?\s*R\$\s*([0-9.]+,[0-9]{2})",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.I):
                value = cls._money(match)
                if value is not None and value > 0:
                    return value
        return None

    @classmethod
    def _explicit_previous_price(cls, text: str):
        if not text:
            return None
        patterns = [
            r"(?:de|era)\s+R\$\s*([0-9.]+,[0-9]{2})\s+(?:por|agora)",
            r"pre[cç]o\s+anterior\s*[:\-]?\s*R\$\s*([0-9.]+,[0-9]{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return cls._money(match.group(1))
        return None

    @staticmethod
    def _seller_from_text(text: str):
        if not text:
            return None
        patterns = [
            r"Vendido\s+por\s+(.+?)\s+e\s+entregue\s+por",
            r"Vendido\s+e\s+entregue\s+por\s+(.+?)(?:\n|$)",
            r"Vendido\s+por\s+(.+?)(?=\s+R\$|\s+Adicionar|\s+Comprar|\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                value = clean_text(match.group(1))
                if value and len(value) <= 120:
                    return value
        return None

    @staticmethod
    def _seller_from_html(soup):
        # Magazine Você/Magalu pode representar o nome do seller apenas por
        # logo/alt, então o texto visível fica literalmente "Vendido por".
        selectors = (
            '[data-testid="seller-modal-content"] [data-testid="main-title"]',
            '[data-testid="seller-icon"][alt]',
            '[data-testid="mod-sellerdetails"] img[alt]',
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            value = clean_text(node.get("alt") or node.get_text(" ", strip=True))
            if value and value.casefold() not in {"vendido por", "entregue por", "magalu"}:
                return value
        return None

    @classmethod
    def _original_price_from_html(cls, soup, current_price=None):
        # O próprio DOM do Magalu usa data-testid=price-original para o preço
        # riscado/de referência. Só aceitamos se for maior que o preço atual.
        node = soup.select_one('[data-testid="price-original"]')
        value = cls._money(node.get_text(" ", strip=True)) if node else None
        if value is not None and (current_price is None or value > current_price):
            return value
        return None

    @classmethod
    def _structured_product_prices(cls, objects):
        """Lê bestPrice/fullPrice apenas do objeto de produto embutido na página."""
        found = []

        def walk(value):
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            price = value.get("price")
            if isinstance(price, dict) and any(k in price for k in ("bestPrice", "fullPrice", "price")):
                best = cls._money(price.get("bestPrice"))
                full = cls._money(price.get("fullPrice"))
                regular = cls._money(price.get("price"))
                found.append((best, full, regular))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)

        for obj in objects or []:
            walk(obj)
        for best, full, regular in found:
            current = best or full or regular
            previous_candidates = [v for v in (full, regular) if v is not None and current is not None and v > current]
            previous = max(previous_candidates) if previous_candidates else None
            if current is not None:
                return current, previous
        return None, None

    @staticmethod
    def _attribute_lookup(attributes):
        return {
            clean_text(row.get("name")).casefold(): clean_text(row.get("value_name"))
            for row in attributes or []
            if clean_text(row.get("name")) and clean_text(row.get("value_name"))
        }

    @staticmethod
    def _looks_like_part_number(value):
        value = clean_text(value)
        if not value or len(value) < 5:
            return False
        # Conservador: MPNs costumam misturar letras/dígitos e/ou hífens.
        return bool(
            re.search(r"[A-Za-z]", value) and re.search(r"\d", value)
            and (
                "-" in value
                or "/" in value
                or (len(value) >= 8 and not re.search(r"\s", value))
            )
        )

    @classmethod
    def _refine_identity(cls, generic, attributes):
        by_name = cls._attribute_lookup(attributes)
        title = clean_text(generic.get("title")) or ""
        generic_brand = clean_text(generic.get("brand"))
        labeled_brand = by_name.get("marca") or by_name.get("manufacturer")
        # Se a marca genérica aparece explicitamente no título, ela é evidência
        # mais forte que um atributo conflitante da ficha (ex.: placa-mãe
        # Gigabyte cuja ficha do Magalu traz "Marca: AMD" por causa da plataforma).
        # Se o JSON-LD trouxer algo genérico/concatenado que não aparece no título,
        # o campo rotulado continua prevalecendo (ex.: "AMD PCYES" -> "AMD").
        if generic_brand and generic_brand.casefold() in title.casefold():
            brand = generic_brand
        else:
            brand = labeled_brand or generic_brand
        model = generic.get("model")
        mpn = generic.get("mpn")

        visible_model = by_name.get("modelo")
        processor_number = by_name.get("número do processador") or by_name.get("numero do processador")

        characteristics = by_name.get("características") or by_name.get("caracteristicas") or ""
        embedded_part_number = None
        match = re.search(r"(?:Part\s*Number|P/N|MPN)\s*:\s*([^|;]+)", characteristics, re.I)
        if match:
            embedded_part_number = clean_text(match.group(1))

        # Alguns parceiros publicam em Características algo como
        # "Modelo: 306-7ZP6B22-809", enquanto o campo Modelo visível traz o
        # nome comercial (MAG A600DN). Se esse código também aparece no título,
        # tratamos como identificador de fabricante, sem adivinhação externa.
        embedded_model_code = None
        match = re.search(r"(?:^|\|)\s*Modelo\s*:\s*([^|;]+)", characteristics, re.I)
        if match:
            candidate = clean_text(match.group(1))
            if candidate and candidate != visible_model and candidate in title and cls._looks_like_part_number(candidate):
                embedded_model_code = candidate

        reference = by_name.get("referência") or by_name.get("referencia")
        labeled_mpn = (
            by_name.get("mpn")
            or by_name.get("part number")
            or by_name.get("part number do fabricante")
            or by_name.get("código do fabricante")
            or by_name.get("codigo do fabricante")
        )

        # Campos explicitamente rotulados como MPN/Part Number podem ser aceitos
        # diretamente. Já "Referência" é ambíguo no Magalu: em muitos anúncios
        # repete apenas o modelo comercial (ex.: B550M AORUS ELITE). Por isso,
        # Referência só vira MPN quando tiver formato forte de part number.
        if labeled_mpn:
            mpn = labeled_mpn
        elif reference and cls._looks_like_part_number(reference):
            mpn = reference
        elif embedded_part_number and cls._looks_like_part_number(embedded_part_number):
            mpn = embedded_part_number
        elif embedded_model_code:
            mpn = embedded_model_code

        if processor_number:
            model = processor_number
            if not mpn and cls._looks_like_part_number(visible_model):
                mpn = visible_model
        else:
            # O campo Modelo da ficha pode ser mais específico que o JSON-LD.
            # Ex.: ASUS DUAL-RTX5060TI-O8G + referência 90YV0MP2-M0NA00.
            # Quando o Modelo é distinto do MPN, ele representa a identidade
            # comercial do produto e deve ser preservado.
            if visible_model and clean_text(visible_model) != clean_text(mpn):
                model = visible_model
            elif not model:
                model = visible_model or by_name.get("model") or by_name.get("model name")

        if not mpn and cls._looks_like_part_number(visible_model) and visible_model in title:
            mpn = visible_model

        # Alguns anúncios não têm campo Modelo, mas o título termina com um
        # código comercial explícito (ex.: "- M711", "- AM8"). Isso é
        # suficiente para modelo, mas NÃO para afirmar MPN.
        if not model and title:
            match = re.search(r"\s-\s([A-Z0-9][A-Z0-9._/+() -]{1,35})$", title, re.I)
            if match:
                candidate = clean_text(match.group(1))
                if candidate and len(candidate) <= 40 and re.search(r"[A-Za-z]", candidate) and re.search(r"\d", candidate):
                    model = candidate

        # Em processadores, alguns sellers colocam o MPN no campo "Modelo".
        # Quando o nome comercial está explícito no título, preservamos ambos:
        # modelo comercial em `modelo` e part number em `mpn`.
        if title and (not model or (mpn and clean_text(model) == clean_text(mpn))):
            commercial = None
            m = re.search(r"\bRyzen\s+[3579]\s+([0-9]{4}[A-Z0-9]+)\b", title, re.I)
            if m:
                commercial = m.group(1).upper()
            if not commercial:
                m = re.search(r"\bCore\s+(i[3579][ -]?[0-9]{4,5}[A-Z0-9]*)\b", title, re.I)
                if m:
                    commercial = re.sub(r"\s+", "", m.group(1))
            if not commercial:
                m = re.search(r"\bCore\s+Ultra\s+[3579]\s+([0-9]{3}[A-Z0-9]*)\b", title, re.I)
                if m:
                    commercial = m.group(1).upper()
            if commercial:
                model = commercial

        # Em GPUs, chip e modelo do fabricante são conceitos diferentes.
        # Ex.: GPU = RTX 5060 Ti, Modelo = DUAL-RTX5060TI-O8G. Quando o seller
        # só fornece o part number no campo Modelo, usamos Linha + chip para
        # evitar que placas distintas do mesmo chip virem o mesmo produto.
        if title and (not model or (mpn and clean_text(model) == clean_text(mpn))):
            commercial_gpu = None
            m = re.search(r"\b(RX\s*[0-9]{4}\s*(?:XTX|XT|GRE)?)\b", title, re.I)
            if m:
                commercial_gpu = re.sub(r"\s+", " ", m.group(1)).upper()
            if not commercial_gpu:
                m = re.search(r"\b((?:RTX|GTX)\s*[0-9]{3,4}(?:\s*(?:TI|SUPER))?)\b", title, re.I)
                if m:
                    commercial_gpu = re.sub(r"\s+", " ", m.group(1)).upper()
            if commercial_gpu:
                line = by_name.get("linha") or by_name.get("line")
                model = clean_text(f"{line} {commercial_gpu}") if line else commercial_gpu

        # Para outros produtos cujo campo Modelo é apenas o mesmo part number,
        # uma Linha explícita pode ser identidade comercial melhor.
        if mpn and clean_text(model) == clean_text(mpn):
            line = by_name.get("linha") or by_name.get("line")
            if line:
                model = line

        return clean_text(brand), clean_text(model), clean_text(mpn)

    @staticmethod
    def _description_section(text: str):
        if not text:
            return None
        marker = re.search(r"Descri[cç][aã]o\s+e\s+ficha\s+t[eé]cnica", text, flags=re.I)
        if not marker:
            return None
        section = text[marker.end():]
        end = re.search(
            r"\n(?:Avalia[cç][oõ]es|Perguntas|Produtos\s+similares|Quem\s+viu|Veja\s+tamb[eé]m|Formas\s+de\s+pagamento)\b",
            section,
            flags=re.I,
        )
        if end:
            section = section[:end.start()]
        section = clean_text(section)
        if not section:
            return None
        return section[:12000]

    @staticmethod
    def _json_objects(soup):
        objects = []
        selectors = [
            'script[type="application/ld+json"]',
            'script[type="application/json"]',
            'script#__NEXT_DATA__',
        ]
        seen = set()
        for selector in selectors:
            for script in soup.select(selector):
                raw = (script.string or script.get_text() or "").strip()
                if not raw or len(raw) > 6_000_000:
                    continue
                fingerprint = hash(raw)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                objects.append(data)
        return objects

    @staticmethod
    def _structured_pairs(objects):
        """Extrai pares nome/valor apenas de ramos com semântica técnica."""
        pairs = []
        seen = set()
        context_words = (
            "spec", "attribute", "characteristic", "feature", "technical",
            "ficha", "detail", "property", "properties",
        )

        def add(name, value):
            name = clean_text(name)
            if isinstance(value, (dict, list)):
                return
            value = clean_text(value)
            if not name or not value or len(name) > 160 or len(value) > 1200:
                return
            key = (name.casefold(), value.casefold())
            if key in seen:
                return
            seen.add(key)
            pairs.append({"id": None, "name": name, "value_name": value})

        def walk(value, path=""):
            if isinstance(value, list):
                for item in value:
                    walk(item, path)
                return
            if not isinstance(value, dict):
                return

            path_low = path.casefold()
            in_technical_context = any(word in path_low for word in context_words)

            if in_technical_context:
                name = value.get("name") or value.get("label") or value.get("title") or value.get("key")
                candidate = (
                    value.get("value")
                    if "value" in value else
                    value.get("value_name")
                    if "value_name" in value else
                    value.get("text")
                )
                if name is not None and candidate is not None:
                    add(name, candidate)

            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(child, (dict, list)):
                    walk(child, child_path)

        for obj in objects:
            walk(obj)
        return pairs[:300]

    @staticmethod
    def _merge_attributes(*lists):
        result = []
        seen = set()
        for rows in lists:
            for row in rows or []:
                name = clean_text(row.get("name"))
                value = clean_text(row.get("value_name"))
                if not name or not value:
                    continue
                key = (name.casefold(), value.casefold())
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "id": row.get("id"),
                    "name": name,
                    "value_name": value,
                })
        return result[:350]

    @staticmethod
    def _is_product_attribute(name: str):
        """Mantém somente informações sobre o produto em si."""
        key = clean_text(name).casefold()
        if not key:
            return False
        blocked = (
            "vendido por", "vendedor", "seller", "entregue por", "entrega",
            "frete", "prazo", "cep", "parcel", "pagamento", "cartão", "cartao",
            "pix", "total", "preço", "preco", "sacola",
        )
        return not any(term in key for term in blocked)

    @classmethod
    def _product_attributes_only(cls, attributes, brand=None, model=None, mpn=None):
        result = []
        seen = set()
        brand_key = clean_text(brand).casefold() if clean_text(brand) else None
        model_key = clean_text(model).casefold() if clean_text(model) else None
        mpn_key = clean_text(mpn).casefold() if clean_text(mpn) else None

        for row in attributes or []:
            name = clean_text(row.get("name"))
            value = clean_text(row.get("value_name"))
            if not name or not value or not cls._is_product_attribute(name):
                continue

            name_key = name.casefold()
            value_key = value.casefold()

            # Não manter na ficha "limpa" uma marca que contradiz a identidade
            # confirmada pelo título/JSON-LD. Isso evita casos como placa-mãe
            # Gigabyte cuja ficha traz "Marca: AMD" por causa da plataforma.
            if name_key in {"marca", "manufacturer"} and brand_key and value_key != brand_key:
                continue

            # Alguns sellers usam "Modelo" para o próprio part number. Se a
            # normalização já separou Modelo e MPN, não repetir o MPN como modelo.
            if name_key in {"modelo", "model"} and mpn_key and value_key == mpn_key and model_key != mpn_key:
                name = "MPN"
                name_key = "mpn"

            key = (name_key, value_key)
            if key in seen:
                continue
            seen.add(key)
            result.append({"nome": name, "valor": value})
        return result

    @staticmethod
    def _selected_variants(soup):
        """Captura apenas opções explicitamente marcadas como selecionadas."""
        result = []
        seen = set()

        def add(name, value):
            name = clean_text(name) or "variante"
            value = clean_text(value)
            if not value or len(value) > 160:
                return
            key = (name.casefold(), value.casefold())
            if key in seen:
                return
            seen.add(key)
            result.append({"nome": name, "valor": value})

        for select in soup.select("select")[:30]:
            selected = select.select_one("option[selected]")
            if not selected:
                continue
            label = select.get("aria-label") or select.get("name") or select.get("id") or "variante"
            add(label, selected.get_text(" ", strip=True) or selected.get("value"))

        for node in soup.select('[aria-selected="true"], [aria-checked="true"]')[:60]:
            value = node.get("aria-label") or node.get("title") or node.get_text(" ", strip=True)
            label = node.get("data-testid") or node.get("name") or "variante"
            add(label, value)

        for inp in soup.select('input[type="radio"][checked]')[:30]:
            value = inp.get("aria-label") or inp.get("value")
            label = inp.get("name") or "variante"
            if inp.get("id"):
                lab = soup.select_one(f'label[for="{inp.get("id")}"]')
                if lab:
                    value = lab.get_text(" ", strip=True) or value
            add(label, value)

        return result[:20]

    @staticmethod
    def _kit_combo_info(title: str, attributes=None):
        text = clean_text(title) or ""
        low = text.casefold()
        is_kit = bool(re.search(r"\b(?:kit|combo|conjunto)\b", low))
        quantity = None
        patterns = [
            r"\bkit\s+(?:com|de)\s+(\d+)\b",
            r"\b(\d+)\s*x\s*(?:8|16|24|32|48|64)\s*gb\b",
            r"\b(\d+)\s*(?:fans?|ventoinhas?)\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, low, re.I)
            if m:
                quantity = int(m.group(1))
                is_kit = True
                break

        components = []
        component_terms = (
            ("TECLADO", r"\bteclado\b"),
            ("MOUSE", r"\bmouse\b"),
            ("VENTOINHA", r"\b(?:fan|ventoinha)"),
            ("MEMORIA_RAM", r"\b(?:mem[oó]ria\s+ram|ddr[345])\b"),
        )
        for category, pattern in component_terms:
            if re.search(pattern, low, re.I):
                components.append(category)
        if len(components) > 1:
            is_kit = True
        return {"ehKitCombo": is_kit, "quantidadeDetectada": quantity, "componentesDetectados": components}

    @staticmethod
    def _image_variant_key(url: str):
        return re.sub(r"/\d+x\d+/", "/{size}/", clean_text(url) or "", count=1)

    @classmethod
    def _best_product_image(cls, soup, html: str, fallback=None):
        """Prefere a maior variante realmente presente da imagem principal."""
        og = soup.select_one('meta[property="og:image"]')
        og_url = clean_text(og.get("content")) if og else clean_text(fallback)
        if not og_url:
            return clean_text(fallback)
        target_key = cls._image_variant_key(og_url)
        candidates = [og_url]
        pattern = r"https://[^\"'<>\s]+\.(?:jpe?g|png|webp)"
        for url in re.findall(pattern, html or "", flags=re.I):
            url = url.replace("&amp;", "&")
            if cls._image_variant_key(url) == target_key:
                candidates.append(url)

        def score(url):
            match = re.search(r"/(\d+)x(\d+)/", url)
            if not match:
                return 0
            return int(match.group(1)) * int(match.group(2))

        return max(dict.fromkeys(candidates), key=score)

    def _parse_magazine_html(self, url, final_url, html, body_text=None, source="MAGALU_PAGINA"):
        generic = self.generic._parse_html(url, final_url, html, source=source)
        soup = BeautifulSoup(html, "html.parser")
        text = body_text or soup.get_text("\n", strip=True)
        objects = self._json_objects(soup)
        structured = self._structured_pairs(objects)

        attributes = self._merge_attributes(generic.get("attributes"), structured)
        attributes = [
            row for row in attributes
            if not re.search(
                r"^(?:\(Produto \+ Frete\)|\d{2}x\s+de\s+R\$|Numero de parcelas|Total$)",
                clean_text(row.get("name")) or "",
                re.I,
            )
        ]
        attributes_text = "\n".join(
            f"{row['name']}: {row['value_name']}" for row in attributes
        )
        brand, model, mpn = self._refine_identity(generic, attributes)
        gtin = self._gtin_from_attributes(attributes, generic.get("gtin"))

        pix_price = self._pix_price_from_text(text)
        regular_text_price = self._regular_price_from_text(text)
        structured_price, structured_previous = self._structured_product_prices(objects)
        product_code = self.product_code_from_url(final_url or url)
        product_attributes = self._product_attributes_only(attributes, brand=brand, model=model, mpn=mpn)
        best_image = self._best_product_image(soup, html, generic.get("image_url"))
        selected_variants = self._selected_variants(soup)
        kit_combo = self._kit_combo_info(generic.get("title") or "", attributes)

        page_description = self._description_section(text)
        description = generic.get("description")
        if description and re.search(r"<[^>]+>", description):
            description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
            description = clean_text(description)
        if page_description:
            if description and page_description.casefold() not in description.casefold():
                description = clean_text(f"{description} {page_description}")
            else:
                description = page_description or description

        available = generic.get("available")
        text_low = text.casefold()
        if any(term in text_low for term in ("produto indisponível", "produto indisponivel", "avise-me quando chegar")):
            available = False
        elif any(term in text_low for term in ("adicionar à sacola", "adicionar a sacola", "comprar agora")):
            available = True

        if pix_price is not None:
            price = pix_price
            price_source = "MAGALU_PIX"
        elif structured_price is not None:
            price = structured_price
            price_source = "MAGALU_ESTRUTURADO"
        elif generic.get("price") is not None:
            price = generic.get("price")
            price_source = generic.get("price_source")
        else:
            price = regular_text_price
            price_source = "MAGALU_TEXTO_PRECO" if regular_text_price is not None else None

        # Não tratar parcelamento como preço anterior. Preferimos o elemento
        # explicitamente marcado pelo Magalu como price-original; depois, rótulos
        # textuais explícitos e JSON-LD highPrice.
        previous = self._original_price_from_html(soup, current_price=price)
        if previous is None:
            previous = self._explicit_previous_price(text)
        if previous is None:
            previous = structured_previous
        if previous is None:
            previous = generic.get("previous_price")
        if previous is not None and price is not None and previous <= price:
            previous = None

        result = dict(generic)
        result.update({
            "ok": bool(generic.get("title")),
            "source": source,
            "url_original": url,
            "url_final": final_url,
            "brand": brand,
            "model": model,
            "mpn": mpn,
            "gtin": gtin,
            "image_url": best_image,
            "description": description,
            "price": price,
            "previous_price": previous,
            "price_source": price_source,
            "available": available,
            "marketplace_product_code": product_code,
            "product_attributes": product_attributes,
            "selected_variants": selected_variants,
            "kit_combo": kit_combo,
            "attributes": attributes,
            "attributes_text": attributes_text,
            "error": None if generic.get("title") else "MAGALU_SEM_DADOS_DE_PRODUTO",
        })
        return result

    def _http_get(self, url):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait(url)
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code == 429 and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(30.0, max(4.0, float(retry_after)))
                    except (TypeError, ValueError):
                        delay = 5.0
                    time.sleep(delay)
                    continue
                if response.status_code in (500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(4.0)
                    continue
                response.raise_for_status()
                return response, None
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(4.0)
                    continue
        return None, last_error

    @classmethod
    def _capture_has_product_evidence(cls, url: str, html: str, title: str = "", text: str = ""):
        if not cls.is_product_url(url):
            return False
        html = html or ""
        title = clean_text(title) or ""
        text = clean_text(text) or ""
        if len(html.strip()) < 80:
            return False
        soup = BeautifulSoup(html, "html.parser")
        has_product_json = bool(GenericScraper._product_json_ld(soup))
        has_h1 = bool(clean_text(soup.select_one("h1").get_text(" ", strip=True)) if soup.select_one("h1") else None)
        has_title = bool(title and len(title) >= 6)
        has_product_signal = bool(
            re.search(r"(?:adicionar\s+[àa]\s+sacola|comprar\s+agora|produto\s+indispon[ií]vel|avise-me\s+quando\s+chegar)", text, re.I)
        )
        return has_product_json or (has_h1 and (has_title or has_product_signal))

    @staticmethod
    def _is_verification_url(url: str | None):
        low = (url or "").casefold()
        return any(marker in low for marker in (
            "/az-request-verify",
            "/account-verification",
            "/challenge/",
        ))

    @classmethod
    def _is_access_error_page(cls, title: str | None, text: str | None, url: str | None = None):
        if cls._is_verification_url(url):
            return True
        sample = " ".join(filter(None, [clean_text(title), clean_text(text)]))[:8000].casefold()
        terms = (
            "não é possível acessar a página",
            "nao e possivel acessar a pagina",
            "não foi possível acessar a página",
            "this site can't be reached",
            "this site can’t be reached",
            "access denied",
            "403 forbidden",
            "erro de privacidade",
            "err_connection_",
            "err_timed_out",
            # Página real observada no Magazine Você/Magalu em IP de datacenter.
            "acessou nosso site de uma forma um pouco diferente do comum",
            "para sua segurança precisamos de uma verificação rápida",
            "para sua seguranca precisamos de uma verificacao rapida",
            "essa é uma etapa simples e rápida",
            "essa e uma etapa simples e rapida",
        )
        return any(term in sample for term in terms)

    @classmethod
    def _magazineluiza_equivalent_url(cls, url: str):
        """Converte uma página Magazine Você para a página pública equivalente
        do Magazine Luiza quando a estrutura da URL permite.

        Não tenta contornar CAPTCHA; apenas usa outra página pública do mesmo
        ecossistema para o mesmo código de produto.
        """
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").casefold()
        if not host.endswith("magazinevoce.com.br"):
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 3 or not parts[0].casefold().startswith("magazine"):
            return None
        new_path = "/" + "/".join(parts[1:])
        if parsed.path.endswith("/"):
            new_path += "/"
        return urlunparse((
            "https",
            "www.magazineluiza.com.br",
            new_path,
            "",
            parsed.query,
            "",
        ))

    @classmethod
    def _magazineluiza_candidate_urls(cls, url: str):
        """Gera URLs públicas alternativas do mesmo produto no ecossistema Magalu.

        A ordem prioriza a página oficial desktop e depois variações sem
        ``seller_id`` e no domínio móvel. Nenhuma delas resolve CAPTCHA; são
        apenas URLs públicas do mesmo código de produto que podem ter políticas
        de entrega/cache diferentes na borda.
        """
        base = cls._magazineluiza_equivalent_url(url)
        if not base:
            return []

        result = []
        seen = set()

        def add(mode: str, candidate: str):
            if candidate and candidate not in seen:
                seen.add(candidate)
                result.append((mode, candidate))

        add("MAGAZINELUIZA", base)

        parsed = urlparse(base)
        query_without_seller = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() != "seller_id"
        ]
        no_seller = urlunparse(parsed._replace(query=urlencode(query_without_seller, doseq=True)))
        add("MAGAZINELUIZA_SEM_SELLER", no_seller)

        mobile = urlunparse(parsed._replace(netloc="m.magazineluiza.com.br"))
        add("MAGAZINELUIZA_MOBILE", mobile)

        mobile_parsed = urlparse(mobile)
        mobile_no_seller = urlunparse(
            mobile_parsed._replace(query=urlencode(query_without_seller, doseq=True))
        )
        add("MAGAZINELUIZA_MOBILE_SEM_SELLER", mobile_no_seller)

        return result

    @classmethod
    def _response_is_product_page(cls, requested_url: str, final_url: str, html: str):
        soup = BeautifulSoup(html or "", "html.parser")
        title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
        text = soup.get_text(" ", strip=True)[:12000]
        if cls._is_access_error_page(title, text, final_url):
            return False
        evidence_url = final_url if cls.is_product_url(final_url) else requested_url
        return cls._capture_has_product_evidence(evidence_url, html, title, text)

    @classmethod
    def _cacheable_result(cls, result: dict):
        return bool(
            isinstance(result, dict)
            and result.get("ok")
            and result.get("title")
            and not result.get("blocked")
            and not cls._is_verification_url(result.get("url_final"))
            and not cls._is_access_error_page(result.get("title"), result.get("description"), result.get("url_final"))
        )

    def collect_from_local_capture(self, url: str, capture: dict):
        """Processa uma captura feita no navegador LOCAL do usuário.

        A captura contém apenas HTML/texto/URL/título da página. O arquivo não
        precisa nem deve conter cookies, tokens ou dados do perfil do navegador.
        """
        if not isinstance(capture, dict):
            return {
                "ok": False,
                "source": "MAGALU_NAVEGADOR_LOCAL",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "marketplace_product_code": self.product_code_from_url(url),
                "local_capture": True,
                "error": "MAGALU_CAPTURA_LOCAL_INVALIDA",
            }

        final_url = clean_text(capture.get("final_url")) or url
        html = capture.get("html") or ""
        text = capture.get("text") or ""
        title = capture.get("title") or ""

        if not self.is_product_url(final_url) and not self.is_product_url(url):
            return {
                "ok": False,
                "source": "MAGALU_NAVEGADOR_LOCAL",
                "api_used": False,
                "url_original": url,
                "url_final": final_url,
                "marketplace_product_code": None,
                "local_capture": True,
                "blocked": False,
                "error": "MAGALU_URL_NAO_E_PAGINA_DE_PRODUTO",
            }

        if capture.get("blocked") or capture.get("error") or self._is_access_error_page(title, text, final_url):
            return {
                "ok": False,
                "source": "MAGALU_NAVEGADOR_LOCAL",
                "api_used": False,
                "url_original": url,
                "url_final": final_url,
                "marketplace_product_code": self.product_code_from_url(final_url) or self.product_code_from_url(url),
                "local_capture": True,
                "blocked": True,
                "error": clean_text(capture.get("error")) or "MAGALU_CAPTURA_LOCAL_SEM_ACESSO_A_PAGINA",
            }

        if not self._capture_has_product_evidence(final_url if self.is_product_url(final_url) else url, html, title, text):
            return {
                "ok": False,
                "source": "MAGALU_NAVEGADOR_LOCAL",
                "api_used": False,
                "url_original": url,
                "url_final": final_url,
                "marketplace_product_code": self.product_code_from_url(final_url) or self.product_code_from_url(url),
                "local_capture": True,
                "blocked": False,
                "error": "MAGALU_CAPTURA_LOCAL_INCOMPLETA",
            }

        result = self._parse_magazine_html(
            url,
            final_url,
            html,
            body_text=text,
            source="MAGALU_NAVEGADOR_LOCAL",
        )
        result["local_capture"] = True
        result["cache_hit"] = False
        if not result.get("title") or self._is_access_error_page(result.get("title"), text, final_url):
            result["ok"] = False
            result["blocked"] = bool(self._is_access_error_page(result.get("title"), text, final_url))
            result["error"] = "MAGALU_CAPTURA_LOCAL_SEM_DADOS_DE_PRODUTO"
        return result

    def _try_http_product(self, original_url: str, candidate_url: str, source: str):
        response, error = self._http_get(candidate_url)
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code in (404, 410):
            return None, error, False
        if response is None:
            return None, error, False

        html = response.text or ""
        blocked = self._is_access_error_page(None, html, response.url)
        if blocked or not self._response_is_product_page(candidate_url, response.url, html):
            return None, error, blocked

        result = self._parse_magazine_html(
            original_url,
            response.url,
            html,
            source=source,
        )
        result["blocked"] = False
        result["url_original"] = original_url
        return result, error, False

    def _try_browser_product(self, original_url: str, candidate_url: str, source: str):
        from .browser_scraper import BrowserScraper

        browser = BrowserScraper().fetch(candidate_url)
        if browser.get("error"):
            return None, browser.get("error"), False
        title = browser.get("title") or ""
        body_text = browser.get("text") or ""
        final_url = browser.get("final_url") or candidate_url
        blocked = bool(browser.get("blocked")) or self._is_access_error_page(title, body_text, final_url)
        if blocked:
            return None, None, True
        if not self._capture_has_product_evidence(
            final_url if self.is_product_url(final_url) else candidate_url,
            browser.get("html") or "",
            title,
            body_text,
        ):
            return None, "MAGALU_NAVEGADOR_SEM_EVIDENCIA_DE_PRODUTO", False

        result = self._parse_magazine_html(
            original_url,
            final_url,
            browser.get("html") or "",
            body_text=body_text,
            source=source,
        )
        result["blocked"] = False
        result["url_original"] = original_url
        return result, None, False

    def _try_browserless_product(self, original_url: str, candidate_url: str, source: str):
        from .browser_scraper import BrowserScraper

        scraper = BrowserScraper()
        if not scraper.browserless_configured():
            return None, "BROWSERLESS_NAO_CONFIGURADO", False
        browser = scraper.fetch_browserless(candidate_url)
        if browser.get("error"):
            return None, browser.get("error"), False
        title = browser.get("title") or ""
        body_text = browser.get("text") or ""
        final_url = browser.get("final_url") or candidate_url
        blocked = bool(browser.get("blocked")) or self._is_access_error_page(title, body_text, final_url)
        if blocked:
            return None, None, True
        if not self._capture_has_product_evidence(
            final_url if self.is_product_url(final_url) else candidate_url,
            browser.get("html") or "",
            title,
            body_text,
        ):
            return None, "MAGALU_BROWSERLESS_SEM_EVIDENCIA_DE_PRODUTO", False

        result = self._parse_magazine_html(
            original_url,
            final_url,
            browser.get("html") or "",
            body_text=body_text,
            source=source,
        )
        result["blocked"] = False
        result["url_original"] = original_url
        result["browserless"] = True
        result["proxy_network"] = browser.get("proxy")
        result["proxy_country"] = browser.get("proxy_country")
        return result, None, False

    def collect(self, url, no_browser=False):
        if not self.is_product_url(url):
            return {
                "ok": False,
                "source": "MAGALU_VALIDACAO_URL",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "marketplace_product_code": None,
                "cache_hit": False,
                "error": "MAGALU_URL_NAO_E_PAGINA_DE_PRODUTO",
            }

        cached = self.cache.get(
            url,
            namespace=self.cache_namespace,
            ttl_seconds=self.cache_ttl,
        )
        if isinstance(cached, dict) and self._cacheable_result(cached):
            cached = dict(cached)
            cached["cache_hit"] = True
            return cached

        attempts = []
        any_blocked = False
        last_error = None

        # 1) URL original por HTTP.
        result, error, blocked = self._try_http_product(url, url, "MAGALU_PAGINA")
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code in (404, 410):
            return {
                "ok": False,
                "source": "MAGALU_HTTP",
                "api_used": False,
                "url_original": url,
                "url_final": url,
                "marketplace_product_code": self.product_code_from_url(url),
                "cache_hit": False,
                "blocked": False,
                "error": "MAGALU_URL_404" if status_code == 404 else "MAGALU_PRODUTO_REMOVIDO",
            }
        attempts.append({"modo": "HTTP_ORIGINAL", "url": url, "bloqueado": blocked, "erro": clean_text(str(error)) if error else None})
        any_blocked = any_blocked or blocked
        last_error = error or last_error
        if self._cacheable_result(result):
            result["cache_hit"] = False
            result["tentativasColeta"] = attempts
            self.cache.set(url, result, namespace=self.cache_namespace)
            return result

        # 2) Mesmo link em Chromium/Playwright.
        if not no_browser:
            try:
                result, error, blocked = self._try_browser_product(url, url, "MAGALU_NAVEGADOR")
            except Exception as exc:
                result, error, blocked = None, str(exc), False
            attempts.append({"modo": "NAVEGADOR_ORIGINAL", "url": url, "bloqueado": blocked, "erro": clean_text(str(error)) if error else None})
            any_blocked = any_blocked or blocked
            last_error = error or last_error
            if self._cacheable_result(result):
                result["cache_hit"] = False
                result["tentativasColeta"] = attempts
                self.cache.set(url, result, namespace=self.cache_namespace)
                return result

        # 3) Para Magazine Você, tenta páginas públicas equivalentes do
        # Magazine Luiza para o MESMO código de produto. Primeiro HTTP nas
        # variações desktop/móvel e com/sem seller_id; depois navegador.
        # Isso não resolve CAPTCHA: apenas tenta endpoints públicos oficiais
        # equivalentes que podem ter comportamento diferente na borda.
        alternative_candidates = self._magazineluiza_candidate_urls(url)

        for mode, alternative_url in alternative_candidates:
            http_source = (
                "MAGALU_URL_ALTERNATIVA_HTTP"
                if mode == "MAGAZINELUIZA"
                else f"MAGALU_URL_ALTERNATIVA_HTTP_{mode}"
            )
            result, error, blocked = self._try_http_product(
                url,
                alternative_url,
                http_source,
            )
            attempts.append({
                "modo": f"HTTP_{mode}",
                "url": alternative_url,
                "bloqueado": blocked,
                "erro": clean_text(str(error)) if error else None,
            })
            any_blocked = any_blocked or blocked
            last_error = error or last_error
            if self._cacheable_result(result):
                result["cache_hit"] = False
                result["tentativasColeta"] = attempts
                self.cache.set(url, result, namespace=self.cache_namespace)
                return result

        if not no_browser:
            for mode, alternative_url in alternative_candidates:
                try:
                    browser_source = (
                        "MAGALU_URL_ALTERNATIVA_NAVEGADOR"
                        if mode == "MAGAZINELUIZA"
                        else f"MAGALU_URL_ALTERNATIVA_NAVEGADOR_{mode}"
                    )
                    result, error, blocked = self._try_browser_product(
                        url,
                        alternative_url,
                        browser_source,
                    )
                except Exception as exc:
                    result, error, blocked = None, str(exc), False
                attempts.append({
                    "modo": f"NAVEGADOR_{mode}",
                    "url": alternative_url,
                    "bloqueado": blocked,
                    "erro": clean_text(str(error)) if error else None,
                })
                any_blocked = any_blocked or blocked
                last_error = error or last_error
                if self._cacheable_result(result):
                    result["cache_hit"] = False
                    result["tentativasColeta"] = attempts
                    self.cache.set(url, result, namespace=self.cache_namespace)
                    return result

        # 4) Ultimo fallback cloud: Browserless com proxy residencial.
        # So consome unidades quando as tentativas HTTP/Chromium da Railway falharam.
        if not no_browser:
            browserless_candidates = [("ORIGINAL", url)] + alternative_candidates
            for mode, candidate_url in browserless_candidates:
                try:
                    result, error, blocked = self._try_browserless_product(
                        url,
                        candidate_url,
                        "MAGALU_BROWSERLESS_RESIDENCIAL",
                    )
                except Exception as exc:
                    result, error, blocked = None, str(exc), False
                # Se nao estiver configurado, registrar explicitamente no diagnostico.
                if error == "BROWSERLESS_NAO_CONFIGURADO":
                    attempts.append({
                        "modo": "BROWSERLESS_CONFIG",
                        "url": candidate_url,
                        "bloqueado": False,
                        "erro": error,
                    })
                    break
                attempts.append({
                    "modo": f"BROWSERLESS_{mode}",
                    "url": candidate_url,
                    "bloqueado": blocked,
                    "erro": clean_text(str(error)) if error else None,
                })
                any_blocked = any_blocked or blocked
                last_error = error or last_error
                # Falha de conexao/conta do Browserless nao melhora ao trocar a URL
                # do mesmo produto; evita repetir conexoes e gastar unidades.
                if error and (
                    str(error).startswith("Falha no Browserless")
                    or str(error).startswith("Timeout do Browserless")
                ):
                    break
                if self._cacheable_result(result):
                    result["cache_hit"] = False
                    result["tentativasColeta"] = attempts
                    self.cache.set(url, result, namespace=self.cache_namespace)
                    return result

        error_code = "MAGALU_COLETA_BLOQUEADA" if any_blocked else "MAGALU_SEM_DADOS_DE_PRODUTO"
        return {
            "ok": False,
            "source": "MAGALU_BLOQUEADO" if any_blocked else "MAGALU_COLETA_FALHOU",
            "api_used": False,
            "url_original": url,
            # Não devolver URL de az-request-verify como se fosse produto.
            "url_final": url,
            "marketplace_product_code": self.product_code_from_url(url),
            "cache_hit": False,
            "blocked": any_blocked,
            "requires_local_capture": any_blocked,
            "collection_attempts": attempts,
            "error": error_code if any_blocked else (
                f"MAGALU_ERRO_COLETA: {last_error}" if last_error else error_code
            ),
        }
