import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="cooking-profile-tests-"))
TEST_DATABASE = TEST_ROOT / "database.db"
TEST_UPLOADS = TEST_ROOT / "uploads"
TEST_SECRET = "test-secret-that-is-long-enough-for-hs256"

os.environ["DATABASE_PATH"] = str(TEST_DATABASE)
os.environ["UPLOAD_DIR"] = str(TEST_UPLOADS)
os.environ["JWT_SECRET_KEY"] = TEST_SECRET

from database import get_db, init_db  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_test_state():
    if TEST_DATABASE.exists():
        TEST_DATABASE.unlink()
    if TEST_UPLOADS.exists():
        shutil.rmtree(TEST_UPLOADS)
    TEST_UPLOADS.mkdir(parents=True, exist_ok=True)

    init_db()
    connection = get_db()
    try:
        connection.execute(
            """
            INSERT INTO users (
                id, username, email, phone_number, password_hash,
                full_name, avatar_url, bio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "panda",
                "panda@example.com",
                "0901234567",
                "must-never-be-returned",
                "Panda Bếp",
                None,
                "Yêu các món Việt",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def access_token():
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "1",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def authorization(access_token):
    return {"Authorization": f"Bearer {access_token}"}
