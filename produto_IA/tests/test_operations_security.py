import hashlib
import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from src.app import app
from src import operations
from src.security import validate_service_key, extension_owner


@pytest.fixture
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv('PRODUTO_IA_STATE_DB', str(tmp_path/'state.db'))
    monkeypatch.setenv('PRODUTO_IA_API_KEY', 'service-secret')
    monkeypatch.setenv('PRODUTO_IA_EXTENSION_KEYS', json.dumps({'desktop': 'sha256:'+hashlib.sha256(b'device-key').hexdigest()}))
    monkeypatch.setattr(operations, 'schedule', lambda _: None)
    return TestClient(app)


def test_service_fails_closed_and_extension_is_scoped(monkeypatch):
    monkeypatch.delenv('PRODUTO_IA_API_KEY', raising=False)
    with pytest.raises(HTTPException) as error:
        validate_service_key(None)
    assert error.value.status_code == 503
    monkeypatch.setenv('PRODUTO_IA_API_KEY', 'service-secret')
    with pytest.raises(HTTPException):
        validate_service_key('wrong')
    validate_service_key('service-secret')
    monkeypatch.setenv('PRODUTO_IA_EXTENSION_KEYS', json.dumps({'pc': 'sha256:'+hashlib.sha256(b'device-key').hexdigest()}))
    assert extension_owner('device-key')
    with pytest.raises(HTTPException):
        extension_owner('service-secret')


def create(client, key='unique-request-1', **overrides):
    body={'urlProduto':'https://www.amazon.com.br/dp/B012345678','urlAfiliada':'https://amzn.to/exemplo',**overrides}
    return client.post('/extensao/operacoes',headers={'X-API-Key':'device-key','Idempotency-Key':key},json=body)


def test_retry_keeps_same_operation_and_other_data_conflicts(environment):
    first=create(environment)
    assert first.status_code == 202, first.text
    second=create(environment)
    assert first.json()['id'] == second.json()['id']
    assert create(environment, precoManual=100).status_code == 409


def test_closed_window_can_retrieve_result_without_running_again(environment, monkeypatch):
    from src.extension import router_v2
    calls=[]
    monkeypatch.setattr(router_v2,'_import_v2_sync',lambda payload: calls.append(payload) or {'status':'BUILD_E_OFERTA_CRIADOS','produto':{'id':123}})
    identifier=create(environment).json()['id']
    operations._run(identifier)
    operations._run(identifier)
    response=environment.get('/extensao/operacoes/'+identifier,headers={'X-API-Key':'device-key'})
    assert response.json()['resultado']['produto']['id']==123
    assert len(calls)==1


def test_cancelled_queue_does_not_write_catalog(environment, monkeypatch):
    identifier=create(environment).json()['id']
    assert environment.post(f'/extensao/operacoes/{identifier}/cancelar',headers={'X-API-Key':'device-key'}).json()['estado']=='CANCELADA'
    from src.extension import router_v2
    monkeypatch.setattr(router_v2,'_import_v2_sync',lambda _: pytest.fail('Cancelamento não pode cadastrar'))
    operations._run(identifier)


def test_other_device_cannot_read_and_revoked_key_cannot_resume(environment, monkeypatch):
    identifier=create(environment).json()['id']
    monkeypatch.setenv('PRODUTO_IA_EXTENSION_KEYS', json.dumps({'other': 'sha256:'+hashlib.sha256(b'other-key').hexdigest()}))
    assert environment.get('/extensao/operacoes/'+identifier,headers={'X-API-Key':'other-key'}).status_code==404
    assert environment.get('/extensao/operacoes/'+identifier,headers={'X-API-Key':'device-key'}).status_code==401


def test_daily_limit_does_not_count_cached_response(environment,monkeypatch):
    from src.usage import reserve,finish,summary
    from src.technical_ai.providers import TechnicalAIResponse,TechnicalAIProviderError
    monkeypatch.setenv('PRODUTO_IA_MAX_DAILY_AI_CALLS','1')
    monkeypatch.setenv('AI_COST_USD_PER_MILLION',json.dumps({'OPENAI/test':{'input':1,'output':2}}))
    provider=type('Provider',(),{'name':'OPENAI','model':'test'})()
    identifier=reserve(provider)
    finish(identifier,TechnicalAIResponse('OPENAI','test','ok',[],{'usage':{'input_tokens':100,'output_tokens':50}}))
    with pytest.raises(TechnicalAIProviderError): reserve(provider)
    data=summary()['usoIA'][0]
    assert data['chamadas']==1
    assert data['custo']==pytest.approx(.0002)


def test_admin_issues_revocable_device_key_without_sharing_service_secret(environment,monkeypatch):
    monkeypatch.delenv('PRODUTO_IA_EXTENSION_KEYS',raising=False)
    assert extension_owner('service-secret')
    issued=environment.post('/admin/extensao/chaves',headers={'X-API-Key':'service-secret'},json={'nome':'Computador QA'}).json()
    assert issued['chave'].startswith('cbext_')
    assert extension_owner(issued['chave'])
    with pytest.raises(HTTPException): extension_owner('service-secret')
    assert environment.get('/admin/operacoes/resumo',headers={'X-API-Key':issued['chave']}).status_code==401
    listed=environment.get('/admin/extensao/chaves',headers={'X-API-Key':'service-secret'}).json()
    assert 'hash' not in listed[0] and 'chave' not in listed[0]
    environment.post('/admin/extensao/chaves/'+issued['id']+'/revogar',headers={'X-API-Key':'service-secret'})
    with pytest.raises(HTTPException): extension_owner(issued['chave'])
