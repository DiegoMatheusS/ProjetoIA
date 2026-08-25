import argparse
import json
import sys

from dotenv import load_dotenv
from loguru import logger
from .scrapers.mercadolivre_scraper import MercadoLivreScraper
from .scrapers.generic_scraper import GenericScraper
from .extractors.category import detect_category
from .extractors.backend_schemas import SCHEMAS, REQUIRED
from .extractors.ml_specs import extract_specs
from .utils.data_handler import DataHandler

load_dotenv()


def build_result(raw, forced_category=None):
    text = "\n".join(filter(None, [
        raw.get("title"), raw.get("brand"), raw.get("model"), raw.get("description"), raw.get("attributes_text")
    ]))
    category = detect_category(text, forced_category)
    specs = extract_specs(category, raw.get("attributes") or [])
    schema = SCHEMAS.get(category) if category else None
    tipo_cadastro, spec_field, expected = schema if schema else (None, None, [])

    payload = {
        "nome": raw.get("title"),
        "marca": raw.get("brand"),
        "modelo": raw.get("model"),
        "descricao": raw.get("description"),
        "mpn": raw.get("model"),
        "gtin": raw.get("gtin"),
        "imagemUrl": raw.get("image_url"),
    }
    if category and tipo_cadastro == "HARDWARE":
        payload["categoria"] = category
    if spec_field:
        payload[spec_field] = specs

    missing = [f for f in REQUIRED.get(category, []) if specs.get(f) in (None, "", [])]

    return {
        "categoriaDetectada": category,
        "tipoCadastro": tipo_cadastro,
        "payloadParcialBackend": payload,
        "ofertaColetada": {
            "preco": raw.get("price"),
            "precoAnterior": raw.get("previous_price"),
            "moeda": raw.get("currency") or "BRL",
            "disponivel": raw.get("available"),
            "urlOriginal": raw.get("url_original"),
            "urlProduto": raw.get("url_final"),
            "vendedorId": raw.get("seller_id"),
        },
        "especificacoesEncontradas": specs,
        "camposEspecificacaoEsperados": expected,
        "camposObrigatoriosAusentes": missing,
        "marketplace": {
            "plataforma": "MERCADO_LIVRE" if MercadoLivreScraper.is_mercadolivre(raw.get("url_original") or "") else None,
            "apiUsada": raw.get("api_used", False),
            "itemId": raw.get("item_id"),
            "catalogProductId": raw.get("catalog_product_id"),
            "errosApi": raw.get("api_errors", []),
            "bloqueadoNoNavegador": bool(raw.get("blocked")),
        },
        "fonte": raw.get("source"),
        "erro": raw.get("error"),
    }


def main():
    parser = argparse.ArgumentParser(description="Coletor de produtos do CriaByte em Python")
    parser.add_argument("url", help="URL do produto")
    parser.add_argument("categoria", nargs="?", help="Categoria forçada, ex.: PROCESSADOR")
    parser.add_argument("--save", action="store_true", help="Salvar JSON e CSV em data/raw")
    parser.add_argument("--no-browser", action="store_true", help="Não usar navegador como fallback")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    if MercadoLivreScraper.is_mercadolivre(args.url):
        raw = MercadoLivreScraper().collect(args.url, no_browser=args.no_browser)
    else:
        raw = GenericScraper().collect(args.url)
        raw.setdefault("source", "NAVEGADOR_GENERICO")
        raw.setdefault("api_used", False)

    result = build_result(raw, args.categoria)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.save:
        handler = DataHandler()
        base = result.get("marketplace", {}).get("itemId") or "produto"
        json_path = handler.save_json(result, base)
        csv_path = handler.save_csv(result, base)
        logger.info(f"JSON salvo: {json_path}")
        logger.info(f"CSV salvo: {csv_path}")


if __name__ == "__main__":
    main()
