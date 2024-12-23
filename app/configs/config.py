from pydantic import BaseSettings

class Settings(BaseSettings):
    API_NANE: str = "FastAPI MinIO Service"
    API_KEY: str = "42k6LXj8ATdznqs"
    ADMIN_API_KEY: str = "admin_api_key_123"
    VERSION: str = "0.1.0-beta"

    DATABASE_URL: str = "postgresql://ieltsdaily:AliBig+Hi@185.112.32.51:15432/test"
    POSTGRES_HOST: str = "185.112.32.51"
    POSTGRES_PORT: int = 15432
    POSTGRES_USER: str = "ieltsdaily"
    POSTGRES_PASSWORD: str = "AliBig+Hi"
    POSTGRES_DB: str = "test"

    MINIO_URL: str = "http://minio.ieltsdailylms.com:9001"
    MINIO_ACCESS_KEY: str = "b6gHWF9yW1VtHe7pTUJx"
    MINIO_SECRET_KEY: str = "gFbzLYhW7GtTQiOWgvgvQO1SioFvDKCPNJgY0r5g"

    REDIS_API_BASE: str = "http://185.112.32.51:8888"    
    REDIS_PASSWORD: str = "eYVX7EwVmmxKPCDmwMtyKVge8oLd2t81HBSDsdkjgasdj"
    REDIS_HOST: str = "redis-db"
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