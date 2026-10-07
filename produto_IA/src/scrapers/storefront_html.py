"""Fallbacks de HTML do produto principal, sem ler recomendações ou parcelas."""
import json
import re
from urllib.parse import urljoin, urlsplit

from ..utils.normalizers import clean_text, to_float


SELECTORS = {
    "AMAZON": {
        "domains": ("amazon.com.br",),
        "title": ("#productTitle",),
        "image": ("#landingImage", "#imgBlkFront"),
        "price": (
            "#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen",
            "#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen",
            ".priceToPay .a-offscreen",
            "#priceblock_dealprice",
            "#priceblock_ourprice",
        ),
    },
    "MERCADO_LIVRE": {
        "domains": ("mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com"),
        "title": ("h1.ui-pdp-title",),
        "image": (".ui-pdp-gallery img", "img.ui-pdp-image"),
        "price": (
            ".ui-pdp-price__second-line .andes-money-amount:not(.andes-money-amount--previous)",
            ".ui-pdp-price__main-container .andes-money-amount:not(.andes-money-amount--previous)",
            "[data-testid='price-part'] .andes-money-amount:not(.andes-money-amount--previous)",
        ),
    },
    "MAGALU": {
        "domains": ("magazineluiza.com.br", "magazinevoce.com.br", "magalu.com"),
        "title": ("[data-testid='heading-product-title']",),
        "image": ("[data-testid='image-selected-thumbnail'] img", "[data-testid='product-image'] img"),
        "price": ("[data-testid='price-value']",),
    },
    "KABUM": {
        "domains": ("kabum.com.br",),
        "title": ("h1", "[data-testid='product-title']", "[data-testid='productName']"),
        "image": ("main img[data-testid='product-image']", "main img[fetchpriority='high']", "main img"),
        "price": (
            "[data-testid='price']", "[data-testid='price-value']",
            "[class*='finalPrice']", "[class*='priceCard']",
        ),
    },
    "PICHAU": {
        "domains": ("pichau.com.br",),
        "title": ("h1", "[class*='product-name']", "[class*='productName']"),
        "image": ("main img[fetchpriority='high']", "[class*='gallery'] img", "main img"),
        "price": (
            "#valor-promocional", "[class*='special-price'] [class*='price']",
            "[class*='price-boleto']", "[class*='pricePix']",
        ),
    },
    "TERABYTE": {
        "domains": ("terabyteshop.com.br",),
        "title": ("h1", ".tit-prod", "[class*='product-name']"),
        "image": (".img-produto", "[class*='gallery'] img", "main img"),
        "price": (
            "#valVista", ".valVista", "[class*='precoAvista']",
            "[class*='pricePix']", "[data-testid='price']",
        ),
    },
    "SHOPEE": {
        "domains": ("shopee.com.br",),
        "title": ("h1", "[data-testid='product-title']"),
        "image": ("main img[fetchpriority='high']", "[data-testid='product-image'] img"),
        "price": ("[data-testid='product-price']", "[data-testid='price']"),
    },
    "ALIEXPRESS": {
        "domains": ("aliexpress.com",),
        "title": ("h1[data-pl='product-title']", "h1", "[class*='product-title']"),
        "image": ("[class*='magnifier'] img", "main img[fetchpriority='high']", "main img"),
        "price": (
            "[class*='product-price-value']", "[class*='price--current']",
            "[data-pl='product-price']",
        ),
    },
}


def _public_image(value, page_url):
    address = urljoin(page_url, clean_text(value) or "")
    try:
        parsed = urlsplit(address)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
            return address if value else None
    except ValueError:
        pass
    return None


def _image(node, page_url):
    for attr in ("data-old-hires", "data-zoom", "data-src"):
        if address := _public_image(node.get(attr), page_url):
            return address
    # Amazon publica as resoluções da foto em um atributo JSON.
    try:
        dynamic = json.loads(node.get("data-a-dynamic-image") or "{}")
    except (ValueError, TypeError):
        dynamic = {}
    candidates = []
    if isinstance(dynamic, dict):
        for value, dimensions in dynamic.items():
            if (isinstance(dimensions, list) and len(dimensions) == 2
                    and all(isinstance(size, (int, float)) and size > 0 for size in dimensions)):
                if address := _public_image(value, page_url):
                    candidates.append((dimensions[0] * dimensions[1], address))
    if candidates:
        return max(candidates)[1]
    return _public_image(node.get("src"), page_url)


def _price(node):
    text = clean_text(node.get_text(" ", strip=True)) or ""
    # Seletores de preço não podem transformar parcelas em valor total.
    context = clean_text(node.parent.get_text(" ", strip=True)) if node.parent else text
    if re.search(r"\b\d{1,2}\s*x\b|parcela|sem\s+juros", context or "", re.I):
        return None
    fraction = node.select_one(".andes-money-amount__fraction")
    cents = node.select_one(".andes-money-amount__cents")
    if fraction:
        digits = re.sub(r"\D", "", fraction.get_text())
        decimal = re.sub(r"\D", "", cents.get_text()) if cents else "00"
        if not digits or len(decimal) != 2:
            return None
        return to_float(f"{digits}.{decimal}")
    # Exige um único valor monetário; ignora textos com frete e preços concorrentes.
    amounts = re.findall(r"R\$\s*(\d[\d.]*,\d{2})(?!\d)", text)
    prices = {to_float(value) for value in amounts}
    prices.discard(None)
    return prices.pop() if len(prices) == 1 else None


def storefront_fields(soup, page_url):
    host = (urlsplit(page_url).hostname or "").casefold()
    store, config = next(((name, config) for name, config in SELECTORS.items()
        if any(host == domain or host.endswith("." + domain) for domain in config["domains"])), (None, None))
    if not config:
        return {}
    result = {}
    for selector in config["title"]:
        if node := soup.select_one(selector):
            if title := clean_text(node.get_text(" ", strip=True)):
                result["title"] = title
                break
    for selector in config["image"]:
        for node in soup.select(selector)[:10]:
            if image := _image(node, page_url):
                result["image_url"] = image
                break
        if result.get("image_url"):
            break
    for selector in config["price"]:
        prices = {_price(node) for node in soup.select(selector)[:10]}
        prices.discard(None)
        if len(prices) > 1:
            break
        if prices and (price := prices.pop()) > 0:
            result["price"] = price
            result["price_source"] = f"HTML_{store}"
            break
    return result
