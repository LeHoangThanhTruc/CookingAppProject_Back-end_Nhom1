from datetime import datetime, timedelta, timezone

import jwt
import pytest

from conftest import TEST_SECRET
from database import get_db
from features import auth as auth_module


def get_user_row(**conditions):
    column, value = next(iter(conditions.items()))
    connection = get_db()
    try:
        return connection.execute(
            f"SELECT * FROM users WHERE {column} = ?", (value,)
        ).fetchone()
    finally:
        connection.close()


def register_payload(**overrides):
    payload = {
        "username": "newchef",
        "email": "newchef@example.com",
        "password": "matkhau123",
        "full_name": "Đầu Bếp Mới",
        "phone_number": "0912345678",
    }
    payload.update(overrides)
    return payload


# ---------- Register ----------

def test_register_creates_user_with_hashed_password(client):
    response = client.post("/api/auth/register", json=register_payload())

    assert response.status_code == 201
    user = response.json()["user"]
    assert user["username"] == "newchef"
    assert user["email"] == "newchef@example.com"
    assert user["auth_provider"] == "LOCAL"
    assert "password" not in response.text
    assert "password_hash" not in response.text

    row = get_user_row(username="newchef")
    assert row["password_hash"].startswith("pbkdf2_sha256$")
    assert "matkhau123" not in row["password_hash"]


def test_register_without_username_generates_one_from_email(client):
    payload = register_payload()
    del payload["username"]

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 201
    username = response.json()["user"]["username"]
    assert username.startswith("newchef_")
    login = client.post(
        "/api/auth/login",
        json={"email": "newchef@example.com", "password": "matkhau123"},
    )
    assert login.status_code == 200


def test_register_rejects_duplicate_email_and_username(client):
    duplicate_email = client.post(
        "/api/auth/register",
        json=register_payload(email="PANDA@example.com"),
    )
    duplicate_username = client.post(
        "/api/auth/register",
        json=register_payload(username="panda"),
    )

    assert duplicate_email.status_code == 409
    assert duplicate_username.status_code == 409


def test_register_rejects_invalid_input(client):
    bad_email = client.post("/api/auth/register", json=register_payload(email="khong-phai-email"))
    short_username = client.post("/api/auth/register", json=register_payload(username="ab"))
    bad_username = client.post("/api/auth/register", json=register_payload(username="co dau cach"))
    short_password = client.post("/api/auth/register", json=register_payload(password="1234567"))

    assert bad_email.status_code == 400
    assert short_username.status_code == 400
    assert bad_username.status_code == 400
    assert short_password.status_code == 400
    assert get_user_row(username="newchef") is None


# ---------- Login ----------

