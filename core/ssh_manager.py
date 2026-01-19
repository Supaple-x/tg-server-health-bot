"""
SSH Manager - handles connections to remote servers
"""
import asyncio
import asyncssh
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

from config import settings


@dataclass
class SSHResult:
    """Result of SSH command execution"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    error: Optional[str] = None


class SSHManager:
    """Manages SSH connections to servers"""
    
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = None
    ):
        self.host = host
        self.port = port
        self.username = username
        self.key_path = key_path or str(settings.expanded_ssh_key_path)
        self.password = password
        self.timeout = timeout or settings.ssh_timeout
    
    async def execute(self, command: str) -> SSHResult:
        """Execute a command on the remote server"""
        try:
            # Prepare connection options
            connect_options = {
                "host": self.host,
                "port": self.port,
                "username": self.username,
                "known_hosts": None,  # Skip host key verification (for simplicity)
            }
            
            # Add authentication
            if self.password:
                connect_options["password"] = self.password
            elif Path(self.key_path).exists():
                connect_options["client_keys"] = [self.key_path]
            
            # Connect and execute
            async with asyncio.timeout(self.timeout):
                async with asyncssh.connect(**connect_options) as conn:
                    result = await conn.run(command, check=False)
                    
                    return SSHResult(
                        success=result.exit_status == 0,
                        stdout=result.stdout or "",
                        stderr=result.stderr or "",
                        exit_code=result.exit_status or 0
                    )
        
        except asyncio.TimeoutError:
            return SSHResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error=f"Connection timeout ({self.timeout}s)"
            )
        except asyncssh.Error as e:
            return SSHResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error=f"SSH error: {str(e)}"
            )
        except Exception as e:
            return SSHResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error=f"Unexpected error: {str(e)}"
            )
    
    async def test_connection(self) -> bool:
        """Test if connection is working"""
        result = await self.execute("echo 'OK'")
        return result.success and "OK" in result.stdout
    
    async def execute_multiple(self, commands: list[str]) -> dict[str, SSHResult]:
        """Execute multiple commands and return results by command"""
        results = {}
        for cmd in commands:
            results[cmd] = await self.execute(cmd)
        return results


class LocalSSHManager(SSHManager):
    """SSH Manager for localhost (current server)"""
    
    def __init__(self):
        super().__init__(
            host="localhost",
            port=22,
            username="root"
        )
    
    async def execute(self, command: str) -> SSHResult:
        """Execute command locally using subprocess"""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            async with asyncio.timeout(self.timeout):
                stdout, stderr = await proc.communicate()
                
                return SSHResult(
                    success=proc.returncode == 0,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    exit_code=proc.returncode or 0
                )
        
        except asyncio.TimeoutError:
            return SSHResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error=f"Command timeout ({self.timeout}s)"
            )
        except Exception as e:
            return SSHResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error=f"Execution error: {str(e)}"
            )
