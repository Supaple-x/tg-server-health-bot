"""
Configuration module for Server Health Bot
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Telegram
    bot_token: str = Field(..., env="BOT_TOKEN")
    admin_id: int = Field(..., env="ADMIN_ID")
    
    # Database
    database_path: str = Field("./data/servers.db", env="DATABASE_PATH")
    
    # SSH
    ssh_timeout: int = Field(30, env="SSH_TIMEOUT")
    ssh_key_path: str = Field("~/.ssh/id_rsa", env="SSH_KEY_PATH")
    
    # Scheduler
    check_interval_hours: int = Field(6, env="CHECK_INTERVAL_HOURS")
    alert_check_interval_minutes: int = Field(15, env="ALERT_CHECK_INTERVAL_MINUTES")
    
    # Thresholds
    cpu_warning: int = Field(70, env="CPU_WARNING")
    cpu_critical: int = Field(90, env="CPU_CRITICAL")
    ram_warning: int = Field(70, env="RAM_WARNING")
    ram_critical: int = Field(85, env="RAM_CRITICAL")
    disk_warning: int = Field(70, env="DISK_WARNING")
    disk_critical: int = Field(85, env="DISK_CRITICAL")
    swap_warning: int = Field(30, env="SWAP_WARNING")
    swap_critical: int = Field(50, env="SWAP_CRITICAL")
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: str = Field("./logs/bot.log", env="LOG_FILE")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def expanded_ssh_key_path(self) -> Path:
        """Expand ~ in SSH key path"""
        return Path(self.ssh_key_path).expanduser()
    
    @property
    def thresholds(self) -> dict:
        """Get all thresholds as a dict"""
        return {
            "cpu": {"warning": self.cpu_warning, "critical": self.cpu_critical},
            "ram": {"warning": self.ram_warning, "critical": self.ram_critical},
            "disk": {"warning": self.disk_warning, "critical": self.disk_critical},
            "swap": {"warning": self.swap_warning, "critical": self.swap_critical},
        }


# Create directories if they don't exist
def ensure_directories():
    """Create necessary directories"""
    dirs = ["./data", "./logs"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
ensure_directories()
