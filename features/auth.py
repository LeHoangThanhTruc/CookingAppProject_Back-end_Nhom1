from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# --- Pydantic Schemas (Khai báo định dạng dữ liệu đầu vào) ---

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class LoginRequest(BaseModel):
    email: str  # Hoặc username tùy bạn quy định ở Android
    password: str

class OAuthLoginRequest(BaseModel):
    provider: str      # GOOGLE hoặc FACEBOOK
    provider_id: str   # ID định danh từ Google/Facebook
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

class LogoutRequest(BaseModel):
    user_id: int

# --- API Endpoints ---

@router.post("/register")
def register(data: RegisterRequest):
    # TODO: Logic đăng ký tài khoản mới (INSERT vào bảng users)
    pass

@router.post("/login")
def login(data: LoginRequest):
    # TODO: Logic đăng nhập (CHECK email/password, UPDATE last_login_at)
    pass

@router.post("/oauth-login")
def oauth_login(data: OAuthLoginRequest):
    # TODO: Logic đăng nhập qua Google/Facebook (Thêm mới nếu chưa tồn tại hoặc Cập nhật last_login_at)
    pass

@router.post("/logout")
def logout(data: LogoutRequest):
    # TODO: Logic đăng xuất (UPDATE last_logout_at)
    pass