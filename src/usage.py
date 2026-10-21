"""Métricas agregadas sem prompts, respostas ou credenciais."""
from contextlib import contextmanager
import json
import os
import time
import uuid
from .operations import connection


@contextmanager
def _db():
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS ai_usage (id TEXT PRIMARY KEY, provider TEXT, model TEXT, created REAL, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cost_usd REAL, state TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS research_metrics (created REAL, category TEXT, filled INTEGER, conflicts INTEGER, missing INTEGER, duration_ms INTEGER)')
        yield db


def reserve(provider):
    from .technical_ai.providers import TechnicalAIProviderError
    limit = max(0, int(os.getenv('PRODUTO_IA_MAX_DAILY_AI_CALLS', '0')))
    now = time.time()
    with _db() as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute('SELECT COUNT(*) FROM ai_usage WHERE created>=?', (int(now//86400)*86400,)).fetchone()[0]
        if limit and count >= limit:
            raise TechnicalAIProviderError('LIMITE_DIARIO_IA', 'Limite diário de chamadas de IA atingido', status_code=429)
        identifier = str(uuid.uuid4())
        db.execute('INSERT INTO ai_usage(id,provider,model,created,state) VALUES (?,?,?,?,?)', (identifier, getattr(provider,'name','EXTERNO'), getattr(provider,'model',''), now, 'INICIADA'))
    return identifier


def finish(identifier, response=None):
    metadata = getattr(response, 'raw_metadata', None) or {}
    usage = metadata.get('usage') or {}
    input_tokens = int(usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('output_tokens') or 0)
    with _db() as db:
        row = db.execute('SELECT provider,model FROM ai_usage WHERE id=?',(identifier,)).fetchone()
        cost = None
        try:
            # Preços são configuração operacional. Sem tabela, custo fica
            # desconhecido em vez de ser apresentado como zero.
            prices = json.loads(os.getenv('AI_COST_USD_PER_MILLION', '{}'))
            price = prices.get(f"{row['provider']}/{row['model']}")
            if price and usage:
                cost = (input_tokens*float(price['input'])+output_tokens*float(price['output']))/1000000
        except (ValueError, TypeError, KeyError):
            pass
        db.execute('UPDATE ai_usage SET state=?,input_tokens=?,output_tokens=?,cost_usd=? WHERE id=?', ('CONCLUIDA' if response else 'FALHOU',input_tokens,output_tokens,cost,identifier))


def research(category, info):
    agent = info.get('agentePesquisa') or {}
    with _db() as db:
        db.execute('INSERT INTO research_metrics VALUES (?,?,?,?,?,?)', (time.time(), category, len(info.get('camposPreenchidos') or []), len(info.get('conflitosNaoResolvidos') or info.get('conflitos') or []), len(agent.get('camposAusentesDepois') or []), int(agent.get('duracaoMs') or 0)))


def summary():
    with _db() as db:
        usage = db.execute('SELECT provider,model,COUNT(*) chamadas,SUM(input_tokens) entrada,SUM(output_tokens) saida,SUM(cost_usd) custo,SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) desconhecidos FROM ai_usage WHERE created>=? GROUP BY provider,model',(time.time()-30*86400,)).fetchall()
        quality = db.execute('SELECT category,COUNT(*) pesquisas,SUM(filled) preenchidos,SUM(conflicts) conflitos,AVG(duration_ms) duracao_media_ms FROM research_metrics WHERE created>=? GROUP BY category',(time.time()-30*86400,)).fetchall()
    return {'usoIA': [dict(row) for row in usage], 'qualidade': [dict(row) for row in quality], 'periodoDias':30}
