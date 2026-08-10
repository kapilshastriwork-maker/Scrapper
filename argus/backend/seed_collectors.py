from app import config
from app.database import SessionLocal, init_db
from app.models import Collector

COLLECTOR_DEFS = [
    {"id": "amazon", "name": "Amazon"},
    {"id": "flipkart", "name": "Flipkart"},
    {"id": "croma", "name": "Croma"},
    {"id": "demo", "name": "Demo Shop"},
]


def main():
    init_db()

    db = SessionLocal()
    try:
        existing_ids = {c.id for c in db.query(Collector).all()}

        created = 0
        for c in COLLECTOR_DEFS:
            if c["id"] in existing_ids:
                continue
            db.add(
                Collector(
                    id=c["id"],
                    name=c["name"],
                    brightdata_collector_id=config.BRIGHTDATA_COLLECTORS[c["id"]],
                    site_url=config.SITE_URLS[c["id"]],
                )
            )
            created += 1

        db.commit()
        total = len(existing_ids) + created
        print(f"Seeded {created} new collector(s). Total collectors in DB: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
