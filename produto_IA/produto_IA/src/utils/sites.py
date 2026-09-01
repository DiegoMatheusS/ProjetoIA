from urllib.parse import urlparse


def detect_site(url: str):
    host = (urlparse(url or "").hostname or "").lower()
    rules = [
        (("mercadolivre.com.br", "mercadolibre.com"), "MERCADO_LIVRE", "API_OFICIAL"),
        (("kabum.com.br",), "KABUM", "PAGINA_ESTRUTURADA"),
        (("pichau.com.br",), "PICHAU", "PAGINA_ESTRUTURADA"),
        (("terabyteshop.com.br",), "TERABYTE", "PAGINA_ESTRUTURADA"),
        (("amazon.com.br",), "AMAZON", "PAGINA_ESTRUTURADA"),
        (("magazineluiza.com.br", "magazinevoce.com.br", "magalu.com"), "MAGALU", "EXTRATOR_ESPECIFICO"),
        (("shopee.com.br",), "SHOPEE", "PAGINA_ESTRUTURADA"),
        (("aliexpress.com",), "ALIEXPRESS", "PAGINA_ESTRUTURADA"),
    ]
    for suffixes, name, mode in rules:
        if any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            return {"plataforma": name, "host": host, "modoIntegracao": mode}
    return {"plataforma": "OUTRO_SITE", "host": host or None, "modoIntegracao": "PAGINA_ESTRUTURADA"}
