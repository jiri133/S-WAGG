"""Deploy in one container (Hugging Face Spaces): FastAPI also serves the built React app.

Off unless STATIC_DIR points at `frontend/dist`; in development Vite serves React.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve `dist`: real files as they are, any other path as index.html (React routes)."""
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (dist / path).resolve()
        if path and file.is_file() and dist.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(index)
