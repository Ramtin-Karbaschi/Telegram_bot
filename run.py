"""
Main entry point for the Daraei Academy Telegram Bot system.
Starts both main bot and manager bot simultaneously.
"""

import asyncio
import logging
import sys
import os
import json
from bots import MainBot, ManagerBot
from database.models import Database
from database.queries import DatabaseQueries
# Patch DatabaseQueries with static aliases so legacy calls without an instance work
import database.compat_aliases  # noqa: E402, performs side-effects
import config
from dotenv import load_dotenv

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

# Load environment variables from .env file
load_dotenv()

async def main():
    """Start both bots"""
    logger.info("Starting Daraei Academy Telegram Bot System")
    
    # Ensure database directory exists
    os.makedirs(os.path.dirname(config.DATABASE_NAME), exist_ok=True)
    
    # Initialize database
    db_instance = Database()
    db_queries = DatabaseQueries(db_instance)
    db_queries.init_database()
    logger.info("Database initialized")
    
    # Create bot instances
    main_bot = MainBot()
    
    # Parse admin configuration from environment variable
    admin_config_str = os.getenv('ALL_ADMINS_CONFIG', '[]')
    admin_config = json.loads(admin_config_str)

    # Create manager bot instance
    manager_bot = ManagerBot(
        manager_bot_token=os.getenv('MANAGER_BOT_TOKEN'),
        admin_users_config=admin_config,  # Pass the parsed JSON list here
        db_name=os.getenv('DB_FILENAME'),
        main_bot_app=main_bot.application  # Pass the main bot's app instance
    )
    
    # Store manager_bot instance in main bot's application for cross-bot communication
    main_bot.application.manager_bot = manager_bot
    logger.info("Manager bot instance stored in main bot application context")
    
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
