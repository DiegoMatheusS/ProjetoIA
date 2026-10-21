"""Fila durável de importação. A janela do Chrome não é dona da requisição."""
from contextlib import contextmanager
import contextvars
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Header, HTTPException
from .security import extension_owner, validate_service_key

router = APIRouter(tags=['Operações da extensão'])
_current = contextvars.ContextVar('import_operation', default=None)
_pool = ThreadPoolExecutor(max_workers=max(1, min(4, int(os.getenv('PRODUTO_IA_IMPORT_CONCURRENCY', '1')))))
_scheduled = set()
_lock = threading.Lock()
TERMINAL = {'CONCLUIDA', 'FALHOU', 'CANCELADA', 'INTERROMPIDA'}


def _open_database():
    path = Path(os.getenv('PRODUTO_IA_STATE_DB', '.data/operations.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS extension_keys (id TEXT PRIMARY KEY, label TEXT NOT NULL, hash TEXT UNIQUE NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, active INTEGER DEFAULT 1)')
    db.execute('''CREATE TABLE IF NOT EXISTS operations (
      id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL,
      fingerprint TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
      stage TEXT NOT NULL, result TEXT, error TEXT, cancel INTEGER DEFAULT 0,
      created REAL NOT NULL, updated REAL NOT NULL, duration_ms INTEGER DEFAULT 0,
      UNIQUE(owner, request_key))''')
    return db


@contextmanager
def connection():
    db = _open_database()
    try:
        with db:
            yield db
    finally:
        db.close()


def public(row):
    payload = json.loads(row['payload'])
    return { 'id': row['id'], 'estado': row['state'], 'etapa': row['stage'],
             'envio': {key: payload.get(key) for key in ('urlProduto', 'urlAfiliada')},
             'resultado': json.loads(row['result']) if row['result'] else None,
             'erro': row['error'], 'criadaEm': row['created'], 'atualizadaEm': row['updated'],
             'duracaoMs': row['duration_ms'] }


def stage(name):
    operation = _current.get()
    if not operation:
        return
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT cancel FROM operations WHERE id=?', (operation,)).fetchone()
        if row and row['cancel']:
            raise InterruptedError('Operação cancelada antes de gravar o catálogo')
        db.execute('UPDATE operations SET stage=?, updated=? WHERE id=?', (name, time.time(), operation))


def _run(operation):
    started = time.monotonic()
    try:
        with connection() as db:
            claimed = db.execute("UPDATE operations SET state='PROCESSANDO', updated=? WHERE id=? AND state='NA_FILA' AND cancel=0", (time.time(), operation))
            if not claimed.rowcount:
                return
            row = db.execute('SELECT * FROM operations WHERE id=?', (operation,)).fetchone()
        token = _current.set(operation)
        try:
            from .extension.router_v2 import ImportAffiliateOfferV2Request, _import_v2_sync
            result = _import_v2_sync(ImportAffiliateOfferV2Request(**json.loads(row['payload'])))
        finally:
            _current.reset(token)
        state, error = 'CONCLUIDA', None
    except InterruptedError as exc:
        result, state, error = None, 'CANCELADA', str(exc)
    except Exception as exc:
        # Mensagens de fornecedor podem conter URLs/credenciais. O histórico
        # guarda somente a mensagem pública do contrato HTTP, nunca traceback.
        detail = getattr(exc, 'detail', None)
        error = detail if isinstance(detail, (str, dict)) else 'Falha na importação. Revise os dados e tente novamente.'
        if type(exc).__name__ == 'MissingPriceError':
            result, state, error = {'status': 'PRECO_NAO_IDENTIFICADO', 'motivo': str(exc)}, 'CONCLUIDA', None
        else:
            result, state = None, 'FALHOU'
        error = json.dumps(error, ensure_ascii=False) if isinstance(error, dict) else error
    finally:
        with _lock:
            _scheduled.discard(operation)
    with connection() as db:
        db.execute('UPDATE operations SET state=?, stage=?, result=?, error=?, duration_ms=?, updated=? WHERE id=?',
                   (state, state, json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error, int((time.monotonic()-started)*1000), time.time(), operation))


def schedule(operation):
    with _lock:
        if operation in _scheduled:
            return
        _scheduled.add(operation)
    _pool.submit(_run, operation)


def recover_operations():
    with connection() as db:
        # Uma gravação pode ter chegado ao backend antes da reinicialização.
        # Exige revisão em vez de repetir uma mutação de resultado desconhecido.
        db.execute("UPDATE operations SET state='INTERROMPIDA', stage='INTERROMPIDA', error='Serviço reiniciado. Confira o catálogo antes de reenviar.' WHERE state='PROCESSANDO'")
        queued = db.execute("SELECT id FROM operations WHERE state='NA_FILA'").fetchall()
    for row in queued:
        schedule(row['id'])


@router.post('/extensao/operacoes', status_code=202)
def create_operation(payload: dict, x_api_key: str | None = Header(None), idempotency_key: str | None = Header(None)):
    owner = extension_owner(x_api_key)
    from .extension.router_v2 import ImportAffiliateOfferV2Request
    try:
        body = ImportAffiliateOfferV2Request(**payload).model_dump()
    except ValueError:
        raise HTTPException(422, 'Dados de importação inválidos')
    if not idempotency_key or not 8 <= len(idempotency_key) <= 120:
        raise HTTPException(400, 'Identificador de operação inválido')
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM operations WHERE owner=? AND request_key=?', (owner, idempotency_key)).fetchone()
        if row and row['fingerprint'] != fingerprint:
            raise HTTPException(409, 'Este identificador pertence a outros dados')
        if not row:
            active = db.execute("SELECT COUNT(*) FROM operations WHERE owner=? AND state IN ('NA_FILA','PROCESSANDO')", (owner,)).fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM operations WHERE state IN ('NA_FILA','PROCESSANDO')").fetchone()[0]
            if active >= 3 or total >= 100:
                raise HTTPException(429, 'Fila cheia. Aguarde uma operação terminar')
            operation = str(uuid.uuid4())
            now = time.time()
            db.execute('INSERT INTO operations (id,owner,request_key,fingerprint,payload,state,stage,created,updated) VALUES (?,?,?,?,?,?,?,?,?)',
                       (operation, owner, idempotency_key, fingerprint, encoded, 'NA_FILA', 'AGUARDANDO', now, now))
            row = db.execute('SELECT * FROM operations WHERE id=?', (operation,)).fetchone()
    schedule(row['id'])
    return public(row)


@router.get('/extensao/operacoes')
def list_operations(x_api_key: str | None = Header(None)):
    owner = extension_owner(x_api_key)
    with connection() as db:
        return [public(row) for row in db.execute('SELECT * FROM operations WHERE owner=? ORDER BY created DESC LIMIT 50', (owner,))]


def owned(operation, owner):
    with connection() as db:
        row = db.execute('SELECT * FROM operations WHERE id=? AND owner=?', (operation, owner)).fetchone()
    if not row:
        raise HTTPException(404, 'Operação não encontrada')
    return row


@router.get('/extensao/operacoes/{operation}')
def read_operation(operation: str, x_api_key: str | None = Header(None)):
    return public(owned(operation, extension_owner(x_api_key)))


@router.post('/extensao/operacoes/{operation}/cancelar')
def cancel_operation(operation: str, x_api_key: str | None = Header(None)):
    owner = extension_owner(x_api_key)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM operations WHERE id=? AND owner=?', (operation, owner)).fetchone()
        if not row:
            raise HTTPException(404, 'Operação não encontrada')
        if row['state'] not in TERMINAL:
            if row['stage'] == 'SALVANDO':
                raise HTTPException(409, 'Gravação em andamento. Aguarde a confirmação para evitar resultado indefinido')
            db.execute("UPDATE operations SET cancel=1, state=CASE WHEN state='NA_FILA' THEN 'CANCELADA' ELSE state END, updated=? WHERE id=?", (time.time(), operation))

    return public(owned(operation, owner))


@router.get('/admin/operacoes/resumo')
def metrics(x_api_key: str | None = Header(None)):
    validate_service_key(x_api_key)
    with connection() as db:
        rows = db.execute('SELECT state, COUNT(*) AS total, AVG(duration_ms) AS media FROM operations GROUP BY state').fetchall()
    from .usage import summary
    return {**summary(), 'operacoes': [{'estado': row['state'], 'total': row['total'], 'duracaoMediaMs': round(row['media'])} for row in rows]}


@router.get('/admin/extensao/chaves')
def list_keys(x_api_key: str | None = Header(None)):
    validate_service_key(x_api_key)
    with connection() as db:
        return [dict(row) for row in db.execute('SELECT id,label,created,expires,active FROM extension_keys ORDER BY created DESC')]


@router.post('/admin/extensao/chaves')
def issue_key(payload: dict, x_api_key: str | None = Header(None)):
    import secrets
    validate_service_key(x_api_key)
    label = str(payload.get('nome') or '').strip()
    if not 2 <= len(label) <= 80:
        raise HTTPException(422, 'Informe um nome para o dispositivo')
    token, identifier, now = 'cbext_'+secrets.token_urlsafe(32), str(uuid.uuid4()), time.time()
    with connection() as db:
        db.execute('INSERT INTO extension_keys(id,label,hash,created,expires) VALUES (?,?,?,?,?)',
                   (identifier,label,hashlib.sha256(token.encode()).hexdigest(),now,now+365*86400))
    return {'id':identifier,'nome':label,'chave':token,'expiraEm':now+365*86400}


@router.post('/admin/extensao/chaves/{identifier}/revogar')
def revoke_key(identifier: str, x_api_key: str | None = Header(None)):
    validate_service_key(x_api_key)
    with connection() as db:
        db.execute('UPDATE extension_keys SET active=0 WHERE id=?',(identifier,))
    return {'revogada':True}
