"""
Telegram bot command handlers
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import settings
from database.db import db, Server
from core.ssh_manager import SSHManager, LocalSSHManager
from core.health_checker import HealthChecker, check_local_server, check_remote_server
from core.report_formatter import (
    format_full_report,
    format_short_report,
    format_processes_report,
    format_all_servers_summary,
    format_server_map
)
from bot.keyboards import (
    main_menu_keyboard,
    servers_list_keyboard,
    server_actions_keyboard,
    report_actions_keyboard,
    optimize_keyboard,
    confirm_keyboard,
    settings_keyboard,
    schedule_keyboard
)

logger = logging.getLogger(__name__)
router = Router()


# Country flags mapping
COUNTRY_FLAGS = {
    "USA": "🇺🇸",
    "Finland": "🇫🇮",
    "Germany": "🇩🇪",
    "Netherlands": "🇳🇱",
    "Russia": "🇷🇺",
    "UK": "🇬🇧",
    "France": "🇫🇷",
    "Canada": "🇨🇦",
    "Japan": "🇯🇵",
    "Singapore": "🇸🇬",
}


def get_server_flag(server_name: str) -> str:
    """Get country flag for server"""
    return COUNTRY_FLAGS.get(server_name, "🌐")


# FSM States for adding server
class AddServerStates(StatesGroup):
    name = State()
    host = State()
    port = State()
    username = State()
    key_path = State()


# ============== Command Handlers ==============

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command"""
    if message.from_user.id != settings.admin_id:
        await message.answer("⛔ Доступ запрещён")
        return
    
    await message.answer(
        "🖥 <b>Server Health Bot</b>\n\n"
        "Мониторинг и управление серверами.\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    help_text = """
🖥 <b>Server Health Bot — Помощь</b>

<b>Основные команды:</b>
/start — Главное меню
/status — Быстрый статус всех серверов
/check — Полная проверка сервера
/servers — Список серверов

<b>Управление:</b>
/add — Добавить сервер
/remove — Удалить сервер

<b>Настройки:</b>
/schedule — Расписание проверок
/alerts — Настройка уведомлений

<b>Использование:</b>
• Нажимайте кнопки для навигации
• Используйте /check [имя] для быстрой проверки
"""
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Quick status of all servers"""
    if message.from_user.id != settings.admin_id:
        return
    
    await message.answer("🔄 Проверяю серверы...")
    
    servers = await db.get_all_servers()
    
    if not servers:
        await message.answer(
            "📭 Нет серверов.\n\nДобавьте первый сервер:",
            reply_markup=servers_list_keyboard([])
        )
        return
    
    reports = []
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
        except Exception as e:
            logger.error(f"Error checking {server.name}: {e}")
    
    if reports:
        text = format_all_servers_summary(reports, servers)
        await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        await message.answer("❌ Не удалось проверить серверы")


@router.message(Command("check"))
async def cmd_check(message: Message):
    """Check specific server or show menu"""
    if message.from_user.id != settings.admin_id:
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1:
        server_name = args[1]
        await check_server_by_name(message, server_name)
    else:
        servers = await db.get_all_servers()
        await message.answer(
            "🔍 Выберите сервер для проверки:",
            reply_markup=servers_list_keyboard(servers, "check")
        )


@router.message(Command("servers"))
async def cmd_servers(message: Message):
    """List all servers"""
    if message.from_user.id != settings.admin_id:
        return

    servers = await db.get_all_servers()

    # Build text with server info: status, flag, IP, name
    lines = ["🖥 <b>Серверы:</b>", ""]
    for server in servers:
        status_emoji = {
            "ok": "🟢", "warning": "🟡", "critical": "🔴", None: "⚪"
        }.get(server.last_status, "⚪")
        flag = get_server_flag(server.name)
        lines.append(f"{status_emoji} {flag} <code>{server.host}</code> — {server.name}")

    await message.answer(
        "\n".join(lines),
        reply_markup=servers_list_keyboard(servers, "server"),
        parse_mode="HTML"
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    """Start adding a server"""
    if message.from_user.id != settings.admin_id:
        return
    
    await state.set_state(AddServerStates.name)
    await message.answer(
        "➕ <b>Добавление сервера</b>\n\n"
        "Введите имя сервера (например: production, dev-1):",
        parse_mode="HTML"
    )


# ============== Callback Handlers ==============

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    """Return to main menu"""
    await callback.message.edit_text(
        "🖥 <b>Server Health Bot</b>\n\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "status_all")
async def cb_status_all(callback: CallbackQuery):
    """Check all servers"""
    await callback.answer("🔄 Проверяю...")

    servers = await db.get_all_servers()

    if not servers:
        await callback.message.edit_text(
            "📭 Нет серверов",
            reply_markup=servers_list_keyboard([])
        )
        return

    total = len(servers)
    reports = []

    for i, server in enumerate(servers, 1):
        # Update progress message
        flag = get_server_flag(server.name)
        progress_bar = "▓" * i + "░" * (total - i)
        await callback.message.edit_text(
            f"🔄 <b>Проверка серверов</b> [{i}/{total}]\n\n"
            f"{progress_bar}\n\n"
            f"➡️ {flag} {server.name} (<code>{server.host}</code>)...",
            parse_mode="HTML"
        )

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
        except Exception as e:
            logger.error(f"Error checking {server.name}: {e}")
    
    if reports:
        text = format_all_servers_summary(reports, servers)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )


@router.callback_query(F.data == "servers_list")
async def cb_servers_list(callback: CallbackQuery):
    """Show servers list"""
    servers = await db.get_all_servers()

    # Build text with server info: status, flag, IP, name
    lines = ["🖥 <b>Серверы:</b>", ""]
    for server in servers:
        status_emoji = {
            "ok": "🟢", "warning": "🟡", "critical": "🔴", None: "⚪"
        }.get(server.last_status, "⚪")
        flag = get_server_flag(server.name)
        lines.append(f"{status_emoji} {flag} <code>{server.host}</code> — {server.name}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=servers_list_keyboard(servers, "server"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("server:"))
async def cb_server_detail(callback: CallbackQuery):
    """Show server details"""
    server_name = callback.data.split(":")[1]
    server = await db.get_server(server_name)
    
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    
    status_emoji = {
        "ok": "🟢",
        "warning": "🟡",
        "critical": "🔴",
        None: "⚪"
    }.get(server.last_status, "⚪")
    
    text = (
        f"🖥 <b>{server.name}</b>\n\n"
        f"📍 Host: <code>{server.host}:{server.port}</code>\n"
        f"👤 User: {server.username}\n"
        f"📊 Статус: {status_emoji} {server.last_status or 'не проверялся'}\n"
        f"🕐 Последняя проверка: {server.last_check or 'никогда'}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=server_actions_keyboard(server_name),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check:"))
async def cb_check_server(callback: CallbackQuery):
    """Check specific server"""
    server_name = callback.data.split(":")[1]
    await callback.answer("🔄 Проверяю...")
    await callback.message.edit_text(f"🔄 Проверяю {server_name}...")
    
    server = await db.get_server(server_name)
    
    if not server:
        await callback.message.edit_text("❌ Сервер не найден")
        return
    
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
        
        await db.update_last_check(server_name, report.overall_status)

        text = format_full_report(report, server)
        await callback.message.edit_text(
            text,
            reply_markup=report_actions_keyboard(server_name),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error checking {server_name}: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка проверки: {str(e)}",
            reply_markup=server_actions_keyboard(server_name)
        )


@router.callback_query(F.data.startswith("processes:"))
async def cb_processes(callback: CallbackQuery):
    """Show top processes"""
    server_name = callback.data.split(":")[1]
    await callback.answer("🔄 Получаю...")
    
    server = await db.get_server(server_name)
    
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    
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
        
        text = format_processes_report(report)
        await callback.message.edit_text(
            text,
            reply_markup=report_actions_keyboard(server_name),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")


@router.callback_query(F.data.startswith("optimize:"))
async def cb_optimize_menu(callback: CallbackQuery):
    """Show optimization options"""
    server_name = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"🛠 <b>Оптимизация {server_name}</b>\n\n"
        "Выберите действие:",
        reply_markup=optimize_keyboard(server_name),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("opt_journal:"))
async def cb_opt_journal(callback: CallbackQuery):
    """Clean systemd journal logs"""
    server_name = callback.data.split(":")[1]
    server = await db.get_server(server_name)

    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    await callback.answer("🔄 Очищаю журналы...")
    await callback.message.edit_text(f"🔄 Очищаю журналы на {server_name}...")

    try:
        ssh = SSHManager(
            host=server.host,
            port=server.port,
            username=server.username,
            key_path=server.key_path
        )
        await ssh.connect()
        result = await ssh.execute("journalctl --vacuum-size=200M 2>&1")
        await ssh.disconnect()

        if result.success:
            # Parse freed space from output
            import re
            match = re.search(r'freed ([\d.]+[KMGT]?B?)', result.stdout)
            freed = match.group(1) if match else "some space"
            await callback.message.edit_text(
                f"✅ <b>Журналы очищены на {server_name}</b>\n\n"
                f"Освобождено: {freed}",
                reply_markup=optimize_keyboard(server_name),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка: {result.stderr}",
                reply_markup=optimize_keyboard(server_name),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error cleaning journal on {server_name}: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("opt_cache:"))
async def cb_opt_cache(callback: CallbackQuery):
    """Clean system cache"""
    server_name = callback.data.split(":")[1]
    server = await db.get_server(server_name)

    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    await callback.answer("🔄 Очищаю кэш...")
    await callback.message.edit_text(f"🔄 Очищаю кэш на {server_name}...")

    try:
        ssh = SSHManager(
            host=server.host,
            port=server.port,
            username=server.username,
            key_path=server.key_path
        )
        await ssh.connect()
        # Clean apt cache and tmp files older than 7 days
        result = await ssh.execute(
            "apt-get clean 2>/dev/null; "
            "rm -rf /tmp/* 2>/dev/null; "
            "rm -rf /var/tmp/* 2>/dev/null; "
            "echo 'OK'"
        )
        await ssh.disconnect()

        await callback.message.edit_text(
            f"✅ <b>Кэш очищен на {server_name}</b>\n\n"
            "Очищено:\n"
            "• APT кэш\n"
            "• /tmp\n"
            "• /var/tmp",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error cleaning cache on {server_name}: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("opt_logs:"))
async def cb_opt_logs(callback: CallbackQuery):
    """Clean old log files"""
    server_name = callback.data.split(":")[1]
    server = await db.get_server(server_name)

    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    await callback.answer("🔄 Очищаю логи...")
    await callback.message.edit_text(f"🔄 Очищаю старые логи на {server_name}...")

    try:
        ssh = SSHManager(
            host=server.host,
            port=server.port,
            username=server.username,
            key_path=server.key_path
        )
        await ssh.connect()
        # Truncate large log files and remove old rotated logs
        result = await ssh.execute(
            "find /var/log -name '*.gz' -delete 2>/dev/null; "
            "find /var/log -name '*.1' -delete 2>/dev/null; "
            "find /var/log -name '*.old' -delete 2>/dev/null; "
            "truncate -s 0 /var/log/*.log 2>/dev/null; "
            "echo 'OK'"
        )
        await ssh.disconnect()

        await callback.message.edit_text(
            f"✅ <b>Логи очищены на {server_name}</b>\n\n"
            "Очищено:\n"
            "• Архивы логов (.gz, .1, .old)\n"
            "• Текущие лог-файлы обрезаны",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error cleaning logs on {server_name}: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("opt_packages:"))
async def cb_opt_packages(callback: CallbackQuery):
    """Remove old packages"""
    server_name = callback.data.split(":")[1]
    server = await db.get_server(server_name)

    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    await callback.answer("🔄 Удаляю старые пакеты...")
    await callback.message.edit_text(f"🔄 Удаляю старые пакеты на {server_name}...")

    try:
        ssh = SSHManager(
            host=server.host,
            port=server.port,
            username=server.username,
            key_path=server.key_path
        )
        await ssh.connect()
        result = await ssh.execute("apt-get autoremove -y 2>&1 | tail -5")
        await ssh.disconnect()

        await callback.message.edit_text(
            f"✅ <b>Старые пакеты удалены на {server_name}</b>\n\n"
            f"<code>{result.stdout[:500]}</code>",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error removing packages on {server_name}: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=optimize_keyboard(server_name),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("map:"))
async def cb_server_map(callback: CallbackQuery):
    """Show server map with services"""
    server_name = callback.data.split(":")[1]
    server = await db.get_server(server_name)

    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return

    services = await db.get_server_services(server_name)

    if not services and not server.location:
        await callback.message.edit_text(
            f"🗺️ <b>Карта {server_name}</b>\n\n"
            "ℹ️ Информация о сервере ещё не заполнена.\n\n"
            f"📍 Host: <code>{server.host}</code>\n"
            f"👤 User: {server.username}\n\n"
            "Используйте /setmap для настройки.",
            reply_markup=server_actions_keyboard(server_name),
            parse_mode="HTML"
        )
    else:
        text = format_server_map(server, services)
        await callback.message.edit_text(
            text,
            reply_markup=server_actions_keyboard(server_name),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "add_server")
async def cb_add_server(callback: CallbackQuery, state: FSMContext):
    """Start adding a server"""
    await state.set_state(AddServerStates.name)
    await callback.message.edit_text(
        "➕ <b>Добавление сервера</b>\n\n"
        "Введите имя сервера (например: production, dev-1):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    """Show settings menu"""
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ============== FSM Handlers for Adding Server ==============

@router.message(AddServerStates.name)
async def add_server_name(message: Message, state: FSMContext):
    """Process server name"""
    name = message.text.strip()
    
    # Check if exists
    existing = await db.get_server(name)
    if existing:
        await message.answer("❌ Сервер с таким именем уже существует. Введите другое имя:")
        return
    
    await state.update_data(name=name)
    await state.set_state(AddServerStates.host)
    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\n"
        "Введите хост (IP или домен).\n"
        "Для текущего сервера введите: localhost",
        parse_mode="HTML"
    )


@router.message(AddServerStates.host)
async def add_server_host(message: Message, state: FSMContext):
    """Process server host"""
    host = message.text.strip()
    await state.update_data(host=host)
    await state.set_state(AddServerStates.port)
    await message.answer(
        f"✅ Хост: <b>{host}</b>\n\n"
        "Введите SSH порт (по умолчанию 22).\n"
        "Нажмите /skip для порта по умолчанию.",
        parse_mode="HTML"
    )


@router.message(AddServerStates.port)
async def add_server_port(message: Message, state: FSMContext):
    """Process server port"""
    if message.text == "/skip":
        port = 22
    else:
        try:
            port = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Введите число или /skip")
            return
    
    await state.update_data(port=port)
    await state.set_state(AddServerStates.username)
    await message.answer(
        f"✅ Порт: <b>{port}</b>\n\n"
        "Введите имя пользователя SSH (по умолчанию root).\n"
        "Нажмите /skip для root.",
        parse_mode="HTML"
    )


@router.message(AddServerStates.username)
async def add_server_username(message: Message, state: FSMContext):
    """Process username and save server"""
    if message.text == "/skip":
        username = "root"
    else:
        username = message.text.strip()
    
    data = await state.get_data()
    
    # Create server
    server = Server(
        id=None,
        name=data["name"],
        host=data["host"],
        port=data["port"],
        username=username
    )
    
    try:
        await db.add_server(server)
        await state.clear()
        
        await message.answer(
            f"✅ <b>Сервер добавлен!</b>\n\n"
            f"📍 {server.name}\n"
            f"🌐 {server.host}:{server.port}\n"
            f"👤 {server.username}\n\n"
            "Хотите проверить подключение?",
            reply_markup=server_actions_keyboard(server.name),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ============== Helper Functions ==============

async def check_server_by_name(message: Message, server_name: str):
    """Check server by name and send report"""
    server = await db.get_server(server_name)
    
    if not server:
        await message.answer(f"❌ Сервер '{server_name}' не найден")
        return
    
    await message.answer(f"🔄 Проверяю {server_name}...")
    
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
        
        await db.update_last_check(server_name, report.overall_status)

        text = format_full_report(report, server)
        await message.answer(
            text,
            reply_markup=report_actions_keyboard(server_name),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error checking {server_name}: {e}")
        await message.answer(f"❌ Ошибка проверки: {str(e)}")
