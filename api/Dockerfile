# Dockerfile

# استفاده از تصویر رسمی پایتون
FROM python:3.11.4

# تنظیم متغیر محیطی برای جلوگیری از ایجاد فایل‌های pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ایجاد پوشه کاری
WORKDIR /app

# کپی کردن فایل وابستگی‌ها
COPY requirements.txt .

# تنظیم pip با استفاده از pip.conf
COPY ./pip.conf /etc/pip.conf

# نصب pip و وابستگی‌ها
RUN pip install --upgrade pip

# نصب وابستگی‌ها
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن کد پروژه
COPY . .

# ایجاد پوشه لاگ‌ها
RUN mkdir -p logs

# Expose the default port for FastAPI
EXPOSE 8000

# Command to run the application 
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120",  "--reload"]
