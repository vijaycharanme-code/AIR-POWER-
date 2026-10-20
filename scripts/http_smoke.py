"""Exercise every OpenAPI operation against a running loopback server."""
import json
import uuid
from pathlib import Path
import httpx

def run(base='http://127.0.0.1:8000'):
    rows=[]
    with httpx.Client(base_url=base,trust_env=False,timeout=30) as client:
        def call(method,path,body=None,version=None,status=200,template=None):
            headers={'Idempotency-Key':str(uuid.uuid4())}
            if version is not None:headers['If-Match']=str(version)
            r=client.request(method,'/api/v1'+path,json=body,headers=headers)
            rows.append({'method':method,'path':'/api/v1'+(template or path),'http_status':r.status_code,'expected':status,'passed':r.status_code==status})
            assert r.status_code==status,(path,r.status_code,r.text)
            return r.json()
        for p in ('/live','/ready','/session','/demo/metadata'):call('GET',p)
        imp=call('POST','/import-runs',{'fixture':'development-v1'})
        call('GET','/import-runs/'+imp['run_id'],template='/import-runs/{runId}')
        call('GET','/cases')
        cid='DEV-VALID-001';casepath='/cases/'+cid
        c=call('GET',casepath,template='/cases/{caseId}')
        e=call('POST',casepath+'/evaluations',{},c['version'],template='/cases/{caseId}/evaluations')
        d=call('POST',casepath+'/dispositions',{'disposition':'DEFER','note':'HTTP endpoint smoke check'},e['case_version'],template='/cases/{caseId}/dispositions')
        call('GET',casepath+'/events',template='/cases/{caseId}/events')
        call('POST',casepath+'/explanations',{},d['case_version'],status=503,template='/cases/{caseId}/explanations')
        for kind in ('evaluation','rul','simulation'):
            result=call('POST','/'+kind+'-runs',{'suite':'frozen-v1'} if kind=='evaluation' else {})
            call('GET','/'+kind+'-runs/'+result['run_id'],template='/'+kind+'-runs/{runId}')
            if kind!='evaluation':call('GET','/'+kind+'-runs')
            else:call('GET','/artifacts/'+result['result']['artifact_id'],template='/artifacts/{artifactId}')
        schema=client.get('/api/v1/openapi.json').json()
        required={(method.upper(),path) for path,ops in schema['paths'].items() for method in ops if method in ('get','post','put','delete','patch')}
        covered={(r['method'],r['path']) for r in rows}
        assert required<=covered,required-covered
    report={'passed':len(rows),'total':len(required),'operations':rows,'live_gemini':'NOT_RUN: no key supplied; missing-key 503 verified; provider responses tested using controlled transport.'}
    (Path(__file__).resolve().parents[1]/'reports'/'endpoint-smoke.json').write_text(json.dumps(report,indent=2))
    print(f'HTTP ENDPOINT CHECK: {len(rows)}/{len(required)} passed')
if __name__=='__main__':run()
