"""
Слияние YES + NO токенов обратно в USDT
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
║          OPINION TRADE - СЛИЯНИЕ ТОКЕНОВ                  ║
║                                                            ║
║  Этот скрипт объединит YES + NO токены обратно в USDT    ║
╚════════════════════════════════════════════════════════════╝
""")

# Включить торговлю
try:
    client.enable_trading()
    logger.info("✅ Торговля активирована")
except Exception as e:
    logger.info(f"ℹ️  Торговля уже активирована: {e}")

# Получить позиции
logger.info("📊 Получение позиций...")
positions_resp = client.get_my_positions(page=1, limit=10)
if positions_resp.errno != 0:
    logger.error(f"❌ Ошибка получения позиций: {positions_resp.errmsg}")
    exit(1)

if not hasattr(positions_resp.result, 'list'):
    logger.error("⚠️  Нет данных о позициях")
    exit(1)

positions = positions_resp.result.list
market_1463_positions = {
    "YES": None,
    "NO": None
}

for pos in positions:
    if pos.market_id == MARKET_ID:
        if pos.outcome_side_enum == "Yes":
            market_1463_positions["YES"] = pos
        elif pos.outcome_side_enum == "No":
            market_1463_positions["NO"] = pos

yes_balance = float(market_1463_positions["YES"].shares_owned) if market_1463_positions["YES"] else 0
no_balance = float(market_1463_positions["NO"].shares_owned) if market_1463_positions["NO"] else 0

logger.info(f"💰 Текущие позиции на рынке {MARKET_ID}:")
logger.info(f"   YES: {yes_balance}")
logger.info(f"   NO: {no_balance}")

if yes_balance < 0.01 and no_balance < 0.01:
    logger.info("✅ Токенов уже нет, слияние не требуется")
    exit(0)

# Минимум - то, что меньше
merge_amount = min(yes_balance, no_balance)

if merge_amount < 0.01:
    logger.warning(f"⚠️  Недостаточно токенов для слияния: мин={merge_amount}")
    exit(0)

logger.info(f"🔄 Слияние {merge_amount:.4f} YES и {merge_amount:.4f} NO...")

# Если YES позиция существует, используем её данные
if market_1463_positions["YES"]:
    yes_pos = market_1463_positions["YES"]
else:
    logger.error("❌ Позиция YES не найдена")
    exit(1)

# Слияние: продаем YES по цене 1.0 + покупаем NO по цене 0.0
# Результат: получаем ~merge_amount USDT

try:
    # Шаг 1: Продать YES
    logger.info(f"📍 Шаг 1: Продажа {merge_amount:.4f} YES @ 1.0...")
    
    place_order_input = PlaceOrderDataInput(
        market_id=MARKET_ID,
        price=1.0,
        size=merge_amount,
        side=OrderSide.SELL,  # Продаем YES (то же самое, что BID для NO)
        order_type=LIMIT_ORDER,
        outcome=yes_pos.token_id
    )
    
    order_resp = client.place_order(place_order_input)
    if order_resp.errno != 0:
        logger.error(f"❌ Ошибка при размещении ордера SELL YES: {order_resp.errmsg}")
        exit(1)
    
    order_id = order_resp.result.id if hasattr(order_resp.result, 'id') else str(order_resp.result)
    logger.info(f"✅ Ордер размещен: {order_id}")
    
    # Дождаться исполнения
    time.sleep(2)
    
    # Шаг 2: Продать NO (обратное действие)
    logger.info(f"📍 Шаг 2: Покупка {merge_amount:.4f} NO @ 0.0...")
    
    if market_1463_positions["NO"]:
        no_pos = market_1463_positions["NO"]
        place_order_input = PlaceOrderDataInput(
            market_id=MARKET_ID,
            price=0.0,
            size=merge_amount,
            side=OrderSide.BUY,  # Покупаем NO
            order_type=LIMIT_ORDER,
            outcome=no_pos.token_id
        )
        
        order_resp = client.place_order(place_order_input)
        if order_resp.errno != 0:
            logger.error(f"❌ Ошибка при размещении ордера BUY NO: {order_resp.errmsg}")
            exit(1)
        
        order_id = order_resp.result.id if hasattr(order_resp.result, 'id') else str(order_resp.result)
        logger.info(f"✅ Ордер размещен: {order_id}")
    
    time.sleep(2)
    
    # Проверить новый баланс
    logger.info("📊 Проверка результата...")
    positions_resp = client.get_my_positions(page=1, limit=10)
    
    for pos in positions_resp.result.list:
        if pos.market_id == MARKET_ID:
            balance = float(pos.shares_owned)
            if pos.outcome_side_enum == "Yes":
                logger.info(f"   YES: {balance}")
            elif pos.outcome_side_enum == "No":
                logger.info(f"   NO: {balance}")
    
    logger.info("✅ Слияние завершено!")

except Exception as e:
    logger.error(f"❌ Ошибка при слиянии: {e}")
    import traceback
    traceback.print_exc()
