from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./argus.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    from app import models

    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    inspector = inspect(engine)
    if "heal_events" not in inspector.get_table_names():
        return
    column_names = {c["name"] for c in inspector.get_columns("heal_events")}
    if "error_message" not in column_names:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE heal_events ADD COLUMN error_message TEXT"))

    if "scrape_results" in inspector.get_table_names():
        scrape_columns = {c["name"] for c in inspector.get_columns("scrape_results")}
        if "reviews" not in scrape_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE scrape_results ADD COLUMN reviews TEXT"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