def test_login_with_email_returns_valid_token_and_updates_last_login(client):
    client.post("/api/auth/register", json=register_payload())

    response = client.post(
        "/api/auth/login",
        json={"email": "newchef@example.com", "password": "matkhau123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "newchef"
    assert "password_hash" not in response.text

    payload = jwt.decode(body["access_token"], TEST_SECRET, algorithms=["HS256"])
    assert payload["sub"] == str(body["user"]["id"])
    assert get_user_row(username="newchef")["last_login_at"] is not None


def test_login_with_username_works(client):
    client.post("/api/auth/register", json=register_payload())

    response = client.post(
        "/api/auth/login",
        json={"email": "newchef", "password": "matkhau123"},
    )

    assert response.status_code == 200


def test_login_token_can_access_protected_profile_api(client):
    client.post("/api/auth/register", json=register_payload())
    token = client.post(
        "/api/auth/login",
        json={"email": "newchef@example.com", "password": "matkhau123"},
    ).json()["access_token"]

    response = client.get(
        "/api/profile/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "newchef"


def test_login_rejects_wrong_password_unknown_user_and_invalid_stored_hash(client):
    client.post("/api/auth/register", json=register_payload())

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "newchef@example.com", "password": "sai-mat-khau"},
    )
    unknown_user = client.post(
        "/api/auth/login",
        json={"email": "khongco@example.com", "password": "matkhau123"},
    )
    # User có sẵn trong conftest có password_hash không đúng định dạng
    invalid_stored_hash = client.post(
        "/api/auth/login",
        json={"email": "panda@example.com", "password": "must-never-be-returned"},
    )

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert invalid_stored_hash.status_code == 401
    assert wrong_password.json() == unknown_user.json()


# ---------- OAuth login (Google / Facebook) ----------

GOOGLE_INFO = {
    "aud": "web-client-id.apps.googleusercontent.com",
    "iss": "https://accounts.google.com",
    "sub": "google-123",
    "email": "oauth@example.com",
    "email_verified": "true",
    "name": "Người Dùng Google",
    "picture": "https://example.com/avatar.png",
}


def oauth_payload(**overrides):
    payload = {"provider": "GOOGLE", "token": "fake-google-id-token"}
    payload.update(overrides)
    return payload


@pytest.fixture
def google_env(monkeypatch):
    """Giả lập Google trả về thông tin token; test sửa dict trả về để thử các trường hợp."""
    monkeypatch.setenv("GOOGLE_WEB_CLIENT_ID", GOOGLE_INFO["aud"])
    info = dict(GOOGLE_INFO)
    monkeypatch.setattr(auth_module, "_http_get_json", lambda url: dict(info))
    return info


@pytest.fixture
def facebook_env(monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_ID", "fb-app-id")
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "fb-secret")
    state = {
        "debug": {"data": {"is_valid": True, "app_id": "fb-app-id", "user_id": "fb-123"}},
        "me": {
            "id": "fb-123",
            "name": "Người Dùng Facebook",
            "email": "fb@example.com",
            "picture": {"data": {"url": "https://example.com/fb.png"}},
        },
    }
    monkeypatch.setattr(
        auth_module,
        "_http_get_json",
        lambda url: state["debug"] if "debug_token" in url else state["me"],
    )
    return state


def test_google_login_creates_user_once_and_reuses_it(client, google_env):
    first = client.post("/api/auth/oauth-login", json=oauth_payload())
    second = client.post("/api/auth/oauth-login", json=oauth_payload())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
    assert first.json()["user"]["auth_provider"] == "GOOGLE"

    row = get_user_row(email="oauth@example.com")
    assert row["password_hash"] is None
    assert row["provider_id"] == "google-123"
    assert row["full_name"] == "Người Dùng Google"
    assert row["avatar_url"] == "https://example.com/avatar.png"
    assert row["last_login_at"] is not None


def test_oauth_login_rejects_unsupported_provider_and_existing_email(client, google_env):
    bad_provider = client.post("/api/auth/oauth-login", json=oauth_payload(provider="TWITTER"))
    # panda@example.com đã được đăng ký bằng LOCAL trong conftest
    google_env["email"] = "panda@example.com"
    existing_email = client.post("/api/auth/oauth-login", json=oauth_payload())

    assert bad_provider.status_code == 400
    assert existing_email.status_code == 409


def test_oauth_account_cannot_login_with_password(client, google_env):
    client.post("/api/auth/oauth-login", json=oauth_payload())

    response = client.post(
        "/api/auth/login",
        json={"email": "oauth@example.com", "password": "bat-ky-mat-khau-nao"},
    )

    assert response.status_code == 401


def test_oauth_login_rejects_old_style_payload_without_token(client, google_env):
    response = client.post(
        "/api/auth/oauth-login",
        json={"provider": "GOOGLE", "provider_id": "kẻ-giả-mạo", "email": "panda@example.com"},
    )

    assert response.status_code == 422
    assert get_user_row(provider_id="kẻ-giả-mạo") is None


def test_google_login_needs_server_configuration(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_WEB_CLIENT_ID", raising=False)

    response = client.post("/api/auth/oauth-login", json=oauth_payload())

    assert response.status_code == 503


def test_google_login_rejects_token_for_another_app_or_unverified_email(client, google_env):
    google_env["aud"] = "client-id-cua-app-khac"
    other_app = client.post("/api/auth/oauth-login", json=oauth_payload())

    google_env["aud"] = GOOGLE_INFO["aud"]
    google_env["email_verified"] = "false"
    unverified = client.post("/api/auth/oauth-login", json=oauth_payload())

    assert other_app.status_code == 401
    assert unverified.status_code == 401
    assert get_user_row(email="oauth@example.com") is None


def test_google_login_rejects_token_google_does_not_accept(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_WEB_CLIENT_ID", GOOGLE_INFO["aud"])

    def google_refuses(url):
        raise OSError("Google từ chối token")

    monkeypatch.setattr(auth_module, "_http_get_json", google_refuses)

    response = client.post("/api/auth/oauth-login", json=oauth_payload())

    assert response.status_code == 401


def test_facebook_login_creates_user_with_profile(client, facebook_env):
    response = client.post(
        "/api/auth/oauth-login",
        json=oauth_payload(provider="facebook", token="fake-facebook-token"),
    )

    assert response.status_code == 200
    assert response.json()["user"]["auth_provider"] == "FACEBOOK"
    row = get_user_row(email="fb@example.com")
    assert row["provider_id"] == "fb-123"
    assert row["avatar_url"] == "https://example.com/fb.png"


def test_facebook_login_rejects_invalid_or_foreign_tokens(client, facebook_env):
    facebook_env["debug"] = {"data": {"is_valid": False}}
    invalid = client.post(
        "/api/auth/oauth-login",
        json=oauth_payload(provider="FACEBOOK", token="fake-facebook-token"),
    )

    facebook_env["debug"] = {"data": {"is_valid": True, "app_id": "app-khac", "user_id": "fb-123"}}
    foreign_app = client.post(
        "/api/auth/oauth-login",
        json=oauth_payload(provider="FACEBOOK", token="fake-facebook-token"),
    )

    assert invalid.status_code == 401
    assert foreign_app.status_code == 401
    assert get_user_row(email="fb@example.com") is None


def test_facebook_login_requires_email_and_server_configuration(client, facebook_env, monkeypatch):
    del facebook_env["me"]["email"]
    no_email = client.post(
        "/api/auth/oauth-login",
        json=oauth_payload(provider="FACEBOOK", token="fake-facebook-token"),
    )

    monkeypatch.delenv("FACEBOOK_APP_ID", raising=False)
    monkeypatch.delenv("FACEBOOK_APP_SECRET", raising=False)
    unconfigured = client.post(
        "/api/auth/oauth-login",
        json=oauth_payload(provider="FACEBOOK", token="fake-facebook-token"),
    )

    assert no_email.status_code == 400
    assert unconfigured.status_code == 503


# ---------- Logout ----------

def test_logout_requires_bearer_token(client):
    response = client.post("/api/auth/logout")

    assert response.status_code == 401


def test_logout_updates_last_logout_for_token_owner(client, authorization):
    assert get_user_row(id=1)["last_logout_at"] is None

    response = client.post("/api/auth/logout", headers=authorization)

    assert response.status_code == 200
    assert get_user_row(id=1)["last_logout_at"] is not None


# ---------- Quên mật khẩu / Đặt lại mật khẩu ----------

@pytest.fixture
def sent_otps(monkeypatch):
    """Chặn việc gửi OTP thật và ghi lại (email, otp) để test đọc được mã."""
    sent = []
    monkeypatch.setattr(auth_module, "_deliver_otp", lambda email, otp: sent.append((email, otp)))
    return sent


def register_user(client):
    assert client.post("/api/auth/register", json=register_payload()).status_code == 201


def request_otp(client, sent_otps, identifier="newchef@example.com"):
    response = client.post("/api/auth/forgot-password", json={"identifier": identifier})
    assert response.status_code == 200
    return sent_otps[-1][1] if sent_otps else None


def verify(client, otp, identifier="newchef@example.com"):
    return client.post("/api/auth/verify-otp", json={"identifier": identifier, "otp": otp})


def login(client, password, identifier="newchef@example.com"):
    return client.post("/api/auth/login", json={"email": identifier, "password": password})


def test_full_forgot_password_flow(client, sent_otps):
    register_user(client)
    otp = request_otp(client, sent_otps)
    assert sent_otps[0][0] == "newchef@example.com"

    verified = verify(client, otp)
    assert verified.status_code == 200

    reset = client.post(
        "/api/auth/reset-password",
        json={"reset_token": verified.json()["reset_token"], "new_password": "matkhaumoi456"},
    )

    assert reset.status_code == 200
    assert login(client, "matkhau123").status_code == 401
    assert login(client, "matkhaumoi456").status_code == 200


def test_forgot_password_requires_an_email_address(client, sent_otps):
    register_user(client)

    by_phone = client.post("/api/auth/forgot-password", json={"identifier": "0912345678"})
    empty = client.post("/api/auth/forgot-password", json={"identifier": "   "})

    assert by_phone.status_code == 400
    assert empty.status_code == 400
    assert sent_otps == []


def test_forgot_password_email_is_case_insensitive(client, sent_otps):
    register_user(client)

    request_otp(client, sent_otps, identifier="  NewChef@Example.com ")

    assert sent_otps[0][0] == "newchef@example.com"


def test_forgot_password_unknown_account_gets_same_reply_and_no_otp(client, sent_otps):
    register_user(client)

    known = client.post("/api/auth/forgot-password", json={"identifier": "newchef@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"identifier": "khongco@example.com"})

    assert known.json() == unknown.json()
    assert len(sent_otps) == 1


def test_forgot_password_has_resend_cooldown(client, sent_otps):
    register_user(client)

    request_otp(client, sent_otps)
    request_otp(client, sent_otps)

    assert len(sent_otps) == 1


def test_verify_otp_locks_after_too_many_wrong_attempts(client, sent_otps):
    register_user(client)
    otp = request_otp(client, sent_otps)
    wrong = "000000" if otp != "000000" else "111111"

    for _ in range(5):
        assert verify(client, wrong).status_code == 400

    assert verify(client, otp).status_code == 400


def test_verify_otp_rejects_expired_code(client, sent_otps):
    register_user(client)
    otp = request_otp(client, sent_otps)
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    connection = get_db()
    try:
        connection.execute("UPDATE password_resets SET expires_at = ?", (expired,))
        connection.commit()
    finally:
        connection.close()

    assert verify(client, otp).status_code == 400


def test_reset_token_cannot_be_used_as_access_token(client, sent_otps):
    register_user(client)
    otp = request_otp(client, sent_otps)
    reset_token = verify(client, otp).json()["reset_token"]

    response = client.get(
        "/api/profile/me",
        headers={"Authorization": f"Bearer {reset_token}"},
    )

    assert response.status_code == 401


def test_reset_password_token_is_single_use_and_checks_password_first(client, sent_otps):
    register_user(client)
    otp = request_otp(client, sent_otps)
    reset_token = verify(client, otp).json()["reset_token"]

    too_short = client.post(
        "/api/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "short"},
    )
    first = client.post(
        "/api/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "matkhaumoi456"},
    )
    second = client.post(
        "/api/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "matkhauthuba789"},
    )

    assert too_short.status_code == 400
    assert first.status_code == 200
    assert second.status_code == 400
    assert login(client, "matkhaumoi456").status_code == 200


def test_reset_password_rejects_garbage_token(client):
    response = client.post(
        "/api/auth/reset-password",
        json={"reset_token": "khong-phai-token", "new_password": "matkhaumoi456"},
    )

    assert response.status_code == 400


# ---------- Đổi mật khẩu (đã đăng nhập) ----------

def test_change_password_requires_bearer_token(client):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "matkhau123", "new_password": "matkhaumoi456"},
    )

    assert response.status_code == 401


def test_change_password_validates_current_and_new_password(client):
    register_user(client)
    token = login(client, "matkhau123").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    wrong_current = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "sai-mat-khau", "new_password": "matkhaumoi456"},
    )
    same_password = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "matkhau123", "new_password": "matkhau123"},
    )
    too_short = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "matkhau123", "new_password": "short"},
    )

    # Sai mật khẩu hiện tại phải là 400, không phải 401, để app không tự đăng xuất
    assert wrong_current.status_code == 400
    assert same_password.status_code == 400
    assert too_short.status_code == 400


