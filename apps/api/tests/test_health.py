from fastapi.testclient import TestClient
from sqlmodel import Session

from config import settings
from db.database import get_session
from main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_protected_requires_token(engine):
    """Runs against the in-memory test database, never the owner's real one."""
    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    try:
        assert client.get("/api/v1/records").status_code == 401
        ok = client.get("/api/v1/records", headers={"Authorization": f"Bearer {settings.api_secret_key}"})
        assert ok.status_code == 200
    finally:
        app.dependency_overrides.pop(get_session, None)
