from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from database import get_db
from services.cloud_storage import upload_file_to_cloud
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import mimetypes
import os
import sqlite3

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
class CommentCreateRequest(BaseModel):
    user_id: int
    content: Optional[str] = ""
    parent_id: Optional[int] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None

class ReactionRequest(BaseModel):
    user_id: int
    reaction_type: str # "LIKE" hoặc "DISLIKE"
class CommentEditRequest(BaseModel):
    user_id: int
    content: str

def get_vietnam_time():
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).strftime("%Y-%m-%d %H:%M:%S")
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

def _get_post_details(cursor, post_id: int, post_type: str, current_user_id: int = 1):
    details = {}
    
    cursor.execute("""
        SELECT 
            pm.id, 
            pm.media_url, 
            pm.media_type,
            COALESCE(pm.like_count, 0) as like_count,
            COALESCE(pm.comment_count, 0) as comment_count,
            EXISTS(SELECT 1 FROM post_media_likes WHERE media_id = pm.id AND user_id = ?) as is_liked
        FROM post_media pm
        WHERE pm.post_id = ?
        ORDER BY pm.id ASC
    """, (current_user_id, post_id))
    
    media_rows = cursor.fetchall()
    
    media_list = []
    # m_likes đứng trước m_cmts cho đúng với thứ tự SELECT ở trên
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
            "like_count": m_likes,
            "comment_count": m_cmts,
            "is_liked": True if m_is_liked else False
        })
    details["media_list"] = media_list

    cursor.execute("""
        SELECT recipe_title, cover_image_url, servings, servings_to, cooking_time, cooking_time_unit, difficulty
        FROM recipes WHERE post_id = ?
    """, (post_id,))
    r_row = cursor.fetchone()
    if r_row:
        r_title, r_cover, r_servings, r_servings_to, r_time, r_unit, r_diff = r_row

        cursor.execute("SELECT ingredient_name, amount, unit FROM recipe_ingredients WHERE post_id = ?", (post_id,))
        ingredients = [{"name": i[0], "amount": i[1], "unit": i[2]} for i in cursor.fetchall()]

        cursor.execute("""
            SELECT step_number, instruction, media_url, media_type 
            FROM recipe_steps WHERE post_id = ? ORDER BY step_number ASC
        """, (post_id,))
        steps = [{
            "step_number": s[0], 
            "instruction": s[1],
            "media_url": s[2], 
            "media_type": s[3] if s[3] else "IMAGE"
        } for s in cursor.fetchall()]

        recipe_obj = {
            "title": r_title,
            "cover_image_url": r_cover,
            "servings": r_servings,
            "servings_to": r_servings_to if r_servings_to else 0,
            "cooking_time": r_time,
            "cooking_time_unit": r_unit if r_unit else "phút",
            "difficulty": r_diff if r_diff else "Dễ",
            "ingredients": ingredients,
            "steps": steps
        }

        details["recipe"] = recipe_obj
        details["recipe_details"] = recipe_obj
            
    return details


