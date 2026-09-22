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
    """Cliente HTTP do backend real do CriaByte.

    As rotas de leitura continuam servindo ao planejador da v14. As rotas de
    escrita abaixo são usadas apenas por fluxos administrativos explícitos,
    como a extensão de importação de ofertas. A autenticação do backend atual
    é feita por cookie de sessão, então aceitamos um token de sessão já emitido
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
        api_base = (
            base_url
            or os.getenv("CRIABYTE_API_URL")
            or "https://api.criabyte.com.br"
        ).rstrip("/")
        if not api_base.endswith("/api"):
            api_base = f"{api_base}/api"
        self.base_url = f"{api_base}/"
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

    def importar_oferta_extensao(self, dados, api_key=None):
        key = (api_key or os.getenv("PRODUTO_IA_API_KEY") or "").strip()
        if not key:
            raise CriaByteApiError("PRODUTO_IA_API_KEY não configurada para a integração interna.")
        return self._request(
            "POST",
            "/interno/produto-ia/extensao/importar-oferta",
            json=dados,
            headers={"X-API-Key": key},
        )

    def cadastrar_hardware_descoberto(self, payload, id_temporario=None):
        self.ensure_authenticated()
        body = {"payload": payload}
        if id_temporario:
            body["idTemporario"] = id_temporario
        return self._request("POST", "/admin/hardwares/descobrir/cadastrar", json=body)

    def criar_produto_de_hardware(self, hardware_id, dados=None):
        self.ensure_authenticated()
        return self._request(
            "POST",
            f"/admin/produtos/de-hardware/{int(hardware_id)}",
            json=dados or {},
        )

    def criar_oferta(self, dados):
        self.ensure_authenticated()
        return self._request("POST", "/admin/ofertas", json=dados)

    def atualizar_oferta(self, oferta_id, dados):
        self.ensure_authenticated()
        return self._request("PATCH", f"/admin/ofertas/{int(oferta_id)}", json=dados)

    def criar_parceiro(self, dados):
        self.ensure_authenticated()
        return self._request("POST", "/admin/ofertas/parceiros", json=dados)

    def snapshot(self):
        self.ensure_authenticated()
        return {
            "hardwares": self.listar_hardwares(),
            "produtos": self.listar_produtos(),
            "ofertas": self.listar_ofertas(),
            "parceiros": self.listar_parceiros(),
            "categorias": self.listar_categorias(),
        }
