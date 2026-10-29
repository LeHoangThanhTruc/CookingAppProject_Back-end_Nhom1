from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

# --- Pydantic Schemas (Định dạng dữ liệu đầu vào) ---

class CreateRegularPostRequest(BaseModel):
    user_id: int
    caption: str
    privacy: Optional[str] = "PUBLIC" # PUBLIC, FRIENDS, ONLY_ME
    media_urls: Optional[List[str]] = [] # Danh sách URL ảnh/video

class IngredientItem(BaseModel):
    ingredient_name: str
    amount: float
    unit: str

class StepItem(BaseModel):
    step_number: int
    instruction: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None # IMAGE, VIDEO, BOTH

class CreateRecipePostRequest(BaseModel):
    user_id: int
    caption: Optional[str] = None # Mô tả chung
    privacy: Optional[str] = "PUBLIC"
    recipe_title: str
    cover_image_url: str
    servings: Optional[int] = None
    cooking_time: Optional[int] = None # Thời gian nấu (phút)
    ingredients: List[IngredientItem]
    steps: List[StepItem]

class LikeRequest(BaseModel):
    user_id: int
    post_id: int

class CommentRequest(BaseModel):
    user_id: int
    post_id: int
    content: str
    parent_id: Optional[int] = None # NULL nếu là comment gốc, có ID nếu là reply

# --- API Endpoints ---
@router.get("/feed")
def get_main_feed(user_id: int, limit: int = 10, offset: int = 0):
    # TODO: Lấy danh sách bài viết hiển thị ở trang Home (Bao gồm cả Regular và Recipe)
    # Kiểm tra quyền riêng tư (PUBLIC hoặc bạn bè)
    pass

@router.get("/recipe-detail/{post_id}")
def get_recipe_detail(post_id: int):
    # TODO: Lấy chi tiết bài viết công thức khi bấm vào nút "Hướng dẫn chi tiết"
    # Trả về danh sách nguyên liệu (recipe_ingredients) và các bước (recipe_steps)
    pass
@router.post("/create-regular-post")
def create_regular_post(data: CreateRegularPostRequest):
    # TODO: Tạo bài viết thông thường (INSERT vào posts và post_media)
    pass

@router.post("/create-recipe-post")
def create_recipe_post(data: CreateRecipePostRequest):
    # TODO: Tạo bài viết công thức (INSERT vào posts, recipes, recipe_ingredients, recipe_steps)
    pass

@router.post("/like")
def toggle_like(data: LikeRequest):
    # TODO: Xử lý Thích / Bỏ thích bài viết (INSERT/DELETE vào likes và UPDATE like_count trong posts)
    pass

@router.get("/comments/{post_id}")
def get_post_comments(post_id: int):
    # TODO: Lấy danh sách bình luận của bài viết
    pass

@router.post("/comment")
def add_comment(data: CommentRequest):
    # TODO: Thêm bình luận mới (INSERT vào comments và UPDATE comment_count trong posts)
    pass