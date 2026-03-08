

# app/redis_client.py
import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

# Initialize the Redis connection
# decode_responses=True ensures we get clean strings back, not raw bytes
if REDIS_URL:
    try:
        redis_db = redis.from_url(REDIS_URL, decode_responses=True)
        redis_db.ping() # Test the connection
        print("🟢 Redis Cache Connected Successfully!")
    except Exception as e:
        print(f"🔴 Redis Connection Failed: {e}")
        redis_db = None
else:
    print("⚠️ WARNING: REDIS_URL missing. Caching is disabled.")
    redis_db = None