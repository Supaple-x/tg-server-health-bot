"""
Script to populate Russia server data
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


async def populate_russia_server():
    """Populate Russia server (176.108.251.49) with metadata and services"""

    # Initialize database
    await db.init()

    # Get server or create it
    server = await db.get_server("Russia")

    if not server:
        print("Server 'Russia' not found. Creating...")
        # Create server
        new_server = Server(
            id=None,
            name="Russia",
            host="176.108.251.49",
            port=22,
            username="artemfcsm",
            key_path="~/.ssh/id_ed25519"
        )
        server_id = await db.add_server(new_server)
        server = await db.get_server("Russia")
        print(f"Created server with ID: {server_id}")

    print(f"Found server: {server.name} ({server.host})")

    # Update server metadata
    await db.update_server_metadata(
        name="Russia",
        location="Russia, Moscow (Cloud.ru)",
        description="Monitoring Bot Server",
        cpu_cores=2,
        ram_gb=2,
        disk_gb=10
    )
    print("Updated server metadata")

    # Clear existing services
    await db.delete_server_services("Russia")
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
            ram_mb=150,
            disk_mb=50,
            config_path="/opt/server-health-bot/.env",
            systemd_name="server-health-bot.service"
        ),
    ]

    for svc in services:
        await db.add_service(svc)
        print(f"Added service: {svc.name}")

    print("\nRussia server data populated successfully!")

    # Verify
    services = await db.get_server_services("Russia")
    print(f"\nTotal services: {len(services)}")
    for s in services:
        print(f"  - {s.name} ({s.service_type})")


if __name__ == "__main__":
    asyncio.run(populate_russia_server())
