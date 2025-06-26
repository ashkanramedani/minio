# app/main.py
from fastapi import FastAPI
from routes.file_routes import file_router
from utils import check_minio_connection, check_database_connection
from libs import logger
from dbs import Base, engine
from configs import settings
from fastapi.middleware.cors import CORSMiddleware

# بررسی اتصال‌ها قبل از شروع برنامه
try:
    check_minio_connection()
    check_database_connection()
except Exception as e:
    print(e)
    raise SystemExit("Failed to start the application due to connection issues.")

app = FastAPI(
    # root_path="/file",
    title=settings.API_NAME,
    version=settings.VERSION
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(file_router, prefix='/api/v1' )

@app.on_event("startup")
async def startup_event():
    logger.info("Starting application...")

    # بررسی اتصال‌ها
    try:
        check_minio_connection()
        logger.info("MinIO connection successful.")
        check_database_connection()
        logger.info("PostgreSQL connection successful.")
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        raise SystemExit("Failed to start the application due to connection issues.")

    # ساخت جداول دیتابیس در صورت عدم وجود
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")

    logger.info("Application started successfully.")
