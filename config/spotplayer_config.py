"""
SpotPlayer Configuration Module
Loads and manages SpotPlayer configuration from environment variables
"""

import os
import json
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class SpotPlayerConfig:
    """SpotPlayer configuration manager"""
    
    def __init__(self):
        """Initialize SpotPlayer configuration"""
        load_dotenv()
        
        # Load API configuration
        self.API_KEY = os.getenv('SPOTPLAYER_API_KEY', '')
        self.API_URL = os.getenv('SPOTPLAYER_API_URL', 'https://panel.spotplayer.ir/license/edit/')
        
        # Load Zarinpal configuration
        self.ZARINPAL_MERCHANT = os.getenv('ZARINPAL_MERCHANT_ID', '')
        self.ZARINPAL_VERIFY_URL = 'https://api.zarinpal.com/pg/v4/payment/verify.json'
        
        # Load available channels
        self.channels = self._load_channels()
        
        # Load course configurations
        self.courses = self._load_courses()
        
        # Validation
        self._validate_config()
        
        logger.info(f"SpotPlayer config loaded: {len(self.channels)} channels, {len(self.courses)} courses")
    
    def _load_channels(self) -> Dict[int, Dict]:
        """Load channel information from environment"""
        channels_json = os.getenv('TELEGRAM_CHANNELS_INFO', '[]')
        
        try:
            channels_list = json.loads(channels_json)
            channels_dict = {}
            
            for channel in channels_list:
                channel_id = channel.get('id')
                if channel_id:
                    channels_dict[channel_id] = {
                        'id': channel_id,
                        'link': channel.get('link', ''),
                        'title': channel.get('title', 'Unknown Channel'),
                        'username': self._extract_username_from_link(channel.get('link', ''))
                    }
            
            return channels_dict
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing TELEGRAM_CHANNELS_INFO: {e}")
            return {}
    
    def _load_courses(self) -> Dict[str, Dict]:
        """Load SpotPlayer course configurations from environment"""
        courses_json = os.getenv('SPOTPLAYER_COURSES', '[]')
        
        try:
            courses_list = json.loads(courses_json)
            courses_dict = {}
            
            for course in courses_list:
                course_id = course.get('id')
                if course_id:
                    courses_dict[course_id] = {
                        'id': course_id,
                        'name': course.get('name', 'Unknown Course'),
                        'description': course.get('description', '')
                    }
            
            return courses_dict
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing SPOTPLAYER_COURSES: {e}")
            return {}
    
    def _extract_username_from_link(self, link: str) -> str:
        """Extract username from Telegram link"""
        if 't.me/' in link:
            # Handle both public and private links
            parts = link.split('t.me/')
            if len(parts) > 1:
                username = parts[1].split('/')[0].split('?')[0]
                if not username.startswith('+'):
                    return f"@{username}"
        return ''
    
    def _validate_config(self):
        """Validate configuration"""
        errors = []
        
        if not self.API_KEY:
            errors.append("SPOTPLAYER_API_KEY not set in .env")
        
        if not self.ZARINPAL_MERCHANT:
            errors.append("ZARINPAL_MERCHANT_ID not set in .env")
        
        if not self.channels:
            errors.append("No channels found in TELEGRAM_CHANNELS_INFO")
        
        if not self.courses:
            logger.warning("No courses found in SPOTPLAYER_COURSES - using defaults")
        
        if errors:
            for error in errors:
                logger.error(error)
            raise ValueError(f"SpotPlayer configuration errors: {', '.join(errors)}")
    
    def get_channel_by_id(self, channel_id: int) -> Optional[Dict]:
        """Get channel information by ID"""
        return self.channels.get(channel_id)
    
    def get_course_by_id(self, course_id: str) -> Optional[Dict]:
        """Get course information by ID"""
        return self.courses.get(course_id)
    
    def get_all_channels(self) -> List[Dict]:
        """Get all available channels"""
        return list(self.channels.values())
    
    def get_all_courses(self) -> List[Dict]:
        """Get all available courses"""
        return list(self.courses.values())
    
    def get_channel_choices(self) -> List[tuple]:
        """Get channel choices for forms (id, title)"""
        return [(str(ch['id']), ch['title']) for ch in self.channels.values()]
    
    def get_course_choices(self) -> List[tuple]:
        """Get course choices for forms (id, name)"""
        return [(c['id'], c['name']) for c in self.courses.values()]
    
    def to_dict(self) -> Dict:
        """Export configuration as dictionary"""
        return {
            'api_key': self.API_KEY[:10] + '...' if self.API_KEY else 'Not set',
            'api_url': self.API_URL,
            'merchant_id': self.ZARINPAL_MERCHANT[:10] + '...' if self.ZARINPAL_MERCHANT else 'Not set',
            'channels_count': len(self.channels),
            'courses_count': len(self.courses),
            'channels': self.channels,
            'courses': self.courses
        }

# Create singleton instance
spotplayer_config = SpotPlayerConfig()
