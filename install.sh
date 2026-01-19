#!/bin/bash
# Server Health Bot - Installation Script

set -e

INSTALL_DIR="/opt/server-health-bot"
LOG_DIR="/var/log/server-health-bot"

echo "🚀 Installing Server Health Bot..."

# Create directories
echo "📁 Creating directories..."
mkdir -p $INSTALL_DIR
mkdir -p $LOG_DIR

# Copy files
echo "📋 Copying files..."
cp -r . $INSTALL_DIR/

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
cd $INSTALL_DIR
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env if not exists
if [ ! -f .env ]; then
    echo "⚙️ Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit $INSTALL_DIR/.env with your BOT_TOKEN and ADMIN_ID"
    echo ""
fi

# Create data directory
mkdir -p data

# Install systemd service
echo "🔧 Installing systemd service..."
cp server-health-bot.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit configuration:  nano $INSTALL_DIR/.env"
echo "2. Enable service:      systemctl enable server-health-bot"
echo "3. Start service:       systemctl start server-health-bot"
echo "4. Check status:        systemctl status server-health-bot"
echo "5. View logs:           tail -f $LOG_DIR/bot.log"
echo ""
