import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def _access_error(title: str, text: str):
    sample = f"{title}\n{text[:5000]}".casefold()
    terms = (
        "não é possível acessar a página",
        "nao e possivel acessar a pagina",
        "não foi possível acessar a página",
        "this site can't be reached",
        "this site can’t be reached",
        "access denied",
        "403 forbidden",
        "err_connection_",
        "err_timed_out",
    )
    return any(term in sample for term in terms)


def capture(url: str, output: Path, auto=False, headless=False, browser_name="chrome"):
    with sync_playwright() as p:
        launch_kwargs = {"headless": headless}
        browser = None

        # No Windows local, usar o Chrome instalado tende a reproduzir melhor a
        # navegação normal do usuário. Se não estiver disponível, cai para o
        # Chromium instalado pelo Playwright.
        if browser_name == "chrome":
            try:
                browser = p.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                browser = None
        if browser is None:
            browser = p.chromium.launch(**launch_kwargs)

        context = browser.new_context(locale="pt-BR")
        page = context.new_page()
        payload = {
            "capture_version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "original_url": url,
            "final_url": url,
            "title": None,
            "html": "",
            "text": "",
            "blocked": False,
            "error": None,
        }

        try:
            print("Abrindo a página no navegador LOCAL...", file=sys.stderr)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)

            if not auto and not headless:
                print(
                    "Quando a página do produto estiver carregada, volte ao terminal e pressione ENTER.",
                    file=sys.stderr,
                )
                try:
                    input()
                except EOFError:
                    pass

            payload["final_url"] = page.url
            payload["title"] = page.title()
            payload["html"] = page.content()
            try:
                payload["text"] = page.locator("body").inner_text(timeout=8000)
            except Exception:
                payload["text"] = ""
            payload["blocked"] = _access_error(payload["title"] or "", payload["text"] or "")
            if payload["blocked"]:
                payload["error"] = "CAPTURA_LOCAL_SEM_ACESSO_A_PAGINA"
        except PlaywrightTimeoutError as exc:
            payload["final_url"] = page.url
            payload["error"] = f"CAPTURA_LOCAL_TIMEOUT: {exc}"
        except Exception as exc:
            payload["final_url"] = page.url
            payload["error"] = f"CAPTURA_LOCAL_ERRO: {exc}"
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            context.close()
            browser.close()

    print(f"Captura salva em: {output}")
    if payload.get("error"):
        print(f"Aviso: {payload['error']}", file=sys.stderr)
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Captura local de uma página de produto para o Produto IA do CriaByte"
    )
    parser.add_argument("url", help="URL do produto a abrir no navegador local")
    parser.add_argument(
        "--output",
        default="magalu_capture.json",
        help="Arquivo JSON de saída (padrão: magalu_capture.json)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Capturar automaticamente sem esperar ENTER",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executar sem janela. Para Magalu, prefira o navegador visível.",
    )
    parser.add_argument(
        "--browser",
        choices=("chrome", "chromium"),
        default="chrome",
        help="Chrome instalado ou Chromium do Playwright",
    )
    args = parser.parse_args()
    raise SystemExit(capture(args.url, Path(args.output), args.auto, args.headless, args.browser))


if __name__ == "__main__":
    main()
