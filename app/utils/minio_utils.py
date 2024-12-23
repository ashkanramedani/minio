from minio import Minio
from minio.error import S3Error
from dbs import minio_client

def upload_file_to_minio(bucket_name: str, file_name: str, file_content):
    try:
        # اطمینان از وجود باکت
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        # آپلود فایل و دریافت نتیجه
        result = minio_client.put_object(
            bucket_name,
            file_name,
            file_content,
            length=-1,  # Auto-detect length
            part_size=10 * 1024 * 1024  # 10 MB parts
        )

        # بازگرداندن نتیجه آپلود
        return result
    except S3Error as e:
        raise Exception(f"Failed to upload file: {str(e)}")
    
def generate_presigned_url(bucket_name: str, file_name: str):
    try:
        # Generate a presigned URL
        return minio_client.presigned_get_object(bucket_name, file_name)
    except S3Error as e:
        raise Exception(f"Failed to generate presigned URL: {str(e)}")
    
def list_buckets():
    try:
        # دریافت لیست باکت‌ها
        buckets = minio_client.list_buckets()
        bucket_list = []
        for bucket in buckets:
            is_public = is_bucket_public(bucket.name)
            bucket_list.append({
                "name": bucket.name,
                "creation_date": bucket.creation_date,
                "public": is_public
            })
        return bucket_list
    except Exception as e:
        raise Exception(f"Failed to list buckets: {str(e)}")
    
def is_bucket_public(bucket_name: str) -> bool:
    """
    بررسی می‌کند که آیا باکت عمومی است یا خیر.
    """
    try:
        # دریافت سیاست باکت
        policy = minio_client.get_bucket_policy(bucket_name)
        # اگر سیاست باکت شامل "allow" برای "s3:GetObject" باشد، عمومی است
        if "s3:GetObject" in policy:
            return True
        return False
    except Exception:
        # اگر سیاست تعریف نشده باشد یا خطایی رخ دهد، فرض می‌شود باکت خصوصی است
        return False
    
def list_objects_in_bucket(bucket_name: str):
    """
    لیست اشیاء موجود در یک باکت را برمی‌گرداند.
    """
    try:
        # دریافت لیست اشیاء از MinIO
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
    تبدیل اندازه فایل به فرمت قابل خواندن برای انسان (KB, MB, GB).
    """
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / 1024 ** 2:.2f} MB"
    else:
        return f"{size_in_bytes / 1024 ** 3:.2f} GB"