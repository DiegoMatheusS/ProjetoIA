from http.server import BaseHTTPRequestHandler, HTTPServer
import html
import json
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv
from .mercadolivre_oauth import PROJECT_ROOT, PENDING_FILE, exchange_code, configured_redirect_uri

load_dotenv(PROJECT_ROOT / ".env")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, status, text):
        body = f"""<!doctype html><html><head><meta charset='utf-8'><title>Mercado Livre OAuth</title></head>
<body style='font-family:Arial,sans-serif;padding:40px'><h2>{html.escape(text)}</h2><p>Pode fechar esta aba.</p></body></html>""".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self._send(404, "Rota não encontrada")
            return
        query = parse_qs(parsed.query)
        code = (query.get("code") or [None])[0]
        state = (query.get("state") or [None])[0]
        if not code:
            self._send(400, "Código de autorização não recebido")
            return

        if PENDING_FILE.exists():
            try:
                pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
                expected = pending.get("state")
                if expected and state != expected:
                    self._send(400, "State inválido. Tente autorizar novamente.")
                    return
            except Exception:
                pass

        try:
            exchange_code(code, save=True)
            self._send(200, "Autorização concluída e token salvo no .env")
        except Exception as exc:
            self._send(500, f"Falha ao gerar token: {exc}")


def main():
    host = "0.0.0.0"
    port = 8765
    print("Callback OAuth aguardando na porta 8765")
    print("Redirect URI configurada:", configured_redirect_uri())
    print("No Codespaces, deixe a porta 8765 visível no navegador durante a autorização.")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
