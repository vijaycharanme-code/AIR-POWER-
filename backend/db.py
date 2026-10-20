from pathlib import Path
from sqlalchemy import create_engine, event, MetaData, Table, Column, String, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.pool import StaticPool
metadata = MetaData()
def table(name, *columns):
    return Table(name, metadata, *columns)
cases = table('cases', Column('id',String,primary_key=True), Column('version',Integer,nullable=False), Column('snapshot',JSON,nullable=False))
versions = table('case_versions', Column('id',String,primary_key=True), Column('case_id',ForeignKey('cases.id'),nullable=False), Column('version',Integer,nullable=False), Column('snapshot',JSON,nullable=False), UniqueConstraint('case_id','version'))
evaluations = table('evaluations', Column('id',String,primary_key=True), Column('case_id',ForeignKey('cases.id'),nullable=False), Column('data',JSON,nullable=False))
events = table('case_events', Column('id',Integer,primary_key=True,autoincrement=True), Column('case_id',ForeignKey('cases.id'),nullable=False), Column('data',JSON,nullable=False))
runs = table('runs', Column('id',String,primary_key=True), Column('kind',String,nullable=False), Column('status',String,nullable=False), Column('data',JSON,nullable=False))
sources = table('source_records', Column('id',String,primary_key=True), Column('run_id',ForeignKey('runs.id'),nullable=False), Column('data',JSON,nullable=False))
validations = table('validation_results', Column('id',String,primary_key=True), Column('run_id',ForeignKey('runs.id'),nullable=False), Column('data',JSON,nullable=False))
mappings = table('asset_component_mappings', Column('id',String,primary_key=True), Column('case_id',ForeignKey('cases.id'),nullable=False), Column('data',JSON,nullable=False))
links = table('case_evidence_links', Column('id',String,primary_key=True), Column('case_id',ForeignKey('cases.id'),nullable=False), Column('source_id',ForeignKey('source_records.id'),nullable=False))
configs = table('rule_config_versions', Column('id',String,primary_key=True), Column('data',JSON,nullable=False))
models = table('model_registry_versions', Column('id',String,primary_key=True), Column('data',JSON,nullable=False))
idem = table('idempotency_records', Column('id',String,primary_key=True), Column('fingerprint',String,nullable=False), Column('response',JSON,nullable=False))
artifacts = table('artifact_references', Column('id',String,primary_key=True), Column('filename',String,nullable=False), Column('sha256',String,nullable=False))
audit = table('security_audit_events', Column('id',Integer,primary_key=True,autoincrement=True), Column('data',JSON,nullable=False))

def engine_for(url):
    kwargs = {'connect_args': {'check_same_thread': False, 'timeout': 30}}
    if url.endswith(':memory:'):
        kwargs['poolclass'] = StaticPool
    engine = create_engine(url, **kwargs)
    @event.listens_for(engine, 'connect')
    def pragmas(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    return engine
