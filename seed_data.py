import sys

from database import get_db, init_db
from features.auth import hash_password

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def seed_database():
    # 1. Tự động tạo lại cấu trúc bảng mới nhất nếu chưa có
    init_db()

    conn = get_db()
    cursor = conn.cursor()

    print("Đang dọn dẹp dữ liệu cũ...")
    cursor.execute("DELETE FROM friendships;")  # Dọn dẹp bảng bạn bè
    cursor.execute("DELETE FROM notifications;")
    cursor.execute("DELETE FROM follows;")
    cursor.execute("DELETE FROM cooking_schedules;")
    cursor.execute("DELETE FROM recipe_reviews;")
    cursor.execute("DELETE FROM favorites;")
    cursor.execute("DELETE FROM saved_recipes;")
    cursor.execute("DELETE FROM messages;")                      
    cursor.execute("DELETE FROM likes;")
    cursor.execute("DELETE FROM comments;")
    cursor.execute("DELETE FROM recipe_steps;")
    cursor.execute("DELETE FROM recipe_ingredients;")
    cursor.execute("DELETE FROM recipes;")
    cursor.execute("DELETE FROM post_media;")
    cursor.execute("DELETE FROM posts;")
    cursor.execute("DELETE FROM users;")

    print("1. Đang thêm 4 tài khoản demo...")
    demo_password = hash_password("Demo12345")
    users = [
        (1, 'chef_albert', 'albert@example.com', 'Chef Albert', 'https://picsum.photos/id/64/200/200', demo_password),
        (2, 'gordon_ramsay', 'gordon@example.com', 'Gordon Ramsay', 'https://picsum.photos/id/1025/200/200', demo_password),
        (3, 'hoa_bep_viet', 'hoa@example.com', 'Hoa Bếp Việt', 'https://picsum.photos/id/1062/200/200', demo_password),
        (4, 'lan_eating', 'lan@example.com', 'Lan Foodie', 'https://picsum.photos/id/338/200/200', demo_password),
    ]
    cursor.executemany("""
        INSERT INTO users (id, username, email, full_name, avatar_url, password_hash)
        VALUES (?, ?, ?, ?, ?, ?)
    """, users)

    print("2. Đang thêm Bạn bè (Friendships) cho User 1...")
    # Dữ liệu mối quan hệ bạn bè ACCEPTED
    friendships = [
        (1, 2, 'ACCEPTED'),  # User 1 là bạn của Gordon Ramsay (User 2)
        (1, 3, 'ACCEPTED'),  # User 1 là bạn của Hoa Bếp Việt (User 3)
        (1, 4, 'ACCEPTED')   # User 1 là bạn của Lan Foodie (User 4)
    ]
    cursor.executemany("""
        INSERT INTO friendships (user_id, friend_id, status)
        VALUES (?, ?, ?)
    """, friendships)

    print("3. Đang thêm Bài viết thường (REGULAR) với Privacy đa dạng...")
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

    # Bài 3: REGULAR - Nhiều ảnh - ONLY_ME (Chỉ mình tôi)
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (3, 4, 'REGULAR', 'Nhật ký chuẩn bị nguyên liệu cho nhà hàng cuối tuần!', 'ONLY_ME', 5, 0, 0, '2026-10-30 19:00:00');
    """)
    cursor.executemany("INSERT INTO post_media (post_id, media_url, media_type) VALUES (?, ?, ?)", [
        (3, 'https://picsum.photos/id/292/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/493/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/1080/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/835/600/400', 'IMAGE'),
        (3, 'https://picsum.photos/id/1020/600/400', 'IMAGE')
    ])

    print("4. Đang thêm Bài viết công thức (RECIPE) - PUBLIC...")
    # Bài 4: RECIPE - Phở Bò
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (4, 2, 'RECIPE', 'Bí quyết nấu Phở Bò truyền thống chuẩn vị Hà Nội', 'PUBLIC', 128, 24, 12, '2026-10-27 10:00:00');
    """)

    cursor.execute("""
        INSERT INTO recipes (post_id, recipe_title, cover_image_url, servings, servings_to, cooking_time, cooking_time_unit, difficulty) 
        VALUES (4, 'Phở Bò Gia Truyền', 'https://picsum.photos/id/292/600/400', 4, 6, 90, 'phút', 'Trung bình');
    """)
    
    ingredients_4 = [
        (4, 'Thịt bò tươi', 500, 'gram'),
        (4, 'Bánh phở', 1, 'kg'),
        (4, 'Hành tây, hành lá', 200, 'gram'),
        (4, 'Gừng, hoa hồi, thảo quả', 50, 'gram')
    ]
    cursor.executemany("INSERT INTO recipe_ingredients (post_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?)", ingredients_4)
    
    steps_4 = [
        (4, 1, 'Sơ chế thịt bò và hầm xương lấy nước dùng ngọt thanh.', 'https://picsum.photos/id/493/600/400', 'IMAGE'),
        (4, 2, 'Xem hướng dẫn chi tiết cách nêm nếm nước dùng chuẩn vị.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/DatabaseCookingApp.xlsx.mp4', 'VIDEO'),
        (4, 3, 'Trần bánh phở, xếp thịt bò và chan nước dùng nóng hổi.', 'https://picsum.photos/id/1080/600/400', 'IMAGE')
    ]
    cursor.executemany("INSERT INTO recipe_steps (post_id, step_number, instruction, media_url, media_type) VALUES (?, ?, ?, ?, ?)", steps_4)

    # Bài 5: Thêm một Bài viết công thức mới thay thế cho bài share (RECIPE - Bánh ngọt)
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (5, 3, 'RECIPE', 'Hướng dẫn làm bánh bông lan trứng muối mềm xốp tại nhà cực đơn giản.', 'PUBLIC', 85, 12, 4, '2026-10-31 09:12:00');
    """)

    cursor.execute("""
        INSERT INTO recipes (post_id, recipe_title, cover_image_url, servings, servings_to, cooking_time, cooking_time_unit, difficulty) 
        VALUES (5, 'Bánh Bông Lan Trứng Muối', 'https://picsum.photos/id/365/600/400', 6, 8, 45, 'phút', 'Dễ');
    """)

    ingredients_5 = [
        (5, 'Bột mì số 8', 150, 'gram'),
        (5, 'Trứng gà', 4, 'quả'),
        (5, 'Đường cát', 100, 'gram'),
        (5, 'Trứng muối', 6, 'lòng đỏ')
    ]
    cursor.executemany("INSERT INTO recipe_ingredients (post_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?)", ingredients_5)

    steps_5 = [
        (5, 1, 'Đánh bông trứng với đường cho đến khi chuyển màu kem mịn.', 'https://picsum.photos/id/365/600/400', 'IMAGE'),
        (5, 2, 'Trộn đều bột mì vào hỗn hợp trứng và đem nướng trong lò.', 'https://picsum.photos/id/1062/600/400', 'IMAGE')
    ]
    cursor.executemany("INSERT INTO recipe_steps (post_id, step_number, instruction, media_url, media_type) VALUES (?, ?, ?, ?, ?)", steps_5)

    # Bài 6: Thêm một Bài viết thường mới thay thế cho bài share (REGULAR - Mẹo vặt)
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (6, 1, 'REGULAR', 'Mẹo giữ rau xanh tươi lâu trong tủ lạnh cả tuần không bị héo!', 'PUBLIC', 56, 14, 9, '2026-11-01 11:45:00');
    """)
    cursor.execute("INSERT INTO post_media (post_id, media_url, media_type) VALUES (6, 'https://picsum.photos/id/429/600/400', 'IMAGE');")

    print("6. Đang thêm Tin nhắn thông thường (Messages)...")
    # Tin nhắn mẫu không gắn kèm shared_post_id (hoặc để NULL)
    messages = [
        (1, 2, 'Chào chef Albert, tuần này anh có dự định món mới nào chưa?'), 
        (4, 1, 'Cảm ơn công thức phở bò của anh nhé, rất tuyệt vời!')    
    ]
    cursor.executemany("""
        INSERT INTO messages (sender_id, receiver_id, message_text)
        VALUES (?, ?, ?)
    """, messages)

    print("7. Đang thêm dữ liệu tương tác mẫu (Likes)...")
    likes = [
        (1, 1), # User 1 like bài 1
        (1, 4), # User 1 like bài 4
        (3, 4), # User 3 like bài 4
        (4, 2), # User 4 like bài 2
        (2, 5), # Gordon Ramsay like bài 5
        (4, 6)  # Lan Foodie like bài 6
    ]
    cursor.executemany("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", likes)

    print("8. Đang thêm yêu thích, công thức đã lưu và lịch nấu mẫu...")
    cursor.executemany("INSERT INTO favorites (user_id, recipe_id) VALUES (?, ?)", [(1, 4), (1, 5)])
    cursor.executemany("INSERT INTO saved_recipes (user_id, recipe_id) VALUES (?, ?)", [(1, 4), (1, 5)])
    cursor.execute(
        "INSERT INTO cooking_schedules (user_id, recipe_id, scheduled_for, note) VALUES (?, ?, ?, ?)",
        (1, 4, "2026-11-11T18:00:00", "Bữa tối demo"),
    )
    cursor.execute(
        "INSERT INTO recipe_reviews (recipe_id, user_id, rating, content) VALUES (?, ?, ?, ?)",
        (4, 1, 5, "Công thức dễ làm và rất ngon"),
    )

    conn.commit()
    conn.close()
    print("Đã bơm dữ liệu test đầy đủ (Users, Friendships, Posts, Messages, Likes - Không có bài Share) vào database.db!")

if __name__ == "__main__":
    seed_database()
