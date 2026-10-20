"""Database schema migrations runner for SQLite.

RULE: Never edit an applied migration; always add a new one with an incremented version.

Migrations are defined as an ordered list of tuples:
    (version, name, up(conn), verify(conn))

apply_migrations(engine=None) runs unapplied migrations inside a BEGIN IMMEDIATE
transaction so concurrent executions (e.g. API startup and database sync) cannot
conflict.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.load.database import engine as default_engine
from src.load.models import Base


def _up_0001_baseline(conn: Connection) -> None:
    from src.load.loader import _ensure_schema

    Base.metadata.create_all(bind=conn)
    _ensure_schema(conn)

    # Migrate optional columns if speeches table already exists
    existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(speeches)"))}
    if existing_cols:
        cols_to_check = [
            ("agenda_title", "TEXT"),
            ("video_url", "TEXT"),
            ("status", "TEXT"),
            ("speaker_uuid", "TEXT"),
            ("ems_id", "TEXT"),
            ("speech_type", "TEXT"),
            ("external_id", "INTEGER"),
            ("start_time", "TEXT"),
            ("end_time", "TEXT"),
            ("duration_seconds", "INTEGER"),
            ("speech_key", "TEXT"),
        ]
        for col_name, col_type in cols_to_check:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE speeches ADD COLUMN {col_name} {col_type};"))


def _verify_0001_baseline(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    for table_name, table in Base.metadata.tables.items():
        if table_name in {"agenda_items", "lemma_links", "attendance_checks"}:
            continue
        if table_name not in tables:
            raise RuntimeError(f"Migration verification failed: missing table '{table_name}'")
        existing_cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table_name})"))}
        for col in table.columns:
            if table_name == "lemmas" and col.name in ("df", "pos"):
                continue
            if col.name not in existing_cols:
                raise RuntimeError(
                    f"Migration verification failed: missing column '{table_name}.{col.name}'"
                )


def _up_0002_agenda_items(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS agenda_items (
                agenda_item_uuid TEXT PRIMARY KEY,
                sitting_uuid TEXT,
                sitting_date TEXT,
                sitting_datetime TEXT,
                source_file TEXT,
                "order" INTEGER,
                steno_title TEXT,
                api_title TEXT,
                document_type TEXT,
                type_code TEXT,
                stage TEXT,
                decision_code TEXT,
                decision_value TEXT,
                draft_uuid TEXT,
                draft_mark TEXT,
                draft_title TEXT,
                voting_uuids TEXT
            );
            """
        )
    )


