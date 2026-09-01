import csv
import json
from pathlib import Path

from ..scrapers.magazine_scraper import MagazineScraper
from ..scrapers.mercadolivre_scraper import MercadoLivreScraper
from ..scrapers.generic_scraper import GenericScraper


def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(".", "").replace(",", ".")) if isinstance(value, str) and "," in value else float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().casefold()
    if token in {"true", "1", "sim", "s", "yes", "disponivel", "disponível"}:
        return True
    if token in {"false", "0", "nao", "não", "n", "no", "indisponivel", "indisponível", "esgotado"}:
        return False
    return None


def normalize_batch_item(item, index=0):
    if isinstance(item, str):
        item = {"url": item}
    # Para o CriaByte, a URL original é a referência comercial primária.
    # A afiliada continua como fallback, nunca como requisito para entrar no lote.
    url_original = item.get("urlOriginal") or item.get("url") or item.get("link")
    url_afiliada = item.get("urlAfiliada") or item.get("urlAfiliado")
    url = url_original or url_afiliada
    status_atual = item.get("statusAtual") or item.get("status")
    disponivel_atual = _bool_or_none(item.get("disponivelAtual") if "disponivelAtual" in item else item.get("disponivel"))
    if disponivel_atual is None and status_atual in {"ATIVA", "INDISPONIVEL"}:
        disponivel_atual = status_atual == "ATIVA"
    return {
        "id": item.get("id") or item.get("ofertaId") or item.get("produtoId") or index + 1,
        "produtoId": item.get("produtoId"),
        "ofertaId": item.get("ofertaId") or item.get("id"),
        "nome": item.get("nome") or item.get("produto"),
        "url": url,
        "urlOriginal": url_original,
        "urlAfiliada": url_afiliada,
        "precoAtual": _float_or_none(item.get("precoAtual") if "precoAtual" in item else item.get("preco")),
        "disponivelAtual": disponivel_atual,
        "statusAtual": status_atual,
    }


def load_batch_items(path):
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("ofertas") or data.get("itens") or data.get("items") or []
        if not isinstance(data, list):
            raise ValueError("JSON de lote deve conter uma lista ou a chave 'ofertas'.")
        return [normalize_batch_item(item, idx) for idx, item in enumerate(data)]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return [normalize_batch_item(row, idx) for idx, row in enumerate(rows)]

    # TXT: uma URL por linha.
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [normalize_batch_item(line, idx) for idx, line in enumerate(lines) if line and not line.startswith("#")]


