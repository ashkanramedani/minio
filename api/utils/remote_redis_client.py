# api/utils/remote_redis_client.py
import httpx
from fastapi import HTTPException
from configs import settings

REDIS_API_BASE = settings.REDIS_API_BASE
API_KEY = settings.API_KEY
DB_INDEX = settings.REDIS_DB_INDEX

async def setex(key: str, ttl: int, value: str):
    # یک درخواست POST به /create می‌فرستیم
    data = {
        "key": key,
        "value": str(value),
        "db_index": DB_INDEX,
        "ttl": ttl
    }
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{REDIS_API_BASE}/create", json=data, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print("HTTP Status Error:", e.response.status_code, e.response.text)
        raise HTTPException(status_code=500, detail="Failed to store data in Redis")
    except Exception as e:
        print("Unexpected Error:", str(e))
        raise HTTPException(status_code=500, detail="Unexpected error occurred")

async def get(key: str):
    headers = {
        "x-api-key": API_KEY
    }
    params = {
        "key": key,
        "db_index": DB_INDEX
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{REDIS_API_BASE}/get", headers=headers, params=params)
        # فرض می‌کنیم اگر کلید وجود نداشته باشد، ممکن است چه پاسخی بدهد؟
        # احتمالا اگر وجود نداشته باشد باید handling کنید.
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        # فرض می‌کنیم پاسخ JSON است و شامل value
        result = resp.json()
        # انتظار می‌رود که result چیزی شبیه:
        # { "value": "the_value" } برگرداند
        return result.get("value")

async def delete(key: str):
    # متاسفانه شما اندپوینت حذف ندارید.
    # می‌توانید با یک مقدار بی‌اعتبار (مثلاً ttl=1) یک مقدار ست کنید تا سریع منقضی شود
    # یا از فرانت‌اند بخواهید که یک اندپوینت برای حذف اضافه کند.
    # فعلاً اینجا فقط یک راه‌حل موقت:
    await setex(key, 1, "expired")

async def update(key: str, ttl: int, value: str):
    # یک درخواست PUT به /update می‌فرستیم
    data = {
        "key": key,
        "value": str(value),
        "db_index": DB_INDEX,
        "ttl": ttl
    }
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{REDIS_API_BASE}/update", json=data, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print("HTTP Status Error:", e.response.status_code, e.response.text)
        raise HTTPException(status_code=500, detail="Failed to store data in Redis")
    except Exception as e:
        print("Unexpected Error:", str(e))
        raise HTTPException(status_code=500, detail="Unexpected error occurred")