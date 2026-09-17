import os
from sqlalchemy import create_engine

database_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://policies:local-demo-only@localhost:5432/policies")
# Hosted providers supply the standard scheme; this app uses psycopg 3.
if database_url.startswith(('postgres://', 'postgresql://')):
    database_url = 'postgresql+psycopg://' + database_url.split('://', 1)[1]

engine = create_engine(
    database_url,
    pool_pre_ping=True,
)
