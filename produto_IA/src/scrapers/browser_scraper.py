import os
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class BrowserScraper:
    def __init__(self):
        self.timeout_ms = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))
        self.headless = os.getenv("HEADLESS", "true").lower() != "false"

    def fetch(self, url: str):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                locale="pt-BR",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/152.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            try:
                logger.info(f"Abrindo navegador: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(1200)
                final_url = page.url
                title = page.title()
                html = page.content()
                body_text = page.locator("body").inner_text(timeout=5000)
                blocked = (
                    "account-verification" in final_url.lower()
                    or "verificação" in body_text.lower()[:5000]
                    or "verificacao" in body_text.lower()[:5000]
                )
                return {
                    "html": html,
                    "text": body_text,
                    "title": title,
                    "final_url": final_url,
                    "blocked": blocked,
                }
            except PlaywrightTimeoutError as exc:
                return {"error": f"Timeout do navegador: {exc}", "final_url": page.url}
            finally:
                context.close()
                browser.close()
