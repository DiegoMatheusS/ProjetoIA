import argparse
import json
import sys

from dotenv import load_dotenv
from loguru import logger

from .scrapers.mercadolivre_scraper import MercadoLivreScraper
from .scrapers.magazine_scraper import MagazineScraper
from .extractors.category import detect_category
from .extractors.backend_schemas import SCHEMAS, REQUIRED, CATEGORY_SLUGS
from .extractors.ml_specs import extract_specs
from .utils.data_handler import DataHandler
from .utils.sites import detect_site

load_dotenv()


def build_result(raw, forced_category=None):
    text = "\n".join(filter(None, [
        raw.get("title"),
        raw.get("brand"),
        raw.get("model"),
        raw.get("description"),
        raw.get("attributes_text"),
    ]))

    category = detect_category(text, forced_category)
    specs = extract_specs(
        category,
        raw.get("attributes") or [],
        context_text=text,
    )

    schema = SCHEMAS.get(category) if category else None
    tipo_cadastro, spec_field, expected = schema if schema else (None, None, [])

    payload = {
        "nome": raw.get("title"),
        "marca": raw.get("brand"),
        "modelo": raw.get("model"),
        "descricao": raw.get("description"),
        # Não usar MODEL como MPN. MPN só entra quando o marketplace realmente
        # fornece part number / manufacturer part number.
        "mpn": raw.get("mpn"),
        "gtin": raw.get("gtin"),
        "imagemUrl": raw.get("image_url"),
    }

    if category and tipo_cadastro == "HARDWARE":
        payload["categoria"] = category

    if spec_field:
        payload[spec_field] = specs

    # Builds e produtos sem tabela técnica própria não recebem campos
    # desconhecidos no payload. As especificações continuam em
    # especificacoesEncontradas para revisão do ADMIN.
    if category == "PC_MONTADO":
        for key in ("finalidade", "resolucaoRecomendada"):
            if specs.get(key) not in (None, "", []):
                payload[key] = specs[key]

    missing = [
        field
        for field in REQUIRED.get(category, [])
        if specs.get(field) in (None, "", [])
    ]

    site = detect_site(raw.get("url_original") or "")

    return {
        "categoriaDetectada": category,
        "categoriaSlugSugerida": CATEGORY_SLUGS.get(category),
        "tipoCadastro": tipo_cadastro,
        "payloadParcialBackend": payload,
        "ofertaColetada": {
            "preco": raw.get("price"),
            "precoAnterior": raw.get("previous_price"),
            "fontePreco": raw.get("price_source"),
            "moeda": raw.get("currency") or "BRL",
            "disponivel": raw.get("available"),
            "urlOriginal": raw.get("url_original"),
            "urlProduto": raw.get("url_final"),
            "vendedorId": raw.get("seller_id"),
            "vendedorMarketplace": raw.get("seller_name"),
            "vendedorMarketplaceSlug": raw.get("seller_slug"),
            "codigoMarketplace": raw.get("marketplace_product_code"),
        },
        "especificacoesEncontradas": specs,
        "camposEspecificacaoEsperados": expected,
        "camposObrigatoriosAusentes": missing,
        "origemColeta": {
            **site,
            "fonte": raw.get("source"),
        },
        "politicaColeta": {
            "modo": "URL_INDIVIDUAL",
            "semCrawlerEmMassa": True,
            "delayEntreRequisicoes": True,
            "retriesLimitados": True,
            "cacheAtivo": True,
            "cacheUsadoNestaExecucao": bool(raw.get("cache_hit")),
        },
        "marketplace": {
            "plataforma": (
                "MERCADO_LIVRE"
                if MercadoLivreScraper.is_mercadolivre(
                    raw.get("url_original") or ""
                )
                else None
            ),
            "apiUsada": raw.get("api_used", False),
            "itemId": raw.get("item_id"),
            "catalogProductId": raw.get("catalog_product_id"),
            "buyBoxItemId": raw.get("buy_box_item_id"),
            "catalogOfferEncontrada": raw.get("catalog_offer_found", False),
            "errosApi": raw.get("api_errors", []),
            "diagnosticoApi": raw.get("api_debug", []),
            "bloqueadoNoNavegador": bool(raw.get("blocked")),
        },
        "fonte": raw.get("source"),
        "erro": raw.get("error"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Coletor de produtos do CriaByte em Python"
    )
    parser.add_argument("url", help="URL do produto")
    parser.add_argument(
        "categoria",
        nargs="?",
        help="Categoria forçada, ex.: PROCESSADOR",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Salvar JSON e CSV em data/raw",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não usar navegador como fallback",
    )
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    if MercadoLivreScraper.is_mercadolivre(args.url):
        raw = MercadoLivreScraper().collect(
            args.url,
            no_browser=args.no_browser,
        )
    elif MagazineScraper.is_magazine(args.url):
        raw = MagazineScraper().collect(
            args.url,
            no_browser=args.no_browser,
        )
    else:
        from .scrapers.generic_scraper import GenericScraper
        raw = GenericScraper().collect(args.url, no_browser=args.no_browser)
        raw.setdefault("source", "NAVEGADOR_GENERICO")
        raw.setdefault("api_used", False)

    result = build_result(raw, args.categoria)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.save:
        handler = DataHandler()
        base_name = (
            result.get("marketplace", {}).get("itemId")
            or "produto"
        )
        json_path = handler.save_json(result, base_name)
        csv_path = handler.save_csv(result, base_name)
        logger.info(f"JSON salvo: {json_path}")
        logger.info(f"CSV salvo: {csv_path}")


if __name__ == "__main__":
    main()
