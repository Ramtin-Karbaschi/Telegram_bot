"""
Retry helper for handling Telegram API timeouts and network issues
"""
import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Optional
from telegram.error import TimedOut, NetworkError, RetryAfter

logger = logging.getLogger(__name__)


def auto_retry(max_attempts: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """
    Decorator for automatic retry on Telegram API errors
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                    
                except TimedOut as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"TimedOut in {func.__name__} (attempt {attempt + 1}/{max_attempts}). "
                            f"Retrying in {current_delay} seconds..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"TimedOut in {func.__name__} after {max_attempts} attempts. Giving up."
                        )
                        
                except RetryAfter as e:
                    # Telegram is explicitly asking us to wait
                    wait_time = e.retry_after
                    logger.warning(
                        f"Telegram API rate limit hit in {func.__name__}. "
                        f"Waiting {wait_time} seconds as requested..."
                    )
                    await asyncio.sleep(wait_time)
                    # Don't count this as an attempt
                    continue
                    
                except NetworkError as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"NetworkError in {func.__name__} (attempt {attempt + 1}/{max_attempts}). "
                            f"Retrying in {current_delay} seconds..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"NetworkError in {func.__name__} after {max_attempts} attempts. Giving up."
                        )
                        
                except Exception as e:
                    # For non-network errors, don't retry
                    logger.error(f"Unexpected error in {func.__name__}: {e}")
                    raise
            
            # If we get here, all attempts failed
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


async def send_message_with_retry(
    bot,
    chat_id: int,
    text: str,
    max_attempts: int = 3,
    **kwargs
) -> Optional[Any]:
    """
    Send a message with automatic retry on failure
    
    Args:
        bot: Telegram bot instance
        chat_id: Target chat ID
        text: Message text
        max_attempts: Maximum number of retry attempts
        **kwargs: Additional arguments for send_message
    
    Returns:
        Message object on success, None on failure
    """
    delay = 2.0
    backoff = 2.0
    
    for attempt in range(max_attempts):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            
        except TimedOut as e:
            if attempt < max_attempts - 1:
                logger.warning(
                    f"TimedOut sending message to {chat_id} (attempt {attempt + 1}/{max_attempts}). "
                    f"Retrying in {delay} seconds..."
                )
                await asyncio.sleep(delay)
                delay *= backoff
            else:
                logger.error(
                    f"Failed to send message to {chat_id} after {max_attempts} attempts: {e}"
                )
                return None
                
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(
                f"Rate limit hit sending message to {chat_id}. Waiting {wait_time} seconds..."
            )
            await asyncio.sleep(wait_time)
            # Don't count this as an attempt, retry immediately after wait
            continue
            
        except Exception as e:
            logger.error(f"Unexpected error sending message to {chat_id}: {e}")
            return None
    
    return None


async def edit_message_with_retry(
    bot,
    chat_id: int,
    message_id: int,
    text: str,
    max_attempts: int = 3,
    **kwargs
) -> Optional[Any]:
    """
    Edit a message with automatic retry on failure
    
    Args:
        bot: Telegram bot instance
        chat_id: Target chat ID
        message_id: Message ID to edit
        text: New message text
        max_attempts: Maximum number of retry attempts
        **kwargs: Additional arguments for edit_message_text
    
    Returns:
        Message object on success, None on failure
    """
    delay = 2.0
    backoff = 2.0
    
    for attempt in range(max_attempts):
        try:
            return await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                **kwargs
            )
            
        except TimedOut as e:
            if attempt < max_attempts - 1:
                logger.warning(
                    f"TimedOut editing message {message_id} in {chat_id} "
                    f"(attempt {attempt + 1}/{max_attempts}). Retrying in {delay} seconds..."
                )
                await asyncio.sleep(delay)
                delay *= backoff
            else:
                logger.error(
                    f"Failed to edit message {message_id} in {chat_id} "
                    f"after {max_attempts} attempts: {e}"
                )
                return None
                
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(
                f"Rate limit hit editing message {message_id} in {chat_id}. "
                f"Waiting {wait_time} seconds..."
            )
            await asyncio.sleep(wait_time)
            continue
            
        except Exception as e:
            logger.error(
                f"Unexpected error editing message {message_id} in {chat_id}: {e}"
            )
            return None
    
    return None
