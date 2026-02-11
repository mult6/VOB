# Opinion Trade Market Maker Bot

Автоматический маркет-мейкер бот для торговли на платформе Opinion Trade с использованием CLOB SDK.

## 🤖 Три варианта ботов

### 1. 📱 Telegram Bot - Виртуальная торговля ⭐ ДЛЯ ОБУЧЕНИЯ!
- Торговля через Telegram
- **Виртуальный баланс** (без реальных денег!)
- Идеально для обучения и тестирования
- Понимание механики рынка
- Симуляция исполнения ордеров

**→ [Перейти в папку telegram_bot/](telegram_bot/)** - все файлы бота здесь!  
**→ [Telegram Bot Quick Start](telegram_bot/TELEGRAM_BOT_QUICKSTART.md)** - запуск за 3 минуты!  
**→ [Telegram Bot Guide](telegram_bot/TELEGRAM_BOT_GUIDE.md)** - полное руководство

### 2. 🌐 Web-режим (браузер) - Реальная торговля
- Запуск через веб-интерфейс
- Подключение через MetaMask
- Приватный ключ остается в безопасности
- Работает 24/7 на сервере

**→ [Quick Start Guide](QUICKSTART.md)** - начните здесь!  
**→ [Web3 Setup Guide](WEB3_SETUP_GUIDE.md)** - подробная инструкция  
**→ [Web Deployment Guide](WEB_DEPLOYMENT_GUIDE.md)** - для развертывания на сервере  
**→ [FAQ](FAQ.md)** - часто задаваемые вопросы

### 3. 🖥️ Локальный режим (консоль) - Реальная торговля
- Запуск на вашем компьютере
- Приватный ключ в `.env` файле
- Полный контроль
- Требует постоянного подключения

---

## 🚀 Возможности

### Telegram Bot (Виртуальная торговля)
- ✅ Поиск бинарных рынков (YES/NO)
- ✅ Виртуальный баланс для тестирования
- ✅ Размещение виртуальных ордеров
- ✅ Симуляция исполнения
- ✅ Отслеживание PnL
- ✅ Обучение без риска

### Реальная торговля (Web + Локальный)
- ✅ Автоматическое размещение лимит-ордеров (BID/ASK)
- ✅ Динамическое переключение между YES/NO токенами
- ✅ Адаптивная стратегия в зависимости от доступных средств
- ✅ Валидация цен согласно требованиям платформы
- ✅ Обработка ошибок и автоматическая отмена ордеров
- ✅ **Web-интерфейс с MetaMask** (Web-режим)
- ✅ **WebSocket для real-time обновлений** (Web-режим)

## 📋 Требования

**Для Telegram Bot (виртуальная торговля):**
- Python 3.8+
- Telegram Bot Token (от @BotFather)
- ❌ **БЕЗ** API ключа, Private key, блокчейна!

**Для реальной торговли (Web + Локальный):**
- Python 3.8+
- BNB на балансе для gas fees
- USDT на Opinion Trade для торговли
- API ключ Opinion Trade
- Приватный ключ от кошелька

## 📁 Структура проекта

```
opinion/
├── telegram_bot/              # 📱 Telegram Bot (виртуальная торговля)
│   ├── telegram_bot.py        # Основной файл бота
│   ├── README.md              # Документация
│   ├── TELEGRAM_BOT_QUICKSTART.md
│   ├── TELEGRAM_BOT_GUIDE.md
│   └── ...
├── web/                       # 🌐 Web-интерфейс
│   ├── index.html
│   └── app.js
├── bot_v2.py                  # 🖥️ Основной бот v2 (консоль)
├── web_server.py              # 🌐 Web-сервер
├── find_binary_markets.py     # 🔍 Поиск рынков
├── config.py                  # ⚙️ Конфигурация
└── ...
```

## 🛠️ Установка

### Для Telegram Bot

```bash
cd telegram_bot
pip install -r requirements-telegram.txt
python telegram_bot.py
```

**→ См. [telegram_bot/README.md](telegram_bot/README.md) для деталей**

