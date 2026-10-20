import base64
import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, insert, update
from . import db
from .contracts import Bundle, ImportRequest
from .domain import assemble, context, DecisionGate, digest, canonical, now, rank

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TIME = datetime(2026,10,19,12,0,tzinfo=timezone.utc)
RULE_CONFIG = {'version':'gate-a-v1','freshness':'per-case policy; inclusive max_age; future rejected',
               'ranking':['validity','feasibility','urgency_desc','consequence_desc','lead_hours_asc','quality','case_id_asc'],
               'gate_precedence':['policy','critical_evidence','hard_constraint','unknown','rul','ready']}

class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message

class Service:
    def __init__(self, engine, artifact_root, principal, role):
        self.engine = engine
        self.artifact_root = Path(artifact_root).absolute()
        if self.artifact_root.is_symlink():
            raise RuntimeError('Artifact root may not be a symlink')
        self.artifact_root.mkdir(parents=True,exist_ok=True)
        self.principal, self.role = principal, role
        # ponytail: serialized writes for one local instance; DB constraints also protect retries.
        self.lock = threading.RLock()
        self.run_lock = threading.Lock()
        self.fail_before_commit = False  # fault-injection seam; not exposed by API

    def audit(self, action, outcome):
        with self.engine.begin() as c:
            c.execute(insert(db.audit).values(data={'principal':self.principal,'role':self.role,'action':action,'outcome':outcome,'time':now().isoformat()}))

    def mutate(self, scope, key, body, expected, fn):
        if not key or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',key):
            raise Problem(422,'IDEMPOTENCY_KEY_REQUIRED','Supply a 1–128 character Idempotency-Key.')
        token = digest([self.principal,scope,key])
        fingerprint = digest([body,expected])
        with self.lock, self.engine.begin() as c:
            old = c.execute(select(db.idem).where(db.idem.c.id==token)).mappings().first()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise Problem(409,'IDEMPOTENCY_CONFLICT','Key already used with different input or version.')
                return old['response']
            result = fn(c)
            if self.fail_before_commit:
                raise RuntimeError('Injected persistence failure')
            c.execute(insert(db.idem).values(id=token,fingerprint=fingerprint,response=result))
            c.execute(insert(db.audit).values(data={'principal':self.principal,'action':scope,'outcome':'SUCCESS','time':now().isoformat()}))
            return result

    def get_case(self,c,cid,expected=None):
        row = c.execute(select(db.cases).where(db.cases.c.id==cid)).mappings().first()
        if not row: raise Problem(404,'CASE_NOT_FOUND','Case does not exist.')
        if expected is not None and row['version'] != expected:
            raise Problem(409,'STALE_VERSION','Refresh the case before submitting.')
        return row

    def append(self,c,cid,version,snapshot,event):
        c.execute(update(db.cases).where(db.cases.c.id==cid).values(version=version,snapshot=snapshot))
        c.execute(insert(db.versions).values(id=f'{cid}:{version}',case_id=cid,version=version,snapshot=snapshot))
        c.execute(insert(db.events).values(case_id=cid,data={**event,'case_version':version,'time':now().isoformat(),'principal':self.principal,'snapshot_hash':digest(snapshot)}))

    def case_card(self,c,row):
        snap = row['snapshot']
        ev = c.execute(select(db.evaluations.c.data).where(db.evaluations.c.case_id==row['id'])).scalars().all()
        latest = max(ev,key=lambda x:x['case_version']) if ev else None
        # Evidence import invalidates prior evaluation; history retains it.
        if latest and latest['input_snapshot'] != snap:
            latest = None
        ctx = context(snap,now())
        return {'case_id':row['id'],'version':row['version'],'title':snap['title'],
                'asset_id':snap['asset_id'],'component_id':snap['component_id'],
                'gate_state':latest['gate_state'] if latest else None,
                'freshness_state':'CURRENT' if ctx['current'] else ('STALE' if snap['records'] else 'UNKNOWN'),
                'snapshot':snap,'latest_evaluation':latest,'rank':rank(snap)}

    def detail(self,cid):
        with self.engine.connect() as c:
            return self.case_card(c,self.get_case(c,cid))

    def listing(self,filters,limit,cursor):
        with self.engine.connect() as c:
            cards = [self.case_card(c,r) for r in c.execute(select(db.cases)).mappings()]
        for field,value in filters.items():
            if value is not None: cards = [r for r in cards if r[field]==value]
        cards.sort(key=lambda r: (*r['rank'],r['case_id']))
        signature = digest([[r['case_id'],r['version'],r['rank']] for r in cards])
        offset = 0
        if cursor:
            try:
                p = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if p['filter'] != digest(filters) or p['signature'] != signature:
                    raise Problem(409,'CURSOR_EXPIRED','Queue changed. Restart at the first page.')
                offset = p['offset']
                if not isinstance(offset,int) or offset<0: raise ValueError()
            except Problem: raise
            except Exception: raise Problem(422,'INVALID_CURSOR','Cursor is invalid.')
        page = cards[offset:offset+limit]
        nxt = base64.urlsafe_b64encode(canonical({'offset':offset+limit,'filter':digest(filters),'signature':signature}).encode()).decode() if offset+limit<len(cards) else None
        return {'items':page,'next_cursor':nxt}

    def fixture(self,name,rebase=True):
        pack = json.loads((ROOT/'fixtures'/f'{name}.json').read_text())
        if rebase:
            delta = now()-FIXTURE_TIME
            for b in pack['bundles']:
                for r in b['records']:
                    for k in ('event_time','ingest_time','valid_from','valid_to','window_start','window_end'):
                        if k in r and r[k] is not None:
                            r[k] = (datetime.fromisoformat(r[k])+delta).isoformat()
        return pack

    def import_bundles(self,c,request):
        bundles = self.fixture(request['fixture'])['bundles'] if request.get('fixture') else request['bundles']
        rid = str(uuid.uuid4())
        c.execute(insert(db.runs).values(id=rid,kind='import',status='RUNNING',data={}))
        results = []
        for data in bundles:
            b = Bundle.model_validate(data).model_dump(mode='json')
            snapshot = assemble(b)
            old = c.execute(select(db.cases).where(db.cases.c.id==b['case_id'])).mappings().first()
            if old and old['snapshot']==snapshot:
                results.append({'case_id':b['case_id'],'state':'UNCHANGED','version':old['version']})
                continue
            version = old['version']+1 if old else 1
            if not old:
                c.execute(insert(db.cases).values(id=b['case_id'],version=0,snapshot={}))
            self.append(c,b['case_id'],version,snapshot,{'type':'EVIDENCE_IMPORTED','run_id':rid})
            for raw in b['records']:
                sid = str(uuid.uuid4())
                c.execute(insert(db.sources).values(id=sid,run_id=rid,data=raw))
                c.execute(insert(db.links).values(id=str(uuid.uuid4()),case_id=b['case_id'],source_id=sid))
            for v in snapshot['validation']:
                c.execute(insert(db.validations).values(id=str(uuid.uuid4()),run_id=rid,data=v))
            c.execute(insert(db.mappings).values(id=str(uuid.uuid4()),case_id=b['case_id'],data={'version':version,'state':snapshot['linkage'],'configuration_id':snapshot['configuration_id']}))
            results.append({'case_id':b['case_id'],'state':'QUARANTINED' if any(v['state']!='VALIDATED' for v in snapshot['validation']) else 'VALIDATED','version':version})
        result = {'cases':results,'record_count':sum(len(b['records']) for b in bundles),'fixture':request.get('fixture'),'fixture_time_rebased':bool(request.get('fixture'))}
        c.execute(update(db.runs).where(db.runs.c.id==rid).values(status='COMPLETED',data=result))
        return {'run_id':rid,'kind':'import','status':'COMPLETED','result':result}

    def evaluate(self,c,cid,expected):
        row = self.get_case(c,cid,expected)
        snapshot = row['snapshot']
        at = now()
        ctx = context(snapshot,at)
        gate,reasons = DecisionGate.decide(ctx)
        version = row['version']+1
        data = {'evaluation_id':str(uuid.uuid4()),'case_id':cid,'case_version':version,'gate_state':gate,
                'reason_codes':reasons,'evidence_references':[r['source_record_key'] for r in snapshot['records']],
                'config_fingerprint':digest({'rules':RULE_CONFIG,'policy':snapshot['policy']}),
                'decision_time':at.isoformat(),'input_snapshot':snapshot,'feasibility':ctx['feasibility'],'rul':ctx['rul']}
        if not c.execute(select(db.configs).where(db.configs.c.id==data['config_fingerprint'])).first():
            c.execute(insert(db.configs).values(id=data['config_fingerprint'],data={'rules':RULE_CONFIG,'policy':snapshot['policy']}))
        c.execute(insert(db.evaluations).values(id=data['evaluation_id'],case_id=cid,data=data))
        self.append(c,cid,version,snapshot,{'type':'EVALUATED','evaluation':data})
        return data

    def disposition(self,c,cid,expected,body):
        row = self.get_case(c,cid,expected)
        card = self.case_card(c,row)
        if card['latest_evaluation'] is None:
            raise Problem(409,'EVALUATION_REQUIRED','Evaluate current evidence before recording a disposition.')
        version = row['version']+1
        result = {'case_id':cid,'case_version':version,**body,'advisory_only':True}
        self.append(c,cid,version,row['snapshot'],{'type':'DISPOSITION_RECORDED',**result,'evaluation_id':card['latest_evaluation']['evaluation_id']})
        return result

    def history(self,cid):
        with self.engine.connect() as c:
            row = self.get_case(c,cid)
            entries = c.execute(select(db.events.c.data).where(db.events.c.case_id==cid).order_by(db.events.c.id)).scalars().all()
            vv = c.execute(select(db.versions).where(db.versions.c.case_id==cid).order_by(db.versions.c.version)).mappings().all()
        complete = [v['version'] for v in vv] == list(range(1,row['version']+1)) and len(entries)==row['version']
        replay = []
        for e in entries:
            if e['type']=='EVALUATED':
                ev=e['evaluation']
                gate,reasons=DecisionGate.decide(context(ev['input_snapshot'],datetime.fromisoformat(ev['decision_time'])))
                replay.append({'case_version':ev['case_version'],'matches':gate==ev['gate_state'] and reasons==ev['reason_codes'] and ev['config_fingerprint']==digest({'rules':RULE_CONFIG,'policy':ev['input_snapshot']['policy']})})
        return {'case_id':cid,'events':entries,'versions':[dict(v) for v in vv],'history_complete':complete,'replay':replay,'tamper_proof':False}

    def run(self,rid,kind):
        with self.engine.connect() as c:
            row = c.execute(select(db.runs).where(db.runs.c.id==rid,db.runs.c.kind==kind)).mappings().first()
        if not row: raise Problem(404,'RUN_NOT_FOUND','Run does not exist.')
        return {'run_id':rid,'kind':kind,'status':row['status'],'result':row['data']}

    def artifact(self,aid):
        with self.engine.connect() as c:
            row = c.execute(select(db.artifacts).where(db.artifacts.c.id==aid)).mappings().first()
        if not row: raise Problem(404,'ARTIFACT_NOT_FOUND','Artifact does not exist.')
        path = self.artifact_root/row['filename']
        if path.is_symlink() or path.parent.resolve()!=self.artifact_root.resolve() or not path.is_file():
            raise Problem(409,'ARTIFACT_UNAVAILABLE','Registered artifact is missing or unsafe.')
        import hashlib
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise Problem(409,'ARTIFACT_HASH_MISMATCH','Artifact checksum failed.')
        return path

    def frozen_suite(self,c):
        if not self.run_lock.acquire(blocking=False):
            raise Problem(409,'RUN_ACTIVE','An evaluation run is active.')
        try:
            rid, aid = str(uuid.uuid4()), str(uuid.uuid4())
            tests=[]
            for name in ('development-v1','holdout-v1'):
                pack=self.fixture(name,False)
                expected=pack['expected']
                for bundle in pack['bundles']:
                    snap=assemble(bundle)
                    state,reasons=DecisionGate.decide(context(snap,FIXTURE_TIME))
                    tests.append({'case_id':bundle['case_id'],'suite':name,'expected':expected[bundle['case_id']],'actual':state,'passed':state==expected[bundle['case_id']],'reason_codes':reasons})
            report={'suite':'frozen-v1','decision_time':FIXTURE_TIME.isoformat(),'passed':sum(t['passed'] for t in tests),'total':len(tests),'cases':tests,'scope':'Policy acceptance on generated fixtures; no operational accuracy claim.'}
            content=canonical(report).encode()
            filename=aid+'.json'
            tmp=self.artifact_root/(aid+'.tmp')
            tmp.write_bytes(content)
            os.replace(tmp,self.artifact_root/filename)
            import hashlib
            c.execute(insert(db.artifacts).values(id=aid,filename=filename,sha256=hashlib.sha256(content).hexdigest()))
            result={'passed':report['passed'],'total':report['total'],'artifact_id':aid,'status':'PASSED' if report['passed']==report['total'] else 'FAILED'}
            c.execute(insert(db.runs).values(id=rid,kind='evaluation',status='COMPLETED',data=result))
            return {'run_id':rid,'kind':'evaluation','status':'COMPLETED','result':result}
        finally:
            self.run_lock.release()

    def stub(self,c,kind):
        rid=str(uuid.uuid4())
        result={'status':'PENDING' if kind=='rul' else 'NOT_RUN','reason':'Gate B model validation required.' if kind=='rul' else 'Gate C simulation validation required.','value':None}
        c.execute(insert(db.runs).values(id=rid,kind=kind,status='BLOCKED',data=result))
        return {'run_id':rid,'kind':kind,'status':'BLOCKED','result':result}
