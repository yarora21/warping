"""Server routing and database initialization checks; no browser automation."""
import asyncio
import pytest
from sqlalchemy import text
from starlette.exceptions import HTTPException
from app import bootstrap
from app.static import FrontendFiles


def test_frontend_fallback_preserves_api_and_asset_errors(tmp_path):
    (tmp_path / 'index.html').write_text('<html>Northstar</html>')
    frontend = FrontendFiles(directory=tmp_path, html=True)
    scope = {'type': 'http', 'method': 'GET', 'headers': [], 'path': '/'}
    for path in ('.', 'people/jamie'):
        response = asyncio.run(frontend.get_response(path, scope))
        assert response.status_code == 200
        assert response.media_type == 'text/html'
    for path in ('api/missing', 'assets/missing.js', 'assets/missing', 'missing.css', '../secret.txt'):
        with pytest.raises(HTTPException) as error:
            asyncio.run(frontend.get_response(path, scope))
        assert error.value.status_code == 404


def test_hosted_bootstrap_skips_existing_data(monkeypatch):
    # The outer context rolls back so the shared isolated test schema stays empty.
    from app.database import engine
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text('SELECT pg_advisory_xact_lock(72021001)'))
            monkeypatch.setenv('APP_TODAY', '2026-09-12')
            assert bootstrap.seed_if_empty(connection) is True
            connection.execute(text("UPDATE employees SET name='Saved demo edit' WHERE id='jamie'"))

            def unexpected_seed(connection):
                pytest.fail('A restart must not invoke seed on existing application data')

            monkeypatch.setattr(bootstrap, 'seed', unexpected_seed)
            assert bootstrap.seed_if_empty(connection) is False
            assert connection.execute(text("SELECT name FROM employees WHERE id='jamie'")).scalar() == 'Saved demo edit'
        finally:
            transaction.rollback()
