# api/models/file_model.py

from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from dbs import Base
from uuid import uuid4
from datetime import datetime

class FileRequestLog(Base):
    __tablename__ = "file_request_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)  # نوع داده UUID
    ip_address = Column(String, nullable=False)
    user_agent = Column(String, nullable=True)
    project_name = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    file = relationship("FileModel", back_populates="requests")

class FileModel(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    file_name = Column(String, nullable=False)  # نام فایل اصلی   
    file_key = Column(String, nullable=False)  # نام فایل اصلی   
    file_extension = Column(String, nullable=True)  # پسوند فایل
    bucket_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Float, nullable=False)
    download_count = Column(Integer, default=0)
    public_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String, index=True)  # شناسه کاربر مرتبط با فایل
    version_id = Column(String, nullable=True)  # نگهداری نسخه فایل
    folder_path = Column(String, nullable=False)

    # ارتباط با جدول درخواست‌ها
    requests = relationship("FileRequestLog", back_populates="file", cascade="all, delete-orphan")