### Для реальной торговли

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/yourusername/opinion-market-maker.git
cd opinion-market-maker
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте конфигурацию

```bash
# Скопируйте пример конфига
cp .env.example .env

# Отредактируйте .env и заполните своими данными
notepad .env  # Windows
nano .env     # Linux/Mac
```

**⚠️ ВАЖНО:** Никогда не публикуйте файл `.env` с реальными ключами!

### 5. Получите API ключ

Заполните форму для получения API ключа:
https://docs.google.com/forms/d/1h7gp8UffZeXzYQ-lv4jcou9PoRNOqMAQhyW4IwZDnII

## 🎯 Использование

### Режим 1: Консольный бот

```bash
python bot.py
```

### Режим 2: GUI интерфейс

```bash
python bot_gui.py
```

### Режим 3: Простой бот (без GUI)

```bash
python simple_bot.py
```

## 📁 Структура проекта

```
opinion-market-maker/
├── bot.py                    # Основной бот с полным функционалом
├── bot_gui.py               # GUI интерфейс
├── simple_bot.py            # Упрощенная версия
├── multi_market_bot.py      # Мульти-маркет торговля
├── opinion_openapi.py       # Обертка Opinion OpenAPI
├── config.py                # Конфигурация
├── requirements.txt         # Python зависимости
├── .env.example            # Пример конфигурации
├── .gitignore              # Игнорируемые файлы
└── DOCUMENTATION_UPDATES.md # Документация изменений
```

## ⚙️ Конфигурация

Основные параметры в `.env`:

```bash
# API и подключение
APIKEY=your_api_key_here
PRIVATE_KEY=0xYOUR_PRIVATE_KEY
MULTISIG_WALLET=0xYOUR_WALLET

# Рынок
MARKET_ID=1463

# Стратегия
BID_AMOUNT=5.0
ASK_AMOUNT=5.0
SPREAD_OFFSET=0.10
CHECK_INTERVAL=30
```

## 📊 Стратегия

Бот использует адаптивную стратегию:

1. **Двусторонняя торговля** (при наличии USDT и токенов):
   - BID на маловероятный исход выше рынка
   - ASK на вероятный исход ниже рынка

2. **Только продажа** (при наличии только токенов):
   - ASK на имеющиеся токены выше рынка

3. **Только покупка** (при наличии только USDT):
   - BID на маловероятный исход ниже рынка

## 🔒 Безопасность

**⚠️ КРИТИЧЕСКИ ВАЖНО:**

1. ✅ Никогда не публикуйте `.env` файл
2. ✅ Храните приватный ключ в безопасности
3. ✅ Используйте отдельный кошелек для бота
4. ✅ Начинайте с малых сумм
5. ✅ Регулярно проверяйте балансы

## 📚 Документация

- [Opinion OpenAPI](https://docs.opinion.trade/developer-guide/opinion-open-api)
- [Opinion CLOB SDK](https://docs.opinion.trade/developer-guide/opinion-clob-sdk)
- [Opinion Builders Program](https://forms.gle/9oBLs9wns6sJVm87A)

## 🐛 Устранение неполадок

### Ошибка: "PRIVATE_KEY не установлен"
- Проверьте что `.env` файл существует и содержит `PRIVATE_KEY`

### Ошибка: "Rate limit превышен"
- Уменьшите частоту проверок (увеличьте `CHECK_INTERVAL`)

### Ордера не размещаются
- Проверьте баланс USDT и токенов
- Убедитесь что торговля активирована

## 📝 Лицензия

MIT License - используйте на свой риск.

## 🤝 Участие в разработке

1. Fork проекта
2. Создайте feature ветку (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add some AmazingFeature'`)
4. Push в ветку (`git push origin feature/AmazingFeature`)
5. Создайте Pull Request

## ⚠️ Дисклеймер

Этот бот предоставляется "как есть" без каких-либо гарантий. Торговля криптовалютами сопряжена с риском. Используйте на свой страх и риск.

---

**Автор:** Your Name  
**Версия:** 2.0  
**Дата:** Декабрь 2025
