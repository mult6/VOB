"""
Автоматический виртуальный трейдер (логика из bot_v2.py)
Работает с реальными ценами, но виртуальными позициями
"""
# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Константы
MIN_ORDER_USDT = 5.0
TICK_SIZE = 0.001
DEFAULT_SPREAD_PERCENT = 0.10  # 10%
USDT_THRESHOLD = 6.0  # Порог для переключения режимов
STALE_ORDER_THRESHOLD = 0.02  # 2% для отмены устаревших ордеров
PRICE_CHANGE_NOTIFICATION_THRESHOLD = 0.01  # 1% изменение цены для уведомления

# Комиссии Opinion Trade (из документации)
# Maker (лимит ордера) = 0% БЕСПЛАТНО!
# Taker (маркет ордера) = topic_rate * price * (1 - price) * discounts
# Минимальная комиссия = $0.50
TAKER_FEE_TOPIC_RATE = 0.08  # Базовый коэффициент (может отличаться для разных рынков)
MIN_TAKER_FEE = 0.50  # Минимальная комиссия $0.50

# Арбитраж
# Split: $1 USDT → 1 YES + 1 NO токен
# Merge: 1 YES + 1 NO → $1 USDT  
ARBITRAGE_MIN_PROFIT_PERCENT = 0.01  # Минимальная прибыль 1% для арбитража (с учётом комиссий)

# Гибридная стратегия (hybrid)
# Распределение баланса между dual_side и арбитражем
HYBRID_DUAL_SIDE_PERCENT = 0.70  # 70% на маркет-мейкинг
HYBRID_ARBITRAGE_PERCENT = 0.30  # 30% резерв для арбитража


def calculate_taker_fee(price: float, amount: float, topic_rate: float = TAKER_FEE_TOPIC_RATE) -> float:
    """
    Рассчитать комиссию taker по формуле Opinion Trade.
    
    Fee = topic_rate × price × (1 − price) × notional
    Минимум = $0.50
    
    Args:
        price: Цена токена (0-1)
        amount: Сумма сделки в USDT
        topic_rate: Коэффициент рынка (по умолчанию 0.08)
    
    Returns:
        Комиссия в USDT
    """
    # Формула: fee_rate = topic_rate * price * (1 - price)
    # При price=0.5: fee_rate = 0.08 * 0.5 * 0.5 = 0.02 (2%)
    # При price=0.1: fee_rate = 0.08 * 0.1 * 0.9 = 0.0072 (0.72%)
    fee_rate = topic_rate * price * (1 - price)
    fee = amount * fee_rate
    
    # Минимальная комиссия $0.50
    return max(fee, MIN_TAKER_FEE)


@dataclass
class VirtualOrder:
    """Виртуальный ордер"""
    order_id: str
    token: str  # 'YES' или 'NO'
    side: str   # 'BID' или 'ASK'
    price: float
    amount: float  # В USDT
    tokens: float  # Количество токенов
    created_at: datetime = field(default_factory=datetime.now)
    status: str = 'open'  # 'open', 'filled', 'cancelled'


@dataclass
class Trade:
    """Исполненная сделка"""
    trade_id: str
    token: str
    side: str  # 'BUY' или 'SELL'
    price: float
    amount: float
    tokens: float
    pnl: float = 0.0
    executed_at: datetime = field(default_factory=datetime.now)


