import os
import sqlite3
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from database import get_db
from security import get_current_user_id

router = APIRouter()
schedule_router = APIRouter()
MAX_RECIPE_IMAGE_BYTES = 8 * 1024 * 1024
RECIPE_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class IngredientInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=30)


class StepInput(BaseModel):
    step_number: int = Field(gt=0)
    instruction: str = Field(min_length=1, max_length=2000)
    media_url: str | None = None
    media_type: Literal["IMAGE", "VIDEO"] = "IMAGE"


class RecipeInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    caption: str | None = Field(default=None, max_length=2000)
    cover_image_url: str = Field(min_length=1)
    servings: int | None = Field(default=None, gt=0)
    cooking_time: int | None = Field(default=None, gt=0)
    difficulty: Literal["Dễ", "Trung bình", "Khó"] = "Dễ"
    privacy: Literal["PUBLIC", "FRIENDS", "ONLY_ME"] = "PUBLIC"
    ingredients: list[IngredientInput] = Field(min_length=1)
    steps: list[StepInput] = Field(min_length=1)


class ReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str | None = Field(default=None, max_length=2000)
    media_url: str | None = Field(default=None, max_length=1000)


class ScheduleInput(BaseModel):
    recipe_id: int
    scheduled_for: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("scheduled_for")
    @classmethod
    def validate_scheduled_for(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("scheduled_for phải theo định dạng ISO 8601") from error
        return value


@router.post("/upload")
async def upload_recipe_image(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    content_type = (file.content_type or "").lower()
    extension = RECIPE_IMAGE_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(415, "Ảnh công thức phải là JPEG, PNG hoặc WebP")
    content = await file.read(MAX_RECIPE_IMAGE_BYTES + 1)
    await file.close()
    if len(content) > MAX_RECIPE_IMAGE_BYTES:
        raise HTTPException(413, "Ảnh công thức không được vượt quá 8 MiB")
    try:
        from io import BytesIO
        with Image.open(BytesIO(content)) as image:
            image.verify()
            if (image.format or "").upper() not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Nội dung tệp không phải ảnh hợp lệ")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(415, "Nội dung tệp không phải ảnh hợp lệ") from exc
    root = Path(os.getenv("UPLOAD_DIR", "uploads")).expanduser().resolve()
    directory = root / "recipes"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    (directory / filename).write_bytes(content)
    return {"media_url": f"/uploads/recipes/{filename}"}


def _require_recipe(connection: sqlite3.Connection, recipe_id: int):
    row = connection.execute(
        "SELECT p.*, r.* FROM posts p JOIN recipes r ON r.post_id=p.id WHERE p.id=?",
        (recipe_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Không tìm thấy công thức")
    return row


def _recipe_detail(connection: sqlite3.Connection, recipe_id: int) -> dict:
    row = _require_recipe(connection, recipe_id)
    ingredients = connection.execute(
        "SELECT ingredient_name AS name, amount, unit FROM recipe_ingredients WHERE post_id=? ORDER BY id",
        (recipe_id,),
    ).fetchall()
    steps = connection.execute(
        "SELECT step_number, instruction, media_url, media_type FROM recipe_steps WHERE post_id=? ORDER BY step_number",
        (recipe_id,),
    ).fetchall()
    owner = connection.execute(
        "SELECT username, full_name, avatar_url FROM users WHERE id=?", (row["user_id"],)
    ).fetchone()
    return {
        "id": recipe_id,
        "user_id": row["user_id"],
        "author": dict(owner),
        "title": row["recipe_title"],
        "caption": row["caption"],
        "cover_image_url": row["cover_image_url"],
        "servings": row["servings"],
        "cooking_time": row["cooking_time"],
        "difficulty": row["difficulty"],
        "privacy": row["privacy"],
        "created_at": row["created_at"],
        "ingredients": [dict(item) for item in ingredients],
        "steps": [dict(item) for item in steps],
    }


def _replace_children(connection: sqlite3.Connection, recipe_id: int, data: RecipeInput):
    connection.execute("DELETE FROM recipe_ingredients WHERE post_id=?", (recipe_id,))
    connection.execute("DELETE FROM recipe_steps WHERE post_id=?", (recipe_id,))
    connection.executemany(
        "INSERT INTO recipe_ingredients(post_id, ingredient_name, amount, unit) VALUES(?,?,?,?)",
        [(recipe_id, item.name.strip(), item.amount, item.unit.strip()) for item in data.ingredients],
    )
    connection.executemany(
        "INSERT INTO recipe_steps(post_id, step_number, instruction, media_url, media_type) VALUES(?,?,?,?,?)",
        [(recipe_id, item.step_number, item.instruction.strip(), item.media_url, item.media_type) for item in data.steps],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_recipe(data: RecipeInput, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        cursor = connection.execute(
            "INSERT INTO posts(user_id, post_type, caption, privacy) VALUES(?, 'RECIPE', ?, ?)",
            (user_id, data.caption, data.privacy),
        )
        recipe_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO recipes(post_id, recipe_title, cover_image_url, servings, cooking_time, difficulty) VALUES(?,?,?,?,?,?)",
            (recipe_id, data.title.strip(), data.cover_image_url, data.servings, data.cooking_time, data.difficulty),
        )
        _replace_children(connection, recipe_id, data)
        connection.commit()
        return _recipe_detail(connection, recipe_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@router.get("")
def list_recipes(
    q: str | None = None,
    difficulty: str | None = None,
    exclude_ingredient: list[str] = Query(default=[]),
    min_rating: int | None = Query(default=None, ge=1, le=5),
    max_time: int | None = Query(default=None, gt=0, le=1440),
    limit: int = Query(30, ge=1, le=100),
):
    connection = get_db()
    try:
        clauses = ["p.post_type='RECIPE'", "p.privacy='PUBLIC'"]
        values: list[object] = []
        if q:
            clauses.append("(lower(r.recipe_title) LIKE ? OR lower(COALESCE(p.caption,'')) LIKE ?)")
            needle = f"%{q.strip().lower()}%"
            values.extend([needle, needle])
        if difficulty:
            clauses.append("r.difficulty=?")
            values.append(difficulty)
        if max_time is not None:
            clauses.append("r.cooking_time<=?")
            values.append(max_time)
        for ingredient in exclude_ingredient:
            clauses.append("NOT EXISTS (SELECT 1 FROM recipe_ingredients ri WHERE ri.post_id=p.id AND lower(ri.ingredient_name) LIKE ?)")
            values.append(f"%{ingredient.strip().lower()}%")
        if min_rating is not None:
            clauses.append("COALESCE((SELECT AVG(rr.rating) FROM recipe_reviews rr WHERE rr.recipe_id=p.id),0)>=?")
            values.append(min_rating)
        rows = connection.execute(
            f"SELECT p.id FROM posts p JOIN recipes r ON r.post_id=p.id WHERE {' AND '.join(clauses)} ORDER BY p.created_at DESC, p.id DESC LIMIT ?",
            (*values, limit),
        ).fetchall()
        return [_recipe_detail(connection, row["id"]) for row in rows]
    finally:
        connection.close()


@router.get("/favorites/me")
def favorite_recipes(user_id: int = Depends(get_current_user_id)):
    return _personal_recipes("favorites", user_id)


@router.get("/saved/me")
def saved_recipes(user_id: int = Depends(get_current_user_id)):
    return _personal_recipes("saved_recipes", user_id)


@router.get("/reviews/me")
def my_reviews(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            "SELECT rr.id, rr.recipe_id, r.recipe_title AS title, rr.rating, rr.content, rrm.media_url, rr.created_at "
            "FROM recipe_reviews rr JOIN recipes r ON r.post_id=rr.recipe_id "
            "LEFT JOIN recipe_review_media rrm ON rrm.review_id=rr.id WHERE rr.user_id=? "
            "ORDER BY rr.updated_at DESC, rr.id DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _personal_recipes(table: str, user_id: int):
    connection = get_db()
    try:
        rows = connection.execute(
            f"SELECT recipe_id FROM {table} WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [_recipe_detail(connection, row["recipe_id"]) for row in rows]
    finally:
        connection.close()


@router.get("/{recipe_id}")
def get_recipe(recipe_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        recipe = _recipe_detail(connection, recipe_id)
        if recipe["privacy"] != "PUBLIC" and recipe["user_id"] != user_id:
            raise HTTPException(403, "Bạn không có quyền xem công thức này")
        return recipe
    finally:
        connection.close()


@router.put("/{recipe_id}")
def update_recipe(recipe_id: int, data: RecipeInput, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        row = _require_recipe(connection, recipe_id)
        if row["user_id"] != user_id:
            raise HTTPException(403, "Bạn không có quyền sửa công thức này")
        connection.execute("UPDATE posts SET caption=?, privacy=? WHERE id=?", (data.caption, data.privacy, recipe_id))
        connection.execute(
            "UPDATE recipes SET recipe_title=?, cover_image_url=?, servings=?, cooking_time=?, difficulty=? WHERE post_id=?",
            (data.title.strip(), data.cover_image_url, data.servings, data.cooking_time, data.difficulty, recipe_id),
        )
        _replace_children(connection, recipe_id, data)
        connection.commit()
        return _recipe_detail(connection, recipe_id)
    finally:
        connection.close()


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        row = _require_recipe(connection, recipe_id)
        if row["user_id"] != user_id:
            raise HTTPException(403, "Bạn không có quyền xóa công thức này")
        connection.execute("DELETE FROM posts WHERE id=?", (recipe_id,))
        connection.commit()
    finally:
        connection.close()


def _toggle(table: str, recipe_id: int, user_id: int):
    connection = get_db()
    try:
        _require_recipe(connection, recipe_id)
        existing = connection.execute(f"SELECT 1 FROM {table} WHERE user_id=? AND recipe_id=?", (user_id, recipe_id)).fetchone()
        if existing:
            connection.execute(f"DELETE FROM {table} WHERE user_id=? AND recipe_id=?", (user_id, recipe_id))
        else:
            connection.execute(f"INSERT INTO {table}(user_id, recipe_id) VALUES(?,?)", (user_id, recipe_id))
        connection.commit()
        return {"active": not bool(existing)}
    finally:
        connection.close()


@router.post("/{recipe_id}/favorite")
def toggle_favorite(recipe_id: int, user_id: int = Depends(get_current_user_id)):
    return _toggle("favorites", recipe_id, user_id)


@router.post("/{recipe_id}/save")
def toggle_saved(recipe_id: int, user_id: int = Depends(get_current_user_id)):
    return _toggle("saved_recipes", recipe_id, user_id)


@router.post("/{recipe_id}/reviews", status_code=201)
def upsert_review(recipe_id: int, data: ReviewInput, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        _require_recipe(connection, recipe_id)
        connection.execute(
            "INSERT INTO recipe_reviews(recipe_id,user_id,rating,content) VALUES(?,?,?,?) ON CONFLICT(recipe_id,user_id) DO UPDATE SET rating=excluded.rating, content=excluded.content, updated_at=CURRENT_TIMESTAMP",
            (recipe_id, user_id, data.rating, data.content),
        )
        review_id = connection.execute(
            "SELECT id FROM recipe_reviews WHERE recipe_id=? AND user_id=?", (recipe_id, user_id)
        ).fetchone()["id"]
        connection.execute("DELETE FROM recipe_review_media WHERE review_id=?", (review_id,))
        if data.media_url:
            connection.execute(
                "INSERT INTO recipe_review_media(review_id,media_url,media_type) VALUES(?,?,'IMAGE')",
                (review_id, data.media_url),
            )
        connection.commit()
        return {"recipe_id": recipe_id, "user_id": user_id, **data.model_dump()}
    finally:
        connection.close()


@router.get("/{recipe_id}/reviews")
def list_reviews(recipe_id: int):
    connection = get_db()
    try:
        _require_recipe(connection, recipe_id)
        rows = connection.execute(
            "SELECT rr.id, rr.user_id, u.username, rr.rating, rr.content, rrm.media_url, rr.created_at FROM recipe_reviews rr JOIN users u ON u.id=rr.user_id LEFT JOIN recipe_review_media rrm ON rrm.review_id=rr.id WHERE rr.recipe_id=? ORDER BY rr.created_at DESC",
            (recipe_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@schedule_router.post("", status_code=201)
def create_schedule(data: ScheduleInput, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        _require_recipe(connection, data.recipe_id)
        cursor = connection.execute(
            "INSERT INTO cooking_schedules(user_id,recipe_id,scheduled_for,note) VALUES(?,?,?,?)",
            (user_id, data.recipe_id, data.scheduled_for, data.note),
        )
        connection.commit()
        return {"id": cursor.lastrowid, "user_id": user_id, **data.model_dump()}
    finally:
        connection.close()


@schedule_router.get("")
def list_schedules(user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        rows = connection.execute(
            "SELECT cs.*, r.recipe_title AS title FROM cooking_schedules cs JOIN recipes r ON r.post_id=cs.recipe_id WHERE cs.user_id=? ORDER BY cs.scheduled_for",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@schedule_router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, user_id: int = Depends(get_current_user_id)):
    connection = get_db()
    try:
        cursor = connection.execute(
            "DELETE FROM cooking_schedules WHERE id=? AND user_id=?",
            (schedule_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy lịch nấu")
        connection.commit()
    finally:
        connection.close()
