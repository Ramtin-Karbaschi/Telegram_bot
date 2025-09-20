import asyncio
import logging

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    """مدیر تسک‌های پس‌زمینه برای جلوگیری از blocking"""
    
    @staticmethod
    async def run_in_background(coro):
        """اجرای یک coroutine در پس‌زمینه بدون blocking"""
        try:
            return await coro
        except Exception as e:
            logger.error(f"Background task error: {e}")
    
    @staticmethod  
    def schedule(coro):
        """زمان‌بندی یک task برای اجرا در پس‌زمینه"""
        asyncio.create_task(BackgroundTaskManager.run_in_background(coro))

# Global instance
background_tasks = BackgroundTaskManager()
