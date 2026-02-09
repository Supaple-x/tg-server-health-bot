"""
Database models and CRUD operations for server management
"""
import aiosqlite
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from pathlib import Path

from config import settings


@dataclass
class Server:
    """Server configuration"""
    id: Optional[int]
    name: str
    host: str
    port: int = 22
    username: str = "root"
    key_path: Optional[str] = None
    password: Optional[str] = None  # Encrypted in real implementation
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_check: Optional[datetime] = None
    last_status: Optional[str] = None
    # Metadata
    location: Optional[str] = None  # e.g., "Finland", "USA"
    description: Optional[str] = None  # e.g., "VPN & Media Bot Server"
    cpu_cores: Optional[int] = None
    ram_gb: Optional[float] = None
    disk_gb: Optional[float] = None


@dataclass
class ServerService:
    """Service running on a server"""
    id: Optional[int]
    server_id: int
    name: str  # e.g., "xray", "AdGuard Home"
    service_type: str  # e.g., "vpn", "dns", "bot", "api", "docker"
    description: str  # e.g., "VPN-прокси (VLESS protocol)"
    port: Optional[str] = None  # e.g., "443", "53,80,853"
    status: str = "active"  # active, stopped, unknown
    cpu_percent: Optional[float] = None
    ram_mb: Optional[float] = None
    disk_mb: Optional[float] = None
    config_path: Optional[str] = None  # e.g., "/usr/local/etc/xray/config.json"
    systemd_name: Optional[str] = None  # e.g., "xray.service"
    docker_name: Optional[str] = None  # for docker containers


class Database:
    """Database manager for server configurations"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.database_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def init(self):
        """Initialize database schema"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER DEFAULT 22,
                    username TEXT DEFAULT 'root',
                    key_path TEXT,
                    password TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check TIMESTAMP,
                    last_status TEXT
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS check_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    cpu_load REAL,
                    ram_percent REAL,
                    disk_percent REAL,
                    issues TEXT,
                    FOREIGN KEY (server_id) REFERENCES servers(id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Server services table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    description TEXT,
                    port TEXT,
                    status TEXT DEFAULT 'active',
                    cpu_percent REAL,
                    ram_mb REAL,
                    disk_mb REAL,
                    config_path TEXT,
                    systemd_name TEXT,
                    docker_name TEXT,
                    FOREIGN KEY (server_id) REFERENCES servers(id),
                    UNIQUE(server_id, name)
                )
            """)

            # Add metadata columns to servers if not exist
            try:
                await db.execute("ALTER TABLE servers ADD COLUMN location TEXT")
            except:
                pass
            try:
                await db.execute("ALTER TABLE servers ADD COLUMN description TEXT")
            except:
                pass
            try:
                await db.execute("ALTER TABLE servers ADD COLUMN cpu_cores INTEGER")
            except:
                pass
            try:
                await db.execute("ALTER TABLE servers ADD COLUMN ram_gb REAL")
            except:
                pass
            try:
                await db.execute("ALTER TABLE servers ADD COLUMN disk_gb REAL")
            except:
                pass

            await db.commit()
    
    async def add_server(self, server: Server) -> int:
        """Add a new server"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO servers (name, host, port, username, key_path, password)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (server.name, server.host, server.port, server.username, 
                  server.key_path, server.password))
            await db.commit()
            return cursor.lastrowid
    
    async def get_server(self, name: str) -> Optional[Server]:
        """Get server by name"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM servers WHERE name = ?", (name,)
            )
            row = await cursor.fetchone()
            if row:
                return Server(**dict(row))
            return None
    
    async def get_server_by_id(self, server_id: int) -> Optional[Server]:
        """Get server by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM servers WHERE id = ?", (server_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Server(**dict(row))
            return None
    
    async def get_all_servers(self, active_only: bool = True) -> list[Server]:
        """Get all servers"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM servers"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY name"
            
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            return [Server(**dict(row)) for row in rows]
    
    async def update_server(self, server: Server) -> bool:
        """Update server configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE servers 
                SET host = ?, port = ?, username = ?, key_path = ?, 
                    password = ?, is_active = ?
                WHERE name = ?
            """, (server.host, server.port, server.username, server.key_path,
                  server.password, server.is_active, server.name))
            await db.commit()
            return True
    
    async def update_last_check(self, name: str, status: str) -> bool:
        """Update last check timestamp and status"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE servers 
                SET last_check = CURRENT_TIMESTAMP, last_status = ?
                WHERE name = ?
            """, (status, name))
            await db.commit()
            return True
    
    async def delete_server(self, name: str) -> bool:
        """Delete server by name"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM servers WHERE name = ?", (name,))
            await db.commit()
            return True
    
    async def add_check_history(
        self, 
        server_id: int, 
        status: str,
        cpu_load: float,
        ram_percent: float,
        disk_percent: float,
        issues: str
    ):
        """Add check to history"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO check_history 
                (server_id, status, cpu_load, ram_percent, disk_percent, issues)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (server_id, status, cpu_load, ram_percent, disk_percent, issues))
            await db.commit()
    
    async def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    
    async def set_setting(self, key: str, value: str):
        """Set a setting value"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
            """, (key, value))
            await db.commit()

    # ============== Server Metadata ==============

    async def update_server_metadata(
        self,
        name: str,
        location: str = None,
        description: str = None,
        cpu_cores: int = None,
        ram_gb: float = None,
        disk_gb: float = None
    ) -> bool:
        """Update server metadata"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE servers
                SET location = COALESCE(?, location),
                    description = COALESCE(?, description),
                    cpu_cores = COALESCE(?, cpu_cores),
                    ram_gb = COALESCE(?, ram_gb),
                    disk_gb = COALESCE(?, disk_gb)
                WHERE name = ?
            """, (location, description, cpu_cores, ram_gb, disk_gb, name))
            await db.commit()
            return True

    # ============== Server Services ==============

    async def add_service(self, service: ServerService) -> int:
        """Add a service to a server"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT OR REPLACE INTO server_services
                (server_id, name, service_type, description, port, status,
                 cpu_percent, ram_mb, disk_mb, config_path, systemd_name, docker_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (service.server_id, service.name, service.service_type,
                  service.description, service.port, service.status,
                  service.cpu_percent, service.ram_mb, service.disk_mb,
                  service.config_path, service.systemd_name, service.docker_name))
            await db.commit()
            return cursor.lastrowid

    async def get_server_services(self, server_name: str) -> list[ServerService]:
        """Get all services for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT ss.* FROM server_services ss
                JOIN servers s ON ss.server_id = s.id
                WHERE s.name = ?
                ORDER BY ss.service_type, ss.name
            """, (server_name,))
            rows = await cursor.fetchall()
            return [ServerService(**dict(row)) for row in rows]

    async def delete_server_services(self, server_name: str) -> bool:
        """Delete all services for a server"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                DELETE FROM server_services
                WHERE server_id = (SELECT id FROM servers WHERE name = ?)
            """, (server_name,))
            await db.commit()
            return True


# Global database instance
db = Database()
