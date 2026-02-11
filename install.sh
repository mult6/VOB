#!/bin/bash

# ============================================
# Opinion Trading Bot - Installation Script
# ============================================

set -e

echo "🚀 Installing Opinion Trading Bot..."
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Получаем директорию скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📁 Working directory: $SCRIPT_DIR"
echo ""

# 1. Проверка Python
echo "🔍 Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found!${NC}"
    echo "Install it with: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ $PYTHON_VERSION${NC}"

# 2. Создание виртуального окружения
echo ""
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${YELLOW}⚠️ Virtual environment already exists${NC}"
fi

# 3. Активация и установка зависимостей
echo ""
echo "📥 Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install python-telegram-bot[job-queue] python-dotenv requests -q
echo -e "${GREEN}✅ Dependencies installed${NC}"

# 4. Проверка .env файла
echo ""
echo "🔐 Checking .env file..."
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️ .env file not found!${NC}"
    echo ""
    read -p "Enter your TELEGRAM_BOT_TOKEN: " TG_TOKEN
    read -p "Enter your OPINION_API_KEY: " API_KEY
    
    echo "TELEGRAM_BOT_TOKEN=$TG_TOKEN" > .env
    echo "OPINION_API_KEY=$API_KEY" >> .env
    
    echo -e "${GREEN}✅ .env file created${NC}"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# 5. Тестовый запуск
echo ""
echo "🧪 Testing bot startup..."
timeout 5 python telegram_bot_auto.py &> /dev/null &
BOT_PID=$!
sleep 3

if ps -p $BOT_PID > /dev/null 2>&1; then
    kill $BOT_PID 2>/dev/null
    echo -e "${GREEN}✅ Bot starts successfully!${NC}"
else
    echo -e "${RED}❌ Bot failed to start. Check your .env file${NC}"
    exit 1
fi

# 6. Настройка systemd
echo ""
echo "🔧 Setting up systemd service..."

SERVICE_FILE="/etc/systemd/system/opinion-bot.service"
USER=$(whoami)

sudo tee $SERVICE_FILE > /dev/null << EOF
[Unit]
Description=Opinion Trading Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment=PATH=$SCRIPT_DIR/venv/bin
ExecStart=$SCRIPT_DIR/venv/bin/python telegram_bot_auto.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable opinion-bot
echo -e "${GREEN}✅ Systemd service configured${NC}"

# 7. Запуск бота
echo ""
echo "▶️ Starting bot..."
sudo systemctl start opinion-bot
sleep 2

if sudo systemctl is-active --quiet opinion-bot; then
    echo -e "${GREEN}✅ Bot is running!${NC}"
else
    echo -e "${RED}❌ Failed to start bot${NC}"
    sudo journalctl -u opinion-bot --no-pager -n 10
    exit 1
fi

# Готово!
echo ""
echo "============================================"
echo -e "${GREEN}🎉 Installation complete!${NC}"
echo "============================================"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status opinion-bot   - Check status"
echo "  sudo systemctl restart opinion-bot  - Restart bot"
echo "  sudo systemctl stop opinion-bot     - Stop bot"
echo "  sudo journalctl -u opinion-bot -f   - View logs"
echo ""
echo "Your bot is now running 24/7! 🚀"
