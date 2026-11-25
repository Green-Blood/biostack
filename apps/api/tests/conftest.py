import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import db.models  # noqa: F401  (register tables)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    from fastapi.testclient import TestClient

    from config import settings
    from db.database import get_session
    from main import app

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    c = TestClient(app, headers={"Authorization": f"Bearer {settings.api_secret_key}"})
    yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_startup_hook_on_the_real_db(monkeypatch):
    """App start-up marks interrupted imports on the configured database; tests must never reach it."""
    import main
    monkeypatch.setattr(main, "_mark_interrupted_imports", lambda: None)
