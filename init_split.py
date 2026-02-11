"""
Инициализация - разделение USDT на YES + NO токены для торговли
Запустите этот скрипт ОДИН РАЗ перед использованием бота
"""
# -*- coding: utf-8 -*-

import time
import logging
from config import *
from opinion_clob_sdk import Client
from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализируем клиент
client = Client(
    host=HOST,
    apikey=APIKEY if APIKEY else "",
    chain_id=CHAIN_ID,
    rpc_url=RPC_URL,
    private_key=PRIVATE_KEY
)

print("""
╔════════════════════════════════════════════════════════════╗
║          OPINION TRADE - ИНИЦИАЛИЗАЦИЯ (SPLIT)            ║
║                                                            ║
║  Этот скрипт разделит USDT на YES + NO токены            ║
╚════════════════════════════════════════════════════════════╝
""")

# Включить торговлю
try:
    client.enable_trading()
    logger.info("✅ Торговля активирована")
except:
    logger.info("⚠️  Торговля уже активирована")

# Получить баланс
response = client.get_my_balances()
if response.errno != 0:
    logger.error(f"❌ Ошибка получения баланса: {response.errmsg}")
    exit(1)

balance_data = response.result
if not hasattr(balance_data, 'balances') or not balance_data.balances:
    logger.error("⚠️  Нет данных о балансе")
    exit(1)

balance = balance_data.balances[0]
available = float(getattr(balance, 'available_balance', 0))

logger.info(f"💰 Доступный баланс: {available:.2f} USDT")

if available < 1:
    logger.error(f"❌ Недостаточный баланс для split (нужно минимум 1 USDT)")
    exit(1)

# Запросить сумму
amount_str = input(f"\nСколько USDT разделить на YES+NO? (доступно {available:.2f}): ").strip()
try:
    amount = float(amount_str)
    if amount <= 0 or amount > available:
        logger.error(f"❌ Неверная сумма")
        exit(1)
except:
    logger.error("❌ Неверный формат числа")
    exit(1)

# Выполнить split
logger.info(f"\n💸 Разделение {amount} USDT на YES + NO токены...")

amount_wei = int(amount * 10**18)

logger.info(f"📝 Split параметры:")
logger.info(f"   Рынок: {MARKET_ID}")
logger.info(f"   Сумма: {amount} USDT ({amount_wei} wei)")

try:
    tx_hash, receipt, event = client.split(
        market_id=MARKET_ID,
        amount=amount_wei,
        check_approval=True
    )
    
    logger.info(f"✅ Split успешно выполнен!")
    logger.info(f"   TX Hash: {tx_hash.hex() if hasattr(tx_hash, 'hex') else tx_hash}")
    logger.info(f"   Gas used: {receipt.gasUsed if hasattr(receipt, 'gasUsed') else 'N/A'}")
    logger.info(f"📊 Теперь у вас должны быть ~{amount} YES + ~{amount} NO токенов")
    logger.info(f"\n✅ Инициализация завершена! Теперь можно запустить simple_bot.py")
    
except Exception as e:
    logger.error(f"❌ Ошибка split: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
