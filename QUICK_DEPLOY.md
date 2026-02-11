# 🚀 Быстрый деплой (шпаргалка)

## 1️⃣ На сервере (первоначальная настройка)

```bash
# Установка
apt update && apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Создание папки
mkdir -p /var/www/opinion/web
cd /var/www/opinion
```

## 2️⃣ Копирование файлов (с вашего компьютера)

```powershell
# Копируем всё через SCP
scp web_server.py web_trader.py presigned_orders_api.py opinion_openapi.py config.py requirements.txt root@IP:/var/www/opinion/
scp web\wallet-connect.js web\presigned-orders.js web\bot-page.html root@IP:/var/www/opinion/web/
```

## 3️⃣ На сервере (настройка Python)

```bash
cd /var/www/opinion
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn python-dotenv requests websockets aiohttp pydantic
```

## 4️⃣ Создаём .env

```bash
cat > /var/www/opinion/.env << 'EOF'
APIKEY=ваш_ключ
HOST=https://proxy.opinion.trade:8443
EOF
chmod 600 .env
```

## 5️⃣ Systemd сервис

```bash
cat > /etc/systemd/system/opinion-bot.service << 'EOF'
[Unit]
Description=Opinion Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/opinion
Environment="PATH=/var/www/opinion/venv/bin"
ExecStart=/var/www/opinion/venv/bin/python web_server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

chown -R www-data:www-data /var/www/opinion
systemctl daemon-reload
systemctl enable --now opinion-bot
```

## 6️⃣ Nginx

```bash
cat > /etc/nginx/sites-available/opinion << 'EOF'
server {
    listen 80;
    server_name ваш-домен.com;
    
    location /static/ { alias /var/www/opinion/web/; }
    location /bot { alias /var/www/opinion/web/bot-page.html; default_type text/html; }
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
EOF

ln -sf /etc/nginx/sites-available/opinion /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## 7️⃣ SSL

```bash
certbot --nginx -d ваш-домен.com
```

## ✅ Готово!

Откройте: `https://ваш-домен.com/bot`

---

## 🔧 Полезные команды

```bash
# Логи бота
journalctl -u opinion-bot -f

# Перезапуск
systemctl restart opinion-bot

# Статус
systemctl status opinion-bot
```