class BatchPriceUpdater:
    """Verifica preço/disponibilidade de várias ofertas, UMA URL por vez.

    Não altera especificações técnicas e não executa requisições em paralelo.
    Isso permite o CriaByte usar este módulo no botão Recalcular preços sem
    transformar o recurso em crawler massivo.
    """

    def __init__(self, collector=None, price_tolerance=0.009):
        self.collector = collector or self._collect_offer
        self.price_tolerance = float(price_tolerance)

    @staticmethod
    def _collect_offer(url, no_browser=False):
        if MercadoLivreScraper.is_mercadolivre(url):
            raw = MercadoLivreScraper().collect(url, no_browser=no_browser)
        elif MagazineScraper.is_magazine(url):
            raw = MagazineScraper().collect(url, no_browser=no_browser)
        else:
            raw = GenericScraper().collect(url, no_browser=no_browser)
        return {
            "ok": bool(raw.get("ok") and not raw.get("error")),
            "preco": raw.get("price"),
            "precoAnterior": raw.get("previous_price"),
            "disponivel": raw.get("available"),
            "urlFinal": raw.get("url_final") or url,
            "fonte": raw.get("source"),
            "erro": raw.get("error"),
        }

    def _price_changed(self, old, new):
        if new is None:
            return False
        if old is None:
            return True
        return abs(float(old) - float(new)) > self.price_tolerance

    def check_item(self, item, no_browser=False):
        item = normalize_batch_item(item)
        url = item.get("url")
        base = dict(item)
        if not url:
            return {**base, "status": "ERRO", "erro": "URL_AUSENTE", "atualizacao": None}

        try:
            found = self.collector(url, no_browser=no_browser)
        except TypeError:
            # Facilita injeção de collector simples em integrações/testes.
            found = self.collector(url)
        except Exception as exc:
            return {**base, "status": "ERRO", "erro": f"ERRO_COLETA: {exc}", "atualizacao": None}

        if not found or not found.get("ok"):
            return {
                **base,
                "status": "ERRO",
                "erro": (found or {}).get("erro") or "NAO_FOI_POSSIVEL_VERIFICAR",
                "fonte": (found or {}).get("fonte"),
                "atualizacao": None,
            }

        new_price = _float_or_none(found.get("preco"))
        new_available = _bool_or_none(found.get("disponivel"))
        price_changed = self._price_changed(item.get("precoAtual"), new_price)
        availability_changed = (
            new_available is not None
            and item.get("disponivelAtual") is not None
            and new_available != item.get("disponivelAtual")
        )
        # Se o cadastro ainda não tem disponibilidade, podemos preencher quando a fonte sabe.
        if item.get("disponivelAtual") is None and new_available is not None:
            availability_changed = True

        update = None
        status = "SEM_ALTERACAO"
        if price_changed or availability_changed:
            status = "ATUALIZAR"
            desired_available = new_available if availability_changed else item.get("disponivelAtual")
            backend_payload = {}
            if price_changed and new_price is not None:
                # O AtualizarOfertaDto já coloca o preço salvo anterior em precoAnterior.
                backend_payload["preco"] = new_price
            if availability_changed and desired_available is not None:
                backend_payload["status"] = "ATIVA" if desired_available else "INDISPONIVEL"
            update = {
                "produtoId": item.get("produtoId"),
                "ofertaId": item.get("ofertaId"),
                "preco": new_price if price_changed else item.get("precoAtual"),
                "disponivel": desired_available,
                "statusOferta": "ATIVA" if desired_available is True else ("INDISPONIVEL" if desired_available is False else item.get("statusAtual")),
                "alterarPreco": price_changed,
                "alterarDisponibilidade": availability_changed,
                "url": url,
                "rotaBackend": f"/admin/ofertas/{item.get('ofertaId')}" if item.get("ofertaId") is not None else None,
                "metodoBackend": "PATCH" if item.get("ofertaId") is not None else None,
                "payloadBackend": backend_payload,
            }

        return {
            **base,
            "status": status,
            "erro": None,
            "precoEncontrado": new_price,
            "precoAnteriorEncontrado": _float_or_none(found.get("precoAnterior")),
            "disponivelEncontrado": new_available,
            "urlFinal": found.get("urlFinal"),
            "fonte": found.get("fonte"),
            "atualizacao": update,
        }

    def check_many(self, items, no_browser=False):
        results = []
        for idx, item in enumerate(items):
            normalized = normalize_batch_item(item, idx)
            results.append(self.check_item(normalized, no_browser=no_browser))

        updates = [row["atualizacao"] for row in results if row.get("status") == "ATUALIZAR" and row.get("atualizacao")]
        errors = [row for row in results if row.get("status") == "ERRO"]
        unchanged = [row for row in results if row.get("status") == "SEM_ALTERACAO"]
        return {
            "modo": "RECALCULAR_PRECOS_LOTE",
            "politica": {
                "processamentoSequencial": True,
                "umaUrlPorVez": True,
                "alteraSomenteOferta": True,
                "alteraFichaTecnica": False,
                "urlOriginalTemPrioridade": True,
                "urlAfiliadaEhFallback": True,
                "payloadCompatívelComAtualizarOfertaDto": True,
            },
            "resumo": {
                "total": len(results),
                "atualizar": len(updates),
                "semAlteracao": len(unchanged),
                "erros": len(errors),
            },
            "atualizacoes": updates,
            "itens": results,
        }
