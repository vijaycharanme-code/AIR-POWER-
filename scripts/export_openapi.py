import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.api import create_app
ROOT=Path(__file__).resolve().parents[1]
app=create_app(principal='schema-export',role='planner')
(ROOT/'docs'/'openapi.json').write_text(json.dumps(app.openapi(),indent=2))
