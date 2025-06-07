"""
Main entry point for the Daraei Academy Telegram Bot system.
Starts both main bot and manager bot simultaneously.
"""

import asyncio
import logging
import sys
import os
from bots import MainBot, ManagerBot
from database.models import Database
from database.queries import DatabaseQueries
import config

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Enable DEBUG logging for the dispatcher to see handler processing details
dispatcher_logger = logging.getLogger("telegram.ext.dispatcher")
dispatcher_logger.setLevel(logging.DEBUG)

# Diagnostic prints for logging configuration
print(f"[LOG_DIAGNOSTIC] Root logger effective level: {logging.getLogger().getEffectiveLevel()} (DEBUG is {logging.DEBUG}, INFO is {logging.INFO})")
print(f"[LOG_DIAGNOSTIC] Dispatcher logger effective level: {dispatcher_logger.getEffectiveLevel()}")
print(f"[LOG_DIAGNOSTIC] Root logger handlers: {logging.getLogger().handlers}")
print(f"[LOG_DIAGNOSTIC] Dispatcher logger handlers: {dispatcher_logger.handlers}")
print(f"[LOG_DIAGNOSTIC] Dispatcher logger propagate: {dispatcher_logger.propagate}")

logger = logging.getLogger(__name__)

async def main():
    """Start both bots"""
    logger.info("Starting Daraei Academy Telegram Bot System")
    
    # Ensure database directory exists
    os.makedirs(os.path.dirname(config.DATABASE_NAME), exist_ok=True)
    
    # Initialize database
    db = Database(config.DATABASE_NAME)
    DatabaseQueries.init_database()  # Changed from initialize_database to init_database
    logger.info("Database initialized")
    
    # Create bot instances
    main_bot = MainBot()
    # Pass necessary config and main_bot's application instance to ManagerBot
    manager_bot = ManagerBot(
        manager_bot_token=config.MANAGER_BOT_TOKEN,
        admin_users_config=config.MANAGER_BOT_ADMINS_DICT, # Use the new consolidated admin dict
        db_name=config.DATABASE_NAME,
        main_bot_app=main_bot.application # Pass the application instance of the main bot
    )
    
    try:
        # Start both bots
        await asyncio.gather(
            main_bot.start(),
            manager_bot.start()
        )
        
        logger.info("Both bots are running")
        
        # Keep the program running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        # Handle graceful shutdown on Ctrl+C
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        # Stop both bots
        await asyncio.gather(
            main_bot.stop(),
            manager_bot.stop()
        )
        
        logger.info("Both bots have been stopped")

if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 7):
        logger.error("Python 3.7 or higher is required")
        sys.exit(1)
        
    # Run the main function
    asyncio.run(main())