# --- 3. API Newsfeed ---
@router.get("/feed")
def get_main_feed(post_type: str = "ALL", current_user_id: int = Query(default=1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Đếm trực tiếp COUNT(*) lượt like và comment chung từ DB
        query = """
            SELECT p.id, p.post_type, p.caption, 
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as real_like_count,
                   (SELECT COUNT(*) FROM comments WHERE post_id = p.id AND (media_id IS NULL OR media_id = 0)) as real_comment_count,
                   p.share_count, p.created_at, p.original_post_id, p.privacy,
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

# --- 4. API Thả tim Bài viết Tổng ---
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

# --- 5. Thả tim / Bỏ tim RIÊNG cho từng Media ---
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

# --- 6. Share APIs ---
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
        current_time = get_vietnam_time()
        cursor.execute("""
            INSERT INTO posts (user_id, post_type, caption, privacy, original_post_id, created_at) 
            VALUES (?, 'SHARED', ?, ?, ?, ?)
        """, (payload.user_id, payload.caption, payload.privacy, post_id, current_time))
        
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
# 7. API Lấy danh sách bình luận (Đã cấu trúc đệ quy/phân tầng)
@router.get("/{post_id}/comments")
def get_post_comments(post_id: int, current_user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Lấy cột like/dislike tính sẵn + Lọc điều kiện (media_id IS NULL OR media_id = 0)
        cursor.execute("""
            SELECT c.id, c.parent_id, c.content, c.media_url, c.media_type, c.created_at, 
                   u.id as user_id, u.full_name, u.avatar_url,
                   c.like_count_com_post_chung,
                   c.dislike_count_com_post_chung,
                   (SELECT reaction_type FROM comment_reactions WHERE comment_id = c.id AND user_id = ?) as my_reaction
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = ? AND (c.media_id IS NULL OR c.media_id = 0)
            ORDER BY c.created_at ASC
        """, (current_user_id, post_id))
        
        rows = cursor.fetchall()

        all_cmts = {}
        root_cmts = []

        for r in rows:
            c_id, p_id, content, m_url, m_type, created_at, u_id, full_name, avatar_url, likes, dislikes, my_react = r
            
            # Tự động nhận diện media_type nếu rỗng
            final_m_type = m_type
            if m_url and not final_m_type:
                final_m_type = detect_media_type_by_mime(m_url)

            cmt_obj = {
                "comment_id": c_id,
                "parent_id": p_id,
                "content": content if content else "",
                "media_url": m_url,
                "media_type": final_m_type,
                "created_at": created_at,
                "author": {"user_id": u_id, "full_name": full_name, "avatar_url": avatar_url},
                "like_count": likes if likes else 0,
                "dislike_count": dislikes if dislikes else 0,
                "my_reaction": my_react if my_react else "NONE",
                "replies": []
            }
            all_cmts[c_id] = cmt_obj

        for c_id, cmt in all_cmts.items():
            p_id = cmt["parent_id"]
            if p_id and p_id in all_cmts:
                all_cmts[p_id]["replies"].append(cmt)
            else:
                root_cmts.append(cmt)

        return {"status": "success", "comments": root_cmts}
    finally:
        conn.close()


# 8. API Thêm bình luận mới (Gốc hoặc Trả lời của Header bài viết)
@router.post("/{post_id}/comments")
def add_comment(post_id: int, req: CommentCreateRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if not req.content and not req.media_url:
            raise HTTPException(status_code=400, detail="Bình luận phải có chữ hoặc ảnh đính kèm")

        cursor.execute("""
            INSERT INTO comments (post_id, user_id, parent_id, content, media_url, media_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (post_id, req.user_id, req.parent_id, req.content, req.media_url, req.media_type, get_vietnam_time()))
        
        # 1. CHỈ ĐẾM LẠI COMMENT THUỘC HEADER (LOẠI BỎ COMMENT CỦA MEDIA)
        cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id = ? AND (media_id IS NULL OR media_id = 0)", (post_id,))
        real_count = cursor.fetchone()[0]

        # 2. Cập nhật lại cột comment_count chuẩn (chỉ đếm header) trong bảng posts
        cursor.execute("UPDATE posts SET comment_count = ? WHERE id = ?", (real_count, post_id))
        conn.commit()

        return {
            "status": "success", 
            "message": "Đăng bình luận thành công", 
            "comment_count": real_count
        }
    finally:
        conn.close()

# 9. API Thả Like / Dislike bình luận
@router.post("/comments/{comment_id}/react")
def react_comment(comment_id: int, req: ReactionRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Thêm / Cập nhật / Xóa reaction của user trong bảng comment_reactions
        if req.reaction_type == "NONE":
            cursor.execute("DELETE FROM comment_reactions WHERE user_id = ? AND comment_id = ?", 
                           (req.user_id, comment_id))
        else:
            cursor.execute("""
                INSERT INTO comment_reactions (user_id, comment_id, reaction_type)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, comment_id) DO UPDATE SET reaction_type = excluded.reaction_type
            """, (req.user_id, comment_id, req.reaction_type))

        # 2. Đếm số lượng LIKE và DISLIKE mới nhất của comment này
        cursor.execute("SELECT COUNT(*) FROM comment_reactions WHERE comment_id = ? AND reaction_type = 'LIKE'", (comment_id,))
        new_likes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM comment_reactions WHERE comment_id = ? AND reaction_type = 'DISLIKE'", (comment_id,))
        new_dislikes = cursor.fetchone()[0]

        # 3. Phân biệt xem comment_id thuộc bảng comments hay post_media_comments để UPDATE
        cursor.execute("SELECT id FROM comments WHERE id = ?", (comment_id,))
        if cursor.fetchone():
            # Cập nhật vào bảng comments bài post chung
            cursor.execute("""
                UPDATE comments 
                SET like_count_com_post_chung = ?, dislike_count_com_post_chung = ? 
                WHERE id = ?
            """, (new_likes, new_dislikes, comment_id))
        else:
            # Cập nhật vào bảng post_media_comments của media
            cursor.execute("""
                UPDATE post_media_comments 
                SET like_count_com_media = ?, dislike_count_com_media = ? 
                WHERE id = ?
            """, (new_likes, new_dislikes, comment_id))

        conn.commit()

        return {
            "status": "success",
            "comment_id": comment_id,
            "my_reaction": req.reaction_type,
            "like_count": new_likes,
            "dislike_count": new_dislikes
        }
    finally:
        conn.close()
# --- 10. API Lấy danh sách bình luận RIÊNG cho từng Media ---
@router.get("/media/{media_id}/comments")
def get_media_comments(media_id: int, current_user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT c.id, c.parent_id, c.content, c.media_url, c.media_type, c.created_at, 
                   u.id as user_id, u.full_name, u.avatar_url
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.media_id = ?
            ORDER BY c.created_at ASC
        """, (media_id,))
        rows = cursor.fetchall()

        all_cmts = {}
        root_cmts = []

        for r in rows:
            c_id, p_id, content, m_url, m_type, created_at, u_id, full_name, avatar_url = r
            
            # Lấy thống kê Like / Dislike / Reaction của user hiện tại
            cursor.execute("SELECT COUNT(*) FROM comment_reactions WHERE comment_id = ? AND reaction_type = 'LIKE'", (c_id,))
            likes = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM comment_reactions WHERE comment_id = ? AND reaction_type = 'DISLIKE'", (c_id,))
            dislikes = cursor.fetchone()[0]
            cursor.execute("SELECT reaction_type FROM comment_reactions WHERE comment_id = ? AND user_id = ?", (c_id, current_user_id))
            my_react_row = cursor.fetchone()
            my_react = my_react_row[0] if my_react_row else "NONE"

            cmt_obj = {
                "comment_id": c_id,
                "parent_id": p_id,
                "content": content if content else "",
                "media_url": m_url,
                "media_type": m_type,
                "created_at": created_at,
                "author": {"user_id": u_id, "full_name": full_name, "avatar_url": avatar_url},
                "like_count": likes,
                "dislike_count": dislikes,
                "my_reaction": my_react,
                "replies": []
            }
            all_cmts[c_id] = cmt_obj

        for c_id, cmt in all_cmts.items():
            p_id = cmt["parent_id"]
            if p_id and p_id in all_cmts:
                all_cmts[p_id]["replies"].append(cmt)
            else:
                root_cmts.append(cmt)

        return {"status": "success", "comments": root_cmts}
    finally:
        conn.close()

# --- 11. API Thêm bình luận RIÊNG cho từng Media ---
@router.post("/media/{media_id}/comments")
def add_media_comment(media_id: int, req: CommentCreateRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Lấy post_id từ bảng post_media
        cursor.execute("SELECT post_id FROM post_media WHERE id = ?", (media_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy Media")
        post_id = row[0]

        cursor.execute("""
            INSERT INTO comments (post_id, media_id, user_id, parent_id, content, media_url, media_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (post_id, media_id, req.user_id, req.parent_id, req.content, req.media_url, req.media_type, get_vietnam_time()))
        
        # Cập nhật số lượng comment trong post_media
        cursor.execute("SELECT COUNT(*) FROM comments WHERE media_id = ?", (media_id,))
        new_media_cmt_count = cursor.fetchone()[0]
        cursor.execute("UPDATE post_media SET comment_count = ? WHERE id = ?", (new_media_cmt_count, media_id))
        conn.commit()

        return {
            "status": "success", 
            "message": "Đăng bình luận media thành công", 
            "comment_count": new_media_cmt_count
        }
    finally:
        conn.close()
     
# --12. API Xóa bình luận--        
@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, user_id: int = Query(default=1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Kiểm tra xem comment_id nằm trong bảng `comments` (Bài post Header hoặc Media)
        cursor.execute("SELECT post_id, media_id FROM comments WHERE id = ?", (comment_id,))
        row_post = cursor.fetchone()

        if row_post:
            post_id, media_id = row_post
            # Xóa comment chính + comment phản hồi (replies)
            cursor.execute("DELETE FROM comments WHERE id = ? OR parent_id = ?", (comment_id, comment_id))
            
            # Nếu là comment media (media_id > 0)
            if media_id and media_id > 0:
                cursor.execute("SELECT COUNT(*) FROM comments WHERE media_id = ?", (media_id,))
                new_count = cursor.fetchone()[0]
                cursor.execute("UPDATE post_media SET comment_count = ? WHERE id = ?", (new_count, media_id))
                
                conn.commit()
                return {
                    "status": "success", 
                    "message": "Đã xóa bình luận media", 
                    "comment_count": new_count,
                    "target": "MEDIA",
                    "media_id": media_id,
                    "post_id": post_id
                }
            else:
                # Nếu là comment Header của bài post chung
                cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id = ? AND (media_id IS NULL OR media_id = 0)", (post_id,))
                new_count = cursor.fetchone()[0]
                cursor.execute("UPDATE posts SET comment_count = ? WHERE id = ?", (new_count, post_id))

                conn.commit()
                return {
                    "status": "success", 
                    "message": "Đã xóa bình luận", 
                    "comment_count": new_count,
                    "target": "HEADER",
                    "post_id": post_id
                }

        # 2. Nếu không có trong `comments`, kiểm tra tiếp trong bảng `post_media_comments`
        cursor.execute("SELECT media_id FROM post_media_comments WHERE id = ?", (comment_id,))
        row_media = cursor.fetchone()

        if row_media:
            media_id = row_media[0]
            cursor.execute("DELETE FROM post_media_comments WHERE id = ? OR parent_id = ?", (comment_id, comment_id))
            
            cursor.execute("SELECT COUNT(*) FROM post_media_comments WHERE media_id = ?", (media_id,))
            new_count = cursor.fetchone()[0]
            cursor.execute("UPDATE post_media SET comment_count = ? WHERE id = ?", (new_count, media_id))
            
            conn.commit()
            return {
                "status": "success", 
                "message": "Đã xóa bình luận media", 
                "comment_count": new_count,
                "target": "MEDIA",
                "media_id": media_id
            }

        raise HTTPException(status_code=404, detail="Không tìm thấy bình luận")
    finally:
        conn.close()
#--13.API Chỉnh sửa nội dung bình luận--
@router.put("/comments/{comment_id}")
def edit_comment(comment_id: int, req: CommentEditRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Thử UPDATE ở bảng `comments` trước
        cursor.execute("UPDATE comments SET content = ? WHERE id = ?", (req.content, comment_id))
        
        # Nếu không có dòng nào được update (do id thuộc comment media), update tiếp bảng `post_media_comments`
        if cursor.rowcount == 0:
            cursor.execute("UPDATE post_media_comments SET content = ? WHERE id = ?", (req.content, comment_id))

        conn.commit()
        return {"status": "success", "message": "Đã cập nhật bình luận"}
    finally:
        conn.close()
# --- API Lấy chi tiết bài viết (Khi đã có prefix /api/posts trong main.py) ---
@router.get("/{post_id}")
def get_post_detail_endpoint(post_id: int, current_user_id: int = Query(default=1)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.id, p.post_type, p.caption, 
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as real_like_count,
                   --CHỈ ĐẾM BÌNH LUẬN CỦA HEADER (LOẠI BỎ BÌNH LUẬN MEDIA)
                   (SELECT COUNT(*) FROM comments WHERE post_id = p.id AND (media_id IS NULL OR media_id = 0)) as real_comment_count,
                   p.share_count, p.created_at, p.privacy,
                   u.id as user_id, u.full_name, u.avatar_url,
                   (SELECT 1 FROM likes WHERE user_id = ? AND post_id = p.id) as is_liked
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.id = ?
        """, (current_user_id, post_id))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bài viết không tồn tại")
        
        p_id, p_type, caption, like_count, comment_count, share_count, created_at, privacy, u_id, u_name, u_avatar, is_liked = row
        
        post_data = {
            "post_id": p_id,
            "post_type": p_type,
            "caption": caption if caption else "",
            "privacy": privacy if privacy else "PUBLIC",
            "like_count": like_count if like_count else 0,
            "comment_count": comment_count if comment_count else 0, # Con số này giờ đây sẽ chuẩn xác = 2!
            "share_count": share_count if share_count else 0,
            "created_at": created_at if created_at else "",
            "is_liked": True if is_liked else False,
            "author": {
                "user_id": u_id,
                "full_name": u_name,
                "avatar_url": u_avatar
            }
        }

        details = _get_post_details(cursor, p_id, p_type, current_user_id)
        post_data.update(details)

        return {"status": "success", "post": post_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lấy chi tiết bài viết: {str(e)}")
    finally:
        conn.close()

# API Lấy danh sách bạn bè đã kết bạn (status = 'ACCEPTED')
@router.get("/users/{user_id}/friends")
def get_user_friends(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT u.id, u.full_name, u.avatar_url
            FROM users u
            WHERE u.id IN (
                SELECT friend_id FROM friendships WHERE user_id = ? AND status = 'ACCEPTED'
                UNION
                SELECT user_id FROM friendships WHERE friend_id = ? AND status = 'ACCEPTED'
            )
        """, (user_id, user_id))
        
        rows = cursor.fetchall()
        friends = [{"user_id": r[0], "full_name": r[1], "avatar_url": r[2]} for r in rows]
        return {"status": "success", "friends": friends}
    finally:
        conn.close()
# Thêm endpoint này vào file router chứa các API /api/posts
@router.get("/users/{user_id}")
def get_user_profile(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name, avatar_url FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User không tìm thấy")
        return {
            "user_id": row[0],
            "full_name": row[1],
            "avatar_url": row[2]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
#Thuật toán học bài viết theo sơở thích của người dùng (Dựa vào số lượt like, comment, share, thời gian đăng bài) sẽ được triển khai trong các phiên bản sau.
#Sự khác biệt giữa Quyền xem (privacy) và thuật toàn phân phối (Feed Algorithm) sẽ được triển khai trong các phiên bản sau.
# Khi share bài viết cho bạn bè cần kiểm tra người đó có phải bạn bè hay không
# Chưa làm khi có nguười comment bài viết do mình tạo thì sẽ gửi thông báo cho người tạo
# Chưa làm khi có người trả lời comment của mình thì mình sẽ được gửi thông báo.
# Chưa làm khi có người like, share bài viết do mình tạo thì sẽ gửi thông báo cho người tạo 

