from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db

# Import các APIRouter từ thư mục features
from features import auth, main_screen, user_profile

app = FastAPI(
    title="Cooking App API",
    description="API cho ứng dụng nấu ăn kết hợp mạng xã hội",
    version="1.0.0"
)

# Cấu hình CORS cho phép ứng dụng Android kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tự động tạo bảng database nếu chưa tồn tại khi server khởi động
init_db()

# Đăng ký các router từ thư mục features vào app
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(main_screen.router, prefix="/api/posts", tags=["Main Screen Feed"])
app.include_router(user_profile.router, prefix="/api/profile", tags=["User Profile"])

@app.get("/", tags=["Root"])
def root():
    return {
        "status": "success",
        "message": "Backend Cooking App API đang chạy bình thường"
    }