# Развертывание бота на VPS без Docker

## 🚀 Быстрый перенос через терминал

### 1. Подключитесь к серверу
```bash
ssh user@your-server-ip
```

### 2. Установите Python и pip (если ещё не установлены)
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv -y

# CentOS/RHEL
sudo yum install python3 python3-pip -y
```

### 3. Создайте папку для бота
```bash
mkdir -p ~/telegram_bot
cd ~/telegram_bot
```

### 4. Скопируйте файлы на сервер (с вашего компьютера)

**Вариант A: Через SCP (с Windows PowerShell)**
```powershell
# Запустите эту команду на ВАШЕМ компьютере (не на сервере)
scp -r C:\Users\KIRST\Projects\opinion\telegram_bot\* user@your-server-ip:~/telegram_bot/
```

**Вариант B: Через rsync (быстрее, с WSL или Git Bash)**
```bash
rsync -avz /c/Users/KIRST/Projects/opinion/telegram_bot/ user@your-server-ip:~/telegram_bot/
```

**Вариант C: Через Git (если код в репозитории)**
```bash
# На сервере
cd ~
git clone https://github.com/your-username/your-repo.git telegram_bot
cd telegram_bot
```

### 5. Настройте виртуальное окружение на сервере
```bash
cd ~/telegram_bot
python3 -m venv venv
source venv/bin/activate
pip install python-telegram-bot[job-queue] python-dotenv requests
```

### 6. Создайте файл .env
```bash
nano .env
```

Вставьте:
```
TELEGRAM_BOT_TOKEN=ваш_токен_бота
OPINION_API_KEY=ваш_api_ключ
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 7. Проверьте запуск
```bash
cd ~/telegram_bot
source venv/bin/activate
python telegram_bot_auto.py
```

---

## 🔄 Автозапуск через systemd (24/7)

### Создайте systemd сервис
```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

Вставьте (замените `your_username` на ваше имя пользователя):
```ini
[Unit]
Description=Telegram Trading Bot
After=network.target

[Service]
Type=simple
User=uzver
WorkingDirectory=/home/uzver/Downloads/telegram_bot
Environment=PATH=/home/uzver/Downloads/telegram_bot/venv/bin
ExecStart=/home/uzver/Downloads/telegram_bot/venv/bin/python telegram_bot_auto.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Активируйте сервис
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

### Полезные команды
```bash
# Статус бота
sudo systemctl status telegram-bot

# Логи бота
sudo journalctl -u telegram-bot -f

# Перезапустить бота
sudo systemctl restart telegram-bot

# Остановить бота
sudo systemctl stop telegram-bot
```

---

## 📋 Краткая шпаргалка

```bash
# === НА ВАШЕМ КОМПЬЮТЕРЕ (PowerShell) ===
scp -r C:\Users\KIRST\Projects\opinion\telegram_bot\* user@SERVER_IP:~/telegram_bot/

# === НА СЕРВЕРЕ ===
cd ~/telegram_bot
python3 -m venv venv
source venv/bin/activate
pip install python-telegram-bot[job-queue] python-dotenv requests
nano .env  # добавьте токены
python telegram_bot_auto.py  # тест

# Для 24/7 работы - настройте systemd (см. выше)
```

---

## ❓ Решение проблем

**Ошибка "Permission denied":**
```bash
chmod +x telegram_bot_auto.py
```

**Бот не запускается после перезагрузки:**
```bash
sudo systemctl enable telegram-bot
```

**Посмотреть ошибки:**
```bash
sudo journalctl -u telegram-bot --no-pager -n 50
```
