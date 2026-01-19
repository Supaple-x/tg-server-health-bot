"""
Scheduler for periodic health checks
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from config import settings
from database.db import db
from core.health_checker import check_local_server, check_remote_server
from core.report_formatter import format_full_report, format_all_servers_summary

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def scheduled_health_check(bot: Bot):
    """Perform scheduled health check of all servers"""
    logger.info("Running scheduled health check")
    
    servers = await db.get_all_servers()
    
    if not servers:
        logger.info("No servers configured, skipping check")
        return
    
    reports = []
    critical_reports = []
    
    for server in servers:
        try:
            if server.host == "localhost":
                report = await check_local_server(server.name)
            else:
                report = await check_remote_server(
                    host=server.host,
                    name=server.name,
                    port=server.port,
                    username=server.username,
                    key_path=server.key_path
                )
            
            reports.append(report)
            await db.update_last_check(server.name, report.overall_status)
            
            # Track critical issues
            if report.overall_status == "critical":
                critical_reports.append(report)
                
        except Exception as e:
            logger.error(f"Error checking {server.name}: {e}")
    
    # Send summary to admin
    if reports:
        text = "📊 <b>Плановая проверка</b>\n\n" + format_all_servers_summary(reports)
        
        try:
            await bot.send_message(
                chat_id=settings.admin_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send scheduled report: {e}")
    
    # Send critical alerts
    for report in critical_reports:
        alert_text = (
            f"🚨 <b>КРИТИЧЕСКОЕ СОСТОЯНИЕ</b>\n\n"
            f"{format_full_report(report)}"
        )
        try:
            await bot.send_message(
                chat_id=settings.admin_id,
                text=alert_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send critical alert: {e}")


async def quick_alert_check(bot: Bot):
    """Quick check for critical issues (more frequent)"""
    servers = await db.get_all_servers()
    
    for server in servers:
        try:
            if server.host == "localhost":
                report = await check_local_server(server.name)
            else:
                report = await check_remote_server(
                    host=server.host,
                    name=server.name,
                    port=server.port,
                    username=server.username,
                    key_path=server.key_path
                )
            
            # Only alert on status change to critical
            if report.overall_status == "critical" and server.last_status != "critical":
                alert_text = (
                    f"🚨 <b>ВНИМАНИЕ: {server.name}</b>\n\n"
                    f"Статус изменился на КРИТИЧЕСКИЙ!\n\n"
                )
                for issue in report.issues:
                    alert_text += f"• {issue}\n"
                
                await bot.send_message(
                    chat_id=settings.admin_id,
                    text=alert_text,
                    parse_mode="HTML"
                )
            
            await db.update_last_check(server.name, report.overall_status)
            
        except Exception as e:
            logger.error(f"Quick check error for {server.name}: {e}")


def setup_scheduler(bot: Bot):
    """Setup scheduled jobs"""
    
    # Main health check (default: every 6 hours)
    if settings.check_interval_hours > 0:
        scheduler.add_job(
            scheduled_health_check,
            trigger=IntervalTrigger(hours=settings.check_interval_hours),
            args=[bot],
            id="health_check",
            replace_existing=True,
            name="Periodic health check"
        )
        logger.info(f"Scheduled health check every {settings.check_interval_hours} hours")
    
    # Quick alert check (default: every 15 minutes)
    if settings.alert_check_interval_minutes > 0:
        scheduler.add_job(
            quick_alert_check,
            trigger=IntervalTrigger(minutes=settings.alert_check_interval_minutes),
            args=[bot],
            id="alert_check",
            replace_existing=True,
            name="Quick alert check"
        )
        logger.info(f"Scheduled alert check every {settings.alert_check_interval_minutes} minutes")


def update_check_interval(hours: int, bot: Bot):
    """Update the health check interval"""
    # Remove existing job
    try:
        scheduler.remove_job("health_check")
    except:
        pass
    
    if hours > 0:
        scheduler.add_job(
            scheduled_health_check,
            trigger=IntervalTrigger(hours=hours),
            args=[bot],
            id="health_check",
            replace_existing=True,
            name="Periodic health check"
        )
        logger.info(f"Updated health check interval to {hours} hours")


def start_scheduler():
    """Start the scheduler"""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
