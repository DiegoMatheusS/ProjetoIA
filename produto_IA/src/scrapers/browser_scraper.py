import os
from urllib.parse import urlencode
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


    def browserless_configured(self):
        return bool(os.getenv("BROWSERLESS_TOKEN", "").strip())

    def fetch_browserless(self, url: str):
        """Abre a pagina no Browserless usando proxy residencial configurado.

        So e chamado como fallback cloud depois das tentativas locais da Railway.
        O token nunca e logado nem devolvido no resultado.
        """
        token = os.getenv("BROWSERLESS_TOKEN", "").strip()
        if not token:
            return {"error": "BROWSERLESS_NAO_CONFIGURADO", "final_url": url}

        base = os.getenv("BROWSERLESS_WS_URL", "wss://production-sfo.browserless.io").strip().rstrip("/")
        proxy = os.getenv("BROWSERLESS_PROXY", "residential").strip() or "residential"
        country = os.getenv("BROWSERLESS_PROXY_COUNTRY", "BR").strip() or "BR"
        sticky = os.getenv("BROWSERLESS_PROXY_STICKY", "true").strip().lower() not in {"0", "false", "no", "nao"}
        stealth = os.getenv("BROWSERLESS_STEALTH", "true").strip().lower() not in {"0", "false", "no", "nao"}
        locale_match = os.getenv("BROWSERLESS_PROXY_LOCALE_MATCH", "true").strip().lower() not in {"0", "false", "no", "nao"}

        params = {
            "token": token,
            "proxy": proxy,
            "proxyCountry": country,
            "proxySticky": "true" if sticky else "false",
            "proxyLocaleMatch": "true" if locale_match else "false",
        }
        path = "/chromium/stealth" if stealth else ""
        endpoint = f"{base}{path}?{urlencode(params)}"

        with sync_playwright() as p:
            browser = None
            context = None
            try:
                safe_host = base.replace("wss://", "").replace("ws://", "")
                logger.info(
                    f"Abrindo Browserless residencial: host={safe_host} "
                    f"proxy={proxy} pais={country} sticky={sticky} stealth={stealth}"
                )
                browser = p.chromium.connect_over_cdp(endpoint, timeout=max(self.timeout_ms, 60000))
                contexts = browser.contexts
                context = contexts[0] if contexts else browser.new_context(
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1365, "height": 900},
                    color_scheme="light",
                )
                page = context.new_page()
                self.rate_limiter.wait(url)
                page.goto(url, wait_until="domcontentloaded", timeout=max(self.timeout_ms, 60000))
                page.wait_for_timeout(3500)
                final_url = page.url
                title = page.title()
                html = page.content()
                body_text = page.locator("body").inner_text(timeout=10000)
                sample = f"{title}\n{body_text[:5000]}".casefold()
                blocked = (
                    "account-verification" in final_url.lower()
                    or "az-request-verify" in final_url.lower()
                    or "acessou nosso site de uma forma um pouco diferente do comum" in sample
                    or "para sua segurança precisamos de uma verificação rápida" in sample
                    or "para sua seguranca precisamos de uma verificacao rapida" in sample
                    or "access denied" in sample
                    or "403 forbidden" in sample
                )
                return {
                    "html": html,
                    "text": body_text,
                    "title": title,
                    "final_url": final_url,
                    "blocked": blocked,
                    "browserless": True,
                    "proxy": proxy,
                    "proxy_country": country,
                }
            except PlaywrightTimeoutError as exc:
                return {"error": f"Timeout do Browserless: {exc}", "final_url": url, "browserless": True}
            except Exception as exc:
                return {"error": f"Falha no Browserless: {exc}", "final_url": url, "browserless": True}
            finally:
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass

    def fetch(self, url: str):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1365, "height": 900},
                color_scheme="light",
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
                page.wait_for_timeout(2500)
                final_url = page.url
                title = page.title()
                html = page.content()
                body_text = page.locator("body").inner_text(timeout=5000)
                sample = f"{title}\n{body_text[:5000]}".casefold()
                blocked = (
                    "account-verification" in final_url.lower()
                    or "az-request-verify" in final_url.lower()
                    or "acessou nosso site de uma forma um pouco diferente do comum" in sample
                    or "para sua segurança precisamos de uma verificação rápida" in sample
                    or "para sua seguranca precisamos de uma verificacao rapida" in sample
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
