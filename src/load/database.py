import functools
import os
import re

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_DIR, DATABASE_URL

os.makedirs(DATABASE_DIR, exist_ok=True)


@functools.lru_cache(maxsize=1024)
def _compile_phrase_regex(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def sqlite_phrase_match(text_lemmas: str | None, pattern: str | None) -> bool:
    """Check if text_lemmas matches the compiled phrase regex pattern.

    Known limitation: text_lemmas has no punctuation, so a phrase can rarely
    match across a sentence boundary.
    """
    if not text_lemmas or not pattern:
        return False
    return bool(_compile_phrase_regex(pattern).search(text_lemmas))


@event.listens_for(Engine, "connect")
def _register_sqlite_functions(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, "create_function"):
        dbapi_connection.create_function("phrase_match", 2, sqlite_phrase_match, deterministic=True)


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
