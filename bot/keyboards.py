"""
Telegram inline keyboards
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


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


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статус всех", callback_data="status_all"),
        InlineKeyboardButton(text="🧹 Оптимизировать все", callback_data="optimize_all")
    )
    builder.row(
        InlineKeyboardButton(text="🖥 Серверы", callback_data="servers_list"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    )
    return builder.as_markup()


def servers_list_keyboard(servers: list, action: str = "check") -> InlineKeyboardMarkup:
    """Keyboard with list of servers"""
    builder = InlineKeyboardBuilder()

    for server in servers:
        status_emoji = {
            "ok": "🟢",
            "warning": "🟡",
            "critical": "🔴",
            None: "⚪"
        }.get(server.last_status, "⚪")
        flag = COUNTRY_FLAGS.get(server.name, "🌐")

        builder.row(InlineKeyboardButton(
            text=f"{status_emoji} {flag} {server.name}",
            callback_data=f"{action}:{server.name}"
        ))

    builder.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data="add_server"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )
    return builder.as_markup()


def server_actions_keyboard(server_name: str) -> InlineKeyboardMarkup:
    """Actions for a specific server"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔍 Полная проверка", callback_data=f"check:{server_name}"),
        InlineKeyboardButton(text="🗺️ Карта", callback_data=f"map:{server_name}")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Процессы", callback_data=f"processes:{server_name}"),
        InlineKeyboardButton(text="🛠 Оптимизация", callback_data=f"optimize:{server_name}")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit:{server_name}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{server_name}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="servers_list"))
    return builder.as_markup()


def report_actions_keyboard(server_name: str) -> InlineKeyboardMarkup:
    """Actions after viewing report"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"check:{server_name}"),
        InlineKeyboardButton(text="📊 Процессы", callback_data=f"processes:{server_name}")
    )
    builder.row(
        InlineKeyboardButton(text="🛠 Оптимизировать", callback_data=f"optimize:{server_name}"),
        InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")
    )
    return builder.as_markup()


def optimize_keyboard(server_name: str) -> InlineKeyboardMarkup:
    """Optimization options"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🧹 Очистить логи", callback_data=f"opt_logs:{server_name}"),
        InlineKeyboardButton(text="🗑 Очистить кэш", callback_data=f"opt_cache:{server_name}")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Очистить journal", callback_data=f"opt_journal:{server_name}"),
        InlineKeyboardButton(text="📦 Удалить старые пакеты", callback_data=f"opt_packages:{server_name}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"server:{server_name}"))
    return builder.as_markup()


def confirm_keyboard(action: str, server_name: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, выполнить", callback_data=f"confirm_{action}:{server_name}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"server:{server_name}")
    )
    return builder.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    """Settings menu"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏰ Расписание", callback_data="schedule_settings"),
        InlineKeyboardButton(text="🔔 Алерты", callback_data="alert_settings")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Пороги", callback_data="threshold_settings"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )
    return builder.as_markup()


def schedule_keyboard(current_interval: int) -> InlineKeyboardMarkup:
    """Schedule settings keyboard"""
    builder = InlineKeyboardBuilder()
    
    intervals = [1, 3, 6, 12, 24]
    for interval in intervals:
        emoji = "✅" if interval == current_interval else ""
        builder.button(
            text=f"{emoji} {interval}ч",
            callback_data=f"set_interval:{interval}"
        )
    
    builder.adjust(5)
    builder.row(
        InlineKeyboardButton(text="⏸ Выкл", callback_data="set_interval:0"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="settings")
    )
    return builder.as_markup()
