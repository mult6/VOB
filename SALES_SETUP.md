# 🛒 Система продаж бота через Telegram

## Обзор

Система позволяет продавать консольную версию бота через Telegram с оплатой криптовалютой через Coinbase Commerce API.

**Ключевые особенности:**
- ✅ Динамическое создание платежей через API
- ✅ Идентификация покупателя через metadata
- ✅ Автоматическая доставка после подтверждения платежа
- ✅ Проверка статуса платежа в реальном времени
- ✅ Админ-панель для управления продажами

## Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Пользователь   │────▶│  Telegram Bot    │────▶│  Coinbase Commerce  │
│  /buy           │     │  create_charge() │     │  API                │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
                                │                         │
                                │  metadata:              │
                                │  telegram_user_id       │
                                ▼                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Покупатель     │◀────│  Webhook Server  │◀────│  charge:confirmed   │
│  получает ZIP   │     │  (Flask)         │     │  + metadata         │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
```

## Компоненты

### 1. coinbase_client.py
Клиент для работы с Coinbase Commerce API.

```python
from coinbase_client import CoinbaseCommerceClient, create_bot_purchase_charge

# Создание клиента
client = CoinbaseCommerceClient(api_key, webhook_secret)

# Создание персонализированного платежа
result = create_bot_purchase_charge(
    client=client,
    telegram_user_id=123456789,
    telegram_username="john_doe",
    price=49.00
)

# result.hosted_url - ссылка на оплату
# result.charge_id  - ID для отслеживания
```

### 2. package_bot.py
Скрипт для создания чистого архива бота без приватных данных.

```bash
# Создать архив
python package_bot.py

# С указанием версии
python package_bot.py --version 3.1

# Кастомное имя файла
python package_bot.py --output my_bot.zip
```

### 3. telegram_bot_auto.py (обновлённый)
Телеграм бот с админ-панелью и системой продаж.

**Админ команды:**
- `/admin` - открыть панель администратора
- `/confirm <user_id>` - подтвердить покупку вручную

**Пользовательские команды:**
- `/buy` - начать процесс покупки
- `/download` - скачать бота повторно (для тех кто уже купил)

### 4. coinbase_webhook.py
Flask сервер для приёма webhook от Coinbase Commerce.

```bash
python coinbase_webhook.py
```

## Настройка

### Шаг 1: Конфигурация .env

```env
# Ваш Telegram User ID (узнать: @userinfobot)
ADMIN_USER_ID=123456789

# Включить продажи
SALES_ENABLED=false

# Coinbase Commerce API
COINBASE_API_KEY=your_api_key_here
COINBASE_WEBHOOK_SECRET=your_webhook_secret

# Fallback ссылка (если API недоступен)
COINBASE_CHECKOUT_URL=https://commerce.coinbase.com/checkout/xxx

# Путь к архиву
BOT_ARCHIVE_PATH=./opinion_trade_bot.zip

# Цена
BOT_PRICE_USD=49.00

# Порт для webhook сервера
WEBHOOK_PORT=5000
```

### Шаг 2: Получение Coinbase Commerce API Key

1. Войдите в [Coinbase Commerce Dashboard](https://beta.commerce.coinbase.com)
2. Перейдите в `Settings -> Security`
3. Создайте API Key и скопируйте в `COINBASE_API_KEY`

### Шаг 3: Настройка Webhook

1. В Coinbase Commerce: `Settings -> Security -> Webhook subscriptions`
2. Добавьте endpoint: `https://your-server.com/webhook/coinbase`
3. Скопируйте Shared Secret в `COINBASE_WEBHOOK_SECRET`

### Шаг 4: Генерация архива бота

```bash
cd /path/to/opinion
python package_bot.py --version 3.0
```

## Использование

### Для администратора

1. **Запуск бота:**
   ```bash
   cd telegram_bot
   python telegram_bot_auto.py
   ```

2. **Запуск webhook сервера (в отдельном терминале):**
   ```bash
   python coinbase_webhook.py
   ```

3. **Включить продажи:**
   - Отправьте `/admin` в Telegram
   - Нажмите "Enable Sales"

4. **Ручное подтверждение покупки (если нужно):**
   - Отправьте `/confirm <user_id>`

### Для пользователя

1. Пользователь видит кнопку "🛒 Buy Console Bot"
2. Нажимает и получает информацию о боте
3. Получает персональную ссылку на оплату Coinbase
4. После оплаты получает архив автоматически!

## Как работает автоматическая доставка

1. **Пользователь нажимает /buy:**
   - Бот создаёт charge через Coinbase API
   - В metadata передаётся `telegram_user_id`
   - Пользователь получает персональную ссылку

2. **Пользователь оплачивает:**
   - Coinbase обрабатывает платёж
   - При подтверждении отправляет webhook

3. **Webhook получает событие:**
   - `charge:confirmed` содержит metadata
   - Извлекается `telegram_user_id`
   - Архив отправляется пользователю автоматически

## Тестирование локально

```bash
# Установите ngrok
ngrok http 5000

# Используйте полученный URL в Coinbase Webhook
# Например: https://abc123.ngrok.io/webhook/coinbase
```

## API Webhook сервера

### GET /health
Проверка работоспособности

### POST /webhook/coinbase
Endpoint для Coinbase Commerce webhook

### POST /register_purchase
Регистрация pending покупки
```json
{
    "user_id": 123456789,
    "checkout_id": "abc123"
}
```

### POST /manual_send/<user_id>
Ручная отправка бота пользователю

## Безопасность

- ✅ Проверка подписи webhook от Coinbase
- ✅ Приватные ключи не попадают в архив
- ✅ Админ-функции доступны только ADMIN_USER_ID
- ✅ Повторное скачивание только для подтверждённых покупателей

## Troubleshooting

### Бот не отправляется после оплаты
1. Проверьте COINBASE_WEBHOOK_SECRET
2. Проверьте доступность webhook сервера
3. Используйте `/confirm <user_id>` для ручной отправки

### Кнопка покупки не появляется
1. Убедитесь что SALES_ENABLED=true в .env
2. Или включите через `/admin -> Enable Sales`
3. Перезапустите бота

### Архив не создаётся
1. Проверьте что все файлы из INCLUDE_FILES существуют
2. Запустите `python package_bot.py --debug`
