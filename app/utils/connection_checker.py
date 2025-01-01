from dbs import engine
from dbs import minio_client
from sqlalchemy.sql import text

def check_database_connection():
    try:
        # اتصال به دیتابیس و اجرای کوئری تست
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            if result != 1:
                raise Exception("Unexpected result from database")
        print("PostgreSQL connection successful.")
    except Exception as e:
        raise Exception(f"Failed to connect to PostgreSQL: {str(e)}")
    
def check_minio_connection():
    try:
        # فهرست باکت‌های موجود به‌عنوان یک عملیات تست
        minio_client.list_buckets()
        print("MinIO connection successful.")
    except Exception as e:
        raise Exception(f"Failed to connect to MinIO: {str(e)}")