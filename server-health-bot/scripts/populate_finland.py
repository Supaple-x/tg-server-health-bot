"""
Script to populate Finland server data
Run once to add server metadata and services
"""
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path and change to it for .env loading
project_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_dir))
os.chdir(project_dir)

from database.db import db, Server, ServerService


async def populate_finland_server():
    """Populate Finland server (65.109.142.30) with metadata and services"""

    # Initialize database
    await db.init()

    # Get server or create it
    server = await db.get_server("Finland")

    if not server:
        print("Server 'Finland' not found. Creating...")
        # Create server
        new_server = Server(
            id=None,
            name="Finland",
            host="65.109.142.30",
            port=22,
            username="root",
            key_path="~/.ssh/id_ed25519"
        )
        server_id = await db.add_server(new_server)
        server = await db.get_server("Finland")
        print(f"Created server with ID: {server_id}")

    print(f"Found server: {server.name} ({server.host})")

    # Update server metadata
    await db.update_server_metadata(
        name="Finland",
        location="Finland, Hetzner",
        description="VPN & Media Bot Server",
        cpu_cores=2,
        ram_gb=1.9,
        disk_gb=38
    )
    print("Updated server metadata")

    # Clear existing services
    await db.delete_server_services("Finland")
    print("Cleared existing services")

    # Add services
    services = [
        ServerService(
            id=None,
            server_id=server.id,
            name="Xray",
            service_type="vpn",
            description="VPN-прокси (VLESS protocol)",
            port="443",
            status="active",
            cpu_percent=1.3,
            ram_mb=26,
            disk_mb=0.016,
            config_path="/usr/local/etc/xray/config.json",
            systemd_name="xray.service"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="AdGuard Home",
            service_type="dns",
            description="DNS с блокировкой рекламы",
            port="53,80,853,8443",
            status="active",
            cpu_percent=1.0,
            ram_mb=122,
            disk_mb=399,
            config_path="/opt/AdGuardHome/AdGuardHome.yaml",
            systemd_name="AdGuardHome.service"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="Telegram Cover Bot",
            service_type="bot",
            description="Скачивание медиа (YouTube, VK, Yandex)",
            port=None,
            status="active",
            cpu_percent=0,
            ram_mb=15,
            disk_mb=235,
            config_path="/opt/telegram-cover-bot/.env",
            systemd_name="telegram-cover-bot.service"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="Telegram Bot API",
            service_type="api",
            description="Локальный API (файлы до 2GB)",
            port="8081",
            status="active",
            cpu_percent=1.0,
            ram_mb=8,
            disk_mb=50,
            docker_name="telegram-bot-api"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="BGUtil Provider",
            service_type="media",
            description="YouTube PoT для обхода защиты",
            port="4416",
            status="active",
            cpu_percent=0,
            ram_mb=5,
            disk_mb=20,
            docker_name="bgutil-provider"
        ),
    ]

    for svc in services:
        await db.add_service(svc)
        print(f"Added service: {svc.name}")

    print("\nFinland server data populated successfully!")

    # Verify
    services = await db.get_server_services("Finland")
    print(f"\nTotal services: {len(services)}")
    for s in services:
        print(f"  - {s.name} ({s.service_type})")


if __name__ == "__main__":
    asyncio.run(populate_finland_server())
