import ast
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
tests={node.name for file in (ROOT/'tests').glob('test_*.py') for node in ast.walk(ast.parse(file.read_text())) if isinstance(node,ast.FunctionDef) and node.name.startswith('test_')}
rtm=json.loads((ROOT/'docs'/'traceability.json').read_text())
required={f'F{i:02}' for i in [1,2,3,4,5,6,7,8,9,12,13]}
assert required<=set(rtm)
for requirement,names in rtm.items():
    assert names and set(names)<=tests,(requirement,names)
# Gate-state producer must remain singular; no literal outputs in UI/controller/service.
source=(ROOT/'backend'/'domain.py').read_text()
assert source.count('class DecisionGate:')==1
for filename in ('api.py','service.py','gemini.py'):
    tree=ast.parse((ROOT/'backend'/filename).read_text())
    assert not any(isinstance(n,ast.Constant) and n.value in ('READY_FOR_HUMAN_REVIEW','HOLD','BLOCK') for n in ast.walk(tree)),filename
print(f'TRACEABILITY PASSED: {len(rtm)} supplied requirements linked to existing tests; single gate producer check passed.')
