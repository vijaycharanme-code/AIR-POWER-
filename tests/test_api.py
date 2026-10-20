import copy
import json
import uuid
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,insert
from openapi_spec_validator import validate
from backend.api import create_app
from backend import db
from backend.service import ROOT

P='/api/v1'
def post(c,path,body,key=None,version=None,**kwargs):
    headers={'Idempotency-Key':key or str(uuid.uuid4())}
    if version is not None:headers['If-Match']=str(version)
    headers.update(kwargs.pop('headers',{}))
    return c.post(P+path,json=body,headers=headers,**kwargs)
def seed(c):
    r=post(c,'/import-runs',{'fixture':'development-v1'})
    assert r.status_code==200,r.text
    return r.json()
def card(c):return c.get(P+'/cases/DEV-VALID-001').json()
def evalcase(c,key=None):
    v=card(c)['version']
    r=post(c,'/cases/DEV-VALID-001/evaluations',{},key,v)
    assert r.status_code==200,r.text
    return r

def test_all_canonical_routes(client):
    for route in ('/live','/ready','/session','/demo/metadata'):
        assert client.get(P+route).status_code==200
    r=seed(client)
    assert client.get(P+'/import-runs/'+r['run_id']).json()==r
    assert client.get(P+'/cases').status_code==200
    assert card(client)['version']==1
    e=evalcase(client).json()
    assert e['gate_state']=='READY_FOR_HUMAN_REVIEW'
    assert all(e.get(k) for k in ('evidence_references','config_fingerprint','decision_time','input_snapshot','reason_codes'))
    d=post(client,'/cases/DEV-VALID-001/dispositions',{'disposition':'DEFER','note':'Await review'},version=2)
    assert d.status_code==200,d.text
    history=client.get(P+'/cases/DEV-VALID-001/events').json()
    assert history['history_complete'] and history['replay'][0]['matches']
    assert len(history['versions'])==3
    for kind in ('evaluation','rul','simulation'):
        body={'suite':'frozen-v1'} if kind=='evaluation' else {}
        r=post(client,'/'+kind+'-runs',body)
        assert r.status_code==200,r.text
        result=r.json()
        assert client.get(P+'/'+kind+'-runs/'+result['run_id']).json()==result
        if kind=='evaluation':
            assert result['result']['passed']==result['result']['total']==280
            a=client.get(P+'/artifacts/'+result['result']['artifact_id'])
            assert a.status_code==200 and a.json()['passed']==280
        else: assert result['status']=='BLOCKED'

@pytest.mark.parametrize('route', ['/cases/missing','/cases/missing/events','/import-runs/missing','/evaluation-runs/missing','/rul-runs/missing','/simulation-runs/missing','/artifacts/missing','/health','/imports','/evaluate'])
def test_missing_and_no_alias(client,route):
    r=client.get(P+route);assert r.status_code==404 and 'error' in r.json()
@pytest.mark.parametrize('query',['limit=0','limit=51','limit=x','gate_state=READY','freshness_state=oops','cursor=bad'])
def test_invalid_filters(client,query):
    assert client.get(P+'/cases?'+query).status_code==422

def test_idempotency_and_versions(client):
    seed(client);key='same-key';r=evalcase(client,key)
    replay=post(client,'/cases/DEV-VALID-001/evaluations',{},key,1)
    assert replay.json()==r.json()
    assert post(client,'/cases/DEV-VALID-001/evaluations',{},key,2).status_code==409
    assert post(client,'/cases/DEV-VALID-001/evaluations',{},version=1).status_code==409
    assert client.post(P+'/import-runs',json={'fixture':'development-v1'}).status_code==422
    assert post(client,'/cases/DEV-VALID-001/evaluations',{}).status_code==422
    assert post(client,'/cases/DEV-VALID-001/dispositions',{'disposition':'APPROVE'},version=2).status_code==422

def test_duplicate_import_same_key(client):
    a=post(client,'/import-runs',{'fixture':'development-v1'},'import-once')
    b=post(client,'/import-runs',{'fixture':'development-v1'},'import-once')
    assert a.json()==b.json() and card(client)['version']==1
    assert post(client,'/import-runs',{'fixture':'holdout-v1'},'import-once').status_code==409

