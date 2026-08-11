import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import brightdata_client, database, orchestrator
from app.database import Base
from app.models import Collector


@pytest.fixture()
def db_env(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(orchestrator, "SessionLocal", factory)
    monkeypatch.setattr(brightdata_client, "SessionLocal", factory)

    db = factory()
    db.add(
        Collector(
            id="demo",
            name="Demo Shop",
            brightdata_collector_id="c_demo",
            site_url="https://example.com",
        )
    )
    db.commit()
    db.close()

    return factory
