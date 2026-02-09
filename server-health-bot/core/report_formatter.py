"""
Report Formatter - formats health reports for Telegram
"""
from typing import Optional
from core.health_checker import HealthReport, Metric
from database.db import Server, ServerService


def status_emoji(status: str) -> str:
    """Get emoji for status"""
    return {
        "ok": "🟢",
        "warning": "🟡",
        "critical": "🔴",
        "error": "⚪"
    }.get(status, "⚪")


def progress_bar(value: float, width: int = 10) -> str:
    """Create a text progress bar"""
    filled = int(value / 100 * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def format_metric_line(metric: Metric, show_bar: bool = True) -> str:
    """Format a single metric line"""
    emoji = status_emoji(metric.status)
    if show_bar and metric.unit == "%":
        bar = progress_bar(metric.value)
        return f"├ {metric.name}: {bar} {metric.value}% {emoji}"
    else:
        return f"├ {metric.name}: {metric.value}{metric.unit} {emoji}"


def format_short_report(report: HealthReport) -> str:
    """Format a short status report"""
    emoji = status_emoji(report.overall_status)

    status_text = {
        "ok": "Всё в порядке",
        "warning": "Требует внимания",
        "critical": "Критическое состояние",
        "error": "Ошибка проверки"
    }.get(report.overall_status, "Неизвестно")

    lines = [
        f"🖥 <b>{report.server_name}</b>",
        f"{emoji} {status_text}",
        "",
        f"💻 CPU: {report.cpu_load.value} ({report.cpu_load_per_core}/core) {status_emoji(report.cpu_load.status)}",
        f"🧠 RAM: {report.ram.value}% {status_emoji(report.ram.status)}",
    ]

    # Add disk with worst status
    if report.disks:
        worst_disk = max(report.disks, key=lambda d: d.value)
        lines.append(f"💾 Disk: {worst_disk.value}% {status_emoji(worst_disk.status)}")

    # Sessions
    lines.append(f"👥 Sessions: {int(report.sessions.value)} {status_emoji(report.sessions.status)}")

    return "\n".join(lines)


def format_full_report(report: HealthReport, server: Server = None) -> str:
    """Format a full detailed report for Telegram"""
    emoji = status_emoji(report.overall_status)
    flag = COUNTRY_FLAGS.get(report.server_name, "🌐")

    status_text = {
        "ok": "Хорошее",
        "warning": "Требует внимания",
        "critical": "Критическое",
        "error": "Ошибка проверки"
    }.get(report.overall_status, "Неизвестно")

    lines = [
        f"{flag} <b>Server:</b> {report.server_name}",
    ]
    if server:
        lines.append(f"🌐 <b>IP:</b> <code>{server.host}</code>")
    lines.extend([
        f"📅 {report.timestamp.strftime('%Y-%m-%d %H:%M')} UTC",
        f"⏱ {report.uptime}",
        "",
        f"📊 <b>Общее состояние:</b> {emoji} {status_text}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "💻 <b>Ресурсы:</b>",
    ])

    # CPU (load per core as percentage)
    cpu_pct = min(report.cpu_load_per_core * 100, 100)
    cpu_bar = progress_bar(cpu_pct)
    lines.append(f"├ CPU:  {cpu_bar} {cpu_pct:.0f}% {status_emoji(report.cpu_load.status)}")
    lines.append(f"│       Load: {report.cpu_load.value} {report.cpu_load.unit}")

    # RAM
    ram_bar = progress_bar(report.ram.value)
    lines.append(f"├ RAM:  {ram_bar} {report.ram.value}% {status_emoji(report.ram.status)}")
    if report.ram.details:
        lines.append(f"│       {report.ram.details}")

    # Swap
    swap_bar = progress_bar(report.swap.value)
    lines.append(f"├ Swap: {swap_bar} {report.swap.value}% {status_emoji(report.swap.status)}")
    if report.swap.details and report.swap.value > 0:
        lines.append(f"│       {report.swap.details}")

    # Disks
    for i, disk in enumerate(report.disks):
        disk_bar = progress_bar(disk.value)
        disk_name = disk.name.replace("Disk ", "")
        lines.append(f"├ {disk_name}: {disk_bar} {disk.value}% {status_emoji(disk.status)}")
        if disk.details:
            lines.append(f"│       {disk.details}")

    # Sessions
    lines.append(f"├ 👥 Sessions: {int(report.sessions.value)} users {status_emoji(report.sessions.status)}")

    # Docker (if available)
    if report.docker:
        lines.append(f"├ 🐳 Docker: {report.docker.value}GB {status_emoji(report.docker.status)}")
        if report.docker.details:
            lines.append(f"│       {report.docker.details}")

    # Journal (if available)
    if report.journal_size:
        lines.append(f"└ 📋 Journal: {int(report.journal_size.value)}MB {status_emoji(report.journal_size.status)}")
    else:
        # Close the tree if no docker/journal
        pass

    # Issues
    if report.issues:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ <b>Проблемы:</b>")
        for issue in report.issues[:5]:  # Limit to 5
            lines.append(f"• {issue}")

    # Recommendations
    if report.recommendations:
        lines.append("")
        lines.append("💡 <b>Рекомендации:</b>")
        for rec in report.recommendations[:3]:  # Limit to 3
            lines.append(f"• {rec}")

    # Errors
    if report.errors:
        lines.append("")
        lines.append("❌ <b>Ошибки сбора:</b>")
        for err in report.errors[:3]:
            lines.append(f"• {err}")

    return "\n".join(lines)


def format_processes_report(report: HealthReport) -> str:
    """Format top processes report"""
    lines = [
        f"🖥 <b>{report.server_name}</b> — Top процессы",
        "",
        "🔥 <b>По CPU:</b>",
    ]

    for p in report.top_cpu_processes[:5]:
        lines.append(f"• {p.cpu}% | {p.user} | {p.command[:30]}")

    lines.append("")
    lines.append("🧠 <b>По памяти:</b>")

    for p in report.top_mem_processes[:5]:
        lines.append(f"• {p.mem}% | {p.user} | {p.command[:30]}")

    return "\n".join(lines)


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


def format_all_servers_summary(reports: list[HealthReport], servers: list = None, vpn_statuses: list = None) -> str:
    """Format summary of all servers with VPN status"""
    # Build server lookup by name
    server_lookup = {}
    if servers:
        server_lookup = {s.name: s for s in servers}

    lines = [
        "📊 <b>Статус всех серверов</b>",
        f"🕐 {reports[0].timestamp.strftime('%Y-%m-%d %H:%M')} UTC" if reports else "",
        "",
    ]

    # Sort by status priority
    status_order = {"critical": 0, "warning": 1, "error": 2, "ok": 3}
    sorted_reports = sorted(reports, key=lambda r: status_order.get(r.overall_status, 4))

    for report in sorted_reports:
        emoji = status_emoji(report.overall_status)
        flag = COUNTRY_FLAGS.get(report.server_name, "🌐")
        server = server_lookup.get(report.server_name)
        host = f"<code>{server.host}</code>" if server else ""

        lines.append(f"{emoji} {flag} {host} <b>{report.server_name}</b>")
        disk_val = f"{report.disks[0].value}%" if report.disks else "?"
        sessions_val = int(report.sessions.value) if report.sessions else 0
        lines.append(f"   CPU: {report.cpu_load.value} | RAM: {report.ram.value}% | Disk: {disk_val} | 👥 {sessions_val}")

    # Summary
    critical = sum(1 for r in reports if r.overall_status == "critical")
    warning = sum(1 for r in reports if r.overall_status == "warning")
    ok = sum(1 for r in reports if r.overall_status == "ok")

    lines.append("")
    lines.append(f"<b>Серверы:</b> 🔴 {critical} | 🟡 {warning} | 🟢 {ok}")

    # VPN Status
    if vpn_statuses:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔐 <b>VPN:</b>")

        for vpn in vpn_statuses:
            flag = COUNTRY_FLAGS.get(vpn.server_name, "🌐")
            status_icon = "🟢" if vpn.is_running else "🔴"
            conn_text = f"👥 {vpn.active_connections}" if vpn.is_running else "offline"
            lines.append(f"{status_icon} {flag} {vpn.server_name} ({vpn.server_host}) — {conn_text}")

        # VPN summary
        vpn_ok = sum(1 for v in vpn_statuses if v.is_running)
        vpn_down = sum(1 for v in vpn_statuses if not v.is_running)
        total_connections = sum(v.active_connections for v in vpn_statuses if v.is_running)

        lines.append(f"<b>VPN:</b> 🟢 {vpn_ok} | 🔴 {vpn_down} | 👥 {total_connections} подкл.")

    return "\n".join(lines)


def format_vpn_status(vpn_statuses: list) -> str:
    """Format VPN status report"""
    lines = [
        "🔐 <b>Статус VPN серверов</b>",
        "",
    ]

    for vpn in vpn_statuses:
        flag = COUNTRY_FLAGS.get(vpn.server_name, "🌐")
        status_icon = "🟢" if vpn.is_running else "🔴"
        status_text = "Работает" if vpn.is_running else "Не работает"

        lines.append(f"{flag} <b>{vpn.server_name}</b>")
        lines.append(f"   {status_icon} {status_text}")
        lines.append(f"   🌐 IP: <code>{vpn.server_host}</code>")
        lines.append(f"   🔌 Порт: {vpn.port}")

        if vpn.is_running:
            lines.append(f"   👥 Подключений: {vpn.active_connections}")
        elif vpn.error:
            lines.append(f"   ❌ {vpn.error}")

        lines.append("")

    # Summary
    vpn_ok = sum(1 for v in vpn_statuses if v.is_running)
    vpn_down = sum(1 for v in vpn_statuses if not v.is_running)
    total_connections = sum(v.active_connections for v in vpn_statuses if v.is_running)

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"<b>Итого:</b> 🟢 {vpn_ok} работает | 🔴 {vpn_down} не работает")
    lines.append(f"<b>Всего подключений:</b> {total_connections}")

    return "\n".join(lines)


