import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from database import get_db
from security import get_current_user_id

# Đọc file .env (JWT_SECRET_KEY, JWT_EXPIRE_MINUTES...) ngay khi module này được import
load_dotenv()

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,50}$")
PHONE_RE = re.compile(r"^\+?\d{9,15}$")  # sau khi bỏ khoảng trắng, dấu chấm, gạch ngang, ngoặc
PASSWORD_ITERATIONS = 600_000
SUPPORTED_OAUTH_PROVIDERS = {"GOOGLE", "FACEBOOK"}
OTP_TTL_MINUTES = 10          # Mã OTP có hiệu lực 10 phút
OTP_MAX_ATTEMPTS = 5          # Nhập sai tối đa 5 lần cho mỗi mã
OTP_RESEND_SECONDS = 60       # Chờ 60 giây mới được xin mã mới
RESET_TOKEN_MINUTES = 10      # Thời gian được đặt mật khẩu mới sau khi xác thực OTP

# --- Pydantic Schemas (Khai báo định dạng dữ liệu đầu vào) ---

class RegisterRequest(BaseModel):
    username: Optional[str] = None  # Không gửi thì server tự tạo từ email
    email: str
    password: str
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class LoginRequest(BaseModel):
    email: str  # Nhận cả email lẫn username
    password: str

class OAuthLoginRequest(BaseModel):
    provider: str  # GOOGLE hoặc FACEBOOK
    token: str     # GOOGLE: ID token; FACEBOOK: access token (do SDK trên Android cấp)

class LogoutRequest(BaseModel):
    user_id: int

# --- Hàm hỗ trợ ---

