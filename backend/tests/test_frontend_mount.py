"""Deploy: FastAPI serves the built React app; /api stays the API, React routes get index.html."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.frontend import mount_frontend


def test_serves_files_and_falls_back_to_index_for_react_routes(tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    mount_frontend(app, tmp_path)
    c = TestClient(app)
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/plan").text == "<html>app</html>"  # a React route
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/api/nope").status_code == 404  # not swallowed by the fallback
    assert c.get("/../backend/app.db").text == "<html>app</html>"  # no way out of dist
