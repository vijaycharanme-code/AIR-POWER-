import os
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, Depends, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from sqlalchemy import text
from dotenv import load_dotenv
from .contracts import (ImportRequest, Empty, Disposition, Explanation, SuiteRequest,
                        Gate, CaseCard, CasePage, EvaluationResult, RunResult, Error, Health, Technical, Spares, Agency)
from .db import engine_for
from .service import Service, Problem, ROOT
from .gemini import explain

CAPABILITIES = {
    'planner': {'read','import','evaluate','disposition','run','metadata','artifact','explain'},
    'analyst': {'read','metadata','artifact','explain'},
    'reviewer': {'read','evaluate','disposition','metadata','artifact','explain'},
    'evaluator': {'read','import','evaluate','run','metadata','artifact','explain'},
}

def create_app(engine=None, artifact_root=None, principal=None, role=None):
    load_dotenv(ROOT/'.env')
    principal=principal or os.getenv('AIRPOWER_PRINCIPAL')
    role=role or os.getenv('AIRPOWER_ROLE')
    if not principal or role not in CAPABILITIES:
        raise RuntimeError('Configure AIRPOWER_PRINCIPAL and a valid AIRPOWER_ROLE in .env before startup.')
    (ROOT/'data').mkdir(exist_ok=True)
    service=Service(engine or engine_for(os.getenv('DATABASE_URL','sqlite:///data/airpower.db')),
                    artifact_root or os.getenv('ARTIFACT_ROOT','data/artifacts'), principal, role)
    app=FastAPI(title='AirPower Advisory API',version='1.0.0',openapi_url='/api/v1/openapi.json',docs_url='/api/docs',redoc_url=None, responses={code:{'model':Error} for code in (403,404,409,413,422,500,502,503,504)})
    app.state.service=service
    def envelope(status,code,message):
        return JSONResponse(status_code=status,content={'error':{'code':code,'message':message}})
    @app.exception_handler(Problem)
    async def problem_handler(_,exc): return envelope(exc.status,exc.code,exc.message)
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_,exc):
        return envelope(422,'VALIDATION_ERROR','Invalid request. Check required fields, types, filters and timezone-aware timestamps.')
    @app.exception_handler(HTTPException)
    async def http_handler(_,exc): return envelope(exc.status_code,'HTTP_ERROR',str(exc.detail))
    @app.exception_handler(Exception)
    async def failure_handler(_,exc):
        return envelope(500,'OPERATION_FAILED','Operation failed. No decision result was committed; retry safely with the same key.')

    @app.middleware('http')
    async def local_guard(request,call_next):
        host=request.url.hostname
        if host not in ('127.0.0.1','localhost','::1','testserver'):
            return envelope(403,'LOOPBACK_ONLY','Use the loopback address.')
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('origin')
            if origin:
                u=urlsplit(origin)
                if u.scheme != request.url.scheme or u.netloc != request.url.netloc:
                    service.audit(request.url.path,'CROSS_ORIGIN_DENIED')
                    return envelope(403,'ORIGIN_DENIED','Mutation origin must match the local application.')
            if request.headers.get('sec-fetch-site') in ('cross-site','same-site'):
                service.audit(request.url.path,'CROSS_SITE_DENIED')
                return envelope(403,'ORIGIN_DENIED','Cross-site mutations are denied.')
            # Stream bound applies even without Content-Length.
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>2_000_000:
                    return envelope(413,'PAYLOAD_TOO_LARGE','Import limit is 2 MB and 300 case bundles.')
            request._body=bytes(body)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
        return response

    def require(cap):
        def check():
            if cap not in CAPABILITIES[role]:
                service.audit(cap,'DENIED')
                raise Problem(403,'FORBIDDEN','This startup-configured demo role cannot perform that action.')
        return Depends(check)
    def version(if_match: str | None = Header(default=None)):
        try:
            v=int((if_match or '').strip('"'))
            if v<1: raise ValueError()
            return v
        except ValueError:
            raise Problem(422,'IF_MATCH_REQUIRED','Supply the current positive case version in If-Match.')
    def mutation(request,key,body,fn,expected=None):
        return service.mutate(request.url.path,key,body,expected,fn)
    prefix='/api/v1'
    @app.get(prefix+'/live')
    def live(): return {'status':'LIVE','release_id':'airpower-1.0.0'}
    @app.get(prefix+'/ready')
    def ready():
        try:
            with service.engine.connect() as c:
                c.execute(text('SELECT version_num FROM alembic_version'))
                c.execute(text('SELECT count(*) FROM cases'))
            test=service.artifact_root/'.ready'
            test.write_text('ready'); test.unlink()
        except Exception:
            raise Problem(503,'NOT_READY','Run migrations and check database/artifact directory permissions.')
        return {'status':'READY','database':'OK','artifacts':'OK'}
    @app.get(prefix+'/session')
    def session(): return {'principal':principal,'role':role,'demo_only':True,'capabilities':sorted(CAPABILITIES[role])}
    @app.get(prefix+'/demo/metadata',dependencies=[require('metadata')])
    def metadata():
        return {'fixtures':['development-v1','holdout-v1'],'policy_version':'gate-a-v1','model_version':'gate-b-not-validated','gemini_configured':bool(os.getenv('GEMINI_API_KEY')),'gemini_model':os.getenv('GEMINI_MODEL','gemini-flash-latest')}
    @app.get(prefix+'/cases',response_model=CasePage,dependencies=[require('read')])
    def cases(gate_state:Gate|None=None,asset_id:str|None=None,component_id:str|None=None,
              freshness_state:str|None=Query(None,pattern='^(CURRENT|STALE|UNKNOWN)$'),
              limit:int=Query(25,ge=1,le=50),cursor:str|None=Query(None,max_length=2000)):
        return service.listing({'gate_state':gate_state.value if gate_state else None,'asset_id':asset_id,'component_id':component_id,'freshness_state':freshness_state},limit,cursor)
    @app.get(prefix+'/cases/{caseId}',response_model=CaseCard,dependencies=[require('read')])
    def detail(caseId:str): return service.detail(caseId)
    @app.get(prefix+'/cases/{caseId}/events',dependencies=[require('read')])
    def events(caseId:str): return service.history(caseId)
    @app.post(prefix+'/import-runs',response_model=RunResult,dependencies=[require('import')])
    def imports(body:ImportRequest,request:Request,idempotency_key:str|None=Header(None)):
        data=body.model_dump(mode='json')
        return mutation(request,idempotency_key,data,lambda c:service.import_bundles(c,data))
    @app.get(prefix+'/import-runs/{runId}',response_model=RunResult,dependencies=[require('read')])
    def import_run(runId:str): return service.run(runId,'import')
    @app.post(prefix+'/cases/{caseId}/evaluations',response_model=EvaluationResult,dependencies=[require('evaluate')])
    def evaluate(caseId:str,body:Empty,request:Request,expected:int=Depends(version),idempotency_key:str|None=Header(None)):
        return mutation(request,idempotency_key,{},lambda c:service.evaluate(c,caseId,expected),expected)
    @app.post(prefix+'/cases/{caseId}/dispositions',dependencies=[require('disposition')])
    def disposition(caseId:str,body:Disposition,request:Request,expected:int=Depends(version),idempotency_key:str|None=Header(None)):
        data=body.model_dump()
        return mutation(request,idempotency_key,data,lambda c:service.disposition(c,caseId,expected,data),expected)
    @app.post(prefix+'/evaluation-runs',response_model=RunResult,dependencies=[require('run')])
    def suite(body:SuiteRequest,request:Request,idempotency_key:str|None=Header(None)):
        return mutation(request,idempotency_key,body.model_dump(),service.frozen_suite)
    @app.get(prefix+'/evaluation-runs/{runId}',response_model=RunResult,dependencies=[require('read')])
    def evaluation_run(runId:str): return service.run(runId,'evaluation')
    @app.get(prefix+'/rul-runs',dependencies=[require('read')])
    def rul_list(): return run_list('rul')
    @app.get(prefix+'/simulation-runs',dependencies=[require('read')])
    def simulation_list(): return run_list('simulation')
    def run_list(kind):
        from sqlalchemy import select
        from . import db
        with service.engine.connect() as c:
            rows=c.execute(select(db.runs).where(db.runs.c.kind==kind).order_by(db.runs.c.id).limit(50)).mappings().all()
        return {'items':[{'run_id':r['id'],'kind':kind,'status':r['status'],'result':r['data']} for r in rows]}
    @app.post(prefix+'/rul-runs',response_model=RunResult,dependencies=[require('run')])
    def rul(body:Empty,request:Request,idempotency_key:str|None=Header(None)):
        return mutation(request,idempotency_key,{},lambda c:service.stub(c,'rul'))
    @app.get(prefix+'/rul-runs/{runId}',response_model=RunResult,dependencies=[require('read')])
    def rul_run(runId:str): return service.run(runId,'rul')
    @app.post(prefix+'/simulation-runs',response_model=RunResult,dependencies=[require('run')])
    def simulation(body:Empty,request:Request,idempotency_key:str|None=Header(None)):
        return mutation(request,idempotency_key,{},lambda c:service.stub(c,'simulation'))
    @app.get(prefix+'/simulation-runs/{runId}',response_model=RunResult,dependencies=[require('read')])
    def simulation_run(runId:str): return service.run(runId,'simulation')
    @app.get(prefix+'/artifacts/{artifactId}',dependencies=[require('artifact')])
    def artifact(artifactId:str): return FileResponse(service.artifact(artifactId),media_type='application/json',filename=artifactId+'.json')
    @app.post(prefix+'/cases/{caseId}/explanations',dependencies=[require('explain')])
    def explanation(caseId:str,body:Explanation,request:Request,expected:int=Depends(version),idempotency_key:str|None=Header(None)):
        def work(c):
            card=service.case_card(c,service.get_case(c,caseId,expected))
            return explain(card,body.question)
        return mutation(request,idempotency_key,body.model_dump(),work,expected)

    dist=ROOT/'frontend'/'dist'
    if (dist/'assets').is_dir(): app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}',include_in_schema=False)
    def spa(path:str):
        if path.startswith('api/'):
            raise Problem(404,'NOT_FOUND','API route does not exist.')
        if not (dist/'index.html').is_file():
            raise Problem(503,'FRONTEND_NOT_BUILT','Run npm ci and npm run build in frontend.')
        return FileResponse(dist/'index.html')
    original_openapi=app.openapi
    def contract_openapi():
        schema=original_openapi()
        for model in (Health,Technical,Spares,Agency):
            schema['components']['schemas'][model.__name__]=model.model_json_schema()
        return schema
    app.openapi=contract_openapi
    return app
