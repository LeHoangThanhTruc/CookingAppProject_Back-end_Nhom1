def _register_and_login(client, email="friend@example.com", username="friend"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Password123"},
    )
    assert response.status_code == 201
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "Password123"}
    )
    assert response.status_code == 200
    return response.json()


def test_health_checks_database_and_uploads(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "uploads": "ok"}


def test_post_upload_requires_auth_and_valid_image(client, authorization):
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    missing_token = client.post("/api/posts/upload", files={"file": ("post.png", png, "image/png")})
    assert missing_token.status_code == 401
    invalid = client.post(
        "/api/posts/upload",
        headers=authorization,
        files={"file": ("post.png", b"not-an-image", "image/png")},
    )
    assert invalid.status_code == 415
    uploaded = client.post(
        "/api/posts/upload",
        headers=authorization,
        files={"file": ("post.png", png, "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["media_url"].startswith("/uploads/posts/")


def test_recipe_lifecycle_and_personal_lists(client, authorization):
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    uploaded = client.post(
        "/api/recipes/upload",
        headers=authorization,
        files={"file": ("cover.png", png, "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["media_url"].startswith("/uploads/recipes/")
    invalid_upload = client.post(
        "/api/recipes/upload",
        headers=authorization,
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert invalid_upload.status_code == 415
    created = client.post(
        "/api/recipes",
        headers=authorization,
        json={
            "title": "Canh chua",
            "caption": "Món nhà",
            "cover_image_url": uploaded.json()["media_url"],
            "servings": 2,
            "cooking_time": 30,
            "difficulty": "Dễ",
            "privacy": "PUBLIC",
            "ingredients": [{"name": "Cá", "amount": 300, "unit": "g"}],
            "steps": [{"step_number": 1, "instruction": "Nấu nước dùng"}],
        },
    )
    assert created.status_code == 201
    recipe_id = created.json()["id"]

    feed = client.get("/api/posts/feed", headers=authorization)
    assert feed.status_code == 200
    recipe_post = next(item for item in feed.json()["data"] if item["post_id"] == recipe_id)
    assert recipe_post["post_type"] == "RECIPE"
    assert recipe_post["caption"] == "Món nhà"
    assert recipe_post["recipe_details"]["title"] == "Canh chua"

    detail = client.get(f"/api/recipes/{recipe_id}", headers=authorization)
    assert detail.status_code == 200
    assert detail.json()["ingredients"][0]["name"] == "Cá"

    searched = client.get("/api/recipes", params={"q": "canh", "difficulty": "Dễ"})
    assert [item["id"] for item in searched.json()] == [recipe_id]

    assert client.post(f"/api/recipes/{recipe_id}/favorite", headers=authorization).status_code == 200
    assert client.post(f"/api/recipes/{recipe_id}/save", headers=authorization).status_code == 200
    assert client.post(
        "/api/schedules",
        headers=authorization,
        json={"recipe_id": recipe_id, "scheduled_for": "2026-11-11T18:00:00"},
    ).status_code == 201
    assert len(client.get("/api/recipes/favorites/me", headers=authorization).json()) == 1
    assert len(client.get("/api/recipes/saved/me", headers=authorization).json()) == 1
    schedules = client.get("/api/schedules", headers=authorization).json()
    assert len(schedules) == 1
    assert client.delete(f"/api/schedules/{schedules[0]['id']}", headers=authorization).status_code == 204
    assert client.get("/api/schedules", headers=authorization).json() == []

    review = client.post(
        f"/api/recipes/{recipe_id}/reviews",
        headers=authorization,
        json={"rating": 5, "content": "Rất ngon", "media_url": uploaded.json()["media_url"]},
    )
    assert review.status_code == 201
    assert client.get(f"/api/recipes/{recipe_id}/reviews").json()[0]["rating"] == 5
    mine = client.get("/api/recipes/reviews/me", headers=authorization)
    assert mine.status_code == 200
    assert mine.json()[0]["recipe_id"] == recipe_id
    assert mine.json()[0]["media_url"] == uploaded.json()["media_url"]

    updated_payload = {
        "title": "Canh chua cá",
        "caption": "Đã chỉnh sửa",
        "cover_image_url": uploaded.json()["media_url"],
        "servings": 3,
        "cooking_time": 25,
        "difficulty": "Trung bình",
        "privacy": "PUBLIC",
        "ingredients": [{"name": "Cá", "amount": 350, "unit": "g"}],
        "steps": [{"step_number": 1, "instruction": "Nấu chín"}],
    }
    updated = client.put(f"/api/recipes/{recipe_id}", headers=authorization, json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["title"] == "Canh chua cá"
    assert client.delete(f"/api/recipes/{recipe_id}", headers=authorization).status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}", headers=authorization).status_code == 404


def test_missing_comment_reaction_is_rejected(client, authorization):
    response = client.post(
        "/api/posts/comments/999999/react",
        headers=authorization,
        json={"reaction_type": "LIKE"},
    )
    assert response.status_code == 404
    invalid_schedule = client.post(
        "/api/schedules",
        headers=authorization,
        json={"recipe_id": 1, "scheduled_for": "not-a-date"},
    )
    assert invalid_schedule.status_code == 422


def test_post_interactions_create_owner_notifications(client, authorization):
    created = client.post(
        "/api/recipes",
        headers=authorization,
        json={
            "title": "Món để tương tác",
            "cover_image_url": "/uploads/test.png",
            "servings": 1,
            "cooking_time": 10,
            "difficulty": "Dễ",
            "privacy": "PUBLIC",
            "ingredients": [{"name": "Gạo", "amount": 1, "unit": "bát"}],
            "steps": [{"step_number": 1, "instruction": "Nấu"}],
        },
    )
    post_id = created.json()["id"]
    friend = _register_and_login(client, "notifier@example.com", "notifier")
    friend_auth = {"Authorization": f"Bearer {friend['access_token']}"}
    assert client.post(f"/api/posts/{post_id}/like", headers=friend_auth).status_code == 200
    assert client.post(f"/api/posts/{post_id}/comments", headers=friend_auth, json={"content": "Ngon"}).status_code == 200
    parent_id = client.get(f"/api/posts/{post_id}/comments", headers=authorization).json()["comments"][0]["comment_id"]
    assert client.post(
        f"/api/posts/{post_id}/comments",
        headers=authorization,
        json={"content": "Cảm ơn bạn", "parent_id": parent_id},
    ).status_code == 200
    friend_kinds = {item["type"] for item in client.get("/api/notifications", headers=friend_auth).json()}
    assert "COMMENT_REPLY" in friend_kinds
    assert client.post(
        f"/api/posts/{post_id}/comments",
        headers=authorization,
        json={"content": "Sai parent", "parent_id": 999999},
    ).status_code == 404
    assert client.post(f"/api/posts/{post_id}/share-to-feed", headers=friend_auth, json={"caption": "Xem món này", "privacy": "PUBLIC"}).status_code == 200
    kinds = {item["type"] for item in client.get("/api/notifications", headers=authorization).json()}
    assert {"POST_LIKE", "POST_COMMENT", "POST_SHARE"}.issubset(kinds)


def test_profile_friendship_messages_and_notifications(client, authorization):
    friend = _register_and_login(client)
    friend_id = friend["user"]["id"]
    friend_auth = {"Authorization": f"Bearer {friend['access_token']}"}

    profile = client.get(f"/api/profile/{friend_id}", headers=authorization)
    assert profile.status_code == 200
    assert "email" not in profile.json()

    request = client.post(
        "/api/social/friend-requests", headers=authorization, json={"friend_id": friend_id}
    )
    assert request.status_code == 201
    request_id = request.json()["id"]
    pending = client.get("/api/social/friend-requests", headers=friend_auth)
    assert pending.status_code == 200
    assert pending.json()[0]["id"] == request_id
    sent_requests = client.get("/api/social/friend-requests/sent", headers=authorization)
    assert sent_requests.status_code == 200
    assert sent_requests.json()[0]["id"] == request_id
    notifications = client.get("/api/notifications", headers=friend_auth).json()
    assert len(notifications) == 1
    notification_id = notifications[0]["id"]
    assert client.post(f"/api/notifications/{notification_id}/read", headers=friend_auth).json()["is_read"] is True
    assert client.delete(f"/api/notifications/{notification_id}", headers=friend_auth).status_code == 204

    accepted = client.post(
        f"/api/social/friend-requests/{request_id}/accept", headers=friend_auth
    )
    assert accepted.status_code == 200
    assert len(client.get("/api/social/friends", headers=authorization).json()) == 1
    assert client.post(f"/api/social/follow/{friend_id}", headers=authorization).json()["following"] is True
    assert client.get("/api/social/following", headers=authorization).json()[0]["id"] == friend_id
    assert client.get("/api/social/users", headers=authorization, params={"q": "friend"}).json()[0]["id"] == friend_id

    sent = client.post(
        "/api/messages", headers=authorization, json={"receiver_id": friend_id, "text": "Chào bạn"}
    )
    assert sent.status_code == 201
    conversation = client.get("/api/messages/1", headers=friend_auth)
    assert conversation.status_code == 200
    assert conversation.json()[0]["text"] == "Chào bạn"
    summaries = client.get("/api/messages", headers=friend_auth)
    assert summaries.status_code == 200
    assert summaries.json()[0]["last_message"] == "Chào bạn"

    second = _register_and_login(client, "cancel@example.com", "cancel_target")
    cancel_request = client.post(
        "/api/social/friend-requests", headers=authorization, json={"friend_id": second["user"]["id"]}
    )
    assert cancel_request.status_code == 201
    assert client.delete(
        f"/api/social/friend-requests/{cancel_request.json()['id']}", headers=authorization
    ).status_code == 204


def test_feed_and_recipe_detail_enforce_privacy(client, authorization):
    friend = _register_and_login(client, "private@example.com", "private_user")
    friend_auth = {"Authorization": f"Bearer {friend['access_token']}"}
    created = client.post(
        "/api/recipes",
        headers=friend_auth,
        json={
            "title": "Công thức riêng",
            "cover_image_url": "/uploads/private.jpg",
            "privacy": "ONLY_ME",
            "ingredients": [{"name": "Bí mật", "amount": 1, "unit": "phần"}],
            "steps": [{"step_number": 1, "instruction": "Không chia sẻ"}],
        },
    )
    assert created.status_code == 201
    recipe_id = created.json()["id"]

    owner_detail = client.get(f"/api/recipes/{recipe_id}", headers=friend_auth)
    assert owner_detail.status_code == 200
    assert client.get(f"/api/recipes/{recipe_id}", headers=authorization).status_code == 403

    feed_ids = [item["post_id"] for item in client.get("/api/posts/feed", headers=authorization).json()["data"]]
    assert recipe_id not in feed_ids
import base64

def test_recipe_advanced_filters(client):
    response = client.get(
        "/api/recipes",
        params=[("difficulty", "Dễ"), ("max_time", "30"), ("exclude_ingredient", "hải sản")],
    )
    assert response.status_code == 200
    assert all(item["difficulty"] == "Dễ" for item in response.json())
    assert all(item["cooking_time"] <= 30 for item in response.json())

