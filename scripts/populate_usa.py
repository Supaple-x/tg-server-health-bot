"""
Script to populate USA server data
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


async def populate_usa_server():
    """Populate USA server (178.156.167.178) with metadata and services"""

    # Initialize database
    await db.init()

    # Get server or create it
    server = await db.get_server("USA")

    if not server:
        print("Server 'USA' not found. Creating...")
        # Create server
        new_server = Server(
            id=None,
            name="USA",
            host="178.156.167.178",
            port=22,
            username="root",
            key_path="~/.ssh/id_ed25519"
        )
        server_id = await db.add_server(new_server)
        server = await db.get_server("USA")
        print(f"Created server with ID: {server_id}")

    print(f"Found server: {server.name} ({server.host})")

    # Update server metadata
    await db.update_server_metadata(
        name="USA",
        location="USA, Virginia (Ashburn)",
        description="Monitoring & AI Agent Server",
        cpu_cores=2,
        ram_gb=1.9,
        disk_gb=38
    )
    print("Updated server metadata")

    # Clear existing services
    await db.delete_server_services("USA")
    print("Cleared existing services")

    # Add services
    services = [
        ServerService(
            id=None,
            server_id=server.id,
            name="Server Health Bot",
            service_type="monitoring",
            description="Мониторинг здоровья серверов",
            port=None,
            status="active",
            cpu_percent=0,
            ram_mb=174,
            disk_mb=69,
            config_path="/opt/server-health-bot/.env",
            systemd_name="server-health-bot.service"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="Telegram AI Agent",
            service_type="bot",
            description="AI-агент для Telegram",
            port=None,
            status="active",
            cpu_percent=0.5,
            ram_mb=216,
            disk_mb=189,
            config_path="/opt/telegram_ai_agent/.env",
            systemd_name="telegram-ai-agent.service"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="Telegram Bot Manager",
            service_type="bot",
            description="Менеджер Telegram ботов",
            port=None,
            status="active",
            cpu_percent=0,
            ram_mb=119,
            disk_mb=0,
            systemd_name="telegram-bot-manager.service"
        ),
        ServerService(
            id=None,
            server_id=server.id,
            name="Xray",
            service_type="vpn",
            description="VPN-прокси (VLESS protocol)",
            port="443",
            status="active",
            cpu_percent=0,
            ram_mb=35,
            disk_mb=0.016,
            config_path="/usr/local/etc/xray/config.json",
            systemd_name="xray.service"
        ),
    ]

    for svc in services:
        await db.add_service(svc)
        print(f"Added service: {svc.name}")

    print("\nUSA server data populated successfully!")

    # Verify
    services = await db.get_server_services("USA")
    print(f"\nTotal services: {len(services)}")
    for s in services:
        print(f"  - {s.name} ({s.service_type})")


if __name__ == "__main__":
    asyncio.run(populate_usa_server())
