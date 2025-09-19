"""
Integration module for SpotPlayer functionality
This module handles the integration of SpotPlayer with the main bot
"""

import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from telegram.ext import Application

from database.queries import DatabaseQueries
from database.spotplayer_queries import SpotPlayerQueries
from handlers.spotplayer.spotplayer_handler import SpotPlayerHandler
from handlers.spotplayer.admin_spotplayer_handler import AdminSpotPlayerHandler

logger = logging.getLogger(__name__)

class SpotPlayerIntegration:
    """Integration class for SpotPlayer functionality"""
    
    def __init__(self, db_connection, config):
        """Initialize SpotPlayer integration"""
        self.db = DatabaseQueries()
        self.spotplayer_db = SpotPlayerQueries(db_connection)
        self.config = config
        
        # Initialize handlers
        self.spotplayer_handler = SpotPlayerHandler(self.db, config)
        self.admin_spotplayer_handler = AdminSpotPlayerHandler(self.db, config)
        
        # Update SpotPlayer handler with queries
        self.spotplayer_handler.spotplayer_db = self.spotplayer_db
        self.admin_spotplayer_handler.spotplayer_db = self.spotplayer_db
        
        logger.info("SpotPlayer integration initialized")
    
    def integrate_with_main_bot(self, application: Application):
        """Integrate SpotPlayer handlers with main bot"""
        
        # Add SpotPlayer conversation handler for users
        spotplayer_conv = self.spotplayer_handler.get_conversation_handler()
        application.add_handler(spotplayer_conv, group=5)
        
        logger.info("SpotPlayer user handler integrated with main bot")
    
    def integrate_with_manager_bot(self, application: Application):
        """Integrate SpotPlayer admin handlers with manager bot"""
        
        # Add admin handlers
        admin_handlers = self.admin_spotplayer_handler.get_handlers()
        
        for handler in admin_handlers:
            application.add_handler(handler, group=5)
        
        logger.info(f"SpotPlayer admin handlers ({len(admin_handlers)}) integrated with manager bot")
    
    def add_to_user_menu(self, keyboard: list) -> list:
        """Add SpotPlayer option to user menu"""
        
        # Check if SpotPlayer is enabled
        if self.spotplayer_db.get_config('enabled') == '1':
            # Add SpotPlayer button to keyboard
            spotplayer_button = KeyboardButton("🎬 تأیید خرید SpotPlayer")
            
            # Find appropriate row or create new one
            if len(keyboard) > 0 and len(keyboard[-1]) < 2:
                keyboard[-1].append(spotplayer_button)
            else:
                keyboard.append([spotplayer_button])
        
        return keyboard
    
    def add_to_admin_menu(self, keyboard: list) -> list:
        """Add SpotPlayer option to admin menu"""
        
        # Add SpotPlayer management button
        spotplayer_button = InlineKeyboardButton(
            "🎬 مدیریت SpotPlayer",
            callback_data="admin_spotplayer_menu"
        )
        
        # Add as a new row
        keyboard.insert(-1, [spotplayer_button])  # Insert before back button
        
        return keyboard
    
    def update_configuration(self, key: str, value: str) -> bool:
        """Update SpotPlayer configuration"""
        
        success = self.spotplayer_db.update_config(key, value)
        
        if success:
            # Update handler configuration
            if key in self.spotplayer_handler.SPOTPLAYER_CONFIG:
                if key in ['price', 'subscription_days', 'channel_id']:
                    # Convert to appropriate type
                    if key == 'price':
                        value = int(value)
                    elif key == 'subscription_days':
                        value = int(value)
                    elif key == 'channel_id':
                        value = int(value)
                
                self.spotplayer_handler.SPOTPLAYER_CONFIG[key] = value
                logger.info(f"Updated SpotPlayer config: {key} = {value}")
        
        return success
    
    def get_configuration(self) -> dict:
        """Get current SpotPlayer configuration"""
        
        config_keys = [
            'product_name', 'price', 'subscription_days',
            'channel_id', 'channel_username', 'zarinpal_merchant',
            'min_amount', 'max_amount', 'enabled'
        ]
        
        config = {}
        for key in config_keys:
            value = self.spotplayer_db.get_config(key)
            config[key] = value
        
        return config
    
    def get_statistics(self) -> dict:
        """Get SpotPlayer statistics"""
        return self.spotplayer_db.get_purchase_stats()
    
    def verify_system_health(self) -> dict:
        """Verify SpotPlayer system health"""
        
        health = {
            'database': False,
            'configuration': False,
            'handlers': False,
            'channel_access': False
        }
        
        # Check database tables
        try:
            self.spotplayer_db.get_config('enabled')
            health['database'] = True
        except:
            pass
        
        # Check configuration
        config = self.get_configuration()
        if config.get('enabled') and config.get('zarinpal_merchant') != 'YOUR_MERCHANT_ID':
            health['configuration'] = True
        
        # Check handlers
        if self.spotplayer_handler and self.admin_spotplayer_handler:
            health['handlers'] = True
        
        # Overall health
        health['overall'] = all([
            health['database'],
            health['configuration'],
            health['handlers']
        ])
        
        return health

# Integration helper functions

def setup_spotplayer_in_main_bot(application: Application, config):
    """Setup SpotPlayer in main bot"""
    try:
        from database.queries import DatabaseQueries
        
        # Get database connection
        db = DatabaseQueries()
        
        # Create integration
        integration = SpotPlayerIntegration(db.connection, config)
        
        # Integrate with main bot
        integration.integrate_with_main_bot(application)
        
        # Store integration instance for later use
        application.bot_data['spotplayer_integration'] = integration
        
        logger.info("SpotPlayer successfully integrated with main bot")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up SpotPlayer in main bot: {e}")
        return False

def setup_spotplayer_in_manager_bot(application: Application, config):
    """Setup SpotPlayer in manager bot"""
    try:
        from database.queries import DatabaseQueries
        
        # Get database connection
        db = DatabaseQueries()
        
        # Create integration
        integration = SpotPlayerIntegration(db.connection, config)
        
        # Integrate with manager bot
        integration.integrate_with_manager_bot(application)
        
        # Store integration instance for later use
        application.bot_data['spotplayer_integration'] = integration
        
        logger.info("SpotPlayer successfully integrated with manager bot")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up SpotPlayer in manager bot: {e}")
        return False
