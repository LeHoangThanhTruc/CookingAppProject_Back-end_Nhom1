from datetime import datetime, timedelta, timezone
from io import BytesIO

import jwt
from PIL import Image

from conftest import TEST_SECRET, TEST_UPLOADS


def make_image(image_format="PNG", color=(0, 135, 90)):
    output = BytesIO()
    Image.new("RGB", (32, 32), color=color).save(output, format=image_format)
    return output.getvalue()


def test_get_profile_requires_bearer_token(client):
    response = client.get("/api/profile/me")

    assert response.status_code == 401


def test_get_profile_rejects_expired_token(client):
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "1", "exp": now - timedelta(seconds=1)},
        TEST_SECRET,
        algorithm="HS256",
    )

    response = client.get(
        "/api/profile/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_get_profile_returns_only_safe_profile_fields(client, authorization):
    response = client.get("/api/profile/me", headers=authorization)

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "username": "panda",
        "email": "panda@example.com",
        "full_name": "Panda Bếp",
        "phone_number": "0901234567",
        "bio": "Yêu các món Việt",
        "avatar_url": None,
    }
    assert "password_hash" not in response.text


def test_get_profile_returns_not_found_for_unknown_subject(client):
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "999", "exp": now + timedelta(minutes=5)},
        TEST_SECRET,
        algorithm="HS256",
    )

    response = client.get(
        "/api/profile/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_patch_profile_updates_only_supplied_fields(client, authorization):
    response = client.patch(
        "/api/profile/me",
        headers=authorization,
        json={
            "full_name": "  Bếp Nhà Panda  ",
            "phone_number": "+84901234567",
            "bio": "  Món Việt mỗi ngày  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Bếp Nhà Panda"
    assert response.json()["phone_number"] == "+84901234567"
    assert response.json()["bio"] == "Món Việt mỗi ngày"
    assert response.json()["username"] == "panda"
    assert response.json()["email"] == "panda@example.com"

    persisted = client.get("/api/profile/me", headers=authorization).json()
    assert persisted == response.json()


def test_patch_profile_can_clear_optional_phone_and_bio(client, authorization):
    response = client.patch(
        "/api/profile/me",
        headers=authorization,
        json={"phone_number": "  ", "bio": None},
    )

    assert response.status_code == 200
    assert response.json()["phone_number"] is None
    assert response.json()["bio"] is None


def test_patch_profile_rejects_invalid_or_unowned_fields(client, authorization):
    invalid_name = client.patch(
        "/api/profile/me",
        headers=authorization,
        json={"full_name": "   "},
    )
    invalid_phone = client.patch(
        "/api/profile/me",
        headers=authorization,
        json={"phone_number": "12-34"},
    )
    extra_field = client.patch(
        "/api/profile/me",
        headers=authorization,
        json={"email": "other@example.com"},
    )
    empty_patch = client.patch(
        "/api/profile/me",
        headers=authorization,
        json={},
    )

    assert invalid_name.status_code == 422
    assert invalid_phone.status_code == 422
    assert extra_field.status_code == 422
    assert empty_patch.status_code == 422


def test_upload_avatar_persists_and_serves_verified_image(client, authorization):
    response = client.post(
        "/api/profile/me/avatar",
        headers=authorization,
        files={"file": ("avatar.png", make_image(), "image/png")},
    )

    assert response.status_code == 200
    avatar_url = response.json()["avatar_url"]
    assert avatar_url.startswith("/uploads/avatars/")
    stored_files = list((TEST_UPLOADS / "avatars").iterdir())
    assert len(stored_files) == 1
    assert client.get(avatar_url).status_code == 200


def test_replacing_avatar_removes_previous_local_file(client, authorization):
    first = client.post(
        "/api/profile/me/avatar",
        headers=authorization,
        files={"file": ("first.png", make_image(), "image/png")},
    )
    first_path = TEST_UPLOADS / first.json()["avatar_url"].removeprefix("/uploads/")
    assert first_path.exists()

    second = client.post(
        "/api/profile/me/avatar",
        headers=authorization,
        files={"file": ("second.jpg", make_image("JPEG"), "image/jpeg")},
    )

    assert second.status_code == 200
    assert not first_path.exists()
    assert len(list((TEST_UPLOADS / "avatars").iterdir())) == 1


def test_upload_avatar_rejects_fake_and_oversized_images(client, authorization):
    fake_image = client.post(
        "/api/profile/me/avatar",
        headers=authorization,
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    oversized = client.post(
        "/api/profile/me/avatar",
        headers=authorization,
        files={"file": ("large.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")},
    )

    assert fake_image.status_code == 415
    assert oversized.status_code == 413
    assert not list((TEST_UPLOADS / "avatars").glob("*"))
