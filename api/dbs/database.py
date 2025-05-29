from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from configs import settings
from minio import Minio

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,  # تعداد کانکشن‌های همزمان
    max_overflow=20,  # تعداد کانکشن‌های اضافی
    pool_timeout=30,  # مدت زمان انتظار برای دریافت کانکشن
    pool_pre_ping=True  # بررسی سالم بودن کانکشن قبل از استفاده
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize MinIO client
minio_client = Minio(
    endpoint=settings.MINIO_URL.replace("http://", "").replace("https://", ""),
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_URL.startswith("https://")
)