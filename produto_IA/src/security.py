"""Autenticação obrigatória; chaves da extensão podem ser revogadas separadamente."""
import hashlib
import hmac
import json
import os
from fastapi import HTTPException


def validate_service_key(value):
    expected = os.getenv('PRODUTO_IA_API_KEY', '').strip()
    if not expected:
        raise HTTPException(503, 'Autenticação do serviço não configurada')
    if not value or not hmac.compare_digest(value, expected):
        raise HTTPException(401, 'API key inválida')


def extension_owner(value):
    # JSON {"nome-do-dispositivo": "sha256:hash-do-token"}. Nunca enviar a
    # chave interna do backend a um dispositivo novo.
    configured = os.getenv('PRODUTO_IA_EXTENSION_KEYS', '').strip()
    if configured:
        try:
            keys = json.loads(configured)
            if not isinstance(keys, dict) or not keys:
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(503, 'Chaves da extensão configuradas incorretamente')
        digest = hashlib.sha256((value or '').encode()).hexdigest()
        for name, expected in keys.items():
            if isinstance(expected, str) and expected.startswith('sha256:') and hmac.compare_digest(digest, expected[7:]):
                return hashlib.sha256(str(name).encode()).hexdigest()
    from .operations import connection
    import time
    digest = hashlib.sha256((value or '').encode()).hexdigest()
    with connection() as db:
        row = db.execute('SELECT id FROM extension_keys WHERE hash=? AND active=1 AND expires>?', (digest,time.time())).fetchone()
        count = db.execute('SELECT COUNT(*) FROM extension_keys').fetchone()[0]
    if row:
        return hashlib.sha256(row['id'].encode()).hexdigest()
    # Compatibilidade anterior termina assim que uma chave própria for emitida.
    if not configured and not count and os.getenv('PRODUTO_IA_ALLOW_LEGACY_EXTENSION_KEY', 'true').lower() == 'true':
        validate_service_key(value)
        return hashlib.sha256((value or '').encode()).hexdigest()
    raise HTTPException(401, 'Chave da extensão inválida, expirada ou revogada')
