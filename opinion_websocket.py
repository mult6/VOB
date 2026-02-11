"""
Opinion Trade WebSocket Client
Real-time market data streaming for Opinion prediction markets

Документация: https://docs.opinion.trade/developer-guide/opinion-websocket

ВАЖНО: WebSocket возвращает только DIFF (изменения), а не полный стакан!
Нужно сначала загрузить начальный стакан через REST API.
"""

import json
import logging
import threading
import time
import requests
from typing import Callable, Dict, Optional, List
from collections import defaultdict

try:
    import websocket
except ImportError:
    print("Установите websocket-client: pip install websocket-client")
    raise

from config import APIKEY

logger = logging.getLogger(__name__)


class OpinionWebSocket:
    """
    WebSocket клиент для получения real-time данных с Opinion Trade
    
    Поддерживаемые каналы:
    - market.depth.diff - изменения в стакане (orderbook)
    - market.last.price - последняя цена сделки
    - market.last.trade - информация о последней сделке
    - trade.order.update - обновления ваших ордеров
    - trade.record.new - подтверждённые сделки on-chain
    
    ВАЖНО: WebSocket даёт только изменения (diff)!
    При подписке на orderbook нужно сначала загрузить snapshot через REST API.
    """
    
    WS_URL = "wss://ws.opinion.trade"
    REST_URL = "https://openapi.opinion.trade/openapi"
    HEARTBEAT_INTERVAL = 25  # секунд (документация рекомендует 30)
    RECONNECT_DELAY = 5  # секунд между попытками переподключения
    MAX_RECONNECT_ATTEMPTS = 10
    
    def __init__(self, api_key: str = None):
        """
        Инициализация WebSocket клиента
        
        Args:
            api_key: API ключ (по умолчанию из config.py)
        """
        self.api_key = api_key or APIKEY
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        
        self._connected = False
        self._running = False
        self._reconnect_count = 0
        
        # Подписки
        self._subscriptions: List[Dict] = []
        self._subscribed_markets: set = set()  # ID рынков с подпиской
        
        # Token IDs для рынков
        self._market_tokens: Dict[int, Dict] = {}  # market_id -> {'yes': token_id, 'no': token_id}
        
        # Кэш данных
        self._orderbook: Dict[str, Dict] = defaultdict(lambda: {'bids': {}, 'asks': {}})
        self._last_prices: Dict[str, float] = {}
        self._last_trades: Dict[str, Dict] = {}
        
        # Callbacks
        self._on_orderbook_update: Optional[Callable] = None
        self._on_price_update: Optional[Callable] = None
        self._on_trade_update: Optional[Callable] = None
        self._on_order_update: Optional[Callable] = None
        
        # Lock для thread-safe доступа к данным
        self._lock = threading.RLock()
        
        # HTTP сессия для REST API
        self._session = requests.Session()
        self._session.headers.update({
            'apikey': self.api_key,
            'Content-Type': 'application/json'
        })
    
    @property
    def connected(self) -> bool:
        """Проверить подключение"""
        return self._connected and self.ws is not None
    
    def connect(self) -> bool:
        """
        Установить WebSocket соединение
        
        Returns:
            True если успешно подключились
        """
        if self._running:
            logger.warning("WebSocket уже запущен")
            return True
        
        self._running = True
        self._reconnect_count = 0
        
        # Запускаем в отдельном потоке
        self.ws_thread = threading.Thread(target=self._run_forever, daemon=True)
        self.ws_thread.start()
        
        # Ждём подключения (максимум 10 секунд)
        for _ in range(100):
            if self._connected:
                logger.info("✅ WebSocket подключен")
                return True
            time.sleep(0.1)
        
        logger.error("❌ Не удалось подключиться к WebSocket")
        return False
    
    def disconnect(self):
        """Закрыть соединение"""
        self._running = False
        self._connected = False
        
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        
        logger.info("🔌 WebSocket отключен")
    
    def _run_forever(self):
        """Основной цикл WebSocket с автопереподключением"""
        while self._running:
            try:
                url = f"{self.WS_URL}?apikey={self.api_key}"
                
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                logger.info(f"🔄 Подключение к WebSocket... (попытка {self._reconnect_count + 1})")
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
                
            except Exception as e:
                logger.error(f"❌ WebSocket ошибка: {e}")
            
            # Переподключение
            if self._running:
                self._reconnect_count += 1
                if self._reconnect_count > self.MAX_RECONNECT_ATTEMPTS:
                    logger.error(f"❌ Превышено максимальное количество попыток переподключения")
                    self._running = False
                    break
                
                logger.info(f"⏳ Переподключение через {self.RECONNECT_DELAY} сек...")
                time.sleep(self.RECONNECT_DELAY)
    
    def _on_open(self, ws):
        """Callback при открытии соединения"""
        self._connected = True
        self._reconnect_count = 0
        logger.info("✅ WebSocket соединение установлено")
        
        # Запускаем heartbeat
        self._start_heartbeat()
        
        # Восстанавливаем подписки
        for sub in self._subscriptions:
            self._send(sub)
    
    def _on_message(self, ws, message):
        """Callback при получении сообщения"""
        try:
            data = json.loads(message)
            msg_type = data.get('msgType', '')
            
            if msg_type == 'market.depth.diff':
                self._handle_orderbook_update(data)
            elif msg_type == 'market.last.price':
                self._handle_price_update(data)
            elif msg_type == 'market.last.trade':
                self._handle_trade_update(data)
            elif msg_type == 'trade.order.update':
                self._handle_order_update(data)
            elif msg_type == 'trade.record.new':
                self._handle_trade_executed(data)
            elif 'error' in data:
                logger.error(f"❌ WebSocket ошибка: {data}")
            else:
                logger.debug(f"📨 Неизвестное сообщение: {data}")
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
    
    def _on_error(self, ws, error):
        """Callback при ошибке"""
        logger.error(f"❌ WebSocket ошибка: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Callback при закрытии соединения"""
        self._connected = False
        logger.warning(f"🔌 WebSocket закрыт: {close_status_code} - {close_msg}")
    
    def _send(self, data: Dict) -> bool:
        """Отправить сообщение"""
        if not self._connected or not self.ws:
            logger.warning("⚠️ WebSocket не подключен")
            return False
        
        try:
            self.ws.send(json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
    
    def _start_heartbeat(self):
        """Запустить heartbeat поток"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        
        def heartbeat_loop():
            while self._running and self._connected:
                time.sleep(self.HEARTBEAT_INTERVAL)
                if self._connected:
                    self._send({"action": "HEARTBEAT"})
        
        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
    
    # =========================================================================
    # REST API для начального snapshot
    # =========================================================================
    
    def _load_market_info(self, market_id: int) -> bool:
        """Загрузить информацию о рынке (token IDs)"""
        try:
            resp = self._session.get(
                f"{self.REST_URL}/market/{market_id}",
                timeout=10
            )
            if resp.status_code != 200:
                logger.error(f"❌ HTTP {resp.status_code} при загрузке market info")
                return False
            
            data = resp.json()
            code = data.get('code', data.get('errno', -1))
            if code != 0:
                logger.error(f"❌ API ошибка {code}: {data.get('msg', 'unknown')}")
                return False
            
            result = data.get('result', {}).get('data', {})
            if not result:
                # Пробуем другую структуру ответа
                result = data.get('result', {})
            
            yes_token = str(result.get('yesTokenId', ''))
            no_token = str(result.get('noTokenId', ''))
            
            if yes_token and no_token:
                self._market_tokens[market_id] = {
                    'yes': yes_token,
                    'no': no_token
                }
                logger.info(f"📋 Market #{market_id}: YES={yes_token[:30]}... NO={no_token[:30]}...")
                return True
            
            logger.error(f"❌ Не найдены token IDs в ответе: {list(result.keys())}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки информации о рынке: {e}")
            return False
    
    def _load_orderbook_snapshot(self, token_id: str) -> bool:
        """
        Загрузить начальный snapshot стакана через REST API
        
        ВАЖНО: WebSocket даёт только diff, нужен начальный snapshot!
        """
        try:
            resp = self._session.get(
                f"{self.REST_URL}/token/orderbook",
                params={'token_id': token_id},
                timeout=10
            )
            
            if resp.status_code != 200:
                logger.error(f"❌ HTTP {resp.status_code} при загрузке orderbook")
                return False
            
            data = resp.json()
            if data.get('errno', data.get('code', -1)) != 0:
                logger.error(f"❌ API ошибка: {data.get('msg')}")
                return False
            
            result = data.get('result', {})
            bids = result.get('bids', [])
            asks = result.get('asks', [])
            
            with self._lock:
                # Очищаем старые данные
                self._orderbook[token_id] = {'bids': {}, 'asks': {}}
                
                # Загружаем bids
                for bid in bids:
                    price = bid.get('price', '0')
                    size = bid.get('size', '0')
                    self._orderbook[token_id]['bids'][price] = size
                
                # Загружаем asks
                for ask in asks:
                    price = ask.get('price', '0')
                    size = ask.get('size', '0')
                    self._orderbook[token_id]['asks'][price] = size
            
            logger.info(f"📖 Snapshot загружен: {len(bids)} bids, {len(asks)} asks")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки orderbook snapshot: {e}")
            return False
    
    # =========================================================================
    # ПОДПИСКИ
    # =========================================================================
    
    def subscribe_orderbook(self, market_id: int, callback: Callable = None, 
                            yes_token_id: str = None, no_token_id: str = None):
        """
        Подписаться на изменения стакана (orderbook)
        
        ВАЖНО: Сначала загружаем snapshot через REST API, 
        потом подписываемся на diff через WebSocket
        
        Args:
            market_id: ID рынка
            callback: Функция вызываемая при обновлении (token_id, side, price, size)
            yes_token_id: Token ID для YES (опционально, загрузится автоматически)
            no_token_id: Token ID для NO (опционально, загрузится автоматически)
        """
        # Загружаем token IDs если не переданы
        if not yes_token_id or not no_token_id:
            if market_id not in self._market_tokens:
                logger.info(f"📋 Загрузка информации о рынке #{market_id}...")
                if not self._load_market_info(market_id):
                    logger.error(f"❌ Не удалось загрузить token IDs для рынка #{market_id}")
                    return
            
            tokens = self._market_tokens.get(market_id, {})
            yes_token_id = tokens.get('yes')
            no_token_id = tokens.get('no')
        else:
            # Сохраняем переданные token IDs
            self._market_tokens[market_id] = {
                'yes': yes_token_id,
                'no': no_token_id
            }
        
        # Загружаем начальные snapshots
        logger.info(f"📖 Загрузка начального стакана для YES...")
        self._load_orderbook_snapshot(yes_token_id)
        
        logger.info(f"📖 Загрузка начального стакана для NO...")
        self._load_orderbook_snapshot(no_token_id)
        
        # Подписываемся на WebSocket diff
        sub = {
            "action": "SUBSCRIBE",
            "channel": "market.depth.diff",
            "marketId": market_id
        }
        
        self._subscriptions.append(sub)
        self._subscribed_markets.add(market_id)
        self._on_orderbook_update = callback
        
        if self._connected:
            self._send(sub)
            logger.info(f"📊 Подписка на orderbook diff рынка #{market_id}")
    
    def subscribe_price(self, market_id: int, callback: Callable = None):
        """
        Подписаться на изменения цены
        
        Args:
            market_id: ID рынка
            callback: Функция вызываемая при обновлении (token_id, price)
        """
        sub = {
            "action": "SUBSCRIBE",
            "channel": "market.last.price",
            "marketId": market_id
        }
        
        self._subscriptions.append(sub)
        self._on_price_update = callback
        
        if self._connected:
            self._send(sub)
            logger.info(f"💰 Подписка на цену рынка #{market_id}")
    
    def subscribe_trades(self, market_id: int, callback: Callable = None):
        """
        Подписаться на сделки
        
        Args:
            market_id: ID рынка  
            callback: Функция вызываемая при сделке
        """
        sub = {
            "action": "SUBSCRIBE",
            "channel": "market.last.trade",
            "marketId": market_id
        }
        
        self._subscriptions.append(sub)
        self._on_trade_update = callback
        
        if self._connected:
            self._send(sub)
            logger.info(f"🔔 Подписка на сделки рынка #{market_id}")
    
    def subscribe_orders(self, market_id: int, callback: Callable = None):
        """
        Подписаться на обновления своих ордеров
        
        Args:
            market_id: ID рынка
            callback: Функция вызываемая при обновлении ордера
        """
        sub = {
            "action": "SUBSCRIBE",
            "channel": "trade.order.update",
            "marketId": market_id
        }
        
        self._subscriptions.append(sub)
        self._on_order_update = callback
        
        if self._connected:
            self._send(sub)
            logger.info(f"📋 Подписка на ордера рынка #{market_id}")
    
    def unsubscribe(self, channel: str, market_id: int):
        """Отписаться от канала"""
        unsub = {
            "action": "UNSUBSCRIBE",
            "channel": channel,
            "marketId": market_id
        }
        
        self._send(unsub)
        
        # Удаляем из списка подписок
        self._subscriptions = [
            s for s in self._subscriptions 
            if not (s.get('channel') == channel and s.get('marketId') == market_id)
        ]
    
    # =========================================================================
    # ОБРАБОТЧИКИ СООБЩЕНИЙ
    # =========================================================================
    
    def _handle_orderbook_update(self, data: Dict):
        """
        Обработка изменения в стакане
        
        Формат: {tokenId, outcomeSide, side, price, size, msgType}
        side: "bids" или "asks"
        size: "0" означает удаление уровня
        """
        token_id = data.get('tokenId', '')
        side = data.get('side', '')  # "bids" или "asks"
        price = data.get('price', '0')
        size = data.get('size', '0')
        
        with self._lock:
            if float(size) == 0:
                # Удаляем уровень
                self._orderbook[token_id][side].pop(price, None)
            else:
                # Обновляем уровень
                self._orderbook[token_id][side][price] = size
        
        # Вызываем callback
        if self._on_orderbook_update:
            try:
                self._on_orderbook_update(token_id, side, price, size)
            except Exception as e:
                logger.error(f"❌ Ошибка в callback orderbook: {e}")
    
    def _handle_price_update(self, data: Dict):
        """
        Обработка изменения цены
        
        Формат: {tokenId, outcomeSide, price, marketId, msgType}
        """
        token_id = data.get('tokenId', '')
        price = float(data.get('price', 0))
        
        with self._lock:
            self._last_prices[token_id] = price
        
        if self._on_price_update:
            try:
                self._on_price_update(token_id, price)
            except Exception as e:
                logger.error(f"❌ Ошибка в callback price: {e}")
    
    def _handle_trade_update(self, data: Dict):
        """
        Обработка новой сделки
        
        Формат: {tokenId, side, outcomeSide, price, shares, amount, marketId, msgType}
        """
        token_id = data.get('tokenId', '')
        
        with self._lock:
            self._last_trades[token_id] = {
                'price': float(data.get('price', 0)),
                'side': data.get('side', ''),
                'shares': float(data.get('shares', 0)),
                'amount': float(data.get('amount', 0)),
                'timestamp': time.time()
            }
        
        if self._on_trade_update:
            try:
                self._on_trade_update(data)
            except Exception as e:
                logger.error(f"❌ Ошибка в callback trade: {e}")
    
    def _handle_order_update(self, data: Dict):
        """Обработка обновления ордера"""
        if self._on_order_update:
            try:
                self._on_order_update(data)
            except Exception as e:
                logger.error(f"❌ Ошибка в callback order: {e}")
    
    def _handle_trade_executed(self, data: Dict):
        """Обработка подтверждённой сделки on-chain"""
        logger.info(f"✅ Сделка подтверждена on-chain: {data.get('tradeNo')}")
    
    # =========================================================================
    # ПОЛУЧЕНИЕ ДАННЫХ
    # =========================================================================
    
    def get_orderbook(self, token_id: str) -> Dict:
        """
        Получить текущий стакан для токена
        
        Returns:
            {'bids': {price: size, ...}, 'asks': {price: size, ...}}
        """
        with self._lock:
            return dict(self._orderbook.get(token_id, {'bids': {}, 'asks': {}}))
    
    def get_best_prices(self, token_id: str) -> tuple:
        """
        Получить лучшие цены bid/ask для токена
        
        Returns:
            (best_bid, best_ask) или (None, None) если нет данных
        """
        with self._lock:
            book = self._orderbook.get(token_id, {'bids': {}, 'asks': {}})
            
            bids = book.get('bids', {})
            asks = book.get('asks', {})
            
            best_bid = max((float(p) for p in bids.keys()), default=None) if bids else None
            best_ask = min((float(p) for p in asks.keys()), default=None) if asks else None
            
            return best_bid, best_ask
    
    def get_last_price(self, token_id: str) -> Optional[float]:
        """Получить последнюю цену сделки"""
        with self._lock:
            return self._last_prices.get(token_id)
    
    def get_market_prices(self, yes_token_id: str, no_token_id: str) -> tuple:
        """
        Получить цены для бинарного рынка
        
        Returns:
            (yes_bid, yes_ask, no_bid, no_ask)
        """
        yes_bid, yes_ask = self.get_best_prices(yes_token_id)
        no_bid, no_ask = self.get_best_prices(no_token_id)
        
        return yes_bid, yes_ask, no_bid, no_ask


# =========================================================================
# ТЕСТИРОВАНИЕ
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("🧪 Тестирование WebSocket клиента")
    print("=" * 50)
    
    ws = OpinionWebSocket()
    
    # Callbacks для отладки
    def on_orderbook(token_id, side, price, size):
        print(f"📊 Orderbook: {side} @ {price} = {size}")
    
    def on_price(token_id, price):
        print(f"💰 Цена: {price}")
    
    def on_trade(data):
        print(f"🔔 Сделка: {data.get('side')} {data.get('shares')} @ {data.get('price')}")
    
    # Подключаемся
    if ws.connect():
        # Подписываемся на рынок 4144
        ws.subscribe_orderbook(4144, on_orderbook)
        ws.subscribe_price(4144, on_price)
        ws.subscribe_trades(4144, on_trade)
        
        print("\n⏳ Ожидание данных (30 сек)...")
        print("Нажмите Ctrl+C для выхода\n")
        
        # Получаем token IDs из кэша
        tokens = ws._market_tokens.get(4144, {})
        yes_token = tokens.get('yes', '')
        no_token = tokens.get('no', '')
        
        try:
            for i in range(30):
                time.sleep(1)
                
                # Каждые 5 секунд показываем текущие данные
                if i % 5 == 0 and yes_token and no_token:
                    yes_bid, yes_ask = ws.get_best_prices(yes_token)
                    no_bid, no_ask = ws.get_best_prices(no_token)
                    
                    print(f"\n--- Прошло {i} сек ---")
                    print(f"   YES: BID={yes_bid or 'N/A':.4f} | ASK={yes_ask or 'N/A':.4f}" if yes_bid or yes_ask else "   YES: нет данных")
                    print(f"   NO:  BID={no_bid or 'N/A':.4f} | ASK={no_ask or 'N/A':.4f}" if no_bid or no_ask else "   NO:  нет данных")
                    
                    if yes_bid and no_ask:
                        total = (yes_bid + yes_ask) / 2 + (no_bid + no_ask) / 2 if yes_ask and no_bid else None
                        if total:
                            print(f"   Сумма mid: {total:.4f} (должна быть ~1.0)")
                    
        except KeyboardInterrupt:
            print("\n⏹️ Остановка...")
        
        ws.disconnect()
    else:
        print("❌ Не удалось подключиться")
