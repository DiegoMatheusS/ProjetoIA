from .base_scraper import BaseScraper
from bs4 import BeautifulSoup
from loguru import logger

class MercadoLivreScraper(BaseScraper):
    def __init__(self):
        super().__init__("https://www.mercadolivre.com.br")
        
    def parse_product(self, html):
        """Extrai dados de um produto do Mercado Livre"""
        soup = BeautifulSoup(html, 'html.parser')
        
        product_data = {
            'title': None,
            'price': None,
            'condition': None,
            'seller': None,
            'reviews': None,
            'url': None
        }
        
        # TÍTULO
        title = soup.find('h1', class_='ui-pdp-title')
        if title:
            product_data['title'] = title.text.strip()
        
        # PREÇO
        price = soup.find('span', class_='andes-money-amount__fraction')
        if price:
            product_data['price'] = price.text.strip()
        
        # CONDIÇÃO
        condition = soup.find('span', class_='ui-pdp-subtitle')
        if condition:
            product_data['condition'] = condition.text.strip()
        
        # VENDEDOR
        seller = soup.find('a', class_='ui-pdp-seller__header__title')
        if seller:
            product_data['seller'] = seller.text.strip()
        
        # AVALIAÇÕES
        reviews = soup.find('span', class_='ui-pdp-review__amount')
        if reviews:
            product_data['reviews'] = reviews.text.strip()
        
        logger.info(f"Dados extraídos do Mercado Livre: {product_data['title']}")
        return product_data
    
    def search_product(self, product_id):
        """Busca um produto específico pelo ID do Mercado Livre"""
        # Remove o "MLB-" se existir
        clean_id = product_id.replace("MLB-", "")
        url = f"https://www.mercadolivre.com.br/p/MLB{clean_id}"
        logger.info(f"Buscando: {url}")
        html = self.fetch_page(url)
        if html:
            return self.parse_product(html)
        return None