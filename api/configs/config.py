from pydantic import BaseSettings
import os

class Settings(BaseSettings):
    API_NAME: str = os.getenv("API_NAME")
    API_KEY: str = os.getenv("API_KEY")
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY")
    VERSION: str = os.getenv("VERSION")

    DATABASE_URL: str = os.getenv("DATABASE_URL")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT: int = os.getenv("POSTGRES_PORT")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB")

    MINIO_URL: str = os.getenv("MINIO_URL")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY")

    REDIS_API_BASE: str = os.getenv("REDIS_API_BASE")
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD")
    REDIS_HOST: str = os.getenv("REDIS_HOST")
    REDIS_PORT: int = os.getenv("REDIS_PORT")
    REDIS_DB_INDEX: int = os.getenv("REDIS_DB_INDEX")

    URL_WALLET: str = os.getenv("URL_WALLET")
    URL_POST: str = os.getenv("URL_POST")
    URL_ACCOUNTING: str = os.getenv("URL_ACCOUNTING")
    URL_AUTHAPI: str = os.getenv("URL_AUTHAPI")
    URL_FILE: str = os.getenv("URL_FILE")
    URL_BBB: str = os.getenv("URL_BBB")
    URL_CART: str = os.getenv("URL_CART")
    URL_INVENTORY: str = os.getenv("URL_INVENTORY")
    URL_PANEL: str = os.getenv("URL_PANEL")
    
    BASE_DOMAIN: str = "file.ieltsdaily.ir"
    MAX_FILE_SIZE = 100 * 1024 * 1024 # 500MB
    MAX_TOTAL_UPLOAD_SIZE = 500 * 1024 * 1024 # 500MB

    class Config:
        env_file = ".env"  # مشخص‌کردن نام فایل env

# ایجاد نمونه از تنظیمات
settings = Settings()

allowed_extensions = [
    "jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp", "svg", "ico",  # Images
    "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v",          # Videos
    "mp3", "wav", "aac", "flac", "ogg", "m4a", "wma", "aiff",         # Audio
    "txt", "doc", "docx", "pdf", "odt", "rtf", "md",                 # Text Files
    "xls", "xlsx", "csv", "ods", "ppt", "pptx", "odp",               # Spreadsheets & Presentations
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz"                    # Compressed
]



# MAJOR . MINOR . PATCH . EXTRA
# 1. MAJOR (نسخه اصلی)
# این عدد نشان‌دهنده تغییرات بزرگ و ناسازگار با نسخه‌های قبلی است.
# 2. MINOR (نسخه فرعی)
# این عدد نشان‌دهنده اضافه شدن قابلیت‌های جدید است که با نسخه قبلی سازگار هستند.
# 3. PATCH (رفع اشکال)
# این عدد برای رفع باگ‌ها و مشکلات بدون اضافه کردن قابلیت‌های جدید استفاده می‌شود.
# 4. EXTRA (پارت چهارم)
# این بخش اختیاری است و معمولاً برای مشخص کردن موارد اضافی مثل نسخه پیش‌نمایش، بیلد، یا اصلاحات خاص استفاده می‌شود.