def hash_password(password: str) -> str:
    """Băm mật khẩu bằng PBKDF2-SHA256 (thư viện chuẩn, không cần cài thêm)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, digest)


def create_access_token(user_id: int) -> str:
    """Tạo JWT khớp với security.get_current_user_id (HS256, có sub và exp)."""
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET_KEY chưa được cấu hình",
        )
    expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _user_to_dict(row: sqlite3.Row) -> dict:
    return {
        key: row[key]
        for key in ("id", "username", "email", "full_name", "avatar_url", "auth_provider")
    }


def _token_response(row: sqlite3.Row) -> dict:
    return {
        "access_token": create_access_token(row["id"]),
        "token_type": "bearer",
        "user": _user_to_dict(row),
    }


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 100 or not EMAIL_RE.match(email):
        raise _bad_request("Email không hợp lệ")
    return email


def _generate_username(conn: sqlite3.Connection, email: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.]", "", email.split("@")[0])[:30] or "user"
    while True:
        candidate = f"{base}_{secrets.token_hex(3)}"
        taken = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (candidate,)
        ).fetchone()
        if not taken:
            return candidate

# --- API Endpoints ---

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest):
    email = _normalize_email(data.email)
    username = data.username.strip() if data.username else None

    if username is not None and not USERNAME_RE.match(username):
        raise _bad_request(
            "Username phải dài 3-50 ký tự, chỉ gồm chữ, số, dấu gạch dưới và dấu chấm"
        )
    if username is not None and PHONE_RE.match(username):
        raise _bad_request("Tên tài khoản không được chỉ gồm số (dễ nhầm với số điện thoại)")

    if not 8 <= len(data.password) <= 128:
        raise _bad_request("Mật khẩu phải dài từ 8 đến 128 ký tự")

    full_name = data.full_name.strip() if data.full_name else None
    phone_number = None
    if data.phone_number and data.phone_number.strip():
        phone_number = re.sub(r"[\s.\-()]", "", data.phone_number)
        if not PHONE_RE.match(phone_number):
            raise _bad_request("Số điện thoại không hợp lệ")

    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được sử dụng")
        if phone_number is not None:
            wanted_phone = _normalize_phone(phone_number)
            for existing in conn.execute(
                "SELECT phone_number FROM users WHERE phone_number IS NOT NULL"
            ).fetchall():
                if _normalize_phone(existing["phone_number"]) == wanted_phone:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Số điện thoại đã được sử dụng")
        if username is None:
            username = _generate_username(conn, email)
        elif conn.execute("SELECT 1 FROM users WHERE lower(username) = ?", (username.lower(),)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Username đã được sử dụng")

        cursor = conn.execute(
            """
            INSERT INTO users (username, email, phone_number, password_hash, full_name, auth_provider)
            VALUES (?, ?, ?, ?, ?, 'LOCAL')
            """,
            (username, email, phone_number, hash_password(data.password), full_name),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return {"message": "Đăng ký thành công", "user": _user_to_dict(row)}
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username hoặc email đã được sử dụng")
    finally:
        conn.close()


def _find_user_for_login(conn: sqlite3.Connection, identifier: str) -> Optional[sqlite3.Row]:
    """Tìm tài khoản theo email, tên tài khoản (không phân biệt hoa thường) hoặc số điện thoại."""
    identifier = identifier.strip()
    if not identifier:
        return None
    if "@" in identifier:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (identifier.lower(),)
        ).fetchone()

    row = conn.execute(
        "SELECT * FROM users WHERE lower(username) = ?", (identifier.lower(),)
    ).fetchone()
    if row is not None:
        return row

    cleaned = re.sub(r"[\s.\-()]", "", identifier)
    if PHONE_RE.match(cleaned):
        wanted = _normalize_phone(cleaned)
        rows = conn.execute("SELECT * FROM users WHERE phone_number IS NOT NULL").fetchall()
        matches = [item for item in rows if _normalize_phone(item["phone_number"]) == wanted]
        if len(matches) == 1:  # số điện thoại dùng chung cho nhiều tài khoản thì không đăng nhập bằng số được
            return matches[0]
    return None


@router.post("/login")
def login(data: LoginRequest):
    identifier = data.email.strip()
    invalid = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Tài khoản hoặc mật khẩu không đúng"
    )

    conn = get_db()
    try:
        row = _find_user_for_login(conn, identifier)

        # Tài khoản đăng ký bằng Google/Facebook không có password_hash nên không đăng nhập bằng mật khẩu
        if row is None or not row["password_hash"]:
            raise invalid
        if not verify_password(data.password, row["password_hash"]):
            raise invalid

        conn.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        conn.commit()
        return _token_response(row)
    finally:
        conn.close()


def _log_auth(message: str) -> None:
    """In lý do từ chối ra terminal của server để dễ tìm lỗi; KHÔNG gửi cho client và không in token."""
    print(f"[AUTH] {message}", flush=True)


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _verify_google_token(id_token: str) -> dict:
    """Hỏi Google xem ID token có hợp lệ và cấp cho đúng ứng dụng của mình không."""
    allowed = [
        value.strip() for value in os.getenv("GOOGLE_WEB_CLIENT_ID", "").split(",") if value.strip()
    ]
    if not allowed:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Server chưa cấu hình đăng nhập Google (GOOGLE_WEB_CLIENT_ID)",
        )
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Google không hợp lệ hoặc đã hết hạn")

    try:
        info = _http_get_json(
            "https://oauth2.googleapis.com/tokeninfo?"
            + urllib.parse.urlencode({"id_token": id_token})
        )
    except urllib.error.HTTPError as exc:
        _log_auth(f"Google từ chối ID token (HTTP {exc.code}): {exc.read().decode('utf-8', 'ignore')[:200]}")
        raise invalid
    except Exception as exc:
        _log_auth(f"Không gọi được Google tokeninfo: {exc!r}")
        raise invalid

    if info.get("aud") not in allowed:
        _log_auth(
            f"ID token cấp cho client '{info.get('aud')}' nhưng GOOGLE_WEB_CLIENT_ID trên server là {allowed}"
        )
        raise invalid
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        _log_auth(f"Nơi cấp token (iss) không hợp lệ: {info.get('iss')}")
        raise invalid
    if str(info.get("email_verified")).lower() != "true":
        _log_auth("Email của tài khoản Google chưa được xác minh")
        raise invalid
    if not info.get("sub") or not info.get("email"):
        _log_auth("Token Google thiếu sub hoặc email")
        raise invalid

    return {
        "provider_id": str(info["sub"]),
        "email": info["email"],
        "full_name": info.get("name"),
        "avatar_url": info.get("picture"),
    }


def _verify_facebook_token(access_token: str) -> dict:
    """Hỏi Facebook xem access token còn hiệu lực, thuộc ứng dụng của mình và của ai."""
    app_id = os.getenv("FACEBOOK_APP_ID", "").strip()
    app_secret = os.getenv("FACEBOOK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Server chưa cấu hình đăng nhập Facebook (FACEBOOK_APP_ID, FACEBOOK_APP_SECRET)",
        )
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Facebook không hợp lệ hoặc đã hết hạn")

    try:
        debug = _http_get_json(
            "https://graph.facebook.com/debug_token?"
            + urllib.parse.urlencode(
                {"input_token": access_token, "access_token": f"{app_id}|{app_secret}"}
            )
        )
        token_info = debug.get("data") or {}
        if not token_info.get("is_valid") or str(token_info.get("app_id")) != app_id:
            raise ValueError("Token không hợp lệ hoặc không thuộc ứng dụng này")

        profile = _http_get_json(
            "https://graph.facebook.com/me?"
            + urllib.parse.urlencode(
                {"fields": "id,name,email,picture.type(large)", "access_token": access_token}
            )
        )
        if not profile.get("id") or str(profile["id"]) != str(token_info.get("user_id")):
            raise ValueError("Thông tin người dùng không khớp với token")
    except urllib.error.HTTPError as exc:
        _log_auth(f"Facebook từ chối token (HTTP {exc.code}): {exc.read().decode('utf-8', 'ignore')[:200]}")
        raise invalid
    except Exception as exc:
        _log_auth(f"Xác minh token Facebook thất bại: {exc!r}")
        raise invalid

    email = profile.get("email")
    if not email:
        raise _bad_request(
            "Tài khoản Facebook không chia sẻ email nên không thể đăng nhập. "
            "Hãy cho phép chia sẻ email hoặc dùng cách đăng nhập khác"
        )
    picture = (profile.get("picture") or {}).get("data") or {}
    return {
        "provider_id": str(profile["id"]),
        "email": email,
        "full_name": profile.get("name"),
        "avatar_url": picture.get("url"),
    }


@router.post("/oauth-login")
def oauth_login(data: OAuthLoginRequest):
    provider = data.provider.strip().upper()
    if provider not in SUPPORTED_OAUTH_PROVIDERS:
        raise _bad_request("Provider phải là GOOGLE hoặc FACEBOOK")
    token = data.token.strip()
    if not token:
        raise _bad_request("Thiếu token đăng nhập từ Google/Facebook")

    # Server tự hỏi Google/Facebook xem token có thật không, không tin dữ liệu do app gửi lên
    profile = _verify_google_token(token) if provider == "GOOGLE" else _verify_facebook_token(token)
    provider_id = profile["provider_id"]
    email = _normalize_email(profile["email"])
    full_name = profile.get("full_name")
    avatar_url = profile.get("avatar_url")

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE auth_provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()

        if row is None:
            # Email đã thuộc về tài khoản khác thì không tự động gộp để tránh bị chiếm tài khoản
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                _log_auth(
                    f"oauth-login {provider}: email '{email}' đã thuộc một tài khoản khác "
                    "trong hệ thống nên bị từ chối (409)"
                )
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Email này đã được đăng ký bằng phương thức khác",
                )
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, full_name, avatar_url, auth_provider, provider_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_generate_username(conn, email), email, full_name, avatar_url, provider, provider_id),
            )
            user_id = cursor.lastrowid
        else:
            user_id = row["id"]

        conn.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _token_response(row)
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Không thể tạo tài khoản, vui lòng thử lại")
    finally:
        conn.close()


@router.post("/logout")
def logout(current_user_id: int = Depends(get_current_user_id)):
    # user_id lấy từ access token (Authorization: Bearer ...), không nhận từ body để tránh đăng xuất hộ người khác
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE users SET last_logout_at = CURRENT_TIMESTAMP WHERE id = ?",
            (current_user_id,),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng")
        return {"message": "Đăng xuất thành công"}
    finally:
        conn.close()


# ======================================================================
# Quên mật khẩu / Đặt lại mật khẩu / Đổi mật khẩu
# ======================================================================

class ForgotPasswordRequest(BaseModel):
    identifier: str  # Email đã đăng ký


class VerifyOtpRequest(BaseModel):
    identifier: str
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeEmailRequest(BaseModel):
    current_password: str
    new_email: str


def _require_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET_KEY chưa được cấu hình",
        )
    return secret


def _reset_secret() -> str:
    # Khóa riêng cho reset token để token này KHÔNG dùng được như access token
    # (security.get_current_user_id chỉ kiểm tra chữ ký bằng JWT_SECRET_KEY).
    return _require_secret() + ":password-reset"


def _check_new_password(password: str) -> None:
    if not 8 <= len(password) <= 128:
        raise _bad_request("Mật khẩu phải dài từ 8 đến 128 ký tự")


def _ensure_reset_table(conn: sqlite3.Connection) -> None:
    # Bảng riêng của chức năng này, tạo khi cần nên không phải sửa database.py của nhóm
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0,        -- 1 khi OTP đã xác thực thành công
            reset_done INTEGER NOT NULL DEFAULT 0,  -- 1 khi đã đặt mật khẩu mới
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )


def _hash_otp(user_id: int, otp: str) -> str:
    return hmac.new(
        _require_secret().encode("utf-8"),
        f"{user_id}:{otp}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _normalize_phone(value: Optional[str]) -> str:
    """Chuẩn hóa số điện thoại để so khớp: bỏ khoảng trắng/dấu, đổi +84 hoặc 84 thành 0."""
    digits = re.sub(r"[\s.\-()]", "", value or "")
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits


def _find_user_for_reset(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    """Tìm tài khoản LOCAL (có mật khẩu) theo email đã đăng ký."""
    return conn.execute(
        "SELECT * FROM users WHERE email = ? AND password_hash IS NOT NULL",
        (email.strip().lower(),),
    ).fetchone()


def _dev_note(message: str) -> None:
    """Chế độ dev (chưa cấu hình SMTP): in lý do ra terminal của server, KHÔNG gửi cho client."""
    if not os.getenv("SMTP_HOST"):
        print(f"[DEV] {message}", flush=True)


def _deliver_otp(email: str, otp: str) -> None:
    """Gửi OTP qua email (SMTP). Chưa cấu hình SMTP thì in mã ra terminal của server (chế độ dev)."""
    host = os.getenv("SMTP_HOST")
    if not host:
        print(f"[DEV] Mã OTP đặt lại mật khẩu của {email}: {otp}", flush=True)
        return
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")

        message = EmailMessage()
        message["Subject"] = "Mã xác thực đặt lại mật khẩu Cooking App"
        message["From"] = os.getenv("SMTP_FROM", user or "no-reply@cookingapp.local")
        message["To"] = email
        message.set_content(
            f"Mã xác thực của bạn là: {otp}\n"
            f"Mã có hiệu lực trong {OTP_TTL_MINUTES} phút. "
            "Nếu bạn không yêu cầu, hãy bỏ qua email này."
        )

        smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with smtp_class(host, port, timeout=10) as smtp:
            if port != 465:
                smtp.starttls()
            if user:
                smtp.login(user, password or "")
            smtp.send_message(message)
    except Exception as exc:  # Không để lỗi gửi mail lộ ra cho client
        print(f"[AUTH] Gửi email OTP thất bại: {exc}", flush=True)


def _create_reset_token(user_id: int, reset_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "rid": reset_id,
        "purpose": "password_reset",
        "iat": now,
        "exp": now + timedelta(minutes=RESET_TOKEN_MINUTES),
    }
    return jwt.encode(payload, _reset_secret(), algorithm="HS256")


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    # Người dùng phải nhập email đã đăng ký; mã OTP được gửi về chính email đó
    identifier = data.identifier.strip()
    if "@" not in identifier:
        raise _bad_request("Vui lòng nhập email đã đăng ký")
    email = _normalize_email(identifier)

    # Luôn trả cùng một thông báo để không lộ email nào đã đăng ký
    generic = {"message": "Nếu email đã đăng ký, mã xác thực đã được gửi tới email đó"}

    conn = get_db()
    try:
        _ensure_reset_table(conn)
        user = _find_user_for_reset(conn, email)
        if user is None:
            _dev_note(
                f"forgot-password: không có tài khoản nào dùng email '{email}' "
                "(chưa đăng ký, hoặc là tài khoản Google/Facebook)."
            )
            return generic

        now = datetime.now(timezone.utc)
        last = conn.execute(
            "SELECT created_at FROM password_resets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if last and now - datetime.fromisoformat(last["created_at"]) < timedelta(seconds=OTP_RESEND_SECONDS):
            _dev_note("forgot-password: bỏ qua vì mã trước đó mới gửi chưa đủ 60 giây, hãy đợi rồi thử lại.")
            return generic  # Đang trong thời gian chờ, không gửi thêm mã

        otp = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute(
            "UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0",
            (user["id"],),
        )
        conn.execute(
            "INSERT INTO password_resets (user_id, otp_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (
                user["id"],
                _hash_otp(user["id"], otp),
                (now + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
        _deliver_otp(user["email"], otp)
        return generic
    finally:
        conn.close()


@router.post("/verify-otp")
def verify_otp(data: VerifyOtpRequest):
    invalid = HTTPException(
        status.HTTP_400_BAD_REQUEST, "Mã xác thực không đúng hoặc đã hết hạn"
    )

    email = _normalize_email(data.identifier)

    conn = get_db()
    try:
        _ensure_reset_table(conn)
        user = _find_user_for_reset(conn, email)
        if user is None:
            raise invalid

        row = conn.execute(
            "SELECT * FROM password_resets WHERE user_id = ? AND used = 0 ORDER BY id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if row is None:
            raise invalid
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            raise invalid
        if row["attempts"] >= OTP_MAX_ATTEMPTS:
            raise invalid

        conn.execute(
            "UPDATE password_resets SET attempts = attempts + 1 WHERE id = ?", (row["id"],)
        )
        if not hmac.compare_digest(_hash_otp(user["id"], data.otp.strip()), row["otp_hash"]):
            conn.commit()
            raise invalid

        conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        return {
            "reset_token": _create_reset_token(user["id"], row["id"]),
            "expires_in_minutes": RESET_TOKEN_MINUTES,
        }
    finally:
        conn.close()


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest):
    _check_new_password(data.new_password)
    invalid = HTTPException(
        status.HTTP_400_BAD_REQUEST, "Phiên đặt lại mật khẩu không hợp lệ hoặc đã hết hạn"
    )

    try:
        payload = jwt.decode(
            data.reset_token,
            _reset_secret(),
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "rid"]},
        )
        if payload.get("purpose") != "password_reset":
            raise invalid
        user_id = int(payload["sub"])
        reset_id = int(payload["rid"])
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise invalid

    conn = get_db()
    try:
        _ensure_reset_table(conn)
        row = conn.execute(
            "SELECT id FROM password_resets WHERE id = ? AND user_id = ? AND used = 1 AND reset_done = 0",
            (reset_id, user_id),
        ).fetchone()
        if row is None:
            raise invalid

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(data.new_password), user_id),
        )
        conn.execute("UPDATE password_resets SET reset_done = 1 WHERE id = ?", (reset_id,))
        conn.commit()
        return {"message": "Đặt lại mật khẩu thành công"}
    finally:
        conn.close()


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user_id: int = Depends(get_current_user_id),
):
    _check_new_password(data.new_password)

    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (current_user_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng")
        if not row["password_hash"]:
            raise _bad_request("Tài khoản đăng nhập bằng Google/Facebook không có mật khẩu để đổi")
        # Dùng 400 (không dùng 401) vì app Android sẽ xóa phiên đăng nhập khi nhận 401
        if not verify_password(data.current_password, row["password_hash"]):
            raise _bad_request("Mật khẩu hiện tại không đúng")
        if data.current_password == data.new_password:
            raise _bad_request("Mật khẩu mới phải khác mật khẩu hiện tại")

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(data.new_password), current_user_id),
        )
        conn.commit()
        return {"message": "Đổi mật khẩu thành công"}
    finally:
        conn.close()


@router.post("/change-email")
def change_email(
    data: ChangeEmailRequest,
    current_user_id: int = Depends(get_current_user_id),
):
    new_email = data.new_email.strip().lower()
    if not EMAIL_RE.fullmatch(new_email):
        raise _bad_request("Email mới không hợp lệ")
    conn = get_db()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (current_user_id,)).fetchone()
        if row is None or not row["password_hash"] or not verify_password(data.current_password, row["password_hash"]):
            raise _bad_request("Mật khẩu hiện tại không đúng")
        if conn.execute("SELECT 1 FROM users WHERE email=? AND id<>?", (new_email, current_user_id)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được sử dụng")
        conn.execute("UPDATE users SET email=? WHERE id=?", (new_email, current_user_id))
        conn.commit()
        return {"status": "success", "message": "Đổi email thành công"}
    finally:
        conn.close()


class VerifyCurrentPasswordRequest(BaseModel):
    current_password: str


@router.post("/verify-current-password")
def verify_current_password(
    data: VerifyCurrentPasswordRequest,
    current_user_id: int = Depends(get_current_user_id),
):
    """Người đã đăng nhập xác nhận mật khẩu hiện tại, nhận reset_token để sang bước đặt mật khẩu mới."""
    conn = get_db()
    try:
        _ensure_reset_table(conn)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (current_user_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng")
        if not row["password_hash"]:
            raise _bad_request("Tài khoản đăng nhập bằng Google/Facebook không có mật khẩu để đổi")
        # Dùng 400 (không dùng 401) vì app Android sẽ xóa phiên đăng nhập khi nhận 401
        if not verify_password(data.current_password, row["password_hash"]):
            raise _bad_request("Mật khẩu hiện tại không đúng")

        now = datetime.now(timezone.utc)
        cursor = conn.execute(
            """
            INSERT INTO password_resets (user_id, otp_hash, expires_at, used, created_at)
            VALUES (?, 'current-password', ?, 1, ?)
            """,
            (
                current_user_id,
                (now + timedelta(minutes=RESET_TOKEN_MINUTES)).isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
        return {
            "reset_token": _create_reset_token(current_user_id, cursor.lastrowid),
            "expires_in_minutes": RESET_TOKEN_MINUTES,
        }
    finally:
        conn.close()
