# app/routes/file_routes.py
from fastapi import File, APIRouter, UploadFile, HTTPException, Depends, Request, Form, Response
from sqlalchemy.orm import Session
from dbs import get_db, minio_client
from typing import List, Optional
from utils import (
    upload_file_to_minio,
    list_buckets,
    list_objects_in_bucket,
    human_readable_size,
    get,
    setex,
    create_path_if_not_exists, 
    does_path_exist,
    stream_buffered,
    stream_minio_object
)
from models import uuid4, FileModel, FileRequestLog
from services import log_request, get_files
from datetime import timedelta
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from minio.versioningconfig import VersioningConfig
from libs import logger
import base64
from uuid import UUID
import json
from mimetypes import guess_type
from PIL import Image
from io import BytesIO
from urllib.parse import quote
from zipfile import ZipFile

file_router = APIRouter(prefix="/files")

ignoree_list_delete_bucket = [
    "cdn",
    "financial",
    "ieltsdaily",
    "products",
    "tmp"
]
ignoree_list_delete_object_bucket = [
    "products",
    "images",
    "cdn"
]

def folder_path_validat(folder_path: str):
    if folder_path == "/":
        return False
    if folder_path and len(folder_path)>0 and folder_path[0] == "/":
        return False
    if folder_path and len(folder_path)>0 and folder_path[len(folder_path)-1] == "/":
        return False
    return True

def convert_folder_path_to_validate_path(folder_path: str):
    if folder_path == "/":
        folder_path = ""
    if folder_path and len(folder_path)>0 and folder_path[0] == "/":
        folder_path = folder_path[1:]
    if folder_path and len(folder_path)>0 and folder_path[len(folder_path)-1] == "/":
        folder_path = folder_path[:-1]
    return folder_path



@file_router.post("/create-path/{bucket_name}/{folder_path:path}", tags=["path"])
def create_path(bucket_name: str, folder_path: str):
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=400, detail=f"folder path is not valid")
    
    if folder_path == 'root' or folder_path.startswith('root/'):
        raise HTTPException(status_code=400, detail=f"you can't use 'root' in your path")
    
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
    
    if does_path_exist(bucket_name, folder_path) and folder_path != "":
        return {"message": f"Path '{folder_path}' does exist this path in bucket '{bucket_name}'."}
        
    try:
        dummy_file = BytesIO(b"")
        folder_object_name = f"{folder_path}/.dummy"  
        minio_client.put_object(bucket_name, folder_object_name, dummy_file, length=0)
        return {"message": f"Path '{folder_path}' created successfully in bucket '{bucket_name}'."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create path: {str(e)}")
    
@file_router.delete("/delete-path/{bucket_name}/{folder_path:path}", tags=["path"])
def delete_path(bucket_name: str, folder_path: str):
    folder_path = convert_folder_path_to_validate_path(folder_path)

    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=400, detail="Folder path is not valid")

    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")

    if not does_path_exist(bucket_name, folder_path):
        raise HTTPException(status_code=404, detail=f"Path '{folder_path}' does not exist in bucket '{bucket_name}'")

    try:
        # لیست تمام آبجکت‌های موجود در مسیر
        objects = list(minio_client.list_objects(bucket_name, prefix=f"{folder_path}/", recursive=False))

        if not objects:  # مسیر کاملاً خالی است
            minio_client.remove_object(bucket_name, folder_path)
            return {"message": f"Path '{folder_path}' deleted successfully from bucket '{bucket_name}' as it was empty."}

        # چک می‌کند که آیا فقط فایل `.dummy` در مسیر است
        if len(objects) == 1 and objects[0].object_name == f"{folder_path}/.dummy":
            minio_client.remove_object(bucket_name, objects[0].object_name)  # حذف فایل `.dummy`
            minio_client.remove_object(bucket_name, folder_path)  # حذف مسیر
            return {"message": f"Path '{folder_path}' and file '.dummy' deleted successfully from bucket '{bucket_name}'."}

        # اگر مسیر شامل فایل‌های دیگری نیز بود
        raise HTTPException(status_code=400, detail=f"Path '{folder_path}' is not empty and cannot be deleted.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete path: {str(e)}")



