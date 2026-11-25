import datetime as dt

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import scripts.seed_demo as seed_script
from config import ROOT
from db.models import DailyMetric, SupplementLog


@pytest.fixture
def scratch_db(tmp_path):
    path = tmp_path / "scratch.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return path, engine


def _rows(engine, table):
    with Session(engine) as session:
        return session.exec(select(table)).all()


def test_nothing_happens_without_yes(scratch_db, capsys):
    path, engine = scratch_db
    assert seed_script.main(["--db", str(path)], env={}) == 2
    assert "--yes" in capsys.readouterr().err
    assert _rows(engine, DailyMetric) == []


def test_an_explicit_database_is_required(capsys):
    assert seed_script.main(["--yes"], env={}) == 2
    assert "--db" in capsys.readouterr().err


def test_the_real_database_is_refused_without_force_real(capsys):
    real = ROOT / "biostack.db"
    assert seed_script.main(["--yes", "--db", str(real)], env={}) == 2
    assert "--force-real" in capsys.readouterr().err
    assert seed_script.main(["--yes", "--remove"], env={"DATABASE_URL": f"sqlite:///{real}"}) == 2


def test_force_real_lifts_only_the_default_database_guard(scratch_db, monkeypatch):
    path, engine = scratch_db
    monkeypatch.setattr(seed_script, "DEFAULT_DB", path)
    assert seed_script.main(["--yes", "--db", str(path)], env={}) == 2
    assert seed_script.main(["--yes", "--force-real", "--db", str(path)], env={}) == 0
    assert len(_rows(engine, DailyMetric)) == 60


def test_seeds_a_scratch_database_given_as_url_or_environment(scratch_db):
    path, engine = scratch_db
    assert seed_script.main(["--yes", "--db", f"sqlite:///{path}"], env={}) == 0
    assert all(row.source == "demo" for row in _rows(engine, SupplementLog))
    assert seed_script.main(["--yes"], env={"DATABASE_URL": f"sqlite:///{path}"}) == 0
    assert len(_rows(engine, DailyMetric)) == 60


def test_remove_deletes_only_demo_rows(scratch_db):
    path, engine = scratch_db
    seed_script.main(["--yes", "--db", str(path)], env={})
    with Session(engine) as session:
        session.add(DailyMetric(metric_date=dt.date(2019, 1, 1), hrv_sdnn=40.0, source="manual"))
        session.commit()
    assert seed_script.main(["--yes", "--remove", "--db", str(path)], env={}) == 0
    assert [m.source for m in _rows(engine, DailyMetric)] == ["manual"]
    assert _rows(engine, SupplementLog) == []


def test_a_database_without_the_schema_is_refused(tmp_path, capsys):
    empty = tmp_path / "empty.db"
    create_engine(f"sqlite:///{empty}").connect().close()
    assert seed_script.main(["--yes", "--db", str(empty)], env={}) == 2
    assert "alembic upgrade head" in capsys.readouterr().err


def test_a_missing_database_file_is_not_created(tmp_path, capsys):
    missing = tmp_path / "nope.db"
    assert seed_script.main(["--yes", "--db", str(missing)], env={}) == 2
    assert not missing.exists()


def test_the_configured_database_is_refused_without_force_real(scratch_db, monkeypatch, capsys):
    path, engine = scratch_db
    monkeypatch.setattr(seed_script.settings, "database_url", f"sqlite:///{path}")
    assert seed_script.main(["--yes", "--db", str(path)], env={}) == 2
    assert "--force-real" in capsys.readouterr().err
    assert _rows(engine, DailyMetric) == []
    assert seed_script.main(["--yes", "--force-real", "--db", str(path)], env={}) == 0
