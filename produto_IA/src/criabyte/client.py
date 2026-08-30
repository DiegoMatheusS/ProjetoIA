import os
from urllib.parse import urljoin

import requests


class CriaByteApiError(RuntimeError):
    pass


def _extract_list(payload, *keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


class CriaByteClient:
    """Cliente de leitura do backend real do CriaByte.

    A v14 usa este cliente para CONSULTAR o banco e montar um plano. Nenhuma
    alteração é aplicada automaticamente. A autenticação do backend atual é
    feita por cookie de sessão, então aceitamos um token de sessão já emitido
    ou login administrativo por e-mail/senha via variáveis de ambiente.
    """

    def __init__(
        self,
        base_url=None,
        session=None,
        session_token=None,
        cookie_name=None,
        timeout=None,
    ):
        self.base_url = (base_url or os.getenv("CRIABYTE_API_URL") or "https://api.criabyte.com.br").rstrip("/") + "/"
        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CriaByte-Produto-IA/14",
        })
        self.timeout = int(timeout or os.getenv("CRIABYTE_API_TIMEOUT", "20"))
        self.cookie_name = cookie_name or os.getenv("CRIABYTE_SESSION_COOKIE_NAME", "pcbuilder_session")
        token = session_token or os.getenv("CRIABYTE_SESSION_TOKEN")
        if token:
            self.session.cookies.set(self.cookie_name, token)

    def _url(self, path):
        return urljoin(self.base_url, str(path).lstrip("/"))

    def _request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise CriaByteApiError(f"Falha ao acessar o CriaByte: {exc}") from exc

        if response.status_code >= 400:
            detail = None
            try:
                data = response.json()
                detail = data.get("message") if isinstance(data, dict) else data
            except ValueError:
                detail = response.text[:500]
            raise CriaByteApiError(f"CriaByte HTTP {response.status_code}: {detail or 'erro sem detalhe'}")

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise CriaByteApiError("O CriaByte retornou uma resposta que não é JSON.") from exc

    def login(self, email=None, senha=None):
        email = email or os.getenv("CRIABYTE_ADMIN_EMAIL")
        senha = senha or os.getenv("CRIABYTE_ADMIN_PASSWORD")
        if not email or not senha:
            raise CriaByteApiError(
                "Sessão não configurada. Informe CRIABYTE_SESSION_TOKEN ou CRIABYTE_ADMIN_EMAIL/CRIABYTE_ADMIN_PASSWORD."
            )
        return self._request("POST", "/auth/login", json={"email": email, "senha": senha})

    def ensure_authenticated(self):
        if self.session.cookies.get(self.cookie_name):
            return
        self.login()

    def listar_hardwares(self):
        return _extract_list(self._request("GET", "/admin/hardwares"), "hardwares", "items")

    def buscar_hardware(self, hardware_id):
        return self._request("GET", f"/admin/hardwares/{int(hardware_id)}")

    def listar_produtos(self):
        return _extract_list(self._request("GET", "/admin/produtos"), "produtos", "items")

    def buscar_produto(self, produto_id):
        return self._request("GET", f"/admin/produtos/{int(produto_id)}")

    def listar_ofertas(self):
        return _extract_list(self._request("GET", "/admin/ofertas"), "ofertas", "items")

    def listar_parceiros(self):
        return _extract_list(self._request("GET", "/admin/ofertas/parceiros"), "parceiros", "items")

    def listar_categorias(self):
        return _extract_list(self._request("GET", "/admin/categorias-produto"), "categorias", "items")

    def snapshot(self):
        self.ensure_authenticated()
        return {
            "hardwares": self.listar_hardwares(),
            "produtos": self.listar_produtos(),
            "ofertas": self.listar_ofertas(),
            "parceiros": self.listar_parceiros(),
            "categorias": self.listar_categorias(),
        }
