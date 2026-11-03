from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from database import get_db
from services.cloud_storage import upload_file_to_cloud
from pydantic import BaseModel
from typing import Optional, List
import mimetypes
import os

router = APIRouter()

# --- Request Models ---
class ShareToFeedRequest(BaseModel):
    user_id: int
    caption: Optional[str] = ""
    privacy: str = "PUBLIC"

class ShareToMessageRequest(BaseModel):
    sender_id: int
    receiver_ids: List[int]
    message_text: Optional[str] = ""

# --- Helper nhận diện Media ---
def detect_media_type(file_url_or_path: str) -> str:
    _, ext = os.path.splitext(file_url_or_path.lower())
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
    video_exts = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.3gp'}
    excel_exts = {'.xlsx', '.xls', '.csv'}
    doc_exts   = {'.pdf', '.doc', '.docx', '.txt'}

    if ext in image_exts:
        return "IMAGE"
    elif ext in video_exts:
        return "VIDEO"
    elif ext in excel_exts:
        return "EXCEL"
    elif ext in doc_exts:
        return "DOCUMENT"
    else:
        return "FILE"

def detect_media_type_by_mime(file_url: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_url)
    if mime_type:
        if mime_type.startswith("image/"):
            return "IMAGE"
        elif mime_type.startswith("video/"):
            return "VIDEO"
        elif mime_type.startswith("audio/"):
            return "AUDIO"
        elif "spreadsheet" in mime_type or "excel" in mime_type or file_url.endswith(".csv"):
            return "EXCEL"
    return "FILE"

