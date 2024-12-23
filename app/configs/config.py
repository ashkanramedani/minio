from pydantic import BaseSettings

class Settings(BaseSettings):
    API_NANE: str = "FastAPI MinIO Service"
    API_KEY: str = ""
    ADMIN_API_KEY: str = ""
    VERSION: str = "0.1.0-beta"

    DATABASE_URL: str = ""
    POSTGRES_HOST: str = ""
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "test"

    MINIO_URL: str = ""
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""

    REDIS_API_BASE: str = ""    
    REDIS_PASSWORD: str = ""
    REDIS_HOST: str = ""
    REDIS_PORT: int = 6379
    REDIS_DB_INDEX: int = 0

settings = Settings()



# MAJOR . MINOR . PATCH . EXTRA
# 1. MAJOR (نسخه اصلی)
# این عدد نشان‌دهنده تغییرات بزرگ و ناسازگار با نسخه‌های قبلی است.
# 2. MINOR (نسخه فرعی)
# این عدد نشان‌دهنده اضافه شدن قابلیت‌های جدید است که با نسخه قبلی سازگار هستند.
# 3. PATCH (رفع اشکال)
# این عدد برای رفع باگ‌ها و مشکلات بدون اضافه کردن قابلیت‌های جدید استفاده می‌شود.
# 4. EXTRA (پارت چهارم)
# این بخش اختیاری است و معمولاً برای مشخص کردن موارد اضافی مثل نسخه پیش‌نمایش، بیلد، یا اصلاحات خاص استفاده می‌شود.