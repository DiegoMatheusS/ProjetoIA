from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from loguru import logger
import time

class SeleniumScraper:
    def __init__(self):
        self.driver = None
        
    def get_driver(self):
        if self.driver is None:
            options = Options()
            options.add_argument('--headless')  # Roda sem abrir janela
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        return self.driver
    
    def fetch_page(self, url, wait_time=5):
        try:
            logger.info(f"Buscando com Selenium: {url}")
            driver = self.get_driver()
            driver.get(url)
            
            # Espera o carregamento da página
            WebDriverWait(driver, wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Scroll para carregar conteúdo dinâmico
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            html = driver.page_source
            return html
            
        except Exception as e:
            logger.error(f"Erro no Selenium: {e}")
            return None
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None