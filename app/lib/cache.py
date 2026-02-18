"""
Redis caching utility for API responses and database queries
"""
import json
import hashlib
from typing import Optional, Any
from functools import wraps
from fastapi import Request
import redis
from app.config import settings

get_settings = settings()


def _make_redis_client():
    """Create Redis client from REDIS_URL or REDIS_HOST/PORT/DB."""
    if get_settings.REDIS_URL:
        # Use full URL (supports redis:// and rediss:// for TLS)
        return redis.from_url(
            get_settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return redis.Redis(
        host=get_settings.REDIS_HOST,
        port=get_settings.REDIS_PORT,
        db=get_settings.REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


# Initialize Redis client (with fallback to in-memory cache if Redis unavailable)
try:
    redis_client = _make_redis_client()
    redis_client.ping()
    REDIS_AVAILABLE = True
except Exception as e:
    REDIS_AVAILABLE = False
    _memory_cache = {}
    print(f"Redis not available, using in-memory cache: {e}")


def get_cache_key(request: Request, prefix: str = "api", user_id: str = None) -> str:
    """Generate cache key from request"""
    query_string = str(request.url.query) if request.url.query else ""
    key_data = f"{request.method}:{request.url.path}:{query_string}"
    if user_id:
        key_data += f":{user_id}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def get(key: str) -> Optional[Any]:
    """Get value from cache"""
    if REDIS_AVAILABLE:
        try:
            value = redis_client.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None
    else:
        return _memory_cache.get(key)


def set(key: str, value: Any, ttl: int = 300) -> bool:
    """Set value in cache with TTL"""
    if REDIS_AVAILABLE:
        try:
            redis_client.setex(key, ttl, json.dumps(value))
            return True
        except Exception:
            return False
    else:
        _memory_cache[key] = value
        return True


def delete(key: str) -> bool:
    """Delete key from cache"""
    if REDIS_AVAILABLE:
        try:
            redis_client.delete(key)
            return True
        except Exception:
            return False
    else:
        _memory_cache.pop(key, None)
        return True


def cache_response(ttl: int = 300, key_prefix: str = "api"):
    """Decorator to cache API responses"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Try to get request from kwargs
            request = kwargs.get('request') or (args[0] if args and hasattr(args[0], 'url') else None)
            
            if not request:
                return await func(*args, **kwargs)
            
            cache_key = get_cache_key(request, key_prefix)
            cached = get(cache_key)
            
            if cached:
                return cached
            
            result = await func(*args, **kwargs)
            set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator


def invalidate_pattern(pattern: str):
    """Invalidate cache keys matching pattern"""
    if REDIS_AVAILABLE:
        try:
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
        except Exception:
            pass
    else:
        # For in-memory cache, clear all (simple implementation)
        _memory_cache.clear()
