import json
import sqlite3
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.db import engine_for
from scripts.backup import backup,restore
from backend.service import ROOT

def test_clean_migration_backup_restore(tmp_path,monkeypatch):
    data=tmp_path/'data';data.mkdir()
    url='sqlite:///'+str(data/'airpower.db');monkeypatch.setenv('DATABASE_URL',url)
    config=Config(str(ROOT/'alembic.ini'));config.set_main_option('script_location',str(ROOT/'alembic'))
    command.upgrade(config,'head')
    engine=engine_for(url)
    with TestClient(create_app(engine,data/'artifacts','backup-test','planner')) as c:
        assert c.get('/api/v1/ready').status_code==200
        r=c.post('/api/v1/import-runs',json={'fixture':'development-v1'},headers={'Idempotency-Key':'backup-import'})
        assert r.status_code==200
        run=c.post('/api/v1/evaluation-runs',json={'suite':'frozen-v1'},headers={'Idempotency-Key':'backup-suite'}).json()
        aid=run['result']['artifact_id']
    engine.dispose()
    backup(data,tmp_path/'backup');restore(tmp_path/'backup',tmp_path/'restored')
    restored=engine_for('sqlite:///'+str(tmp_path/'restored'/'airpower.db'))
    with TestClient(create_app(restored,tmp_path/'restored'/'artifacts','restored','planner')) as c:
        assert len(c.get('/api/v1/cases?limit=50').json()['items'])==40
        assert c.get('/api/v1/artifacts/'+aid).status_code==200
    with pytest.raises(ValueError):restore(tmp_path/'backup',data)
    (tmp_path/'backup'/'artifacts'/(aid+'.json')).write_text('corruption')
    with pytest.raises(ValueError):restore(tmp_path/'backup',tmp_path/'corrupt-restore')
    restored.dispose()