class AutoTrader:
    """
    Автоматический виртуальный трейдер
    
    Работает как bot_v2.py:
    - Автоматически размещает BID/ASK ордера со спредом
    - Проверяет исполнение по реальным ценам
    - Обновляет ордера при изменении цен
    - Ведет учет PnL
    
    Поддерживает два режима получения цен:
    1. API polling (по умолчанию) - запрос каждые 30 сек
    2. WebSocket (realtime) - мгновенные обновления
    """
    
    def __init__(
        self,
        user_id: int,
        balance: float,
        market_id: int,
        market_info: Dict,
        api,  # OpinionAuthAPI
        strategy: str = 'dual_side',
        spread_percent: float = DEFAULT_SPREAD_PERCENT,
        order_amount: float = 5.0,
        websocket_provider=None  # WebSocketPriceProvider для realtime
    ):
        self.user_id = user_id
        self.balance = balance
        self.initial_balance = balance
        self.market_id = market_id
        self.market_info = market_info
        self.api = api
        self.websocket_provider = websocket_provider  # Опциональный WebSocket
        
        # Настройки стратегии
        self.strategy = strategy  # 'dual_side', 'yes_only', 'no_only', 'arbitrage', 'hybrid'
        self.spread_percent = spread_percent
        self.order_amount = max(order_amount, MIN_ORDER_USDT)
        
        # Для гибридной стратегии: распределение баланса
        self.hybrid_dual_side_percent = HYBRID_DUAL_SIDE_PERCENT
        self.hybrid_arbitrage_percent = HYBRID_ARBITRAGE_PERCENT
        self.arbitrage_reserve = 0.0  # Резерв для арбитража
        
        # Арбитраж статистика
        self.arbitrage_trades = 0
        self.arbitrage_profit = 0.0
        
        # Позиции (виртуальные токены)
        self.yes_tokens = 0.0
        self.no_tokens = 0.0
        
        # Активные ордера
        self.orders: Dict[str, VirtualOrder] = {}
        self._order_counter = 0
        
        # История сделок
        self.trades: List[Trade] = []
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        
        # Статус
        self.is_running = False
        self.last_update = None
        self.cycles_count = 0
        
        # Предыдущие цены для отслеживания изменений
        self.prev_yes_bid = None
        self.prev_yes_ask = None
        self.prev_no_bid = None
        self.prev_no_ask = None
        
        # Базовые цены для уведомлений (обновляются только при отправке уведомления)
        self.base_yes_price = None
        self.base_no_price = None
        
        # Средние цены покупки (для расчета PnL)
        self.avg_yes_buy_price = 0.0
        self.avg_no_buy_price = 0.0
        
        logger.info(f"🤖 AutoTrader создан для пользователя {user_id}")
        logger.info(f"   Рынок: #{market_id}")
        logger.info(f"   Баланс: ${balance:.2f}")
        logger.info(f"   Стратегия: {strategy}")
        logger.info(f"   Спред: {spread_percent*100:.1f}%")
    
    def _generate_order_id(self) -> str:
        """Генерация уникального ID ордера"""
        self._order_counter += 1
        return f"V{self.user_id}_{self._order_counter}_{int(datetime.now().timestamp())}"
    
    def get_prices(self) -> Tuple[Optional[float], ...]:
        """
        Получить текущие цены.
        
        Использует WebSocket если доступен (realtime),
        иначе делает API запрос (polling).
        
        Returns:
            (yes_bid, yes_ask, no_bid, no_ask)
        """
        try:
            # Пробуем WebSocket (realtime)
            if self.websocket_provider:
                prices = self.websocket_provider.get_prices(self.market_id)
                if all(prices):  # Все цены доступны
                    return prices
                # Если WebSocket не имеет данных, fallback к API
                logger.debug("WebSocket no data, falling back to API")
            
            # Fallback: API polling
            return self.api.get_market_prices_from_orderbook(
                self.market_id,
                self.market_info['yes_token_id'],
                self.market_info['no_token_id']
            )
        except Exception as e:
            logger.error(f"Ошибка получения цен: {e}")
            return None, None, None, None
    
    def start(self):
        """Запустить автоторговлю"""
        self.is_running = True
        logger.info(f"▶️ AutoTrader запущен для пользователя {self.user_id}")
    
    def stop(self) -> Dict:
        """Остановить автоторговлю и вернуть статистику"""
        self.is_running = False
        
        # Отменяем все ордера
        cancelled_orders = self.cancel_all_orders()
        
        # Финальная статистика
        stats = {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'yes_tokens': self.yes_tokens,
            'no_tokens': self.no_tokens,
            'total_pnl': self.total_pnl,
            'trades_count': len(self.trades),
            'cycles_count': self.cycles_count,
            'cancelled_orders': len(cancelled_orders)
        }
        
        logger.info(f"⏹️ AutoTrader остановлен для пользователя {self.user_id}")
        return stats
    
    def cancel_all_orders(self) -> List[VirtualOrder]:
        """Отменить все открытые ордера"""
        cancelled = []
        
        for order_id, order in list(self.orders.items()):
            if order.status == 'open':
                order.status = 'cancelled'
                
                # Возвращаем средства
                if order.side == 'BID':
                    self.balance += order.amount
                elif order.side == 'ASK':
                    if order.token == 'YES':
                        self.yes_tokens += order.tokens
                    else:
                        self.no_tokens += order.tokens
                
                cancelled.append(order)
                del self.orders[order_id]
        
        return cancelled
    
    def update_orders(self) -> Dict:
        """
        Главный цикл обновления ордеров (как в bot_v2.py)
        
        Returns:
            Словарь с результатами: размещенные ордера, исполненные сделки, ошибки
        """
        if not self.is_running:
            return {'error': 'Trader не запущен'}
        
        self.cycles_count += 1
        self.last_update = datetime.now()
        
        result = {
            'placed_orders': [],
            'executed_trades': [],
            'cancelled_orders': [],
            'repositioned_orders': [],  # Ордера переставленные из-за "прыжка" цены
            'price_changes': [],  # Уведомления об изменении цен
            'errors': []
        }
        
        # 1. Получаем цены
        yes_bid, yes_ask, no_bid, no_ask = self.get_prices()
        
        if not all([yes_bid, yes_ask, no_bid, no_ask]):
            result['errors'].append('Не удалось получить цены')
            return result
        
        yes_mid = (yes_bid + yes_ask) / 2
        no_mid = (no_bid + no_ask) / 2
        
        logger.debug(f"📊 Цены: YES {yes_bid:.3f}/{yes_ask:.3f}, NO {no_bid:.3f}/{no_ask:.3f}")
        
        # 2. Проверяем изменение цен для уведомлений
        price_changes = self._check_price_changes(yes_bid, yes_ask, no_bid, no_ask)
        result['price_changes'] = price_changes
        
        # 3. Проверяем арбитражные возможности (ПРИОРИТЕТ!)
        arbitrage_result = self._check_and_execute_arbitrage(yes_bid, yes_ask, no_bid, no_ask)
        result['arbitrage'] = arbitrage_result
        
        # 4. Проверяем "прыжок" цены через ордера и переставляем
        repositioned = self._check_and_reposition_orders(yes_bid, yes_ask, no_bid, no_ask)
        result['repositioned_orders'] = repositioned
        
        # 5. Проверяем исполнение существующих ордеров
        executed = self._check_order_execution(yes_bid, yes_ask, no_bid, no_ask)
        result['executed_trades'] = executed
        
        # 6. Отменяем устаревшие ордера
        cancelled = self._cancel_stale_orders(yes_bid, yes_ask, no_bid, no_ask)
        result['cancelled_orders'] = cancelled
        
        # 7. Размещаем новые ордера по стратегии
        if self.strategy == 'dual_side':
            placed = self._strategy_dual_side(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'yes_only':
            placed = self._strategy_single_token('YES', yes_bid, yes_ask)
        elif self.strategy == 'no_only':
            placed = self._strategy_single_token('NO', no_bid, no_ask)
        elif self.strategy == 'arbitrage':
            # Арбитраж-only: только ищем арбитражные возможности
            placed = self._strategy_arbitrage_only(yes_bid, yes_ask, no_bid, no_ask)
        elif self.strategy == 'hybrid':
            # Гибрид: dual_side + арбитраж резерв
            placed = self._strategy_hybrid(yes_bid, yes_ask, no_bid, no_ask)
        else:
            placed = self._strategy_dual_side(yes_bid, yes_ask, no_bid, no_ask)
        
        result['placed_orders'] = placed
        
        # Сохраняем текущие цены для следующей проверки
        self.prev_yes_bid = yes_bid
        self.prev_yes_ask = yes_ask
        self.prev_no_bid = no_bid
        self.prev_no_ask = no_ask
        
        return result
    
    def _check_price_changes(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[Dict]:
        """
        Проверить значительные изменения цен для уведомлений.
        
        Использует БАЗОВУЮ цену, которая обновляется только при отправке уведомления.
        Это предотвращает спам при волатильном рынке.
        """
        changes = []
        
        # Текущие mid-цены
        yes_mid_curr = (yes_bid + yes_ask) / 2
        no_mid_curr = (no_bid + no_ask) / 2
        
        # Первый цикл - инициализируем базовые цены
        if self.base_yes_price is None:
            self.base_yes_price = yes_mid_curr
            self.base_no_price = no_mid_curr
            return changes
        
        # Проверяем YES относительно БАЗОВОЙ цены
        if self.base_yes_price > 0:
            yes_change = (yes_mid_curr - self.base_yes_price) / self.base_yes_price
            if abs(yes_change) >= PRICE_CHANGE_NOTIFICATION_THRESHOLD:
                changes.append({
                    'token': 'YES',
                    'prev_price': self.base_yes_price,
                    'curr_price': yes_mid_curr,
                    'change_percent': yes_change * 100,
                    'direction': '📈' if yes_change > 0 else '📉'
                })
                # Обновляем базовую цену ТОЛЬКО после уведомления
                self.base_yes_price = yes_mid_curr
        
        # Проверяем NO относительно БАЗОВОЙ цены
        if self.base_no_price > 0:
            no_change = (no_mid_curr - self.base_no_price) / self.base_no_price
            if abs(no_change) >= PRICE_CHANGE_NOTIFICATION_THRESHOLD:
                changes.append({
                    'token': 'NO',
                    'prev_price': self.base_no_price,
                    'curr_price': no_mid_curr,
                    'change_percent': no_change * 100,
                    'direction': '📈' if no_change > 0 else '📉'
                })
                # Обновляем базовую цену ТОЛЬКО после уведомления
                self.base_no_price = no_mid_curr
        
        return changes
    
    def _check_and_execute_arbitrage(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> Dict:
        """
        Проверить и выполнить арбитражные возможности С УЧЁТОМ КОМИССИЙ.
        
        Логика Opinion Trade:
        - YES + NO всегда = $1.00 в конце (один выиграет, другой проиграет)
        - Split: $1 USDT → 1 YES + 1 NO токен (on-chain, требует gas)
        - Merge: 1 YES + 1 NO → $1 USDT (on-chain, требует gas)
        
        Арбитражные возможности:
        1. BUY_BOTH: Купить YES + NO на рынке, если ASK+ASK < $1 (после Merge = прибыль)
        2. SELL_BOTH: Продать YES + NO если BID+BID > $1 (альтернатива Split)
        3. SPLIT_SELL: Split $1 → YES+NO, продать оба если BID+BID > $1
        
        ВАЖНО: Учитываем комиссии!
        - Maker (лимит ордер) = 0%
        - Taker (маркет ордер) = до 2% (зависит от цены)
        - Минимальная комиссия = $0.50
        
        Returns:
            Dict с информацией об арбитраже
        """
        result = {
            'opportunity': None,
            'executed': False,
            'profit': 0.0,
            'details': None,
            'fees_paid': 0.0
        }
        
        # === АРБИТРАЖ ПОКУПКИ: YES_ASK + NO_ASK < 1.00 ===
        # Покупаем оба токена на рынке. После резолюции получим $1 за пару.
        buy_cost = yes_ask + no_ask
        
        if buy_cost < 1.0:
            # Рассчитываем комиссии (taker fees - покупаем по маркету)
            # Примерная сумма для расчёта комиссий
            test_amount = self.order_amount
            yes_fee = calculate_taker_fee(yes_ask, test_amount / 2)
            no_fee = calculate_taker_fee(no_ask, test_amount / 2)
            total_fees = yes_fee + no_fee
            
            # Реальная прибыль с учётом комиссий
            gross_profit_per_pair = 1.0 - buy_cost
            # Комиссия на пару примерно
            fee_per_pair = (total_fees / (test_amount / buy_cost)) if test_amount > 0 else 0.01
            net_profit_per_pair = gross_profit_per_pair - fee_per_pair
            net_profit_percent = net_profit_per_pair / buy_cost if buy_cost > 0 else 0
            
            if net_profit_per_pair > 0 and net_profit_percent >= ARBITRAGE_MIN_PROFIT_PERCENT:
                result['opportunity'] = 'BUY_BOTH'
                
                logger.info(f"🎯 АРБИТРАЖ BUY_BOTH: YES@{yes_ask:.3f} + NO@{no_ask:.3f} = ${buy_cost:.3f}")
                logger.info(f"   Gross profit: ${gross_profit_per_pair:.3f}/pair")
                logger.info(f"   Fees: ~${fee_per_pair:.3f}/pair")
                logger.info(f"   Net profit: ${net_profit_per_pair:.3f}/pair ({net_profit_percent*100:.2f}%)")
                
                # Выполняем арбитраж
                if self.balance >= MIN_ORDER_USDT * 2:
                    max_pairs = (self.balance * 0.5) / buy_cost
                    pairs_to_buy = min(max_pairs, self.order_amount * 2 / buy_cost)
                    
                    if pairs_to_buy >= 1:
                        yes_cost = pairs_to_buy * yes_ask
                        no_cost = pairs_to_buy * no_ask
                        total_cost = yes_cost + no_cost
                        
                        # Реальные комиссии
                        actual_yes_fee = calculate_taker_fee(yes_ask, yes_cost)
                        actual_no_fee = calculate_taker_fee(no_ask, no_cost)
                        actual_total_fees = actual_yes_fee + actual_no_fee
                        
                        total_cost_with_fees = total_cost + actual_total_fees
                        
                        if total_cost_with_fees <= self.balance:
                            self.balance -= total_cost_with_fees
                            self.yes_tokens += pairs_to_buy
                            self.no_tokens += pairs_to_buy
                            
                            expected_profit = pairs_to_buy - total_cost_with_fees
                            self.arbitrage_trades += 1
                            self.arbitrage_profit += expected_profit
                            
                            result['executed'] = True
                            result['profit'] = expected_profit
                            result['fees_paid'] = actual_total_fees
                            result['details'] = {
                                'type': 'BUY_BOTH',
                                'pairs': pairs_to_buy,
                                'yes_price': yes_ask,
                                'no_price': no_ask,
                                'total_cost': total_cost,
                                'fees': actual_total_fees,
                                'total_cost_with_fees': total_cost_with_fees,
                                'expected_profit': expected_profit,
                                'profit_percent': net_profit_percent * 100
                            }
                            
                            logger.info(f"✅ АРБИТРАЖ BUY_BOTH: {pairs_to_buy:.2f} пар за ${total_cost_with_fees:.2f} (fees: ${actual_total_fees:.2f})")
                            logger.info(f"   Ожидаемая прибыль: ${expected_profit:.2f}")
        
        # === АРБИТРАЖ ПРОДАЖИ: YES_BID + NO_BID > 1.00 ===
        # Продаём оба токена. Альтернатива: Split $1 → YES+NO, затем продать оба.
        sell_revenue = yes_bid + no_bid
        
        if sell_revenue > 1.0:
            # Если у нас есть токены - продаём их
            min_tokens = min(self.yes_tokens, self.no_tokens)
            
            if min_tokens >= 0.1:
                # Рассчитываем комиссии при продаже (taker)
                test_amount = min_tokens * sell_revenue
                yes_fee = calculate_taker_fee(yes_bid, min_tokens * yes_bid)
                no_fee = calculate_taker_fee(no_bid, min_tokens * no_bid)
                total_fees = yes_fee + no_fee
                
                gross_profit_per_pair = sell_revenue - 1.0
                fee_per_pair = total_fees / min_tokens if min_tokens > 0 else 0.01
                net_profit_per_pair = gross_profit_per_pair - fee_per_pair
                net_profit_percent = net_profit_per_pair / 1.0
                
                if net_profit_per_pair > 0 and net_profit_percent >= ARBITRAGE_MIN_PROFIT_PERCENT:
                    if result['opportunity'] is None:
                        result['opportunity'] = 'SELL_BOTH'
                    else:
                        result['opportunity'] = 'BOTH'
                    
                    logger.info(f"🎯 АРБИТРАЖ SELL_BOTH: YES@{yes_bid:.3f} + NO@{no_bid:.3f} = ${sell_revenue:.3f}")
                    logger.info(f"   Gross profit: ${gross_profit_per_pair:.3f}/pair")
                    logger.info(f"   Fees: ~${fee_per_pair:.3f}/pair")
                    logger.info(f"   Net profit: ${net_profit_per_pair:.3f}/pair ({net_profit_percent*100:.2f}%)")
                    
                    # Продаём пары
                    pairs_to_sell = min(min_tokens, self.order_amount / sell_revenue)
                    
                    if pairs_to_sell >= 0.1:
                        yes_revenue_gross = pairs_to_sell * yes_bid
                        no_revenue_gross = pairs_to_sell * no_bid
                        
                        actual_yes_fee = calculate_taker_fee(yes_bid, yes_revenue_gross)
                        actual_no_fee = calculate_taker_fee(no_bid, no_revenue_gross)
                        actual_total_fees = actual_yes_fee + actual_no_fee
                        
                        total_revenue_net = yes_revenue_gross + no_revenue_gross - actual_total_fees
                        
                        self.yes_tokens -= pairs_to_sell
                        self.no_tokens -= pairs_to_sell
                        self.balance += total_revenue_net
                        
                        # Прибыль = выручка - стоимость пар ($1 каждая)
                        actual_profit = total_revenue_net - pairs_to_sell
                        self.arbitrage_trades += 1
                        self.arbitrage_profit += actual_profit
                        self.total_pnl += actual_profit
                        
                        result['executed'] = True
                        result['profit'] = actual_profit
                        result['fees_paid'] = actual_total_fees
                        result['details'] = {
                            'type': 'SELL_BOTH',
                            'pairs': pairs_to_sell,
                            'yes_price': yes_bid,
                            'no_price': no_bid,
                            'gross_revenue': yes_revenue_gross + no_revenue_gross,
                            'fees': actual_total_fees,
                            'net_revenue': total_revenue_net,
                            'profit': actual_profit,
                            'profit_percent': net_profit_percent * 100
                        }
                        
                        logger.info(f"✅ АРБИТРАЖ SELL_BOTH: {pairs_to_sell:.2f} пар, выручка ${total_revenue_net:.2f} (fees: ${actual_total_fees:.2f})")
                        logger.info(f"   Прибыль: ${actual_profit:.2f}")
            
            # Если нет токенов но есть USDT - можно сделать Split+Sell
            # (для виртуальной торговли просто симулируем)
            elif self.balance >= MIN_ORDER_USDT * 2 and result['opportunity'] is None:
                result['opportunity'] = 'SPLIT_SELL'
                result['details'] = {
                    'type': 'SPLIT_SELL',
                    'description': 'Split $1 → YES+NO, then sell both for profit',
                    'yes_bid': yes_bid,
                    'no_bid': no_bid,
                    'potential_gross_profit': sell_revenue - 1.0,
                    'note': 'Requires on-chain transaction (gas fees)'
                }
                logger.info(f"💡 ВОЗМОЖНОСТЬ SPLIT_SELL: Split + продать = ${sell_revenue:.3f} (profit ${sell_revenue-1:.3f})")
        
        return result
    
    def _strategy_arbitrage_only(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[VirtualOrder]:
        """
        Стратегия чистого арбитража - только ищем арбитражные возможности.
        Не размещаем обычные ордера, только моментальные арбитражные сделки.
        """
        # Арбитраж уже обработан в _check_and_execute_arbitrage
        # Здесь просто держим баланс готовым к арбитражу
        
        # Если есть избыточные токены (не в парах) - продаем по рынку
        placed = []
        
        # Продаем "лишние" токены которые не образуют пару
        excess_yes = self.yes_tokens - self.no_tokens
        excess_no = self.no_tokens - self.yes_tokens
        
        if excess_yes > 0.1 and not self._has_open_order('YES', 'ASK'):
            # Продаем лишние YES
            ask_price = round(yes_bid, 3)  # По текущей рыночной цене
            order = self._place_order('YES', 'ASK', ask_price, excess_yes * ask_price)
            if order:
                placed.append(order)
                logger.debug(f"📤 Продаем лишние YES: {excess_yes:.2f} @ {ask_price:.3f}")
        
        if excess_no > 0.1 and not self._has_open_order('NO', 'ASK'):
            # Продаем лишние NO
            ask_price = round(no_bid, 3)
            order = self._place_order('NO', 'ASK', ask_price, excess_no * ask_price)
            if order:
                placed.append(order)
                logger.debug(f"📤 Продаем лишние NO: {excess_no:.2f} @ {ask_price:.3f}")
        
        return placed

    def _strategy_hybrid(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[VirtualOrder]:
        """
        Гибридная стратегия: Dual-Side маркет-мейкинг + резерв для арбитража.
        
        Распределение баланса:
        - 70% на dual_side (постоянные BID/ASK ордера)
        - 30% резерв для арбитража (используется только при возможности)
        
        Преимущества:
        - Постоянный заработок на спреде (dual_side)
        - Готовность к арбитражным возможностям (резерв)
        - Создание ликвидности на рынке
        """
        placed = []
        
        # Рассчитываем доступный баланс для каждой части стратегии
        total_available = self.balance
        
        # Считаем сколько уже заблокировано в ордерах
        locked_in_orders = sum(
            order.amount for order in self.orders.values() 
            if order.status == 'open' and order.side == 'BID'
        )
        
        # Общий "виртуальный" баланс для расчёта распределения
        effective_balance = total_available + locked_in_orders
        
        # Целевые суммы для каждой стратегии
        target_dual_side = effective_balance * self.hybrid_dual_side_percent
        target_arbitrage = effective_balance * self.hybrid_arbitrage_percent
        
        # Обновляем резерв для арбитража (для отображения в статусе)
        self.arbitrage_reserve = max(0, total_available - target_dual_side + locked_in_orders)
        
        # Сколько доступно для dual_side (за вычетом арбитражного резерва)
        available_for_dual_side = max(0, total_available - target_arbitrage)
        
        logger.debug(f"📊 Hybrid: total=${effective_balance:.2f}, "
                    f"dual_side=${target_dual_side:.2f} ({self.hybrid_dual_side_percent*100:.0f}%), "
                    f"arb_reserve=${target_arbitrage:.2f} ({self.hybrid_arbitrage_percent*100:.0f}%)")
        
        has_usdt = available_for_dual_side >= MIN_ORDER_USDT
        
        # === ЧАСТЬ 1: Dual-Side маркет-мейкинг ===
        
        if available_for_dual_side < USDT_THRESHOLD:
            # РЕЖИМ A: Экономный (мало средств для dual_side)
            
            # ASK: продаем токены если есть
            if self.yes_tokens > 0.01 and not self._has_open_order('YES', 'ASK'):
                yes_ask_price = round(yes_ask, 3)
                order = self._place_order('YES', 'ASK', yes_ask_price, self.yes_tokens * yes_ask_price)
                if order:
                    placed.append(order)
            
            if self.no_tokens > 0.01 and not self._has_open_order('NO', 'ASK'):
                no_ask_price = round(no_ask, 3)
                order = self._place_order('NO', 'ASK', no_ask_price, self.no_tokens * no_ask_price)
                if order:
                    placed.append(order)
            
            # BID: покупаем токен которого меньше (используя только dual_side часть)
            if has_usdt:
                order_size = min(self.order_amount, available_for_dual_side)
                
                if self.yes_tokens <= self.no_tokens:
                    if not self._has_open_order('YES', 'BID'):
                        bid_price = round(yes_bid + TICK_SIZE, 3)
                        order = self._place_order('YES', 'BID', bid_price, order_size)
                        if order:
                            placed.append(order)
                else:
                    if not self._has_open_order('NO', 'BID'):
                        bid_price = round(no_bid + TICK_SIZE, 3)
                        order = self._place_order('NO', 'BID', bid_price, order_size)
                        if order:
                            placed.append(order)
        
        else:
            # РЕЖИМ B: Полноценный dual-side
            
            # BID: покупаем оба токена (используя только dual_side часть)
            if has_usdt:
                order_size = min(self.order_amount, available_for_dual_side / 2)
                
                if not self._has_open_order('YES', 'BID') and order_size >= MIN_ORDER_USDT:
                    yes_bid_price = round(yes_bid + TICK_SIZE, 3)
                    order = self._place_order('YES', 'BID', yes_bid_price, order_size)
                    if order:
                        placed.append(order)
                        available_for_dual_side -= order_size  # Уменьшаем доступный баланс
                
                if not self._has_open_order('NO', 'BID') and available_for_dual_side >= MIN_ORDER_USDT:
                    no_bid_price = round(no_bid + TICK_SIZE, 3)
                    remaining = min(self.order_amount, available_for_dual_side)
                    order = self._place_order('NO', 'BID', no_bid_price, remaining)
                    if order:
                        placed.append(order)
            
            # ASK: продаем токены если есть
            if self.yes_tokens > 0.01 and not self._has_open_order('YES', 'ASK'):
                yes_ask_price = round(yes_ask, 3)
                order = self._place_order('YES', 'ASK', yes_ask_price, self.yes_tokens * yes_ask_price)
                if order:
                    placed.append(order)
            
            if self.no_tokens > 0.01 and not self._has_open_order('NO', 'ASK'):
                no_ask_price = round(no_ask, 3)
                order = self._place_order('NO', 'ASK', no_ask_price, self.no_tokens * no_ask_price)
                if order:
                    placed.append(order)
        
        # === ЧАСТЬ 2: Арбитраж ===
        # Арбитраж уже обрабатывается в _check_and_execute_arbitrage
        # который вызывается до выбора стратегии.
        # Резерв автоматически доступен в self.balance для арбитражных сделок.
        
        # Логируем статус арбитражного резерва
        actual_reserve = max(0, self.balance - sum(
            o.amount for o in self.orders.values() 
            if o.status == 'open' and o.side == 'BID'
        ))
        
        if actual_reserve >= MIN_ORDER_USDT * 2:
            logger.debug(f"💰 Арбитраж резерв: ${actual_reserve:.2f} готов к использованию")
        
        return placed

    def _check_and_reposition_orders(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[Dict]:
        """
        Проверить, прыгнула ли цена через наши ордера.
        Если да - отменить старый и создать новый ордер по текущей цене.
        """
        repositioned = []
        
        for order_id, order in list(self.orders.items()):
            if order.status != 'open':
                continue
            
            current_bid = yes_bid if order.token == 'YES' else no_bid
            current_ask = yes_ask if order.token == 'YES' else no_ask
            
            needs_reposition = False
            reason_direction = None  # 'up' or 'down'
            reason_prev = 0.0
            reason_curr = 0.0
            
            if order.side == 'BID':
                # BID: если текущий ASK значительно выше нашего BID (цена ушла вверх)
                # и раньше была ниже - значит "прыгнула" через наш ордер
                if self.prev_yes_ask is not None:
                    prev_ask = self.prev_yes_ask if order.token == 'YES' else self.prev_no_ask
                    # Цена была доступна (prev_ask <= order.price), но теперь ушла
                    if prev_ask <= order.price < current_ask:
                        needs_reposition = True
                        reason_direction = 'up'
                        reason_prev = prev_ask
                        reason_curr = current_ask
                        
            else:  # ASK
                # ASK: если текущий BID значительно ниже нашего ASK (цена ушла вниз)
                if self.prev_yes_bid is not None:
                    prev_bid = self.prev_yes_bid if order.token == 'YES' else self.prev_no_bid
                    # Цена была доступна (prev_bid >= order.price), но теперь ушла
                    if prev_bid >= order.price > current_bid:
                        needs_reposition = True
                        reason_direction = 'down'
                        reason_prev = prev_bid
                        reason_curr = current_bid
            
            if needs_reposition:
                # Отменяем старый ордер
                order.status = 'cancelled'
                
                # Возвращаем средства
                if order.side == 'BID':
                    self.balance += order.amount
                else:
                    if order.token == 'YES':
                        self.yes_tokens += order.tokens
                    else:
                        self.no_tokens += order.tokens
                
                old_price = order.price
                del self.orders[order_id]
                
                # Создаем новый ордер по текущей цене
                if order.side == 'BID':
                    new_price = current_ask * (1 - self.spread_percent / 2)
                else:
                    new_price = current_bid * (1 + self.spread_percent / 2)
                
                new_price = round(new_price, 3)
                
                new_order = self._place_order(order.token, order.side, new_price, order.amount)
                
                if new_order:
                    repositioned.append({
                        'token': order.token,
                        'side': order.side,
                        'old_price': old_price,
                        'new_price': new_price,
                        'reason_direction': reason_direction,
                        'reason_prev': reason_prev,
                        'reason_curr': reason_curr,
                        'new_order': new_order
                    })
                    
                    logger.info(f"🔄 Repositioned {order.token} {order.side}: {old_price:.3f} → {new_price:.3f}")
        
        return repositioned
    
    def _check_order_execution(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[Trade]:
        """Проверить исполнение ордеров по текущим ценам"""
        executed = []
        
        for order_id, order in list(self.orders.items()):
            if order.status != 'open':
                continue
            
            is_filled = False
            execution_price = 0.0
            
            if order.token == 'YES':
                if order.side == 'BID' and yes_ask <= order.price:
                    # BID исполняется когда ASK <= нашей цены
                    is_filled = True
                    execution_price = yes_ask
                elif order.side == 'ASK' and yes_bid >= order.price:
                    # ASK исполняется когда BID >= нашей цены
                    is_filled = True
                    execution_price = yes_bid
            else:  # NO
                if order.side == 'BID' and no_ask <= order.price:
                    is_filled = True
                    execution_price = no_ask
                elif order.side == 'ASK' and no_bid >= order.price:
                    is_filled = True
                    execution_price = no_bid
            
            if is_filled:
                trade = self._execute_order(order, execution_price)
                if trade:
                    executed.append(trade)
                    del self.orders[order_id]
        
        return executed
    
    def _execute_order(self, order: VirtualOrder, execution_price: float) -> Optional[Trade]:
        """Исполнить ордер"""
        order.status = 'filled'
        pnl = 0.0
        
        if order.side == 'BID':
            # Покупка: получаем токены
            tokens_bought = order.amount / execution_price
            
            if order.token == 'YES':
                # Обновляем среднюю цену покупки
                total_tokens = self.yes_tokens + tokens_bought
                if total_tokens > 0:
                    self.avg_yes_buy_price = (
                        (self.avg_yes_buy_price * self.yes_tokens + execution_price * tokens_bought) 
                        / total_tokens
                    )
                self.yes_tokens += tokens_bought
            else:
                total_tokens = self.no_tokens + tokens_bought
                if total_tokens > 0:
                    self.avg_no_buy_price = (
                        (self.avg_no_buy_price * self.no_tokens + execution_price * tokens_bought) 
                        / total_tokens
                    )
                self.no_tokens += tokens_bought
            
            trade_side = 'BUY'
            tokens = tokens_bought
            
        else:  # ASK
            # Продажа: получаем USDT
            revenue = order.tokens * execution_price
            self.balance += revenue
            
            # Рассчитываем PnL
            avg_buy = self.avg_yes_buy_price if order.token == 'YES' else self.avg_no_buy_price
            if avg_buy > 0:
                pnl = (execution_price - avg_buy) * order.tokens
                self.total_pnl += pnl
                self.daily_pnl += pnl
            
            trade_side = 'SELL'
            tokens = order.tokens
        
        trade = Trade(
            trade_id=f"T{order.order_id}",
            token=order.token,
            side=trade_side,
            price=execution_price,
            amount=order.amount,
            tokens=tokens,
            pnl=pnl
        )
        
        self.trades.append(trade)
        
        logger.info(f"✅ Сделка: {trade_side} {order.token} @ {execution_price:.3f}, PnL: ${pnl:.2f}")
        
        return trade
    
    def _cancel_stale_orders(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[VirtualOrder]:
        """Отменить устаревшие ордера (цена ушла > 2%)"""
        cancelled = []
        
        for order_id, order in list(self.orders.items()):
            if order.status != 'open':
                continue
            
            current_price = 0.0
            if order.token == 'YES':
                current_price = yes_bid if order.side == 'BID' else yes_ask
            else:
                current_price = no_bid if order.side == 'BID' else no_ask
            
            if current_price > 0:
                deviation = abs(order.price - current_price) / current_price
                
                if deviation > STALE_ORDER_THRESHOLD:
                    order.status = 'cancelled'
                    
                    # Возвращаем средства
                    if order.side == 'BID':
                        self.balance += order.amount
                    else:
                        if order.token == 'YES':
                            self.yes_tokens += order.tokens
                        else:
                            self.no_tokens += order.tokens
                    
                    cancelled.append(order)
                    del self.orders[order_id]
                    
                    logger.debug(f"🚫 Отменен устаревший ордер: {order.token} {order.side} @ {order.price:.3f}")
        
        return cancelled
    
    def _has_open_order(self, token: str, side: str) -> bool:
        """Проверить есть ли открытый ордер"""
        for order in self.orders.values():
            if order.status == 'open' and order.token == token and order.side == side:
                return True
        return False
    
    def _place_order(self, token: str, side: str, price: float, amount: float) -> Optional[VirtualOrder]:
        """Разместить виртуальный ордер"""
        
        if side == 'BID':
            # Проверка баланса
            if amount > self.balance:
                return None
            
            tokens = amount / price
            self.balance -= amount
            
        else:  # ASK
            # Проверка токенов
            tokens = amount / price
            if token == 'YES':
                if tokens > self.yes_tokens:
                    tokens = self.yes_tokens
                if tokens < 0.01:
                    return None
                self.yes_tokens -= tokens
            else:
                if tokens > self.no_tokens:
                    tokens = self.no_tokens
                if tokens < 0.01:
                    return None
                self.no_tokens -= tokens
            
            amount = tokens * price
        
        order = VirtualOrder(
            order_id=self._generate_order_id(),
            token=token,
            side=side,
            price=price,
            amount=amount,
            tokens=tokens
        )
        
        self.orders[order.order_id] = order
        logger.debug(f"📝 Ордер: {side} {token} @ {price:.3f}, ${amount:.2f}")
        
        return order
    
    def _strategy_dual_side(
        self,
        yes_bid: float,
        yes_ask: float,
        no_bid: float,
        no_ask: float
    ) -> List[VirtualOrder]:
        """Стратегия dual-side (как в bot_v2.py)"""
        placed = []
        
        has_usdt = self.balance >= MIN_ORDER_USDT
        
        if self.balance < USDT_THRESHOLD:
            # РЕЖИМ A: Экономный (< $6)
            # Покупаем 1 токен, продаем оба
            
            # ASK: продаем токены если есть
            if self.yes_tokens > 0.01 and not self._has_open_order('YES', 'ASK'):
                yes_ask_price = round(yes_ask, 3)
                order = self._place_order('YES', 'ASK', yes_ask_price, self.yes_tokens * yes_ask_price)
                if order:
                    placed.append(order)
            
            if self.no_tokens > 0.01 and not self._has_open_order('NO', 'ASK'):
                no_ask_price = round(no_ask, 3)
                order = self._place_order('NO', 'ASK', no_ask_price, self.no_tokens * no_ask_price)
                if order:
                    placed.append(order)
            
            # BID: покупаем токен которого меньше
            if has_usdt:
                if self.yes_tokens <= self.no_tokens:
                    if not self._has_open_order('YES', 'BID'):
                        bid_price = round(yes_bid + TICK_SIZE, 3)
                        order = self._place_order('YES', 'BID', bid_price, min(self.order_amount, self.balance))
                        if order:
                            placed.append(order)
                else:
                    if not self._has_open_order('NO', 'BID'):
                        bid_price = round(no_bid + TICK_SIZE, 3)
                        order = self._place_order('NO', 'BID', bid_price, min(self.order_amount, self.balance))
                        if order:
                            placed.append(order)
        
        else:
            # РЕЖИМ B: Полноценный dual-side (>= $6)
            
            # BID: покупаем оба токена
            if has_usdt:
                order_size = min(self.order_amount, self.balance / 2)
                
                if not self._has_open_order('YES', 'BID') and order_size >= MIN_ORDER_USDT:
                    yes_bid_price = round(yes_bid + TICK_SIZE, 3)
                    order = self._place_order('YES', 'BID', yes_bid_price, order_size)
                    if order:
                        placed.append(order)
                
                if not self._has_open_order('NO', 'BID') and self.balance >= MIN_ORDER_USDT:
                    no_bid_price = round(no_bid + TICK_SIZE, 3)
                    order = self._place_order('NO', 'BID', no_bid_price, min(self.order_amount, self.balance))
                    if order:
                        placed.append(order)
            
            # ASK: продаем токены если есть
            if self.yes_tokens > 0.01 and not self._has_open_order('YES', 'ASK'):
                yes_ask_price = round(yes_ask, 3)
                order = self._place_order('YES', 'ASK', yes_ask_price, self.yes_tokens * yes_ask_price)
                if order:
                    placed.append(order)
            
            if self.no_tokens > 0.01 and not self._has_open_order('NO', 'ASK'):
                no_ask_price = round(no_ask, 3)
                order = self._place_order('NO', 'ASK', no_ask_price, self.no_tokens * no_ask_price)
                if order:
                    placed.append(order)
        
        return placed
    
    def _strategy_single_token(
        self,
        token: str,
        bid: float,
        ask: float
    ) -> List[VirtualOrder]:
        """Стратегия торговли одним токеном"""
        placed = []
        
        has_usdt = self.balance >= MIN_ORDER_USDT
        token_balance = self.yes_tokens if token == 'YES' else self.no_tokens
        
        # BID
        if has_usdt and not self._has_open_order(token, 'BID'):
            bid_price = round(bid + TICK_SIZE, 3)
            order = self._place_order(token, 'BID', bid_price, min(self.order_amount, self.balance))
            if order:
                placed.append(order)
        
        # ASK
        if token_balance > 0.01 and not self._has_open_order(token, 'ASK'):
            ask_price = round(ask, 3)
            order = self._place_order(token, 'ASK', ask_price, token_balance * ask_price)
            if order:
                placed.append(order)
        
        return placed
    
    def get_portfolio_value(self) -> Tuple[float, float, float]:
        """
        Рассчитать общую стоимость портфеля по текущим рыночным ценам
        
        Returns:
            (total_value, yes_value, no_value) - общая стоимость, стоимость YES, стоимость NO
        """
        yes_bid, yes_ask, no_bid, no_ask = self.get_prices()
        
        # Стоимость токенов по BID ценам (по какой мы можем продать)
        yes_value = 0.0
        no_value = 0.0
        
        if yes_bid and self.yes_tokens > 0:
            yes_value = self.yes_tokens * yes_bid
        
        if no_bid and self.no_tokens > 0:
            no_value = self.no_tokens * no_bid
        
        # Стоимость средств заблокированных в ордерах
        orders_value = 0.0
        for order in self.orders.values():
            if order.status == 'open':
                if order.side == 'BID':
                    # BID ордер - деньги заблокированы
                    orders_value += order.amount
                else:
                    # ASK ордер - токены заблокированы, считаем по текущей цене
                    if order.token == 'YES' and yes_bid:
                        orders_value += order.tokens * yes_bid
                    elif order.token == 'NO' and no_bid:
                        orders_value += order.tokens * no_bid
        
        total_value = self.balance + yes_value + no_value + orders_value
        
        return total_value, yes_value, no_value
    
    def get_unrealized_pnl(self) -> float:
        """
        Рассчитать нереализованный PnL (изменение стоимости портфеля)
        """
        total_value, _, _ = self.get_portfolio_value()
        return total_value - self.initial_balance
    
    def get_total_pnl(self) -> float:
        """
        Получить общий PnL (реализованный + нереализованный)
        """
        return self.get_unrealized_pnl()
    
    def get_status(self) -> Dict:
        """Получить текущий статус"""
        open_orders = [o for o in self.orders.values() if o.status == 'open']
        
        # Рассчитываем текущую стоимость портфеля
        portfolio_value, yes_value, no_value = self.get_portfolio_value()
        unrealized_pnl = portfolio_value - self.initial_balance
        
        return {
            'is_running': self.is_running,
            'balance': self.balance,
            'initial_balance': self.initial_balance,
            'portfolio_value': portfolio_value,
            'yes_tokens': self.yes_tokens,
            'no_tokens': self.no_tokens,
            'yes_value': yes_value,
            'no_value': no_value,
            'realized_pnl': self.total_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_pnl': unrealized_pnl,  # Общий PnL = изменение портфеля
            'daily_pnl': self.daily_pnl,
            'open_orders': len(open_orders),
            'trades_count': len(self.trades),
            'cycles_count': self.cycles_count,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'strategy': self.strategy,
            'spread_percent': self.spread_percent,
            'market_id': self.market_id,
            'arbitrage_trades': self.arbitrage_trades,
            'arbitrage_profit': self.arbitrage_profit,
            'arbitrage_reserve': self.arbitrage_reserve if self.strategy == 'hybrid' else 0.0,
            'hybrid_dual_side_percent': self.hybrid_dual_side_percent if self.strategy == 'hybrid' else 0.0,
            'hybrid_arbitrage_percent': self.hybrid_arbitrage_percent if self.strategy == 'hybrid' else 0.0
        }
    
    def get_status_message(self) -> str:
        """Получить статус в виде сообщения для Telegram"""
        status = self.get_status()
        
        pnl = status['total_pnl']
        pnl_pct = (pnl / status['initial_balance'] * 100) if status['initial_balance'] > 0 else 0
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        running_emoji = "🟢" if status['is_running'] else "🔴"
        
        open_orders_str = ""
        for order in self.orders.values():
            if order.status == 'open':
                side_emoji = "🟢" if order.side == 'BID' else "🔴"
                open_orders_str += f"\n   {side_emoji} {order.token} {order.side}: ${order.amount:.2f} @ {order.price:.3f}"
        
        if not open_orders_str:
            open_orders_str = "\n   No active orders"
        
        # Стоимость позиций
        yes_value_str = f"(${status['yes_value']:.2f})" if status['yes_value'] > 0 else ""
        no_value_str = f"(${status['no_value']:.2f})" if status['no_value'] > 0 else ""
        
        # Проверяем текущие арбитражные возможности
        arb_opportunity = ""
        try:
            yes_bid, yes_ask, no_bid, no_ask = self.get_prices()
            if yes_bid and yes_ask and no_bid and no_ask:
                buy_cost = yes_ask + no_ask
                sell_revenue = yes_bid + no_bid
                
                if buy_cost < 0.99:
                    arb_opportunity = f"\n💡 **Arb opportunity:** BUY BOTH @ ${buy_cost:.3f} (profit ${1-buy_cost:.3f})"
                elif sell_revenue > 1.01:
                    arb_opportunity = f"\n💡 **Arb opportunity:** SELL BOTH @ ${sell_revenue:.3f} (profit ${sell_revenue-1:.3f})"
        except:
            pass
        
        # Арбитраж статистика
        arb_str = ""
        if status['arbitrage_trades'] > 0:
            arb_str = f"\n🎯 **Arbitrage:** {status['arbitrage_trades']} trades, ${status['arbitrage_profit']:.2f} profit"
        
        # Информация о комиссиях
        fee_info = "\n💸 **Fees:** Maker 0% | Taker ~0.5-2%"
        
        # Информация о гибридной стратегии
        hybrid_info = ""
        if status['strategy'] == 'hybrid':
            dual_pct = int(status['hybrid_dual_side_percent'] * 100)
            arb_pct = int(status['hybrid_arbitrage_percent'] * 100)
            arb_reserve = status.get('arbitrage_reserve', 0)
            hybrid_info = f"\n🔀 **Hybrid:** {dual_pct}% dual-side | {arb_pct}% arb reserve (${arb_reserve:.2f})"
        
        # Форматирование названия стратегии
        strategy_names = {
            'dual_side': 'Dual-Side',
            'yes_only': 'YES Only',
            'no_only': 'NO Only',
            'arbitrage': 'Arbitrage',
            'hybrid': 'Hybrid (Dual+Arb)'
        }
        strategy_name = strategy_names.get(status['strategy'], status['strategy'])
        
        return f"""
{running_emoji} **Auto-trading {'active' if status['is_running'] else 'stopped'}**

💰 **USDT:** ${status['balance']:.2f}
💼 **Portfolio:** ${status['portfolio_value']:.2f}
📊 Initial: ${status['initial_balance']:.2f}

🎯 **Positions:**
   ✅ YES: {status['yes_tokens']:.4f} tokens {yes_value_str}
   ❌ NO: {status['no_tokens']:.4f} tokens {no_value_str}

{pnl_emoji} **PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%)**{arb_str}{arb_opportunity}{hybrid_info}

📝 **Orders:** {open_orders_str}

⚙️ Strategy: {strategy_name} | Spread: {status['spread_percent']*100:.1f}%
📈 Trades: {status['trades_count']} | Cycles: {status['cycles_count']}{fee_info}
        """.strip()
