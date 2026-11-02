import boto3
import uuid

# 1. Điền các thông số Cloudflare R2 của bạn vào đây
R2_ACCOUNT_ID = "128756c768355245b05dd05aaf41c249"
AWS_ACCESS_KEY_ID = "a127560a8b93b6c46de56c1eeb1821d4"
AWS_SECRET_ACCESS_KEY = "18dd7472f555f6f4e2d88e6ae6e39bd8d464bc8b0476215878d651daee2a7b7f"
BUCKET_NAME = "cooking-app-media"  # Tên Bucket bạn tạo trên R2
PUBLIC_DOMAIN = "https://pub-52fbec2f048b4573862992791c0b7a23.r2.dev"  # Public Development URL bạn đã bật

# 2. Khởi tạo S3 Client kết nối với Cloudflare R2
s3_client = boto3.client(
    "s3",
    endpoint_url=f"https://128756c768355245b05dd05aaf41c249.r2.cloudflarestorage.com",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

def upload_file_to_cloud(file_bytes, filename: str, content_type: str) -> str:
    """Tải file (ảnh/video) lên Cloudflare R2 và trả về URL công khai"""
    # Lấy đuôi file (jpg, png, mp4...)
    file_ext = filename.split(".")[-1] if "." in filename else "jpg"
    # Đặt tên file duy nhất bằng UUID để không bao giờ bị trùng file trên R2
    unique_filename = f"{uuid.uuid4()}.{file_ext}"

    # Đẩy file lên Bucket
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=unique_filename,
        Body=file_bytes,
        ContentType=content_type
    )

    # Trả về đường dẫn URL công khai để Android hiển thị
    return f"{PUBLIC_DOMAIN}/{unique_filename}"