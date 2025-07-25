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
    async def save_uploaded_video(self, file_obj, original_file_name: str | None = None, telegram_file_id: str | None = None, origin_chat_id: int | None = None, origin_message_id: int | None = None) -> int | None:
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
                telegram_file_id=telegram_file_id,
                origin_chat_id=origin_chat_id,
                origin_message_id=origin_message_id,
            )
            
            if video_id and telegram_file_id:
                logger.info(f"Saved video {video_id} with Telegram file_id")
            
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
            # Validate video data
            if not video or not video.get('id'):
                logger.error(f"Invalid video data: {video}")
                return None
            
            video_id = video['id']
            file_path = video.get('file_path', '').strip()
            
            # Try to use cached Telegram file_id first
            if video.get('telegram_file_id'):
                try:
                    message = await bot.send_video(
                        chat_id=user_id,
                        video=video['telegram_file_id'],
                        caption=caption or video.get('display_name', f'Video {video_id}'),
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30
                    )
                    logger.info(f"Successfully sent cached video {video_id} to user {user_id}")
                    return video['telegram_file_id']
                except TelegramError as e:
                    logger.warning(f"Failed to send cached video {video_id}: {e}")
                    # Decide whether to clear cached telegram_file_id
                    error_msg = str(e).lower()
                    if any(permanent_error in error_msg for permanent_error in [
                        'file not found', 'file_id expired', 'file deleted', 
                        'bad file_id', 'invalid file_id',
                        'file_reference expired', 'file reference expired'
                    ]):
                        logger.info(f"Clearing invalid telegram_file_id for video {video_id}")
                        DatabaseQueries.update_video_telegram_file_id(video_id, None)
                    else:
                        logger.info(f"Keeping telegram_file_id for video {video_id} - error might be temporary")
            
            # Fallback: try forwarding original message if origin identifiers are available
            origin_chat_id = video.get('origin_chat_id')
            origin_msg_id = video.get('origin_message_id')
            if origin_chat_id and origin_msg_id:
                try:
                    from telegram._messageid import MessageId  # type: ignore
                    copied_msg = await bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=origin_chat_id,
                        message_id=origin_msg_id,
                    )
                    # PTB may return either Message or MessageId depending on context
                    if isinstance(copied_msg, MessageId):
                        logger.info(f"Forwarded original message (MessageId only) for video {video_id} to user {user_id}")
                        # We cannot cache a new file_id, but message has been delivered
                        return video.get('telegram_file_id')
                    elif copied_msg and getattr(copied_msg, 'video', None):
                        new_file_id = copied_msg.video.file_id
                        # Cache new file_id for future sends
                        DatabaseQueries.update_video_telegram_file_id(video_id, new_file_id)
                        logger.info(f"Forwarded original message for video {video_id} to user {user_id}")
                        return new_file_id
                    else:
                        logger.warning(f"copy_message did not return a video for video {video_id}")
                except TelegramError as copy_error:
                    logger.warning(f"Failed to copy original message for video {video_id}: {copy_error}")
            
            # Validate file path - if empty, try to use Telegram file_id directly
            if not file_path:
                if video.get('telegram_file_id'):
                    logger.info(f"Video {video_id} has empty file_path, trying to use cached Telegram file_id")
                    try:
                        message = await bot.send_video(
                            chat_id=user_id,
                            video=video['telegram_file_id'],
                            caption=caption or video.get('display_name', f'Video {video_id}'),
                            read_timeout=30,
                            write_timeout=30,
                            connect_timeout=30
                        )
                        logger.info(f"Successfully sent video {video_id} using cached file_id")
                        return video['telegram_file_id']
                    except TelegramError as e:
                        logger.warning(f"Failed to send video {video_id} using cached file_id: {e}")
                        # Only clear file_id for permanent errors, not temporary ones
                        error_msg = str(e).lower()
                        if any(permanent_error in error_msg for permanent_error in [
                            'file not found', 'file_id expired', 'file deleted', 
                            'bad file_id', 'invalid file_id',
                            'file_reference expired', 'file reference expired'
                        ]):
                            logger.info(f"Clearing invalid telegram_file_id for video {video_id}")
                            DatabaseQueries.update_video_telegram_file_id(video_id, None)
                        else:
                            logger.info(f"Keeping telegram_file_id for video {video_id} - error might be temporary")
                        
                        # Try to fallback to file_path if available
                        if file_path and os.path.exists(file_path):
                            logger.info(f"Falling back to file_path for video {video_id}")
                            # Continue to file_path sending logic below
                        else:
                            # This is likely a large video from private channel
                            # The telegram_file_id is not accessible for regular users
                            logger.warning(f"Video {video_id} telegram_file_id failed - likely from private channel")
                            
                            # For now, we cannot send this video as we don't have local file
                            # Admin needs to re-upload the video directly to bot (not forward from private channel)
                            logger.warning(f"Attempting to download video {video_id} from Telegram servers…")
                            new_path = await self._download_video_from_telegram(
                                bot,
                                video_id,
                                video['telegram_file_id'],
                                suggested_filename=video.get('filename') or f"video_{video_id}.mp4"
                            )
                            if new_path and os.path.exists(new_path):
                                logger.info(f"Downloaded video {video_id} to {new_path}. Retrying send…")
                                file_path = new_path
                            else:
                                logger.error(f"Cannot send video {video_id}: download attempt failed")
                                return None
                else:
                    # telegram_file_id worked, return it
                    return video['telegram_file_id']
                
            # If we reach here, either no telegram_file_id or it failed but we have file_path
            if not file_path:
                logger.error(f"Video {video_id} has empty file_path and no valid Telegram file_id")
                return None
            
            # Check if file exists
            if not os.path.exists(file_path):
                logger.warning(f"Video file not found at: {file_path} for video {video_id}")
                # Try multiple fallback strategies
                alt_paths = []
                
                # Strategy 1: Try filename only in videos directory
                if video.get('filename'):
                    alt_paths.append(self.get_video_path(video['filename']))
                
                # Strategy 2: Try basename of current path in videos directory
                filename_only = os.path.basename(file_path)
                if filename_only:
                    alt_paths.append(os.path.join(self.videos_directory, filename_only))
                
                # Strategy 3: Try display_name as filename
                if video.get('display_name'):
                    display_name = video['display_name']
                    # Try common video extensions
                    for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
                        if not display_name.lower().endswith(ext.lower()):
                            alt_paths.append(os.path.join(self.videos_directory, display_name + ext))
                
                # Try each alternative path
                found_path = None
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        logger.info(f"Found video at alternative path: {alt_path}")
                        found_path = alt_path
                        break
                
                if found_path:
                    file_path = found_path
                    # Update database with correct path
                    DatabaseQueries.update_video_file_path(video_id, found_path)
                else:
                    logger.error(f"Video file not found in any location for video {video_id}")
                    logger.error(f"Tried paths: {alt_paths}")
                    return None
            
            # Check file size (Telegram limit is 50MB for bots)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:  # 50MB
                logger.error(f"Video {video_id} is too large ({file_size} bytes) for Telegram")
                return None
            
            # Upload video file with timeout handling
            try:
                with open(file_path, 'rb') as video_file:
                    message = await bot.send_video(
                        chat_id=user_id,
                        video=video_file,
                        caption=caption or video.get('display_name', f'Video {video_id}'),
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=30
                    )
                
                # Cache the file_id for future use
                file_id = message.video.file_id
                DatabaseQueries.update_video_telegram_file_id(video_id, file_id)
                
                logger.info(f"Successfully sent video {video_id} to user {user_id}")
                return file_id
                
            except Exception as upload_error:
                logger.error(f"Failed to upload video {video_id} to user {user_id}: {upload_error}")
                return None
            
        except Exception as e:
            logger.error(f"Error sending video {video.get('id', 'unknown')} to user {user_id}: {e}")
            return None
    
    async def _download_video_from_telegram(self, bot: Bot, video_id: int, file_id: str, suggested_filename: str = None) -> Optional[str]:
        """Download a Telegram file by its file_id and save it locally.

        Args:
            bot: telegram.Bot instance.
            video_id: DB id, only for logging / db update.
            file_id: telegram file_id to download.
            suggested_filename: filename to save under (will ensure uniqueness).

        Returns:
            Absolute path where the file was saved, or None on failure.
        """
        try:
            telegram_file = await bot.get_file(file_id)
            if not suggested_filename:
                suggested_filename = f"video_{video_id}.mp4"
            # ensure unique path
            dst_path = os.path.join(self.videos_directory, suggested_filename)
            base, ext = os.path.splitext(dst_path)
            counter = 1
            while os.path.exists(dst_path):
                dst_path = f"{base}_{counter}{ext}"
                counter += 1

            await telegram_file.download_to_drive(dst_path)
            # update DB path
            DatabaseQueries.update_video_file_path(video_id, dst_path)
            logger.info(f"Downloaded video {video_id} from Telegram to {dst_path}")
            return dst_path
        except Exception as e:
            logger.error(f"Failed to download video {video_id} from Telegram: {e}")
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

    def delete_video(self, video_id: int, file_path: str = None) -> bool:
        """
        Delete a video both from the filesystem and the database (including plan links).
        Args:
            video_id: ID of the video to delete
            file_path: (optional) path to the video file. If not provided, will fetch from DB.
        Returns:
            True if database record was deleted (file may or may not exist)
        """
        try:
            # If file_path not provided, fetch from DB
            if not file_path:
                video = DatabaseQueries.get_video_by_id(video_id)
                if not video or not video.get('file_path'):
                    logger.error(f"Cannot find file_path for video {video_id}")
                    file_path = None
                else:
                    file_path = video['file_path']
            # Try to delete the file if it exists
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted video file: {file_path}")
                except Exception as fe:
                    logger.error(f"Failed to delete video file {file_path}: {fe}")
            else:
                logger.warning(f"Video file does not exist: {file_path}")
            # Delete from database (including plan links)
            result = DatabaseQueries.delete_video(video_id)
            if result:
                logger.info(f"Deleted video {video_id} from database and plan associations.")
            else:
                logger.error(f"Failed to delete video {video_id} from database.")
            return result
        except Exception as e:
            logger.error(f"Error deleting video {video_id}: {e}")
            return False

# Global instance
video_service = VideoService()
