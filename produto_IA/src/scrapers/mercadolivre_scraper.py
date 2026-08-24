from .base_scraper import BaseScraper
from bs4 import BeautifulSoup
from loguru import logger
import re

class MercadoLivreScraper(BaseScraper):
    def __init__(self):
        super().__init__("https://www.mercadolivre.com.br")
        
    def parse_product(self, html):
        """Extrai dados de um produto do Mercado Livre"""
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        product_data = {
            'title': None,
            'price': None,
            'condition': None,
            'seller': None,
            'reviews': None,
            'description': None,
            'url': None
        }
        
        # TÍTULO - Várias tentativas
        title_selectors = [
            'h1.ui-pdp-title',
            'h1[class*="title"]',
            'meta[property="og:title"]',
            'meta[name="title"]',
            '.product-title',
            '[itemprop="name"]'
        ]
        
        for selector in title_selectors:
            if selector.startswith('meta'):
                tag = soup.find('meta', {'property': 'og:title'}) if 'og:title' in selector else soup.find('meta', {'name': 'title'})
                if tag:
                    product_data['title'] = tag.get('content', '').strip()
                    break
            else:
                tag = soup.select_one(selector)
                if tag:
                    product_data['title'] = tag.text.strip()
                    break
        
        # Se não encontrou título, tenta por padrão
        if not product_data['title']:
            title_tag = soup.find('h1')
            if title_tag:
                product_data['title'] = title_tag.text.strip()
        
        # PREÇO - Várias tentativas
        price_selectors = [
            'span.andes-money-amount__fraction',
            'meta[itemprop="price"]',
            'meta[property="product:price:amount"]',
            '.price-tag-fraction',
            '[class*="price"] span:first-child'
        ]
        
        for selector in price_selectors:
            if 'meta' in selector:
                tag = soup.find('meta', {'itemprop': 'price'}) if 'itemprop' in selector else soup.find('meta', {'property': 'product:price:amount'})
                if tag:
                    product_data['price'] = tag.get('content', '').strip()
                    break
            else:
                tag = soup.select_one(selector)
                if tag:
                    product_data['price'] = tag.text.strip().replace('.', '').replace(',', '.')
                    break
        
        # CONDIÇÃO
        condition = soup.find('span', class_='ui-pdp-subtitle')
        if condition:
            product_data['condition'] = condition.text.strip()
        else:
            condition = soup.select_one('.condition-text')
            if condition:
                product_data['condition'] = condition.text.strip()
        
        # VENDEDOR
        seller = soup.find('a', class_='ui-pdp-seller__header__title')
        if seller:
            product_data['seller'] = seller.text.strip()
        else:
            seller = soup.select_one('.seller-info__name')
            if seller:
                product_data['seller'] = seller.text.strip()
        
        # AVALIAÇÕES
        reviews = soup.find('span', class_='ui-pdp-review__amount')
        if reviews:
            product_data['reviews'] = reviews.text.strip()
        
        # DESCRIÇÃO (se existir)
        description = soup.find('p', class_='ui-pdp-description__content')
        if description:
            product_data['description'] = description.text.strip()[:200]  # Primeiros 200 caracteres
        
        logger.info(f"Dados extraídos: {product_data['title']}")
        return product_data
    
    def search_product(self, product_id):
        """Busca um produto específico pelo ID do Mercado Livre"""
        # Limpa o ID
        clean_id = product_id.replace("MLB-", "").replace("MLB", "")
        
        # Tenta diferentes formatos de URL
        urls = [
            f"https://www.mercadolivre.com.br/p/MLB{clean_id}",
            f"https://produto.mercadolivre.com.br/MLB-{clean_id}",
            f"https://www.mercadolivre.com.br/produto/MLB-{clean_id}"
        ]
        
        for url in urls:
            logger.info(f"Tentando: {url}")
            html = self.fetch_page(url)
            if html and len(html) > 2000:  # Página com conteúdo
                result = self.parse_product(html)
                if result and result.get('title'):
                    return result
        
        # Se não encontrou, tenta com o ID do produto da URL original
        # O ID real é MLB38775549 (do processador)
        logger.warning(f"Tentando formato alternativo para: {clean_id}")
        url = f"https://www.mercadolivre.com.br/p/MLB{clean_id}"
        html = self.fetch_page(url, retries=5)
        if html:
            result = self.parse_product(html)
            if result and result.get('title'):
                return result
        
        logger.warning(f"Produto não encontrado: {product_id}")
        return None