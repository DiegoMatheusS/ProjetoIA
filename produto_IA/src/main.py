from scrapers.mercadolivre_scraper import MercadoLivreScraper
from utils.data_handler import DataHandler
from loguru import logger
import sys

logger.add(sys.stderr, level="INFO")

def main():
    logger.info("🚀 Iniciando Projeto IA Scraper")
    
    try:
        # Inicializa o scraper do Mercado Livre
        scraper = MercadoLivreScraper()
        data_handler = DataHandler()
        
        # 🔥 SEU ID DO PRODUTO
        product_id = "MLB-7254149004"  # ← Você copiou este ID
        
        logger.info(f"Buscando produto ID: {product_id}")
        product_data = scraper.search_product(product_id)
        
        if product_data and product_data.get('title'):
            # Salva os dados
            json_file = data_handler.save_json(product_data, f"produto_{product_id}")
            csv_file = data_handler.save_csv(product_data, f"produto_{product_id}")
            logger.info(f"✅ Dados salvos com sucesso!")
            logger.info(f"📁 JSON: {json_file}")
            logger.info(f"📁 CSV: {csv_file}")
        else:
            logger.warning("❌ Produto não encontrado ou erro na extração")
        
        logger.info("✅ Processo finalizado!")
        
    except Exception as e:
        logger.error(f"❌ Erro: {e}")

if __name__ == "__main__":
    main()