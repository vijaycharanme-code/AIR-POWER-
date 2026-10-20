import copy
import hashlib
import json
from datetime import timedelta
import pytest
from backend.domain import assemble,context,DecisionGate
from backend.service import ROOT,FIXTURE_TIME

PACKS=[json.loads((ROOT/'fixtures'/f'{name}.json').read_text()) for name in ('development-v1','holdout-v1')]
VECTORS=[(b,p['expected'][b['case_id']]) for p in PACKS for b in p['bundles']]
@pytest.mark.parametrize('bundle,expected',VECTORS,ids=[b['case_id'] for b,_ in VECTORS])
def test_frozen(bundle,expected):
    snap=assemble(bundle)
    assert DecisionGate.decide(context(snap,FIXTURE_TIME))[0]==expected

@pytest.mark.parametrize('filename,sha',[(m['filename'],m['sha256']) for m in json.loads((ROOT/'fixtures'/'manifest.json').read_text())])
def test_fixtures_locked(filename,sha):
    assert hashlib.sha256((ROOT/'fixtures'/filename).read_bytes()).hexdigest()==sha

def valid():return copy.deepcopy(PACKS[0]['bundles'][0])
@pytest.mark.parametrize('mode', ['missing_policy','unresolved','hard','stale_hard','unknown','rul','overlap','epoch_end','naive_time','future','untrusted','unknown_domain','pending_class','conflicting_health','alias','stale_ingest'])
def test_truth_table(mode):
    b=valid();expected='HOLD'
    if mode=='missing_policy': b['policy']=None;b['records'][2]['quantity']=0
    if mode=='unresolved': b['records'][1]['approved']=False;b['records'][2]['quantity']=0
    if mode=='hard': b['records'][2]['quantity']=0;expected='BLOCK'
    if mode=='stale_hard': b['records'][2]['quantity']=0;b['records'][2]['event_time']=(FIXTURE_TIME-timedelta(hours=72)).isoformat()
    if mode=='unknown':b['records'][3]['approval']=None
    if mode=='rul':b['policy']['rul_required']=True
    if mode=='overlap':
        other=copy.deepcopy(b['records'][1]);other['source_record_key']='overlap';b['records'].append(other)
    if mode=='epoch_end':b['records'][1]['valid_to']=b['records'][0]['event_time']
    if mode=='naive_time':b['records'][0]['event_time']='2026-10-19T11:00:00'
    if mode=='future':b['records'][0]['event_time']=(FIXTURE_TIME+timedelta(hours=1)).isoformat()
    if mode=='untrusted':b['records'][2]['trusted']=False;b['records'][2]['quantity']=0
    if mode=='unknown_domain':b['records'][0]['domain']='unsupported'
    if mode=='pending_class':b['records'][2]['evidence_class']='PENDING'
    if mode=='conflicting_health':
        other=copy.deepcopy(b['records'][0]);other['source_record_key']='health-2';b['records'].append(other)
    if mode=='alias':b['records'][0]['component_id']='ENGINE-PRIMARY';expected='READY_FOR_HUMAN_REVIEW'
    if mode=='stale_ingest':b['records'][2]['ingest_time']=(FIXTURE_TIME+timedelta(hours=10)).isoformat()
    assert DecisionGate.decide(context(assemble(b),FIXTURE_TIME))[0]==expected

def test_half_open_start():
    b=valid();b['records'][1]['valid_from']=b['records'][0]['event_time']
    assert assemble(b)['linkage']=='RESOLVED'

def test_deterministic_replay():
    snap=assemble(valid())
    assert DecisionGate.decide(context(snap,FIXTURE_TIME))==DecisionGate.decide(context(json.loads(json.dumps(snap)),FIXTURE_TIME))

@pytest.mark.parametrize('domain',['health','technical'])
def test_untrusted_identity_cannot_support_hard_block(domain):
    b=valid();next(r for r in b['records'] if r['domain']==domain)['trusted']=False
    b['records'][2]['quantity']=0
    assert DecisionGate.decide(context(assemble(b),FIXTURE_TIME))[0]=='HOLD'
