"""Tests for database schema migrations runner."""

import concurrent.futures
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from src.load import migrations
from src.load.migrations import apply_migrations
from src.load.models import Base


def test_fresh_db_all_tables_exist_and_migration_recorded(tmp_path):
    """Fresh DB: all declared tables exist, schema_migrations contains 0001."""
    db_path = str(tmp_path / "fresh.sqlite")
    eng = create_engine(f"sqlite:///{db_path}")

    applied = apply_migrations(eng)
    assert applied == ["0001_baseline", "0002_agenda_items"]

    with eng.connect() as conn:
        tables = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        for expected_table in Base.metadata.tables:
            assert expected_table in tables
        assert "schema_migrations" in tables

        rows = conn.execute(
            text("SELECT version, name FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == ("0001", "baseline")
        assert rows[1] == ("0002", "agenda_items")


def test_old_shape_db_migrates_columns_and_preserves_data(tmp_path):
    """Old-shape DB: missing columns are added, 0001 and 0002 are recorded, and existing rows are intact."""
    db_path = str(tmp_path / "old_shape.sqlite")
    raw_conn = sqlite3.connect(db_path)
    # Create speeches without speech_key, duration_seconds, speaker_uuid, status
    raw_conn.execute(
        """
        CREATE TABLE speeches (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_url TEXT NOT NULL,
            speaker TEXT NOT NULL,
            speaker_role TEXT,
            speaker_faction TEXT,
            text TEXT NOT NULL,
            text_lemmas TEXT
        );
        """
    )
    raw_conn.execute(
        "INSERT INTO speeches (id, date, time, source_file, source_url, speaker, text) "
        "VALUES (1, '2023-01-01', '10:00', 'f1.json', 'http://1', 'Kõneleja 1', 'Sisu 1'), "
        "(2, '2023-01-02', '11:00', 'f2.json', 'http://2', 'Kõneleja 2', 'Sisu 2');"
    )

    # Create votings with initial schema (without sitting_date, sitting_datetime)
    raw_conn.execute(
        """
        CREATE TABLE votings (
            uuid TEXT PRIMARY KEY,
            voting_number INTEGER,
            type TEXT,
            description TEXT,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            membership INTEGER,
            sitting_uuid TEXT,
            sitting_title TEXT,
            related_document_uuid TEXT,
            related_document_reference TEXT,
            related_document_title TEXT,
            related_document_type TEXT,
            chairman_uuid TEXT,
            present INTEGER,
            absent INTEGER,
            in_favor INTEGER,
            against INTEGER,
            neutral INTEGER,
            abstained INTEGER
        );
        """
    )
    raw_conn.execute("INSERT INTO votings (uuid, date) VALUES ('v-uuid-1', '2023-01-01');")

    # Create attendance with initial schema (without member_uuid)
    raw_conn.execute(
        """
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY,
            session_date TEXT NOT NULL,
            voting_uuid TEXT NOT NULL,
            member_name TEXT NOT NULL,
            faction TEXT,
            status TEXT NOT NULL
        );
        """
    )
    raw_conn.execute(
        "INSERT INTO attendance (id, session_date, voting_uuid, member_name, faction, status) "
        "VALUES (10, '2023-01-01', 'v-uuid-1', 'Jaan Tamm', 'RE', 'KOHAL');"
    )
    raw_conn.commit()
    raw_conn.close()

    eng = create_engine(f"sqlite:///{db_path}")
    applied = apply_migrations(eng)
    assert applied == ["0001_baseline", "0002_agenda_items"]

    with eng.connect() as conn:
        # Check speeches columns and rows
        sp_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(speeches)"))}
        assert "speech_key" in sp_cols
        assert "duration_seconds" in sp_cols
        assert "speaker_uuid" in sp_cols
        assert "status" in sp_cols
        sp_count = conn.execute(text("SELECT count(*) FROM speeches")).scalar()
        assert sp_count == 2
        sp_row1 = conn.execute(text("SELECT speaker, text FROM speeches WHERE id=1")).fetchone()
        assert sp_row1 == ("Kõneleja 1", "Sisu 1")

        # Check votings columns and rows
        v_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(votings)"))}
        assert "sitting_date" in v_cols
        assert "sitting_datetime" in v_cols
        v_count = conn.execute(text("SELECT count(*) FROM votings")).scalar()
        assert v_count == 1

        # Check attendance columns and rows
        att_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(attendance)"))}
        assert "member_uuid" in att_cols
        att_count = conn.execute(text("SELECT count(*) FROM attendance")).scalar()
        assert att_count == 1

        # Check agenda_items table exists
        tables = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        assert "agenda_items" in tables

        # Check schema_migrations
        mig_rows = conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert len(mig_rows) == 2
        assert [r[0] for r in mig_rows] == ["0001", "0002"]


def test_second_apply_migrations_returns_empty_and_no_change(tmp_path):
    """Subsequent apply_migrations calls return [] and leave state unchanged."""
    db_path = str(tmp_path / "idempotent.sqlite")
    eng = create_engine(f"sqlite:///{db_path}")

    first_run = apply_migrations(eng)
    assert first_run == ["0001_baseline", "0002_agenda_items"]

    second_run = apply_migrations(eng)
    assert second_run == []

    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "0001"
        assert rows[1][0] == "0002"


def test_concurrent_apply_migrations_threads(tmp_path):
    """Two engines calling apply_migrations simultaneously record migrations exactly once without errors."""
    db_path = str(tmp_path / "threads.sqlite")
    eng1 = create_engine(f"sqlite:///{db_path}")
    eng2 = create_engine(f"sqlite:///{db_path}")

    def run_mig(eng):
        return apply_migrations(eng)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_mig, eng1)
        f2 = executor.submit(run_mig, eng2)
        res1 = f1.result()
        res2 = f2.result()

    expected = ["0001_baseline", "0002_agenda_items"]
    assert (res1 == expected and res2 == []) or (res2 == expected and res1 == [])

    with eng1.connect() as conn:
        rows = conn.execute(
            text("SELECT version, name FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == ("0001", "baseline")
        assert rows[1] == ("0002", "agenda_items")


def test_failed_migration_verify_rolls_back_and_does_not_record(tmp_path, monkeypatch):
    """A test-only migration 0003 whose verify() fails raises, is not recorded, and schema changes roll back."""
    db_path = str(tmp_path / "failing_mig.sqlite")
    eng = create_engine(f"sqlite:///{db_path}")

    # Baseline & 0002 succeed first
    apply_migrations(eng)

    def _up_0003_fail(conn):
        conn.execute(text("CREATE TABLE test_table_failed (id INTEGER PRIMARY KEY);"))

    def _verify_0003_fail(conn):
        raise RuntimeError(
            "Migration verification failed: missing column 'test_table_failed.required_col'"
        )

    test_migrations = list(migrations.MIGRATIONS) + [
        ("0003", "failing_migration", _up_0003_fail, _verify_0003_fail)
    ]
    monkeypatch.setattr(migrations, "MIGRATIONS", test_migrations)

    with pytest.raises(RuntimeError, match="missing column 'test_table_failed.required_col'"):
        apply_migrations(eng)

    with eng.connect() as conn:
        tables = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        # Table must be rolled back
        assert "test_table_failed" not in tables

        # schema_migrations must only have 0001 and 0002
        rows = conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert [r[0] for r in rows] == ["0001", "0002"]


def test_succeeding_test_migration_0003(tmp_path, monkeypatch):
    """A test-only migration 0003 that succeeds is applied once and recorded."""
    db_path = str(tmp_path / "success_mig.sqlite")
    eng = create_engine(f"sqlite:///{db_path}")

    # Baseline & 0002 succeed
    apply_migrations(eng)

    def _up_0003_ok(conn):
        conn.execute(text("CREATE TABLE test_table_ok (id INTEGER PRIMARY KEY, title TEXT);"))

    def _verify_0003_ok(conn):
        tables = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        if "test_table_ok" not in tables:
            raise RuntimeError("Missing table 'test_table_ok'")

    test_migrations = list(migrations.MIGRATIONS) + [
        ("0003", "ok_migration", _up_0003_ok, _verify_0003_ok)
    ]
    monkeypatch.setattr(migrations, "MIGRATIONS", test_migrations)

    applied = apply_migrations(eng)
    assert applied == ["0003_ok_migration"]

    with eng.connect() as conn:
        tables = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        assert "test_table_ok" in tables

        rows = conn.execute(
            text("SELECT version, name FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert len(rows) == 3
        assert rows[0] == ("0001", "baseline")
        assert rows[1] == ("0002", "agenda_items")
        assert rows[2] == ("0003", "ok_migration")

    # Second call applies nothing
    second = apply_migrations(eng)
    assert second == []


def test_apply_migrations_does_not_call_create_indexes(tmp_path, monkeypatch):
    """build_full_database path creates indexes at the end: apply_migrations must not call create_indexes."""
    from src.load import indexes

    called = []

    def mock_create_indexes(target_engine=None):
        called.append(True)

    monkeypatch.setattr(indexes, "create_indexes", mock_create_indexes)

    db_path = str(tmp_path / "no_indexes.sqlite")
    eng = create_engine(f"sqlite:///{db_path}")

    apply_migrations(eng)
    assert len(called) == 0

    with eng.connect() as conn:
        index_names = {
            r[0]
            for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            if r[0] is not None
        }
        # Fast-search indexes like idx_speeches_speaker_faction must NOT exist yet
        assert "idx_speeches_speaker_faction" not in index_names
        assert "idx_speech_terms_lemma_speech" not in index_names


def test_migration_0002_applies_on_db_with_0001_already_applied(tmp_path):
    """A database that already ran 0001 gets upgraded with migration 0002."""
    db_path = str(tmp_path / "upgraded.sqlite")
    eng = create_engine(f"sqlite:///{db_path}")

    # Set up DB with only 0001 recorded
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT, applied_at TEXT);"
            )
        )
        conn.execute(
            text(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES ('0001', 'baseline', '2026-10-18T10:00:00Z');"
            )
        )
        conn.commit()

    applied = apply_migrations(eng)
    assert applied == ["0002_agenda_items"]

    with eng.connect() as conn:
        tables = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        assert "agenda_items" in tables

        rows = conn.execute(
            text("SELECT version, name FROM schema_migrations ORDER BY version")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == ("0001", "baseline")
        assert rows[1] == ("0002", "agenda_items")
