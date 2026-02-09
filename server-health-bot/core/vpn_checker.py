"""
VPN Status Checker - проверка статуса VPN сервисов на серверах
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import asyncssh

logger = logging.getLogger(__name__)

# Состояние DPI-блокировок (in-memory)
_dpi_state: dict[str, bool] = {}  # server_name -> is_blocked


@dataclass
class VPNStatus:
    """Статус VPN сервиса"""
    server_name: str
    server_host: str
    is_running: bool
    active_connections: int
    protocol: str  # "xray", "marzban", etc.
    port: int
    error: Optional[str] = None


@dataclass
class VPNLink:
    """VPN ссылка для подключения"""
    name: str
    protocol: str  # "vless", "ss2022", etc.
    link: str
    server: str


def _load_vpn_config() -> dict:
    """Load VPN server configuration from vpn_config.json"""
    config_paths = [
        Path(__file__).parent.parent / "vpn_config.json",
        Path("/opt/server-health-bot/vpn_config.json"),
    ]
    for path in config_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                logger.info(f"Loaded VPN config from {path}")
                return json.load(f)
    logger.warning("vpn_config.json not found, VPN features disabled")
    return {}


# Конфигурация VPN серверов (загружается из vpn_config.json)
VPN_SERVERS = _load_vpn_config()


async def _execute_direct(host: str, user: str, key_path: str,
                          command: str, timeout: int = 15) -> tuple[bool, str]:
    """Выполнить команду напрямую на сервере"""
    expanded_key = os.path.expanduser(key_path)
    try:
        async with asyncssh.connect(
            host,
            username=user,
            client_keys=[expanded_key],
            known_hosts=None,
            connect_timeout=timeout
        ) as conn:
            result = await conn.run(command, timeout=timeout)
            return True, result.stdout.strip()
    except Exception as e:
        logger.error(f"SSH error to {host}: {e}")
        return False, str(e)


async def _execute_via_proxy(proxy_host: str, proxy_user: str, proxy_key: str,
                              target_host: str, target_user: str, target_key: str,
                              command: str, timeout: int = 15) -> tuple[bool, str]:
    """Выполнить команду на удалённом сервере через прокси"""
    expanded_key = os.path.expanduser(proxy_key)
    try:
        # Подключаемся к прокси серверу
        async with asyncssh.connect(
            proxy_host,
            username=proxy_user,
            client_keys=[expanded_key],
            known_hosts=None,
            connect_timeout=timeout
        ) as proxy_conn:
            # Формируем команду для выполнения на целевом сервере
            ssh_cmd = f"ssh -i {target_key} -o StrictHostKeyChecking=no {target_user}@{target_host} '{command}'"
            result = await proxy_conn.run(ssh_cmd, timeout=timeout)
            return True, result.stdout.strip()
    except Exception as e:
        logger.error(f"SSH error via proxy to {target_host}: {e}")
        return False, str(e)


async def check_vpn_status(server_name: str) -> VPNStatus:
    """Проверить статус VPN на сервере"""
    if server_name not in VPN_SERVERS:
        return VPNStatus(
            server_name=server_name,
            server_host="unknown",
            is_running=False,
            active_connections=0,
            protocol="unknown",
            port=0,
            error=f"Сервер {server_name} не настроен"
        )

    config = VPN_SERVERS[server_name]
    proxy = config.get("ssh_via")
    is_direct = config.get("ssh_direct", False)

    # Проверяем, запущен ли XRay
    services_running = []
    for service in config["services"]:
        if is_direct:
            # Прямое подключение к серверу
            success, output = await _execute_direct(
                host=config["host"],
                user=config["user"],
                key_path=config["key_path"],
                command=service["check_cmd"]
            )
        elif proxy:
            # Подключение через прокси
            success, output = await _execute_via_proxy(
                proxy_host=proxy["host"],
                proxy_user=proxy["user"],
                proxy_key=proxy["key_path"],
                target_host=config["host"],
                target_user=config["user"],
                target_key=config["key_path"],
                command=service["check_cmd"]
            )
        else:
            success, output = False, "SSH not configured"

        if success and output:
            services_running.append(service["name"])

    # Получаем количество активных подключений
    active_connections = 0
    if services_running:
        if is_direct:
            success, output = await _execute_direct(
                host=config["host"],
                user=config["user"],
                key_path=config["key_path"],
                command=config["connections_cmd"]
            )
        elif proxy:
            success, output = await _execute_via_proxy(
                proxy_host=proxy["host"],
                proxy_user=proxy["user"],
                proxy_key=proxy["key_path"],
                target_host=config["host"],
                target_user=config["user"],
                target_key=config["key_path"],
                command=config["connections_cmd"]
            )
        else:
            success, output = False, ""

        if success:
            try:
                active_connections = int(output.strip())
            except ValueError:
                active_connections = 0

    is_running = len(services_running) > 0

    return VPNStatus(
        server_name=server_name,
        server_host=config["host"],
        is_running=is_running,
        active_connections=active_connections,
        protocol="xray" if is_running else "none",
        port=443,
        error=None if is_running else "VPN не запущен"
    )


async def check_all_vpn_servers() -> list[VPNStatus]:
    """Проверить статус всех VPN серверов"""
    statuses = []
    for server_name in VPN_SERVERS:
        status = await check_vpn_status(server_name)
        statuses.append(status)
    return statuses


def get_vpn_links(server_name: str = None) -> list[VPNLink]:
    """Получить VPN ссылки для подключения"""
    links = []

    servers = [server_name] if server_name else VPN_SERVERS.keys()

    for name in servers:
        if name not in VPN_SERVERS:
            continue
        config = VPN_SERVERS[name]
        for link_config in config.get("links", []):
            links.append(VPNLink(
                name=link_config["name"],
                protocol=link_config["protocol"],
                link=link_config["link"],
                server=name
            ))

    return links


def get_all_vpn_links_text() -> str:
    """Получить текст со всеми VPN ссылками"""
    lines = ["🔐 <b>VPN Ссылки для подключения:</b>", ""]

    for server_name, config in VPN_SERVERS.items():
        flag = {"Finland": "🇫🇮", "USA": "🇺🇸", "Russia": "🇷🇺"}.get(server_name, "🌐")
        lines.append(f"{flag} <b>{server_name}</b> ({config['host']})")

        for link in config.get("links", []):
            lines.append(f"• {link['name']}:")
            lines.append(f"<code>{link['link']}</code>")
            lines.append("")

    return "\n".join(lines)


# ==================== DPI Monitoring ====================

@dataclass
class DPICheckResult:
    """Результат проверки DPI-блокировки"""
    server_name: str
    host: str
    port: int
    is_blocked: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    # Relay check
    relay_ok: Optional[bool] = None
    relay_latency_ms: Optional[float] = None
    relay_port: Optional[int] = None


async def check_dpi_for_server(server_name: str) -> Optional[DPICheckResult]:
    """Проверить DPI-блокировку для сервера через TCP-connect с России"""
    config = VPN_SERVERS.get(server_name)
    if not config or "dpi_check" not in config:
        return None

    dpi = config["dpi_check"]
    host = dpi["host"]
    port = dpi["port"]

    # Проверяем TCP-подключение к серверу с Russia
    russia = VPN_SERVERS["Russia"]
    check_cmd = (
        f"timeout 10 bash -c '"
        f"start=$(date +%s%N); "
        f"echo | openssl s_client -connect {host}:{port} "
        f"-servername www.microsoft.com -verify_quiet 2>/dev/null && "
        f"end=$(date +%s%N); "
        f"echo OK $(( (end - start) / 1000000 ))ms"
        f"' 2>/dev/null || echo BLOCKED"
    )

    relay_port = dpi.get("relay_port")

    try:
        success, output = await _execute_direct(
            host=russia["host"],
            user=russia["user"],
            key_path=russia["key_path"],
            command=check_cmd,
            timeout=15
        )

        if success and output.startswith("OK"):
            parts = output.split()
            latency = None
            if len(parts) > 1:
                try:
                    latency = float(parts[1].replace("ms", ""))
                except ValueError:
                    pass
            result = DPICheckResult(
                server_name=server_name,
                host=host, port=port,
                is_blocked=False,
                latency_ms=latency,
                relay_port=relay_port
            )
        else:
            result = DPICheckResult(
                server_name=server_name,
                host=host, port=port,
                is_blocked=True,
                error=output[:100] if output else "Connection failed",
                relay_port=relay_port
            )
    except Exception as e:
        logger.error(f"DPI check error for {server_name}: {e}")
        result = DPICheckResult(
            server_name=server_name,
            host=host, port=port,
            is_blocked=True,
            error=str(e)[:100],
            relay_port=relay_port
        )

    # Check relay connectivity FROM Russia to localhost:relay_port
    # This is the actual client path: Client → Russia:relay_port → (DNAT) → target:443
    if relay_port:
        try:
            relay_cmd = (
                f"timeout 10 bash -c '"
                f"start=$(date +%s%N); "
                f"echo | openssl s_client -connect 127.0.0.1:{relay_port} "
                f"-servername www.microsoft.com -verify_quiet 2>/dev/null && "
                f"end=$(date +%s%N); "
                f"echo OK $(( (end - start) / 1000000 ))ms"
                f"' 2>/dev/null || echo FAIL"
            )
            r_success, r_output = await _execute_direct(
                host=russia["host"],
                user=russia["user"],
                key_path=russia["key_path"],
                command=relay_cmd,
                timeout=15
            )
            if r_success and "OK" in r_output:
                result.relay_ok = True
                # Parse relay latency
                parts = r_output.split()
                if len(parts) > 1:
                    try:
                        result.relay_latency_ms = float(parts[1].replace("ms", ""))
                    except ValueError:
                        pass
            else:
                result.relay_ok = False
        except Exception as e:
            logger.error(f"Relay check error for {server_name}: {e}")
            result.relay_ok = False

    return result


async def check_all_dpi() -> list[DPICheckResult]:
    """Проверить DPI-блокировки для всех серверов"""
    results = []
    for name, config in VPN_SERVERS.items():
        if "dpi_check" in config:
            result = await check_dpi_for_server(name)
            if result:
                results.append(result)
    return results


def get_dpi_state() -> dict[str, bool]:
    """Получить текущее состояние DPI-блокировок"""
    return dict(_dpi_state)


def update_dpi_state(server_name: str, is_blocked: bool) -> Optional[str]:
    """Обновить состояние DPI и вернуть тип изменения если есть.
    Returns: 'blocked', 'unblocked', or None (no change)
    """
    prev = _dpi_state.get(server_name)
    _dpi_state[server_name] = is_blocked

    if prev is None:
        # Первая проверка — не алертим, только инициализируем
        return None
    if prev != is_blocked:
        return "blocked" if is_blocked else "unblocked"
    return None


def format_dpi_alert(result: DPICheckResult, change_type: str) -> str:
    """Форматировать алерт о DPI-блокировке"""
    flag = {"Finland": "🇫🇮", "USA": "🇺🇸"}.get(result.server_name, "🌐")
    config = VPN_SERVERS.get(result.server_name, {})
    relay_port = config.get("dpi_check", {}).get("relay_port")

    if change_type == "blocked":
        lines = [
            f"🚫 <b>DPI БЛОКИРОВКА: {flag} {result.server_name}</b>",
            "",
            f"Прямое подключение к <code>{result.host}:{result.port}</code> заблокировано ТСПУ.",
            "",
            "🔄 <b>Используй relay через Россию:</b>",
        ]
        # Найти relay-ссылку
        for link in config.get("links", []):
            if "через Россию" in link.get("name", ""):
                lines.append(f"<code>{link['link']}</code>")
                break
        if relay_port:
            russia_host = VPN_SERVERS.get("Russia", {}).get("host", "?")
            lines.append(f"\n📡 Relay: <code>{russia_host}:{relay_port}</code> → <code>{result.host}:{result.port}</code>")
    else:
        lines = [
            f"✅ <b>DPI разблокировка: {flag} {result.server_name}</b>",
            "",
            f"Прямое подключение к <code>{result.host}:{result.port}</code> восстановлено.",
            "Можно переключиться на прямой профиль.",
        ]

    return "\n".join(lines)


def format_dpi_status_report(results: list[DPICheckResult]) -> str:
    """Форматировать отчёт о статусе DPI"""
    lines = ["🛡 <b>DPI Мониторинг (ТСПУ):</b>", ""]
    for r in results:
        flag = {"Finland": "🇫🇮", "USA": "🇺🇸"}.get(r.server_name, "🌐")

        # Direct connection status
        if r.is_blocked:
            direct = "🚫 Заблокирован"
        else:
            latency = f" ({r.latency_ms:.0f}ms)" if r.latency_ms else ""
            direct = f"✅ Доступен{latency}"

        # Relay status
        if r.relay_port and r.relay_ok is not None:
            if r.relay_ok:
                relay_lat = f" ({r.relay_latency_ms:.0f}ms)" if r.relay_latency_ms else ""
                relay = f"✅ Работает (:{r.relay_port}){relay_lat}"
            else:
                relay = f"❌ Не работает (:{r.relay_port})"
        else:
            relay = "—"

        lines.append(f"{flag} <b>{r.server_name}</b>")
        lines.append(f"  Прямой: {direct}")
        lines.append(f"  Relay:  {relay}")
        lines.append("")

    return "\n".join(lines)
