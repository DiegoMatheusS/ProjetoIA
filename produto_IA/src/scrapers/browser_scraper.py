import os
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from ..utils.rate_limiter import PoliteRateLimiter


class BrowserScraper:
    def __init__(self):
        self.timeout_ms = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))
        self.headless = os.getenv("HEADLESS", "true").lower() != "false"
        self.rate_limiter = PoliteRateLimiter(
            min_delay=float(os.getenv("BROWSER_MIN_DELAY_SECONDS", "1.8")),
            jitter=float(os.getenv("BROWSER_JITTER_SECONDS", "0.6")),
        )

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
                self.rate_limiter.wait(url)
                logger.info(f"Abrindo navegador: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(1200)
                final_url = page.url
                title = page.title()
                html = page.content()
                body_text = page.locator("body").inner_text(timeout=5000)
                sample = f"{title}\n{body_text[:5000]}".casefold()
                blocked = (
                    "account-verification" in final_url.lower()
                    or "verificação" in sample
                    or "verificacao" in sample
                    or "não é possível acessar a página" in sample
                    or "nao e possivel acessar a pagina" in sample
                    or "this site can't be reached" in sample
                    or "this site can’t be reached" in sample
                    or "access denied" in sample
                    or "403 forbidden" in sample
                    or "err_connection_" in sample
                    or "err_timed_out" in sample
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
