"""Texto do anúncio, separado de resumos técnicos e metadados de busca."""
import re

from bs4 import BeautifulSoup


def description_text(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value
    if re.search(r"</?[a-z][^>]*>", text, re.I):
        soup = BeautifulSoup(text, "html.parser")
        for node in soup.select("script, style, noscript, iframe"):
            node.decompose()
        for node in soup.select("br"):
            node.replace_with("\n")
        for node in soup.select("p, div, section, li, tr, h1, h2, h3, h4"):
            node.insert_before("\n")
            node.insert_after("\n")
        text = soup.get_text()
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip() or None


def listing_description(soup, product):
    # Apenas contêineres do anúncio: nunca body/main, avaliações ou recomendações.
    selectors = (
        '[itemprop="description"], #description, #descricao, #product-description, '
        '#productDescription, #feature-bullets, #aplus, .ui-pdp-description__content, '
        '.shopee-product-detail__description, [data-testid="product-description"], '
        '[data-testid="description"], [data-testid="rich-content-container"], '
        '[class*="product-description"], [class*="description__content"]'
    )
    sections = []
    for node in soup.select(selectors):
        text = description_text(str(node))
        if not text or any(text in existing for existing in sections):
            continue
        sections = [existing for existing in sections if existing not in text]
        sections.append(text)
    visible = "\n\n".join(sections)
    structured = description_text(product.get("description"))
    if visible and (not structured or len(visible) >= len(structured)):
        return visible, "PAGINA"
    if structured:
        return structured, "DADOS_ESTRUTURADOS"
    for selector in ('meta[name="description"]', 'meta[property="og:description"]'):
        node = soup.select_one(selector)
        text = description_text(node.get("content")) if node else None
        if text:
            return text, "META"
    return None, None
