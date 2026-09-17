"""Keep integration tests separate from the human's editable demo company."""
from importlib import import_module
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, text
from app.database import engine


@pytest.fixture(scope='session', autouse=True)
def isolated_test_schema():
    schema = 'test_' + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
        connection.execute(text(f'SET LOCAL search_path TO {schema}, public'))
        with Operations.context(MigrationContext.configure(connection)):
            for name in ('0001_directory','0002_assignments','0003_overrides'):
                import_module(f'migrations.versions.{name}').upgrade()

    def select_schema(dbapi_connection, connection_record, connection_proxy):
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO {schema}, public')
        dbapi_connection.autocommit = previous

    event.listen(engine,'checkout',select_schema)
    try:
        yield
    finally:
        event.remove(engine,'checkout',select_schema)
        engine.dispose()
        with engine.begin() as connection:
            # Only the fresh random schema created above is removed.
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
