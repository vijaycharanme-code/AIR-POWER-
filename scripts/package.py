"""Create a clean release ZIP with a per-file SHA-256 manifest."""
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'node_modules','.venv','.pytest_cache','__pycache__','data','test-results','playwright-report'}
def included(p):
    parts=p.relative_to(ROOT).parts
    return not any(part in EXCLUDE for part in parts) and p.name not in ('.env','package-manifest.json') and p.suffix not in ('.pyc','.zip') and not p.name.endswith('.log')
files=sorted(p for p in ROOT.rglob('*') if p.is_file() and included(p))
manifest={'release':'airpower-1.0.0','files':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
mp=ROOT/'docs'/'package-manifest.json';mp.write_text(json.dumps(manifest,indent=2));files.append(mp)
output=ROOT.parent/'AirPower_SIH26249_Complete_Tested.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,'AirPower/'+str(p.relative_to(ROOT)))
with zipfile.ZipFile(output) as z:
    assert z.testzip() is None
    for name,sha in manifest['files'].items():assert hashlib.sha256(z.read('AirPower/'+name)).hexdigest()==sha
print(f'{output}: {len(files)} files, {output.stat().st_size} bytes; archive and manifest verified')
