# app/routes/file_routes.py
from fastapi import APIRouter, UploadFile, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from dbs import get_db, minio_client
from utils import (
    upload_file_to_minio,
    list_buckets,
    list_objects_in_bucket,
    human_readable_size,
    get,
    setex,
)
from models import uuid4, FileModel, FileRequestLog
from services import log_request
from datetime import timedelta
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from minio.versioningconfig import VersioningConfig
from libs import logger
import base64
import json
from mimetypes import guess_type
from PIL import Image
from io import BytesIO

file_router = APIRouter(prefix="/files")

@file_router.post("/upload", tags=["files"])
def upload_file(
    bucket_name: str,
    file: UploadFile,
    request: Request,
    format: str = None,
    width: int = None,
    height: int = None,
    current_file_id: str = None,
    user_id: str = "1",
    db: Session = Depends(get_db)
):
    """
    آپلود فایل به MinIO و ذخیره اطلاعات در دیتابیس.
    """
    try:
        logger.info("Starting file upload process")
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else None

        if not file_extension:
            logger.warning("File extension is missing")

        # شناسایی نوع فایل
        mime_type, _ = guess_type(file.filename)
        file_type = mime_type.split('/')[0] if mime_type else None

        if current_file_id:
            existing_file = db.query(FileModel).filter(FileModel.id == current_file_id).first()
            if not existing_file:
                logger.error("File not found in database")
                raise HTTPException(status_code=404, detail="File not found")

            file_key = str(existing_file.id) + (f".{file_extension}" if file_extension else "")
        else:
            new_file = FileModel(
                file_name=file.filename,
                file_key="",
                file_extension=file_extension,
                bucket_name=bucket_name,
                file_type=file.content_type,
                file_size=0,
                public_url="",
                user_id=user_id
            )
            db.add(new_file)
            db.commit()
            db.refresh(new_file)
            file_key = str(new_file.id) + (f".{file_extension}" if file_extension else "")

        try:
            logger.info(f"Uploading file to MinIO: {file_key}")

            # اگر کاربر فرمت یا اندازه مشخص کرده باشد
            if format or width or height:
                if file_type == "image":
                    logger.info("Processing image for format/resize")
                    try:
                        img = Image.open(file.file)
                        if width and height:
                            logger.info(f"Resizing image to width={width}, height={height}")
                            img = img.resize((width, height))
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

            result = upload_file_to_minio(bucket_name, file_key, file.file)
            version_id = getattr(result, "version_id", None)
            if not version_id:
                logger.warning("Version ID is None. Check if versioning is enabled in the bucket.")

            file_size = file.file.seek(0, 2)
            if file_size <= 0:
                logger.error("Invalid file size detected")
                raise HTTPException(status_code=400, detail="Invalid file size")
            file.file.seek(0)

            public_url = f"{request.base_url}files/download/public-url/{bucket_name}/"
            if current_file_id: public_url += f"{current_file_id}"
            else: public_url += f"{new_file.id}"
            if version_id: public_url += f"?version_id={version_id}"

            if current_file_id:
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
    دریافت لیست باکت‌های موجود در MinIO و وضعیت عمومی یا خصوصی بودن آنها.
    """
    try:
        buckets = list_buckets()
        return buckets
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving buckets: {str(e)}")

@file_router.get("/objects/{bucket_name}", tags=["buckets"])
def get_objects_in_bucket(bucket_name: str, db: Session = Depends(get_db)):
    """
    دریافت لیست اشیاء موجود در یک باکت.
    """
    try:
        # بررسی وجود باکت
        if not minio_client.bucket_exists(bucket_name):
            raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' does not exist")

        objects = list_objects_in_bucket(bucket_name)
        detailed_objects = []

        for obj in objects:
            object_name = obj.get("object_name") or obj.get("name")
            if not object_name:
                continue  # در صورت عدم وجود نام فایل، این رکورد را نادیده بگیرید
         
            # جستجوی فایل در دیتابیس
            file_record = db.query(FileModel).filter(
                FileModel.bucket_name == bucket_name,
                FileModel.file_key == object_name
            ).first()

            if file_record:
                file_type = file_record.file_type
            else:
                file_type = "unknown"  # پیش‌فرض اگر فایل در دیتابیس یافت نشود

            detailed_objects.append({
                "object_name": object_name,
                "size": obj["size"],
                "human_readable_size": human_readable_size(obj["size"]),
                "last_modified": obj.get("last_modified", None),
                "etag": obj.get("etag", None),
                "file_type": file_type
            })

        return {"bucket_name": bucket_name, "objects": detailed_objects}
    except HTTPException as e:
        raise e  # انتقال خطای مشخص به کلاینت
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving objects from bucket '{bucket_name}': {str(e)}")

@file_router.post("/buckets/{bucket_name}", tags=["buckets"])
def create_bucket(bucket_name: str):
    """
    ایجاد یک باکت جدید در MinIO با تنظیمات پابلیک و قابلیت ورژن‌بندی.
    """
    try:
        # بررسی وجود باکت
        if minio_client.bucket_exists(bucket_name):
            raise HTTPException(status_code=400, detail=f"Bucket '{bucket_name}' already exists")

        # ایجاد باکت
        minio_client.make_bucket(bucket_name)
        logger.info(f"Bucket '{bucket_name}' created successfully")

        # تنظیم سیاست پابلیک برای باکت
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*"  # دسترسی به تمام اشیاء
                }
            ]
        }
        minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
        logger.info(f"Public policy set for bucket '{bucket_name}'")

        # فعال‌سازی ورژن‌بندی برای باکت
        versioning_config = VersioningConfig("Enabled")  # وضعیت ورژن‌بندی را به "Enabled" تنظیم کنید
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
    حذف یک باکت اگر خالی باشد.
    """
    try:
        # بررسی وجود آبجکت‌ها در دیتابیس
        db_objects_count = db.query(FileModel).filter(FileModel.bucket_name == bucket_name).count()
        if db_objects_count > 0:
            raise HTTPException(status_code=400, detail="Bucket is not empty in database")

        # بررسی وجود آبجکت‌ها در MinIO
        objects = list(minio_client.list_objects(bucket_name, recursive=True))
        if objects:
            raise HTTPException(status_code=400, detail="Bucket is not empty in MinIO")

        # حذف باکت از MinIO
        try:
            minio_client.remove_bucket(bucket_name)
        except S3Error as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove bucket: {str(e)}")

        return {"message": "Bucket deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting bucket: {str(e)}")


