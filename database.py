import os
import sqlite3
from pathlib import Path

DB_NAME = "database.db"

# Hàm lấy kết nối đến Database
def get_db():
    database_path = os.getenv("DATABASE_PATH", DB_NAME)
    if database_path != ":memory:":
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    # Bật tính năng ràng buộc khóa ngoại (Foreign Key) trong SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# Hàm khởi tạo toàn bộ các bảng trong CSDL khi ứng dụng bắt đầu chạy
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Bảng Users (Tài khoản & Profile)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone_number TEXT,
            password_hash TEXT, -- NULLABLE để hỗ trợ đăng nhập OAuth (Google/Facebook)
            full_name TEXT,
            avatar_url TEXT,
            bio TEXT,
            auth_provider TEXT DEFAULT 'LOCAL', -- LOCAL, GOOGLE, FACEBOOK
            provider_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP DEFAULT NULL, -- Thời gian đăng nhập gần nhất
            last_logout_at TIMESTAMP DEFAULT NULL-- Thời gian đăng xuất gần nhất
        )
    ''')

    # 2. Bảng Friendships (Mối quan hệ bạn bè)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friendships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            status TEXT DEFAULT 'PENDING', -- PENDING, ACCEPTED, BLOCKED
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (friend_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # 3. Bảng Posts (Bài viết chung)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_type TEXT NOT NULL, -- REGULAR (Thường) hoặc RECIPE (Công thức)
            caption TEXT,
            privacy TEXT DEFAULT 'PUBLIC', -- PUBLIC, FRIENDS, ONLY_ME
            like_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # 4. Bảng Post_Media (Hình ảnh/Video cho bài viết thông thường)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            media_url TEXT NOT NULL,
            media_type TEXT NOT NULL, -- IMAGE hoặc VIDEO
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    ''')

    # 5. Bảng Recipes (Chi tiết bài viết công thức)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            post_id INTEGER PRIMARY KEY,
            recipe_title TEXT NOT NULL,
            cover_image_url TEXT NOT NULL,
            servings INTEGER,
            cooking_time INTEGER, -- Tính theo phút
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    ''')

    # 6. Bảng Recipe_Ingredients (Nguyên liệu)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            ingredient_name TEXT NOT NULL,
            amount REAL NOT NULL,
            unit TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES recipes(post_id) ON DELETE CASCADE
        )
    ''')

    # 7. Bảng Recipe_Steps (Các bước thực hiện)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipe_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            instruction TEXT NOT NULL,
            media_url TEXT,
            media_type TEXT, -- IMAGE, VIDEO, hoặc BOTH
            FOREIGN KEY (post_id) REFERENCES recipes(post_id) ON DELETE CASCADE
        )
    ''')

    # 8. Bảng Comments (Bình luận)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            parent_id INTEGER, -- Chứa ID cmt gốc nếu là reply, NULL nếu là cmt cha
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
        )
    ''')

    # 9. Bảng Likes (Lượt thích)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, post_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Khởi tạo toàn bộ cơ sở dữ liệu thành công!")