@file_router.post("/upload/multiple/{bucket_name}/{folder_path:path}", tags=["upload"], summary="Upload multiple files to MinIO and record metadata")
def upload_multiple_files(
    bucket_name: str,
    folder_path: str,
    files: List[UploadFile] = File(...),
    user_id: str = "00000000-0000-4b94-8e27-44833c2b940f",
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Upload multiple files to MinIO, save metadata in the database, and return upload results.
    """
    # Normalize and validate folder path
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=400, detail=f"Invalid folder path: '{folder_path}'")

    # Validate bucket existence
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")

    # Validate folder path exists in bucket (if provided)
    if folder_path and not does_path_exist(bucket_name, folder_path):
        raise HTTPException(status_code=404, detail=f"Path '{folder_path}' does not exist in bucket '{bucket_name}'")

    uploaded_files = []

    for upload in files:
        try:
            filename = upload.filename
            # Determine extension and type
            extension = filename.rsplit('.', 1)[-1] if '.' in filename else None
            if not extension:
                logger.warning(f"File extension missing: {filename}")

            mime_type = upload.content_type
            # Create DB record
            new_file = FileModel(
                file_name=filename,
                file_key="",
                file_extension=extension,
                bucket_name=bucket_name,
                file_type=mime_type,
                file_size=0,
                folder_path=folder_path,
                public_url="",
                user_id=user_id
            )
            db.add(new_file)
            db.commit()
            db.refresh(new_file)

            # Set object key and upload
            file_key = f"{new_file.id}.{extension}" if extension else str(new_file.id)
            # Upload to MinIO
            result = upload_file_to_minio(bucket_name, folder_path, file_key, upload.file)
            version_id = getattr(result, "version_id", None)

            # Calculate file size
            upload.file.seek(0, 2)
            size = upload.file.tell()
            if size <= 0:
                raise HTTPException(status_code=400, detail="Invalid file size")
            upload.file.seek(0)

            # Construct public URL
            base = request.base_url if request else ""
            public_url = f"{base}files/download/public-url/{bucket_name}/{new_file.id}?folder_path={folder_path}"
            if version_id:
                public_url += f"&version_id={version_id}"

            # Update DB record
            new_file.file_key = file_key
            new_file.file_size = size
            new_file.public_url = public_url
            new_file.version_id = version_id
            db.commit()

            uploaded_files.append({
                "file_id": str(new_file.id),
                "name": new_file.file_name,
                "file_key": new_file.file_key,
                "folder_path": new_file.folder_path,
                "file_type": new_file.file_type,
                "extension": new_file.file_extension,
                "size": new_file.file_size,
                "version_id": new_file.version_id,
                "human_readable_size": human_readable_size(new_file.file_size),
                "last_modified": new_file.created_at.isoformat(),
                "etag": str(new_file.id),
                "public_url": new_file.public_url
            })
        except HTTPException:
            # Propagate HTTP errors
            raise
        except Exception as e:
            logger.error(f"Failed to upload {filename}: {e}")
            continue

    return {"message": "Files uploaded successfully", "uploaded_files": uploaded_files}

@file_router.post("/upload/{bucket_name}/{folder_path:path}", tags=["upload"])
def upload_file(
    bucket_name: str,
    file: UploadFile,
    request: Request,
    folder_path: str,
    format: str = None,
    width: int = None,
    height: int = None,
    current_file_id: str = None,
    user_id: str = "00000000-0000-4b94-8e27-44833c2b940f",
    db: Session = Depends(get_db)
):
    """
    Upload the file to MinIO and save the information in the database.
    """
    
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")   

    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
    
    if not does_path_exist(bucket_name, folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")
    
    try:
        logger.info("Starting file upload process")

        file_extension = file.filename.split('.')[-1] if '.' in file.filename else None
        if not file_extension:
            logger.warning("File extension is missing")

        # شناسایی نوع فایل
        mime_type, _ = guess_type(file.filename)
        file_type = mime_type.split('/')[0] if mime_type else None
        create_new_flg = True
        existing_file = None
        if current_file_id:
            existing_file = db.query(FileModel).filter(FileModel.id == current_file_id and FileModel.folder_path == folder_path).first()
            if not existing_file:
                logger.error("File not found in database")
                create_new_flg = True
            else:
                file_key = str(existing_file.id) + (f".{file_extension}" if file_extension else "")
                create_new_flg = False
        if create_new_flg:
            new_file = FileModel(
                file_name=file.filename,
                file_key="",
                file_extension=file_extension,
                bucket_name=bucket_name,
                file_type=file.content_type,
                file_size=0,
                folder_path=folder_path,
                public_url="",
                user_id=user_id
            )
            db.add(new_file)
            db.commit()
            db.refresh(new_file)
            file_key = str(new_file.id) + (f".{file_extension}" if file_extension else "")
            current_file_id = new_file.id

        try:
            logger.info(f"Uploading file to MinIO: {file_key}")

            # اگر کاربر فرمت یا اندازه مشخص کرده باشد
            if format or width or height:
                if file_type == "image":
                    logger.info("Processing image for format/resize")
                    try:
                        img = Image.open(file.file)
                        original_width, original_height = img.size  # اندازه اصلی تصویر

                        if width and height:
                            logger.info(f"Resizing image to width={width}, height={height}")
                            img = img.resize((width, height))
                            
                        elif width:
                            # محاسبه نسبت طول برای حفظ نسبت ابعاد
                            new_height = int((width / original_width) * original_height)
                            logger.info(f"Resizing image to width={width}, height={new_height} (aspect ratio preserved)")
                            img = img.resize((width, new_height))

                        elif height:
                            # محاسبه نسبت عرض برای حفظ نسبت ابعاد
                            new_width = int((height / original_height) * original_width)
                            logger.info(f"Resizing image to width={new_width}, height={height} (aspect ratio preserved)")
                            img = img.resize((new_width, height))

                        if format:
                            logger.info(f"Converting image to format={format}")
                            file_extension = format.lower()
                            
                        img_io = BytesIO()
                        img.save(img_io, format=format.upper() if format else img.format)
                        img_io.seek(0)

                        file.file = img_io
                        file.content_type = f"image/{file_extension}"
                    except Exception as e:
                        logger.error(f"Error processing image: {e}")
                        raise HTTPException(status_code=400, detail="Error processing image for format/resize")

                else:
                    logger.info("در حال حاضر قابلیت کانورت این نوع فایل را نداریم")                    
                    raise HTTPException(status_code=400, detail="در حال حاضر قابلیت کانورت این نوع فایل را نداریم")

            result = upload_file_to_minio(bucket_name, folder_path, file_key, file.file)            
            version_id = getattr(result, "version_id", None)

            if not version_id:
                logger.warning("Version ID is None. Check if versioning is enabled in the bucket.")

            file_size = file.file.seek(0, 2)

            if file_size <= 0:
                logger.error("Invalid file size detected")
                raise HTTPException(status_code=400, detail="Invalid file size")
            
            file.file.seek(0)

            public_url = f"https://file.ieltsdaily.ir/files/download/public-url"

            if current_file_id: 
                public_url += f"/{current_file_id}"

            else: 
                public_url += f"/{new_file.id}"

            if version_id: 
                public_url += f"?version_id={version_id}"

            if existing_file:
                existing_file.file_name = file.filename
                existing_file.file_size = file_size
                existing_file.version_id = version_id
                existing_file.public_url = public_url
                existing_file.file_extension = file_extension
                existing_file.file_type = file.content_type
                db.commit()
                db.refresh(existing_file)
                updated_file = existing_file
                
            else:
                new_file.file_key = file_key
                new_file.file_size = file_size
                new_file.public_url = public_url
                new_file.version_id = version_id
                new_file.file_extension = file_extension
                new_file.file_type = file.content_type
                db.commit()
                updated_file = new_file        

            logger.info("File uploaded successfully")
            return {
                "message": "File uploaded successfully",
                "file_id": str(updated_file.id),
                "name": updated_file.file_name,
                "file_key": updated_file.file_key,
                "folder_path": updated_file.folder_path,
                "file_type": updated_file.file_type,
                "extension": updated_file.file_extension,
                "size": updated_file.file_size,
                "version_id": updated_file.version_id,
                "human_readable_size": human_readable_size(updated_file.file_size),
                "last_modified": updated_file.created_at.isoformat(),
                "etag": updated_file.id,
                "public_url": public_url
            }

        except Exception as upload_error:
            logger.error(f"Upload to MinIO failed: {str(upload_error)}")
            if not current_file_id:
                db.delete(new_file)
                db.commit()
            try:
                logger.info(f"Removing file from MinIO: {file_key}")
                minio_client.remove_object(bucket_name, file_key)
            except Exception as remove_error:
                logger.error(f"Failed to remove file from MinIO: {str(remove_error)}")
            raise HTTPException(status_code=500, detail=f"Upload to MinIO failed: {str(upload_error)}")

    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@file_router.get("/buckets", tags=["buckets"])
def get_buckets():
    """
    Get a list of buckets available in MinIO and their public or private status.
    """
    try:
        buckets = list_buckets()
        return buckets
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving buckets: {str(e)}")

@file_router.post("/buckets/{bucket_name}", tags=["buckets"])
def create_bucket(bucket_name: str):
    """
    Create a new bucket in MinIO with public settings and versioning capabilities.
    """    
    if minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=400, detail=f"Bucket '{bucket_name}' does exist")
    
    try:        
        minio_client.make_bucket(bucket_name)
        logger.info(f"Bucket '{bucket_name}' created successfully")

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*" 
                }
            ]
        }
        minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
        logger.info(f"Public policy set for bucket '{bucket_name}'")
        
        versioning_config = VersioningConfig("Enabled") 
        minio_client.set_bucket_versioning(bucket_name, versioning_config)
        logger.info(f"Versioning enabled for bucket '{bucket_name}'")

        return {"message": f"Bucket '{bucket_name}' created successfully with public access and versioning enabled"}
    except S3Error as e:
        logger.error(f"MinIO S3Error: {e}")
        raise HTTPException(status_code=500, detail=f"MinIO S3Error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error occurred: {str(e)}")

@file_router.delete("/buckets/{bucket_name}", tags=["buckets"])
def delete_bucket(bucket_name: str, db: Session = Depends(get_db)):
    """
    Delete a bucket if it is empty.
    """    
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
    
    if bucket_name in ignoree_list_delete_bucket:
        raise HTTPException(status_code=400, detail="You are not authorized to delete this bucket")
    
    try:
        db_objects_count = db.query(FileModel).filter(FileModel.bucket_name == bucket_name).count()
        if db_objects_count > 0:
            raise HTTPException(status_code=400, detail="Bucket is not empty in database")

        objects = list(minio_client.list_objects(bucket_name, recursive=True))
        if objects:
            raise HTTPException(status_code=400, detail="Bucket is not empty in MinIO")

        try:
            minio_client.remove_bucket(bucket_name)
        except S3Error as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove bucket: {str(e)}")

        return {"message": "Bucket deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting bucket: {str(e)}")

@file_router.get("/bucket/stats/{bucket_name}", tags=["buckets"])
def get_bucket_stats(bucket_name: str):
    """
    Returns the number of files and the total size of files in a bucket.
    param bucket_name: Bucket name
    return: Number of files and the total size (in bytes)
    """
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
    
    try:
        total_files = 0
        total_size = 0

        objects = minio_client.list_objects(bucket_name, recursive=True)

        for obj in objects:
            total_files += 1
            total_size += obj.size  

        return {
            "bucket_name": bucket_name,
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_human_readable": human_readable_size(total_size)
        }

    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve bucket stats: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")



@file_router.get("/objects/{bucket_name}/{folder_path:path}", tags=["objects"])
async def get_objects_in_bucket(bucket_name: str, folder_path: str, db: Session = Depends(get_db)):
    """
    Get a list of objects in a bucket.
    """
    
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")   

    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
    
    if not does_path_exist(bucket_name, folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")

    try:        
        objects = list_objects_in_bucket(bucket_name, folder_path)
        detailed_objects = []
        subfolders = set()

        for obj in objects:
            object_name = obj.get("object_name") or obj.get("name")
            if not object_name :
                continue  # در صورت عدم وجود نام فایل، این رکورد را نادیده بگیرید
                
            # بررسی اگر فایل یا فولدر است
            relative_path = object_name[len(folder_path):].strip("/")
            if "/" in relative_path:
                # فولدر فرعی
                subfolder_name = relative_path.split('/')[0]  # استخراج نام فولدر فرعی
                if subfolder_name and subfolder_name not in subfolders:
                    subfolders.add(subfolder_name)
                    detailed_objects.append({
                        "type": "folder",
                        "folder_name": subfolder_name,
                        "full_path": f"{folder_path}/{subfolder_name}".strip("/")
                    })
            else:
                if "/.dummy" in object_name:
                    continue
                # جستجوی فایل در دیتابیس
                file_record = db.query(FileModel).filter(
                    FileModel.bucket_name == bucket_name,
                    FileModel.folder_path == folder_path,
                    FileModel.file_key == relative_path
                ).first()

                if file_record:
                    file_type = file_record.file_type
                    file_name = file_record.file_name
                else:
                    file_type = "path"  # پیش‌فرض اگر فایل در دیتابیس یافت نشود
                    file_name = ""

                folder_pathes = folder_path.split('/')

                detailed_objects.append({
                    "type": "file",
                    "folder_name": folder_pathes[len(folder_pathes)-1],
                    "full_path": folder_path,
                    "file_name": file_name,
                    "file_id": relative_path.split('.')[0] if '.' in relative_path else relative_path,
                    "file_key": relative_path,
                    "size": obj.get('size', -1),
                    "human_readable_size": human_readable_size(obj.get('size', -1)),
                    "last_modified": obj.get('last_modified', None),
                    "etag": obj.get("etag", None),
                    "file_type": file_type,
                    "in_database": bool(file_record),  # آیا فایل در دیتابیس موجود است؟
                })

        return {"bucket_name": bucket_name, "folder_path": folder_path, "objects": detailed_objects}
    except HTTPException as e:
        raise e 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving objects from folder '{folder_path}' in bucket '{bucket_name}': {str(e)}")

@file_router.delete("/objects/{bucket_name}/{folder_path:path}/{current_file_id}", tags=["objects"])
def delete_object(bucket_name: str, folder_path: str, current_file_id: str, user_id: str, db: Session = Depends(get_db)):
    """
    Delete an object from a specific path in MinIO and the database (only if the creator user_id matches).
    """    
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")   
    
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
    
    if bucket_name in ignoree_list_delete_object_bucket:
        raise HTTPException(status_code=400, detail="شما مجاز به حذف هیچ فایلی از این باکت نیستید")
        
    if not does_path_exist(bucket_name, folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")
    
    try:
        existing_file = db.query(FileModel).filter(
            FileModel.bucket_name == bucket_name and  
            FileModel.id == current_file_id and 
            FileModel.folder_path == folder_path
        ).first()
        if not existing_file:
             raise HTTPException(status_code=404, detail="Object not found in database")
        
        # Combine folder path and object name to get full object key
        full_object_key = f"{folder_path}/{existing_file.file_key}" if folder_path else existing_file.file_key

        # بررسی تطابق user_id
        if existing_file.user_id != user_id:
            raise HTTPException(status_code=403, detail="Permission denied: You can only delete your own objects")

        # حذف آبجکت از MinIO
        try:
            minio_client.remove_object(bucket_name, full_object_key)
        except S3Error as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove object from MinIO: {str(e)}")

        # حذف رکورد از دیتابیس
        db.delete(existing_file)
        db.commit()

        return {"message": "Object deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting object: {str(e)}")



@file_router.get("/generate/minio-url/{bucket_name}/{folder_path:path}/{current_file_id}", tags=["generate url"])
def generate_presigned_url(bucket_name: str, folder_path: str, current_file_id: str, expiry_seconds: int = 12, db: Session = Depends(get_db)):
    """
    تولید لینک موقت (Presigned URL) برای دانلود فایل از مسیر مشخص.
    """
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")   
    
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
 
    if not does_path_exist(bucket_name, folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")
    
    try:
        # محاسبه زمان انقضا به ثانیه
        expiry_seconds = timedelta(seconds=expiry_seconds)  # تبدیل به عدد صحیح برای ثانیه

        existing_file = db.query(FileModel).filter(
            FileModel.bucket_name == bucket_name and  
            FileModel.id == current_file_id and 
            FileModel.folder_path == folder_path
        ).first()
        
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # Combine folder path and object name to get full object key
        full_object_key = f"{folder_path}/{existing_file.file_key}" if folder_path else existing_file.file_key

        # تولید لینک موقت
        presigned_url = minio_client.presigned_get_object(bucket_name, full_object_key, expires=expiry_seconds)

        return {
            "message": "Presigned URL generated successfully",
            "bucket_name": bucket_name,
            "folder_path": folder_path,
            "file_key": existing_file.file_key,
            "presigned_url": presigned_url,
            "expires_in": expiry_seconds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")

@file_router.get("/generate/api-url/{bucket_name}/{folder_path:path}/{current_file_id}", tags=["generate url"])
async def generate_presigned_url_with_redis(
    bucket_name: str, folder_path: str, current_file_id: str, expiry_seconds: int = 12, db: Session = Depends(get_db), request: Request = None
):
    """
    تولید لینک موقت (Presigned URL) برای دانلود فایل از مسیر مشخص از طریق API با استفاده از Redis.
    """
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")   
    
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
 
    if not does_path_exist(bucket_name, folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")
    
    try:
        # دریافت اطلاعات فایل از دیتابیس
        existing_file = db.query(FileModel).filter(            
            FileModel.bucket_name == bucket_name and  
            FileModel.id == current_file_id and 
            FileModel.folder_path == folder_path
        ).first()
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # ایجاد شناسه یکتا برای نشست دانلود
        session_id = str(uuid4())

        # ذخیره اطلاعات در Redis
        session_data = {
            "current_file_id": current_file_id,
            "file_key": existing_file.file_key,
            "bucket_name": bucket_name,
            "folder_path": folder_path,
            "version_id": existing_file.version_id
        }
        session_data_encoded = json.dumps(session_data, ensure_ascii=False).encode("utf-8")
        await setex(session_id, expiry_seconds, session_data_encoded)

        # لینک API با session_id
        api_presigned_url = f"{request.base_url}files/download/api-url/{session_id}"

        return {
            "message": "Presigned API URL generated successfully",
            "bucket_name": bucket_name,
            "folder_path": folder_path,
            "file_key": existing_file.file_key,
            "api_presigned_url": api_presigned_url,
            "expires_in": expiry_seconds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned API URL: {str(e)}")

    
    

@file_router.get("/download/base64/{bucket_name}/{folder_path:path}/{current_file_id}", tags=["download"])
async def download_file_as_base64(
    bucket_name: str,
    folder_path: str,
    current_file_id: str,
    version_id: str = None,
    width: int = None,
    height: int = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    دانلود فایل از MinIO و بازگرداندن آن به فرمت Base64 از مسیر مشخص.
    """
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")   
    
    if not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
 
    if not does_path_exist(bucket_name, folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")
    
    try:
        # ثبت لاگ درخواست
        log_request(
            db=db,
            file_id=current_file_id,
            ip_address=request.headers.get("x-forwarded-for", "127.0.0.1"),
            user_agent=request.headers.get("user-agent"),
            project_name=request.headers.get("project-name"),
        )
    except Exception as e:
        logger.warning(e)

    try:
        # دریافت اطلاعات فایل از دیتابیس
        existing_file = db.query(FileModel).filter(            
            FileModel.bucket_name == bucket_name and  
            FileModel.id == current_file_id and 
            FileModel.folder_path == folder_path
        ).first()
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")


        # Combine folder path and object name to get full object key
        full_object_key = f"{folder_path}/{existing_file.file_key}" if folder_path else existing_file.file_key

        # دریافت فایل از MinIO
        try:
            if version_id:
                response = minio_client.get_object(bucket_name, full_object_key, version_id=version_id)
            else:
                response = minio_client.get_object(bucket_name, full_object_key)
        except S3Error as e:
            logger.error(f"MinIO error: {e.code} - {e.message}")
            raise HTTPException(status_code=404, detail=f"MinIO error: {e.message}")

        # اگر فایل یک تصویر باشد، تغییر اندازه انجام شود
        if existing_file.file_type.startswith("image/") and (width or height):
            try:
                img = Image.open(BytesIO(response.read()))
                original_width, original_height = img.size

                # محاسبه ابعاد جدید
                if width and height:
                    img = img.resize((width, height))
                elif width:
                    new_height = int((width / original_width) * original_height)
                    img = img.resize((width, new_height))
                elif height:
                    new_width = int((height / original_height) * original_width)
                    img = img.resize((new_width, height))

                # ذخیره تصویر تغییر یافته در حافظه
                img_io = BytesIO()                
                img.save(img_io, format=existing_file.file_extension)
                img_io.seek(0)

                # تبدیل تصویر تغییر یافته به Base64
                base64_encoded_file = base64.b64encode(img_io.read()).decode("utf-8")
            except Exception as e:
                logger.error(f"Error resizing image: {e}")
                raise HTTPException(status_code=400, detail="Error resizing image")
        else:
            # اگر تصویر نیست یا ابعاد داده نشده‌اند، به صورت معمولی به Base64 تبدیل شود
            base64_encoded_file = base64.b64encode(response.read()).decode("utf-8")

        # افزایش شمارش دانلود
        existing_file.download_count += 1
        db.commit()

        # بازگرداندن فایل به صورت Base64 همراه با اطلاعات
        return {
            "message": "File downloaded and converted to Base64 successfully",
            "file_id": str(existing_file.id),
            "file_name": existing_file.file_name,
            "file_size": existing_file.file_size,
            "file_type": existing_file.file_type,
            "file_extension": existing_file.file_extension,
            "bucket_name": bucket_name,
            "folder_path": folder_path,
            "base64_data": f"data:{existing_file.file_type};base64,{base64_encoded_file}"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# @file_router.get("/download/public-url/{bucket_name}/{folder_path:path}/{current_file_id}", tags=["download"])
@file_router.get("/download/public-url/{current_file_id}", tags=["download"])
async def download_file_through_api(
    current_file_id: str,
    bucket_name: str = None,
    folder_path: str = None,
    version_id: str = None,
    width: int = None,
    height: int = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    دانلود فایل از MinIO به صورت واسطه (API به MinIO) از مسیر مشخص.
    """
    logger.warning(1)
    folder_path = convert_folder_path_to_validate_path(folder_path)
    if not folder_path_validat(folder_path) and folder_path != "":
        raise HTTPException(status_code=404, detail=f"folder path is not valid")  
    logger.warning(2)
     
    if folder_path == 'root':
        folder_path = ''
    logger.warning(3)
    
    try:
        # ثبت لاگ درخواست
        log_request(
            db=db,
            file_id=current_file_id,
            ip_address=request.headers.get("x-forwarded-for", "127.0.0.1"),
            user_agent=request.headers.get("user-agent"),
            project_name=request.headers.get("project-name"),
        )
    except Exception as e:
        logger.warning(e)

    try:
        # دریافت اطلاعات فایل از دیتابیس
        existing_file = db.query(FileModel).filter(      
            FileModel.id == current_file_id      
        ).first()
        
        if not minio_client.bucket_exists(existing_file.bucket_name):
            raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")
        logger.warning(4)
    
        if not does_path_exist(existing_file.bucket_name, existing_file.folder_path) and existing_file.folder_path != "":
            raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' have not exist this path '{folder_path}'")
        logger.warning(5)

        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # Combine folder path and object name to get full object key
        full_object_key = f"{existing_file.folder_path}/{existing_file.file_key}" if existing_file.folder_path else existing_file.file_key

        # دریافت فایل از MinIO
        try:
            if version_id:
                response = minio_client.get_object(existing_file.bucket_name, full_object_key, version_id=version_id)
            else:
                response = minio_client.get_object(existing_file.bucket_name, full_object_key)
        except S3Error as e:
            logger.error(f"MinIO error: {e.code} - {e.message}")
            raise HTTPException(status_code=404, detail=f"MinIO error: {e.message}")

        # افزایش شمارش دانلود
        existing_file.download_count += 1
        db.commit()

        # اگر فایل یک تصویر باشد و ابعاد داده شده باشد، تغییر اندازه انجام شود
        if existing_file.file_type.startswith("image/") and (width or height):
            try:
                img = Image.open(BytesIO(response.read()))
                original_width, original_height = img.size

                # محاسبه ابعاد جدید
                if width and height:
                    img = img.resize((width, height))
                elif width:
                    new_height = int((width / original_width) * original_height)
                    img = img.resize((width, new_height))
                elif height:
                    new_width = int((height / original_height) * original_width)
                    img = img.resize((new_width, height))

                # ذخیره تصویر تغییر یافته در حافظه
                img_io = BytesIO()                
                img.save(img_io, format=existing_file.file_extension)
                img_io.seek(0)

                # بازگرداندن تصویر تغییر یافته به صورت استریم
                return StreamingResponse(
                        stream_buffered(img_io),  # ارسال داده‌ها به صورت چانک
                        media_type=f"image/{existing_file.file_extension}",
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(existing_file.file_name)}"
                        },
                    )
            except Exception as e:
                logger.error(f"Error resizing image: {e}")
                raise HTTPException(status_code=400, detail="Error resizing image")
        else:      
            # اگر تصویر نیست یا ابعاد داده نشده‌اند، فایل اصلی بازگردانده شود
            return StreamingResponse(
                stream_minio_object(response),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(existing_file.file_name)}"
                },
            )
    except HTTPException as e:
        raise e  # انتقال خطای HTTPException به پاسخ کلاینت
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@file_router.get("/download/api-url/{session_id}", tags=["download"])
async def download_file_with_redis(
    session_id: str,
    width: int = None,
    height: int = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    اعتبارسنجی شناسه نشست و دانلود فایل از MinIO.
    """
    try:       
        # بازیابی داده از Redis
        session_data_encoded = await get(session_id)
        logger.info(f"Raw session data from Redis: {session_data_encoded}")

        # بررسی اینکه آیا داده دریافت شده است
        if not session_data_encoded:
            raise HTTPException(status_code=404, detail="Session not found in Redis")

        # رمزگشایی داده در صورت نیاز
        try:
            # رمزگشایی اگر داده به صورت بایت باشد
            if isinstance(session_data_encoded, bytes):
                session_data_json = session_data_encoded.decode("utf-8")
                logger.info(f"Decoded session data as JSON string: {session_data_json}")
            elif isinstance(session_data_encoded, str):
                session_data_json = session_data_encoded.strip()[2:-1]
                logger.info(f"Session data is already a JSON string: {session_data_json}")
            else:
                raise HTTPException(status_code=500, detail="Unexpected data type from Redis")
        except UnicodeDecodeError as e:
            logger.error(f"Unicode decoding error: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to decode session data")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding error: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to parse session data as JSON")
        
        # تبدیل رشته JSON به دیکشنری
        try:
            session_data = json.loads(session_data_json) 
            # ثبت لاگ درخواست
            log_request(
                db=db,
                file_id=session_data['current_file_id'],
                ip_address=request.headers.get("x-forwarded-for", "127.0.0.1"),
                user_agent=request.headers.get("user-agent"),
                project_name=request.headers.get("project-name"),  # فرض می‌کنیم پروژه را در هدر درخواست ارسال می‌کنید
            )
        except json.JSONDecodeError:       
            logger.error("Failed to decode Redis data")
            raise HTTPException(status_code=500, detail="Invalid data format in Redis")

        # استخراج اطلاعات از نشست
        current_file_id = session_data.get("current_file_id")
        file_key = session_data.get("file_key")
        version_id = session_data.get("version_id", None)
        bucket_name = session_data.get("bucket_name")

        if not current_file_id or not file_key or not bucket_name:
            raise HTTPException(status_code=400, detail="Invalid session data")

        # بررسی وجود فایل در دیتابیس
        existing_file = db.query(FileModel).filter(FileModel.id == current_file_id).first()
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # دریافت فایل از MinIO
        try:
            if version_id:
                response = minio_client.get_object(bucket_name, full_object_key, version_id=version_id)
            else:
                response = minio_client.get_object(bucket_name, full_object_key)
        except S3Error as e:
            logger.error(f"MinIO error: {e.code} - {e.message}")
            raise HTTPException(status_code=404, detail=f"MinIO error: {e.message}")
        
        # افزایش شمارش دانلود
        existing_file.download_count += 1
        db.commit()

        # اگر فایل تصویر است و ابعاد مشخص شده‌اند، تغییر اندازه انجام شود
        if existing_file.file_type.startswith("image/") and (width or height):
            try:                               
                img = Image.open(BytesIO(response.read()))
                original_width, original_height = img.size
                
                # محاسبه ابعاد جدید
                if width and height:
                    img = img.resize((width, height))
                elif width:
                    new_height = int((width / original_width) * original_height)
                    img = img.resize((width, new_height))
                elif height:
                    new_width = int((height / original_height) * original_width)
                    img = img.resize((new_width, height))

                # ذخیره تصویر تغییر یافته در حافظه
                img_io = BytesIO()
                img.save(img_io, format=existing_file.file_extension)
                img_io.seek(0)

                # بازگرداندن تصویر تغییر یافته به صورت استریم
                return StreamingResponse(
                    stream_buffered(img_io),  # ارسال داده‌ها به صورت چانک
                    media_type=f"image/{existing_file.file_extension}",
                    headers={
                        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(existing_file.file_name)}"
                    },
                )
            except Exception as e:
                logger.error(f"Error resizing image: {e}")
                raise HTTPException(status_code=400, detail="Error resizing image")

        # بازگرداندن فایل اصلی اگر تصویر نیست یا ابعاد مشخص نشده‌اند
        return StreamingResponse(
            stream_minio_object(response),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(existing_file.file_name)}"
            },
        )
    except HTTPException as e:
        raise e  # انتقال خطای HTTPException به پاسخ کلاینت
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@file_router.post("/download/zip-files", tags=["download"], summary="Zip files by IDs")
async def zip_files_endpoint(
    file_ids: List[UUID],
    bucket_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Validate bucket if provided
    if bucket_name and not minio_client.bucket_exists(bucket_name):
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")

    # Fetch DB records, applying bucket filter
    files = get_files(db, file_ids, bucket_name)
    if not files:
        raise HTTPException(status_code=404, detail="No files found matching criteria")

    # Build ZIP in memory
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w") as zf:
        for f in files:
            full_key = f"{f.folder_path}/{f.file_key}" if hasattr(f, 'folder_path') and f.folder_path else f.file_key
            try:
                response = minio_client.get_object(f.bucket_name, full_key)
                data = response.read()
                zf.writestr(full_key, data)
            except Exception as e:
                # Log and continue
                print(f"[zip] failed to fetch {full_key}: {e}")
                continue

    # Return ZIP via Response
    zip_buffer.seek(0)
    content = zip_buffer.getvalue()
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="files.zip"'}
    )

    
@file_router.get("/logs/{file_id}", tags=["logs"])
def get_file_logs(file_id: str, db: Session = Depends(get_db)):
    """
    دریافت لاگ درخواست‌های یک فایل.
    """
    logs = db.query(FileRequestLog).filter(FileRequestLog.file_id == file_id).all()
    return {"file_id": file_id, "logs": [log.__dict__ for log in logs]}
