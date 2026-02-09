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
from core.ssh_manager import SSHManager
from core.vpn_checker import check_all_dpi, update_dpi_state, format_dpi_alert

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


async def auto_optimize_server(server, bot: Bot) -> str:
    """Auto-optimize server when disk > 80%"""
    try:
        ssh = SSHManager(
            host=server.host,
            port=server.port,
            username=server.username,
            key_path=server.key_path
        )

        # Clean journal and cache
        await ssh.execute("journalctl --vacuum-size=200M 2>&1")
        await ssh.execute("apt-get clean 2>/dev/null; rm -rf /tmp/* /var/tmp/* 2>/dev/null")

        # Check new disk usage
        result = await ssh.execute("df / --output=pcent | tail -1 | tr -d ' %'")
        new_percent = int(result.stdout.strip()) if result.success else 0

        logger.info(f"Auto-optimized {server.name}, disk now at {new_percent}%")
        return f"✅ Очищено, диск: {new_percent}%"

    except Exception as e:
        logger.error(f"Auto-optimize error for {server.name}: {e}")
        return f"❌ Ошибка: {str(e)[:30]}"


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

            # Auto-optimize if any disk > 80%
            max_disk = max((d.value for d in report.disks), default=0)
            if max_disk > 80:
                logger.info(f"Disk on {server.name} at {max_disk}%, auto-optimizing...")
                optimize_result = await auto_optimize_server(server, bot)

                await bot.send_message(
                    chat_id=settings.admin_id,
                    text=(
                        f"🧹 <b>Авто-оптимизация: {server.name}</b>\n\n"
                        f"Диск был заполнен на {max_disk}%\n"
                        f"{optimize_result}"
                    ),
                    parse_mode="HTML"
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


async def dpi_monitor_check(bot: Bot):
    """Check for DPI blocking and send alerts on state changes"""
    try:
        results = await check_all_dpi()

        for result in results:
            change = update_dpi_state(result.server_name, result.is_blocked)
            if change:
                alert_text = format_dpi_alert(result, change)
                try:
                    await bot.send_message(
                        chat_id=settings.admin_id,
                        text=alert_text,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to send DPI alert: {e}")

            if result.is_blocked:
                logger.warning(f"DPI blocking detected for {result.server_name}")
            else:
                logger.debug(f"DPI OK for {result.server_name}")

    except Exception as e:
        logger.error(f"DPI monitor error: {e}")


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

    # DPI monitor (default: every 3 minutes)
    if settings.dpi_check_interval_minutes > 0:
        scheduler.add_job(
            dpi_monitor_check,
            trigger=IntervalTrigger(minutes=settings.dpi_check_interval_minutes),
            args=[bot],
            id="dpi_monitor",
            replace_existing=True,
            name="DPI blocking monitor"
        )
        logger.info(f"Scheduled DPI monitor every {settings.dpi_check_interval_minutes} minutes")


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
