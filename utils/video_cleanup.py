#!/usr/bin/env python3
"""
Video cleanup utility for fixing broken video records in the database.
This script helps identify and fix videos with missing files or empty paths.
"""

import os
import sys

# Add the project root directory to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.queries import DatabaseQueries
from services.video_service import video_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_broken_videos():
    """Find videos with missing files or empty paths."""
    videos = DatabaseQueries.get_all_videos()
    broken_videos = []
    
    for video in videos:
        video_id = video['id']
        file_path = video.get('file_path', '').strip()
        
        if not file_path:
            broken_videos.append({
                'video': video,
                'issue': 'empty_path',
                'description': f"Video {video_id} has empty file_path"
            })
        elif not os.path.exists(file_path):
            broken_videos.append({
                'video': video,
                'issue': 'missing_file',
                'description': f"Video {video_id} file not found: {file_path}"
            })
    
    return broken_videos

def get_available_files():
    """Get list of available video files in the videos directory."""
    videos_dir = os.path.join(os.getcwd(), 'database', 'data', 'videos')
    if not os.path.exists(videos_dir):
        return []
    
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'}
    files = []
    
    for filename in os.listdir(videos_dir):
        if any(filename.lower().endswith(ext) for ext in video_extensions):
            files.append({
                'filename': filename,
                'path': os.path.join(videos_dir, filename),
                'size': os.path.getsize(os.path.join(videos_dir, filename))
            })
    
    return files

def fix_broken_video(video_id, new_file_path):
    """Fix a broken video by updating its file path."""
    try:
        DatabaseQueries.update_video_file_path(video_id, new_file_path)
        logger.info(f"Fixed video {video_id} with new path: {new_file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to fix video {video_id}: {e}")
        return False

def auto_fix_broken_videos():
    """Automatically fix broken videos by matching them with available files."""
    broken_videos = find_broken_videos()
    available_files = get_available_files()
    
    if not broken_videos:
        logger.info("No broken videos found!")
        return
    
    if not available_files:
        logger.warning("No video files available for fixing!")
        return
    
    logger.info(f"Found {len(broken_videos)} broken videos")
    logger.info(f"Found {len(available_files)} available files")
    
    fixed_count = 0
    
    for broken in broken_videos:
        video = broken['video']
        video_id = video['id']
        filename = video.get('filename', '')
        
        # Try to find a matching file
        matching_file = None
        
        # First, try exact filename match
        for file_info in available_files:
            if file_info['filename'] == filename:
                matching_file = file_info
                break
        
        # If no exact match, use the first available file
        if not matching_file and available_files:
            matching_file = available_files[0]
        
        if matching_file:
            if fix_broken_video(video_id, matching_file['path']):
                fixed_count += 1
                logger.info(f"Fixed video {video_id} ({video['display_name']}) -> {matching_file['filename']}")
            else:
                logger.error(f"Failed to fix video {video_id}")
        else:
            logger.warning(f"No suitable file found for video {video_id}")
    
    logger.info(f"Fixed {fixed_count} out of {len(broken_videos)} broken videos")

def main():
    """Main function to run the cleanup utility."""
    print("🎥 Video Cleanup Utility")
    print("=" * 50)
    
    # Check for broken videos
    broken_videos = find_broken_videos()
    available_files = get_available_files()
    
    print(f"📊 Status:")
    print(f"  - Broken videos: {len(broken_videos)}")
    print(f"  - Available files: {len(available_files)}")
    
    if broken_videos:
        print("\n🔍 Broken videos found:")
        for broken in broken_videos:
            video = broken['video']
            print(f"  - Video {video['id']}: {video['display_name']} ({broken['issue']})")
    
    if available_files:
        print("\n📁 Available files:")
        for file_info in available_files:
            size_mb = file_info['size'] / (1024 * 1024)
            print(f"  - {file_info['filename']} ({size_mb:.1f} MB)")
    
    if broken_videos:
        response = input("\n🔧 Do you want to auto-fix broken videos? (y/n): ").lower()
        if response == 'y':
            auto_fix_broken_videos()
            print("\n✅ Cleanup completed!")
        else:
            print("\n❌ Cleanup cancelled.")
    else:
        print("\n✅ No broken videos found. Everything looks good!")

if __name__ == "__main__":
    main()
