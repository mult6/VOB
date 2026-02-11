#!/usr/bin/env python3
"""
Opinion Trade Bot - Скрипт упаковки для продажи
================================================

Создаёт чистый ZIP-архив с ботом без приватных данных.

Использование:
    python package_bot.py
    python package_bot.py --output my_bot.zip
    python package_bot.py --version 3.1
"""

import os
import sys
import zipfile
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================

# Файлы для включения в архив
INCLUDE_FILES = [
    # Основной бот
    'real_trader.py',
    'opinion_openapi.py',
    'config.py',
    
    # Утилиты
    'find_binary_markets.py',
    'init_split.py',
    'merge_tokens.py',
    
    # Конфиг (example, не .env!)
    '.env.example',
    
    # Документация
    'README.md',
    'QUICKSTART.md',
    'REAL_TRADER_GUIDE.md',
    'FAQ.md',
    
    # Зависимости
    'requirements.txt',
]

# Папки для включения (рекурсивно)
INCLUDE_DIRS = [
    # SDK если локальная копия
    # 'opinion_clob_sdk',
]

# Файлы/паттерны для ИСКЛЮЧЕНИЯ (даже если в INCLUDE_DIRS)
EXCLUDE_PATTERNS = [
    '.env',              # Приватные данные!
    '.git',
    '__pycache__',
    '*.pyc',
    '*.pyo',
    '.vscode',
    '.idea',
    'venv',
    'node_modules',
    '*.log',
    'bot_state*.json',
    'telegram_bot',      # Телеграм бот - отдельный продукт
    'web',               # Веб интерфейс - отдельный продукт
    'web_*.py',
    'presigned_*.py',
    '*.zip',
    '*.rar',
    '*.7z',
    'package_bot.py',    # Сам этот скрипт
]

# =============================================================================
# ФУНКЦИИ
# =============================================================================

def should_exclude(path: str) -> bool:
    """Проверить, нужно ли исключить файл/папку"""
    name = os.path.basename(path)
    
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith('*'):
            # Паттерн с wildcard
            if name.endswith(pattern[1:]):
                return True
        elif pattern in path or name == pattern:
            return True
    
    return False


def create_clean_env_example(source_path: str, temp_dir: str) -> str:
    """Создать чистый .env.example без реальных данных"""
    
    clean_content = '''# =============================================================================
# Opinion Trade Market Maker Bot - Конфигурация
# =============================================================================

# Скопируйте этот файл в .env и заполните своими значениями

# =============================================================================
# ПОДКЛЮЧЕНИЕ К OPINION TRADE
# =============================================================================

# API ключ от Opinion Trade (получите на https://app.opinion.trade -> Profile -> API Keys)
APIKEY=your_api_key_here

# Хост API (не меняйте)
HOST=https://proxy.opinion.trade:8443

# =============================================================================
# WEB3 НАСТРОЙКИ (для реальной торговли)
# =============================================================================

# RPC URL для BSC (Binance Smart Chain)
# Можете использовать публичный или свой узел
RPC_URL=https://bsc-dataseed.binance.org/

# Chain ID (56 = BSC Mainnet)
CHAIN_ID=56

# Приватный ключ вашего кошелька (БЕЗ префикса 0x!)
# ⚠️ ВАЖНО: Никогда не публикуйте этот ключ!
# Получите его из MetaMask: Настройки -> Безопасность -> Показать приватный ключ
PRIVATE_KEY=your_private_key_without_0x_prefix

# Адрес кошелька (с префиксом 0x)
# Это ваш публичный адрес кошелька
MULTISIG_WALLET=0xYourWalletAddressHere

# =============================================================================
# ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ (опционально)
# =============================================================================

# Включить debug логирование (true/false)
DEBUG=false

# Интервал между циклами в секундах (по умолчанию 30)
# CHECK_INTERVAL=30

# Спред по умолчанию в процентах (0.02 = 2%)
# DEFAULT_SPREAD=0.02

# Размер ордера по умолчанию в USDT
# ORDER_AMOUNT=5.0
'''
    
    dest_path = os.path.join(temp_dir, '.env.example')
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(clean_content)
    
    return dest_path


