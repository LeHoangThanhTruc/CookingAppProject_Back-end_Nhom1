from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# --- Pydantic Schemas (Định dạng dữ liệu đầu vào) ---

class UpdateProfileRequest(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

class FriendRequest(BaseModel):
    user_id: int
    friend_id: int

# --- API Endpoints ---

@router.get("/{user_id}")
def get_user_profile(user_id: int):
    # TODO: Lấy thông tin cá nhân của người dùng (từ bảng users)
    pass

@router.put("/update")
def update_user_profile(data: UpdateProfileRequest):
    # TODO: Cập nhật thông tin hồ sơ (UPDATE bảng users)
    pass

@router.get("/{user_id}/posts")
def get_user_posts(user_id: int):
    # TODO: Lấy tất cả bài viết do người dùng này đăng
    pass

@router.post("/friend-request")
def send_friend_request(data: FriendRequest):
    # TODO: Gửi lời mời kết bạn (INSERT vào friendships với status='PENDING')
    pass

@router.post("/accept-friend")
def accept_friend_request(data: FriendRequest):
    # TODO: Chấp nhận kết bạn (UPDATE status='ACCEPTED' trong friendships)
    pass