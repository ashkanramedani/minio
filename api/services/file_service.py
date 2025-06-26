# api/services/file_service.py
from sqlalchemy.orm import Session
from models import FileModel, FileRequestLog
from sqlalchemy.dialects.postgresql import UUID
from typing import List

def save_file_to_db(db: Session, bucket_name: str, file_name: str, file_type: str, file_size: float, public_url: str, version_id: str, user_id: str):
    new_file = FileModel(
        file_name=file_name,        
        bucket_name=bucket_name,
        file_type=file_type,
        file_size=file_size,
        public_url=public_url,
        version_id=version_id,  # ذخیره نسخه فایل
        user_id=user_id  # ذخیره شناسه کاربر
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    return new_file

def log_request(db: Session, file_id: str, ip_address: str, user_agent: str = None, project_name: str = None):
    """
    ثبت لاگ درخواست فایل.
    """
    new_request = FileRequestLog(
        file_id=file_id,
        ip_address=ip_address,
        user_agent=user_agent,
        project_name=project_name,
    )
    db.add(new_request)
    db.commit()


def get_files(db: Session, file_ids: List[UUID], bucket: str = None) -> List[FileModel]:
    """
    Retrieve FileModel instances from the database by their UUIDs.
    """
    return db.query(FileModel).filter(FileModel.id.in_(file_ids)).all()