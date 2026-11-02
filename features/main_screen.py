from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from database import get_db
from services.cloud_storage import upload_file_to_cloud
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

# --- Request Models ---
class ShareToFeedRequest(BaseModel):
    user_id: int
    caption: Optional[str] = ""
    privacy: str = "PUBLIC"  # PUBLIC, FRIENDS, ONLY_ME

class ShareToMessageRequest(BaseModel):
    sender_id: int
    receiver_ids: List[int]  # Danh sách ID bạn bè nhận tin nhắn
    message_text: Optional[str] = ""


# --- 1. API Upload Ảnh/Video lên Cloudflare R2 ---
@router.post("/upload")
async def upload_media(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        media_url = upload_file_to_cloud(
            file_bytes=contents,
            filename=file.filename,
            content_type=file.content_type
        )
        return {
            "status": "success",
            "media_url": media_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi upload: {str(e)}")


# --- HÀM BỔ SUNG CHI TIẾT MEDIA / RECIPE CHO BÀI VIẾT ---
def _get_post_details(cursor, post_id: int, post_type: str):
    details = {}
    
    # 1. BẮT BUỘC: Lấy danh sách Ảnh/Video từ bảng post_media
    cursor.execute("""
        SELECT media_url, media_type 
        FROM post_media 
        WHERE post_id = ?
    """, (post_id,))
    media_rows = cursor.fetchall()
    
    # Tạo danh sách media khớp chuẩn với Android Model (trả về cả "url" và "media_url" để chắc chắn 100%)
    media_list = []
    for m_url, m_type in media_rows:
        media_list.append({
            "url": m_url,          # Khớp với @SerializedName("url") trong Post.java của bạn
            "media_url": m_url,    # Backup nếu Android dùng media_url
            "type": m_type,        # Khớp với @SerializedName("type")
            "media_type": m_type   # Backup
        })
    details["media_list"] = media_list

    # 2. Nếu là bài RECIPE -> Lấy thêm thông tin công thức
    if post_type == "RECIPE":
        cursor.execute("""
            SELECT recipe_title, cover_image_url, servings, cooking_time 
            FROM recipes 
            WHERE post_id = ?
        """, (post_id,))
        r_row = cursor.fetchone()
        if r_row:
            r_title, r_cover, r_servings, r_time = r_row
            
            # Lấy nguyên liệu
            cursor.execute("SELECT ingredient_name, amount, unit FROM recipe_ingredients WHERE post_id = ?", (post_id,))
            ing_rows = cursor.fetchall()
            ingredients = [{"name": i[0], "amount": f"{i[1]} {i[2]}".strip()} for i in ing_rows]
            
            # Lấy các bước làm
            cursor.execute("SELECT step_number, instruction FROM recipe_steps WHERE post_id = ? ORDER BY step_number ASC", (post_id,))
            step_rows = cursor.fetchall()
            steps = [{"step": s[0], "instruction": s[1]} for s in step_rows]
            
            details["recipe_details"] = {
                "title": r_title,
                "cover_image_url": r_cover,
                "ingredients": ingredients,
                "steps": steps
            }
            
    return details


# --- API Lấy danh sách Newsfeed ---
@router.get("/feed")
def get_main_feed(post_type: str = "ALL", current_user_id: int = 1):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # LEFT JOIN với bài viết gốc (orig_p) để lấy loại thực sự của bài gốc nếu là bài SHARED
        query = """
            SELECT p.id, p.post_type, p.caption, p.like_count, p.comment_count, p.share_count, p.created_at, p.original_post_id, p.privacy,
                   u.id as user_id, u.full_name, u.avatar_url,
                   (SELECT 1 FROM likes WHERE user_id = ? AND post_id = p.id) as is_liked,
                   COALESCE(orig_p.post_type, p.post_type) as effective_type
            FROM posts p
            JOIN users u ON p.user_id = u.id
            LEFT JOIN posts orig_p ON p.original_post_id = orig_p.id
        """
        params = [current_user_id]

        # Lọc dựa trên effective_type
        # --- Lọc dựa trên loại bài viết bản thân HOẶC loại bài viết gốc (nếu là bài Share) ---
        if post_type == "REGULAR":
            # Lấy các bài REGULAR hoặc bài SHARED mà bài gốc là REGULAR
            query += " WHERE p.post_type = 'REGULAR' OR (p.post_type = 'SHARED' AND orig_p.post_type = 'REGULAR')"
        elif post_type == "RECIPE":
            # Lấy các bài RECIPE hoặc bài SHARED mà bài gốc là RECIPE
            query += " WHERE p.post_type = 'RECIPE' OR (p.post_type = 'SHARED' AND orig_p.post_type = 'RECIPE')"

        # Giữ nguyên dòng sắp xếp thời gian
        query += " ORDER BY p.created_at DESC"
        cursor.execute(query, params)
        posts_raw = cursor.fetchall()

        feed_list = []
        for row in posts_raw:
            post_id, p_type, caption, like_count, comment_count, share_count, created_at, original_post_id, privacy, user_id, full_name, avatar_url, is_liked, effective_type = row
            
            post_data = {
                "post_id": post_id,
                "post_type": p_type,
                "caption": caption if caption else "",
                "privacy": privacy if privacy else "PUBLIC",
                "like_count": like_count if like_count else 0,
                "comment_count": comment_count if comment_count else 0,
                "share_count": share_count if share_count else 0,
                "created_at": created_at if created_at else "",
                "is_liked": True if is_liked else False,
                "author": {
                    "user_id": user_id,
                    "full_name": full_name,
                    "avatar_url": avatar_url
                }
            }

            # Lấy media/recipe cho bản thân bài viết
            details = _get_post_details(cursor, post_id, p_type)
            post_data.update(details)

            # Nếu là bài SHARED -> Nạp đầy đủ 8 cột thông tin chi tiết bài viết gốc
            if p_type == "SHARED" and original_post_id:
                cursor.execute("""
                    SELECT p.id, p.post_type, p.caption, p.privacy, p.created_at, u.id, u.full_name, u.avatar_url
                    FROM posts p
                    JOIN users u ON p.user_id = u.id
                    WHERE p.id = ?
                """, (original_post_id,))
                orig_row = cursor.fetchone()
                
                if orig_row:
                    # Khớp đúng 8 cột dữ liệu trả về từ SELECT
                    orig_id, orig_type, orig_caption, orig_privacy, orig_created_at, orig_u_id, orig_u_name, orig_u_avatar = orig_row
                    orig_details = _get_post_details(cursor, orig_id, orig_type)
                    
                    post_data["original_post"] = {
                        "post_id": orig_id,
                        "post_type": orig_type,
                        "caption": orig_caption if orig_caption else "",
                        "privacy": orig_privacy if orig_privacy else "PUBLIC",
                        "created_at": orig_created_at if orig_created_at else "",
                        "author": {
                            "user_id": orig_u_id,
                            "full_name": orig_u_name,
                            "avatar_url": orig_u_avatar
                        },
                        **orig_details
                    }

            feed_list.append(post_data)

        return {"status": "success", "data": feed_list}
    except Exception as e:
        print(f"LỖI FEED 500: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi lấy feed: {str(e)}")
    finally:
        conn.close()

# --- 3. API Thả tim / Bỏ tim bài viết ---
@router.post("/{post_id}/like")
def toggle_like(post_id: int, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?", (user_id, post_id))
        liked = cursor.fetchone()

        if liked:
            cursor.execute("DELETE FROM likes WHERE user_id = ? AND post_id = ?", (user_id, post_id))
            cursor.execute("UPDATE posts SET like_count = MAX(0, like_count - 1) WHERE id = ?", (post_id,))
            message = "Đã bỏ tim"
        else:
            cursor.execute("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", (user_id, post_id))
            cursor.execute("UPDATE posts SET like_count = like_count + 1 WHERE id = ?", (post_id,))
            message = "Đã thả tim"

        conn.commit()
        return {"status": "success", "message": message}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý like: {str(e)}")
    finally:
        conn.close()


# --- 4. API Share tổng quát (Fix lỗi 404 cho Android) ---
@router.post("/{post_id}/share")
def share_post_legacy(
    post_id: int, 
    user_id: int = Query(1), 
    share_type: str = Query("FEED"), 
    caption: str = Query("")
):
    if share_type == "FEED":
        payload = ShareToFeedRequest(user_id=user_id, caption=caption)
        return share_post_to_feed(post_id, payload)
    else:
        payload = ShareToMessageRequest(sender_id=user_id, receiver_ids=[2], message_text=caption)
        return share_post_to_message(post_id, payload)


# --- 5. API Bấm "Chia sẻ ngay" lên Feed ---
@router.post("/{post_id}/share-to-feed")
def share_post_to_feed(post_id: int, payload: ShareToFeedRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO posts (user_id, post_type, caption, privacy, original_post_id)
            VALUES (?, 'SHARED', ?, ?, ?)
        """, (payload.user_id, payload.caption, payload.privacy, post_id))
        
        new_post_id = cursor.lastrowid
        cursor.execute("UPDATE posts SET share_count = share_count + 1 WHERE id = ?", (post_id,))

        conn.commit()
        return {
            "status": "success",
            "message": "Đã chia sẻ lên Trang cá nhân!",
            "new_post_id": new_post_id
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi chia sẻ: {str(e)}")
    finally:
        conn.close()


# --- 6. API Bấm "Gửi" qua Tin nhắn bạn bè ---
@router.post("/{post_id}/share-to-message")
def share_post_to_message(post_id: int, payload: ShareToMessageRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        for receiver_id in payload.receiver_ids:
            cursor.execute("""
                INSERT INTO messages (sender_id, receiver_id, message_text, shared_post_id)
                VALUES (?, ?, ?, ?)
            """, (payload.sender_id, receiver_id, payload.message_text, post_id))

        cursor.execute(
            "UPDATE posts SET share_count = share_count + ? WHERE id = ?",
            (len(payload.receiver_ids), post_id)
        )

        conn.commit()
        return {
            "status": "success",
            "message": f"Đã gửi bài viết cho {len(payload.receiver_ids)} người bạn!"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi gửi tin nhắn chia sẻ: {str(e)}")
    finally:
        conn.close()

#Thuật toán học bài viết theo sơở thích của người dùng (Dựa vào số lượt like, comment, share, thời gian đăng bài) sẽ được triển khai trong các phiên bản sau.
#Sự khác biệt giữa Quyền xem (privacy) và thuật toàn phân phối (Feed Algorithm) sẽ được triển khai trong các phiên bản sau.
# Khi share bài viết cho bạn bè cần kiểm tra người đó có phải bạn bè hay không
# Chưa làm chức năng comment 
