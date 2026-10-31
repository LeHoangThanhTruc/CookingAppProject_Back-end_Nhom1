import os
import re
import sqlite3
import warnings
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, field_validator

from database import get_db
from security import get_current_user_id


router = APIRouter()

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
PHONE_PATTERN = re.compile(r"^\+?\d{8,15}$")
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/jpg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}


class ProfileResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class UpdateMyProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("Họ và tên không được để trống")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Họ và tên không được để trống")
        if len(normalized) > 100:
            raise ValueError("Họ và tên không được vượt quá 100 ký tự")
        return normalized

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("Số điện thoại phải gồm 8-15 chữ số và có thể bắt đầu bằng +")
        return normalized

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 500:
            raise ValueError("Giới thiệu không được vượt quá 500 ký tự")
        return normalized


class LegacyUpdateProfileRequest(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class FriendRequest(BaseModel):
    user_id: int
    friend_id: int


def _fetch_profile(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT id, username, email, full_name, phone_number, bio, avatar_url
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )
    return row


def _profile_response(row: sqlite3.Row) -> ProfileResponse:
    return ProfileResponse(**dict(row))


def _upload_root() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "uploads")).expanduser().resolve()


def _old_local_avatar_path(avatar_url: Optional[str], upload_root: Path) -> Optional[Path]:
    if not avatar_url or not avatar_url.startswith("/uploads/"):
        return None

    relative = PurePosixPath(avatar_url.removeprefix("/uploads/"))
    candidate = (upload_root / Path(*relative.parts)).resolve()
    if not candidate.is_relative_to(upload_root):
        return None
    return candidate


def _normalize_image(content: bytes, content_type: Optional[str]) -> tuple[bytes, str]:
    expected = ALLOWED_IMAGE_TYPES.get((content_type or "").lower())
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Ảnh đại diện phải là JPEG, PNG hoặc WebP",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                source.load()
                detected_format = (source.format or "").upper()
                if detected_format != expected[0]:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Nội dung ảnh không khớp định dạng đã khai báo",
                    )
                if source.width * source.height > MAX_AVATAR_PIXELS:
                    raise HTTPException(
                        status_code=413,
                        detail="Kích thước ảnh đại diện quá lớn",
                    )

                image = ImageOps.exif_transpose(source)
                if detected_format == "JPEG" and image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")

                output = BytesIO()
                image.save(output, format=detected_format, optimize=True)
                return output.getvalue(), expected[1]
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(
            status_code=413,
            detail="Kích thước ảnh đại diện quá lớn",
        )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tệp tải lên không phải ảnh hợp lệ",
        ) from exc


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        return _profile_response(_fetch_profile(connection, user_id))
    finally:
        connection.close()


@router.patch("/me", response_model=ProfileResponse)
def update_my_profile(
    data: UpdateMyProfileRequest,
    user_id: int = Depends(get_current_user_id),
):
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=422,
            detail="Cần cung cấp ít nhất một trường để cập nhật",
        )

    connection = get_db()
    try:
        _fetch_profile(connection, user_id)
        assignments = ", ".join(f"{field} = ?" for field in updates)
        values = [*updates.values(), user_id]
        connection.execute(
            f"UPDATE users SET {assignments} WHERE id = ?",
            values,
        )
        connection.commit()
        return _profile_response(_fetch_profile(connection, user_id))
    finally:
        connection.close()


@router.post("/me/avatar", response_model=ProfileResponse)
async def upload_my_avatar(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    content_type = file.content_type
    content = await file.read(MAX_AVATAR_BYTES + 1)
    await file.close()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Ảnh đại diện không được vượt quá 5 MiB",
        )

    normalized_image, extension = _normalize_image(content, content_type)
    upload_root = _upload_root()
    avatar_directory = (upload_root / "avatars").resolve()
    if not avatar_directory.is_relative_to(upload_root):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cấu hình thư mục upload không hợp lệ",
        )
    avatar_directory.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid4().hex}{extension}"
    new_avatar_path = (avatar_directory / filename).resolve()
    if not new_avatar_path.is_relative_to(avatar_directory):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đường dẫn ảnh đại diện không hợp lệ",
        )

    avatar_url = f"/uploads/avatars/{filename}"
    connection = get_db()
    old_avatar_path = None
    try:
        current_profile = _fetch_profile(connection, user_id)
        old_avatar_path = _old_local_avatar_path(current_profile["avatar_url"], upload_root)
        new_avatar_path.write_bytes(normalized_image)
        connection.execute(
            "UPDATE users SET avatar_url = ? WHERE id = ?",
            (avatar_url, user_id),
        )
        connection.commit()
        updated_profile = _profile_response(_fetch_profile(connection, user_id))
    except Exception:
        connection.rollback()
        new_avatar_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    if old_avatar_path and old_avatar_path != new_avatar_path and old_avatar_path.is_file():
        old_avatar_path.unlink(missing_ok=True)

    return updated_profile


# Các endpoint bên dưới thuộc chức năng trang người khác/social và được giữ nguyên
# để không mở rộng phạm vi của phần user profile hiện tại.
@router.get("/{user_id}")
def get_user_profile(user_id: int):
    # TODO: Lấy thông tin cá nhân công khai của người dùng khác.
    pass


@router.put("/update")
def update_user_profile(data: LegacyUpdateProfileRequest):
    # TODO: Endpoint cũ, không dùng cho luồng profile đã xác thực.
    pass


@router.get("/{user_id}/posts")
def get_user_posts(user_id: int):
    # TODO: Lấy tất cả bài viết do người dùng này đăng.
    pass


@router.post("/friend-request")
def send_friend_request(data: FriendRequest):
    # TODO: Gửi lời mời kết bạn.
    pass


@router.post("/accept-friend")
def accept_friend_request(data: FriendRequest):
    # TODO: Chấp nhận kết bạn.
    pass
