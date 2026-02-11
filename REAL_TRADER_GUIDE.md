# Real Trader v3.0 - Руководство

## Обзор

**Real Trader** - бот для реальной торговли на Opinion Trade с тремя стратегиями:

| Стратегия | Описание | Риск | Доходность |
|-----------|----------|------|------------|
| `dual_side` | Market Making (BID/ASK со спредом) | Низкий | Стабильный |
| `arbitrage` | Арбитраж (BUY_BOTH / SELL_BOTH) | Минимальный | Высокий при возможности |
| `hybrid` | 70% MM + 30% арбитраж резерв | Низкий | Сбалансированный |

## Быстрый старт

```bash
# 1. Убедитесь что .env настроен
cp .env.example .env
# Заполните PRIVATE_KEY, MULTISIG_WALLET, APIKEY

# 2. Найти бинарный рынок
python find_binary_markets.py

# 3. Запустить бота
python real_trader.py --market 3365 --strategy dual_side
```

## Стратегии

### 1. Dual Side (Market Making)

```bash
python real_trader.py --market 3365 --strategy dual_side --spread 0.02
```

**Как работает:**
- Размещает BID (покупка) на 2% ниже рыночного ASK
- Размещает ASK (продажа) на 2% выше рыночного BID
- **Maker Fee = 0%** - бесплатно!
- Зарабатывает на спреде между покупкой и продажей

**Пример:**
```
YES рынок: BID 0.40 | ASK 0.42
Наш BID: 0.42 × 0.98 = 0.4116 (покупаем дешевле)
Наш ASK: 0.40 × 1.02 = 0.408 (продаем дороже)
Прибыль на цикле: ~2%
```

### 2. Arbitrage (Арбитраж)

```bash
python real_trader.py --market 3365 --strategy arbitrage
```

**Как работает:**

**BUY_BOTH** (когда YES_ASK + NO_ASK < $1.00):
```
YES_ASK = 0.45
NO_ASK = 0.50
Сумма = 0.95 < 1.00

→ Покупаем 1 YES и 1 NO за $0.95
→ После резолюции один токен = $1.00
→ Прибыль: $0.05/пара (5.3%)
```

**SELL_BOTH** (когда YES_BID + NO_BID > $1.00):
```
YES_BID = 0.55
NO_BID = 0.50
Сумма = 1.05 > 1.00

→ Продаем 1 YES и 1 NO за $1.05
→ Себестоимость пары = $1.00
→ Прибыль: $0.05/пара (5%)
```

### 3. Hybrid (Гибрид)

```bash
python real_trader.py --market 3365 --strategy hybrid
```

**Как работает:**
- 70% баланса → Market Making (постоянный доход)
- 30% баланса → Резерв для арбитража (когда появляется возможность)

**Преимущества:**
- Постоянный заработок на спреде
- Готовность к арбитражным возможностям
- Создание ликвидности на рынке

## Параметры CLI

```bash
python real_trader.py [опции]

Обязательные:
  --market, -m      ID бинарного рынка (например: 3365)

Опциональные:
  --strategy, -s    Стратегия: dual_side, arbitrage, hybrid (по умолчанию: dual_side)
  --spread, -sp     Спред для MM (по умолчанию: 0.02 = 2%)
  --amount, -a      Размер ордера в USDT (по умолчанию: 5)
  --debug           Debug логирование
```

## Примеры

```bash
# Market Making с 3% спредом и ордерами по $10
python real_trader.py --market 3365 --strategy dual_side --spread 0.03 --amount 10

# Только арбитраж
python real_trader.py --market 3365 --strategy arbitrage

# Гибрид с debug
python real_trader.py --market 3365 --strategy hybrid --debug
```

## Комиссии Opinion Trade

| Тип ордера | Комиссия |
|------------|----------|
| **Maker** (лимит в книге) | **0%** ✅ |
| Taker (маркет ордер) | ~2% при price=0.5 |
| Минимальная taker | $0.50 |

**Формула taker fee:**
```
fee = topic_rate × price × (1 - price) × amount
```

## Требования

- Бинарные рынки (только YES и NO)
- Минимальный ордер: **$5 USDT**
- Цены: **0.01 - 0.99**
- Баланс на кошельке: USDT + BNB для gas

## Конфигурация .env

```env
# Обязательные
PRIVATE_KEY=0x...your_private_key...
MULTISIG_WALLET=0x...your_wallet_address...
APIKEY=your_opinion_api_key

# Опциональные
HOST=https://proxy.opinion.trade:8443
CHAIN_ID=56
RPC_URL=https://bsc-dataseed.binance.org/
```

## Безопасность

⚠️ **ВАЖНО:**
- Никогда не публикуйте PRIVATE_KEY
- Используйте отдельный кошелек для торговли
- Начните с минимальных сумм
- Тестируйте на небольших рынках

## Остановка

- **Ctrl+C** - graceful shutdown
- Бот автоматически отменит все открытые ордера

## Файлы проекта

| Файл | Описание |
|------|----------|
| `real_trader.py` | Реальный торговый бот v3.0 |
| `bot_v2.py` | Старый бот (deprecated) |
| `find_binary_markets.py` | Поиск бинарных рынков |
| `opinion_openapi.py` | API клиент для чтения данных |
| `config.py` | Загрузка конфигурации из .env |
