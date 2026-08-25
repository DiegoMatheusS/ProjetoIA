import requests
from bs4 import BeautifulSoup
import time
import random
from loguru import logger
from dotenv import load_dotenv
import os
import re

load_dotenv()

class BaseScraper:
    def __init__(self, base_url, headers=None):
        self.base_url = base_url
        self.headers = headers or {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.google.com/'
        }
        self.timeout = int(os.getenv('TIMEOUT', 15))
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def fetch_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                logger.info(f"Buscando: {url}")
                response = self.session.get(
                    url, 
                    timeout=self.timeout,
                    allow_redirects=True
                )
                response.raise_for_status()
                
                # Verifica se a página pede para aceitar cookies
                if "Acesse sua conta" in response.text or "cookies" in response.text.lower():
                    logger.warning("Página pede aceitação de cookies. Tentando novamente...")
                    time.sleep(random.uniform(2, 4))
                    continue
                
                # Verifica se tem conteúdo HTML válido
                if len(response.text) < 1000:
                    logger.warning("Página com conteúdo muito curto, pode estar bloqueada")
                    continue
                    
                return response.text
            except requests.exceptions.RequestException as e:
                logger.error(f"Tentativa {attempt+1} falhou: {e}")
                if attempt < retries - 1:
                    delay = random.uniform(
                        float(os.getenv('DELAY_MIN', 2)), 
                        float(os.getenv('DELAY_MAX', 5))
                    )
                    time.sleep(delay)
        return None

    def parse_product(self, html):
        raise NotImplementedError("Cada site precisa implementar seu próprio parser")