import os
from sqlalchemy import create_engine

engine = create_engine(
    os.environ.get("DATABASE_URL", "postgresql+psycopg://policies:local-demo-only@localhost:5432/policies"),
    pool_pre_ping=True,
)
