import os

from alembic import context
from sqlalchemy import create_engine

URL = os.environ.get("DATABASE_URL", "postgresql://x@localhost/x").replace("postgresql://", "postgresql+psycopg://", 1)


def offline():
    context.configure(url=URL, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def online():
    with create_engine(URL).connect() as conn:
        context.configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()


offline() if context.is_offline_mode() else online()
