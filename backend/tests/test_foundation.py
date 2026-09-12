"""PostgreSQL checks run inside rolled-back transactions; no demo data is reset."""
from datetime import date
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from app.database import engine
from app.seed import seed
from app.queries import people, catalog


@pytest.fixture
def connection():
    with engine.connect() as conn:
        transaction = conn.begin()
        yield conn
        transaction.rollback()


def test_seed_is_additive_and_directory_is_readable(connection, monkeypatch):
    monkeypatch.setenv("APP_TODAY", "2026-09-12")
    seed(connection)
    before = connection.execute(text("SELECT count(*) FROM employee_versions")).scalar()
    connection.execute(text("UPDATE employees SET name='Jamie Updated' WHERE id='jamie'"))
    seed(connection)
    assert connection.execute(text("SELECT count(*) FROM employee_versions")).scalar() == before
    records = {p.id: p for p in people(connection, date(2026, 9, 12))}
    assert records["jamie"].name == "Jamie Updated"
    assert records["jamie"].manager_name == "Alex Chen"
    assert records["riley"].status == "upcoming"
    assert len(catalog(connection, date(2026, 9, 12))) == 5


@pytest.mark.parametrize("statement", [
    "INSERT INTO employments VALUES ('test_invalid','missing_employee')",
    """INSERT INTO employee_versions
        (id, employment_id, employment_type,country,department_id,effective_from,created_by,change_reason)
        SELECT 'test_overlap',employment_id,employment_type,country,department_id,effective_from,created_by,change_reason
        FROM employee_versions WHERE id='attributes_jamie_1'""",
])
def test_database_rejects_invalid_reference_and_overlap(connection, statement):
    seed(connection)
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(text(statement))


def test_revisions_only_allow_one_time_supersession(connection):
    seed(connection)
    with pytest.raises(DBAPIError):
        with connection.begin_nested():
            connection.execute(text("UPDATE employee_versions SET country='GB' WHERE id='attributes_jamie_1'"))
    connection.execute(text("""UPDATE employee_versions SET superseded_at=now(), superseded_by='taylor',
        superseded_reason='Test revision' WHERE id='attributes_jamie_1'"""))
    with pytest.raises(DBAPIError):
        with connection.begin_nested():
            connection.execute(text("UPDATE employee_versions SET superseded_reason='Changed' WHERE id='attributes_jamie_1'"))