def _verify_0002_agenda_items(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "agenda_items" not in tables:
        raise RuntimeError("Migration verification failed: missing table 'agenda_items'")

    existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(agenda_items)"))}
    expected_cols = [
        "agenda_item_uuid",
        "sitting_uuid",
        "sitting_date",
        "sitting_datetime",
        "source_file",
        "order",
        "steno_title",
        "api_title",
        "document_type",
        "type_code",
        "stage",
        "decision_code",
        "decision_value",
        "draft_uuid",
        "draft_mark",
        "draft_title",
        "voting_uuids",
    ]
    for col in expected_cols:
        if col not in existing_cols:
            raise RuntimeError(
                f"Migration verification failed: missing column 'agenda_items.{col}'"
            )


def _up_0003_agenda_match_method(conn: Connection) -> None:
    existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(agenda_items)"))}
    if "match_method" not in existing_cols:
        conn.execute(text("ALTER TABLE agenda_items ADD COLUMN match_method TEXT;"))


def _verify_0003_agenda_match_method(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "agenda_items" not in tables:
        raise RuntimeError("Migration verification failed: missing table 'agenda_items'")
    existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(agenda_items)"))}
    if "match_method" not in existing_cols:
        raise RuntimeError(
            "Migration verification failed: missing column 'agenda_items.match_method'"
        )


def _up_0004_lemma_links(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS lemma_links (
                lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
                target_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
                kind TEXT NOT NULL,
                PRIMARY KEY (lemma_id, target_lemma_id, kind)
            );
            """
        )
    )


def _verify_0004_lemma_links(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "lemma_links" not in tables:
        raise RuntimeError("Migration verification failed: missing table 'lemma_links'")
    existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(lemma_links)"))}
    expected_cols = ["lemma_id", "target_lemma_id", "kind"]
    for col in expected_cols:
        if col not in existing_cols:
            raise RuntimeError(f"Migration verification failed: missing column 'lemma_links.{col}'")


def _up_0005_lemma_df(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "lemmas" not in tables:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS lemmas (
                    id INTEGER PRIMARY KEY,
                    lemma TEXT UNIQUE NOT NULL,
                    df INTEGER
                );
                """
            )
        )
    else:
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(lemmas)"))}
        if "df" not in existing_cols:
            conn.execute(text("ALTER TABLE lemmas ADD COLUMN df INTEGER;"))


def _verify_0005_lemma_df(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "lemmas" in tables:
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(lemmas)"))}
        if "df" not in existing_cols:
            raise RuntimeError("Migration verification failed: missing column 'lemmas.df'")


def _up_0006_lemma_pos(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "lemmas" not in tables:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS lemmas (
                    id INTEGER PRIMARY KEY,
                    lemma TEXT UNIQUE NOT NULL,
                    df INTEGER,
                    pos TEXT
                );
                """
            )
        )
    else:
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(lemmas)"))}
        if "pos" not in existing_cols:
            conn.execute(text("ALTER TABLE lemmas ADD COLUMN pos TEXT;"))


def _verify_0006_lemma_pos(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "lemmas" in tables:
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(lemmas)"))}
        if "pos" not in existing_cols:
            raise RuntimeError("Migration verification failed: missing column 'lemmas.pos'")


def _up_0007_attendance_checks(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS attendance_checks (
                voting_uuid TEXT PRIMARY KEY,
                sitting_uuid TEXT,
                sitting_title TEXT,
                sitting_datetime TEXT,
                sitting_type TEXT NOT NULL
            );
            """
        )
    )


def _verify_0007_attendance_checks(conn: Connection) -> None:
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "attendance_checks" not in tables:
        raise RuntimeError("Migration verification failed: missing table 'attendance_checks'")
    existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(attendance_checks)"))}
    for col in [
        "voting_uuid",
        "sitting_uuid",
        "sitting_title",
        "sitting_datetime",
        "sitting_type",
    ]:
        if col not in existing_cols:
            raise RuntimeError(
                f"Migration verification failed: missing column 'attendance_checks.{col}'"
            )


MigrationTuple = tuple[str, str, Callable[[Connection], None], Callable[[Connection], None]]

MIGRATIONS: list[MigrationTuple] = [
    ("0001", "baseline", _up_0001_baseline, _verify_0001_baseline),
    ("0002", "agenda_items", _up_0002_agenda_items, _verify_0002_agenda_items),
    ("0003", "agenda_match_method", _up_0003_agenda_match_method, _verify_0003_agenda_match_method),
    ("0004", "lemma_links", _up_0004_lemma_links, _verify_0004_lemma_links),
    ("0005", "lemma_df", _up_0005_lemma_df, _verify_0005_lemma_df),
    ("0006", "lemma_pos", _up_0006_lemma_pos, _verify_0006_lemma_pos),
    ("0007", "attendance_checks", _up_0007_attendance_checks, _verify_0007_attendance_checks),
]


def apply_migrations(engine: Engine | None = None) -> list[str]:
    """Apply all pending migrations in order, recording each in schema_migrations."""
    eng = engine or default_engine
    applied: list[str] = []

    # 1. Create schema_migrations table if missing
    with eng.connect() as conn:
        conn.execute(text("PRAGMA busy_timeout = 30000;"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                """
            )
        )
        conn.commit()

    # 2. Iterate through MIGRATIONS
    for version, name, up_fn, verify_fn in MIGRATIONS:
        # Check if already applied outside transaction first (quick skip)
        with eng.connect() as conn:
            conn.execute(text("PRAGMA busy_timeout = 30000;"))
            already = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE version = :v"),
                {"v": version},
            ).fetchone()
            if already:
                continue

        # Open transaction with BEGIN IMMEDIATE
        with eng.connect() as conn:
            conn.execute(text("PRAGMA busy_timeout = 30000;"))
            conn.execute(text("BEGIN IMMEDIATE"))
            try:
                # Re-check inside IMMEDIATE transaction to avoid race condition
                already = conn.execute(
                    text("SELECT 1 FROM schema_migrations WHERE version = :v"),
                    {"v": version},
                ).fetchone()
                if already:
                    conn.rollback()
                    continue

                up_fn(conn)
                verify_fn(conn)

                now_utc = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (:version, :name, :applied_at)"
                    ),
                    {"version": version, "name": name, "applied_at": now_utc},
                )
                conn.commit()
                version_str = f"{version}_{name}" if name else version
                applied.append(version_str)
            except Exception:
                conn.rollback()
                raise

    return applied
