"""Offline backup/restore. Stop the server before using either operation."""
import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

def inventory(root):
    hashes={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError('Symlinks are not allowed in backups')
        if p.is_file():hashes[str(p.relative_to(root)).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes

def backup(source,target):
    source,target=Path(source),Path(target)
    if target.exists():raise ValueError('Backup destination must not exist')
    if not (source/'airpower.db').is_file():raise ValueError('Database not found')
    target.mkdir(parents=True)
    with sqlite3.connect(source/'airpower.db') as src, sqlite3.connect(target/'airpower.db') as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    if (source/'artifacts').is_dir():
        inventory(source/'artifacts')
        shutil.copytree(source/'artifacts',target/'artifacts')
    (target/'backup-manifest.json').write_text(json.dumps(inventory(target),indent=2))

def restore(source,target):
    source,target=Path(source),Path(target)
    if target.exists():raise ValueError('Restore target must not exist; preserve the original data directory')
    expected=json.loads((source/'backup-manifest.json').read_text())
    actual=inventory(source);actual.pop('backup-manifest.json',None)
    if actual!=expected:raise ValueError('Backup checksum mismatch')
    shutil.copytree(source,target)
    (target/'backup-manifest.json').unlink()
    with sqlite3.connect(target/'airpower.db') as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['backup','restore']);p.add_argument('source');p.add_argument('target');args=p.parse_args()
    (backup if args.operation=='backup' else restore)(args.source,args.target)
    print(args.operation.upper()+' PASSED')
