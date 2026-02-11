"""
Opinion Trade Market Maker Bot v2.2 - Чистый Market Making
==========================================================

СТРАТЕГИЯ: Чистый Market Making (без split)
✅ BID дешевле рынка → покупаем токены за USDT
✅ ASK дороже рынка → продаем токены за USDT
✅ Заработок на спреде между покупкой и продажей

ФУНКЦИИ (v2.2):
✨ 1. Выбор стратегии: dual_side, high_probability, custom
✨ 2. Поддержка нескольких рынков одновременно
✨ 3. Настраиваемые суммы ордеров для каждого рынка
✨ 4. Настраиваемый спред (0.05% - 10%)
✨ 5. Risk Management (макс. потеря, макс. позиция)
✨ 6. Отслеживание дневного PnL
✨ 7. Автоматическая отмена устаревших ордеров (порог 2%)
✨ 8. Graceful shutdown (Ctrl+C) с отменой всех ордеров
✨ 9. Адаптивный режим: <$6 = 1 BID, ≥$6 = 2 BID
"""
# -*- coding: utf-8 -*-

import time
import logging
from typing import Optional, List, Dict
import json
import os
import signal
import sys
from datetime import datetime, timedelta
from config import *
from opinion_clob_sdk import Client
from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER
from opinion_openapi import OpinionOpenAPI

# =============================================================================
# ⚙️ КОНФИГУРАЦИЯ - ЗАГРУЖАЕТСЯ ИЗ config.py И .env
# =============================================================================

# Для обратной совместимости
MARKET_ID = 1463
YES_TOKEN_ID = "91263182015381827009811905354009393225622653324877176380977546025702641459008"
NO_TOKEN_ID = "20149227795492566109318550481016190805078857503551684520611528784231324976722"

# Суммы ордеров (по умолчанию)
DEFAULT_BID_AMOUNT = 5.0  # USDT для BID (минимум $5)
DEFAULT_ASK_AMOUNT = 5.0  # USDT для ASK (минимум $5)

# Минимальные требования платформы
MIN_ORDER_USDT = 5.00  # Минимум по стоимости в USDT ($5)
MIN_ORDER_AMOUNT = 5   # USDT (минимум на платформе)

# Комиссии (MAKER FEE = 0% для лимит-ордеров!)
MAKER_FEE = 0.0  
MIN_FEE = 0.5    # Минимальная комиссия для TAKER ($0.5)

# Стратегия
TICK_SIZE = 0.01  # Минимальный шаг торговли
DEFAULT_SPREAD_PERCENT = 0.10  # Спред 10% (минимальный безопасный спред)
CHECK_INTERVAL = 30  # Проверять цены каждые 30 сек

# Файл для сохранения состояния
STATE_FILE = "bot_state_v2.json"

# =============================================================================
# 📝 НАСТРОЙКА ЛОГИРОВАНИЯ
# =============================================================================

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# 🤖 БОТ v2.0 - С РАСШИРЕННЫМИ ФУНКЦИЯМИ
# =============================================================================