def create_readme_for_buyers(temp_dir: str, version: str) -> str:
    """Создать README для покупателей"""
    
    content = f'''# 🤖 Opinion Trade Market Maker Bot v{version}

## 🚀 Быстрый старт

### 1. Установка Python
Убедитесь что установлен Python 3.10 или выше:
```bash
python --version
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка .env
```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Отредактируйте .env и добавьте свои данные:
# - APIKEY: ваш API ключ от Opinion Trade
# - PRIVATE_KEY: приватный ключ кошелька (БЕЗ 0x)
# - MULTISIG_WALLET: адрес вашего кошелька (с 0x)
```

### 4. Запуск бота
```bash
# Интерактивный режим (выбор рынка и стратегии)
python real_trader.py

# Или с параметрами
python real_trader.py --market 3365 --strategy dual_side --spread 0.02 --amount 10
```

## 📊 Стратегии

### 1. Dual Side (Market Making)
```bash
python real_trader.py --strategy dual_side
```
- Размещает BID и ASK ордера со спредом
- Зарабатывает на разнице между покупкой и продажей
- Maker Fee = 0% (бесплатно!)

### 2. Arbitrage
```bash
python real_trader.py --strategy arbitrage
```
- Ищет арбитражные возможности: YES + NO < $1 или > $1
- Мгновенная прибыль без риска

### 3. Hybrid (70% MM + 30% Arbitrage)
```bash
python real_trader.py --strategy hybrid
```
- Комбинация обеих стратегий
- 70% баланса на market making
- 30% резерв для арбитража

## 🛠 Дополнительные команды

```bash
# Поиск активных рынков
python find_binary_markets.py

# Split $1 → YES + NO токены
python init_split.py --market 3365 --amount 10

# Merge YES + NO → $1
python merge_tokens.py --market 3365
```

## ⚙️ Параметры запуска

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| --market, -m | ID рынка | Интерактивный выбор |
| --strategy, -s | Стратегия (dual_side/arbitrage/hybrid) | dual_side |
| --spread, -sp | Спред для MM (0.01-0.10) | 0.02 (2%) |
| --amount, -a | Размер ордера в USDT | 5.0 |
| --debug | Включить debug логи | false |

## 💰 Требования к балансу

- Минимум: $10 USDT (для 2 ордеров по $5)
- Рекомендуемо: $50-100 USDT для стабильной работы

## 📞 Поддержка

По вопросам обращайтесь: @your_telegram_username

---
Дата сборки: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Версия: {version}
'''
    
    dest_path = os.path.join(temp_dir, 'README.md')
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return dest_path


def package_bot(output_path: str, version: str, source_dir: str) -> bool:
    """
    Создать ZIP архив с ботом
    
    Args:
        output_path: Путь к выходному ZIP файлу
        version: Версия бота
        source_dir: Исходная директория
        
    Returns:
        True если успешно
    """
    print(f"\n{'='*60}")
    print(f"📦 УПАКОВКА Opinion Trade Bot v{version}")
    print(f"{'='*60}\n")
    
    # Создаём временную директорию
    temp_dir = os.path.join(source_dir, '_package_temp')
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    try:
        files_added = []
        
        # 1. Копируем файлы
        print("📋 Копирование файлов...")
        
        for filename in INCLUDE_FILES:
            src = os.path.join(source_dir, filename)
            
            if os.path.exists(src):
                # Специальная обработка .env.example (не исключать!)
                if filename == '.env.example':
                    create_clean_env_example(src, temp_dir)
                    files_added.append('.env.example')
                    print(f"   ✅ {filename} (очищен)")
                    continue
                
                if should_exclude(filename):
                    print(f"   ⏭️ Пропуск: {filename}")
                    continue
                
                dest = os.path.join(temp_dir, filename)
                shutil.copy2(src, dest)
                files_added.append(filename)
                print(f"   ✅ {filename}")
            else:
                print(f"   ⚠️ Не найден: {filename}")
        
        # 2. Создаём кастомный README
        print("\n📝 Создание README для покупателей...")
        create_readme_for_buyers(temp_dir, version)
        files_added.append('README.md (custom)')
        
        # 3. Копируем папки
        for dirname in INCLUDE_DIRS:
            src_dir = os.path.join(source_dir, dirname)
            if os.path.exists(src_dir) and os.path.isdir(src_dir):
                dest_dir = os.path.join(temp_dir, dirname)
                
                def copy_filter(src, names):
                    return [n for n in names if should_exclude(n)]
                
                shutil.copytree(src_dir, dest_dir, ignore=copy_filter)
                files_added.append(f"{dirname}/")
                print(f"   ✅ {dirname}/ (директория)")
        
        # 4. Создаём ZIP
        print(f"\n📦 Создание архива: {output_path}")
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        
        # 5. Статистика
        zip_size = os.path.getsize(output_path)
        print(f"\n{'='*60}")
        print(f"✅ АРХИВ СОЗДАН УСПЕШНО!")
        print(f"{'='*60}")
        print(f"   📁 Файл: {output_path}")
        print(f"   📊 Размер: {zip_size / 1024:.1f} KB")
        print(f"   📋 Файлов: {len(files_added)}")
        print(f"   🏷️ Версия: {version}")
        print(f"{'='*60}\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        return False
        
    finally:
        # Очистка
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Упаковка Opinion Trade Bot для продажи'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Путь к выходному ZIP файлу'
    )
    
    parser.add_argument(
        '--version', '-v',
        type=str,
        default='3.0',
        help='Версия бота (по умолчанию: 3.0)'
    )
    
    args = parser.parse_args()
    
    # Определяем пути
    source_dir = os.path.dirname(os.path.abspath(__file__))
    
    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        output_path = os.path.join(
            source_dir, 
            f'opinion_trade_bot_v{args.version}_{timestamp}.zip'
        )
    
    # Упаковываем
    success = package_bot(output_path, args.version, source_dir)
    
    if success:
        print("🎉 Готово! Архив можно отправлять покупателю.")
    else:
        print("❌ Не удалось создать архив.")
        sys.exit(1)


if __name__ == "__main__":
    main()
