"""Captura LOCAL da última resposta visível do Meta AI no WhatsApp Web.

Uso previsto:
1. Executar localmente no computador do admin.
2. Fazer login no WhatsApp Web quando necessário.
3. Abrir o chat do Meta AI e fazer a pergunta manualmente.
4. Quando a resposta terminar, voltar ao terminal e pressionar ENTER.
5. O script salva apenas o texto da última mensagem visível encontrada.

Não é executado na Railway e não salva cookies no JSON de saída.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


WHATSAPP_WEB_URL = "https://web.whatsapp.com/"


def _message_texts(page):
    selectors = (
        "#main .message-in [data-pre-plain-text]",
        "#main .message-in .copyable-text",
        "#main .message-in [dir='ltr']",
        "#main [data-testid='msg-container']",
        "#main [data-pre-plain-text]",
    )
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue
        if not count:
            continue
        values = []
        for idx in range(count):
            try:
                text = locator.nth(idx).inner_text(timeout=1500).strip()
            except Exception:
                continue
            if text:
                values.append(text)
        if values:
            return values
    return []


def capture(output: Path, profile_dir: Path, browser_name: str = "chrome") -> int:
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        launch_kwargs = {
            "headless": False,
            "user_data_dir": str(profile_dir),
            "locale": "pt-BR",
        }
        context = None
        if browser_name == "chrome":
            try:
                context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
            except Exception:
                context = None
        if context is None:
            context = p.chromium.launch_persistent_context(**launch_kwargs)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded", timeout=60000)
        print("WhatsApp Web aberto.", file=sys.stderr)
        print("Abra o chat do Meta AI, faça a pergunta e espere a resposta terminar.", file=sys.stderr)
        print("Depois volte ao terminal e pressione ENTER para capturar a última resposta visível.", file=sys.stderr)
        try:
            input()
        except EOFError:
            pass

        values = _message_texts(page)
        last_text = values[-1].strip() if values else ""
        payload = {
            "capture_version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source": "META_AI_WHATSAPP",
            "url": page.url,
            "response_text": last_text,
            "ok": bool(last_text),
            "error": None if last_text else "META_AI_WHATSAPP_RESPOSTA_NAO_ENCONTRADA",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        context.close()

    print(f"Captura salva em: {output}")
    if not last_text:
        print("Não foi possível localizar uma mensagem visível. Tente novamente com o chat do Meta AI aberto.", file=sys.stderr)
        return 2
    print("Resposta capturada com sucesso.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Captura a última resposta visível do Meta AI no WhatsApp Web")
    parser.add_argument("--output", default="meta_ai_whatsapp_capture.json")
    parser.add_argument("--profile", default="~/.criabyte_meta_ai_whatsapp_profile")
    parser.add_argument("--browser", choices=("chrome", "chromium"), default="chrome")
    args = parser.parse_args()
    raise SystemExit(capture(Path(args.output), Path(args.profile).expanduser(), args.browser))


if __name__ == "__main__":
    main()
