"""
Конфигурация проекта Opinion Trade Market Maker Bot
Загружает параметры из .env файла
"""

import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# =============================================================================
# НАСТРОЙКИ ПОДКЛЮЧЕНИЯ
# =============================================================================

HOST = os.getenv('HOST', 'https://proxy.opinion.trade:8443')
APIKEY = os.getenv('APIKEY', '')
RPC_URL = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/')
CHAIN_ID = int(os.getenv('CHAIN_ID', '56'))
PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')
MULTISIG_WALLET = os.getenv('MULTISIG_WALLET', '')

# =============================================================================
# НАСТРОЙКИ РЫНКА
# =============================================================================

MARKET_ID = int(os.getenv('MARKET_ID', '55'))
TOKEN_ID = os.getenv('TOKEN_ID', 'token_yes')

# =============================================================================
# НАСТРОЙКИ ОРДЕРОВ
# =============================================================================

BID_AMOUNT = float(os.getenv('BID_AMOUNT', '100.0'))
ASK_AMOUNT = float(os.getenv('ASK_AMOUNT', '100.0'))

# =============================================================================
# НАСТРОЙКИ СТРАТЕГИИ
# =============================================================================

SPREAD_OFFSET = float(os.getenv('SPREAD_OFFSET', '0.10'))
MIN_PRICE_MOVE = float(os.getenv('MIN_PRICE_MOVE', '0.01'))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '30'))

# =============================================================================
# ВАЛИДАЦИЯ КОНФИГУРАЦИИ
# =============================================================================

def validate_config():
    """
    Проверяет корректность конфигурации
    """
    errors = []
    
    if not PRIVATE_KEY or PRIVATE_KEY == 'your_private_key_here':
        errors.append("❌ PRIVATE_KEY не задан в .env файле")
    
    if not MULTISIG_WALLET or MULTISIG_WALLET == 'your_wallet_address_here':
        errors.append("❌ MULTISIG_WALLET не задан в .env файле")
    
    if MARKET_ID <= 0:
        errors.append("❌ MARKET_ID должен быть больше 0")
    
    if not TOKEN_ID:
        errors.append("❌ TOKEN_ID не задан")
    
    if BID_AMOUNT <= 0:
        errors.append("❌ BID_AMOUNT должен быть больше 0")
    
    if ASK_AMOUNT <= 0:
        errors.append("❌ ASK_AMOUNT должен быть больше 0")
    
    if not (0 < SPREAD_OFFSET < 1):
        errors.append("❌ SPREAD_OFFSET должен быть между 0 и 1")
    
    if MIN_PRICE_MOVE <= 0:
        errors.append("❌ MIN_PRICE_MOVE должен быть больше 0")
    
    if CHECK_INTERVAL <= 0:
        errors.append("❌ CHECK_INTERVAL должен быть больше 0")
    
    return errors


def print_config():
    """
    Выводит текущую конфигурацию
    """
    print("=" * 80)
    print("⚙️  КОНФИГУРАЦИЯ БОТА")
    print("=" * 80)
    print(f"🌐 Host: {HOST}")
    print(f"🔗 Chain ID: {CHAIN_ID}")
    print(f"🔌 RPC URL: {RPC_URL}")
    print(f"👛 Wallet: {MULTISIG_WALLET[:10]}...{MULTISIG_WALLET[-6:] if MULTISIG_WALLET else ''}")
    print(f"📊 Market ID: {MARKET_ID}")
    print(f"🎯 Token ID: {TOKEN_ID}")
    print(f"💰 BID Amount: {BID_AMOUNT} USDT")
    print(f"💰 ASK Amount: {ASK_AMOUNT} tokens")
    print(f"📏 Spread Offset: {SPREAD_OFFSET * 100:.1f}%")
    print(f"📐 Min Price Move: {MIN_PRICE_MOVE * 100:.1f}%")
    print(f"⏱️  Check Interval: {CHECK_INTERVAL} seconds")
    print("=" * 80)