class OpinionMarketMakerV2:
    """
    Расширенный Market Maker Bot v2.0
    
    Новые параметры:
    -----------------
    strategy_type : str
        'dual_side' - двусторонняя торговля (по умолчанию)
        'high_probability' - торгуем только токен с вероятностью >50%
        'custom' - указываем конкретный токен (YES или NO)
    
    custom_token : str, optional
        Для strategy_type='custom': 'YES' или 'NO'
    
    markets : list[dict], optional
        Список рынков для торговли. Каждый словарь содержит:
        {
            'market_id': int,
            'yes_token_id': str,
            'no_token_id': str,
            'bid_amount': float,  # USDT для BID
            'ask_amount': float,  # USDT для ASK
            'name': str  # Опциональное название
        }
        Если не указано, использует MARKET_ID из конфига
    
    spread_percent : float
        Спред в процентах (0.0001 - 0.01), по умолчанию 0.001 (0.1%)
        Примеры:
        - 0.0005 = 0.05% (очень узкий)
        - 0.001 = 0.1% (нормальный)
        - 0.002 = 0.2% (широкий)
        - 0.005 = 0.5% (очень широкий)
    
    max_daily_loss : float, optional
        Максимальная дневная потеря в USDT. Бот остановится при достижении.
        None = без лимита (по умолчанию)
    
    max_position_size : float
        Максимальный размер позиции в % от баланса (0.1 - 1.0)
        По умолчанию 0.5 (50% баланса)
    
    Пример использования:
    ---------------------
    # 1. Простой режим (как bot.py):
    bot = OpinionMarketMakerV2()
    
    # 2. High Probability стратегия с узким спредом:
    bot = OpinionMarketMakerV2(
        strategy_type='high_probability',
        spread_percent=0.0005  # 0.05%
    )
    
    # 3. Несколько рынков с разными суммами:
    bot = OpinionMarketMakerV2(
        strategy_type='dual_side',
        markets=[
            {
                'market_id': 1951,
                'yes_token_id': 'xxx',
                'no_token_id': 'yyy',
                'bid_amount': 10.0,
                'ask_amount': 10.0
            },
            {
                'market_id': 1463,
                'yes_token_id': 'aaa',
                'no_token_id': 'bbb',
                'bid_amount': 5.0,
                'ask_amount': 5.0
            }
        ]
    )
    
    # 4. Custom стратегия с риск-менеджментом:
    bot = OpinionMarketMakerV2(
        strategy_type='custom',
        custom_token='YES',
        spread_percent=0.002,  # 0.2%
        max_daily_loss=50.0,   # Стоп при -$50
        max_position_size=0.3  # Не более 30% баланса
    )
    """
    
    def __init__(
        self,
        strategy_type: str = 'dual_side',
        custom_token: Optional[str] = None,
        markets: Optional[List[Dict]] = None,
        spread_percent: float = DEFAULT_SPREAD_PERCENT,
        max_daily_loss: Optional[float] = None,
        max_position_size: float = 0.5
    ):
        """
        Инициализация бота с расширенными параметрами
        """
        # Валидация стратегии
        if strategy_type not in ['dual_side', 'high_probability', 'custom']:
            raise ValueError(f"Неверный strategy_type: {strategy_type}. Допустимые: dual_side, high_probability, custom")
        
        if strategy_type == 'custom' and custom_token not in ['YES', 'NO']:
            raise ValueError(f"Для strategy_type='custom' укажите custom_token='YES' или 'NO'")
        
        # Валидация спреда (расширено до 10%)
        if not (0.0001 <= spread_percent <= 0.10):
            raise ValueError(f"spread_percent должен быть от 0.0001 (0.01%) до 0.10 (10%). Указано: {spread_percent}")
        
        # Валидация max_position_size
        if not (0.1 <= max_position_size <= 1.0):
            raise ValueError(f"max_position_size должен быть от 0.1 (10%) до 1.0 (100%). Указано: {max_position_size}")
        
        # Сохраняем параметры
        self.strategy_type = strategy_type
        self.custom_token = custom_token
        self.spread_percent = spread_percent
        self.max_daily_loss = max_daily_loss
        self.max_position_size = max_position_size
        
        logger.info(f"🎯 Инициализация OpinionMarketMakerV2")
        logger.info(f"   Стратегия: {strategy_type}")
        if strategy_type == 'custom':
            logger.info(f"   Токен: {custom_token}")
        logger.info(f"   Спред: {spread_percent*100:.2f}%")
        if max_daily_loss:
            logger.info(f"   Макс. дневная потеря: ${max_daily_loss:.2f}")
        logger.info(f"   Макс. размер позиции: {max_position_size*100:.0f}%")
        
        # Настройка рынков
        if markets is None:
            # Используем рынок из конфига (для обратной совместимости)
            self.markets = [{
                'market_id': MARKET_ID,
                'yes_token_id': YES_TOKEN_ID,
                'no_token_id': NO_TOKEN_ID,
                'bid_amount': DEFAULT_BID_AMOUNT,
                'ask_amount': DEFAULT_ASK_AMOUNT,
                'name': f'Market {MARKET_ID}'
            }]
            logger.info(f"   Рынок: {MARKET_ID} (по умолчанию)")
        else:
            # Валидируем markets
            for m in markets:
                required_keys = ['market_id', 'yes_token_id', 'no_token_id', 'bid_amount', 'ask_amount']
                if not all(k in m for k in required_keys):
                    raise ValueError(f"Рынок должен содержать: {required_keys}. Найдено: {m.keys()}")
                if m['bid_amount'] < MIN_ORDER_USDT or m['ask_amount'] < MIN_ORDER_USDT:
                    raise ValueError(f"Минимальная сумма ордера: ${MIN_ORDER_USDT}. Рынок {m['market_id']}: BID={m['bid_amount']}, ASK={m['ask_amount']}")
            
            self.markets = markets
            logger.info(f"   Рынков: {len(markets)}")
            for m in markets:
                logger.info(f"     - #{m['market_id']}: BID=${m['bid_amount']}, ASK=${m['ask_amount']}")
        
        # Инициализация SDK Client
        try:
            if not PRIVATE_KEY:
                raise ValueError("PRIVATE_KEY не установлен в .env файле")
            
            private_key = PRIVATE_KEY
            if isinstance(private_key, str) and private_key.startswith('0x'):
                private_key_hex = private_key[2:]
            else:
                private_key_hex = private_key
            
            self.client = Client(
                host=HOST,
                apikey=APIKEY if APIKEY else "",
                chain_id=CHAIN_ID,
                rpc_url=RPC_URL,
                private_key=private_key_hex,
                multi_sig_addr=MULTISIG_WALLET
            )
            logger.info("✅ Client инициализирован успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Client: {e}")
            raise
        
        # Состояние для каждого рынка
        self.market_states = {}
        for market in self.markets:
            market_id = market['market_id']
            self.market_states[market_id] = {
                'bid_order_id': None,
                'ask_order_id': None,
                'bid_price': None,
                'ask_price': None,
                'bid_placed_time': None,
                'ask_placed_time': None,
                'trading_token': None,
                'yes_balance': 0.0,
                'no_balance': 0.0
            }
        
        # Глобальное состояние
        self.running = False
        self.usdt_balance = 0.0
        
        # Risk Management
        self.daily_pnl = 0.0
        self.daily_pnl_reset_time = datetime.now().date()
        self.initial_balance = None  # Устанавливается при первом запуске
        
        # Сохранить/загрузить состояние
        self.load_state()
    
    def save_state(self):
        """Сохранить состояние в файл"""
        try:
            state = {
                'strategy_type': self.strategy_type,
                'custom_token': self.custom_token,
                'spread_percent': self.spread_percent,
                'markets': self.markets,
                'market_states': self.market_states,
                'daily_pnl': self.daily_pnl,
                'daily_pnl_reset_time': self.daily_pnl_reset_time.isoformat(),
                'initial_balance': self.initial_balance
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"💾 Состояние сохранено в {STATE_FILE}")
        except Exception as e:
            logger.warning(f"⚠️  Ошибка сохранения состояния: {e}")
    
    def load_state(self):
        """Загрузить состояние из файла"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                
                # Merge market_states вместо полной замены
                saved_market_states = state.get('market_states', {})
                for market_id, market_state in saved_market_states.items():
                    # Преобразуем ключ в int (JSON сохраняет как строку)
                    market_id_int = int(market_id)
                    if market_id_int in self.market_states:
                        # Обновляем существующий market_state
                        self.market_states[market_id_int].update(market_state)
                
                self.daily_pnl = state.get('daily_pnl', 0.0)
                
                reset_time_str = state.get('daily_pnl_reset_time')
                if reset_time_str:
                    self.daily_pnl_reset_time = datetime.fromisoformat(reset_time_str).date()
                
                self.initial_balance = state.get('initial_balance')
                
                logger.info(f"📂 Состояние загружено из {STATE_FILE}")
                logger.info(f"   Daily PnL: ${self.daily_pnl:.2f}")
        except Exception as e:
            logger.warning(f"⚠️  Ошибка загрузки состояния: {e}")
    
    def reset_daily_pnl_if_needed(self):
        """Сбросить дневной PnL если наступил новый день"""
        current_date = datetime.now().date()
        if current_date > self.daily_pnl_reset_time:
            logger.info(f"🔄 Новый день - сброс Daily PnL (было: ${self.daily_pnl:.2f})")
            self.daily_pnl = 0.0
            self.daily_pnl_reset_time = current_date
            self.save_state()
    
    def check_risk_limits(self) -> bool:
        """
        Проверить риск-лимиты
        
        Returns:
            True если торговля разрешена
            False если достигнут лимит
        """
        # Сброс daily PnL если новый день
        self.reset_daily_pnl_if_needed()
        
        # Проверка макс. дневной потери
        if self.max_daily_loss is not None:
            if self.daily_pnl <= -self.max_daily_loss:
                logger.warning(f"⛔ Достигнут лимит дневной потери: ${self.daily_pnl:.2f} / -${self.max_daily_loss:.2f}")
                logger.warning(f"   Торговля остановлена на сегодня")
                return False
        
        return True
    
    def calculate_allowed_order_size(self, requested_amount: float) -> float:
        """
        Рассчитать разрешенный размер ордера с учетом max_position_size
        
        Args:
            requested_amount: Запрошенная сумма ордера
        
        Returns:
            Разрешенная сумма (может быть меньше requested)
        """
        if self.usdt_balance <= 0:
            return 0.0
        
        max_allowed = self.usdt_balance * self.max_position_size
        
        if requested_amount > max_allowed:
            logger.info(f"ℹ️  Запрошено ${requested_amount:.2f}, но макс. позиция {self.max_position_size*100:.0f}% = ${max_allowed:.2f}")
            return max(max_allowed, MIN_ORDER_USDT)  # Не ниже минимума платформы
        
        return requested_amount
    
    # =========================================================================
    # МЕТОДЫ ИЗ ОРИГИНАЛЬНОГО bot.py (для обратной совместимости)
    # =========================================================================
    
    def enable_trading(self):
        """Включить торговлю"""
        try:
            self.client.enable_trading()
            logger.info("✅ Торговля активирована")
            return True
        except:
            logger.info("⚠️  Торговля уже активирована")
            return True
    
    # Методы split удалены - получаем токены только через BID ордера (market making)
    
    def get_balance(self):
        """Получить доступный USDT баланс"""
        try:
            response = self.client.get_my_balances()
            
            if response.errno != 0:
                logger.error(f"Ошибка получения баланса: {response.errmsg}")
                return None
            
            balance_data = response.result
            if not hasattr(balance_data, 'balances') or not balance_data.balances:
                logger.warning("⚠️  Нет данных о балансе")
                return None
            
            usdt_balance = None
            for bal in balance_data.balances:
                quote_token = getattr(bal, 'quote_token', '').lower()
                if '55d398326f99059ff775485246999027b3197955' in quote_token:
                    usdt_balance = float(getattr(bal, 'available_balance', 0))
                    break
            
            if usdt_balance is None:
                balance = balance_data.balances[0]
                usdt_balance = float(getattr(balance, 'available_balance', 0))
            
            # Установить initial_balance при первом вызове
            if self.initial_balance is None:
                self.initial_balance = usdt_balance
                logger.info(f"💰 Начальный баланс установлен: ${usdt_balance:.2f}")
            
            self.usdt_balance = usdt_balance
            return usdt_balance
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении баланса: {e}")
            return None
    
    def get_token_balance(self, market_id: int, token_name: str) -> float:
        """Получить баланс конкретного токена для рынка"""
        try:
            response = self.client.get_my_positions()
            
            if response.errno != 0:
                return 0
            
            positions_data = response.result
            if not hasattr(positions_data, 'list') or not positions_data.list:
                return 0
            
            # Найти market в self.markets
            market = next((m for m in self.markets if m['market_id'] == market_id), None)
            if not market:
                return 0
            
            target_outcome = "Yes" if token_name == "YES" else "No"
            
            for pos in positions_data.list:
                pos_market_id = getattr(pos, 'market_id', None)
                pos_outcome = getattr(pos, 'outcome_side_enum', None)
                pos_token_id = getattr(pos, 'token_id', '')
                
                # Ищем по market_id и outcome (token_id может быть placeholder)
                if pos_market_id == market_id and pos_outcome == target_outcome:
                    shares_str = getattr(pos, 'shares_owned', '0')
                    available = float(shares_str) if shares_str else 0
                    
                    # Обновляем token_id в конфиге если это placeholder
                    if token_name == "YES" and market['yes_token_id'] == "YOUR_YES_TOKEN_ID_HERE":
                        market['yes_token_id'] = str(pos_token_id)
                        logger.info(f"✅ Обновлен YES token_id для рынка {market_id}: {pos_token_id}")
                    elif token_name == "NO" and market['no_token_id'] == "YOUR_NO_TOKEN_ID_HERE":
                        market['no_token_id'] = str(pos_token_id)
                        logger.info(f"✅ Обновлен NO token_id для рынка {market_id}: {pos_token_id}")
                    
                    return available
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении баланса {token_name} для рынка {market_id}: {e}")
            return 0
    
    def show_all_balances(self):
        """Показать все балансы (USDT + токены для всех рынков)"""
        try:
            logger.info("📊 Все балансы:")
            
            usdt_balance = self.get_balance()
            if usdt_balance is not None:
                logger.info(f"   USDT: ${usdt_balance:.2f}")
            
            for market in self.markets:
                market_id = market['market_id']
                market_name = market.get('name', f'Market {market_id}')
                
                yes_balance = self.get_token_balance(market_id, "YES")
                no_balance = self.get_token_balance(market_id, "NO")
                
                logger.info(f"   {market_name}:")
                logger.info(f"     YES: {yes_balance:.4f}")
                logger.info(f"     NO: {no_balance:.4f}")
            
            # Показать PnL
            if self.initial_balance is not None:
                total_pnl = usdt_balance - self.initial_balance
                logger.info(f"   Total PnL: ${total_pnl:+.2f}")
                logger.info(f"   Daily PnL: ${self.daily_pnl:+.2f}")
                
        except Exception as e:
            logger.warning(f"⚠️  Не удалось получить полные балансы: {e}")
    
    def get_market_price(self, market_id: int):
        """Получить лучшие цены для рынка через SDK"""
        try:
            # Найти market config
            market = next((m for m in self.markets if m['market_id'] == market_id), None)
            if not market:
                logger.error(f"❌ Рынок {market_id} не найден в конфигурации")
                return None, None, None, None
            
            yes_token_id = market['yes_token_id']
            no_token_id = market['no_token_id']
            
            # Получить стакан YES токена через SDK
            response_yes = self.client.get_orderbook(yes_token_id)
            if response_yes.errno != 0:
                logger.error(f"Ошибка получения YES стакана: {response_yes.errmsg}")
                return None, None, None, None
            
            # Получить стакан NO токена через SDK
            response_no = self.client.get_orderbook(no_token_id)
            if response_no.errno != 0:
                logger.error(f"Ошибка получения NO стакана: {response_no.errmsg}")
                return None, None, None, None
            
            # Обработать YES стакан
            book_yes = response_yes.result.data if hasattr(response_yes.result, 'data') else response_yes.result
            yes_bids = []
            yes_asks = []
            
            logger.debug(f"📖 YES Orderbook raw data:")
            logger.debug(f"   BIDs count: {len(book_yes.bids) if book_yes.bids else 0}")
            logger.debug(f"   ASKs count: {len(book_yes.asks) if book_yes.asks else 0}")
            
            if book_yes.bids:
                for i, bid_obj in enumerate(book_yes.bids[:5]):  # Показываем первые 5
                    bid_price = getattr(bid_obj, 'price', None)
                    bid_size = getattr(bid_obj, 'size', None)
                    logger.debug(f"   BID[{i}]: price={bid_price}, size={bid_size}")
                    if bid_price:
                        yes_bids.append(float(bid_price))
            
            if book_yes.asks:
                for i, ask_obj in enumerate(book_yes.asks[:5]):  # Показываем первые 5
                    ask_price = getattr(ask_obj, 'price', None)
                    ask_size = getattr(ask_obj, 'size', None)
                    logger.debug(f"   ASK[{i}]: price={ask_price}, size={ask_size}")
                    if ask_price:
                        yes_asks.append(float(ask_price))
            
            # API уже возвращает отсортированные данные:
            # bids[0] = лучший BID (самый высокий)
            # asks[0] = лучший ASK (самый низкий)
            # Сортировка НЕ нужна - берем первый элемент!
            
            best_yes_bid = yes_bids[0] if yes_bids else None
            best_yes_ask = yes_asks[0] if yes_asks else None
            
            logger.debug(f"   ✅ Best YES BID: {best_yes_bid}, Best YES ASK: {best_yes_ask}")
            
            # Обработать NO стакан
            book_no = response_no.result.data if hasattr(response_no.result, 'data') else response_no.result
            no_bids = []
            no_asks = []
            
            if book_no.bids:
                for bid_obj in book_no.bids:
                    bid_price = getattr(bid_obj, 'price', None)
                    if bid_price:
                        no_bids.append(float(bid_price))
            
            if book_no.asks:
                for ask_obj in book_no.asks:
                    ask_price = getattr(ask_obj, 'price', None)
                    if ask_price:
                        no_asks.append(float(ask_price))
            
            # API уже возвращает отсортированные данные - берем первый элемент
            best_no_bid = no_bids[0] if no_bids else None
            best_no_ask = no_asks[0] if no_asks else None
            
            # Валидация цен
            if not all([best_yes_bid, best_yes_ask, best_no_bid, best_no_ask]):
                logger.warning(f"⚠️  Неполные данные orderbook для рынка {market_id}")
                return None, None, None, None
            
            return best_yes_bid, best_yes_ask, best_no_bid, best_no_ask
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения цен для рынка {market_id}: {e}")
            return None, None, None, None
    
    # =========================================================================
    # УПРАВЛЕНИЕ ОРДЕРАМИ
    # =========================================================================
    
    def get_open_orders(self, market_id: int) -> List[Dict]:
        """
        Получить список открытых ордеров для рынка
        
        Args:
            market_id: ID рынка
            
        Returns:
            Список открытых ордеров
        """
        try:
            response = self.client.get_my_orders(
                market_id=market_id,
                status="open",
                limit=50
            )
            
            if response.errno != 0:
                logger.error(f"Ошибка получения ордеров: {response.errmsg}")
                return []
            
            orders = response.result.list if hasattr(response.result, 'list') else []
            return orders
            
        except Exception as e:
            logger.error(f"❌ Ошибка get_open_orders: {e}")
            return []
    
    def cancel_stale_orders(self, market_id: int, threshold_percent: float = 0.02) -> int:
        """
        Отменить устаревшие ордера если цена ушла больше чем на threshold_percent
        
        Args:
            market_id: ID рынка
            threshold_percent: Порог отклонения цены (по умолчанию 2%)
            
        Returns:
            Количество отмененных ордеров
        """
        try:
            # Получить текущие цены
            best_yes_bid, best_yes_ask, best_no_bid, best_no_ask = self.get_market_price(market_id)
            if not all([best_yes_bid, best_yes_ask, best_no_bid, best_no_ask]):
                return 0
            
            # Получить открытые ордера
            orders = self.get_open_orders(market_id)
            if not orders:
                return 0
            
            # Найти рынок в конфигурации
            market = next((m for m in self.markets if m['market_id'] == market_id), None)
            if not market:
                return 0
            
            cancelled_count = 0
            orders_to_cancel = []
            
            for order in orders:
                order_price = float(order.price) if hasattr(order, 'price') else 0
                order_side = order.side if hasattr(order, 'side') else None
                token_id = order.token_id if hasattr(order, 'token_id') else ""
                order_id = order.order_id if hasattr(order, 'order_id') else ""
                
                if not order_price or not order_id:
                    continue
                
                # Определить YES или NO токен
                is_yes = (token_id == market['yes_token_id'])
                current_best = best_yes_bid if is_yes else best_no_bid
                
                # Проверить отклонение цены
                if order_side == OrderSide.BUY:
                    # BID ордер - сравниваем с текущим best_bid
                    price_diff = abs(order_price - current_best) / current_best
                    if price_diff > threshold_percent:
                        orders_to_cancel.append(order_id)
                        logger.info(f"   🗑️  Отменяем BID {token_id[:8]}... @ {order_price:.3f} (best: {current_best:.3f}, diff: {price_diff*100:.1f}%)")
                elif order_side == OrderSide.SELL:
                    # ASK ордер - сравниваем с текущим best_ask
                    current_best_ask = best_yes_ask if is_yes else best_no_ask
                    price_diff = abs(order_price - current_best_ask) / current_best_ask
                    if price_diff > threshold_percent:
                        orders_to_cancel.append(order_id)
                        logger.info(f"   🗑️  Отменяем ASK {token_id[:8]}... @ {order_price:.3f} (best: {current_best_ask:.3f}, diff: {price_diff*100:.1f}%)")
            
            # Отменить ордера батчем
            if orders_to_cancel:
                results = self.client.cancel_orders_batch(orders_to_cancel)
                for i, result in enumerate(results):
                    if result.get('success', False):
                        cancelled_count += 1
                    else:
                        logger.warning(f"   ⚠️  Не удалось отменить ордер: {result.get('error', 'Unknown error')}")
            
            if cancelled_count > 0:
                logger.info(f"✅ Отменено {cancelled_count} устаревших ордеров")
            
            return cancelled_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка cancel_stale_orders: {e}")
            return 0
    
    def cancel_all_market_orders(self, market_id: int) -> int:
        """
        Отменить все открытые ордера на рынке
        
        Args:
            market_id: ID рынка
            
        Returns:
            Количество отмененных ордеров
        """
        try:
            result = self.client.cancel_all_orders(market_id=market_id)
            cancelled = result.get('cancelled', 0)
            if cancelled > 0:
                logger.info(f"✅ Отменено {cancelled} ордеров на рынке {market_id}")
            return cancelled
        except Exception as e:
            logger.error(f"❌ Ошибка cancel_all_market_orders: {e}")
            return 0
    
    # =========================================================================
    # НОВАЯ ЛОГИКА update_orders() с поддержкой стратегий
    # =========================================================================
    
    def update_orders_for_market(self, market_id: int) -> bool:
        """
        Обновить ордера для конкретного рынка с учетом выбранной стратегии
        
        Args:
            market_id: ID рынка
        
        Returns:
            True если ордера успешно обновлены
        """
        # Найти конфиг рынка
        market = next((m for m in self.markets if m['market_id'] == market_id), None)
        if not market:
            logger.error(f"❌ Рынок {market_id} не найден в конфигурации")
            return False
        
        market_name = market.get('name', f'Market {market_id}')
        logger.info(f"🔄 Обновление ордеров для {market_name} (#{market_id})")
        
        # Получить цены
        best_yes_bid, best_yes_ask, best_no_bid, best_no_ask = self.get_market_price(market_id)
        
        if not all([best_yes_bid, best_yes_ask, best_no_bid, best_no_ask]):
            logger.warning(f"⚠️  Нет данных для размещения ордеров на рынке {market_id}")
            return False
        
        # Средние цены
        yes_mid = (best_yes_bid + best_yes_ask) / 2
        no_mid = (best_no_bid + best_no_ask) / 2
        
        logger.info(f"💹 YES: BID {best_yes_bid:.4f} | ASK {best_yes_ask:.4f} (mid: {yes_mid:.4f})")
        logger.info(f"💹 NO:  BID {best_no_bid:.4f} | ASK {best_no_ask:.4f} (mid: {no_mid:.4f})")
        
        # Получить балансы
        yes_balance = self.get_token_balance(market_id, "YES")
        no_balance = self.get_token_balance(market_id, "NO")
        
        self.market_states[market_id]['yes_balance'] = yes_balance
        self.market_states[market_id]['no_balance'] = no_balance
        
        has_tokens = yes_balance > 0.01 or no_balance > 0.01
        has_usdt = self.usdt_balance > MIN_ORDER_USDT
        
        logger.info(f"💰 USDT: ${self.usdt_balance:.2f}, YES: {yes_balance:.4f}, NO: {no_balance:.4f}")
        
        # =====================================================================
        # КОНСТАНТЫ И ИНИЦИАЛИЗАЦИЯ
        # =====================================================================
        
        USDT_THRESHOLD = 6.0  # Порог переключения режимов
        TICK_SIZE = 0.001     # Минимальный шаг цены
        
        bid_token = None
        ask_token = None
        target_bid = None
        target_ask = None
        bid_orders = []
        ask_orders = []
        orders_placed = 0
        
        # =====================================================================
        # ВЫБОР СТРАТЕГИИ
        # =====================================================================
        
        if self.strategy_type == 'dual_side':
            # ✅ СТРАТЕГИЯ 1: Адаптивный Market Making
            logger.info(f"🎯 Стратегия: DUAL-SIDE MARKET MAKING (Адаптивный)")
            
            # ═════════════════════════════════════════════════════════════════
            # АДАПТИВНЫЙ РЕЖИМ в зависимости от баланса USDT:
            #
            # РЕЖИМ A (USDT < $6): Экономный - чередуем токены
            # РЕЖИМ B (USDT ≥ $6): Полноценный dual-side
            # ═════════════════════════════════════════════════════════════════
            
            if self.usdt_balance < USDT_THRESHOLD:
                # ═══ РЕЖИМ A: ЭКОНОМНЫЙ (< $6) ═══
                logger.info(f"📊 РЕЖИМ A: Экономный (USDT: ${self.usdt_balance:.2f} < ${USDT_THRESHOLD:.2f})")
                logger.info(f"💡 Покупаем 1 токен → Продаем оба → Чередуем YES/NO")
                
                # ASK: продаем ОБА если есть
                if yes_balance > 0.01:
                    # Ставим ТОЧНО по цене лучшего ASK (первые в очереди)
                    yes_ask_price = round(best_yes_ask, 3)
                    ask_orders.append(("YES", yes_ask_price))
                    logger.info(f"   💸 ASK YES @ {yes_ask_price:.3f}")
                
                if no_balance > 0.01:
                    no_ask_price = round(best_no_ask, 3)
                    ask_orders.append(("NO", no_ask_price))
                    logger.info(f"   💸 ASK NO @ {no_ask_price:.3f}")
                
                # BID: покупаем ОДИН (которого меньше)
                if has_usdt:
                    if yes_balance <= no_balance:
                        selected_token = "YES"
                        selected_price = round(best_yes_bid + TICK_SIZE, 3)
                    else:
                        selected_token = "NO"
                        selected_price = round(best_no_bid + TICK_SIZE, 3)
                    
                    bid_orders.append((selected_token, selected_price))
                    logger.info(f"   💵 BID {selected_token} @ {selected_price:.3f}")
                    logger.info(f"      (Баланс: YES={yes_balance:.2f}, NO={no_balance:.2f})")
            
            else:
                # ═══ РЕЖИМ B: ПОЛНОЦЕННЫЙ (≥ $6) ═══
                logger.info(f"📊 РЕЖИМ B: Полноценный dual-side (USDT: ${self.usdt_balance:.2f})")
                logger.info(f"💡 Покупаем YES + NO → Продаем YES + NO")
                
                # BID: покупаем ОБА
                if has_usdt:
                    yes_bid_price = round(best_yes_bid + TICK_SIZE, 3)
                    bid_orders.append(("YES", yes_bid_price))
                    logger.info(f"   💵 BID YES @ {yes_bid_price:.3f}")
                    
                    no_bid_price = round(best_no_bid + TICK_SIZE, 3)
                    bid_orders.append(("NO", no_bid_price))
                    logger.info(f"   💵 BID NO @ {no_bid_price:.3f}")
                
                # ASK: продаем ОБА если есть
                if yes_balance > 0.01:
                    # Ставим ТОЧНО по цене лучшего ASK (первые в очереди)
                    yes_ask_price = round(best_yes_ask, 3)
                    ask_orders.append(("YES", yes_ask_price))
                    logger.info(f"   💸 ASK YES @ {yes_ask_price:.3f}")
                
                if no_balance > 0.01:
                    no_ask_price = round(best_no_ask, 3)
                    ask_orders.append(("NO", no_ask_price))
                    logger.info(f"   💸 ASK NO @ {no_ask_price:.3f}")
            
        elif self.strategy_type == 'high_probability':
            # ✅ СТРАТЕГИЯ 2: Только высоковероятный токен
            logger.info(f"🎯 Стратегия: HIGH PROBABILITY (только >50%)")
            
            # Определяем более вероятный токен
            if yes_mid > 0.5:
                target_token = "YES"
                token_mid = yes_mid
                logger.info(f"   • Торгуем YES ({yes_mid*100:.1f}% вероятность)")
            else:
                target_token = "NO"
                token_mid = no_mid
                logger.info(f"   • Торгуем NO ({no_mid*100:.1f}% вероятность)")
            
            # Размещаем BID и ASK на этот токен
            if has_usdt:
                bid_token = target_token
                target_bid = round(token_mid - (token_mid * self.spread_percent), 4)
                logger.info(f"   • BID {target_token} @ {target_bid:.4f}")
            
            if has_tokens:
                token_balance = yes_balance if target_token == "YES" else no_balance
                if token_balance > 0.01:
                    ask_token = target_token
                    target_ask = round(token_mid + (token_mid * self.spread_percent), 4)
                    logger.info(f"   • ASK {target_token} @ {target_ask:.4f}")
            
        elif self.strategy_type == 'custom':
            # ✅ СТРАТЕГИЯ 3: Кастомный выбор токена
            logger.info(f"🎯 Стратегия: CUSTOM (токен: {self.custom_token})")
            
            target_token = self.custom_token
            token_mid = yes_mid if target_token == "YES" else no_mid
            
            # Размещаем BID и ASK на выбранный токен
            if has_usdt:
                bid_token = target_token
                target_bid = round(token_mid - (token_mid * self.spread_percent), 4)
                logger.info(f"   • BID {target_token} @ {target_bid:.4f}")
            
            if has_tokens:
                token_balance = yes_balance if target_token == "YES" else no_balance
                if token_balance > 0.01:
                    ask_token = target_token
                    target_ask = round(token_mid + (token_mid * self.spread_percent), 4)
                    logger.info(f"   • ASK {target_token} @ {target_ask:.4f}")
        
        # =====================================================================
        # РАЗМЕЩЕНИЕ ОРДЕРОВ
        # =====================================================================
        
        logger.info(f"📝 Размещение ордеров для {market_name}:")
        
        success = False
        
        # Для dual_side используем списки ордеров
        if self.strategy_type == 'dual_side' and bid_orders:
            # Размещаем ASK ордера (продажа токенов)
            for ask_token, target_ask in ask_orders:
                token_balance = yes_balance if ask_token == "YES" else no_balance
                token_id = market['yes_token_id'] if ask_token == "YES" else market['no_token_id']
                
                # Рассчитываем количество токенов для продажи
                tokens_needed = market['ask_amount'] / target_ask
                
                if token_balance >= tokens_needed:
                    tokens_to_sell = tokens_needed
                    ask_amount_usdt = market['ask_amount']
                else:
                    # Продаем всё что есть
                    tokens_to_sell = token_balance
                    ask_amount_usdt = token_balance * target_ask
                    logger.warning(f"   ⚠️  Недостаточно {ask_token}: нужно {tokens_needed:.2f}, есть {token_balance:.2f}")
                
                logger.info(f"   📤 ASK {ask_token}: {tokens_to_sell:.2f} токенов @ {target_ask:.4f} ≈ ${ask_amount_usdt:.2f}")
                
                # Проверка минимальной суммы ордера
                if ask_amount_usdt < MIN_ORDER_USDT:
                    logger.warning(f"   ⚠️  Сумма ${ask_amount_usdt:.2f} < минимум ${MIN_ORDER_USDT:.2f}. Пропуск ASK {ask_token}.")
                else:
                    try:
                        # Размещаем ASK ордер через SDK
                        order_input = PlaceOrderDataInput(
                            marketId=market_id,
                            tokenId=token_id,
                            side=OrderSide.SELL,
                            orderType=LIMIT_ORDER,
                            price=str(target_ask),
                            makerAmountInQuoteToken=str(ask_amount_usdt)
                        )
                    
                        response = self.client.place_order(order_input)
                        
                        if response.errno == 0:
                            order_id = getattr(response.result, 'order_id', None)
                            logger.info(f"   ✅ ASK {ask_token} размещен! ID: {order_id}, ${ask_amount_usdt:.2f}")
                            orders_placed += 1
                        else:
                            logger.error(f"   ❌ Ошибка ASK {ask_token}: {response.errmsg}")
                    except Exception as e:
                        logger.error(f"   ❌ Исключение ASK {ask_token}: {e}")
            
            # Размещаем BID ордера (покупка за USDT)
            if bid_orders:
                if self.usdt_balance < USDT_THRESHOLD:
                    # ═══ РЕЖИМ A: Весь USDT в ОДИН BID ═══
                    logger.info(f"   💵 Размещение BID (РЕЖИМ A): 1 ордер на весь баланс")
                    
                    bid_token, target_bid = bid_orders[0]
                    bid_amount = self.calculate_allowed_order_size(market['bid_amount'])
                    token_id = market['yes_token_id'] if bid_token == "YES" else market['no_token_id']
                    
                    tokens_to_buy = bid_amount / target_bid
                    
                    logger.info(f"   📥 BID {bid_token}: {tokens_to_buy:.2f} токенов @ {target_bid:.3f} за ${bid_amount:.2f}")
                    
                    if bid_amount < MIN_ORDER_USDT:
                        logger.warning(f"   ⚠️  Баланс: ${self.usdt_balance:.2f}, требуется: ${MIN_ORDER_USDT:.2f}")
                        logger.warning(f"   ⚠️  Недостаточно USDT для BID. Пропуск.")
                    else:
                        try:
                            order_input = PlaceOrderDataInput(
                                marketId=market_id,
                                tokenId=token_id,
                                side=OrderSide.BUY,
                                orderType=LIMIT_ORDER,
                                price=str(target_bid),
                                makerAmountInQuoteToken=str(bid_amount)
                            )
                        
                            response = self.client.place_order(order_input)
                            
                            if response.errno == 0:
                                order_id = getattr(response.result, 'order_id', None)
                                logger.info(f"   ✅ BID {bid_token} размещен! ID: {order_id}")
                                self.market_states[market_id]['bid_order_id'] = order_id
                                self.market_states[market_id]['bid_price'] = target_bid
                                orders_placed += 1
                            else:
                                logger.error(f"   ❌ Ошибка BID {bid_token}: {response.errmsg}")
                        except Exception as e:
                            logger.error(f"   ❌ Исключение BID {bid_token}: {e}")
                
                else:
                    # ═══ РЕЖИМ B: USDT делится пополам на 2 BID ═══
                    logger.info(f"   💵 Размещение BID (РЕЖИМ B): {len(bid_orders)} ордеров")
                    
                    bid_amount_per_order = market['bid_amount'] / len(bid_orders)
                    
                    for bid_token, target_bid in bid_orders:
                        bid_amount = self.calculate_allowed_order_size(bid_amount_per_order)
                        token_id = market['yes_token_id'] if bid_token == "YES" else market['no_token_id']
                        
                        tokens_to_buy = bid_amount / target_bid
                        
                        logger.info(f"   📥 BID {bid_token}: {tokens_to_buy:.2f} токенов @ {target_bid:.3f} за ${bid_amount:.2f}")
                        
                        if bid_amount < MIN_ORDER_USDT:
                            logger.warning(f"   ⚠️  Сумма ${bid_amount:.2f} < минимум ${MIN_ORDER_USDT:.2f}. Пропуск BID {bid_token}.")
                            continue
                        
                        try:
                            order_input = PlaceOrderDataInput(
                                marketId=market_id,
                                tokenId=token_id,
                                side=OrderSide.BUY,
                                orderType=LIMIT_ORDER,
                                price=str(target_bid),
                                makerAmountInQuoteToken=str(bid_amount)
                            )
                        
                            response = self.client.place_order(order_input)
                            
                            if response.errno == 0:
                                order_id = getattr(response.result, 'order_id', None)
                                logger.info(f"   ✅ BID {bid_token} размещен! ID: {order_id}")
                                orders_placed += 1
                            else:
                                logger.error(f"   ❌ Ошибка BID {bid_token}: {response.errmsg}")
                        except Exception as e:
                            logger.error(f"   ❌ Исключение BID {bid_token}: {e}")
            
            success = orders_placed > 0
            
        # Для других стратегий - старая логика (одиночные ордера)
        elif ask_token and target_ask:
            token_balance = yes_balance if ask_token == "YES" else no_balance
            token_id = market['yes_token_id'] if ask_token == "YES" else market['no_token_id']
            
            # Рассчитываем количество токенов для продажи
            tokens_needed = market['ask_amount'] / target_ask
            
            if token_balance >= tokens_needed:
                tokens_to_sell = tokens_needed
                ask_amount_usdt = market['ask_amount']
            else:
                # Продаем всё что есть
                tokens_to_sell = token_balance
                ask_amount_usdt = token_balance * target_ask
                logger.warning(f"   ⚠️  Недостаточно {ask_token}: нужно {tokens_needed:.2f}, есть {token_balance:.2f}")
            
            logger.info(f"   📤 ASK: {ask_token} @ {target_ask:.4f}")
            logger.info(f"      Продаем: {tokens_to_sell:.2f} токенов ≈ ${ask_amount_usdt:.2f}")
            
            # Проверка минимальной суммы ордера
            if ask_amount_usdt < MIN_ORDER_USDT:
                logger.warning(f"   ⚠️  Сумма ${ask_amount_usdt:.2f} < минимум ${MIN_ORDER_USDT:.2f}. Пропуск ASK.")
            else:
                try:
                    # Размещаем ASK ордер через SDK
                    # ВАЖНО: makerAmountInQuoteToken - это USDT сумма, не количество токенов!
                    order_input = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.SELL,
                        orderType=LIMIT_ORDER,
                        price=str(target_ask),
                        makerAmountInQuoteToken=str(ask_amount_usdt)  # Сумма в USDT
                    )
                
                    response = self.client.place_order(order_input)
                    
                    if response.errno == 0:
                        order_id = getattr(response.result, 'order_id', None)
                        logger.info(f"   ✅ ASK ордер размещен! ID: {order_id}")
                        logger.info(f"      Цена: ${target_ask:.4f}, Сумма: ${ask_amount_usdt:.2f}")
                        self.market_states[market_id]['ask_order_id'] = order_id
                        self.market_states[market_id]['ask_price'] = target_ask
                        success = True
                    else:
                        logger.error(f"   ❌ Ошибка размещения ASK: {response.errmsg}")
                except Exception as e:
                    logger.error(f"   ❌ Исключение при размещении ASK: {e}")
        
        # Размещаем BID (покупка за USDT)
        if bid_token and target_bid:
            bid_amount = self.calculate_allowed_order_size(market['bid_amount'])
            token_id = market['yes_token_id'] if bid_token == "YES" else market['no_token_id']
            
            # Рассчитываем количество токенов которые купим
            tokens_to_buy = bid_amount / target_bid
            
            logger.info(f"   📥 BID: {bid_token} @ {target_bid:.4f}")
            logger.info(f"      Покупаем: {tokens_to_buy:.2f} токенов за ${bid_amount:.2f}")
            
            # Проверка минимальной суммы ордера
            if bid_amount < MIN_ORDER_USDT:
                logger.warning(f"   ⚠️  Сумма ${bid_amount:.2f} < минимум ${MIN_ORDER_USDT:.2f}. Пропуск BID.")
            else:
                try:
                    # ВАЖНО: makerAmountInQuoteToken - это USDT сумма, не количество токенов!
                    order_input = PlaceOrderDataInput(
                        marketId=market_id,
                        tokenId=token_id,
                        side=OrderSide.BUY,
                        orderType=LIMIT_ORDER,
                        price=str(target_bid),
                        makerAmountInQuoteToken=str(bid_amount)  # Сумма в USDT
                    )
                
                    response = self.client.place_order(order_input)
                    
                    if response.errno == 0:
                        order_id = getattr(response.result, 'order_id', None)
                        logger.info(f"   ✅ BID ордер размещен! ID: {order_id}")
                        logger.info(f"      Цена: ${target_bid:.4f}, Сумма: ${bid_amount:.2f}")
                        self.market_states[market_id]['bid_order_id'] = order_id
                        self.market_states[market_id]['bid_price'] = target_bid
                        success = True
                    else:
                        logger.error(f"   ❌ Ошибка размещения BID: {response.errmsg}")
                except Exception as e:
                    logger.error(f"   ❌ Исключение при размещении BID: {e}")
        
        return success
    
    def update_orders(self):
        """
        Обновить ордера для всех рынков
        """
        # Проверка риск-лимитов
        if not self.check_risk_limits():
            logger.warning("⛔ Торговля заблокирована риск-менеджментом")
            return False
        
        # Получить баланс
        usdt_balance = self.get_balance()
        if usdt_balance is None:
            logger.warning("⚠️  Не удалось получить баланс USDT")
            return False
        
        logger.info(f"💰 Текущий баланс: ${usdt_balance:.2f}")
        logger.info(f"📊 Daily PnL: ${self.daily_pnl:+.2f}")
        
        # Отменить устаревшие ордера (порог 2%)
        for market in self.markets:
            market_id = market['market_id']
            cancelled = self.cancel_stale_orders(market_id, threshold_percent=0.02)
            if cancelled > 0:
                logger.info(f"🗑️  Отменено {cancelled} устаревших ордеров на рынке {market_id}")
        
        # Обновить ордера для каждого рынка
        success_count = 0
        for market in self.markets:
            market_id = market['market_id']
            if self.update_orders_for_market(market_id):
                success_count += 1
        
        logger.info(f"✅ Обновлено {success_count}/{len(self.markets)} рынков")
        
        # Сохранить состояние
        self.save_state()
        
        return success_count > 0
    
    def setup_signal_handlers(self):
        """Настроить обработчики сигналов для graceful shutdown"""
        def signal_handler(signum, frame):
            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info(f"\n⚠️  Получен сигнал {signal_name}. Останавливаем бота...")
            self.stop()
            sys.exit(0)
        
        # Регистрируем обработчики
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # kill command
        logger.info("✅ Обработчики сигналов настроены (Ctrl+C для остановки)")
    
    def start(self):
        """Запустить бота"""
        logger.info("🚀 Запуск OpinionMarketMakerV2")
        logger.info(f"   Стратегия: {self.strategy_type}")
        logger.info(f"   Рынков: {len(self.markets)}")
        logger.info(f"   Спред: {self.spread_percent*100:.2f}%")
        
        # Настроить обработчики сигналов
        self.setup_signal_handlers()
        
        self.enable_trading()
        self.show_all_balances()
        
        # Для dual_side стратегии - чистый market making
        # Токены получаем через BID ордера, split не нужен
        if self.strategy_type == 'dual_side':
            logger.info("\n" + "="*60)
            logger.info("🎯 Стратегия: Чистый Market Making")
            logger.info("="*60)
            logger.info("💡 Логика:")
            logger.info("   1. BID дешевле рынка → покупаем токены за USDT")
            logger.info("   2. Ждем исполнения → получаем токены")
            logger.info("   3. ASK дороже рынка → продаем токены")
            logger.info("   4. Заработок на спреде")
            logger.info("="*60 + "\n")
        
        self.running = True
        
        try:
            while self.running:
                logger.info(f"\n{'='*60}")
                logger.info(f"🔄 Цикл обновления ордеров")
                logger.info(f"{'='*60}\n")
                
                self.update_orders()
                
                logger.info(f"\n⏳ Ожидание {CHECK_INTERVAL} секунд...")
                time.sleep(CHECK_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("\n⏹️  Остановка бота (Ctrl+C)")
            self.stop()
        except Exception as e:
            logger.error(f"❌ Ошибка в главном цикле: {e}", exc_info=True)
            self.stop()
    
    def stop(self):
        """Остановить бота и отменить все ордера"""
        logger.info("🛑 Остановка бота...")
        self.running = False
        
        # Отменить все ордера на всех рынках
        logger.info("🗑️  Отмена всех открытых ордеров...")
        for market in self.markets:
            market_id = market['market_id']
            cancelled = self.cancel_all_market_orders(market_id)
            if cancelled > 0:
                logger.info(f"   Рынок {market_id}: отменено {cancelled} ордеров")
        
        # Сохранить состояние
        self.save_state()
        logger.info("⏹️  Бот остановлен")

# =============================================================================
# 🎯 ТОЧКА ВХОДА
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║  Opinion Trade Market Maker Bot v2.2                      ║
    ║  Adaptive Dual-Side Strategy                              ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # Автоматический запуск в dual-side режиме
    bot = OpinionMarketMakerV2(strategy_type='dual_side')
    bot.start()
