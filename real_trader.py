"""
Opinion Trade Real Trading Bot v3.1 - POINTS MAXIMIZER
=======================================================

ОПТИМИЗИРОВАНО ДЛЯ МАКСИМИЗАЦИИ ПОИНТОВ (PTS) и заработка на спредах!

СИСТЕМА ПОИНТОВ (из документации):
- Лимитные ордера БЛИЖЕ к рыночной цене = БОЛЬШЕ поинтов
- Размер ордера > $10 USDT = бонусные поинты
- Чем ДОЛЬШЕ ордер в стакане = больше поинтов  
- MAKER ордера дают больше поинтов чем TAKER
- Минимум $200 объёма в неделю для участия
- Удержание позиций (токенов) = дополнительные поинты

СТРАТЕГИИ:

1. DUAL_SIDE (Market Making) - ОСНОВНАЯ для поинтов
   - Ордера максимально близко к рынку (0.5-1% от лучшей цены)
   - Maker Fee = 0% (бесплатно!)
   - Постоянная ротация для набора объёма

2. ARBITRAGE (Арбитраж)
   - BUY_BOTH: если YES_ASK + NO_ASK < 1.00
   - SELL_BOTH: если YES_BID + NO_BID > 1.00

3. HYBRID (Гибрид) - 70% MM + 30% арбитраж

4. POINTS_MAX (НОВЫЙ!) - Максимизация поинтов
   - Агрессивное размещение ордеров близко к рынку
   - Частая ротация (каждые 10 сек)
   - Приоритет объёма над прибылью

5. SPLIT - Безрисковый фарминг поинтов
   - ФАЗА 1: Покупаем сразу YES и NO токены (по рыночной цене)
   - ФАЗА 2: Выставляем на продажу на +1 цент от лучшего ASK
   - Ордера стоят в очереди, фармят поинты, не исполняются
   - Независимо от исхода события - выходим в 0 или плюс
   - Идеально для максимизации поинтов без риска

Запуск:
    python real_trader.py --market 3365 --strategy split
    python real_trader.py --market 3365 --strategy points_max
    python real_trader.py --market 3365 --strategy dual_side
"""
# -*- coding: utf-8 -*-

import os
import sys
import time
import signal
import logging
import argparse
import requests
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Импорты Opinion SDK
from opinion_clob_sdk import Client
from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER
from opinion_openapi import OpinionOpenAPI

# WebSocket для real-time данных
try:
    from opinion_websocket import OpinionWebSocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️ WebSocket модуль не найден, используем только REST API")

# =============================================================================
# ⚙️ КОНСТАНТЫ
# =============================================================================

# Лимиты платформы
MIN_ORDER_USDT = 5.0        # Минимальный ордер $5
MIN_PRICE = 0.01            # Минимальная цена 1%
MAX_PRICE = 0.99            # Максимальная цена 99%
TICK_SIZE = 0.001           # Шаг цены
MAX_PRICE_DECIMALS = 4      # Максимум знаков после запятой

# Комиссии Opinion Trade
# Maker (лимит ордера в книге) = 0% БЕСПЛАТНО!
# Taker (маркет ордера) = topic_rate × price × (1-price)
MAKER_FEE = 0.0
TAKER_FEE_TOPIC_RATE = 0.08  # ~2% при price=0.5
MIN_TAKER_FEE = 0.50         # Минимум $0.50

# Стратегии
DEFAULT_SPREAD_PERCENT = 0.10  # 10% спред по умолчанию (безопаснее для низколиквидных рынков)
MIN_SPREAD_PERCENT = 0.05      # 5% минимальный спред
MAX_SPREAD_PERCENT = 0.20      # 20% максимальный спред
ADAPTIVE_SPREAD = True         # Адаптивный спред: автоматически увеличивать если рыночный спред большой
ARBITRAGE_MIN_PROFIT = 0.005   # 0.5% минимальная прибыль для арбитража
STALE_ORDER_THRESHOLD = 0.03   # 3% - порог для переразмещения ордера (было 5%)
REPLACE_STALE_IMMEDIATELY = True  # Сразу переразмещать устаревшие ордера

# Гибрид
HYBRID_DUAL_SIDE_PERCENT = 0.70  # 70% на маркет-мейкинг
HYBRID_ARBITRAGE_PERCENT = 0.30  # 30% резерв для арбитража

# Интервалы
CHECK_INTERVAL = 15  # Секунд между проверками для обычных стратегий
CHECK_INTERVAL_POINTS_MAX = 10  # Для points_max - чаще ротация = больше объёма

# === НАСТРОЙКИ МАКСИМИЗАЦИИ ПОИНТОВ ===
# Адаптивный спред на основе рыночных условий!
POINTS_SPREAD_MIN = 0.015      # 1.5% минимум (для ликвидных рынков)
POINTS_SPREAD_MAX = 0.05       # 5% максимум (для волатильных рынков)
POINTS_SPREAD_RATIO = 0.4      # Наш спред = 40% от рыночного спреда (оставляем себе маржу)
POINTS_MIN_ORDER_SIZE = 5.0    # Минимум $5 (снижено из-за низкого баланса)
POINTS_ROTATION_THRESHOLD = 0.02  # 2% - порог для переразмещения (чаще ротация)
POINTS_WEEKLY_TARGET = 200.0   # Минимум $200/неделю для участия в программе

# === НАСТРОЙКИ SPLIT СТРАТЕГИИ ===
# Безрисковый фарминг поинтов - покупаем YES и NO одновременно
SPLIT_OFFSET = 0.01            # Отступ от лучшего ASK (1 цент = 0.01)
SPLIT_MIN_ORDER_SIZE = 5.0     # Минимум $5 на каждый токен

# =============================================================================
# 📝 ЛОГИРОВАНИЕ
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def calculate_taker_fee(price: float, amount: float, topic_rate: float = TAKER_FEE_TOPIC_RATE) -> float:
    """
    Рассчитать комиссию taker.
    Fee = topic_rate × price × (1 - price) × amount
    """
    fee_rate = topic_rate * price * (1 - price)
    fee = amount * fee_rate
    return max(fee, MIN_TAKER_FEE)


def format_price(price: float) -> str:
    """Форматировать цену для API (максимум 4 знака)"""
    rounded = round(float(price), MAX_PRICE_DECIMALS)
    return f"{rounded:.{MAX_PRICE_DECIMALS}f}".rstrip('0').rstrip('.')


def validate_price(price: float) -> bool:
    """Проверить валидность цены"""
    return MIN_PRICE <= price <= MAX_PRICE


# =============================================================================
# 📊 СТРУКТУРЫ ДАННЫХ
# =============================================================================

@dataclass
class MarketInfo:
    """Информация о рынке"""
    market_id: int
    title: str
    status: str
    yes_token_id: str
    no_token_id: str
    volume_24h: float = 0.0
    yes_price: float = 0.0
    no_price: float = 0.0


@dataclass
class OrderInfo:
    """Информация об ордере"""
    order_id: str
    token: str      # 'YES' или 'NO'
    side: str       # 'BID' или 'ASK'
    price: float
    amount: float   # USDT
    tokens: float   # Количество токенов
    created_at: datetime = field(default_factory=datetime.now)
    status: str = 'open'


@dataclass 
class TradeInfo:
    """Исполненная сделка"""
    trade_id: str
    token: str
    side: str
    price: float
    amount: float
    tokens: float
    pnl: float = 0.0
    fee: float = 0.0
    executed_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# 🔍 ПОИСК РЫНКОВ
# =============================================================================

