"""Database indexes and redundant index cleanup.

Indexes stay outside migrations on purpose: build_full_database creates them
after bulk loading data for speed. create_indexes() is idempotent, with
INDEXES and REDUNDANT_INDEXES acting as the single source of truth for all
database indexes.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.load.database import engine

REDUNDANT_INDEXES = [
    "DROP INDEX IF EXISTS idx_lemmas_lemma",
    "DROP INDEX IF EXISTS idx_speech_terms_lemma_id",
    "DROP INDEX IF EXISTS idx_speech_terms_speech_id",
    "DROP INDEX IF EXISTS idx_speech_terms_speech_lemma",
    "DROP INDEX IF EXISTS idx_speeches_speaker",
    "DROP INDEX IF EXISTS ix_speeches_speaker_uuid",
    "DROP INDEX IF EXISTS ix_speeches_external_id",
    "DROP INDEX IF EXISTS ix_speeches_speech_key",
    "DROP INDEX IF EXISTS ix_speech_aliases_alias_external_id",
    "DROP INDEX IF EXISTS ix_speech_aliases_speech_id",
    "DROP INDEX IF EXISTS ix_persons_full_name",
    "DROP INDEX IF EXISTS ix_attendance_member_uuid",
    "DROP INDEX IF EXISTS idx_votes_voting_uuid",
    "DROP INDEX IF EXISTS ix_votes_voting_uuid",
    "DROP INDEX IF EXISTS ix_votings_date",
    "DROP INDEX IF EXISTS ix_votings_sitting_date",
    "DROP INDEX IF EXISTS ix_votings_related_document_uuid",
    "DROP INDEX IF EXISTS ix_votes_member_uuid",
    "DROP INDEX IF EXISTS ix_agenda_items_draft_uuid",
    "DROP INDEX IF EXISTS ix_agenda_items_source_file_steno_title",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_speech_terms_lemma_speech ON speech_terms(lemma_id, speech_id)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_date ON speeches(date)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_speaker_faction ON speeches(speaker, speaker_faction)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_faction ON speeches(speaker_faction)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_source_file ON speeches(source_file)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_speaker_uuid ON speeches(speaker_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_ems_id ON speeches(ems_id)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_external_id ON speeches(external_id)",
    "CREATE INDEX IF NOT EXISTS idx_speeches_speech_key ON speeches(speech_key)",
    "CREATE INDEX IF NOT EXISTS idx_speech_aliases_alias_id ON speech_aliases(alias_external_id)",
    "CREATE INDEX IF NOT EXISTS idx_persons_full_name ON persons(full_name)",
    "CREATE INDEX IF NOT EXISTS idx_attendance_member_uuid ON attendance(member_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_votings_date ON votings(date)",
    "CREATE INDEX IF NOT EXISTS idx_votings_sitting_date ON votings(sitting_date)",
    "CREATE INDEX IF NOT EXISTS idx_votings_doc_uuid ON votings(related_document_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_votes_member_uuid ON votes(member_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_agenda_items_draft_uuid ON agenda_items(draft_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_agenda_items_source_file_steno_title ON agenda_items(source_file, steno_title)",
]


def create_indexes(target_engine: Engine | None = None) -> None:
    """Create SQLite database indexes for fast keyword search and speaker lookups."""
    eng = target_engine or engine
    with eng.connect() as conn:
        for drop_sql in REDUNDANT_INDEXES:
            conn.execute(text(drop_sql))
        for index in INDEXES:
            conn.execute(text(index))
        conn.commit()
