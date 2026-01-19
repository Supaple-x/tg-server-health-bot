"""
Health Checker - collects server metrics and analyzes health
"""
import re
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from core.ssh_manager import SSHManager, LocalSSHManager
from config import settings


@dataclass
class Metric:
    """Single metric with value and status"""
    name: str
    value: float
    unit: str
    status: str  # ok, warning, critical, error
    details: str = ""


@dataclass
class ProcessInfo:
    """Top process information"""
    pid: int
    user: str
    cpu: float
    mem: float
    command: str


@dataclass
class HealthReport:
    """Complete health report for a server"""
    server_name: str
    hostname: str
    timestamp: datetime
    uptime: str
    os_info: str

    # Overall status
    overall_status: str  # ok, warning, critical, error

    # Metrics
    cpu_load: Metric
    cpu_load_per_core: float
    ram: Metric
    swap: Metric
    disks: list[Metric] = field(default_factory=list)
    sessions: Metric = field(default_factory=lambda: Metric("Sessions", 0, "", "ok"))
    docker: Optional[Metric] = None  # Docker disk usage if available
    journal_size: Optional[Metric] = None  # Systemd journal size

    # Top processes
    top_cpu_processes: list[ProcessInfo] = field(default_factory=list)
    top_mem_processes: list[ProcessInfo] = field(default_factory=list)

    # Issues and recommendations
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # Errors during collection
    errors: list[str] = field(default_factory=list)


