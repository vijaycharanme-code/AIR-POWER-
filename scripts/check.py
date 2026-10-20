import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks=[[sys.executable,'-m','pytest','-q','--junitxml=reports/pytest.xml'],[sys.executable,'scripts/traceability.py']]
for command in checks:
    result=subprocess.run(command,cwd=ROOT,timeout=180)
    if result.returncode:sys.exit(result.returncode)
print('BACKEND AND TRACEABILITY PASSED. UI: cd frontend && npm ci && npm test && npm run build')
