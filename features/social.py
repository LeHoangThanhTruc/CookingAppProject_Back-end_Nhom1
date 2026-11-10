from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from database import get_db
from security import get_current_user_id

router = APIRouter()
message_router = APIRouter()
notification_router = APIRouter()


class FriendRequestInput(BaseModel):
    friend_id: int


class MessageInput(BaseModel):
    receiver_id: int
    text: str = Field(min_length=1, max_length=2000)
    shared_post_id: int | None = None


def _user_exists(connection, user_id: int):
    if connection.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
        raise HTTPException(404, "Không tìm thấy người dùng")


@router.get("/users")
def search_users(q: str = "", limit: int = Query(30, ge=1, le=100), user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        needle = f"%{q.strip().lower()}%"
        rows = connection.execute(
            """
            SELECT id, username, full_name, avatar_url
            FROM users
            WHERE id<>? AND (lower(username) LIKE ? OR lower(COALESCE(full_name,'')) LIKE ?)
            ORDER BY username LIMIT ?
            """,
            (user_id, needle, needle, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _notify(connection, user_id: int, actor_id: int, kind: str, message: str, reference_id: int | None = None):
    connection.execute(
        "INSERT INTO notifications(user_id,actor_id,type,message,reference_id) VALUES(?,?,?,?,?)",
        (user_id, actor_id, kind, message, reference_id),
    )


@router.post("/friend-requests", status_code=status.HTTP_201_CREATED)
def send_friend_request(data: FriendRequestInput, user_id: int = Depends(get_current_user_id)):
    if data.friend_id == user_id:
        raise HTTPException(400, "Không thể kết bạn với chính mình")
    connection = get_db()
    try:
        _user_exists(connection, data.friend_id)
        existing = connection.execute(
            "SELECT * FROM friendships WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)",
            (user_id, data.friend_id, data.friend_id, user_id),
        ).fetchone()
        if existing:
            raise HTTPException(409, "Quan hệ bạn bè hoặc lời mời đã tồn tại")
        cursor = connection.execute(
            "INSERT INTO friendships(user_id,friend_id,status) VALUES(?,?,'PENDING')",
            (user_id, data.friend_id),
        )
        _notify(connection, data.friend_id, user_id, "FRIEND_REQUEST", "Bạn có lời mời kết bạn", cursor.lastrowid)
        connection.commit()
        return {"id": cursor.lastrowid, "user_id": user_id, "friend_id": data.friend_id, "status": "PENDING"}
    finally:
        connection.close()


@router.get("/friend-requests")
def list_friend_requests(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            """
            SELECT f.id, f.user_id, f.friend_id, f.status, f.created_at,
                   u.username, u.full_name, u.avatar_url
            FROM friendships f JOIN users u ON u.id=f.user_id
            WHERE f.friend_id=? AND f.status='PENDING'
            ORDER BY f.created_at DESC, f.id DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@router.get("/friend-requests/sent")
def list_sent_friend_requests(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            """
            SELECT f.id, f.user_id, f.friend_id, f.status, f.created_at,
                   u.username, u.full_name, u.avatar_url
            FROM friendships f JOIN users u ON u.id=f.friend_id
            WHERE f.user_id=? AND f.status='PENDING'
            ORDER BY f.created_at DESC, f.id DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@router.delete("/friend-requests/{request_id}", status_code=204)
def cancel_friend_request(request_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        cursor = connection.execute(
            "DELETE FROM friendships WHERE id=? AND user_id=? AND status='PENDING'",
            (request_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy lời mời kết bạn đã gửi")
        connection.commit()
    finally:
        connection.close()


def _pending_request(connection, request_id: int, recipient_id: int):
    row = connection.execute(
        "SELECT * FROM friendships WHERE id=? AND friend_id=? AND status='PENDING'",
        (request_id, recipient_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Không tìm thấy lời mời kết bạn")
    return row


@router.post("/friend-requests/{request_id}/accept")
def accept_friend_request(request_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        row = _pending_request(connection, request_id, user_id)
        connection.execute("UPDATE friendships SET status='ACCEPTED' WHERE id=?", (request_id,))
        _notify(connection, row["user_id"], user_id, "FRIEND_ACCEPTED", "Lời mời kết bạn đã được chấp nhận", request_id)
        connection.commit()
        return {"id": request_id, "status": "ACCEPTED"}
    finally:
        connection.close()


@router.post("/friend-requests/{request_id}/reject")
def reject_friend_request(request_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        _pending_request(connection, request_id, user_id)
        connection.execute("DELETE FROM friendships WHERE id=?", (request_id,))
        connection.commit()
        return {"id": request_id, "status": "REJECTED"}
    finally:
        connection.close()


@router.delete("/friends/{friend_id}", status_code=204)
def remove_friend(friend_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        cursor = connection.execute(
            "DELETE FROM friendships WHERE status='ACCEPTED' AND ((user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?))",
            (user_id, friend_id, friend_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy quan hệ bạn bè")
        connection.commit()
    finally:
        connection.close()


@router.get("/friends")
def list_friends(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            """
            SELECT u.id, u.username, u.full_name, u.avatar_url
            FROM friendships f JOIN users u ON u.id=CASE WHEN f.user_id=? THEN f.friend_id ELSE f.user_id END
            WHERE f.status='ACCEPTED' AND (f.user_id=? OR f.friend_id=?) ORDER BY u.username
            """,
            (user_id, user_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@router.post("/follow/{target_id}")
def toggle_follow(target_id: int, user_id: int = Depends(get_current_user_id)):
    if target_id == user_id:
        raise HTTPException(400, "Không thể theo dõi chính mình")
    connection = get_db()
    try:
        _user_exists(connection, target_id)
        existing = connection.execute("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?", (user_id, target_id)).fetchone()
        if existing:
            connection.execute("DELETE FROM follows WHERE follower_id=? AND following_id=?", (user_id, target_id))
        else:
            connection.execute("INSERT INTO follows(follower_id,following_id) VALUES(?,?)", (user_id, target_id))
            _notify(connection, target_id, user_id, "FOLLOW", "Có người bắt đầu theo dõi bạn")
        connection.commit()
        return {"following": not bool(existing)}
    finally:
        connection.close()


@router.get("/following")
def list_following(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            """
            SELECT u.id, u.username, u.full_name, u.avatar_url
            FROM follows f JOIN users u ON u.id=f.following_id
            WHERE f.follower_id=? ORDER BY u.username
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@message_router.post("", status_code=201)
def send_message(data: MessageInput, user_id: int = Depends(get_current_user_id)):
    if data.receiver_id == user_id:
        raise HTTPException(400, "Không thể gửi tin nhắn cho chính mình")
    connection = get_db()
    try:
        _user_exists(connection, data.receiver_id)
        if data.shared_post_id is not None and connection.execute("SELECT 1 FROM posts WHERE id=?", (data.shared_post_id,)).fetchone() is None:
            raise HTTPException(404, "Không tìm thấy bài viết được chia sẻ")
        cursor = connection.execute(
            "INSERT INTO messages(sender_id,receiver_id,message_text,shared_post_id) VALUES(?,?,?,?)",
            (user_id, data.receiver_id, data.text.strip(), data.shared_post_id),
        )
        _notify(connection, data.receiver_id, user_id, "MESSAGE", "Bạn có tin nhắn mới", cursor.lastrowid)
        connection.commit()
        return {"id": cursor.lastrowid, "sender_id": user_id, "receiver_id": data.receiver_id, "text": data.text.strip(), "shared_post_id": data.shared_post_id}
    finally:
        connection.close()


@message_router.get("/{other_user_id}")
def conversation(other_user_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        _user_exists(connection, other_user_id)
        rows = connection.execute(
            "SELECT id,sender_id,receiver_id,message_text AS text,shared_post_id,created_at FROM messages WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?) ORDER BY created_at,id",
            (user_id, other_user_id, other_user_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@message_router.get("")
def conversation_list(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            """
            WITH participants AS (
                SELECT CASE WHEN sender_id=? THEN receiver_id ELSE sender_id END AS other_id,
                       MAX(id) AS last_message_id
                FROM messages
                WHERE sender_id=? OR receiver_id=?
                GROUP BY other_id
            )
            SELECT u.id AS user_id, u.username, u.full_name, u.avatar_url,
                   m.message_text AS last_message, m.created_at, m.shared_post_id
            FROM participants p
            JOIN messages m ON m.id=p.last_message_id
            JOIN users u ON u.id=p.other_id
            ORDER BY m.id DESC
            """,
            (user_id, user_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@notification_router.get("")
def notifications(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            "SELECT id,actor_id,type,message,reference_id,is_read,created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@notification_router.post("/{notification_id}/read")
def read_notification(notification_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        cursor = connection.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notification_id, user_id))
        if cursor.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy thông báo")
        connection.commit()
        return {"id": notification_id, "is_read": True}
    finally:
        connection.close()


@notification_router.delete("/{notification_id}", status_code=204)
def delete_notification(notification_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        cursor = connection.execute(
            "DELETE FROM notifications WHERE id=? AND user_id=?",
            (notification_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy thông báo")
        connection.commit()
    finally:
        connection.close()
