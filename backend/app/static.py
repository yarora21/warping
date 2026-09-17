"""Optional same-origin frontend for the combined deployment image."""
import os
from pathlib import PurePosixPath
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        # Unknown API paths must remain API errors, never an HTML success.
        if path.split('/')[0] in {'api', 'docs', 'redoc', 'openapi.json'}:
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            # Client-side routes use the app shell; missing assets stay 404.
            if error.status_code != 404 or PurePosixPath(path).suffix or path.startswith('assets/'):
                raise
            return await super().get_response('index.html', scope)


def mount_frontend(app):
    directory = os.environ.get('STATIC_DIR')
    if directory:
        # Registered after all API routes; fails startup on a missing build.
        app.mount('/', FrontendFiles(directory=directory, html=True), name='frontend')
