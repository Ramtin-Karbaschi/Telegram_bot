import time
from typing import Any, Optional, Dict

class CacheManager:
    """مدیریت کش برای کاهش عملیات‌های تکراری دیتابیس"""
    
    def __init__(self, ttl: int = 300):  # 5 minutes default TTL
        self.cache: Dict[str, tuple[Any, float]] = {}
        self.ttl = ttl
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار از کش"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """ذخیره مقدار در کش"""
        ttl = ttl or self.ttl
        self.cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """پاک‌سازی کش"""
        self.cache.clear()

# Global cache instance  
cache = CacheManager()
