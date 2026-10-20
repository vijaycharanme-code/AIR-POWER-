"""Run a fresh isolated server, every HTTP operation, and browser workflow checks."""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
from http_smoke import run
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='airpower-browser-') as tmp:
    env={**os.environ,'AIRPOWER_PRINCIPAL':'Browser tester','AIRPOWER_ROLE':'planner','DATABASE_URL':'sqlite:///'+str(Path(tmp)/'test.db'),'ARTIFACT_ROOT':str(Path(tmp)/'artifacts'),'GEMINI_API_KEY':''}
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env,check=True)
    with (ROOT/'reports'/'server-test.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(100):
                    if server.poll() is not None:raise RuntimeError('Test server failed to start; inspect reports/server-test.log')
                    try:
                        if client.get('http://127.0.0.1:8000/api/v1/ready').status_code==200:break
                    except httpx.ConnectError:pass
                    time.sleep(.1)
                else:raise RuntimeError('Server readiness timed out')
            run()
            command=['node',str(ROOT/'frontend'/'node_modules'/'@playwright'/'test'/'cli.js'),'test']
            subprocess.run(command,cwd=ROOT/'frontend',env=env,check=True,timeout=120)
        finally:
            server.terminate()
            server.wait(timeout=10)
