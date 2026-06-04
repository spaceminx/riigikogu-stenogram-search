import json
from pathlib import Path
from sqlalchemy.exc import IntegrityError

from config import OUTPUT_DIR_PROCESSED
from src.load.database import engine, SessionLocal
from src.load.models import Base, Speech


def create_tables():
    Base.metadata.create_all(bind=engine)


def load_jsonl_to_database():

    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    session = SessionLocal()

    for input_file in processed_dir.glob("*.jsonl"):
        print(f"Processing {input_file.name}")
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)

                speech = Speech(
                    date=data["date"],
                    time=data["time"],
                    source_file=data["source_file"],
                    source_url=data["source_url"],
                    speaker=data["speaker"],
                    text=data["text"],
                )

                session.add(speech)

                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()

    session.close()