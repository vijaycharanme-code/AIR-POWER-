import pytest
from fastapi.testclient import TestClient
from alembic.config import Config
from alembic import command
from backend.api import create_app
from backend.db import engine_for,metadata

@pytest.fixture
def client(tmp_path):
    engine=engine_for('sqlite:///:memory:')
    metadata.create_all(engine)
    with engine.begin() as c:
        from sqlalchemy import text
        c.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
        c.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    app=create_app(engine,tmp_path/'artifacts','tester','planner')
    with TestClient(app,raise_server_exceptions=False) as c:
        yield c
    engine.dispose()
