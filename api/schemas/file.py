# api/schemas/file.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class FileUploadResponse(BaseModel):
    file_id: str = Field(..., description="Unique identifier of the file")
    name: str = Field(..., description="Original name of the file")
    file_key: str = Field(..., description="Key of the file in the storage system")
    folder_path: str = Field(..., description="Path of the folder where the file is stored")
    file_type: str = Field(..., description="MIME type of the file")
    extension: str = Field(..., description="File extension (e.g., .jpg, .pdf)")
    size: int = Field(..., description="Size of the file in bytes")
    version_id: Optional[str] = Field(None, description="Version ID if versioning is enabled in MinIO")
    human_readable_size: str = Field(..., description="File size in human-readable format")
    last_modified: datetime = Field(..., description="Timestamp of file creation or last update")
    etag: str = Field(..., description="ETag or hash of the file")
    public_url: str = Field(..., description="Public URL to access the file")

    class Config:
        orm_mode = True


class FilesUploadResponse(BaseModel):
    message: str = Field(..., description="Status message")
    uploaded_files: List[FileUploadResponse] = Field(..., description="List of uploaded files")
    
    class Config:
        orm_mode = True