def test_changed_evidence_invalidates_ready(client):
    seed(client);evalcase(client)
    b=client.app.state.service.fixture('development-v1')['bundles'][0]
    b['records'][2]['quantity']=0
    b['records'][2]['record_version']=2
    assert post(client,'/import-runs',{'bundles':[b]}).status_code==200
    assert card(client)['gate_state'] is None
    assert evalcase(client).json()['gate_state']=='BLOCK'

def test_persistence_failure_rollback(client):
    seed(client);svc=client.app.state.service
    svc.fail_before_commit=True
    r=post(client,'/cases/DEV-VALID-001/evaluations',{},'recover',1)
    assert r.status_code==500 and 'gate_state' not in r.text
    assert card(client)['version']==1 and card(client)['latest_evaluation'] is None
    svc.fail_before_commit=False
    assert post(client,'/cases/DEV-VALID-001/evaluations',{},'recover',1).status_code==200

def test_parallel_dispositions(client):
    seed(client);evalcase(client)
    def write(i):return post(client,'/cases/DEV-VALID-001/dispositions',{'disposition':'DEFER','note':str(i)},version=2).status_code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(write,range(2)))
    assert sorted(results)==[200,409]
    assert len(client.get(P+'/cases/DEV-VALID-001/events').json()['events'])==3

def test_rbac_audit(client,tmp_path):
    app=create_app(client.app.state.service.engine,tmp_path/'readonly','observer','analyst')
    with TestClient(app,raise_server_exceptions=False) as c:
        assert c.get(P+'/cases').status_code==200
        assert post(c,'/import-runs',{'fixture':'development-v1'}).status_code==403
    with client.app.state.service.engine.connect() as conn:
        assert any(r['outcome']=='DENIED' for r in conn.execute(select(db.audit.c.data)).scalars())

def test_origin_and_caps(client):
    assert post(client,'/import-runs',{'fixture':'development-v1'},headers={'Origin':'https://evil.example'}).status_code==403
    assert post(client,'/import-runs',{'fixture':'development-v1'},headers={'Origin':'http://testserver'}).status_code==200
    assert client.post(P+'/import-runs',content='x'*2_000_001).status_code==413
    assert post(client,'/import-runs',{'fixture':'../../secret'}).status_code==422
    assert post(client,'/import-runs',{'fixture':'development-v1','role':'planner'}).status_code==422
    assert client.get(P+'/live',headers={'host':'evil.example'}).status_code==403

def test_artifact_reconciliation(client):
    r=post(client,'/evaluation-runs',{'suite':'frozen-v1'}).json()
    aid=r['result']['artifact_id'];svc=client.app.state.service
    path=svc.artifact(aid);path.write_text('modified')
    assert client.get(P+'/artifacts/'+aid).status_code==409
    path.unlink()
    assert client.get(P+'/artifacts/'+aid).status_code==409
    try:
        path.symlink_to(ROOT/'requirements.txt')
    except OSError:return
    assert client.get(P+'/artifacts/'+aid).status_code==409

def test_no_evaluation_disposition(client):
    seed(client)
    assert post(client,'/cases/DEV-VALID-001/dispositions',{'disposition':'DEFER'},version=1).status_code==409

def test_cursor_and_filters(client):
    seed(client)
    p=client.get(P+'/cases?limit=1').json();assert p['next_cursor']
    q=client.get(P+'/cases',params={'limit':1,'cursor':p['next_cursor']}).json()
    assert p['items'][0]['case_id']!=q['items'][0]['case_id']
    assert client.get(P+'/cases',params={'cursor':p['next_cursor'],'asset_id':'AP-100'}).status_code==409
    evalcase(client)
    assert client.get(P+'/cases',params={'cursor':p['next_cursor']}).status_code==409
    assert client.get(P+'/cases?gate_state=READY_FOR_HUMAN_REVIEW').json()['items'][0]['gate_state']=='READY_FOR_HUMAN_REVIEW'

def test_import_reject_naive_times(client):
    b=client.app.state.service.fixture('development-v1')['bundles'][0]
    b['records'][0]['event_time']='2026-10-19T12:00:00'
    assert post(client,'/import-runs',{'bundles':[b]}).status_code==200
    e=evalcase(client).json()
    assert e['gate_state']=='HOLD'
    assert e['input_snapshot']['validation'][0]['state']=='QUARANTINED'