@file_router.delete("/objects/{bucket_name}/{object_name}", tags=["objects"])
def delete_object(bucket_name: str, object_name: str, user_id: str, db: Session = Depends(get_db)):
    """
    حذف یک آبجکت از MinIO و دیتابیس (فقط اگر user_id ایجادکننده تطابق داشته باشد).
    """
    try:
        # جستجوی رکورد در دیتابیس
        file_record = db.query(FileModel).filter(
            FileModel.bucket_name == bucket_name,
            FileModel.file_key== object_name
        ).first()

        if not file_record:
            raise HTTPException(status_code=404, detail="Object not found in database")

        # بررسی تطابق user_id
        if file_record.user_id != user_id:
            raise HTTPException(status_code=403, detail="Permission denied: You can only delete your own objects")

        # حذف آبجکت از MinIO
        try:
            minio_client.remove_object(bucket_name, object_name)
        except S3Error as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove object from MinIO: {str(e)}")

        # حذف رکورد از دیتابیس
        db.delete(file_record)
        db.commit()

        return {"message": "Object deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting object: {str(e)}")



@file_router.get("/generate/minio-url/{bucket_name}/{current_file_id}", tags=["generate url"])
def generate_presigned_url(bucket_name: str, current_file_id: str, expiry_seconds: int = 12, db: Session = Depends(get_db)):
    """
    تولید لینک موقت (Presigned URL) برای دانلود فایل.
    """
    try:
        # محاسبه زمان انقضا به ثانیه
        expiry_seconds = timedelta(seconds=expiry_seconds)  # تبدیل به عدد صحیح برای ثانیه
        
        existing_file = db.query(FileModel).filter(FileModel.id == current_file_id).first()
        file_key = str(current_file_id) + (f".{existing_file.file_extension}" if existing_file.file_extension else "")

        # تولید لینک موقت
        presigned_url = minio_client.presigned_get_object(bucket_name, file_key, expires=expiry_seconds)

        return {
            "message": "Presigned URL generated successfully",
            "bucket_name": bucket_name,
            "file_key": file_key,
            "presigned_url": presigned_url,
            "expires_in": expiry_seconds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")

@file_router.get("/generate/api-url/{bucket_name}/{current_file_id}", tags=["generate url"])
async def generate_presigned_url_with_redis(
    bucket_name: str, current_file_id: str, expiry_seconds: int = 3600, db: Session = Depends(get_db), request: Request = None
):
    """
    تولید لینک موقت (Presigned URL) برای دانلود فایل از طریق API با استفاده از Redis.
    """
    try:
        # دریافت اطلاعات فایل از دیتابیس
        existing_file = db.query(FileModel).filter(FileModel.id == current_file_id).first()
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # ساخت کلید فایل
        file_key = str(current_file_id) + (f".{existing_file.file_extension}" if existing_file.file_extension else "")

        # ایجاد شناسه یکتا برای نشست دانلود
        session_id = str(uuid4())

        # ذخیره اطلاعات در Redis
        session_data = {
            "current_file_id": current_file_id,
            "file_key": file_key,
            "bucket_name": bucket_name,
            "version_id": existing_file.version_id
        }
        session_data_encoded = json.dumps(session_data, ensure_ascii=False).encode("utf-8")
        await setex(session_id, expiry_seconds, session_data_encoded)

        # لینک API با session_id
        api_presigned_url = f"{request.base_url}files/download/api-url/{session_id}"

        return {
            "message": "Presigned API URL generated successfully",
            "bucket_name": bucket_name,
            "file_key": file_key,
            "api_presigned_url": api_presigned_url,
            "expires_in": expiry_seconds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned API URL: {str(e)}")
    
    

@file_router.get("/download/base64/{bucket_name}/{current_file_id}", tags=["download"])
async def download_file_as_base64(bucket_name: str, current_file_id: str, version_id: str = None, request: Request = None, db: Session = Depends(get_db)):
    """
    دانلود فایل از MinIO و بازگرداندن آن به فرمت Base64.
    """
    try:
        # ثبت لاگ درخواست
        log_request(
            db=db,
            file_id=current_file_id,
            ip_address=request.headers.get("x-forwarded-for"),
            user_agent=request.headers.get("user-agent"),
            project_name=request.headers.get("project-name"),  # فرض می‌کنیم پروژه را در هدر درخواست ارسال می‌کنید
        )

        # بررسی اینکه آیا فایل موجود است
        existing_file = db.query(FileModel).filter(
            FileModel.id == current_file_id, FileModel.bucket_name == bucket_name
        ).first()
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # افزایش شمارش دانلود
        existing_file.download_count += 1
        db.commit()

        # ساخت کلید فایل برای MinIO
        file_key = f"{existing_file.id}.{existing_file.file_extension}" if existing_file.file_extension else str(existing_file.id)

        # دریافت فایل از MinIO
        try:
            response = minio_client.get_object(bucket_name, file_key, version_id=version_id)
        except S3Error as e:
            logger.error(f"MinIO error: {e.code} - {e.message}")
            raise HTTPException(status_code=404, detail=f"MinIO error: {e.message}")

        # تبدیل فایل به Base64
        base64_encoded_file = base64.b64encode(response.read()).decode("utf-8")

        # بازگرداندن فایل به صورت Base64 همراه با اطلاعات
        return {
            "message": "File downloaded and converted to Base64 successfully",
            "file_id": str(existing_file.id),
            "file_name": existing_file.file_name,
            "file_size": existing_file.file_size,
            "file_type": existing_file.file_type,
            "file_extension": existing_file.file_extension,
            "bucket_name": bucket_name,
            "base64_data": f"data:{existing_file.file_type};base64,{base64_encoded_file}"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@file_router.get("/download/public-url/{bucket_name}/{current_file_id}", tags=["download"])
async def download_file_through_api(bucket_name: str, current_file_id: str, version_id: str = None, request: Request = None, db: Session = Depends(get_db)):
    """
    دانلود فایل از MinIO به صورت واسطه (API به MinIO).
    """
    try:
        # ثبت لاگ درخواست
        log_request(
            db=db,
            file_id=current_file_id,
            ip_address=request.headers.get("x-forwarded-for"),
            user_agent=request.headers.get("user-agent"),
            project_name=request.headers.get("project-name"),  # فرض می‌کنیم پروژه را در هدر درخواست ارسال می‌کنید
        )
        # بررسی اینکه آیا فایل موجود است
        existing_file = db.query(FileModel).filter(
            FileModel.id == current_file_id, FileModel.bucket_name == bucket_name
        ).first()
        if not existing_file:
            raise HTTPException(status_code=404, detail="File not found in database")

        # ساخت کلید فایل برای MinIO
        file_key = f"{existing_file.id}.{existing_file.file_extension}" if existing_file.file_extension else str(existing_file.id)

        # دریافت فایل از MinIO
        try:
            response = minio_client.get_object(bucket_name, file_key, version_id=version_id)
        except S3Error as e:
            logger.error(f"MinIO error: {e.code} - {e.message}")
            raise HTTPException(status_code=404, detail=f"MinIO error: {e.message}")

        # افزایش شمارش دانلود
        existing_file.download_count += 1
        db.commit()

        # بازگرداندن فایل به صورت استریم
        return StreamingResponse(response, media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename={existing_file.file_name}"
        })

    except HTTPException as e:
        raise e  # انتقال خطای HTTPException به پاسخ کلاینت
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
   
@file_router.get("/download/api-url/{session_id}", tags=["download"])
async def download_file_with_redis(session_id: str, request: Request = None, db: Session = Depends(get_db)):
    """
    اعتبارسنجی شناسه نشست و دانلود فایل از MinIO.
    """
    try:
        # ثبت لاگ درخواست
        log_request(
            db=db,
            file_id=current_file_id,
            ip_address=request.headers.get("x-forwarded-for"),
            user_agent=request.headers.get("user-agent"),
            project_name=request.headers.get("project-name"),  # فرض می‌کنیم پروژه را در هدر درخواست ارسال می‌کنید
        )
        # بازیابی داده از Redis
        session_data_encoded = await get(session_id)
        logger.info(f"Raw session data from Redis: {session_data_encoded}")

        # بررسی اینکه آیا داده دریافت شده است
        if not session_data_encoded:
            raise HTTPException(status_code=404, detail="Session not found in Redis")

        # رمزگشایی داده از باینری به رشته
        try:
            session_data_json = session_data_encoded.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=500, detail="Failed to decode session data")

        # تبدیل رشته JSON به دیکشنری
        try:
            session_data = json.loads(session_data_json)
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
            response = minio_client.get_object(bucket_name, file_key, version_id=version_id)
        except S3Error as e:
            logger.error(f"MinIO error: {e.code} - {e.message}")
            raise HTTPException(status_code=404, detail=f"MinIO error: {e.message}")
        
        # افزایش شمارش دانلود
        existing_file.download_count += 1
        db.commit()

        # بازگرداندن فایل به صورت استریم
        return StreamingResponse(response, media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename={existing_file.file_name}"
        })

    except HTTPException as e:
        raise e  # انتقال خطای HTTPException به پاسخ کلاینت
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@file_router.get("/logs/{file_id}", tags=["logs"])
def get_file_logs(file_id: str, db: Session = Depends(get_db)):
    """
    دریافت لاگ درخواست‌های یک فایل.
    """
    logs = db.query(FileRequestLog).filter(FileRequestLog.file_id == file_id).all()
    return {"file_id": file_id, "logs": [log.__dict__ for log in logs]}