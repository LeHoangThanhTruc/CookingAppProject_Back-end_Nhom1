# Cooking App API

FastAPI backend dùng chung cho Windows 10/11, Android Emulator và Windows Server. SQLite database và uploads được cấu hình bằng `.env`.

## Chạy trên Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Tạo JWT_SECRET_KEY mới trong .env trước khi chạy.
.\.venv\Scripts\python.exe seed_data.py
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`
- Android Emulator gọi backend qua `http://10.0.2.2:8000/`.

Bốn tài khoản seed dùng chung mật khẩu `Demo12345`: `albert@example.com`, `gordon@example.com`, `hoa@example.com`, `lan@example.com`.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Import `postman/CookingApp.postman_collection.json` vào Postman. Request Login tự lưu `access_token` cho các request sau.

Có thể chạy toàn bộ Collection không cần đăng nhập Postman Desktop:

```powershell
npx --yes newman run .\postman\CookingApp.postman_collection.json
```

Collection kiểm tra health, auth, profile, tạo công thức thành bài feed, tìm kiếm, tương tác, lịch nấu, social, message, notification và các lỗi 401/422.

## Bàn giao Windows Server

Source không cần sửa. Người triển khai tạo `.env` riêng, ví dụ:

```env
DATABASE_PATH=C:/app/data/database.db
UPLOAD_DIR=C:/app/uploads
JWT_SECRET_KEY=<secret-moi>
```

Chạy không có `--reload` và kiểm tra health:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
Invoke-RestMethod http://127.0.0.1:8000/health
```

Windows Service, reverse proxy, HTTPS và firewall thuộc giai đoạn triển khai. Không commit `.env`, database runtime hoặc uploads.
