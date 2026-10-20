import os
from pathlib import Path
from alembic import context
from backend.db import metadata, engine_for
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('DATABASE_URL', 'sqlite:///data/airpower.db')
Path('data').mkdir(exist_ok=True)
if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
else:
    with engine_for(url).connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
        with context.begin_transaction(): context.run_migrations()
