# CookingAppProject_Back-end_Nhom1
ĐỀ TÀI: ỨNG DỤNG NẤU ĂN VỚI BỘ LỌC VÀ LIÊN KẾT MẠNG XÃ HỘI
Danh sách thành viên nhóm 1:
  Lê Hoàng Thanh Trúc - 24521868
  Huỳnh Thị Như Hiếu - 24520489
  Nguyễn Phan Thanh Thủy - 23521558

## User Profile API

### Chạy local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Thay JWT_SECRET_KEY trong .env bằng chuỗi bí mật dùng chung với module auth.
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Các endpoint profile yêu cầu header `Authorization: Bearer <token>`. Token dùng
HS256, claim `sub` là ID người dùng dạng chuỗi và bắt buộc có `exp`.

- `GET /api/profile/me`: lấy hồ sơ của người dùng hiện tại.
- `PATCH /api/profile/me`: cập nhật `full_name`, `phone_number`, `bio`.
- `POST /api/profile/me/avatar`: tải ảnh JPEG, PNG hoặc WebP tối đa 5 MiB.

`DATABASE_PATH` và `UPLOAD_DIR` có thể đổi qua biến môi trường. Khi triển khai,
cả database SQLite và thư mục upload cần nằm trên persistent disk.

### Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```
