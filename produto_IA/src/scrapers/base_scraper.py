import requests
from bs4 import BeautifulSoup
import time
import random
from loguru import logger
from dotenv import load_dotenv
import os

load_dotenv()

class BaseScraper:
    def __init__(self, base_url, headers=None):
        self.base_url = base_url
        self.headers = headers or {
            'User-Agent': os.getenv('USER_AGENT', 'ProjetoIA-Scraper/1.0')
        }
        self.timeout = int(os.getenv('TIMEOUT', 10))

    def fetch_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                logger.info(f"Buscando: {url}")
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                logger.error(f"Tentativa {attempt+1} falhou: {e}")
                if attempt < retries - 1:
                    delay = random.uniform(
                        float(os.getenv('DELAY_MIN', 1)), 
                        float(os.getenv('DELAY_MAX', 3))
                    )
                    time.sleep(delay)
        return None

    def parse_product(self, html):
        raise NotImplementedError("Cada site precisa implementar seu próprio parser")