def service_type_emoji(service_type: str) -> str:
    """Get emoji for service type"""
    return {
        "vpn": "🛡️",
        "dns": "🚫",
        "bot": "🤖",
        "api": "📡",
        "docker": "🐳",
        "media": "🎵",
        "database": "🗄️",
        "web": "🌐",
        "monitoring": "📊",
        "other": "⚙️"
    }.get(service_type, "⚙️")


def format_server_map(server: Server, services: list[ServerService]) -> str:
    """Format server map with all services"""
    lines = [
        f"🗺️ <b>Карта сервера: {server.name}</b>",
        "",
    ]

    # Server info
    if server.location:
        lines.append(f"📍 <b>Локация:</b> {server.location}")
    lines.append(f"🌐 <b>IP:</b> <code>{server.host}</code>")
    if server.description:
        lines.append(f"📝 {server.description}")

    # Resources
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💻 <b>Ресурсы:</b>")
    if server.cpu_cores:
        lines.append(f"├ CPU: {server.cpu_cores} cores")
    if server.ram_gb:
        lines.append(f"├ RAM: {server.ram_gb} GB")
    if server.disk_gb:
        lines.append(f"└ Disk: {server.disk_gb} GB")

    # Services grouped by type
    if services:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔧 <b>Сервисы:</b>")

        # Group services by type
        service_groups = {}
        for svc in services:
            if svc.service_type not in service_groups:
                service_groups[svc.service_type] = []
            service_groups[svc.service_type].append(svc)

        for svc_type, svc_list in service_groups.items():
            for svc in svc_list:
                emoji = service_type_emoji(svc.service_type)
                status_mark = "✅" if svc.status == "active" else "⏸️" if svc.status == "stopped" else "❓"

                lines.append(f"")
                lines.append(f"{emoji} <b>{svc.name}</b> {status_mark}")
                lines.append(f"   {svc.description}")

                details = []
                if svc.port:
                    details.append(f"Port: {svc.port}")
                if svc.cpu_percent is not None:
                    details.append(f"CPU: {svc.cpu_percent}%")
                if svc.ram_mb is not None:
                    details.append(f"RAM: {svc.ram_mb:.0f}MB")
                if svc.disk_mb is not None:
                    details.append(f"Disk: {svc.disk_mb:.0f}MB")

                if details:
                    lines.append(f"   {' | '.join(details)}")

                if svc.systemd_name:
                    lines.append(f"   <code>{svc.systemd_name}</code>")
                elif svc.docker_name:
                    lines.append(f"   🐳 <code>{svc.docker_name}</code>")

    # Ports summary
    ports = [svc.port for svc in services if svc.port]
    if ports:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔌 <b>Открытые порты:</b>")
        lines.append(f"   {', '.join(ports)}")

    return "\n".join(lines)


def format_server_map_short(server: Server, services: list[ServerService]) -> str:
    """Format short server map for inline display"""
    lines = [
        f"🗺️ <b>{server.name}</b>",
    ]

    if server.location:
        lines[0] += f" ({server.location})"

    if server.description:
        lines.append(f"   {server.description}")

    # Services list
    svc_names = [f"{service_type_emoji(s.service_type)} {s.name}" for s in services[:5]]
    if svc_names:
        lines.append(f"   {', '.join(svc_names)}")
        if len(services) > 5:
            lines.append(f"   ... +{len(services) - 5} сервисов")

    return "\n".join(lines)
