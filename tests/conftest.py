import os
import tempfile

# Set before the first `from app...` import anywhere in the test session, so
# the module-level production engine in app.database (created at import time
# for the app's own startup create_all) points at a throwaway file instead of
# the repo's ./spend.db, and Settings() doesn't fail-fast for a missing
# API_KEY during test collection. Actual test queries never use this engine —
# each fixture below wires its own per-test engine via dependency_overrides.
os.environ.setdefault(
    "DB_PATH", os.path.join(tempfile.mkdtemp(prefix="spend-tracker-default-"), "unused.db")
)
API_KEY = "test-api-key"
os.environ.setdefault("API_KEY", API_KEY)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


def _wire_test_db(tmp_path):
    """Point the app's get_db dependency at a fresh, isolated SQLite file."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), engine


@pytest.fixture()
def client(tmp_path):
    """Authenticated client — the default for tests that aren't about auth itself."""
    test_client, engine = _wire_test_db(tmp_path)
    test_client.headers.update({"X-API-Key": API_KEY})
    with test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def unauthenticated_client(tmp_path):
    """Same DB wiring as `client`, but with no API key header — for auth tests."""
    test_client, engine = _wire_test_db(tmp_path)
    with test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
