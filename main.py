import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import init_db

# Import các APIRouter từ thư mục features
from features import auth, main_screen, recipes, social, user_profile

load_dotenv()
secret = os.getenv("JWT_SECRET_KEY", "").strip()
if not secret or secret == "replace-with-a-long-random-secret" or len(secret) < 32:
    raise RuntimeError("JWT_SECRET_KEY phải được cấu hình bằng chuỗi bí mật dài ít nhất 32 ký tự")

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

upload_directory = Path(os.getenv("UPLOAD_DIR", "uploads")).expanduser().resolve()
upload_directory.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_directory)), name="uploads")

# Đăng ký các router từ thư mục features vào app
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(main_screen.router, prefix="/api/posts", tags=["Main Screen Feed"])
app.include_router(user_profile.router, prefix="/api/profile", tags=["User Profile"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"])
app.include_router(recipes.schedule_router, prefix="/api/schedules", tags=["Cooking Schedule"])
app.include_router(social.router, prefix="/api/social", tags=["Social"])
app.include_router(social.message_router, prefix="/api/messages", tags=["Messages"])
app.include_router(social.notification_router, prefix="/api/notifications", tags=["Notifications"])

@app.get("/", tags=["Root"])
def root():
    return {
        "status": "success",
        "message": "Backend Cooking App API đang chạy bình thường"
    }

@app.get("/health", tags=["Health"])
def health():
    from database import get_db

    connection = get_db()
    try:
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
    probe = upload_directory / ".healthcheck"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)
    return {"status": "ok", "database": "ok", "uploads": "ok"}