class MarketFinder:
    """Поиск и выбор бинарных рынков"""
    
    BASE_URL = "https://proxy.opinion.trade:8443/openapi"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': self.api_key,
            'Content-Type': 'application/json'
        })
    
    def get_binary_markets(self, max_pages: int = 3) -> List[MarketInfo]:
        """
        Получить список активных бинарных рынков
        
        Args:
            max_pages: Количество страниц для загрузки
            
        Returns:
            Список MarketInfo
        """
        markets = []
        
        for page in range(1, max_pages + 1):
            try:
                params = {
                    'page': page,
                    'limit': 20,
                    'status': 'activated',
                    'sortBy': 5  # По volume 24h
                }
                
                response = self.session.get(
                    f"{self.BASE_URL}/market",
                    params=params,
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                
                errno = data.get('errno', data.get('code', -1))
                if errno != 0:
                    break
                
                result = data.get('result', {})
                market_list = result.get('list', [])
                
                if not market_list:
                    break
                
                for m in market_list:
                    # Только бинарные рынки (marketType == 0)
                    if m.get('marketType', -1) != 0:
                        continue
                    
                    markets.append(MarketInfo(
                        market_id=m.get('marketId', 0),
                        title=m.get('marketTitle', 'Unknown'),
                        status=m.get('statusEnum', 'Unknown'),
                        yes_token_id=str(m.get('yesTokenId', '')),
                        no_token_id=str(m.get('noTokenId', '')),
                        volume_24h=float(m.get('volume24h', 0) or 0)
                    ))
                    
            except Exception as e:
                logger.error(f"Ошибка загрузки страницы {page}: {e}")
                break
        
        return markets
    
    def get_market_prices(self, market: MarketInfo) -> Tuple[float, float]:
        """Получить текущие цены YES и NO для рынка"""
        try:
            # YES orderbook
            resp = self.session.get(
                f"{self.BASE_URL}/token/orderbook",
                params={'token_id': market.yes_token_id},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('errno', data.get('code', -1)) == 0:
                    result = data.get('result', {})
                    asks = result.get('asks', [])
                    if asks:
                        market.yes_price = float(asks[0].get('price', 0))
            
            # NO orderbook
            resp = self.session.get(
                f"{self.BASE_URL}/token/orderbook",
                params={'token_id': market.no_token_id},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('errno', data.get('code', -1)) == 0:
                    result = data.get('result', {})
                    asks = result.get('asks', [])
                    if asks:
                        market.no_price = float(asks[0].get('price', 0))
            
            return market.yes_price, market.no_price
            
        except Exception as e:
            logger.debug(f"Ошибка получения цен для рынка {market.market_id}: {e}")
            return 0.0, 0.0


def select_market_interactive(api_key: str) -> Optional[int]:
    """
    Интерактивный выбор рынка
    
    Returns:
        market_id выбранного рынка или None
    """
    print("\n" + "="*70)
    print("🔍 ПОИСК БИНАРНЫХ РЫНКОВ")
    print("="*70)
    
    finder = MarketFinder(api_key)
    
    print("⏳ Загрузка рынков...")
    markets = finder.get_binary_markets(max_pages=3)
    
    if not markets:
        print("❌ Бинарные рынки не найдены")
        return None
    
    print(f"✅ Найдено {len(markets)} бинарных рынков\n")
    
    # Получаем цены для всех рынков
    print("⏳ Загрузка цен...")
    for market in markets:
        finder.get_market_prices(market)
    
    # Выводим таблицу
    print("\n" + "-"*70)
    print(f"{'#':<3} {'ID':<6} {'Название':<40} {'YES':>6} {'NO':>6} {'Vol24h':>8}")
    print("-"*70)
    
    for i, m in enumerate(markets, 1):
        title = m.title[:38] + ".." if len(m.title) > 40 else m.title
        yes_str = f"{m.yes_price:.2f}" if m.yes_price > 0 else "-"
        no_str = f"{m.no_price:.2f}" if m.no_price > 0 else "-"
        vol_str = f"${m.volume_24h/1000:.1f}k" if m.volume_24h >= 1000 else f"${m.volume_24h:.0f}"
        
        # Подсветка арбитражных возможностей
        arb_flag = ""
        if m.yes_price > 0 and m.no_price > 0:
            total = m.yes_price + m.no_price
            if total < 0.98:
                arb_flag = " 🎯"  # BUY_BOTH opportunity
            elif total > 1.02:
                arb_flag = " 💰"  # SELL_BOTH opportunity
        
        print(f"{i:<3} {m.market_id:<6} {title:<40} {yes_str:>6} {no_str:>6} {vol_str:>8}{arb_flag}")
    
    print("-"*70)
    print("🎯 = BUY_BOTH арбитраж | 💰 = SELL_BOTH арбитраж")
    print("-"*70)
    
    # Выбор
    while True:
        try:
            choice = input(f"\n📌 Введите номер рынка (1-{len(markets)}) или ID рынка, или 'q' для выхода: ").strip()
            
            if choice.lower() == 'q':
                return None
            
            num = int(choice)
            
            # Если это номер в списке
            if 1 <= num <= len(markets):
                selected = markets[num - 1]
                print(f"\n✅ Выбран рынок #{selected.market_id}: {selected.title}")
                return selected.market_id
            
            # Если это ID рынка
            for m in markets:
                if m.market_id == num:
                    print(f"\n✅ Выбран рынок #{m.market_id}: {m.title}")
                    return m.market_id
            
            # Если ID не в списке, но может существовать
            if num > 100:
                confirm = input(f"⚠️ Рынок #{num} не в списке. Использовать? (y/n): ").strip().lower()
                if confirm == 'y':
                    return num
            
            print("❌ Неверный выбор. Попробуйте снова.")
            
        except ValueError:
            print("❌ Введите число.")
        except KeyboardInterrupt:
            return None


# =============================================================================
# 🤖 РЕАЛЬНЫЙ ТРЕЙДЕР
# =============================================================================

class RealTrader:
    """
    Реальный торговый бот для Opinion Trade
    
    Поддерживает три стратегии:
    1. dual_side - Market Making (BID/ASK со спредом)
    2. arbitrage - Арбитраж (BUY_BOTH / SELL_BOTH)
    3. hybrid - Гибрид (70% MM + 30% арбитраж)
    """
    
    def __init__(
        self,
        market_id: int,
        strategy: str = 'dual_side',
        spread_percent: float = DEFAULT_SPREAD_PERCENT,
        order_amount: float = 5.0
    ):
        """
        Args:
            market_id: ID бинарного рынка
            strategy: 'dual_side', 'arbitrage', или 'hybrid'
            spread_percent: Спред для market making (0.01-0.10)
            order_amount: Размер ордера в USDT (минимум 5)
        """
        self.market_id = market_id
        self.strategy = strategy
        self.spread_percent = max(0.005, min(0.10, spread_percent))
        self.order_amount = max(MIN_ORDER_USDT, order_amount)
        
        # Загружаем конфигурацию из .env
        self.host = os.getenv('HOST', 'https://proxy.opinion.trade:8443')
        self.apikey = os.getenv('APIKEY', '')
        self.private_key = os.getenv('PRIVATE_KEY', '')
        self.multisig_wallet = os.getenv('MULTISIG_WALLET', '')
        self.chain_id = int(os.getenv('CHAIN_ID', '56'))
        self.rpc_url = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/')
        
        # Проверка конфигурации
        if not self.private_key:
            raise ValueError("❌ PRIVATE_KEY не установлен в .env")
        if not self.multisig_wallet:
            raise ValueError("❌ MULTISIG_WALLET не установлен в .env")
        
        # Инициализация SDK Client
        logger.info("🔧 Инициализация Opinion SDK Client...")
        
        private_key_hex = self.private_key
        if private_key_hex.startswith('0x'):
            private_key_hex = private_key_hex[2:]
        
        self.client = Client(
            host=self.host,
            apikey=self.apikey,
            chain_id=self.chain_id,
            rpc_url=self.rpc_url,
            private_key=private_key_hex,
            multi_sig_addr=self.multisig_wallet
        )
        
        # OpenAPI для чтения данных
        self.openapi = OpinionOpenAPI(self.apikey)
        
        # Информация о рынке
        self.market_info = None
        self.yes_token_id = None
        self.no_token_id = None
        
        # Балансы
        self.usdt_balance = 0.0
        self.yes_balance = 0.0
        self.no_balance = 0.0
        self.initial_balance = None
        
        # Ордера
        self.orders: Dict[str, OrderInfo] = {}
        self._order_counter = 0
        
        # Отслеживание активных ордеров (локально, т.к. API может не работать)
        self.active_yes_ask = False
        self.active_no_ask = False
        self.active_yes_bid = False
        self.active_no_bid = False
        
        # Цены активных ордеров (для проверки stale)
        self.active_order_prices = {
            'YES_BID': None,
            'YES_ASK': None,
            'NO_BID': None,
            'NO_ASK': None
        }
        
        # ID активных ордеров
        self.active_order_ids = {
            'YES_BID': None,
            'YES_ASK': None,
            'NO_BID': None,
            'NO_ASK': None
        }
        
        # Предыдущие балансы для отслеживания исполнения
        self.prev_usdt_balance = None
        self.prev_yes_balance = None
        self.prev_no_balance = None
        
        # === ЗАЩИТА ОТ УБЫТКОВ: отслеживание средней цены покупки ===
        self.yes_avg_buy_price = None  # Средняя цена покупки YES
        self.no_avg_buy_price = None   # Средняя цена покупки NO
        self.yes_total_cost = 0.0      # Общие затраты на YES
        self.no_total_cost = 0.0       # Общие затраты на NO
        
        # Статистика
        self.trades: List[TradeInfo] = []
        self.total_pnl = 0.0
        self.arbitrage_profit = 0.0
        self.arbitrage_trades = 0
        
        # === СТАТИСТИКА ДЛЯ ПОИНТОВ ===
        self.total_volume = 0.0          # Общий объём торгов
        self.session_volume = 0.0        # Объём за текущую сессию
        self.orders_placed = 0           # Количество размещённых ордеров
        self.orders_filled = 0           # Количество исполненных ордеров
        self.session_start = datetime.now()
        
        # Состояние
        self.running = False
        self.cycles = 0
        
        # === WEBSOCKET для real-time данных ===
        self.ws: Optional['OpinionWebSocket'] = None
        self.use_websocket = False  # Активируется после подключения
        
        # Интервал проверки зависит от стратегии
        self.check_interval = CHECK_INTERVAL_POINTS_MAX if strategy in ('points_max', 'split') else CHECK_INTERVAL
        
        logger.info(f"✅ RealTrader инициализирован")
        logger.info(f"   Рынок: #{market_id}")
        logger.info(f"   Стратегия: {strategy}")
        logger.info(f"   Спред: {spread_percent*100:.1f}%")
        logger.info(f"   Размер ордера: ${order_amount:.2f}")
        if strategy == 'points_max':
            logger.info(f"   🎯 РЕЖИМ МАКСИМИЗАЦИИ ПОИНТОВ!")
            logger.info(f"   📊 Интервал: {self.check_interval} сек (агрессивная ротация)")
    
    # =========================================================================
    # ИНИЦИАЛИЗАЦИЯ РЫНКА
    # =========================================================================
    
    def load_market_info(self) -> bool:
        """Загрузить информацию о бинарном рынке"""
        try:
            logger.info(f"📊 Загрузка информации о рынке #{self.market_id}...")
            
            response = self.openapi.get_market(self.market_id)
            
            if response.get('code') != 0:
                logger.error(f"❌ Ошибка загрузки рынка: {response.get('msg')}")
                return False
            
            market = response.get('result', {}).get('data', {})
            
            if not market:
                logger.error(f"❌ Рынок #{self.market_id} не найден")
                return False
            
            # Проверяем что это бинарный рынок
            market_type = market.get('marketType', -1)
            if market_type != 0:
                logger.error(f"❌ Рынок #{self.market_id} не бинарный (type={market_type})")
                return False
            
            # Извлекаем token IDs - они хранятся напрямую в полях yesTokenId/noTokenId
            self.yes_token_id = str(market.get('yesTokenId', ''))
            self.no_token_id = str(market.get('noTokenId', ''))
            
            # Fallback: проверяем массив tokens если нет прямых полей
            if not self.yes_token_id or not self.no_token_id:
                tokens = market.get('tokens', [])
                for token in tokens:
                    outcome = token.get('outcome', '')
                    token_id = str(token.get('tokenId', ''))
                    
                    if outcome.lower() == 'yes':
                        self.yes_token_id = token_id
                    elif outcome.lower() == 'no':
                        self.no_token_id = token_id
            
            if not self.yes_token_id or not self.no_token_id:
                logger.error(f"❌ Не удалось найти YES/NO токены")
                return False
            
            self.market_info = {
                'market_id': self.market_id,
                'title': market.get('marketTitle', 'Unknown'),
                'status': market.get('statusEnum', 'Unknown'),
                'end_time': market.get('endTime', 'Unknown'),
                'yes_token_id': self.yes_token_id,
                'no_token_id': self.no_token_id
            }
            
            logger.info(f"✅ Рынок загружен: {self.market_info['title']}")
            logger.info(f"   YES Token: {self.yes_token_id[:20]}...")
            logger.info(f"   NO Token: {self.no_token_id[:20]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки рынка: {e}")
            return False
    
    def enable_trading(self) -> bool:
        """Активировать торговлю на платформе"""
        try:
            self.client.enable_trading()
            logger.info("✅ Торговля активирована")
            return True
        except:
            logger.info("⚠️ Торговля уже активирована")
            return True
    
    # =========================================================================
    # БАЛАНСЫ
    # =========================================================================
    
    def get_usdt_balance(self) -> float:
        """Получить баланс USDT"""
        try:
            response = self.client.get_my_balances()
            
            if response.errno != 0:
                logger.error(f"Ошибка получения баланса: {response.errmsg}")
                return 0.0
            
            balance_data = response.result
            if not hasattr(balance_data, 'balances') or not balance_data.balances:
                return 0.0
            
            # USDT на BNB Chain
            usdt_address = '55d398326f99059ff775485246999027b3197955'
            
            for bal in balance_data.balances:
                quote_token = getattr(bal, 'quote_token', '').lower()
                if usdt_address in quote_token:
                    self.usdt_balance = float(getattr(bal, 'available_balance', 0))
                    break
            else:
                # Fallback: первый баланс
                self.usdt_balance = float(getattr(balance_data.balances[0], 'available_balance', 0))
            
            if self.initial_balance is None:
                self.initial_balance = self.usdt_balance
            
            return self.usdt_balance
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            return 0.0
    
    def get_token_balance(self, token: str) -> float:
        """Получить баланс токена (YES или NO)"""
        try:
            response = self.client.get_my_positions()
            
            if response.errno != 0:
                return 0.0
            
            positions = response.result
            if not hasattr(positions, 'list') or not positions.list:
                return 0.0
            
            target_token_id = self.yes_token_id if token == 'YES' else self.no_token_id
            target_outcome = 'Yes' if token == 'YES' else 'No'
            
            for pos in positions.list:
                pos_market = getattr(pos, 'market_id', None)
                pos_outcome = getattr(pos, 'outcome_side_enum', None)
                pos_token = getattr(pos, 'token_id', '')
                
                if (pos_market == self.market_id and 
                    pos_outcome == target_outcome and
                    str(pos_token) == str(target_token_id)):
                    
                    shares = getattr(pos, 'shares_owned', '0')
                    return float(shares) if shares else 0.0
            
            return 0.0
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса {token}: {e}")
            return 0.0
    
    def update_balances(self):
        """Обновить все балансы"""
        self.usdt_balance = self.get_usdt_balance()
        self.yes_balance = self.get_token_balance('YES')
        self.no_balance = self.get_token_balance('NO')
        
        logger.info(f"💰 Балансы: USDT ${self.usdt_balance:.2f} | YES {self.yes_balance:.2f} | NO {self.no_balance:.2f}")
    
    # =========================================================================
    # WEBSOCKET
    # =========================================================================
    
    def init_websocket(self) -> bool:
        """
        Инициализировать WebSocket соединение для real-time данных
        
        Returns:
            True если успешно подключились
        """
        if not WEBSOCKET_AVAILABLE:
            logger.warning("⚠️ WebSocket модуль недоступен")
            return False
        
        try:
            logger.info("🔌 Подключение к WebSocket для real-time данных...")
            
            self.ws = OpinionWebSocket(self.apikey)
            
            if self.ws.connect():
                # Подписываемся на стакан рынка
                # Передаём token IDs чтобы сразу загрузить snapshot
                self.ws.subscribe_orderbook(
                    self.market_id, 
                    self._on_orderbook_update,
                    yes_token_id=self.yes_token_id,
                    no_token_id=self.no_token_id
                )
                self.ws.subscribe_price(self.market_id, self._on_price_update)
                self.ws.subscribe_orders(self.market_id, self._on_order_update)
                
                # Ждём начальных данных
                logger.info("⏳ Ожидание начальных данных от WebSocket...")
                time.sleep(2)
                
                self.use_websocket = True
                logger.info("✅ WebSocket подключен! Используем real-time данные")
                return True
            else:
                logger.warning("⚠️ Не удалось подключиться к WebSocket, используем REST API")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации WebSocket: {e}")
            return False
    
    def _on_orderbook_update(self, token_id: str, side: str, price: str, size: str):
        """Callback при обновлении стакана"""
        token_type = 'YES' if token_id == self.yes_token_id else 'NO' if token_id == self.no_token_id else '?'
        logger.debug(f"📊 WS Orderbook: {token_type} {side} @ {price} = {size}")
    
    def _on_price_update(self, token_id: str, price: float):
        """Callback при изменении цены"""
        token_type = 'YES' if token_id == self.yes_token_id else 'NO' if token_id == self.no_token_id else '?'
        logger.debug(f"💰 WS Price: {token_type} = {price:.4f}")
    
    def _on_order_update(self, data: dict):
        """Callback при обновлении ордера"""
        logger.info(f"📋 WS Order update: {data.get('status', 'unknown')} - {data.get('orderId', 'no_id')[:16]}...")
    
    def disconnect_websocket(self):
        """Отключить WebSocket"""
        if self.ws:
            self.ws.disconnect()
            self.ws = None
            self.use_websocket = False
            logger.info("🔌 WebSocket отключен")
    
    # =========================================================================
    # ЦЕНЫ
    # =========================================================================
    
    def get_prices(self) -> Tuple[Optional[float], ...]:
        """
        Получить текущие цены из orderbook
        
        Приоритет:
        1. WebSocket (если подключен) - real-time данные
        2. REST API (fallback)
        
        Returns:
            (yes_bid, yes_ask, no_bid, no_ask)
        """
        # Попробуем WebSocket сначала
        if self.use_websocket and self.ws and self.ws.connected:
            yes_bid, yes_ask, no_bid, no_ask = self._get_prices_websocket()
            
            # Если получили данные из WS - используем их
            if any([yes_bid, yes_ask, no_bid, no_ask]):
                logger.debug(f"📡 Цены из WebSocket: YES {yes_bid}/{yes_ask} | NO {no_bid}/{no_ask}")
                return yes_bid, yes_ask, no_bid, no_ask
            else:
                logger.debug("⚠️ WebSocket не вернул данные, пробуем REST API...")
        
        # Fallback на REST API
        return self._get_prices_rest_api()
    
    def _get_prices_websocket(self) -> Tuple[Optional[float], ...]:
        """Получить цены из WebSocket кэша"""
        try:
            yes_bid, yes_ask = self.ws.get_best_prices(self.yes_token_id)
            no_bid, no_ask = self.ws.get_best_prices(self.no_token_id)
            return yes_bid, yes_ask, no_bid, no_ask
        except Exception as e:
            logger.error(f"❌ Ошибка получения цен из WebSocket: {e}")
            return None, None, None, None
    
    def _get_prices_rest_api(self) -> Tuple[Optional[float], ...]:
        """Получить цены через REST API (fallback)"""
        try:
            # YES orderbook
            yes_bids, yes_asks = self.openapi.get_orderbook(self.yes_token_id)
            # NO orderbook
            no_bids, no_asks = self.openapi.get_orderbook(self.no_token_id)
            
            if not all([yes_bids, yes_asks, no_bids, no_asks]):
                return None, None, None, None
            
            # Best prices
            yes_bid = float(yes_bids[0]['price']) if yes_bids else None
            yes_ask = float(yes_asks[0]['price']) if yes_asks else None
            no_bid = float(no_bids[0]['price']) if no_bids else None
            no_ask = float(no_asks[0]['price']) if no_asks else None
            
            return yes_bid, yes_ask, no_bid, no_ask
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения цен через REST API: {e}")
            return None, None, None, None
    
    # =========================================================================
    # ОРДЕРА
    # =========================================================================
    
    def place_order(
        self,
        token: str,
        side: str,
        price: float,
        amount_usdt: float
    ) -> Optional[str]:
        """
        Разместить ордер
        
        Args:
            token: 'YES' или 'NO'
            side: 'BID' (покупка) или 'ASK' (продажа)
            price: Цена (0.01 - 0.99)
            amount_usdt: Сумма в USDT
            
        Returns:
            order_id если успешно, None если ошибка
        """
        try:
            # Валидация
            if not validate_price(price):
                logger.warning(f"⚠️ Цена {price} вне диапазона [{MIN_PRICE}, {MAX_PRICE}]")
                return None
            
            if amount_usdt < MIN_ORDER_USDT:
                logger.warning(f"⚠️ Сумма ${amount_usdt:.2f} меньше минимума ${MIN_ORDER_USDT}")
                return None
            
            token_id = self.yes_token_id if token == 'YES' else self.no_token_id
            price_str = format_price(price)
            
            # Определяем сторону и количество
            if side == 'BID':
                order_side = OrderSide.BUY
                # Для BID указываем сумму в USDT
                order = PlaceOrderDataInput(
                    marketId=self.market_id,
                    tokenId=token_id,
                    side=order_side,
                    orderType=LIMIT_ORDER,
                    price=price_str,
                    makerAmountInQuoteToken=str(amount_usdt)
                )
            else:
                order_side = OrderSide.SELL
                # Для ASK указываем количество токенов
                # Округляем вниз с запасом 0.1% чтобы избежать ошибки Insufficient balance
                tokens_to_sell = amount_usdt / price
                tokens_to_sell = float(int(tokens_to_sell * 1000) / 1000)  # Округляем до 3 знаков вниз
                order = PlaceOrderDataInput(
                    marketId=self.market_id,
                    tokenId=token_id,
                    side=order_side,
                    orderType=LIMIT_ORDER,
                    price=price_str,
                    makerAmountInBaseToken=str(tokens_to_sell)
                )
            
            logger.debug(f"📝 Размещение {side} {token} @ {price_str}: ${amount_usdt:.2f}")
            
            # Отправляем ордер
            result = self.client.place_order(order, check_approval=True)
            
            if result.errno == 0:
                order_data = result.result
                order_id = None
                
                # Извлекаем order_id
                if hasattr(order_data, 'order_data'):
                    if hasattr(order_data.order_data, 'order_id'):
                        order_id = order_data.order_data.order_id
                elif hasattr(order_data, 'order_id'):
                    order_id = order_data.order_id
                
                if order_id:
                    # Сохраняем информацию об ордере
                    self.orders[order_id] = OrderInfo(
                        order_id=order_id,
                        token=token,
                        side=side,
                        price=price,
                        amount=amount_usdt,
                        tokens=amount_usdt / price if side == 'BID' else tokens_to_sell
                    )
                    
                    # Обновляем локальное отслеживание активных ордеров
                    order_key = f"{token}_{side}"
                    if token == 'YES' and side == 'ASK':
                        self.active_yes_ask = True
                    elif token == 'NO' and side == 'ASK':
                        self.active_no_ask = True
                    elif token == 'YES' and side == 'BID':
                        self.active_yes_bid = True
                    elif token == 'NO' and side == 'BID':
                        self.active_no_bid = True
                    
                    # Сохраняем цену и ID для отслеживания stale
                    self.active_order_prices[order_key] = price
                    self.active_order_ids[order_key] = order_id
                    
                    logger.info(f"✅ {side} {token} @ {price:.4f}: ${amount_usdt:.2f} (ID: {order_id[:16]}...)")
                    return order_id
                else:
                    # Ордер размещен, но ID не получен - всё равно помечаем как активный
                    fake_id = f"{side}_{token}_{int(time.time()*1000)}"
                    
                    # Обновляем локальное отслеживание
                    order_key = f"{token}_{side}"
                    if token == 'YES' and side == 'ASK':
                        self.active_yes_ask = True
                    elif token == 'NO' and side == 'ASK':
                        self.active_no_ask = True
                    elif token == 'YES' and side == 'BID':
                        self.active_yes_bid = True
                    elif token == 'NO' and side == 'BID':
                        self.active_no_bid = True
                    
                    # Сохраняем цену и ID для отслеживания stale
                    self.active_order_prices[order_key] = price
                    self.active_order_ids[order_key] = fake_id
                    
                    logger.info(f"✅ {side} {token} @ {price:.4f}: ${amount_usdt:.2f} (no ID)")
                    return fake_id
            else:
                logger.warning(f"⚠️ Ошибка ордера {side} {token}: {result.errmsg}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Исключение при размещении ордера: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Отменить ордер"""
        try:
            result = self.client.cancel_order(order_id)
            
            if order_id in self.orders:
                del self.orders[order_id]
            
            logger.debug(f"🗑️ Ордер отменен: {order_id[:16]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отмены ордера: {e}")
            return False
    
    def cancel_all_orders(self) -> int:
        """Отменить все ордера на рынке"""
        try:
            result = self.client.cancel_all_orders(market_id=self.market_id)
            cancelled = result.get('cancelled', 0) if isinstance(result, dict) else 0
            
            self.orders.clear()
            
            if cancelled > 0:
                logger.info(f"🗑️ Отменено {cancelled} ордеров")
            
            return cancelled
            
        except Exception as e:
            logger.error(f"❌ Ошибка отмены ордеров: {e}")
            return 0
    
    def get_open_orders(self) -> List[Dict]:
        """Получить открытые ордера с биржи"""
        try:
            response = self.client.get_my_orders(
                market_id=self.market_id,
                status="open",
                limit=50
            )
            
            if response.errno != 0:
                return []
            
            orders = response.result.list if hasattr(response.result, 'list') else []
            return orders
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения ордеров: {e}")
            return []
    
    # =========================================================================
    # ПРОВЕРКА УСТАРЕВШИХ ОРДЕРОВ
    # =========================================================================
    
    def check_order_execution(self):
        """
        Проверить исполнение ордеров по изменению балансов.
        Если баланс изменился - ордер (частично) исполнен.
        """
        if self.prev_usdt_balance is None:
            # Первый запуск - просто сохраняем
            self.prev_usdt_balance = self.usdt_balance
            self.prev_yes_balance = self.yes_balance
            self.prev_no_balance = self.no_balance
            return
        
        # Проверяем BID ордера (покупка токенов за USDT)
        # Если USDT уменьшился и токены увеличились - BID исполнен
        usdt_decreased = self.usdt_balance < self.prev_usdt_balance - 0.1
        yes_increased = self.yes_balance > self.prev_yes_balance + 0.05
        no_increased = self.no_balance > self.prev_no_balance + 0.05
        
        if usdt_decreased and yes_increased and self.active_yes_bid:
            # Рассчитываем среднюю цену покупки
            usdt_spent = self.prev_usdt_balance - self.usdt_balance
            tokens_bought = self.yes_balance - self.prev_yes_balance
            buy_price = usdt_spent / tokens_bought if tokens_bought > 0 else 0
            
            # Обновляем среднюю цену покупки (средневзвешенная)
            if self.yes_avg_buy_price is None:
                self.yes_avg_buy_price = buy_price
                self.yes_total_cost = usdt_spent
            else:
                old_tokens = self.prev_yes_balance
                new_total_cost = self.yes_total_cost + usdt_spent
                new_total_tokens = old_tokens + tokens_bought
                self.yes_avg_buy_price = new_total_cost / new_total_tokens if new_total_tokens > 0 else buy_price
                self.yes_total_cost = new_total_cost
            
            logger.info(f"✅ YES BID исполнен! YES: {self.prev_yes_balance:.2f} → {self.yes_balance:.2f}")
            logger.info(f"   💰 Куплено {tokens_bought:.2f} YES @ {buy_price:.4f} | Средняя: {self.yes_avg_buy_price:.4f}")
            self.active_yes_bid = False
            self.active_order_prices['YES_BID'] = None
            self.active_order_ids['YES_BID'] = None
        
        if usdt_decreased and no_increased and self.active_no_bid:
            # Рассчитываем среднюю цену покупки
            usdt_spent = self.prev_usdt_balance - self.usdt_balance
            tokens_bought = self.no_balance - self.prev_no_balance
            buy_price = usdt_spent / tokens_bought if tokens_bought > 0 else 0
            
            # Обновляем среднюю цену покупки (средневзвешенная)
            if self.no_avg_buy_price is None:
                self.no_avg_buy_price = buy_price
                self.no_total_cost = usdt_spent
            else:
                old_tokens = self.prev_no_balance
                new_total_cost = self.no_total_cost + usdt_spent
                new_total_tokens = old_tokens + tokens_bought
                self.no_avg_buy_price = new_total_cost / new_total_tokens if new_total_tokens > 0 else buy_price
                self.no_total_cost = new_total_cost
            
            logger.info(f"✅ NO BID исполнен! NO: {self.prev_no_balance:.2f} → {self.no_balance:.2f}")
            logger.info(f"   💰 Куплено {tokens_bought:.2f} NO @ {buy_price:.4f} | Средняя: {self.no_avg_buy_price:.4f}")
            self.active_no_bid = False
            self.active_order_prices['NO_BID'] = None
            self.active_order_ids['NO_BID'] = None
        
        # Проверяем ASK ордера (продажа токенов за USDT)
        # Если токены уменьшились и USDT увеличился - ASK исполнен
        usdt_increased = self.usdt_balance > self.prev_usdt_balance + 0.1
        yes_decreased = self.yes_balance < self.prev_yes_balance - 0.05
        no_decreased = self.no_balance < self.prev_no_balance - 0.05
        
        if usdt_increased and yes_decreased and self.active_yes_ask:
            tokens_sold = self.prev_yes_balance - self.yes_balance
            usdt_received = self.usdt_balance - self.prev_usdt_balance
            sell_price = usdt_received / tokens_sold if tokens_sold > 0 else 0
            
            # Рассчитываем прибыль/убыток
            if self.yes_avg_buy_price is not None:
                profit_per_token = sell_price - self.yes_avg_buy_price
                total_profit = profit_per_token * tokens_sold
                logger.info(f"✅ YES ASK исполнен! YES: {self.prev_yes_balance:.2f} → {self.yes_balance:.2f}")
                logger.info(f"   💵 Продано {tokens_sold:.2f} YES @ {sell_price:.4f} | Прибыль: ${total_profit:+.2f}")
            else:
                logger.info(f"✅ YES ASK исполнен! YES: {self.prev_yes_balance:.2f} → {self.yes_balance:.2f}")
            
            # Если продали все токены - сбрасываем среднюю цену
            if self.yes_balance < 0.1:
                self.yes_avg_buy_price = None
                self.yes_total_cost = 0.0
                logger.info(f"   🔄 YES баланс обнулён, средняя цена сброшена")
            
            self.active_yes_ask = False
            self.active_order_prices['YES_ASK'] = None
            self.active_order_ids['YES_ASK'] = None
        
        if usdt_increased and no_decreased and self.active_no_ask:
            tokens_sold = self.prev_no_balance - self.no_balance
            usdt_received = self.usdt_balance - self.prev_usdt_balance
            sell_price = usdt_received / tokens_sold if tokens_sold > 0 else 0
            
            # Рассчитываем прибыль/убыток
            if self.no_avg_buy_price is not None:
                profit_per_token = sell_price - self.no_avg_buy_price
                total_profit = profit_per_token * tokens_sold
                logger.info(f"✅ NO ASK исполнен! NO: {self.prev_no_balance:.2f} → {self.no_balance:.2f}")
                logger.info(f"   💵 Продано {tokens_sold:.2f} NO @ {sell_price:.4f} | Прибыль: ${total_profit:+.2f}")
            else:
                logger.info(f"✅ NO ASK исполнен! NO: {self.prev_no_balance:.2f} → {self.no_balance:.2f}")
            
            # Если продали все токены - сбрасываем среднюю цену
            if self.no_balance < 0.1:
                self.no_avg_buy_price = None
                self.no_total_cost = 0.0
                logger.info(f"   🔄 NO баланс обнулён, средняя цена сброшена")
            
            self.active_no_ask = False
            self.active_order_prices['NO_ASK'] = None
            self.active_order_ids['NO_ASK'] = None
        
        # Сохраняем текущие балансы
        self.prev_usdt_balance = self.usdt_balance
        self.prev_yes_balance = self.yes_balance
        self.prev_no_balance = self.no_balance
    
    def check_stale_orders(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> int:
        """
        Проверить и отменить устаревшие ордера.
        Ордер считается устаревшим, если рыночная цена ушла от него на > STALE_ORDER_THRESHOLD.
        
        Returns:
            Количество отменённых ордеров
        """
        cancelled = 0
        
        # Проверяем YES BID
        if self.active_yes_bid and self.active_order_prices.get('YES_BID'):
            order_price = self.active_order_prices['YES_BID']
            # Для BID: сравниваем с текущим лучшим ASK (мы хотим купить дешевле)
            # Если рынок упал - наш BID слишком высокий, переразмещаем ниже
            # Если рынок вырос - наш BID слишком низкий, переразмещаем выше
            price_diff = abs(order_price - yes_ask) / yes_ask if yes_ask > 0 else 0
            
            if price_diff > STALE_ORDER_THRESHOLD:
                logger.info(f"🔄 YES BID устарел: ордер@{order_price:.3f} vs рынок ASK@{yes_ask:.3f} (разница {price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('YES_BID')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_yes_bid = False
                self.active_order_prices['YES_BID'] = None
                self.active_order_ids['YES_BID'] = None
                cancelled += 1
        
        # Проверяем NO BID
        if self.active_no_bid and self.active_order_prices.get('NO_BID'):
            order_price = self.active_order_prices['NO_BID']
            price_diff = abs(order_price - no_ask) / no_ask if no_ask > 0 else 0
            
            if price_diff > STALE_ORDER_THRESHOLD:
                logger.info(f"🔄 NO BID устарел: ордер@{order_price:.3f} vs рынок ASK@{no_ask:.3f} (разница {price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('NO_BID')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_no_bid = False
                self.active_order_prices['NO_BID'] = None
                self.active_order_ids['NO_BID'] = None
                cancelled += 1
        
        # Проверяем YES ASK - КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ
        if self.active_yes_ask and self.active_order_prices.get('YES_ASK'):
            order_price = self.active_order_prices['YES_ASK']
            # Для ASK: сравниваем с текущим лучшим ASK в стакане
            # Если наш ордер намного выше рыночного ASK - он не исполнится
            # Если рынок упал - нужно снизить цену продажи
            price_diff = abs(order_price - yes_ask) / yes_ask if yes_ask > 0 else 0
            
            if price_diff > STALE_ORDER_THRESHOLD:
                logger.info(f"🔄 YES ASK устарел: ордер@{order_price:.3f} vs рынок ASK@{yes_ask:.3f} (разница {price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('YES_ASK')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_yes_ask = False
                self.active_order_prices['YES_ASK'] = None
                self.active_order_ids['YES_ASK'] = None
                cancelled += 1
        
        # Проверяем NO ASK
        if self.active_no_ask and self.active_order_prices.get('NO_ASK'):
            order_price = self.active_order_prices['NO_ASK']
            price_diff = abs(order_price - no_ask) / no_ask if no_ask > 0 else 0
            
            if price_diff > STALE_ORDER_THRESHOLD:
                logger.info(f"🔄 NO ASK устарел: ордер@{order_price:.3f} vs рынок ASK@{no_ask:.3f} (разница {price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('NO_ASK')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_no_ask = False
                self.active_order_prices['NO_ASK'] = None
                self.active_order_ids['NO_ASK'] = None
                cancelled += 1
        
        if cancelled > 0:
            logger.info(f"🗑️ Отменено {cancelled} устаревших ордеров")
        
        return cancelled
    
    def _cancel_order_safe(self, order_id: str) -> bool:
        """
        Безопасная отмена ордера - пытается отменить через API,
        даже если ID был сгенерирован локально.
        """
        try:
            # Пытаемся отменить через API
            result = self.client.cancel_order(order_id)
            logger.debug(f"🗑️ Ордер отменен через API: {order_id[:16]}...")
            return True
        except Exception as e:
            # Если не получилось - пробуем отменить все ордера на рынке
            logger.debug(f"⚠️ Не удалось отменить ордер {order_id[:16]}..., пробуем cancel_all")
            try:
                self.client.cancel_all_orders(market_id=self.market_id)
                # Сбрасываем все флаги
                self.active_yes_bid = False
                self.active_no_bid = False
                self.active_yes_ask = False
                self.active_no_ask = False
                return True
            except:
                pass
            return False
    
    # =========================================================================
    # СТРАТЕГИИ
    # =========================================================================
    
    def strategy_dual_side(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> Dict:
        """
        Стратегия Market Making (Dual Side)
        
        Логика:
        - Размещаем BID (покупка) ниже рыночного ASK со спредом
        - Размещаем ASK (продажа) выше рыночного BID со спредом
        - Maker Fee = 0%, поэтому зарабатываем чистый спред
        - Адаптивный спред: если рыночный спред большой, увеличиваем наш
        
        Returns:
            Dict с результатами
        """
        result = {
            'placed_bids': [],
            'placed_asks': [],
            'errors': []
        }
        
        # Адаптивный спред: используем максимум из нашего спреда и рыночного
        if ADAPTIVE_SPREAD:
            # Рыночный спред для YES
            yes_market_spread = (yes_ask - yes_bid) / yes_ask if yes_ask > 0 else 0
            # Рыночный спред для NO
            no_market_spread = (no_ask - no_bid) / no_ask if no_ask > 0 else 0
            
            # Максимальный рыночный спред из двух токенов
            max_market_spread = max(yes_market_spread, no_market_spread)
            
            # Используем спред не меньше рыночного (чтобы не торговать в убыток)
            # +10% от рыночного, но не меньше MIN и не больше MAX
            effective_spread = max(
                self.spread_percent,
                min(max_market_spread * 1.1, MAX_SPREAD_PERCENT),
                MIN_SPREAD_PERCENT
            )
            
            if effective_spread > self.spread_percent:
                logger.info(f"📊 Адаптивный спред: {self.spread_percent*100:.1f}% → {effective_spread*100:.1f}% (рынок YES: {yes_market_spread*100:.1f}%, NO: {no_market_spread*100:.1f}%)")
        else:
            effective_spread = self.spread_percent
        
        # Рассчитываем цены через MIDPOINT для гарантированной прибыли
        # Midpoint = середина между лучшим BID и ASK
        yes_mid = (yes_bid + yes_ask) / 2
        no_mid = (no_bid + no_ask) / 2
        
        # BID = покупаем НИЖЕ midpoint
        yes_bid_price = round(yes_mid * (1 - effective_spread / 2), 3)
        no_bid_price = round(no_mid * (1 - effective_spread / 2), 3)
        
        # ASK = продаём ВЫШЕ midpoint
        # Разница между нашим ASK и BID = спред = прибыль!
        yes_ask_price = round(yes_mid * (1 + effective_spread / 2), 3)
        no_ask_price = round(no_mid * (1 + effective_spread / 2), 3)
        
        # Защита: ASK не выше рыночного ASK
        yes_ask_price = min(yes_ask_price, round(yes_ask * 0.998, 3))
        no_ask_price = min(no_ask_price, round(no_ask * 0.998, 3))
        
        # Защита: BID не ниже рыночного BID
        yes_bid_price = max(yes_bid_price, round(yes_bid * 1.002, 3))
        no_bid_price = max(no_bid_price, round(no_bid * 1.002, 3))
        
        # Ограничиваем диапазон
        yes_bid_price = max(MIN_PRICE, min(yes_bid_price, MAX_PRICE))
        no_bid_price = max(MIN_PRICE, min(no_bid_price, MAX_PRICE))
        yes_ask_price = max(MIN_PRICE, min(yes_ask_price, MAX_PRICE))
        no_ask_price = max(MIN_PRICE, min(no_ask_price, MAX_PRICE))
        
        # Используем локальное отслеживание ордеров (API get_my_orders не всегда работает)
        has_yes_bid = self.active_yes_bid
        has_no_bid = self.active_no_bid
        has_yes_ask = self.active_yes_ask
        has_no_ask = self.active_no_ask
        
        logger.info(f"📋 Активные ордера: YES_BID={has_yes_bid}, NO_BID={has_no_bid}, YES_ASK={has_yes_ask}, NO_ASK={has_no_ask}")
        
        # === BID ордера (покупка за USDT) ===
        # Размещаем BID если хватает хотя бы на один минимальный ордер
        if self.usdt_balance >= MIN_ORDER_USDT:
            # Если хватает на 2 ордера - делим пополам, иначе один ордер
            if self.usdt_balance >= MIN_ORDER_USDT * 2:
                order_size = min(self.order_amount, self.usdt_balance / 2)
            else:
                order_size = self.usdt_balance  # Весь баланс на один ордер
            
            # Выбираем какой токен покупать (приоритет YES если хватает на оба)
            if not has_yes_bid and validate_price(yes_bid_price):
                actual_size = min(order_size, self.usdt_balance)
                if actual_size >= MIN_ORDER_USDT:
                    order_id = self.place_order('YES', 'BID', yes_bid_price, actual_size)
                    if order_id:
                        result['placed_bids'].append({
                            'token': 'YES',
                            'price': yes_bid_price,
                            'amount': actual_size,
                            'order_id': order_id
                        })
            
            remaining = self.usdt_balance - order_size if result['placed_bids'] else self.usdt_balance
            if not has_no_bid and validate_price(no_bid_price) and remaining >= MIN_ORDER_USDT:
                order_id = self.place_order('NO', 'BID', no_bid_price, min(order_size, remaining))
                if order_id:
                    result['placed_bids'].append({
                        'token': 'NO',
                        'price': no_bid_price,
                        'amount': min(order_size, remaining),
                            'order_id': order_id
                        })
        
        # === ASK ордера (продажа токенов) ===
        # Используем 99.5% баланса токенов чтобы избежать ошибок округления
        if self.yes_balance > 0.1 and not has_yes_ask and validate_price(yes_ask_price):
            safe_balance = self.yes_balance * 0.995  # 99.5% от баланса
            ask_amount = safe_balance * yes_ask_price
            if ask_amount >= MIN_ORDER_USDT:
                order_id = self.place_order('YES', 'ASK', yes_ask_price, ask_amount)
                if order_id:
                    result['placed_asks'].append({
                        'token': 'YES',
                        'price': yes_ask_price,
                        'amount': ask_amount,
                        'order_id': order_id
                    })
            else:
                logger.info(f"⏸️ YES ASK: сумма ${ask_amount:.2f} < мин ${MIN_ORDER_USDT}")
        elif self.yes_balance <= 0.1:
            logger.debug(f"⏸️ YES ASK: баланс {self.yes_balance:.2f} слишком мал")
        
        if self.no_balance > 0.1 and not has_no_ask and validate_price(no_ask_price):
            safe_balance = self.no_balance * 0.995  # 99.5% от баланса
            ask_amount = safe_balance * no_ask_price
            if ask_amount >= MIN_ORDER_USDT:
                order_id = self.place_order('NO', 'ASK', no_ask_price, ask_amount)
                if order_id:
                    result['placed_asks'].append({
                        'token': 'NO',
                        'price': no_ask_price,
                        'amount': ask_amount,
                        'order_id': order_id
                    })
            else:
                logger.info(f"⏸️ NO ASK: сумма ${ask_amount:.2f} < мин ${MIN_ORDER_USDT} (цена {no_ask_price:.4f})")
        elif self.no_balance <= 0.1:
            logger.debug(f"⏸️ NO ASK: баланс {self.no_balance:.2f} слишком мал")
        elif not validate_price(no_ask_price):
            logger.info(f"⏸️ NO ASK: цена {no_ask_price:.4f} невалидна")
        
        return result
    
    def strategy_arbitrage(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> Dict:
        """
        Стратегия арбитража
        
        Логика:
        1. BUY_BOTH: если YES_ASK + NO_ASK < 1.00
           - Покупаем оба токена
           - После резолюции получим $1 за пару
           - Прибыль = 1.00 - (YES_ASK + NO_ASK) - fees
           
        2. SELL_BOTH: если YES_BID + NO_BID > 1.00
           - Продаем оба токена (если есть)
           - Прибыль = (YES_BID + NO_BID) - 1.00 - fees
        
        Returns:
            Dict с результатами
        """
        result = {
            'opportunity': None,
            'executed': False,
            'profit': 0.0,
            'details': None
        }
        
        # === BUY_BOTH: YES_ASK + NO_ASK < 1.00 ===
        buy_cost = yes_ask + no_ask
        
        if buy_cost < 1.0:
            gross_profit = 1.0 - buy_cost
            
            # Примерные комиссии (taker)
            test_amount = self.order_amount
            yes_fee = calculate_taker_fee(yes_ask, test_amount / 2)
            no_fee = calculate_taker_fee(no_ask, test_amount / 2)
            fee_per_pair = (yes_fee + no_fee) / (test_amount / buy_cost)
            
            net_profit = gross_profit - fee_per_pair
            profit_percent = net_profit / buy_cost
            
            if net_profit > 0 and profit_percent >= ARBITRAGE_MIN_PROFIT:
                result['opportunity'] = 'BUY_BOTH'
                
                logger.info(f"🎯 АРБИТРАЖ BUY_BOTH найден!")
                logger.info(f"   YES@{yes_ask:.3f} + NO@{no_ask:.3f} = ${buy_cost:.3f} < $1.00")
                logger.info(f"   Потенциальная прибыль: ${net_profit:.3f}/пара ({profit_percent*100:.2f}%)")
                
                # Выполняем арбитраж
                if self.usdt_balance >= MIN_ORDER_USDT * 2:
                    max_pairs = (self.usdt_balance * 0.8) / buy_cost  # 80% баланса
                    pairs_to_buy = min(max_pairs, self.order_amount * 2 / buy_cost)
                    
                    if pairs_to_buy >= 0.5:
                        yes_cost = pairs_to_buy * yes_ask
                        no_cost = pairs_to_buy * no_ask
                        
                        # Покупаем YES
                        yes_order = self.place_order('YES', 'BID', yes_ask, yes_cost)
                        # Покупаем NO
                        no_order = self.place_order('NO', 'BID', no_ask, no_cost)
                        
                        if yes_order and no_order:
                            expected_profit = pairs_to_buy * net_profit
                            self.arbitrage_trades += 1
                            self.arbitrage_profit += expected_profit
                            
                            result['executed'] = True
                            result['profit'] = expected_profit
                            result['details'] = {
                                'type': 'BUY_BOTH',
                                'pairs': pairs_to_buy,
                                'yes_price': yes_ask,
                                'no_price': no_ask,
                                'total_cost': yes_cost + no_cost,
                                'expected_profit': expected_profit
                            }
                            
                            logger.info(f"✅ АРБИТРАЖ BUY_BOTH выполнен: {pairs_to_buy:.2f} пар")
                            logger.info(f"   Ожидаемая прибыль: ${expected_profit:.2f}")
        
        # === SELL_BOTH: YES_BID + NO_BID > 1.00 ===
        sell_revenue = yes_bid + no_bid
        
        if sell_revenue > 1.0 and result['opportunity'] is None:
            min_tokens = min(self.yes_balance, self.no_balance)
            
            if min_tokens >= 0.5:
                gross_profit = sell_revenue - 1.0
                
                # Примерные комиссии
                test_amount = min_tokens * sell_revenue
                yes_fee = calculate_taker_fee(yes_bid, min_tokens * yes_bid)
                no_fee = calculate_taker_fee(no_bid, min_tokens * no_bid)
                fee_per_pair = (yes_fee + no_fee) / min_tokens
                
                net_profit = gross_profit - fee_per_pair
                profit_percent = net_profit / 1.0
                
                if net_profit > 0 and profit_percent >= ARBITRAGE_MIN_PROFIT:
                    result['opportunity'] = 'SELL_BOTH'
                    
                    logger.info(f"🎯 АРБИТРАЖ SELL_BOTH найден!")
                    logger.info(f"   YES@{yes_bid:.3f} + NO@{no_bid:.3f} = ${sell_revenue:.3f} > $1.00")
                    logger.info(f"   Потенциальная прибыль: ${net_profit:.3f}/пара ({profit_percent*100:.2f}%)")
                    
                    # Продаем токены
                    pairs_to_sell = min(min_tokens, self.order_amount / sell_revenue)
                    
                    if pairs_to_sell >= 0.5:
                        yes_revenue = pairs_to_sell * yes_bid
                        no_revenue = pairs_to_sell * no_bid
                        
                        # Продаем YES
                        yes_order = self.place_order('YES', 'ASK', yes_bid, yes_revenue)
                        # Продаем NO
                        no_order = self.place_order('NO', 'ASK', no_bid, no_revenue)
                        
                        if yes_order and no_order:
                            expected_profit = pairs_to_sell * net_profit
                            self.arbitrage_trades += 1
                            self.arbitrage_profit += expected_profit
                            self.total_pnl += expected_profit
                            
                            result['executed'] = True
                            result['profit'] = expected_profit
                            result['details'] = {
                                'type': 'SELL_BOTH',
                                'pairs': pairs_to_sell,
                                'yes_price': yes_bid,
                                'no_price': no_bid,
                                'total_revenue': yes_revenue + no_revenue,
                                'profit': expected_profit
                            }
                            
                            logger.info(f"✅ АРБИТРАЖ SELL_BOTH выполнен: {pairs_to_sell:.2f} пар")
                            logger.info(f"   Прибыль: ${expected_profit:.2f}")
        
        return result
    
    def strategy_hybrid(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> Dict:
        """
        Гибридная стратегия: Dual Side + Арбитраж
        
        Распределение:
        - 70% баланса на Market Making
        - 30% резерв для арбитража
        """
        result = {
            'dual_side': None,
            'arbitrage': None
        }
        
        # 1. Сначала проверяем арбитраж (приоритет)
        arb_result = self.strategy_arbitrage(yes_bid, yes_ask, no_bid, no_ask)
        result['arbitrage'] = arb_result
        
        # 2. Рассчитываем доступный баланс для dual_side
        total_usdt = self.usdt_balance
        
        # Резерв для арбитража
        arbitrage_reserve = total_usdt * HYBRID_ARBITRAGE_PERCENT
        available_for_mm = total_usdt - arbitrage_reserve
        
        logger.debug(f"📊 Hybrid: total=${total_usdt:.2f}, MM=${available_for_mm:.2f}, arb_reserve=${arbitrage_reserve:.2f}")
        
        # 3. Запускаем dual_side с ограниченным балансом
        # Для ASK ордеров (продажа токенов) не нужен USDT баланс!
        # Поэтому вызываем всегда, но с ограниченным USDT для BID
        original_balance = self.usdt_balance
        self.usdt_balance = available_for_mm  # Ограничиваем USDT для BID
        
        ds_result = self.strategy_dual_side(yes_bid, yes_ask, no_bid, no_ask)
        result['dual_side'] = ds_result
        
        # Восстанавливаем
        self.usdt_balance = original_balance
        
        return result
    
    def strategy_points_max(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> Dict:
        """
        🎯 СТРАТЕГИЯ МАКСИМИЗАЦИИ ПОИНТОВ
        
        Оптимизирована для заработка максимума PTS:
        1. Ордера МАКСИМАЛЬНО БЛИЗКО к рыночной цене (0.5% от лучшей)
        2. Размер ордеров >= $10 для бонусных поинтов
        3. Принудительная ротация если цена ушла на 2%
        4. Приоритет на MAKER ордера (0% комиссия + больше поинтов)
        5. Отслеживание объёма для достижения $200/неделю
        
        Returns:
            Dict с результатами
        """
        result = {
            'placed_bids': [],
            'placed_asks': [],
            'volume_added': 0.0,
            'errors': []
        }
        
        # === ВАЛИДАЦИЯ ЦЕН ИЗ СТАКАНА ===
        # КЛЮЧЕВОЕ ПРАВИЛО: YES + NO = 1 (всегда!)
        # Используем это для определения "правильных" цен
        
        logger.info(f"📊 Сырые цены: YES {yes_bid:.3f}/{yes_ask:.3f} | NO {no_bid:.3f}/{no_ask:.3f}")
        
        # === УМНАЯ ВАЛИДАЦИЯ: проверяем каждую цену отдельно ===
        # Цена "хорошая" если она в разумном диапазоне (5-95¢)
        # API часто возвращает 0.001 или 0.999 - это мусор
        
        def is_price_valid(price: float) -> bool:
            return 0.05 < price < 0.95
        
        # === ФИЛЬТР РЕЗКИХ СКАЧКОВ ===
        # Если цена изменилась более чем на 15% от предыдущей "хорошей" - это выброс
        MAX_PRICE_CHANGE = 0.15  # 15%
        
        # Инициализируем кэш если не существует
        if not hasattr(self, '_last_good_prices'):
            self._last_good_prices = {
                'yes_bid': None, 'yes_ask': None,
                'no_bid': None, 'no_ask': None
            }
        
        def is_price_stable(price: float, last_price: float, name: str) -> bool:
            """Проверка что цена не изменилась слишком резко"""
            if last_price is None:
                return True  # Первый раз - принимаем
            change = abs(price - last_price) / last_price
            if change > MAX_PRICE_CHANGE:
                logger.warning(f"   ⚠️ {name}: резкий скачок {last_price:.3f} → {price:.3f} ({change*100:.1f}%), игнорируем")
                return False
            return True
        
        # Проверяем валидность И стабильность
        yes_bid_ok = is_price_valid(yes_bid) and is_price_stable(yes_bid, self._last_good_prices['yes_bid'], 'YES_BID')
        yes_ask_ok = is_price_valid(yes_ask) and is_price_stable(yes_ask, self._last_good_prices['yes_ask'], 'YES_ASK')
        no_bid_ok = is_price_valid(no_bid) and is_price_stable(no_bid, self._last_good_prices['no_bid'], 'NO_BID')
        no_ask_ok = is_price_valid(no_ask) and is_price_stable(no_ask, self._last_good_prices['no_ask'], 'NO_ASK')
        
        logger.info(f"   Валидация: YES_BID={yes_bid_ok} YES_ASK={yes_ask_ok} | NO_BID={no_bid_ok} NO_ASK={no_ask_ok}")
        
        # === ВОССТАНОВЛЕНИЕ: используем правило YES + NO = 1 ===
        # Восстанавливаем ТОЛЬКО плохие цены из хороших противоположного токена
        
        # YES_BID восстанавливаем из NO_ASK: YES_BID = 1 - NO_ASK
        if not yes_bid_ok and no_ask_ok:
            yes_bid = round(1.0 - no_ask, 3)
            logger.info(f"   🔧 Восстановлен YES_BID: {yes_bid:.3f} (из NO_ASK {no_ask:.3f})")
            yes_bid_ok = True
        
        # YES_ASK восстанавливаем из NO_BID: YES_ASK = 1 - NO_BID
        if not yes_ask_ok and no_bid_ok:
            yes_ask = round(1.0 - no_bid, 3)
            logger.info(f"   🔧 Восстановлен YES_ASK: {yes_ask:.3f} (из NO_BID {no_bid:.3f})")
            yes_ask_ok = True
        
        # NO_BID восстанавливаем из YES_ASK: NO_BID = 1 - YES_ASK
        if not no_bid_ok and yes_ask_ok:
            no_bid = round(1.0 - yes_ask, 3)
            logger.info(f"   🔧 Восстановлен NO_BID: {no_bid:.3f} (из YES_ASK {yes_ask:.3f})")
            no_bid_ok = True
        
        # NO_ASK восстанавливаем из YES_BID: NO_ASK = 1 - YES_BID
        if not no_ask_ok and yes_bid_ok:
            no_ask = round(1.0 - yes_bid, 3)
            logger.info(f"   🔧 Восстановлен NO_ASK: {no_ask:.3f} (из YES_BID {yes_bid:.3f})")
            no_ask_ok = True
        
        # Проверяем что есть достаточно данных для работы
        if not (yes_bid_ok and yes_ask_ok) and not (no_bid_ok and no_ask_ok):
            logger.warning(f"⚠️ Недостаточно данных после восстановления. Пропускаем цикл.")
            result['orders_cancelled'] = 0
            return result
        
        # Финальная проверка
        yes_mid = (yes_bid + yes_ask) / 2
        no_mid = (no_bid + no_ask) / 2
        total = yes_mid + no_mid
        
        logger.info(f"   ✅ Финальные цены: YES {yes_bid:.3f}/{yes_ask:.3f} | NO {no_bid:.3f}/{no_ask:.3f}")
        
        # === ПРОСТАЯ ЛОГИКА: ФИКСИРОВАННЫЙ ОТСТУП 0.1¢ ===
        # BID: на 0.1¢ НИЖЕ лучшего BID (мы 2-е в очереди на покупку)
        # ASK: на 0.1¢ ВЫШЕ лучшего ASK (мы 2-е в очереди на продажу)
        # Ордера близко к рынку = больше поинтов!
        
        FIXED_OFFSET = 0.001  # 0.1¢
        
        yes_bid_price = round(yes_bid - FIXED_OFFSET, 3)
        no_bid_price = round(no_bid - FIXED_OFFSET, 3)
        yes_ask_price = round(yes_ask + FIXED_OFFSET, 3)
        no_ask_price = round(no_ask + FIXED_OFFSET, 3)
        
        logger.info(f"   📍 Цены с отступом 0.1¢:")
        logger.info(f"      YES: BID {yes_bid:.3f} - 0.001 = {yes_bid_price:.3f} | ASK {yes_ask:.3f} + 0.001 = {yes_ask_price:.3f}")
        logger.info(f"      NO:  BID {no_bid:.3f} - 0.001 = {no_bid_price:.3f} | ASK {no_ask:.3f} + 0.001 = {no_ask_price:.3f}")
        
        # Ограничиваем диапазон
        yes_bid_price = max(MIN_PRICE, min(yes_bid_price, MAX_PRICE))
        no_bid_price = max(MIN_PRICE, min(no_bid_price, MAX_PRICE))
        yes_ask_price = max(MIN_PRICE, min(yes_ask_price, MAX_PRICE))
        no_ask_price = max(MIN_PRICE, min(no_ask_price, MAX_PRICE))
        
        has_yes_bid = self.active_yes_bid
        has_no_bid = self.active_no_bid
        has_yes_ask = self.active_yes_ask
        has_no_ask = self.active_no_ask
        
        # Рассчитываем потенциальную маржу (прибыль с полного цикла buy+sell)
        yes_margin = (yes_ask_price - yes_bid_price) / yes_bid_price * 100 if yes_bid_price > 0 else 0
        no_margin = (no_ask_price - no_bid_price) / no_bid_price * 100 if no_bid_price > 0 else 0
        
        logger.info(f"🎯 POINTS_MAX: фиксированный отступ 0.1¢")
        logger.info(f"   YES: BID@{yes_bid_price:.3f} → ASK@{yes_ask_price:.3f} (маржа {yes_margin:.1f}%)")
        logger.info(f"   NO:  BID@{no_bid_price:.3f} → ASK@{no_ask_price:.3f} (маржа {no_margin:.1f}%)")
        
        # Размер ордера - минимум $10 для бонусных поинтов!
        order_size = max(POINTS_MIN_ORDER_SIZE, self.order_amount)
        
        # === BID ордера ===
        if self.usdt_balance >= POINTS_MIN_ORDER_SIZE:
            available = self.usdt_balance
            
            if not has_yes_bid and validate_price(yes_bid_price):
                bid_size = min(order_size, available / 2) if available >= order_size * 2 else available
                if bid_size >= POINTS_MIN_ORDER_SIZE:
                    order_id = self.place_order('YES', 'BID', yes_bid_price, bid_size)
                    if order_id:
                        result['placed_bids'].append({'token': 'YES', 'price': yes_bid_price, 'amount': bid_size})
                        result['volume_added'] += bid_size
                        self.session_volume += bid_size
                        self.orders_placed += 1
                        available -= bid_size
            
            if not has_no_bid and validate_price(no_bid_price) and available >= POINTS_MIN_ORDER_SIZE:
                bid_size = min(order_size, available)
                if bid_size >= POINTS_MIN_ORDER_SIZE:
                    order_id = self.place_order('NO', 'BID', no_bid_price, bid_size)
                    if order_id:
                        result['placed_bids'].append({'token': 'NO', 'price': no_bid_price, 'amount': bid_size})
                        result['volume_added'] += bid_size
                        self.session_volume += bid_size
                        self.orders_placed += 1
        
        # === ASK ордера ===
        # ЗАЩИТА ОТ УБЫТКОВ: не продаём ниже средней цены покупки + комиссия
        MIN_SELL_PROFIT = 1.01  # Минимум 1% прибыли
        
        can_sell_yes = True
        can_sell_no = True
        
        if self.yes_avg_buy_price is not None:
            min_yes_ask = self.yes_avg_buy_price * MIN_SELL_PROFIT
            if yes_ask_price < min_yes_ask:
                logger.warning(f"⚠️ YES ASK {yes_ask_price:.3f} < мин.цены {min_yes_ask:.3f} (avg buy {self.yes_avg_buy_price:.3f}) - ОТМЕНА")
                can_sell_yes = False
        
        if self.no_avg_buy_price is not None:
            min_no_ask = self.no_avg_buy_price * MIN_SELL_PROFIT
            if no_ask_price < min_no_ask:
                logger.warning(f"⚠️ NO ASK {no_ask_price:.3f} < мин.цены {min_no_ask:.3f} (avg buy {self.no_avg_buy_price:.3f}) - ОТМЕНА")
                can_sell_no = False
        
        if self.yes_balance > 0.1 and not has_yes_ask and validate_price(yes_ask_price) and can_sell_yes:
            safe_balance = self.yes_balance * 0.995
            ask_amount = safe_balance * yes_ask_price
            if ask_amount >= MIN_ORDER_USDT:  # Для ASK можно от $5
                order_id = self.place_order('YES', 'ASK', yes_ask_price, ask_amount)
                if order_id:
                    result['placed_asks'].append({'token': 'YES', 'price': yes_ask_price, 'amount': ask_amount})
                    result['volume_added'] += ask_amount
                    self.session_volume += ask_amount
                    self.orders_placed += 1
        
        if self.no_balance > 0.1 and not has_no_ask and validate_price(no_ask_price) and can_sell_no:
            safe_balance = self.no_balance * 0.995
            ask_amount = safe_balance * no_ask_price
            if ask_amount >= MIN_ORDER_USDT:
                order_id = self.place_order('NO', 'ASK', no_ask_price, ask_amount)
                if order_id:
                    result['placed_asks'].append({'token': 'NO', 'price': no_ask_price, 'amount': ask_amount})
                    result['volume_added'] += ask_amount
                    self.session_volume += ask_amount
                    self.orders_placed += 1
        
        # Логируем прогресс по поинтам
        session_hours = (datetime.now() - self.session_start).total_seconds() / 3600
        if session_hours > 0:
            volume_per_hour = self.session_volume / session_hours
            est_weekly = volume_per_hour * 24 * 7
            logger.info(f"📊 ПОИНТЫ: сессия ${self.session_volume:.2f} | ~${volume_per_hour:.2f}/час | прогноз ${est_weekly:.0f}/неделю")
            
            if est_weekly < POINTS_WEEKLY_TARGET:
                logger.warning(f"⚠️ Темп ниже ${POINTS_WEEKLY_TARGET}/неделю! Увеличьте баланс или размер ордеров.")
        
        return result
    
    def strategy_split(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float,
        amount_usdt: float = None
    ) -> Dict:
        """
        🎯 СТРАТЕГИЯ SPLIT - БЕЗРИСКОВЫЙ ФАРМИНГ ПОИНТОВ
        
        ФАЗА 1: Покупаем сразу YES и NO токены по рыночной цене
        ФАЗА 2: Выставляем на продажу на +1 цент от лучшего ASK
                (стоят в очереди, фармят поинты, не исполняются)
        
        ЛОГИКА:
        - BUY YES @ yes_ask (мгновенная покупка)
        - BUY NO @ no_ask (мгновенная покупка)
        - SELL YES @ yes_ask + 0.01 (на 1¢ выше → в очереди)
        - SELL NO @ no_ask + 0.01 (на 1¢ выше → в очереди)
        
        РЕЗУЛЬТАТ:
        - Токены куплены, стоят в стакане на продажу
        - Фармят поинты пока стоят в очереди
        - Независимо от исхода события = выход в 0 или плюс
        
        Args:
            yes_bid, yes_ask, no_bid, no_ask: Текущие цены из стакана
            amount_usdt: Сумма для split (если None - используем весь баланс)
            
        Returns:
            Dict с результатами
        """
        result = {
            'phase': None,
            'bought': [],
            'placed_asks': [],
            'volume_added': 0.0,
            'errors': [],
            'split_amount': 0.0
        }
        
        # Определяем сумму для split
        if amount_usdt is None:
            amount_usdt = self.usdt_balance
        
        # Валидация цен
        if not all([yes_ask > 0, no_ask > 0]):
            logger.warning("⚠️ SPLIT: Нет данных о ценах ASK")
            result['errors'].append("Нет данных о ценах ASK")
            return result
        
        logger.info(f"📊 SPLIT: Цены YES ASK: {yes_ask:.3f} | NO ASK: {no_ask:.3f}")
        
        # =====================================================================
        # ФАЗА 1: ПОКУПКА ТОКЕНОВ (если есть USDT и нет токенов)
        # =====================================================================
        
        # Проверяем нужно ли покупать
        need_buy_yes = self.yes_balance < 0.5  # Нет YES токенов
        need_buy_no = self.no_balance < 0.5    # Нет NO токенов
        
        if (need_buy_yes or need_buy_no) and self.usdt_balance >= SPLIT_MIN_ORDER_SIZE * 2:
            result['phase'] = 'BUYING'
            logger.info(f"🛒 ФАЗА 1: ПОКУПКА ТОКЕНОВ")
            
            # Делим доступный баланс пополам
            available = min(amount_usdt, self.usdt_balance)
            half_amount = available / 2
            
            # Покупаем YES (если нужно)
            if need_buy_yes and half_amount >= SPLIT_MIN_ORDER_SIZE:
                # Покупаем по цене ASK чтобы исполнилось сразу
                buy_price = yes_ask
                order_size = half_amount
                
                logger.info(f"   🟢 Покупаем YES @ {buy_price:.3f} за ${order_size:.2f}")
                order_id = self.place_order('YES', 'BID', buy_price, order_size)
                
                if order_id:
                    result['bought'].append({
                        'token': 'YES',
                        'price': buy_price,
                        'amount': order_size
                    })
                    result['volume_added'] += order_size
                    result['split_amount'] += order_size
                    self.session_volume += order_size
                    self.orders_placed += 1
            
            # Покупаем NO (если нужно)
            remaining = self.usdt_balance - result['split_amount']
            if need_buy_no and remaining >= SPLIT_MIN_ORDER_SIZE:
                buy_price = no_ask
                order_size = min(half_amount, remaining)
                
                logger.info(f"   🔴 Покупаем NO @ {buy_price:.3f} за ${order_size:.2f}")
                order_id = self.place_order('NO', 'BID', buy_price, order_size)
                
                if order_id:
                    result['bought'].append({
                        'token': 'NO',
                        'price': buy_price,
                        'amount': order_size
                    })
                    result['volume_added'] += order_size
                    result['split_amount'] += order_size
                    self.session_volume += order_size
                    self.orders_placed += 1
            
            if result['bought']:
                logger.info(f"   ✅ Куплено токенов на ${result['split_amount']:.2f}")
                logger.info(f"   ⏳ Ожидаем исполнения, затем выставим на продажу...")
            
            return result
        
        # =====================================================================
        # ФАЗА 2: ВЫСТАВЛЕНИЕ НА ПРОДАЖУ (если есть токены)
        # =====================================================================
        
        if self.yes_balance > 0.5 or self.no_balance > 0.5:
            result['phase'] = 'SELLING'
            logger.info(f"📤 ФАЗА 2: ВЫСТАВЛЕНИЕ НА ПРОДАЖУ")
            logger.info(f"   Балансы: YES={self.yes_balance:.2f} | NO={self.no_balance:.2f}")
            
            # Рассчитываем цены для ASK ордеров (на 1 цент ВЫШЕ лучшего ASK)
            yes_ask_price = round(yes_ask + SPLIT_OFFSET, 3)
            no_ask_price = round(no_ask + SPLIT_OFFSET, 3)
            
            # Валидация цен
            yes_ask_price = max(MIN_PRICE, min(yes_ask_price, MAX_PRICE))
            no_ask_price = max(MIN_PRICE, min(no_ask_price, MAX_PRICE))
            
            logger.info(f"   📍 Цены ASK: YES @ {yes_ask_price:.3f} (+1¢) | NO @ {no_ask_price:.3f} (+1¢)")
            
            # Проверяем активные ордера
            has_yes_ask = self.active_yes_ask
            has_no_ask = self.active_no_ask
            
            # Выставляем YES на продажу
            if self.yes_balance > 0.5 and not has_yes_ask and validate_price(yes_ask_price):
                safe_balance = self.yes_balance * 0.995  # 99.5% баланса
                ask_amount = safe_balance * yes_ask_price
                
                if ask_amount >= MIN_ORDER_USDT:
                    logger.info(f"   🟢 Выставляем YES на продажу @ {yes_ask_price:.3f}")
                    order_id = self.place_order('YES', 'ASK', yes_ask_price, ask_amount)
                    
                    if order_id:
                        result['placed_asks'].append({
                            'token': 'YES',
                            'price': yes_ask_price,
                            'amount': ask_amount
                        })
                        result['volume_added'] += ask_amount
                        self.session_volume += ask_amount
                        self.orders_placed += 1
            elif has_yes_ask:
                logger.info(f"   ⏸️ YES ASK уже активен")
            
            # Выставляем NO на продажу
            if self.no_balance > 0.5 and not has_no_ask and validate_price(no_ask_price):
                safe_balance = self.no_balance * 0.995
                ask_amount = safe_balance * no_ask_price
                
                if ask_amount >= MIN_ORDER_USDT:
                    logger.info(f"   🔴 Выставляем NO на продажу @ {no_ask_price:.3f}")
                    order_id = self.place_order('NO', 'ASK', no_ask_price, ask_amount)
                    
                    if order_id:
                        result['placed_asks'].append({
                            'token': 'NO',
                            'price': no_ask_price,
                            'amount': ask_amount
                        })
                        result['volume_added'] += ask_amount
                        self.session_volume += ask_amount
                        self.orders_placed += 1
            elif has_no_ask:
                logger.info(f"   ⏸️ NO ASK уже активен")
            
            if result['placed_asks']:
                logger.info(f"   ✅ Выставлено {len(result['placed_asks'])} ASK ордеров")
                logger.info(f"   🎯 Ордера стоят в очереди, фармят поинты!")
            else:
                logger.info(f"   ⏸️ Все ASK ордера уже активны, ждём...")
        
        # =====================================================================
        # НЕТ ДЕЙСТВИЙ (нет ни USDT ни токенов)
        # =====================================================================
        
        if result['phase'] is None:
            result['phase'] = 'WAITING'
            logger.info(f"⏳ SPLIT: Ожидание...")
            logger.info(f"   USDT: ${self.usdt_balance:.2f} | YES: {self.yes_balance:.2f} | NO: {self.no_balance:.2f}")
            
            if self.usdt_balance < SPLIT_MIN_ORDER_SIZE * 2 and self.yes_balance < 0.5 and self.no_balance < 0.5:
                logger.warning(f"   ⚠️ Недостаточно средств! Нужно минимум ${SPLIT_MIN_ORDER_SIZE * 2} или токены")
        
        return result
    
    def check_stale_orders_split(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> int:
        """
        Проверка устаревших ордеров для режима SPLIT.
        Переразмещаем ASK ордера если цена ушла более чем на 2%.
        """
        cancelled = 0
        threshold = 0.02  # 2%
        
        # YES ASK - сравниваем с ожидаемой ценой (ASK + offset)
        if self.active_yes_ask and self.active_order_prices.get('YES_ASK'):
            order_price = self.active_order_prices['YES_ASK']
            expected_price = yes_ask + SPLIT_OFFSET
            price_diff = abs(order_price - expected_price) / expected_price if expected_price > 0 else 0
            
            if price_diff > threshold:
                logger.info(f"🔄 [SPLIT] YES ASK устарел: {order_price:.3f} vs ожидаемый {expected_price:.3f} ({price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('YES_ASK')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_yes_ask = False
                self.active_order_prices['YES_ASK'] = None
                self.active_order_ids['YES_ASK'] = None
                cancelled += 1
        
        # NO ASK - сравниваем с ожидаемой ценой (ASK + offset)
        if self.active_no_ask and self.active_order_prices.get('NO_ASK'):
            order_price = self.active_order_prices['NO_ASK']
            expected_price = no_ask + SPLIT_OFFSET
            price_diff = abs(order_price - expected_price) / expected_price if expected_price > 0 else 0
            
            if price_diff > threshold:
                logger.info(f"🔄 [SPLIT] NO ASK устарел: {order_price:.3f} vs ожидаемый {expected_price:.3f} ({price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('NO_ASK')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_no_ask = False
                self.active_order_prices['NO_ASK'] = None
                self.active_order_ids['NO_ASK'] = None
                cancelled += 1
        
        if cancelled > 0:
            logger.info(f"🔄 [SPLIT] Переразмещение: отменено {cancelled} ASK ордеров")
        
        return cancelled

    def check_stale_orders_points_max(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> int:
        """
        Проверка устаревших ордеров для режима POINTS_MAX.
        Более агрессивный порог (2%) для частой ротации.
        """
        cancelled = 0
        threshold = POINTS_ROTATION_THRESHOLD  # 2%
        
        # YES BID
        if self.active_yes_bid and self.active_order_prices.get('YES_BID'):
            order_price = self.active_order_prices['YES_BID']
            price_diff = abs(order_price - yes_ask) / yes_ask if yes_ask > 0 else 0
            if price_diff > threshold:
                logger.info(f"🔄 [POINTS] YES BID устарел: {order_price:.3f} vs рынок {yes_ask:.3f} ({price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('YES_BID')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_yes_bid = False
                self.active_order_prices['YES_BID'] = None
                self.active_order_ids['YES_BID'] = None
                cancelled += 1
        
        # NO BID
        if self.active_no_bid and self.active_order_prices.get('NO_BID'):
            order_price = self.active_order_prices['NO_BID']
            price_diff = abs(order_price - no_ask) / no_ask if no_ask > 0 else 0
            if price_diff > threshold:
                logger.info(f"🔄 [POINTS] NO BID устарел: {order_price:.3f} vs рынок {no_ask:.3f} ({price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('NO_BID')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_no_bid = False
                self.active_order_prices['NO_BID'] = None
                self.active_order_ids['NO_BID'] = None
                cancelled += 1
        
        # YES ASK
        if self.active_yes_ask and self.active_order_prices.get('YES_ASK'):
            order_price = self.active_order_prices['YES_ASK']
            price_diff = abs(order_price - yes_ask) / yes_ask if yes_ask > 0 else 0
            if price_diff > threshold:
                logger.info(f"🔄 [POINTS] YES ASK устарел: {order_price:.3f} vs рынок {yes_ask:.3f} ({price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('YES_ASK')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_yes_ask = False
                self.active_order_prices['YES_ASK'] = None
                self.active_order_ids['YES_ASK'] = None
                cancelled += 1
        
        # NO ASK
        if self.active_no_ask and self.active_order_prices.get('NO_ASK'):
            order_price = self.active_order_prices['NO_ASK']
            price_diff = abs(order_price - no_ask) / no_ask if no_ask > 0 else 0
            if price_diff > threshold:
                logger.info(f"🔄 [POINTS] NO ASK устарел: {order_price:.3f} vs рынок {no_ask:.3f} ({price_diff*100:.1f}%)")
                order_id = self.active_order_ids.get('NO_ASK')
                if order_id:
                    self._cancel_order_safe(order_id)
                self.active_no_ask = False
                self.active_order_prices['NO_ASK'] = None
                self.active_order_ids['NO_ASK'] = None
                cancelled += 1
        
        if cancelled > 0:
            logger.info(f"🔄 [POINTS] Ротация: отменено {cancelled} ордеров для обновления цен")
        
        return cancelled
    
    # =========================================================================
    # ГЛАВНЫЙ ЦИКЛ
    # =========================================================================
    
    def update_cycle(self) -> Dict:
        """Один цикл обновления"""
        self.cycles += 1
        result = {
            'cycle': self.cycles,
            'strategy_result': None,
            'stale_cancelled': 0,
            'errors': []
        }
        
        # 1. Обновляем балансы
        self.update_balances()
        
        # 2. Проверяем исполнение ордеров по изменению балансов
        self.check_order_execution()
        
        # 3. Получаем цены
        yes_bid, yes_ask, no_bid, no_ask = self.get_prices()
        
        if not all([yes_bid, yes_ask, no_bid, no_ask]):
            result['errors'].append("Не удалось получить цены")
            return result
        
        logger.info(f"📊 Цены: YES {yes_bid:.3f}/{yes_ask:.3f} | NO {no_bid:.3f}/{no_ask:.3f}")
        logger.info(f"   Сумма ASK: {yes_ask + no_ask:.3f} | Сумма BID: {yes_bid + no_bid:.3f}")
        
        # 4. Проверяем и отменяем устаревшие ордера
        if self.strategy == 'points_max':
            # Для points_max - более агрессивная ротация (2%)
            result['stale_cancelled'] = self.check_stale_orders_points_max(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'split':
            # Для split - проверяем относительно ASK
            result['stale_cancelled'] = self.check_stale_orders_split(yes_bid, yes_ask, no_bid, no_ask)
        else:
            # Для остальных стратегий - стандартная проверка (3%)
            result['stale_cancelled'] = self.check_stale_orders(yes_bid, yes_ask, no_bid, no_ask)
        
        # 5. Если были отменены устаревшие ордера - обновляем балансы перед размещением новых
        if result['stale_cancelled'] > 0 and REPLACE_STALE_IMMEDIATELY:
            logger.info("🔄 Обновляем балансы после отмены устаревших ордеров...")
            time.sleep(1)  # Небольшая пауза для обновления данных на бирже
            self.update_balances()
        
        # 6. Выполняем стратегию
        if self.strategy == 'split':
            result['strategy_result'] = self.strategy_split(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'points_max':
            result['strategy_result'] = self.strategy_points_max(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'dual_side':
            result['strategy_result'] = self.strategy_dual_side(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'arbitrage':
            result['strategy_result'] = self.strategy_arbitrage(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'hybrid':
            result['strategy_result'] = self.strategy_hybrid(yes_bid, yes_ask, no_bid, no_ask)
        
        # 7. Логируем состояние ордеров
        active_count = sum([self.active_yes_bid, self.active_no_bid, self.active_yes_ask, self.active_no_ask])
        logger.info(f"📋 Активных ордеров: {active_count}/4 (YES_BID={self.active_yes_bid}, NO_BID={self.active_no_bid}, YES_ASK={self.active_yes_ask}, NO_ASK={self.active_no_ask})")
        
        return result
    
    def start(self):
        """Запустить бота"""
        logger.info("\n" + "="*60)
        logger.info("🚀 ЗАПУСК РЕАЛЬНОГО ТОРГОВОГО БОТА")
        logger.info("="*60)
        
        # 1. Загружаем рынок
        if not self.load_market_info():
            logger.error("❌ Не удалось загрузить рынок")
            return
        
        # 2. Активируем торговлю
        self.enable_trading()
        
        # 2.5. Инициализируем WebSocket для real-time данных
        if WEBSOCKET_AVAILABLE:
            self.init_websocket()
        else:
            logger.info("⚠️ WebSocket недоступен, используем только REST API")
        
        # 3. Отменяем все существующие ордера (чистый старт)
        logger.info("🗑️ Отмена существующих ордеров для чистого старта...")
        try:
            result = self.client.cancel_all_orders(market_id=self.market_id)
            if hasattr(result, 'result'):
                cancelled = getattr(result.result, 'cancelled', 0) if result.result else 0
                logger.info(f"   Отменено ордеров: {cancelled}")
        except Exception as e:
            logger.warning(f"   Не удалось отменить ордера: {e}")
        
        # 4. Сбрасываем флаги активных ордеров
        self.active_yes_ask = False
        self.active_no_ask = False
        self.active_yes_bid = False
        self.active_no_bid = False
        
        # 5. Показываем начальные балансы
        self.update_balances()
        
        logger.info(f"\n📊 Стратегия: {self.strategy.upper()}")
        logger.info(f"⏱️ Интервал проверки: {self.check_interval} сек")
        logger.info(f"📡 Источник данных: {'WebSocket (real-time)' if self.use_websocket else 'REST API (polling)'}")
        if self.strategy == 'split':
            logger.info(f"🎯 РЕЖИМ SPLIT - БЕЗРИСКОВЫЙ ФАРМИНГ!")
            logger.info(f"   - ФАЗА 1: Покупаем YES и NO сразу по рыночной цене")
            logger.info(f"   - ФАЗА 2: Выставляем на продажу @ ASK +${SPLIT_OFFSET:.2f}")
            logger.info(f"   - Ордера стоят в очереди, фармят поинты!")
            logger.info(f"   - Независимо от исхода = выход в 0 или плюс")
        if self.strategy == 'points_max':
            logger.info(f"🎯 РЕЖИМ МАКСИМИЗАЦИИ ПОИНТОВ АКТИВЕН!")
            logger.info(f"   - Фиксированный отступ: 0.1¢ от лучшей цены")
            logger.info(f"   - Мин. размер ордера: ${POINTS_MIN_ORDER_SIZE} (для бонусных поинтов)")
            logger.info(f"   - Порог ротации: {POINTS_ROTATION_THRESHOLD*100:.1f}%")
            logger.info(f"   - Цель: ${POINTS_WEEKLY_TARGET}/неделю минимум")
        logger.info("="*60 + "\n")
        
        # 6. Настраиваем graceful shutdown
        def signal_handler(signum, frame):
            logger.info("\n⚠️ Получен сигнал остановки...")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 7. Главный цикл
        self.running = True
        
        try:
            while self.running:
                try:
                    result = self.update_cycle()
                    
                    if result['errors']:
                        for err in result['errors']:
                            logger.warning(f"⚠️ {err}")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в цикле: {e}")
                
                logger.info(f"💤 Ожидание {self.check_interval} сек...\n")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("\n⚠️ Остановка по Ctrl+C")
            self.stop()
    
    def stop(self):
        """Остановить бота"""
        logger.info("\n🛑 Остановка бота...")
        self.running = False
        
        # Отключаем WebSocket
        self.disconnect_websocket()
        
        # Отменяем все ордера
        cancelled = self.cancel_all_orders()
        
        # Финальная статистика
        session_duration = datetime.now() - self.session_start
        session_hours = session_duration.total_seconds() / 3600
        
        logger.info("\n" + "="*60)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        logger.info("="*60)
        logger.info(f"   Время работы: {session_duration}")
        logger.info(f"   Циклов: {self.cycles}")
        logger.info(f"   Начальный баланс: ${self.initial_balance:.2f}" if self.initial_balance else "   Начальный баланс: N/A")
        logger.info(f"   Текущий баланс USDT: ${self.usdt_balance:.2f}")
        logger.info(f"   YES токены: {self.yes_balance:.2f}")
        logger.info(f"   NO токены: {self.no_balance:.2f}")
        
        logger.info("-"*60)
        logger.info("🎯 СТАТИСТИКА ПОИНТОВ:")
        logger.info(f"   Объём за сессию: ${self.session_volume:.2f}")
        logger.info(f"   Ордеров размещено: {self.orders_placed}")
        if session_hours > 0:
            volume_per_hour = self.session_volume / session_hours
            est_weekly = volume_per_hour * 24 * 7
            logger.info(f"   Скорость: ${volume_per_hour:.2f}/час")
            logger.info(f"   Прогноз на неделю: ${est_weekly:.0f}")
            if est_weekly >= POINTS_WEEKLY_TARGET:
                logger.info(f"   ✅ Темп достаточен для квалификации (>{POINTS_WEEKLY_TARGET}/неделю)")
            else:
                logger.info(f"   ⚠️ Темп ниже квалификационного порога ({POINTS_WEEKLY_TARGET}/неделю)")
        
        logger.info("-"*60)
        logger.info(f"   Арбитражных сделок: {self.arbitrage_trades}")
        logger.info(f"   Прибыль от арбитража: ${self.arbitrage_profit:.2f}")
        logger.info(f"   Общий PnL: ${self.total_pnl:.2f}")
        logger.info("="*60)


# =============================================================================
# 🎯 МУЛЬТИ-РЫНОК SPLIT ТРЕЙДЕР
# =============================================================================

class MultiMarketSplitTrader:
    """
    Мульти-рынок трейдер для стратегии SPLIT.
    Позволяет разделить баланс между несколькими рынками.
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.traders: Dict[int, RealTrader] = {}  # market_id -> RealTrader
        self.allocations: Dict[int, float] = {}   # market_id -> allocated USDT
        self.running = False
        
        # Загружаем конфигурацию
        load_dotenv()
        self.host = os.getenv('HOST', 'https://proxy.opinion.trade:8443')
        self.private_key = os.getenv('PRIVATE_KEY', '')
        self.multisig_wallet = os.getenv('MULTISIG_WALLET', '')
        self.chain_id = int(os.getenv('CHAIN_ID', '56'))
        self.rpc_url = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/')
        
        # Инициализируем SDK Client для получения баланса
        private_key_hex = self.private_key
        if private_key_hex.startswith('0x'):
            private_key_hex = private_key_hex[2:]
        
        self.client = Client(
            host=self.host,
            apikey=self.api_key,
            chain_id=self.chain_id,
            rpc_url=self.rpc_url,
            private_key=private_key_hex,
            multi_sig_addr=self.multisig_wallet
        )
    
    def get_usdt_balance(self) -> float:
        """Получить текущий баланс USDT"""
        try:
            response = self.client.get_my_balances()
            
            if response.errno != 0:
                logger.error(f"Ошибка получения баланса: {response.errmsg}")
                return 0.0
            
            balance_data = response.result
            if not hasattr(balance_data, 'balances') or not balance_data.balances:
                return 0.0
            
            usdt_address = '55d398326f99059ff775485246999027b3197955'
            
            for bal in balance_data.balances:
                quote_token = getattr(bal, 'quote_token', '').lower()
                if usdt_address in quote_token:
                    return float(getattr(bal, 'available_balance', 0))
            
            return float(getattr(balance_data.balances[0], 'available_balance', 0))
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            return 0.0
    
    def interactive_split_setup(self) -> List[Tuple[int, float]]:
        """
        Интерактивный выбор рынков и распределение баланса.
        
        Returns:
            List of (market_id, amount_usdt) tuples
        """
        markets_with_amounts = []
        finder = MarketFinder(self.api_key)
        
        while True:
            # Получаем текущий баланс
            current_balance = self.get_usdt_balance()
            
            # Вычитаем уже распределённые средства
            allocated = sum(self.allocations.values())
            available = current_balance - allocated
            
            print(f"\n{'='*70}")
            print(f"💰 БАЛАНС: ${current_balance:.2f} USDT")
            print(f"   Распределено: ${allocated:.2f}")
            print(f"   Доступно: ${available:.2f}")
            print(f"{'='*70}")
            
            if available < SPLIT_MIN_ORDER_SIZE * 2:
                print(f"⚠️ Недостаточно средств для нового split (минимум ${SPLIT_MIN_ORDER_SIZE * 2})")
                break
            
            # Если это первый рынок или есть ещё средства
            if not markets_with_amounts:
                # Первый рынок - выбираем
                market_id = select_market_interactive(self.api_key)
                if market_id is None:
                    print("👋 Выход без выбора рынка.")
                    return []
                
                # Спрашиваем: использовать всё или разделить?
                print(f"\n💡 Выбран рынок #{market_id}")
                print(f"   Доступно: ${available:.2f} USDT")
                print(f"\n   1. Использовать ВСЕ ${available:.2f} для этого рынка")
                print(f"   2. РАЗДЕЛИТЬ баланс (выбрать несколько рынков)")
                
                try:
                    choice = input("\n📌 Выберите (1 или 2) [1]: ").strip() or "1"
                except KeyboardInterrupt:
                    print("\n👋 Выход.")
                    return []
                
                if choice == "1":
                    # Используем всё
                    amount = available
                    markets_with_amounts.append((market_id, amount))
                    self.allocations[market_id] = amount
                    print(f"\n✅ Рынок #{market_id}: ${amount:.2f} (50% YES + 50% NO)")
                    break
                else:
                    # Разделяем - спрашиваем сумму
                    try:
                        amount_str = input(f"\n💵 Введите сумму для рынка #{market_id} (макс ${available:.2f}): ").strip()
                        amount = float(amount_str)
                        
                        if amount < SPLIT_MIN_ORDER_SIZE * 2:
                            print(f"⚠️ Минимум ${SPLIT_MIN_ORDER_SIZE * 2} для split")
                            amount = SPLIT_MIN_ORDER_SIZE * 2
                        elif amount > available:
                            print(f"⚠️ Максимум ${available:.2f}")
                            amount = available
                        
                        markets_with_amounts.append((market_id, amount))
                        self.allocations[market_id] = amount
                        print(f"\n✅ Рынок #{market_id}: ${amount:.2f} (50% YES + 50% NO)")
                        
                    except (ValueError, KeyboardInterrupt):
                        print("\n❌ Неверная сумма")
                        continue
            else:
                # Уже есть рынки - спрашиваем продолжить или нет
                available = self.get_usdt_balance() - sum(self.allocations.values())
                
                if available < SPLIT_MIN_ORDER_SIZE * 2:
                    print(f"\n⚠️ Осталось ${available:.2f} - недостаточно для нового split")
                    break
                
                print(f"\n❓ Выбрать новое событие или оставить как есть?")
                print(f"   Осталось: ${available:.2f} USDT")
                print(f"   Уже выбрано рынков: {len(markets_with_amounts)}")
                print(f"\n   1. Добавить ещё один рынок")
                print(f"   2. Оставить как есть (запустить бота)")
                
                try:
                    choice = input("\n📌 Выберите (1 или 2) [2]: ").strip() or "2"
                except KeyboardInterrupt:
                    print("\n👋 Запускаем с текущими настройками.")
                    break
                
                if choice != "1":
                    break
                
                # Выбираем новый рынок
                print("\n🔍 Выбор нового рынка...")
                market_id = select_market_interactive(self.api_key)
                
                if market_id is None:
                    print("⏸️ Отмена выбора рынка. Продолжаем с текущими.")
                    break
                
                # Проверяем что рынок ещё не выбран
                if market_id in self.allocations:
                    print(f"⚠️ Рынок #{market_id} уже выбран!")
                    continue
                
                # Спрашиваем: всё или часть?
                print(f"\n💡 У вас есть ${available:.2f} USDT")
                print(f"   1. Использовать ВСЕ ${available:.2f}")
                print(f"   2. РАЗДЕЛИТЬ (указать сумму)")
                
                try:
                    choice = input("\n📌 Выберите (1 или 2) [1]: ").strip() or "1"
                except KeyboardInterrupt:
                    break
                
                if choice == "1":
                    amount = available
                else:
                    try:
                        amount_str = input(f"\n💵 Введите сумму (макс ${available:.2f}): ").strip()
                        amount = float(amount_str)
                        
                        if amount < SPLIT_MIN_ORDER_SIZE * 2:
                            print(f"⚠️ Минимум ${SPLIT_MIN_ORDER_SIZE * 2}")
                            amount = SPLIT_MIN_ORDER_SIZE * 2
                        elif amount > available:
                            print(f"⚠️ Максимум ${available:.2f}")
                            amount = available
                            
                    except (ValueError, KeyboardInterrupt):
                        print("\n❌ Неверная сумма, пропускаем")
                        continue
                
                markets_with_amounts.append((market_id, amount))
                self.allocations[market_id] = amount
                print(f"\n✅ Рынок #{market_id}: ${amount:.2f} (50% YES + 50% NO)")
        
        # Выводим итоговое распределение
        if markets_with_amounts:
            print(f"\n{'='*70}")
            print("📊 ИТОГОВОЕ РАСПРЕДЕЛЕНИЕ:")
            print(f"{'='*70}")
            total = 0
            for market_id, amount in markets_with_amounts:
                print(f"   Рынок #{market_id}: ${amount:.2f}")
                total += amount
            print(f"{'='*70}")
            print(f"   ИТОГО: ${total:.2f}")
            remaining = self.get_usdt_balance() - total
            print(f"   Остаток: ${remaining:.2f}")
            print(f"{'='*70}")
            
            # Подтверждение
            try:
                confirm = input("\n✅ Запустить бота с этими настройками? (y/n) [y]: ").strip().lower() or "y"
                if confirm != 'y':
                    print("❌ Отменено")
                    return []
            except KeyboardInterrupt:
                print("\n❌ Отменено")
                return []
        
        return markets_with_amounts
    
    def create_traders(self, markets_with_amounts: List[Tuple[int, float]]):
        """Создать трейдеров для каждого рынка"""
        for market_id, amount in markets_with_amounts:
            logger.info(f"🔧 Создание трейдера для рынка #{market_id} с ${amount:.2f}")
            
            trader = RealTrader(
                market_id=market_id,
                strategy='split',
                order_amount=amount / 2  # Половина на YES, половина на NO
            )
            
            # Сохраняем выделенную сумму
            trader.split_allocation = amount
            
            self.traders[market_id] = trader
    
    def start_all(self):
        """Запустить всех трейдеров"""
        if not self.traders:
            logger.error("❌ Нет трейдеров для запуска")
            return
        
        print(f"\n{'='*70}")
        print(f"🚀 ЗАПУСК МУЛЬТИ-РЫНОК SPLIT БОТА")
        print(f"   Рынков: {len(self.traders)}")
        print(f"{'='*70}\n")
        
        # Инициализируем все рынки
        for market_id, trader in self.traders.items():
            logger.info(f"\n📊 Инициализация рынка #{market_id}...")
            
            if not trader.load_market_info():
                logger.error(f"❌ Не удалось загрузить рынок #{market_id}")
                continue
            
            trader.enable_trading()
            
            # Отменяем существующие ордера
            try:
                trader.client.cancel_all_orders(market_id=market_id)
            except:
                pass
        
        # Настройка graceful shutdown
        def signal_handler(signum, frame):
            logger.info("\n⚠️ Получен сигнал остановки...")
            self.stop_all()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.running = True
        cycles = 0
        
        # Главный цикл
        try:
            while self.running:
                cycles += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"🔄 ЦИКЛ #{cycles}")
                logger.info(f"{'='*60}")
                
                for market_id, trader in self.traders.items():
                    try:
                        logger.info(f"\n📈 Рынок #{market_id}:")
                        
                        # Обновляем балансы
                        trader.update_balances()
                        
                        # Проверяем исполнение
                        trader.check_order_execution()
                        
                        # Получаем цены
                        yes_bid, yes_ask, no_bid, no_ask = trader.get_prices()
                        
                        if not all([yes_bid, yes_ask, no_bid, no_ask]):
                            logger.warning(f"   ⚠️ Нет данных о ценах")
                            continue
                        
                        logger.info(f"   Цены: YES {yes_bid:.3f}/{yes_ask:.3f} | NO {no_bid:.3f}/{no_ask:.3f}")
                        
                        # Проверяем устаревшие ордера
                        stale = trader.check_stale_orders_split(yes_bid, yes_ask, no_bid, no_ask)
                        
                        if stale > 0:
                            time.sleep(1)
                            trader.update_balances()
                        
                        # Выполняем split стратегию
                        allocation = getattr(trader, 'split_allocation', trader.usdt_balance)
                        result = trader.strategy_split(yes_bid, yes_ask, no_bid, no_ask, allocation)
                        
                        if result.get('placed_bids'):
                            logger.info(f"   ✅ Размещено ордеров: {len(result['placed_bids'])}")
                        
                    except Exception as e:
                        logger.error(f"   ❌ Ошибка: {e}")
                
                logger.info(f"\n💤 Ожидание {CHECK_INTERVAL_POINTS_MAX} сек...")
                time.sleep(CHECK_INTERVAL_POINTS_MAX)
                
        except KeyboardInterrupt:
            logger.info("\n⚠️ Остановка по Ctrl+C")
            self.stop_all()
    
    def stop_all(self):
        """Остановить всех трейдеров"""
        logger.info("\n🛑 Остановка всех трейдеров...")
        self.running = False
        
        for market_id, trader in self.traders.items():
            logger.info(f"   Останавливаем рынок #{market_id}...")
            try:
                trader.cancel_all_orders()
            except:
                pass
        
        # Итоговая статистика
        print(f"\n{'='*60}")
        print("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        print(f"{'='*60}")
        
        total_volume = 0
        for market_id, trader in self.traders.items():
            print(f"\nРынок #{market_id}:")
            print(f"   Объём: ${trader.session_volume:.2f}")
            print(f"   YES токены: {trader.yes_balance:.2f}")
            print(f"   NO токены: {trader.no_balance:.2f}")
            total_volume += trader.session_volume
        
        print(f"\n{'='*60}")
        print(f"ОБЩИЙ ОБЪЁМ: ${total_volume:.2f}")
        print(f"{'='*60}")


# =============================================================================
# 🎯 ТОЧКА ВХОДА
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Opinion Trade Real Trading Bot v3.2 - SPLIT & POINTS MAXIMIZER',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # 🎯 SPLIT - БЕЗРИСКОВЫЙ ФАРМИНГ (мульти-рынок!)
  python real_trader.py --strategy split
  
  # 🎯 МАКСИМИЗАЦИЯ ПОИНТОВ
  python real_trader.py --market 3365 --strategy points_max

  # Интерактивный выбор рынка
  python real_trader.py

  # Market Making на конкретном рынке
  python real_trader.py --market 3365 --strategy dual_side

  # Арбитраж
  python real_trader.py --market 3365 --strategy arbitrage

  # Гибрид (70% MM + 30% арбитраж)
  python real_trader.py --market 3365 --strategy hybrid

  # С кастомными параметрами
  python real_trader.py --market 3365 --strategy points_max --amount 15

СТРАТЕГИЯ SPLIT (НОВОЕ!):
  - ФАЗА 1: Покупаем сразу YES и NO по рыночной цене
  - ФАЗА 2: Выставляем на продажу на +1 цент от ASK
  - Ордера стоят в очереди, фармят поинты
  - Независимо от исхода выходим в 0 или небольшой плюс
  - Максимальный фарминг поинтов БЕЗ РИСКА
  - Поддержка нескольких рынков одновременно!

СИСТЕМА ПОИНТОВ:
  - Лимитные ордера БЛИЖЕ к рынку = БОЛЬШЕ поинтов
  - Размер ордера > $10 = бонусные поинты
  - MAKER ордера (0% комиссия) = больше поинтов чем TAKER
  - Минимум $200/неделю для квалификации
  - Удержание токенов = дополнительные поинты
        """
    )
    
    parser.add_argument(
        '--market', '-m',
        type=int,
        required=False,
        default=None,
        help='ID бинарного рынка. Если не указан - интерактивный выбор'
    )
    
    parser.add_argument(
        '--strategy', '-s',
        type=str,
        choices=['dual_side', 'arbitrage', 'hybrid', 'points_max', 'split'],
        default='split',
        help='Стратегия торговли (по умолчанию: split - безрисковый фарминг поинтов)'
    )
    
    parser.add_argument(
        '--spread', '-sp',
        type=float,
        default=DEFAULT_SPREAD_PERCENT,
        help=f'Спред для market making (по умолчанию: {DEFAULT_SPREAD_PERCENT})'
    )
    
    parser.add_argument(
        '--amount', '-a',
        type=float,
        default=5.0,
        help='Размер ордера в USDT (по умолчанию: 5)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Включить debug логирование'
    )
    
    args = parser.parse_args()
    
    # Настройка логирования
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Заголовок
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║     Opinion Trade Real Trading Bot v3.2                   ║
    ║     SPLIT & POINTS MAXIMIZER                              ║
    ║     https://app.opinion.trade                             ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # Загружаем API ключ для выбора рынка
    load_dotenv()
    api_key = os.getenv('APIKEY', '')
    
    # === ИНТЕРАКТИВНЫЙ ВЫБОР СТРАТЕГИИ (если не указана в аргументах) ===
    if '--strategy' not in sys.argv and '-s' not in sys.argv and args.market is None:
        print("📊 ВЫБЕРИТЕ СТРАТЕГИЮ:")
        print("")
        print("  1. split      - 🎯 БЕЗРИСКОВЫЙ ФАРМИНГ ПОИНТОВ")
        print("                  Покупаем YES и NO, выставляем на +1¢ от рынка")
        print("                  Независимо от исхода = выход в 0 или плюс")
        print("                  Поддержка нескольких рынков!")
        print("")
        print("  2. points_max - 🚀 АГРЕССИВНАЯ МАКСИМИЗАЦИЯ ПОИНТОВ")
        print("                  Ордера близко к рынку, частая ротация")
        print("")
        print("  3. dual_side  - 📈 MARKET MAKING")
        print("                  BID/ASK со спредом, зарабатываем на разнице")
        print("")
        print("  4. arbitrage  - 💰 АРБИТРАЖ")
        print("                  BUY_BOTH / SELL_BOTH при неэффективности рынка")
        print("")
        print("  5. hybrid     - 🔄 ГИБРИД (70% MM + 30% арбитраж)")
        print("")
        
        try:
            choice = input("📌 Номер стратегии (1-5) [1]: ").strip() or "1"
            strategies = {'1': 'split', '2': 'points_max', '3': 'dual_side', '4': 'arbitrage', '5': 'hybrid'}
            args.strategy = strategies.get(choice, 'split')
            print(f"\n✅ Выбрана стратегия: {args.strategy.upper()}\n")
        except KeyboardInterrupt:
            print("\n👋 Выход.")
            return
    
    # === РЕЖИМ SPLIT С МУЛЬТИ-РЫНКОМ ===
    if args.strategy == 'split' and args.market is None:
        print("🎯 РЕЖИМ SPLIT - Безрисковый фарминг поинтов")
        print("   ФАЗА 1: Покупаем YES и NO по рыночной цене")
        print("   ФАЗА 2: Выставляем на продажу на +1¢ от ASK")
        print("   Ордера стоят в очереди, фармят поинты!")
        print("")
        
        multi_trader = MultiMarketSplitTrader(api_key)
        markets = multi_trader.interactive_split_setup()
        
        if not markets:
            print("\n👋 Выход.")
            return
        
        multi_trader.create_traders(markets)
        
        try:
            multi_trader.start_all()
        except KeyboardInterrupt:
            print("\n👋 До свидания!")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            raise
        
        return
    
    # === СТАНДАРТНЫЙ РЕЖИМ (один рынок) ===
    
    # Определяем market_id
    market_id = args.market
    
    if market_id is None:
        # Интерактивный выбор рынка
        market_id = select_market_interactive(api_key)
        
        if market_id is None:
            print("\n👋 Выход.")
            return
        
        # Спрашиваем размер ордера если не указан явно
        if '--amount' not in sys.argv and '-a' not in sys.argv:
            try:
                amount_input = input(f"\n💰 Размер ордера в USDT [{args.amount:.0f}]: ").strip()
                if amount_input:
                    args.amount = max(MIN_ORDER_USDT, float(amount_input))
            except (KeyboardInterrupt, ValueError):
                pass  # Используем значение по умолчанию
    
    print(f"\n🎯 Рынок: #{market_id}")
    print(f"📈 Стратегия: {args.strategy}")
    print(f"📊 Спред: {args.spread*100:.1f}%")
    print(f"💰 Размер ордера: ${args.amount:.2f}")
    
    # Создаем и запускаем бота
    try:
        bot = RealTrader(
            market_id=market_id,
            strategy=args.strategy,
            spread_percent=args.spread,
            order_amount=args.amount
        )
        bot.start()
        
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise


if __name__ == "__main__":
    main()