def test_gemini_no_key(client,monkeypatch):
    seed(client);evalcase(client);monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    r=post(client,'/cases/DEV-VALID-001/explanations',{},version=2)
    assert r.status_code==503 and r.json()['error']['code']=='GEMINI_NOT_CONFIGURED'
    assert card(client)['version']==2

@pytest.mark.parametrize('mode,expected', [('success',200),('quota',502),('empty',502),('timeout',504),('malformed',502)])
def test_gemini_adapter_contract(client,monkeypatch,mode,expected):
    seed(client);evalcase(client);monkeypatch.setenv('GEMINI_API_KEY','test-placeholder-not-a-real-key')
    class FakeClient:
        def __init__(self,**kw):assert kw['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,headers,json):
            assert url.startswith('https://generativelanguage.googleapis.com/v1beta/models/gemini-')
            assert headers['x-goog-api-key']=='test-placeholder-not-a-real-key'
            assert 'input_snapshot' in json['contents'][0]['parts'][0]['text']
            if mode=='timeout':raise httpx.ReadTimeout('timed out')
            if mode=='quota':return httpx.Response(429,json={'error':'quota'})
            if mode=='malformed':return httpx.Response(200,content='invalid json')
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'Advisory explanation.'}]}}]} if mode=='success' else {})
    monkeypatch.setattr('backend.gemini.httpx.Client',FakeClient)
    r=post(client,'/cases/DEV-VALID-001/explanations',{},'gemini-test',2)
    assert r.status_code==expected,r.text
    if mode=='success':
        assert r.json()['gate_unchanged']
        assert post(client,'/cases/DEV-VALID-001/explanations',{},'gemini-test',2).json()==r.json()
    assert card(client)['version']==2
    assert 'test-placeholder' not in r.text

def test_openapi_valid(client):
    schema=client.get(P+'/openapi.json').json();validate(schema)
    committed=json.loads((ROOT/'docs'/'openapi.json').read_text())
    assert schema==committed

def test_startup_requires_principal(monkeypatch):
    monkeypatch.delenv('AIRPOWER_PRINCIPAL',raising=False);monkeypatch.delenv('AIRPOWER_ROLE',raising=False)
    monkeypatch.setattr('backend.api.load_dotenv',lambda *args:None)
    with pytest.raises(RuntimeError):create_app()

def test_disposition_failure_is_atomic(client):
    seed(client);evalcase(client);svc=client.app.state.service
    svc.fail_before_commit=True
    r=post(client,'/cases/DEV-VALID-001/dispositions',{'disposition':'DEFER'},'disposition-rollback',2)
    assert r.status_code==500
    svc.fail_before_commit=False
    assert card(client)['version']==2
    assert len(client.get(P+'/cases/DEV-VALID-001/events').json()['events'])==2
    assert post(client,'/cases/DEV-VALID-001/dispositions',{'disposition':'DEFER'},'disposition-rollback',2).status_code==200

def test_artifact_write_failure_is_error(client,monkeypatch):
    def failed(*args,**kwargs):raise OSError('Injected disk failure')
    monkeypatch.setattr(Path,'write_bytes',failed)
    r=post(client,'/evaluation-runs',{'suite':'frozen-v1'})
    assert r.status_code==500 and 'gate_state' not in r.text
    with client.app.state.service.engine.connect() as c:
        assert not c.execute(select(db.artifacts)).first()
        assert not c.execute(select(db.runs)).first()

@pytest.mark.parametrize('path',['/rul-runs','/simulation-runs'])
def test_stub_collection(client,path):
    assert client.get(P+path).json()=={'items':[]}
    run=post(client,path,{}).json()
    assert client.get(P+path).json()['items'][0]['run_id']==run['run_id']

@pytest.mark.parametrize('domain,field,value',[('health','value','78'),('spares','quantity','2'),('agency','approval','true')])
def test_no_silent_source_type_coercion(client,domain,field,value):
    b=client.app.state.service.fixture('development-v1')['bundles'][0]
    next(r for r in b['records'] if r['domain']==domain)[field]=value
    assert post(client,'/import-runs',{'bundles':[b]}).status_code==200
    assert evalcase(client).json()['gate_state']=='HOLD'
