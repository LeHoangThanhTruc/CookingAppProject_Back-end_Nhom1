import sqlite3
from database import init_db, DB_NAME  # Import init_db và tên DB chuẩn từ database.py

def seed_database():
    # 1. Tự động tạo lại cấu trúc bảng mới nhất nếu chưa có
    init_db()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("Đang dọn dẹp dữ liệu cũ...")
    cursor.execute("DELETE FROM messages;")             
    cursor.execute("DELETE FROM likes;")
    cursor.execute("DELETE FROM comments;")
    cursor.execute("DELETE FROM recipe_steps;")
    cursor.execute("DELETE FROM recipe_ingredients;")
    cursor.execute("DELETE FROM recipes;")
    cursor.execute("DELETE FROM post_media;")
    cursor.execute("DELETE FROM posts;")
    cursor.execute("DELETE FROM users;")

    print("1. Đang thêm 5 Users...")
    users = [
        (1, 'chef_albert', 'albert@gmail.com', 'Chef Albert', 'https://picsum.photos/id/64/200/200'),
        (2, 'gordon_ramsay', 'gordon@gmail.com', 'Gordon Ramsay', 'https://picsum.photos/id/1025/200/200'),
        (3, 'hoa_bep_viet', 'hoabep@gmail.com', 'Hoa Bếp Việt', 'https://picsum.photos/id/1062/200/200'),
        (4, 'lan_eating', 'lan@gmail.com', 'Lan Foodie', 'https://picsum.photos/id/338/200/200'),
        (5, 'minh_masterchef', 'minh@gmail.com', 'Minh MasterChef', 'https://picsum.photos/id/1012/200/200'),
    ]
    cursor.executemany("""
        INSERT INTO users (id, username, email, full_name, avatar_url)
        VALUES (?, ?, ?, ?, ?)
    """, users)

    print("2. Đang thêm Bài viết thường (REGULAR) với Privacy đa dạng...")
    # Bài 1: REGULAR - 1 ảnh - PUBLIC (Công khai)
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (1, 1, 'REGULAR', 'Bữa sáng nhẹ nhàng với bánh mì bơ tươi ngon!', 'PUBLIC', 15, 3, 2, '2026-10-28 08:30:00');
    """)
    cursor.execute("INSERT INTO post_media (post_id, media_url, media_type) VALUES (1, 'https://picsum.photos/id/1060/600/400', 'IMAGE');")

    # Bài 2: REGULAR - 1 video - FRIENDS (Bạn bè)
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (2, 4, 'REGULAR', 'Trải nghiệm làm sinh tố dâu tây ngon tuyệt cùng bạn bè!', 'FRIENDS', 42, 8, 5, '2026-10-29 14:15:00');
    """)
    cursor.execute("INSERT INTO post_media (post_id, media_url, media_type) VALUES (2, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/DatabaseCookingApp.xlsx.mp4', 'VIDEO');")

    # Bài 3: REGULAR - Nhiều ảnh (5 ảnh để test Grid overlay +2) - ONLY_ME (Chỉ mình tôi)
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (3, 5, 'REGULAR', 'Nhật ký chuẩn bị nguyên liệu cho nhà hàng cuối tuần!', 'ONLY_ME', 5, 0, 0, '2026-10-30 19:00:00');
    """)
    cursor.executemany("INSERT INTO post_media (post_id, media_url, media_type) VALUES (?, ?, ?)", [
        (3, 'https://picsum.photos/id/292/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/493/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/1080/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/835/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/1020/600/400', 'IMAGE')
    ])

    print("3. Đang thêm Bài viết công thức (RECIPE) - PUBLIC...")
    # Bài 4: RECIPE - PUBLIC
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (4, 2, 'RECIPE', 'Bí quyết nấu Phở Bò truyền thống chuẩn vị Hà Nội', 'PUBLIC', 128, 24, 12, '2026-10-27 10:00:00');
    """)
    cursor.execute("INSERT INTO recipes (post_id, recipe_title, cover_image_url, servings, cooking_time) VALUES (4, 'Phở Bò Gia Truyền', 'https://picsum.photos/id/292/600/400', 4, 90);")
    
    ingredients = [
        (4, 'Thịt bò tươi', 500, 'gram'),
        (4, 'Bánh phở', 1, 'kg'),
        (4, 'Hành tây, hành lá', 200, 'gram'),
        (4, 'Gừng, hoa hồi, thảo quả', 50, 'gram')
    ]
    cursor.executemany("INSERT INTO recipe_ingredients (post_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?)", ingredients)
    
    steps = [
        (4, 1, 'Sơ chế thịt bò và hầm xương lấy nước dùng ngọt thanh.', 'https://picsum.photos/id/493/600/400', 'IMAGE'),
        (4, 2, 'Xem hướng dẫn chi tiết cách nêm nếm nước dùng chuẩn vị.', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'VIDEO'),
        (4, 3, 'Trần bánh phở, xếp thịt bò và chan nước dùng nóng hổi.', 'https://picsum.photos/id/1080/600/400', 'IMAGE')
    ]
    cursor.executemany("INSERT INTO recipe_steps (post_id, step_number, instruction, media_url, media_type) VALUES (?, ?, ?, ?, ?)", steps)

    print("4. Đang thêm Bài viết chia sẻ (SHARED) có Privacy riêng...")
    # Bài 5: SHARED - Share lại Bài 1 (REGULAR) - FRIENDS
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, original_post_id, like_count, comment_count, share_count, created_at) 
        VALUES (5, 3, 'SHARED', 'Món ăn sáng nhìn ngon quá chef ơi!', 'FRIENDS', 1, 10, 2, 1, '2026-10-31 09:12:00');
    """)

    # Bài 6: SHARED - Share lại Bài 4 (RECIPE) - PUBLIC
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, original_post_id, like_count, comment_count, share_count, created_at) 
        VALUES (6, 1, 'SHARED', 'Công thức phở bò tuyệt vời cho cuối tuần này!', 'PUBLIC', 4, 35, 7, 3, '2026-11-01 11:45:00');
    """)

    print("5. Đang thêm dữ liệu tương tác mẫu (Likes)...")
    likes = [
        (1, 1), # User 1 like bài 1
        (1, 4), # User 1 like bài 4
        (3, 4), # User 3 like bài 4
        (4, 2)  # User 4 like bài 2
    ]
    cursor.executemany("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", likes)

    conn.commit()
    conn.close()
    print("✅ Đã bơm dữ liệu test đa dạng (PUBLIC, FRIENDS, ONLY_ME) thành công vào database.db!")

if __name__ == "__main__":
    seed_database()