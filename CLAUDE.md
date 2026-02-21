# CLAUDE.md

Instructions for Claude Code agents working with this repository.

## Project Overview

Telegram bot for monitoring Linux servers, VPN services, and DPI blocking. Runs on a Russia server (176.108.251.49) and monitors itself + remote servers (Finland, USA) via SSH proxy.

**Tech Stack:** Python 3.11+, aiogram 3.x, asyncssh, APScheduler, aiosqlite, pydantic-settings

## Project Structure

All code lives in `server-health-bot/`. The root contains only repo-level files.

```
server-health-bot/
├── main.py                  # Entry point: bot, DB, scheduler init
├── config.py                # Settings from .env (thresholds, intervals, credentials)
├── bot/
│   ├── handlers.py          # Commands (/start, /check, /ban...) and callback handlers
│   ├── middleware.py         # AuthMiddleware: auto-registers users, blocks banned
│   └── keyboards.py         # Inline and reply keyboard builders
├── core/
│   ├── health_checker.py    # HealthChecker: collects CPU/RAM/Disk/Swap via SSH
│   ├── ssh_manager.py       # SSHManager (remote) + LocalSSHManager (localhost)
│   ├── vpn_checker.py       # VPN status, DPI blocking detection, connection links
│   └── report_formatter.py  # Formats reports as HTML for Telegram
├── database/
│   └── db.py                # SQLite: servers, users, services, check_history, settings
├── scheduler/
│   └── jobs.py              # Periodic jobs: health checks, alerts, DPI monitoring
├── scripts/                 # One-time scripts for populating server data
├── vpn_config.json          # VPN server config with secrets (GITIGNORED)
├── vpn_config.example.json  # Template for vpn_config.json
├── .env                     # Bot token, admin ID, thresholds (GITIGNORED)
├── .env.example             # Template for .env
├── install.sh               # Production install script
└── server-health-bot.service # systemd unit file
```

## Development

```bash
cd server-health-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Set BOT_TOKEN and ADMIN_ID
cp vpn_config.example.json vpn_config.json  # Set VPN server details
python main.py
```

## Production (Russia server)

```bash
# Deploy files
scp -i ~/.ssh/temik_cloudru_key FILE artemfcsm@176.108.251.49:/tmp/bot_deploy/
ssh artemfcsm@176.108.251.49 "sudo cp /tmp/bot_deploy/FILE /opt/server-health-bot/PATH"

# Service management
sudo systemctl restart server-health-bot
sudo systemctl status server-health-bot
journalctl -u server-health-bot -f
```

## Architecture

### Data Flow

1. **Scheduled checks** (APScheduler): Full check every 6h, alert check every 15m, DPI check every 3m
2. **Manual check**: User → command/button → SSH to server → health report → Telegram message
3. **Auto-optimization**: Alert check finds disk >80% → runs cleanup → notifies admin
4. **DPI monitoring**: Checks if Russia can reach VPN ports → alerts on blocking state changes

### SSH Access Pattern

- **Localhost**: `LocalSSHManager` (subprocess)
- **Remote servers**: `SSHManager` via Russia SSH proxy (Russia → Finland/USA)
- VPN checker uses `_execute_direct()` and `_execute_via_proxy()` for SSH commands

### User System

- **Open access**: Any user who messages the bot is auto-registered (middleware)
- **Admin** (`settings.admin_id`): Can ban/unban users, manage servers
- **Banned users**: Blocked by middleware, see "access blocked" message
- Commands: `/ban ID`, `/unban ID`, `/users`

### Database Tables

- `servers` — monitored server configs (name, host, port, username, key_path, metadata)
- `users` — auto-registered bot users (telegram_id, username, is_banned, last_seen)
- `server_services` — services running on servers (type, port, status, resources)
- `check_history` — health check results log
- `settings` — key-value store for dynamic config

### VPN Config

`vpn_config.json` contains sensitive data (UUIDs, public keys, SSH paths, VLESS links). Never commit it. Structure:
```json
{
  "ServerName": {
    "host": "IP", "user": "root", "key_path": "~/.ssh/key",
    "vpn_port": 443, "protocol": "VLESS+Reality",
    "links": ["vless://..."],
    "proxy_host": "...", "proxy_user": "...", "proxy_key_path": "..."
  }
}
```

## Key Patterns

- **All I/O is async** — SSH, DB, Telegram API. Use `await` everywhere.
- **SSHResult** — All SSH ops return `SSHResult(success, stdout, stderr, exit_code)`. Never raise.
- **Health status hierarchy**: critical > warning > error > ok. Overall status = worst metric.
- **HTML parse mode** — All Telegram messages use HTML. Use `<b>`, `<code>`, not Markdown.
- **Config from .env** — Access via global `settings` object from `config.py`. Never hardcode.
- **Middleware handles auth** — No per-handler auth checks. `is_admin` flag passed in handler data.
- **DPI state tracking** — In-memory dict in vpn_checker.py. Alerts only on state changes.
- **Callback data format** — `action:param` (e.g., `check_server:Finland`, `opt_journal:Russia`)

## Important Gotchas

- **VPN checker relay test**: Tests from Russia to `127.0.0.1:relay_port`, NOT from target server back
- **Docker overlay2 mounts**: All show same % as root `/` — they're the same filesystem
- **AdGuardHome on Finland**: Query log can grow to 10+ GB. Set `interval: 2h` in config
- **SSH key on server**: `/home/artemfcsm/.ssh/id_ed25519` (not temik_cloudru_key)
- **Public repo**: Never commit secrets (vpn_config.json, .env, SSH keys)
- **Marzban inbound tags**: Must match tags in Marzban SQLite `inbounds` table
- **iptables relay**: Russia:2054→Finland:443, Russia:2055→USA:443 (DNAT+MASQUERADE)
