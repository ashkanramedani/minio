from io import BytesIO
from minio.error import S3Error
from dbs import minio_client
from configs import settings, allowed_extensions
from starlette.status import HTTP_413_REQUEST_ENTITY_TOO_LARGE
from fastapi import HTTPException
from typing import List
from fastapi import UploadFile

def stream_minio_object(minio_response, buffer_size=1024 * 1024):  # 1 MB buffer
    for chunk in minio_response.stream(buffer_size):
        yield chunk

def stream_buffered(img_io, buffer_size=64 * 1024):  # 64 KB
    img_io.seek(0) 
    while True:
        data = img_io.read(buffer_size)
        if not data:
            break
        yield data

def does_path_exist(bucket_name: str, folder_path: str) -> bool:
    objects = minio_client.list_objects(bucket_name, prefix=folder_path, recursive=True)
    for obj in objects:
        return True 
    return False

def create_path_if_not_exists(bucket_name: str, folder_path: str):
    try:
        if not does_path_exist(bucket_name, folder_path):
            dummy_file = BytesIO(b"")
            folder_object_name = f"{folder_path}/.dummy"
            minio_client.put_object(bucket_name, folder_object_name, dummy_file, length=0)
            return True
        else: 
            return False    
    except S3Error as e:
        raise Exception(f"Failed to create path: {str(e)}")

def validate_file_size(upload_file):
    """
    Validate the uploaded file size.
    """
    file_content = upload_file.file.read()
    upload_file.file.seek(0)  # بازنشانی برای استفاده مجدد

    if len(file_content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{upload_file.filename}' exceeds the maximum allowed size of {settings.MAX_FILE_SIZE // (1024 * 1024)} MB"
        )

def validate_total_size(files: List[UploadFile]):
    total_size = 0
    for file in files:
        content = file.file.read()
        file.file.seek(0)
        total_size += len(content)
    if total_size > settings.MAX_TOTAL_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Total uploaded files exceed the maximum allowed size of {settings.MAX_TOTAL_UPLOAD_SIZE // 1024 // 1024} MB"
        )
      
def upload_file_to_minio(bucket_name: str, folder_path: str, file_name: str, file_content):
    try:        
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        object_name = f"{folder_path}/{file_name}" if folder_path != "" else file_name
        
        result = minio_client.put_object(
            bucket_name,
            object_name,
            file_content,
            length=-1,  # Auto-detect length
            part_size=64 * 1024 * 1024  # 64 MB parts
        )

        return result
    except S3Error as e:
        raise Exception(f"Failed to upload file: {str(e)}")
    
def generate_presigned_url(bucket_name: str, file_name: str):
    """
    Generate a presigned URL
    """
    try:
        return minio_client.presigned_get_object(bucket_name, file_name)
    except S3Error as e:
        raise Exception(f"Failed to generate presigned URL: {str(e)}")
    
def bucket_info(bucket_name: str):    
    total_files = 0
    total_size_bytes = 0

    objects = minio_client.list_objects(bucket_name, recursive=True)

    for obj in objects:
        total_files += 1
        total_size_bytes += obj.size

    return {
        "bucket_name": bucket_name,
        "total_files": total_files,
        "total_size_bytes": total_size_bytes,
        "total_size_human_readable": human_readable_size(total_size_bytes)
    }

def list_buckets():
    try:
        buckets = minio_client.list_buckets()
        bucket_list = []
        for bucket in buckets:
            is_public = is_bucket_public(bucket.name)
            bucket_info_data = bucket_info(bucket.name)
            bucket_list.append({
                "name": bucket.name,
                "creation_date": bucket.creation_date,
                "public": is_public,        
                "total_files": bucket_info_data.get("total_files", -1),
                "total_size_bytes": bucket_info_data.get("total_size_bytes", -1),
                "total_size_human_readable": bucket_info_data.get("total_size_human_readable", 0)
            })
        return bucket_list
    except Exception as e:
        raise Exception(f"Failed to list buckets: {str(e)}")
    
def is_bucket_public(bucket_name: str) -> bool:
    """
    Checks whether the bucket is public or not.
    """
    try:
        policy = minio_client.get_bucket_policy(bucket_name)
        if "s3:GetObject" in policy:
            return True
        return False
    except Exception:
        return False
    
def list_objects_in_bucket(bucket_name: str, folder_path: str):
    """
    Returns a list of objects in a bucket.
    """
    try:
        if folder_path != "":
            objects = minio_client.list_objects(bucket_name, prefix=f"{folder_path}/", recursive=True)
        else:            
            objects = minio_client.list_objects(bucket_name, recursive=True)
        object_list = []
        for obj in objects:
            object_list.append({
                "name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified,
                "etag": obj.etag
            })
        return object_list
    except Exception as e:
        raise Exception(f"Failed to list objects in bucket '{bucket_name}': {str(e)}")
    
def human_readable_size(size_in_bytes):
    """
    Convert file size to human readable format (KB, MB, GB).
    """
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / 1024 ** 2:.2f} MB"
    else:
        return f"{size_in_bytes / 1024 ** 3:.2f} GB"
    
def validate_file_types(file_extension: str) -> bool:
    if file_extension in allowed_extensions:
        return True
    return False
