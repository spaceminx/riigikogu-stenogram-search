from sqlalchemy import text

from src.load.database import engine

REDUNDANT_INDEXES = [
    "DROP INDEX IF EXISTS idx_lemmas_lemma",
    "DROP INDEX IF EXISTS idx_speech_terms_lemma_id",
    "DROP INDEX IF EXISTS idx_speech_terms_speech_id",
    "DROP INDEX IF EXISTS idx_speech_terms_speech_lemma",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_speech_terms_lemma_speech ON speech_terms(lemma_id, speech_id)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_date ON speeches(date)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_speaker ON speeches(speaker)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_faction ON speeches(speaker_faction)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_source_file ON speeches(source_file)",
]


def create_indexes() -> None:
    """Create SQLite database indexes for fast keyword search and speaker lookups."""
    with engine.connect() as conn:
        for drop_sql in REDUNDANT_INDEXES:
            conn.execute(text(drop_sql))
        for index in INDEXES:
            conn.execute(text(index))
        conn.commit()
