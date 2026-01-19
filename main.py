"""
Server Health Bot - Main entry point
"""
import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from database.db import db
from bot.handlers import router
from scheduler.jobs import setup_scheduler, start_scheduler, stop_scheduler


# Setup logging
def setup_logging():
    """Configure logging"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create logs directory
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=log_format,
        handlers=[
            logging.FileHandler(settings.log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from libraries
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def on_startup(bot: Bot):
    """Actions on bot startup"""
    logger = logging.getLogger(__name__)
    logger.info("Bot starting up...")
    
    # Initialize database
    await db.init()
    logger.info("Database initialized")
    
    # Setup and start scheduler
    setup_scheduler(bot)
    start_scheduler()
    logger.info("Scheduler started")
    
    # Notify admin
    try:
        await bot.send_message(
            chat_id=settings.admin_id,
            text="🟢 <b>Server Health Bot запущен</b>\n\n/start — открыть меню",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")


async def on_shutdown(bot: Bot):
    """Actions on bot shutdown"""
    logger = logging.getLogger(__name__)
    logger.info("Bot shutting down...")
    
    # Stop scheduler
    stop_scheduler()
    
    # Notify admin
    try:
        await bot.send_message(
            chat_id=settings.admin_id,
            text="🔴 <b>Server Health Bot остановлен</b>",
            parse_mode="HTML"
        )
    except:
        pass


async def main():
    """Main function"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Validate config
    if not settings.bot_token or settings.bot_token == "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ":
        logger.error("BOT_TOKEN not configured! Edit .env file.")
        sys.exit(1)
    
    if not settings.admin_id or settings.admin_id == 123456789:
        logger.error("ADMIN_ID not configured! Edit .env file.")
        sys.exit(1)
    
    # Create bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher()
    dp.include_router(router)
    
    # Register startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("Starting bot...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
