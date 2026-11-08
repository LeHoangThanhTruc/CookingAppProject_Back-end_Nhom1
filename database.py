import os
import sqlite3
from pathlib import Path

DB_NAME = "database.db"


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
    
    # 1. Bảng Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone_number TEXT,
            password_hash TEXT,
            full_name TEXT,
            avatar_url TEXT,
            bio TEXT, --Tiếu sử cá nhân
            auth_provider TEXT DEFAULT 'LOCAL', --LOCAL, GOOGLE, FACEBOOK
            provider_id TEXT, --ID định danh từ Google/Facebook
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP DEFAULT NULL,
            last_logout_at TIMESTAMP DEFAULT NULL
        )
    ''')

    # 2. Bảng Friendships
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friendships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (friend_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
 
    # 3. Bảng Posts (lưu thông tin của tất cả các bài đăng trên feed hoặc trang cá nhân)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- Mã bài viết
            user_id INTEGER NOT NULL, --id người đăng
            post_type TEXT NOT NULL, -- REGULAR, RECIPE, hoặc SHARED
            caption TEXT,
            privacy TEXT DEFAULT 'PUBLIC', -- PUBLIC, FRIENDS, ONLY_ME
            original_post_id INTEGER DEFAULT NULL, -- ID bài viết gốc nếu là bài share lại
            like_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, --Khi một tài khoản trong bảng users bị xóa (VD: User xóa tài khoản), toàn bộ bài viết (posts) của người đó sẽ tự động bị xóa theo
            FOREIGN KEY (original_post_id) REFERENCES posts(id) ON DELETE CASCADE --Nếu chủ bài viết gốc xóa bài viết gốc, thì tất cả các bài viết chia sẻ lại (SHARED) liên kết tới nó cũng sẽ tự động bị xóa khỏi hệ thống.
        )
    ''')
    
    # 4. Bảng Post_Media (Quản lý Ảnh/Video bài đăng thường) 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- id của từng ảnh/video trong bài viết
            post_id INTEGER NOT NULL, -- Mã bài viết
            media_url TEXT NOT NULL,
            media_type TEXT NOT NULL, -- Loại phương tiện: IMAGE, VIDEO,EXCEL,..
            like_count INTEGER DEFAULT 0,    
            comment_count INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    ''')

    # 5. Bảng Recipes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            post_id INTEGER PRIMARY KEY, -- Liên kết với bảng posts
            recipe_title TEXT NOT NULL, -- Tên món ăn
            cover_image_url TEXT NOT NULL, -- Ảnh bìa món ăn
            servings INTEGER, -- Khẩu phần ăn (từ bao nhiêu người)
            servings_to INTEGER DEFAULT 0, -- Khẩu phần ăn tối đa (ví dụ: 2-4 người)
            cooking_time INTEGER, -- Thời gian nấu
            cooking_time_unit TEXT DEFAULT 'phút', -- Đơn vị thời gian: phút, giờ,...
            difficulty TEXT DEFAULT 'Dễ', -- Độ khó: Dễ, Trung bình, Khó
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    ''')

    # 6. Bảng Recipe_Ingredients (cụ thể từng mục nguyên liệu của công thức nấu ăn)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, --ID nguyên liệu
            post_id INTEGER NOT NULL, --thuộc công thức nào 
            ingredient_name TEXT NOT NULL, --tên nguyên liệu
            amount REAL NOT NULL, --số lượng nguyên liệu
            unit TEXT NOT NULL, --đơn vị đo lường (gram, kg, ml, lít, muỗng, cốc,...)
            FOREIGN KEY (post_id) REFERENCES recipes(post_id) ON DELETE CASCADE
        )
    ''')

    # 7. Bảng Recipe_Steps
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipe_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            instruction TEXT NOT NULL,
            media_url TEXT,
            media_type TEXT DEFAULT 'IMAGE', -- IMAGE hoặc VIDEO
            FOREIGN KEY (post_id) REFERENCES recipes(post_id) ON DELETE CASCADE
        )
    ''')

    # 8. Bảng Comments (Lưu nội dung bình luận của người dùng dưới các bài viết)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            media_id INTEGER DEFAULT 0,
            user_id INTEGER NOT NULL,
            parent_id INTEGER DEFAULT NULL,
            content TEXT,
            media_url TEXT,
            media_type TEXT,
            like_count_com_post_chung INTEGER DEFAULT 0,
            dislike_count_com_post_chung INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # 9. Bảng Likes (lưu vết chính xác ai đã thả tim bài viết nào vào thời điểm nào)
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
    # 10. Bảng Messages (chức năng share bài viết cho bạn bè kèm tin nhắn)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- id lần share đó
            sender_id INTEGER NOT NULL, --id người gửi
            receiver_id INTEGER NOT NULL, --id người nhận
            message_text TEXT,--tin nhắn kèm theo
            shared_post_id INTEGER, --id bài viết được share
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (shared_post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
    ''')
    # 11. Bảng Post_Media_Likes (Thả tim riêng cho từng ảnh/video)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_media_likes (
            user_id INTEGER NOT NULL,
            media_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, media_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (media_id) REFERENCES post_media(id) ON DELETE CASCADE
        )
    ''')

    # 12. Bảng Post_Media_Comments (Bình luận riêng cho từng ảnh/video)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_media_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            parent_id INTEGER DEFAULT NULL,
            content TEXT,
            media_url TEXT,
            media_type TEXT,
            like_count_com_media INTEGER DEFAULT 0,
            dislike_count_com_media INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (media_id) REFERENCES post_media(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    # 13. Bảng Comment_Reactions (Quản lý Like / Dislike từng bình luận)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comment_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            comment_id INTEGER NOT NULL,
            reaction_type TEXT CHECK(reaction_type IN ('LIKE', 'DISLIKE', 'NONE')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, comment_id),
            FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    # Tạo Indexes tối ưu tốc độ truy vấn Newsfeed
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_media_id ON comments(media_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_post_media_likes_media_id ON post_media_likes(media_id);")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Khởi tạo toàn bộ cơ sở dữ liệu thành công!")
