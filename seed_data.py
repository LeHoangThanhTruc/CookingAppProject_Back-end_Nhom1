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
    friendships = [
        (1, 2, 'ACCEPTED'),  # User 1 là bạn của Gordon Ramsay (User 2)
        (1, 3, 'ACCEPTED'),  # User 1 là bạn của Hoa Bếp Việt (User 3)
        (1, 4, 'ACCEPTED')   # User 1 là bạn của Lan Foodie (User 4)
    ]
    cursor.executemany("""
        INSERT INTO friendships (user_id, friend_id, status)
        VALUES (?, ?, ?)
    """, friendships)

    print("3. Đang thêm Bài viết thường (REGULAR) chất lượng mới...")
    # Bài 1: Nhiều ảnh bánh ngọt
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (1, 4, 'REGULAR', 'Hôm nay nhóm tụi mình đã làm được rất nhiều bánh luôn', 'PUBLIC', 25, 4, 2, '2026-10-28 08:30:00');
    """)
    cursor.executemany("INSERT INTO post_media (post_id, media_url, media_type) VALUES (?, ?, ?)", [
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake1.PNG', 'IMAGE'),
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake2.PNG', 'IMAGE'),
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake3.PNG', 'IMAGE'),
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake4.PNG', 'IMAGE'),
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake5.PNG', 'IMAGE'),
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake6.PNG', 'IMAGE'),
        (1, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/cake/Cake7.PNG', 'IMAGE')
    ])

    # Bài 2: Bánh cuốn
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (2, 3, 'REGULAR', 'Bánh cuốn chỗ này ngon ghê, ăn xong giờ còn thèm', 'FRIENDS', 18, 3, 1, '2026-10-29 14:15:00');
    """)
    cursor.execute("INSERT INTO post_media (post_id, media_url, media_type) VALUES (2, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/BanhCuonChoNayNgon.PNG', 'IMAGE');")

    # Bài 3: Bữa trưa ngon miệng
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (3, 1, 'REGULAR', 'tui cỡ này, bạn cỡ nào', 'PUBLIC', 30, 6, 4, '2026-10-30 19:00:00');
    """)
    cursor.execute("INSERT INTO post_media (post_id, media_url, media_type) VALUES (3, 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/BuaTruaNgonMieng.PNG', 'IMAGE');")

    print("4. Đang thêm Bài viết công thức (RECIPE) chất lượng mới...")
    
    # --- Bài 4: Thịt kho tiêu ---
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (4, 1, 'RECIPE', 'Nồi thịt kho tiêu ngon nhất mình từng ăn, không cần nước dừa mà vẫn đậm đà tốn cơm.', 'PUBLIC', 128, 24, 12, '2026-10-27 10:00:00');
    """)
    cursor.execute("""
        INSERT INTO recipes (post_id, recipe_title, cover_image_url, servings, servings_to, cooking_time, cooking_time_unit, difficulty) 
        VALUES (4, 'Thịt kho tiêu', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_kho_tieu/ThitKhoTieu_MinhHoaNguyenLieu.PNG', 1, 2, 45, 'phút', 'Dễ');
    """)
    ingredients_4 = [
        (4, 'Thịt heo ba chỉ', 420, 'gram'),
        (4, 'Ớt cay', 2, 'trái'),
        (4, 'Hành lá', 2, 'cây'),
        (4, 'Hành khô', 3, 'củ'),
        (4, 'Hạt nêm', 1, 'thìa canh'),
        (4, 'Đường', 4, 'thìa canh'),
        (4, 'Nước tương', 1, 'thìa canh'),
        (4, 'Nước mắm', 1, 'thìa canh'),
        (4, 'Tương ớt', 1, 'thìa canh'),
        (4, 'Tiêu xay', 2, 'thìa canh')
    ]
    cursor.executemany("INSERT INTO recipe_ingredients (post_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?)", ingredients_4)
    steps_4 = [
        (4, 1, 'Sơ chế thịt ba chỉ trước khi nấu. Rửa thịt ba chỉ bằng nước muối. Sau đó cắt thịt ba chỉ thành từng lạng mỏng rồi thái thành từng miếng nhỏ. Ướp thịt trước với 1 thìa canh đường làm cho thịt được trong mỡ và lên màu đẹp, trộn đều và ướp trong khoảng 10 phút.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_kho_tieu/ThitKhoTieu_B1.mp4', 'VIDEO'),
        (4, 2, 'Sơ chế hành lá, hành khô, ớt. Băm nhỏ hành khô, hành lá, ớt.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_kho_tieu/ThitKhoTieu_B2.mp4', 'VIDEO'),
        (4, 3, 'Xào sơ thịt trong chảo. Cho dầu vào chảo, lửa vừa, phi thơm hành tỏi rồi cho thịt vào đảo đều. Khi miếng thịt săn lại và hơi vàng nhẹ thì đổ ra nồi đất (chảo,…) để kho.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_kho_tieu/ThitKhoTieu_B3.mp4', 'VIDEO'),
        (4, 4, 'Làm nước kho. Làm nước hàng: 2 thìa canh đường, 1 chút nước. Không dùng đũa, chỉ lắc chảo để tránh bị vón cục, đun cho tới khi chuyển màu cánh gián, tới màu này thì tắt bếp và thêm chút nước nữa là được, sau đó tắt bếp rồi đổ vô thịt luôn. Nêm: 1 thìa canh (hạt nêm, đường, nước tương, nước mắm, tương ớt, tiêu xay và trộn đều.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_kho_tieu/ThitKhoTieu_B4.mp4', 'VIDEO'),
        (4, 5, 'Kho thịt. Thêm nước xăm xắp bề mặt, nếu có bọt thì gạn đi, kho tới khi nước keo sệt lại thì tắt bếp là được. Thêm một chút hành lá, ớt và tiêu xay lên bề mặt món ăn cho hấp dẫn.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_kho_tieu/ThitKhoTieu_B5.mp4', 'VIDEO')
    ]
    cursor.executemany("INSERT INTO recipe_steps (post_id, step_number, instruction, media_url, media_type) VALUES (?, ?, ?, ?, ?)", steps_4)

    # --- Bài 5: Thịt ba chỉ chiên nước mắm ---
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (5, 2, 'RECIPE', 'Thịt Ba Chỉ Chiên Nước Mắm - Cách Làm Thịt Chiên Vàng Mềm Ngon Không Bị Khô Cứng', 'PUBLIC', 95, 15, 6, '2026-10-28 11:00:00');
    """)
    cursor.execute("""
        INSERT INTO recipes (post_id, recipe_title, cover_image_url, servings, servings_to, cooking_time, cooking_time_unit, difficulty) 
        VALUES (5, 'Thịt ba chỉ chiên nước mắm', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_ba_chi_chien_nuoc_mam/TBCCNM_NguyenLieu_B2.PNG', 1, 2, 30, 'phút', 'Dễ');
    """)
    ingredients_5 = [
        (5, 'Thịt ba chỉ', 500, 'gram'),
        (5, 'Gừng', 20, 'gram'),
        (5, 'Muối', 1, 'muỗng café'),
        (5, 'Hành tím', 20, 'gram'),
        (5, 'Gốc hành lá', 10, 'gram'),
        (5, 'Bột bắp', 1, 'muỗng canh'),
        (5, 'Hạt nêm', 1, 'muỗng café'),
        (5, 'Tương ớt chua ngọt', 1, 'muỗng canh'),
        (5, 'Nước mắm', 2, 'muỗng canh')
    ]
    cursor.executemany("INSERT INTO recipe_ingredients (post_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?)", ingredients_5)
    steps_5 = [
        (5, 1, 'Cắt thịt ba chỉ thành miếng vừa ăn, lấy gừng đã đập dập và 1 muỗng cà phê muối cho vào thịt đã cắt rồi chần sơ qua nước sôi khoảng 1-2 phút, sau đó xả lại nước và để ráo.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_ba_chi_chien_nuoc_mam/TBCCNM_B1.mp4', 'VIDEO'),
        (5, 2, 'Cho lần lượt 20g hành tím, 10g gừng, 10 gốc hành lá vào cối xoay và xoay nhuyễn. Trước khi bỏ vào cối xoay có thể cắt nguyên liệu thành lát nhỏ để dễ xoay nhuyễn. Không có cối xoay thì có thể dùng dao băm nhuyễn.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_ba_chi_chien_nuoc_mam/TBCCNM_B2.mp4', 'VIDEO'),
        (5, 3, 'Cho 1 muỗng canh bột bắp vào thịt đã để ráo phía trên và xốc đều, khi rang không bị vàng, thịt mềm, không bị khô.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_ba_chi_chien_nuoc_mam/TBCCNM_B3.mp4', 'VIDEO'),
        (5, 4, 'Chiên thịt với lửa lớn, đảo đều liên tục, chiên đến khi thịt cháy cạnh ra mỡ thì thêm hành tỏi gừng xay (đã làm ở bước 2) vào chảo thịt và đảo đều phi thơm, sau đó cho ½ muỗng canh đường + 1 muỗng cafe hạt nêm + 1 muỗng canh tương ớt chua ngọt + 2 muỗng canh nước mắm và bắt đầu đảo đều lại nhưng với lửa nhỏ. Đảo đến khi thịt vàng lên màu đẹp thì tắt bếp, cho hành lá đã cắt khúc vào chảo đảo vài lần cho thơm rồi dừng lại và thưởng thức.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/thit_ba_chi_chien_nuoc_mam/TBCCNM_B4.mp4', 'VIDEO')
    ]
    cursor.executemany("INSERT INTO recipe_steps (post_id, step_number, instruction, media_url, media_type) VALUES (?, ?, ?, ?, ?)", steps_5)

    # --- Bài 6: Trứng sốt thịt bằm ---
    cursor.execute("""
        INSERT INTO posts (id, user_id, post_type, caption, privacy, like_count, comment_count, share_count, created_at) 
        VALUES (6, 3, 'RECIPE', 'Trứng chiên kiểu này siêu ngon!', 'PUBLIC', 110, 19, 8, '2026-10-29 16:30:00');
    """)
    cursor.execute("""
        INSERT INTO recipes (post_id, recipe_title, cover_image_url, servings, servings_to, cooking_time, cooking_time_unit, difficulty) 
        VALUES (6, 'Trứng sốt thịt bằm', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/trung_sot_thit_bam/TrungSotThitBam_HinhAnhMonAn_B3.PNG', 1, 2, 30, 'phút', 'Dễ');
    """)
    ingredients_6 = [
        (6, 'Thịt xay', 300, 'gram'),
        (6, 'Trứng cút', 20, 'quả'),
        (6, 'Hành tím', 2, 'củ'),
        (6, 'Tỏi', 3, 'tép'),
        (6, 'Hành lá', 8, 'nhánh'),
        (6, 'Ngò rí', 1, 'bó nhỏ'),
        (6, 'Ớt', 2, 'trái'),
        (6, 'Nước mắm', 1, 'thìa canh'),
        (6, 'Nước tương', 1, 'thìa canh'),
        (6, 'Tương ớt', 1, 'thìa canh'),
        (6, 'Hạt nêm', 0.33, 'thìa canh'),
        (6, 'Đường', 0.5, 'thìa canh'),
        (6, 'Tiêu xay', 0.5, 'thìa canh'),
        (6, 'Nước', 0.5, 'chén'),
        (6, 'Dầu ăn', 2, 'thìa')
    ]
    cursor.executemany("INSERT INTO recipe_ingredients (post_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?)", ingredients_6)
    steps_6 = [
        (6, 1, 'Đập dập và băm nhỏ 2 củ hành tím, 3 tép tỏi; thái nhỏ 8 nhánh hành lá, 1 bó nhỏ ngò rí, 2 trái ớt; đập hết 20 quả trứng ra tô.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/trung_sot_thit_bam/TrungSotThitBam_B1.mp4', 'VIDEO'),
        (6, 2, 'Cho 1 thìa canh nước mắm, 1 thìa canh nước tương, 1 thìa canh tương ớt, 1/3 thìa canh hạt nêm, ½ thìa canh đường, ½ thìa canh tiêu xay, 1/2 chén nước vào chén rồi khuấy đều.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/trung_sot_thit_bam/TrungSotThitBam_B2.mp4', 'VIDEO'),
        (6, 3, 'Bắt chảo lên bếp và cho 2 thìa dầu ăn vào, sau khi dầu nóng thì cho hành tỏi băm nhỏ vào phi thơm. Khi hành tỏi bắt đầu xém vàng rồi thì đổ thịt vào, đồng thời hạ nhỏ lửa, dằm thịt ra cho tơi, sau đó từ từ tăng lửa lên và đảo từ từ đến khi thịt săn lại. Khi thịt đã săn lại thì cho một nửa số hành ngò và ớt vào, đảo lên rồi tiếp tục rưới một nửa phần nước sốt và đảo vài lần nữa. Để mức lửa vừa rồi đổ trứng cút vào rồi rưới nốt phần nước sốt còn lại lên bề mặt. Đậy nắp lại chờ nó chín, tùy theo việc muốn trứng lòng đào hay trứng chín kỹ mà đậy nắp bao lâu. Tới khi nước cạn thì trứng cũng đã chín rồi, mở nắp và rắc phần hành ngò ớt còn lại lên, có thể rắc chút tiêu lên bề mặt cho thơm. Món này có thể ăn chung với cơm hoặc bánh mì đều rất ngon.', 'https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev/trung_sot_thit_bam/TrungSotThitBam_B3.mp4', 'VIDEO')
    ]
    cursor.executemany("INSERT INTO recipe_steps (post_id, step_number, instruction, media_url, media_type) VALUES (?, ?, ?, ?, ?)", steps_6)

    print("5. Đang thêm Tin nhắn thông thường (Messages)...")
    messages = [
        (1, 2, 'Chào chef Albert, tuần này anh có dự định món mới nào chưa?'), 
        (4, 1, 'Cảm ơn công thức thịt kho tiêu của anh nhé, rất tuyệt vời!')    
    ]
    cursor.executemany("""
        INSERT INTO messages (sender_id, receiver_id, message_text)
        VALUES (?, ?, ?)
    """, messages)

    print("6. Đang thêm dữ liệu tương tác mẫu (Likes)...")
    likes = [
        (1, 1), # User 1 like bài 1
        (1, 4), # User 1 like bài 4
        (3, 4), # User 3 like bài 4
        (4, 2), # User 4 like bài 2
        (2, 5), # Gordon Ramsay like bài 5
        (4, 6)  # Lan Foodie like bài 6
    ]
    cursor.executemany("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", likes)

    print("7. Đang thêm yêu thích, công thức đã lưu và lịch nấu mẫu...")
    cursor.executemany("INSERT INTO favorites (user_id, recipe_id) VALUES (?, ?)", [(1, 4), (1, 5), (1, 6)])
    cursor.executemany("INSERT INTO saved_recipes (user_id, recipe_id) VALUES (?, ?)", [(1, 4), (1, 5), (1, 6)])
    cursor.execute(
        "INSERT INTO cooking_schedules (user_id, recipe_id, scheduled_for, note) VALUES (?, ?, ?, ?)",
        (1, 4, "2026-11-11T18:00:00", "Nấu món thịt kho tiêu"),
    )
    cursor.execute(
        "INSERT INTO recipe_reviews (recipe_id, user_id, rating, content) VALUES (?, ?, ?, ?)",
        (4, 1, 5, "Công thức siêu tốn cơm, rất dễ làm!"),
    )

    conn.commit()
    conn.close()
    print("Đã cập nhật bộ dữ liệu mẫu mới (Thịt kho tiêu, Ba chỉ chiên nước mắm, Trứng sốt thịt bằm và các bài viết thường) thành công vào database.db!")

if __name__ == "__main__":
    seed_database()