"""
Rate limiting middleware using sliding window algorithm
"""
from collections import defaultdict
from time import time
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Tuple
import redis
from app.config import settings

get_settings = settings()

# Rate limit storage (in-memory fallback if Redis unavailable)
_rate_limit_store: Dict[str, list] = defaultdict(list)


def _make_redis_client():
    """Create Redis client from REDIS_URL or REDIS_HOST/PORT/DB."""
    if get_settings.REDIS_URL:
        return redis.from_url(
            get_settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return redis.Redis(
        host=get_settings.REDIS_HOST,
        port=get_settings.REDIS_PORT,
        db=1,  # use db=1 for rate limit when using host/port to avoid clashing with cache
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


# Initialize Redis for distributed rate limiting
try:
    redis_client = _make_redis_client()
    redis_client.ping()
    REDIS_AVAILABLE = True
except Exception as e:
    REDIS_AVAILABLE = False
    print(f"Redis not available for rate limiting, using in-memory store: {e}")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""
    
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/ml-server/health"]:
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Check rate limit
        if not self._check_rate_limit(client_id, request.url.path):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )
        
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = self._get_remaining(client_id, request.url.path)
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time()) + self.period)
        
        return response
    
    def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier"""
        # Try to get user ID from token if available
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            # In production, decode token to get user ID
            # For now, use IP + token hash
            return f"{request.client.host}:{hash(token) % 10000}"
        return request.client.host
    
    def _check_rate_limit(self, client_id: str, path: str) -> bool:
        """Check if request is within rate limit"""
        key = f"{client_id}:{path}"
        now = time()
        
        if REDIS_AVAILABLE:
            try:
                # Use Redis sorted set for sliding window
                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, now - self.period)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, self.period)
                results = pipe.execute()
                count = results[1]
                return count < self.calls
            except Exception:
                # Fallback to in-memory
                pass
        
        # In-memory rate limiting
        if key not in _rate_limit_store:
            _rate_limit_store[key] = []
        
        # Remove old entries
        _rate_limit_store[key] = [
            t for t in _rate_limit_store[key] 
            if now - t < self.period
        ]
        
        if len(_rate_limit_store[key]) >= self.calls:
            return False
        
        _rate_limit_store[key].append(now)
        return True
    
    def _get_remaining(self, client_id: str, path: str) -> int:
        """Get remaining requests"""
        key = f"{client_id}:{path}"
        now = time()
        
        if REDIS_AVAILABLE:
            try:
                count = redis_client.zcount(key, now - self.period, now)
                return max(0, self.calls - count)
            except Exception:
                pass
        
        if key not in _rate_limit_store:
            return self.calls
        
        _rate_limit_store[key] = [
            t for t in _rate_limit_store[key] 
            if now - t < self.period
        ]
        
        return max(0, self.calls - len(_rate_limit_store[key]))
