# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Telegram bot for monitoring and managing the health of multiple Linux servers. The bot runs on one server and can monitor both itself (localhost) and remote servers via SSH. It provides real-time health checks, scheduled monitoring, automatic alerts, and optimization capabilities.

**Tech Stack:**
- Python 3.11+ with async/await
- aiogram 3.x (Telegram Bot API)
- asyncssh (async SSH connections)
- APScheduler (scheduled jobs)
- aiosqlite (async SQLite database)
- pydantic-settings (configuration)

## Development Commands

### Local Development
```bash
# Setup virtual environment
cd server-health-bot
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with BOT_TOKEN and ADMIN_ID

# Run bot locally
python main.py
```

### Testing
```bash
# Run a health check test (requires SSH to work)
python -c "import asyncio; from core.health_checker import check_local_server; asyncio.run(check_local_server('test'))"

# Test SSH connection to localhost
ssh localhost "uptime && free -h && df -h /"
```

### Production Deployment
```bash
# Install on server (from install.sh)
sudo ./install.sh

# Service management
sudo systemctl status server-health-bot
sudo systemctl restart server-health-bot
sudo systemctl stop server-health-bot

# View logs
journalctl -u server-health-bot -f
tail -f /var/log/server-health-bot/bot.log
```

## Architecture

### Core Components

**main.py** - Entry point
- Initializes bot, database, and scheduler
- Manages startup/shutdown lifecycle
- Sends admin notifications on start/stop

**config.py** - Configuration management
- Uses pydantic-settings to load from .env
- Defines all thresholds (CPU, RAM, Disk, Swap)
- Expands SSH key paths and creates necessary directories

**Database (database/db.py)**
- SQLite with aiosqlite for async operations
- Tables: servers, check_history, settings
- Server model includes: name, host, port, username, key_path, location, description
- CRUD operations for servers and health check history

**SSH Manager (core/ssh_manager.py)**
- SSHManager: Connects to remote servers via asyncssh
- LocalSSHManager: Runs commands locally via subprocess
- Returns SSHResult dataclass with stdout/stderr/exit_code
- Handles timeouts and authentication (key-based or password)

**Health Checker (core/health_checker.py)**
- HealthChecker: Collects metrics from a server via SSH
- Runs multiple commands to gather: CPU load, RAM, Swap, Disk, processes, uptime, etc.
- Analyzes metrics against thresholds to determine status (ok/warning/critical)
- Returns HealthReport dataclass with all metrics and recommendations
- Helper functions: check_local_server(), check_remote_server()

**Report Formatter (core/report_formatter.py)**
- format_full_report(): Detailed report with all metrics and issues
- format_short_report(): Quick summary (one line per server)
- format_all_servers_summary(): Summary of all servers for scheduled checks
- Uses Unicode progress bars and status emojis

**Scheduler (scheduler/jobs.py)**
- scheduled_health_check(): Full health check of all servers (default: every 6 hours)
- quick_alert_check(): Fast check for critical issues (default: every 15 minutes)
- auto_optimize_server(): Automatically cleans disk when >80% full
- Uses APScheduler with AsyncIOScheduler

**Bot Handlers (bot/handlers.py)**
- Command handlers: /start, /help, /status, /check, /servers, /add, /remove
- Callback handlers: For inline keyboard buttons
- FSM (Finite State Machine) for multi-step flows like adding a server
- Admin-only access enforced via ADMIN_ID check

**Bot Keyboards (bot/keyboards.py)**
- Inline keyboards for main menu, server list, actions, etc.
- Dynamic keyboards based on server list from database

### Data Flow

1. **Scheduled Check Flow:**
   - APScheduler triggers job → runs health check on all servers → sends summary to admin
   - If critical issues found → sends additional alert messages

2. **Manual Check Flow:**
   - User sends /check command → bot queries database for server → creates SSH connection → runs health check → formats and sends report

3. **Adding Server Flow:**
   - User sends /add → bot enters FSM → asks for name/host/port/username → tests connection → saves to database

4. **Auto-Optimization Flow:**
   - Quick alert check detects disk >80% → runs cleanup commands → sends notification

## Important Patterns

### Configuration Loading
All configuration is loaded from `.env` via pydantic-settings. Settings are accessed through the global `settings` object from `config.py`. Never hardcode credentials or thresholds.

### Error Handling
- SSH operations always return SSHResult with success flag
- Health checks collect errors in report.errors list
- Async operations use try/except to prevent bot crashes
- Timeouts are enforced on all SSH connections

### Async/Await Usage
- All I/O operations are async (SSH, database, bot API calls)
- Use `async with` for connections (SSH, database)
- Use `await` for all async functions
- Main loop: `asyncio.run(main())`

### Database Access
- Always use async with for database connections
- Use parameterized queries to prevent SQL injection
- Server changes update both database and in-memory state

### Telegram Bot Patterns
- Use aiogram 3.x Router for handlers
- Parse mode is HTML by default (set in Bot initialization)
- Admin-only commands check `message.from_user.id == settings.admin_id`
- FSM (States) for multi-step conversations like adding servers

### SSH Execution
- LocalSSHManager for localhost (uses subprocess)
- SSHManager for remote servers (uses asyncssh)
- Always set timeouts to prevent hanging
- Commands are shell strings executed with `sh -c`

### Health Status Logic
- ok: All metrics below warning threshold
- warning: At least one metric above warning but below critical
- critical: At least one metric above critical threshold
- error: Failed to collect metrics (SSH error, timeout, etc.)

## Key Files Reference

- **main.py:87-120** - Bot initialization and startup sequence
- **config.py:10-60** - Settings class with all configuration
- **database/db.py:53-199** - Database class with CRUD operations
- **core/ssh_manager.py:23-100** - SSHManager class
- **core/health_checker.py:67-300** - HealthChecker class with metric collection
- **bot/handlers.py:68-78** - /start command handler pattern
- **scheduler/jobs.py:22-84** - Scheduled health check job

## Notes for Development

- The bot supports both local (localhost) and remote servers
- SSH keys are stored in ~/.ssh/ and referenced by path in database
- Scheduled jobs are configured via .env (CHECK_INTERVAL_HOURS, ALERT_CHECK_INTERVAL_MINUTES)
- Auto-optimization triggers when disk usage exceeds 80%
- All dangerous operations require confirmation via inline keyboard
- Country flags are mapped in bot/handlers.py:38-49 for server display
- The bot sends startup/shutdown notifications to admin
- Logs are written to both file (./logs/bot.log) and stdout
