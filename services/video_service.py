"""
Video management service for the Telegram bot
Handles video file operations, caching, and database management
"""

import os
import logging
from typing import List, Dict, Optional, Tuple
from database.queries import DatabaseQueries
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class VideoService:
    """Service for managing video files and their database records"""
    
    def __init__(self, videos_directory: str = None):
        self.videos_directory = videos_directory or os.path.join(
            os.getcwd(), 'database', 'data', 'videos'
        )
        self._ensure_videos_directory()
    
    def _ensure_videos_directory(self):
        """Ensure the videos directory exists"""
        if not os.path.exists(self.videos_directory):
            os.makedirs(self.videos_directory, exist_ok=True)
            logger.info(f"Created videos directory: {self.videos_directory}")
    
    def scan_and_sync_videos(self) -> Tuple[int, int]:
        """
        Scan the videos directory and sync with database
        Returns: (new_videos_added, total_videos)
        """
        if not os.path.exists(self.videos_directory):
            logger.warning(f"Videos directory not found: {self.videos_directory}")
            return 0, 0
        
        # Get existing videos from database
        existing_videos = DatabaseQueries.get_all_videos()
        existing_filenames = {video['filename'] for video in existing_videos}
        
        # Scan directory for video files
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'}
        video_files = []
        
        for filename in os.listdir(self.videos_directory):
            if any(filename.lower().endswith(ext) for ext in video_extensions):
                if filename not in existing_filenames:
                    video_files.append(filename)
        
        # Add new videos to database
        new_videos_added = 0
        for filename in video_files:
            file_path = os.path.join(self.videos_directory, filename)
            file_size = os.path.getsize(file_path)
            
            # Create display name from filename (remove extension and clean up)
            display_name = os.path.splitext(filename)[0]
            display_name = display_name.replace('_', ' ').replace('-', ' ').title()
            
            video_id = DatabaseQueries.add_video(
                filename=filename,
                display_name=display_name,
                file_path=file_path,
                file_size=file_size
            )
            
            if video_id:
                new_videos_added += 1
                logger.info(f"Added new video to database: {filename} (ID: {video_id})")
            else:
                logger.error(f"Failed to add video to database: {filename}")
        
        total_videos = len(existing_videos) + new_videos_added
        logger.info(f"Video sync complete: {new_videos_added} new videos added, {total_videos} total")
        
        return new_videos_added, total_videos
    
    # ----------------- Admin Upload Helpers -----------------
    async def save_uploaded_video(self, file_obj, original_file_name: str | None = None) -> int | None:
        """Save an uploaded Telegram file locally & add DB record. Returns new video_id."""
        try:
            # Determine filename
            safe_name = original_file_name or f"video_{file_obj.file_unique_id}.mp4"
            # Ensure unique filename
            dst_path = os.path.join(self.videos_directory, safe_name)
            counter = 1
            base, ext = os.path.splitext(dst_path)
            while os.path.exists(dst_path):
                dst_path = f"{base}_{counter}{ext}"
                counter += 1

            # Download to disk
            await file_obj.download_to_drive(dst_path)

            file_size = os.path.getsize(dst_path)
            display_name = os.path.splitext(os.path.basename(dst_path))[0].replace('_', ' ').title()

            video_id = DatabaseQueries.add_video(
                filename=os.path.basename(dst_path),
                display_name=display_name,
                file_path=dst_path,
                file_size=file_size,
            )
            return video_id
        except Exception as exc:
            logger.error("Failed to save uploaded video: %s", exc)
            return None
    
    def set_video_caption(self, video_id: int, caption: str) -> bool:
        """Update the display_name (caption) of a video."""
        try:
            from database.models import Database
            db = Database()
            if not db.connect():
                return False
            
            cursor = db.conn.cursor()
            cursor.execute(
                "UPDATE videos SET display_name = ? WHERE id = ?",
                (caption, video_id)
            )
            db.conn.commit()
            db.close()
            logger.info(f"Updated caption for video {video_id}: {caption}")
            return True
        except Exception as exc:
            logger.error(f"Failed to set video caption: {exc}")
            return False

    # ----------------- Retrieval Helpers -----------------
    def get_available_videos(self) -> List[Dict]:
        """Get all available videos from database"""
        return DatabaseQueries.get_all_videos()
    
    def get_video_by_id(self, video_id: int) -> Optional[Dict]:
        """Get a specific video by ID"""
        videos = self.get_available_videos()
        for video in videos:
            if video['id'] == video_id:
                return video
        return None
    
    async def send_video_to_user(self, bot: Bot, user_id: int, video: Dict, 
                               caption: str = None) -> Optional[str]:
        """
        Send a video to a user, using cached file_id if available
        Returns the file_id for caching purposes
        """
        try:
            # Try to use cached Telegram file_id first
            if video.get('telegram_file_id'):
                try:
                    message = await bot.send_video(
                        chat_id=user_id,
                        video=video['telegram_file_id'],
                        caption=caption or video['display_name']
                    )
                    return video['telegram_file_id']
                except TelegramError as e:
                    logger.warning(f"Failed to send cached video {video['id']}: {e}")
                    # Fall back to file upload
            
            # Upload video file
            file_path = video['file_path']
            if not os.path.exists(file_path):
                logger.error(f"Video file not found: {file_path}")
                return None
            
            with open(file_path, 'rb') as video_file:
                message = await bot.send_video(
                    chat_id=user_id,
                    video=video_file,
                    caption=caption or video['display_name']
                )
            
            # Cache the file_id for future use
            file_id = message.video.file_id
            DatabaseQueries.update_video_telegram_file_id(video['id'], file_id)
            
            logger.info(f"Successfully sent video {video['id']} to user {user_id}")
            return file_id
            
        except Exception as e:
            logger.error(f"Error sending video {video['id']} to user {user_id}: {e}")
            return None
    
    async def send_plan_videos(self, bot: Bot, user_id: int, plan_id: int) -> bool:
        """
        Send all videos associated with a plan to a user
        Returns True if all videos were sent successfully
        """
        plan_videos = DatabaseQueries.get_plan_videos(plan_id)
        if not plan_videos:
            logger.warning(f"No videos found for plan {plan_id}")
            return False
        
        success_count = 0
        total_videos = len(plan_videos)
        
        for i, video in enumerate(plan_videos, 1):
            # Use custom caption if available, otherwise use display_name only
            if video.get('custom_caption'):
                caption = video['custom_caption']
            else:
                caption = video['display_name']
            
            file_id = await self.send_video_to_user(bot, user_id, video, caption)
            if file_id:
                success_count += 1
            else:
                logger.error(f"Failed to send video {video['id']} to user {user_id}")
        
        logger.info(f"Sent {success_count}/{total_videos} videos from plan {plan_id} to user {user_id}")
        return success_count == total_videos
    
    def get_plan_videos_list(self, plan_id: int) -> List[Dict]:
        """Get list of videos associated with a plan"""
        return DatabaseQueries.get_plan_videos(plan_id)
    
    def add_video_to_plan(self, plan_id: int, video_id: int, display_order: int = 0, custom_caption: str | None = None) -> bool:
        """Add a video to a plan.
        Currently `custom_caption` is ignored (DB schema not yet supporting), but accepted to keep API compatible.
        """
        return DatabaseQueries.add_video_to_plan(plan_id, video_id, display_order, custom_caption)
    
    def remove_video_from_plan(self, plan_id: int, video_id: int) -> bool:
        """Remove a video from a plan"""
        return DatabaseQueries.remove_video_from_plan(plan_id, video_id)
    
    def get_video_file_info(self, video_id: int) -> Optional[Dict]:
        """Get file information for a video"""
        video = self.get_video_by_id(video_id)
        if not video:
            return None
        
        file_path = video['file_path']
        if not os.path.exists(file_path):
            return None
        
        return {
            'id': video['id'],
            'filename': video['filename'],
            'display_name': video['display_name'],
            'file_path': file_path,
            'file_size': video['file_size'],
            'exists': True,
            'telegram_file_id': video.get('telegram_file_id')
        }
    
    def clear_plan_videos(self, plan_id: int) -> bool:
        """Remove all video associations for a given plan."""
        plan_videos = DatabaseQueries.get_plan_videos(plan_id)
        success = True
        for video in plan_videos:
            ok = DatabaseQueries.remove_video_from_plan(plan_id, video['id'])
            if not ok:
                success = False
        if success:
            logger.info(f"Cleared {len(plan_videos)} videos from plan {plan_id}")
        else:
            logger.warning(f"Failed to clear some videos from plan {plan_id}")
        return success

    def list_all_videos(self, page: int = 1, page_size: int = 8) -> Tuple[List[Dict], int]:
        """Return paginated list of available videos.

        Args:
            page (int): 1-based page number.
            page_size (int): number of items per page.

        Returns:
            (page_items, total_count)
        """
        all_videos = DatabaseQueries.get_all_videos()
        total = len(all_videos)
        if page < 1:
            page = 1
        start = (page - 1) * page_size
        end = start + page_size
        return all_videos[start:end], total

    def get_video_path(self, filename: str) -> str:
        """Get the full path to a video file."""
        return os.path.join(self.videos_directory, filename)

# Global instance
video_service = VideoService()
