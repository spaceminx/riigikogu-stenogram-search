from sqlalchemy import text
from src.load.database import engine

INDEXES = [
        "CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma)",
        "CREATE INDEX IF NOT EXISTS idx_speech_terms_lemma_id ON speech_terms(lemma_id)",
        "CREATE INDEX IF NOT EXISTS idx_speech_terms_speech_id ON speech_terms(speech_id)",
        "CREATE INDEX IF NOT EXISTS idx_speech_terms_lemma_speech ON speech_terms(lemma_id, speech_id)",
        "CREATE INDEX IF NOT EXISTS idx_speech_terms_speech_lemma ON speech_terms(speech_id, lemma_id)",
        "CREATE INDEX IF NOT EXISTS idx_speeches_date ON speeches(date)",
        "CREATE INDEX IF NOT EXISTS idx_speeches_speaker ON speeches(speaker)",
    ]

def create_indexes():
    with engine.connect() as conn:
        for index in INDEXES:
            conn.execute(text(index))
        conn.commit()