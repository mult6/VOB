"""
Opinion Trade Bot - Pre-signed Orders Handler
==============================================

Серверная часть для работы с предварительно подписанными ордерами.

Процесс:
1. Пользователь подписывает пачку ордеров в браузере
2. Ордера загружаются на сервер
3. Бот автоматически использует их при хороших условиях
4. Пользователь может спать - бот торгует сам

БЕЗОПАСНОСТЬ:
✅ Приватный ключ никогда не покидает кошелек
✅ Ордера имеют срок действия
✅ Ограниченное количество ордеров
✅ Пользователь контролирует параметры
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
import json
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])

# =============================================================================
# МОДЕЛИ ДАННЫХ
# =============================================================================

class SignedOrder(BaseModel):
    """
    Подписанный ордер от пользователя
    
    Структура соответствует CTF Exchange контракту Opinion Trade
    """
    # Основные поля ордера
    salt: str
    maker: str
    signer: str
    taker: str = "0x0000000000000000000000000000000000000000"
    tokenId: str
    makerAmount: str
    takerAmount: str
    expiration: int
    nonce: str
    feeRateBps: int = 0
    side: int  # 0 = BUY, 1 = SELL
    signatureType: int = 0  # 0 = EOA
    signature: str
    
    # Дополнительные поля для удобства
    price: float = 0.0
    amount: float = 0.0
    used: bool = False

class OrdersUpload(BaseModel):
    """Загрузка пачки ордеров"""
    wallet_address: str
    orders: Dict  # buyYes, buyNo, sellYes, sellNo
    timestamp: int

class OrdersCancel(BaseModel):
    """Отмена ордеров"""
    wallet_address: str

# =============================================================================
# ХРАНИЛИЩЕ ОРДЕРОВ (В продакшене использовать Redis/PostgreSQL)
# =============================================================================

# Структура: { wallet_address: { marketId: { orders... } } }
orders_storage: Dict[str, Dict] = {}

# Файл для сохранения между перезапусками
ORDERS_FILE = Path(__file__).parent / "presigned_orders.json"

def load_orders():
    """Загрузить ордера из файла"""
    global orders_storage
    if ORDERS_FILE.exists():
        try:
            orders_storage = json.loads(ORDERS_FILE.read_text())
            logger.info(f"Загружено {len(orders_storage)} кошельков с ордерами")
        except Exception as e:
            logger.error(f"Ошибка загрузки ордеров: {e}")
            orders_storage = {}

def save_orders():
    """Сохранить ордера в файл"""
    try:
        ORDERS_FILE.write_text(json.dumps(orders_storage, indent=2))
    except Exception as e:
        logger.error(f"Ошибка сохранения ордеров: {e}")

# Загружаем при старте
load_orders()

# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post("/upload")
async def upload_orders(data: OrdersUpload):
    """
    Загрузить подписанные ордера на сервер
    """
    wallet = data.wallet_address.lower()
    
    # Считаем ордера
    total = 0
    for key in ['buyYes', 'buyNo', 'sellYes', 'sellNo']:
        if key in data.orders:
            total += len(data.orders[key])
    
    if total == 0:
        raise HTTPException(400, "Нет ордеров для загрузки")
    
    # Проверяем срок действия первого ордера
    sample_order = None
    for key in ['buyYes', 'buyNo', 'sellYes', 'sellNo']:
        if data.orders.get(key):
            sample_order = data.orders[key][0]
            break
    
    if sample_order:
        expiry = sample_order.get('expiry', 0)
        if expiry < datetime.now().timestamp():
            raise HTTPException(400, "Ордера уже истекли")
    
    # Сохраняем
    if wallet not in orders_storage:
        orders_storage[wallet] = {}
    
    market_id = str(data.orders.get('marketId', 'default'))
    orders_storage[wallet][market_id] = {
        'orders': data.orders,
        'uploaded_at': datetime.now().isoformat(),
        'total': total,
        'used': 0
    }
    
    save_orders()
    
    logger.info(f"✅ Загружено {total} ордеров для {wallet[:10]}... на рынок {market_id}")
    
    return {
        "status": "success",
        "wallet_address": wallet,
        "total_orders": total,
        "market_id": market_id,
        "message": f"Загружено {total} ордеров"
    }


@router.get("/status/{wallet_address}")
async def get_orders_status(wallet_address: str):
    """
    Получить статус ордеров пользователя
    """
    wallet = wallet_address.lower()
    
    if wallet not in orders_storage:
        return {
            "wallet_address": wallet,
            "has_orders": False,
            "markets": []
        }
    
    markets = []
    for market_id, data in orders_storage[wallet].items():
        # Считаем неиспользованные
        remaining = 0
        expired = 0
        now = datetime.now().timestamp()
        
        for key in ['buyYes', 'buyNo', 'sellYes', 'sellNo']:
            orders = data['orders'].get(key, [])
            for order in orders:
                if order.get('used'):
                    continue
                # Проверяем expiration (новый формат) или expiry (старый)
                expiration = order.get('expiration', order.get('expiry', 0))
                if expiration < now:
                    expired += 1
                else:
                    remaining += 1
        
        markets.append({
            "market_id": market_id,
            "total": data.get('total', 0),
            "used": data.get('used', 0),
            "remaining": remaining,
            "expired": expired,
            "uploaded_at": data.get('uploaded_at')
        })
    
    return {
        "wallet_address": wallet,
        "has_orders": len(markets) > 0,
        "markets": markets
    }


@router.post("/cancel")
async def cancel_orders(data: OrdersCancel):
    """
    Отменить все неиспользованные ордера
    """
    wallet = data.wallet_address.lower()
    
    if wallet not in orders_storage:
        raise HTTPException(404, "Ордера не найдены")
    
    # Считаем сколько отменили
    cancelled = 0
    for market_id, market_data in orders_storage[wallet].items():
        for key in ['buyYes', 'buyNo', 'sellYes', 'sellNo']:
            orders = market_data['orders'].get(key, [])
            for order in orders:
                if not order.get('used'):
                    order['used'] = True
                    order['cancelled'] = True
                    cancelled += 1
    
    save_orders()
    
    logger.info(f"❌ Отменено {cancelled} ордеров для {wallet[:10]}...")
    
    return {
        "status": "cancelled",
        "wallet_address": wallet,
        "cancelled": cancelled
    }

# =============================================================================
# ФУНКЦИИ ДЛЯ БОТА
# =============================================================================

def get_best_order(wallet: str, market_id: str, side: int, token_type: str, target_price: float) -> Optional[dict]:
    """
    Найти лучший подходящий ордер
    
    Ищет среди подписанных ордеров тот, который:
    1. Не использован
    2. Не истёк
    3. Соответствует side и token_type
    4. Имеет цену ближайшую к target_price
    
    Args:
        wallet: Адрес кошелька
        market_id: ID рынка
        side: 0 = BUY, 1 = SELL
        token_type: 'yes' или 'no'
        target_price: Желаемая цена
    
    Returns:
        Подписанный ордер со всеми полями CTF Exchange или None
    """
    wallet = wallet.lower()
    
    if wallet not in orders_storage:
        return None
    
    if market_id not in orders_storage[wallet]:
        return None
    
    # Определяем ключ
    if side == 0:  # BUY
        key = 'buyYes' if token_type == 'yes' else 'buyNo'
    else:  # SELL
        key = 'sellYes' if token_type == 'yes' else 'sellNo'
    
    orders = orders_storage[wallet][market_id]['orders'].get(key, [])
    now = datetime.now().timestamp()
    
    best_order = None
    best_diff = float('inf')
    
    for order in orders:
        # Пропускаем использованные
        if order.get('used'):
            continue
        
        # Пропускаем истекшие (проверяем expiration, не expiry)
        expiration = order.get('expiration', order.get('expiry', 0))
        if expiration < now:
            continue
        
        # Ищем ближайшую цену
        order_price = order.get('price', 0)
        diff = abs(order_price - target_price)
        if diff < best_diff:
            best_diff = diff
            best_order = order
    
    return best_order


def mark_order_used(wallet: str, market_id: str, nonce: str):
    """
    Отметить ордер как использованный
    """
    wallet = wallet.lower()
    
    if wallet not in orders_storage:
        return
    
    if market_id not in orders_storage[wallet]:
        return
    
    for key in ['buyYes', 'buyNo', 'sellYes', 'sellNo']:
        orders = orders_storage[wallet][market_id]['orders'].get(key, [])
        for order in orders:
            if order.get('nonce') == nonce:
                order['used'] = True
                order['used_at'] = datetime.now().isoformat()
                orders_storage[wallet][market_id]['used'] = \
                    orders_storage[wallet][market_id].get('used', 0) + 1
                save_orders()
                return


def get_wallet_stats(wallet: str) -> dict:
    """
    Получить статистику ордеров пользователя
    """
    wallet = wallet.lower()
    
    if wallet not in orders_storage:
        return {"total": 0, "used": 0, "remaining": 0}
    
    total = 0
    used = 0
    
    for market_id, data in orders_storage[wallet].items():
        total += data.get('total', 0)
        used += data.get('used', 0)
    
    return {
        "total": total,
        "used": used,
        "remaining": total - used
    }
