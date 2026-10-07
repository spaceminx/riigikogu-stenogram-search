import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Create an isolated temporary directory for test database and processed files
_temp_dir = tempfile.mkdtemp(prefix="riigikogu_test_")
_temp_path = Path(_temp_dir)
_test_db = str(_temp_path / "test_riigikogu.sqlite")
_test_processed = str(_temp_path / "processed")
os.makedirs(_test_processed, exist_ok=True)

# Set environment variables before any application module is imported
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"
os.environ["DATABASE_PATH"] = _test_db
os.environ["OUTPUT_DIR_PROCESSED"] = _test_processed


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_environment():
    """Ensure temporary test directory is cleanly removed after the test session."""
    yield
    try:
        shutil.rmtree(_temp_dir, ignore_errors=True)
    except Exception:
        pass
