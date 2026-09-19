from pathlib import Path
import sys

# Alembic's console entry point does not include the repository root on
# sys.path on Windows. Keep migrations runnable from a fresh terminal.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core import settings
from app.db import Base
from app import models  # noqa: F401 - register metadata
config=context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata=Base.metadata
def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
def run_migrations_online():
    engine=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
