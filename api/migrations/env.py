from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings

config = context.config


def run_migrations() -> None:
    url = config.attributes.get("url") or get_settings().sqlalchemy_url
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