class HealthChecker:
    """Collects and analyzes server health metrics"""
    
    # Commands for metric collection
    COMMANDS = {
        "hostname": "hostname",
        "uptime": "uptime -p 2>/dev/null || uptime",
        "os_info": "cat /etc/os-release | grep -E '^(NAME|VERSION)=' | head -2",
        "cpu_cores": "nproc",
        "load_avg": "cat /proc/loadavg",
        "memory": "free -b | grep -E '^(Mem|Swap):'",
        "disk": "df -B1 --output=target,size,used,avail,pcent | grep -E '^/'",
        "top_cpu": "ps aux --sort=-%cpu | head -6 | tail -5",
        "top_mem": "ps aux --sort=-%mem | head -6 | tail -5",
        "sessions": "who | wc -l",
        "docker": "docker system df --format '{{.Type}}\t{{.Size}}\t{{.Reclaimable}}' 2>/dev/null || echo 'NO_DOCKER'",
        "journal": "journalctl --disk-usage 2>/dev/null | grep -oP '[\\d.]+[KMGT]?' || echo '0'",
    }

    # Thresholds for sessions (warning if >10, critical if >50)
    SESSION_WARNING = 10
    SESSION_CRITICAL = 50

    # Thresholds for Docker (warning if >5GB, critical if >15GB)
    DOCKER_WARNING_GB = 5
    DOCKER_CRITICAL_GB = 15

    # Thresholds for journal (warning if >500MB, critical if >1GB)
    JOURNAL_WARNING_MB = 500
    JOURNAL_CRITICAL_MB = 1000
    
    def __init__(self, ssh_manager: SSHManager, server_name: str = "server"):
        self.ssh = ssh_manager
        self.server_name = server_name
        self.thresholds = settings.thresholds
    
    def _get_status(self, value: float, metric_type: str) -> str:
        """Determine status based on thresholds"""
        th = self.thresholds.get(metric_type, {"warning": 70, "critical": 90})
        if value >= th["critical"]:
            return "critical"
        elif value >= th["warning"]:
            return "warning"
        return "ok"
    
    def _parse_memory(self, output: str) -> tuple[Metric, Metric]:
        """Parse memory output from free command"""
        ram = Metric("RAM", 0, "%", "error", "Failed to parse")
        swap = Metric("Swap", 0, "%", "ok", "No swap")
        
        for line in output.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                if parts[0] == "Mem:":
                    total = int(parts[1])
                    used = int(parts[2])
                    if total > 0:
                        pct = (used / total) * 100
                        ram = Metric(
                            "RAM",
                            round(pct, 1),
                            "%",
                            self._get_status(pct, "ram"),
                            f"{used / (1024**3):.1f}GB / {total / (1024**3):.1f}GB"
                        )
                elif parts[0] == "Swap:":
                    total = int(parts[1])
                    used = int(parts[2])
                    if total > 0:
                        pct = (used / total) * 100
                        swap = Metric(
                            "Swap",
                            round(pct, 1),
                            "%",
                            self._get_status(pct, "swap"),
                            f"{used / (1024**3):.1f}GB / {total / (1024**3):.1f}GB"
                        )
        
        return ram, swap
    
    def _parse_disk(self, output: str) -> list[Metric]:
        """Parse disk usage output"""
        disks = []
        for line in output.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 5:
                mount = parts[0]
                total = int(parts[1])
                used = int(parts[2])
                pct_str = parts[4].rstrip("%")
                try:
                    pct = float(pct_str)
                    disks.append(Metric(
                        f"Disk {mount}",
                        pct,
                        "%",
                        self._get_status(pct, "disk"),
                        f"{used / (1024**3):.1f}GB / {total / (1024**3):.1f}GB"
                    ))
                except ValueError:
                    pass
        return disks
    
    def _parse_processes(self, output: str) -> list[ProcessInfo]:
        """Parse ps aux output"""
        processes = []
        for line in output.strip().split("\n"):
            parts = line.split(None, 10)
            if len(parts) >= 11:
                try:
                    processes.append(ProcessInfo(
                        pid=int(parts[1]),
                        user=parts[0],
                        cpu=float(parts[2]),
                        mem=float(parts[3]),
                        command=parts[10][:50]
                    ))
                except (ValueError, IndexError):
                    pass
        return processes

    def _parse_size_to_gb(self, size_str: str) -> float:
        """Parse size string like '3.7GB' or '500MB' to GB"""
        size_str = size_str.strip().upper()
        try:
            if 'GB' in size_str:
                return float(size_str.replace('GB', ''))
            elif 'MB' in size_str:
                return float(size_str.replace('MB', '')) / 1024
            elif 'KB' in size_str:
                return float(size_str.replace('KB', '')) / (1024 * 1024)
            elif 'B' in size_str:
                return float(size_str.replace('B', '')) / (1024 * 1024 * 1024)
            else:
                return float(size_str)
        except ValueError:
            return 0

    def _parse_docker(self, output: str) -> Optional[Metric]:
        """Parse docker system df output"""
        total_size_gb = 0
        reclaimable_gb = 0

        for line in output.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                size_str = parts[1] if len(parts) > 1 else "0"
                reclaim_str = parts[2] if len(parts) > 2 else "0"
                # Extract just the size part (e.g., "2.946GB" from "2.946GB (79%)")
                reclaim_str = reclaim_str.split()[0] if reclaim_str else "0"
                total_size_gb += self._parse_size_to_gb(size_str)
                reclaimable_gb += self._parse_size_to_gb(reclaim_str)

        if total_size_gb >= self.DOCKER_CRITICAL_GB:
            status = "critical"
        elif total_size_gb >= self.DOCKER_WARNING_GB:
            status = "warning"
        else:
            status = "ok"

        return Metric(
            "Docker",
            round(total_size_gb, 1),
            "GB",
            status,
            f"Reclaimable: {reclaimable_gb:.1f}GB"
        )

    def _parse_journal(self, output: str) -> Optional[Metric]:
        """Parse journalctl --disk-usage output"""
        size_mb = 0
        output = output.strip()

        # Parse size like "881.8M" or "1.2G"
        match = re.search(r'([\d.]+)([KMGT]?)', output)
        if match:
            value = float(match.group(1))
            unit = match.group(2).upper()
            if unit == 'G':
                size_mb = value * 1024
            elif unit == 'M':
                size_mb = value
            elif unit == 'K':
                size_mb = value / 1024
            else:
                size_mb = value / (1024 * 1024)

        if size_mb >= self.JOURNAL_CRITICAL_MB:
            status = "critical"
        elif size_mb >= self.JOURNAL_WARNING_MB:
            status = "warning"
        else:
            status = "ok"

        return Metric(
            "Journal",
            round(size_mb, 0),
            "MB",
            status,
            f"Systemd logs: {size_mb:.0f}MB"
        )

    def _analyze_issues(self, report: HealthReport) -> None:
        """Analyze report and add issues/recommendations"""
        # CPU
        if report.cpu_load.status == "critical":
            report.issues.append(f"🔴 Критическая загрузка CPU: {report.cpu_load.value}")
            report.recommendations.append("Найти и оптимизировать тяжёлые процессы")
        elif report.cpu_load.status == "warning":
            report.issues.append(f"🟡 Повышенная загрузка CPU: {report.cpu_load.value}")
        
        # RAM
        if report.ram.status == "critical":
            report.issues.append(f"🔴 Критическое использование RAM: {report.ram.value}%")
            report.recommendations.append("Проверить утечки памяти, увеличить swap или RAM")
        elif report.ram.status == "warning":
            report.issues.append(f"🟡 Высокое использование RAM: {report.ram.value}%")
        
        # Swap
        if report.swap.status == "critical":
            report.issues.append(f"🔴 Активное использование Swap: {report.swap.value}%")
            report.recommendations.append("Срочно освободить RAM или увеличить память")
        elif report.swap.status == "warning":
            report.issues.append(f"🟡 Swap используется: {report.swap.value}%")
        
        # Disks
        for disk in report.disks:
            if disk.status == "critical":
                report.issues.append(f"🔴 Диск {disk.name} заполнен: {disk.value}%")
                report.recommendations.append(f"Очистить {disk.name}: логи, кэш, старые файлы")
            elif disk.status == "warning":
                report.issues.append(f"🟡 Диск {disk.name} заполняется: {disk.value}%")

        # Sessions
        if report.sessions.status == "critical":
            report.issues.append(f"🔴 Слишком много сессий: {int(report.sessions.value)}")
            report.recommendations.append("Проверить подозрительные подключения, возможна атака")
        elif report.sessions.status == "warning":
            report.issues.append(f"🟡 Много активных сессий: {int(report.sessions.value)}")

        # Docker
        if report.docker and report.docker.status == "critical":
            report.issues.append(f"🔴 Docker занимает много места: {report.docker.value}GB")
            report.recommendations.append("Очистить Docker: docker system prune -a")
        elif report.docker and report.docker.status == "warning":
            report.issues.append(f"🟡 Docker: {report.docker.value}GB ({report.docker.details})")

        # Journal
        if report.journal_size and report.journal_size.status == "critical":
            report.issues.append(f"🔴 Журналы занимают много места: {report.journal_size.value}MB")
            report.recommendations.append("Очистить журналы: journalctl --vacuum-size=200M")
        elif report.journal_size and report.journal_size.status == "warning":
            report.issues.append(f"🟡 Журналы: {report.journal_size.value}MB")

        # Determine overall status
        statuses = [report.cpu_load.status, report.ram.status, report.swap.status, report.sessions.status]
        if report.docker:
            statuses.append(report.docker.status)
        if report.journal_size:
            statuses.append(report.journal_size.status)
        statuses.extend([d.status for d in report.disks])
        
        if "critical" in statuses:
            report.overall_status = "critical"
        elif "warning" in statuses:
            report.overall_status = "warning"
        elif "error" in statuses:
            report.overall_status = "error"
        else:
            report.overall_status = "ok"
    
    async def collect(self) -> HealthReport:
        """Collect all metrics and generate health report"""
        timestamp = datetime.utcnow()
        
        # Execute all commands
        results = await self.ssh.execute_multiple(list(self.COMMANDS.values()))
        
        # Initialize report with defaults
        report = HealthReport(
            server_name=self.server_name,
            hostname="unknown",
            timestamp=timestamp,
            uptime="unknown",
            os_info="unknown",
            overall_status="error",
            cpu_load=Metric("CPU Load", 0, "", "error"),
            cpu_load_per_core=0,
            ram=Metric("RAM", 0, "%", "error"),
            swap=Metric("Swap", 0, "%", "ok"),
        )
        
        # Parse hostname
        r = results.get(self.COMMANDS["hostname"])
        if r and r.success:
            report.hostname = r.stdout.strip()
        
        # Parse uptime
        r = results.get(self.COMMANDS["uptime"])
        if r and r.success:
            report.uptime = r.stdout.strip()
        
        # Parse OS info
        r = results.get(self.COMMANDS["os_info"])
        if r and r.success:
            lines = r.stdout.strip().split("\n")
            os_parts = []
            for line in lines:
                if "=" in line:
                    os_parts.append(line.split("=")[1].strip('"'))
            report.os_info = " ".join(os_parts)
        
        # Parse CPU cores and load
        cores = 1
        r = results.get(self.COMMANDS["cpu_cores"])
        if r and r.success:
            try:
                cores = int(r.stdout.strip())
            except ValueError:
                pass
        
        r = results.get(self.COMMANDS["load_avg"])
        if r and r.success:
            parts = r.stdout.strip().split()
            if parts:
                try:
                    load_1m = float(parts[0])
                    load_per_core = load_1m / cores
                    report.cpu_load = Metric(
                        "CPU Load",
                        round(load_1m, 2),
                        f"/ {cores} cores",
                        self._get_status(load_per_core * 100, "cpu"),
                        f"1m: {parts[0]}, 5m: {parts[1]}, 15m: {parts[2]}"
                    )
                    report.cpu_load_per_core = round(load_per_core, 2)
                except (ValueError, IndexError):
                    pass
        
        # Parse memory
        r = results.get(self.COMMANDS["memory"])
        if r and r.success:
            report.ram, report.swap = self._parse_memory(r.stdout)
        
        # Parse disk
        r = results.get(self.COMMANDS["disk"])
        if r and r.success:
            report.disks = self._parse_disk(r.stdout)
        
        # Parse top processes
        r = results.get(self.COMMANDS["top_cpu"])
        if r and r.success:
            report.top_cpu_processes = self._parse_processes(r.stdout)

        r = results.get(self.COMMANDS["top_mem"])
        if r and r.success:
            report.top_mem_processes = self._parse_processes(r.stdout)

        # Parse sessions
        r = results.get(self.COMMANDS["sessions"])
        if r and r.success:
            try:
                session_count = int(r.stdout.strip())
                if session_count >= self.SESSION_CRITICAL:
                    status = "critical"
                elif session_count >= self.SESSION_WARNING:
                    status = "warning"
                else:
                    status = "ok"
                report.sessions = Metric(
                    "Sessions",
                    session_count,
                    "users",
                    status,
                    f"{session_count} active sessions"
                )
            except ValueError:
                pass

        # Parse Docker usage
        r = results.get(self.COMMANDS["docker"])
        if r and r.success and "NO_DOCKER" not in r.stdout:
            report.docker = self._parse_docker(r.stdout)

        # Parse journal size
        r = results.get(self.COMMANDS["journal"])
        if r and r.success:
            report.journal_size = self._parse_journal(r.stdout)

        # Analyze and add issues/recommendations
        self._analyze_issues(report)
        
        return report


async def check_local_server(name: str = "localhost") -> HealthReport:
    """Quick check of the current server"""
    ssh = LocalSSHManager()
    checker = HealthChecker(ssh, name)
    return await checker.collect()


async def check_remote_server(
    host: str,
    name: str,
    port: int = 22,
    username: str = "root",
    key_path: Optional[str] = None,
    password: Optional[str] = None
) -> HealthReport:
    """Check a remote server via SSH"""
    ssh = SSHManager(
        host=host,
        port=port,
        username=username,
        key_path=key_path,
        password=password
    )
    checker = HealthChecker(ssh, name)
    return await checker.collect()