def test_change_password_updates_login_credentials(client):
    register_user(client)
    token = login(client, "matkhau123").json()["access_token"]

    response = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "matkhau123", "new_password": "matkhaumoi456"},
    )

    assert response.status_code == 200
    assert login(client, "matkhau123").status_code == 401
    assert login(client, "matkhaumoi456").status_code == 200


# ---------- Xác nhận mật khẩu hiện tại rồi đặt mật khẩu mới ----------

def test_verify_current_password_requires_bearer_token(client):
    response = client.post(
        "/api/auth/verify-current-password",
        json={"current_password": "matkhau123"},
    )

    assert response.status_code == 401


def test_verify_current_password_rejects_wrong_password_with_400(client):
    register_user(client)
    token = login(client, "matkhau123").json()["access_token"]

    response = client.post(
        "/api/auth/verify-current-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "sai-mat-khau"},
    )

    # Phải là 400, không phải 401, để app không tự đăng xuất
    assert response.status_code == 400


def test_verify_current_password_token_resets_password_once(client):
    register_user(client)
    token = login(client, "matkhau123").json()["access_token"]

    verified = client.post(
        "/api/auth/verify-current-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "matkhau123"},
    )
    assert verified.status_code == 200
    reset_token = verified.json()["reset_token"]

    first = client.post(
        "/api/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "matkhaumoi456"},
    )
    second = client.post(
        "/api/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "matkhauthuba789"},
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert login(client, "matkhau123").status_code == 401
    assert login(client, "matkhaumoi456").status_code == 200


def test_verify_current_password_token_is_not_an_access_token(client):
    register_user(client)
    token = login(client, "matkhau123").json()["access_token"]
    reset_token = client.post(
        "/api/auth/verify-current-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "matkhau123"},
    ).json()["reset_token"]

    response = client.get(
        "/api/profile/me",
        headers={"Authorization": f"Bearer {reset_token}"},
    )

    assert response.status_code == 401


# ---------- Số điện thoại khi đăng ký ----------

def test_register_stores_cleaned_phone_number(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload(phone_number="091 234 5678"),
    )

    assert response.status_code == 201
    assert get_user_row(username=response.json()["user"]["username"])["phone_number"] == "0912345678"


def test_register_rejects_invalid_phone_number(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload(phone_number="12-34"),
    )

    assert response.status_code == 400
    assert get_user_row(email="newchef@example.com") is None


def test_register_rejects_duplicate_phone_number_in_any_format(client):
    first = client.post("/api/auth/register", json=register_payload())
    second = client.post(
        "/api/auth/register",
        json=register_payload(
            username="other",
            email="other@example.com",
            phone_number="+84912345678",  # cùng số 0912345678 viết khác đi
        ),
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_register_without_phone_number_is_still_allowed(client):
    payload = register_payload()
    del payload["phone_number"]

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 201


# ---------- Đăng nhập bằng tên tài khoản, email hoặc số điện thoại ----------

def test_login_accepts_username_email_or_phone_in_any_format(client):
    register_user(client)  # username newchef, email newchef@example.com, số điện thoại 0912345678

    identifiers = [
        "newchef",
        "NewChef",
        "newchef@example.com",
        "NEWCHEF@Example.com",
        "0912345678",
        "+84912345678",
        "091 234 5678",
    ]
    for identifier in identifiers:
        response = login(client, "matkhau123", identifier=identifier)
        assert response.status_code == 200, identifier


def test_login_by_username_or_phone_still_needs_the_right_password(client):
    register_user(client)

    for identifier in ["newchef", "0912345678"]:
        assert login(client, "sai-mat-khau", identifier=identifier).status_code == 401


def test_login_by_phone_fails_when_two_accounts_share_the_number(client):
    register_user(client)
    connection = get_db()
    try:
        connection.execute("UPDATE users SET phone_number = '0912345678' WHERE id = 1")
        connection.commit()
    finally:
        connection.close()

    assert login(client, "matkhau123", identifier="0912345678").status_code == 401


def test_register_rejects_phone_like_username_and_case_insensitive_duplicate(client):
    phone_like = client.post(
        "/api/auth/register",
        json=register_payload(
            username="0912345678", email="a1@example.com", phone_number="0987654321"
        ),
    )
    first = client.post("/api/auth/register", json=register_payload())
    duplicate = client.post(
        "/api/auth/register",
        json=register_payload(
            username="NEWCHEF", email="b1@example.com", phone_number="0911111111"
        ),
    )

    assert phone_like.status_code == 400
    assert first.status_code == 201
    assert duplicate.status_code == 409