# --- 1. API Upload Media ---
@router.post("/upload")
async def upload_media(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        media_url = upload_file_to_cloud(
            file_bytes=contents,
            filename=file.filename,
            content_type=file.content_type
        )
        return {"status": "success", "media_url": media_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi upload: {str(e)}")

# --- HÀM CHI TIẾT MEDIA VỚI LƯỢT LIKE/COMMENT RIÊNG ---
def _get_post_details(cursor, post_id: int, post_type: str, current_user_id: int = 1):
    details = {}
    
    cursor.execute("""
        SELECT pm.id, pm.media_url, pm.media_type, pm.like_count, pm.comment_count,
               (SELECT 1 FROM post_media_likes WHERE user_id = ? AND media_id = pm.id) as is_liked
        FROM post_media pm
        WHERE pm.post_id = ?
    """, (current_user_id, post_id))
    media_rows = cursor.fetchall()
    
    media_list = []
    for m_id, m_url, m_type, m_likes, m_cmts, m_is_liked in media_rows:
        final_type = m_type
        if not final_type or final_type.strip() == "":
            final_type = detect_media_type_by_mime(m_url)
            if final_type == "FILE":
                final_type = detect_media_type(m_url)

        media_list.append({
            "media_id": m_id,
            "url": m_url,
            "media_url": m_url,
            "type": final_type,
            "media_type": final_type,
            "like_count": m_likes if m_likes else 0,
            "comment_count": m_cmts if m_cmts else 0,
            "is_liked": True if m_is_liked else False
        })
    details["media_list"] = media_list

    if post_type == "RECIPE":
        cursor.execute("""
            SELECT recipe_title, cover_image_url, servings, cooking_time 
            FROM recipes WHERE post_id = ?
        """, (post_id,))
        r_row = cursor.fetchone()
        if r_row:
            r_title, r_cover, r_servings, r_time = r_row
            cursor.execute("SELECT ingredient_name, amount, unit FROM recipe_ingredients WHERE post_id = ?", (post_id,))
            ingredients = [{"name": i[0], "amount": f"{i[1]} {i[2]}".strip()} for i in cursor.fetchall()]
            
            cursor.execute("SELECT step_number, instruction FROM recipe_steps WHERE post_id = ? ORDER BY step_number ASC", (post_id,))
            steps = [{"step": s[0], "instruction": s[1]} for s in cursor.fetchall()]
            
            details["recipe_details"] = {
                "title": r_title,
                "cover_image_url": r_cover,
                "ingredients": ingredients,
                "steps": steps
            }
            
    return details

# --- 2. API Newsfeed ---
@router.get("/feed")
def get_main_feed(post_type: str = "ALL", current_user_id: int = 1):
    conn = get_db()
    cursor = conn.cursor()
    try:
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

        if post_type and post_type.upper() != "ALL":
            if post_type.upper() == "REGULAR":
                query += " WHERE p.post_type = 'REGULAR' OR (p.post_type = 'SHARED' AND orig_p.post_type = 'REGULAR')"
            elif post_type.upper() == "RECIPE":
                query += " WHERE p.post_type = 'RECIPE' OR (p.post_type = 'SHARED' AND orig_p.post_type = 'RECIPE')"

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

            details = _get_post_details(cursor, post_id, p_type, current_user_id)
            post_data.update(details)

            if p_type == "SHARED" and original_post_id:
                cursor.execute("""
                    SELECT p.id, p.post_type, p.caption, p.privacy, p.created_at, u.id, u.full_name, u.avatar_url
                    FROM posts p
                    JOIN users u ON p.user_id = u.id
                    WHERE p.id = ?
                """, (original_post_id,))
                orig_row = cursor.fetchone()
                
                if orig_row:
                    orig_id, orig_type, orig_caption, orig_privacy, orig_created_at, orig_u_id, orig_u_name, orig_u_avatar = orig_row
                    orig_details = _get_post_details(cursor, orig_id, orig_type, current_user_id)
                    
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
        raise HTTPException(status_code=500, detail=f"Lỗi lấy feed: {str(e)}")
    finally:
        conn.close()

# --- 3. API Thả tim Bài viết Tổng ---
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

# --- 🟢 4. API BỔ SUNG: Thả tim / Bỏ tim RIÊNG cho từng Media ---
@router.post("/media/{media_id}/like")
def toggle_media_like(media_id: int, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Kiểm tra xem user này đã tim media này chưa
        cursor.execute("SELECT 1 FROM post_media_likes WHERE user_id = ? AND media_id = ?", (user_id, media_id))
        liked = cursor.fetchone()

        if liked:
            # Trường hợp đã thả tim -> BỎ TIM (Trừ 1)
            cursor.execute("DELETE FROM post_media_likes WHERE user_id = ? AND media_id = ?", (user_id, media_id))
            cursor.execute("UPDATE post_media SET like_count = MAX(0, like_count - 1) WHERE id = ?", (media_id,))
            is_liked_now = False
            message = "Đã bỏ tim media"
        else:
            # Trường hợp chưa thả tim -> THẢ TIM (Cộng 1)
            cursor.execute("INSERT INTO post_media_likes (user_id, media_id) VALUES (?, ?)", (user_id, media_id))
            cursor.execute("UPDATE post_media SET like_count = like_count + 1 WHERE id = ?", (media_id,))
            is_liked_now = True
            message = "Đã thả tim media"

        conn.commit()

        # 2. Lấy lại số like_count chính xác nhất từ cơ sở dữ liệu sau khi vừa update
        cursor.execute("SELECT like_count FROM post_media WHERE id = ?", (media_id,))
        row = cursor.fetchone()
        new_like_count = row[0] if row else 0

        # 3. Trả kết quả về cho Android Studio
        return {
            "status": "success",
            "message": message,
            "media_id": media_id,
            "is_liked": is_liked_now,
            "like_count": new_like_count
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý like media: {str(e)}")
    finally:
        conn.close()

# --- 5. Share APIs ---
@router.post("/{post_id}/share")
def share_post_legacy(post_id: int, user_id: int = Query(1), share_type: str = Query("FEED"), caption: str = Query("")):
    if share_type == "FEED":
        payload = ShareToFeedRequest(user_id=user_id, caption=caption)
        return share_post_to_feed(post_id, payload)
    else:
        payload = ShareToMessageRequest(sender_id=user_id, receiver_ids=[2], message_text=caption)
        return share_post_to_message(post_id, payload)

@router.post("/{post_id}/share-to-feed")
def share_post_to_feed(post_id: int, payload: ShareToFeedRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO posts (user_id, post_type, caption, privacy, original_post_id) VALUES (?, 'SHARED', ?, ?, ?)",
                       (payload.user_id, payload.caption, payload.privacy, post_id))
        new_post_id = cursor.lastrowid
        cursor.execute("UPDATE posts SET share_count = share_count + 1 WHERE id = ?", (post_id,))
        conn.commit()
        return {"status": "success", "message": "Đã chia sẻ lên Trang cá nhân!", "new_post_id": new_post_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi chia sẻ: {str(e)}")
    finally:
        conn.close()

@router.post("/{post_id}/share-to-message")
def share_post_to_message(post_id: int, payload: ShareToMessageRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        for receiver_id in payload.receiver_ids:
            cursor.execute("INSERT INTO messages (sender_id, receiver_id, message_text, shared_post_id) VALUES (?, ?, ?, ?)",
                           (payload.sender_id, receiver_id, payload.message_text, post_id))
        cursor.execute("UPDATE posts SET share_count = share_count + ? WHERE id = ?", (len(payload.receiver_ids), post_id))
        conn.commit()
        return {"status": "success", "message": f"Đã gửi bài viết cho {len(payload.receiver_ids)} người bạn!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi gửi tin nhắn chia sẻ: {str(e)}")
    finally:
        conn.close()
#Thuật toán học bài viết theo sơở thích của người dùng (Dựa vào số lượt like, comment, share, thời gian đăng bài) sẽ được triển khai trong các phiên bản sau.
#Sự khác biệt giữa Quyền xem (privacy) và thuật toàn phân phối (Feed Algorithm) sẽ được triển khai trong các phiên bản sau.
# Khi share bài viết cho bạn bè cần kiểm tra người đó có phải bạn bè hay không
# Chưa làm chức năng comment 
