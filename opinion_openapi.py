"""
Opinion Trade OpenAPI Client
Обертка для удобной работы с Opinion OpenAPI
Используется для чтения данных (цены, стакан, рынки)
"""
# -*- coding: utf-8 -*-

import requests
import logging
from typing import Optional, Dict, List, Tuple
from config import APIKEY, HOST

logger = logging.getLogger(__name__)

class OpinionOpenAPI:
    """Клиент для Opinion OpenAPI"""
    
    BASE_URL = "https://proxy.opinion.trade:8443/openapi"
    RATE_LIMIT = 15  # Запросов в секунду
    
    # Ограничения платформы (из документации)
    MIN_PRICE = 0.01   # Минимальная цена (1%)
    MAX_PRICE = 0.99   # Максимальная цена (99%)
    MAX_PRICE_DECIMALS = 4  # Максимум 4 знака после запятой
    
    def __init__(self, api_key: str):
        """
        Инициализация API клиента
        
        Args:
            api_key: API ключ для аутентификации
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': self.api_key,
            'Content-Type': 'application/json'
        })
    
    @staticmethod
    def validate_price(price: float) -> bool:
        """
        Проверить валидность цены
        Документация: цены должны быть от 0.01 до 0.99 с максимум 4 знаками
        
        Args:
            price: Цена для проверки
            
        Returns:
            True если цена валидна, False иначе
        """
        try:
            p = float(price)
            # Проверяем диапазон
            if p < OpinionOpenAPI.MIN_PRICE or p > OpinionOpenAPI.MAX_PRICE:
                logger.warning(f"Цена {p} вне диапазона [{OpinionOpenAPI.MIN_PRICE}, {OpinionOpenAPI.MAX_PRICE}]")
                return False
            
            # Проверяем точность (максимум 4 знака)
            price_str = f"{p:.{OpinionOpenAPI.MAX_PRICE_DECIMALS}f}".rstrip('0').rstrip('.')
            if len(price_str.split('.')[-1]) > OpinionOpenAPI.MAX_PRICE_DECIMALS:
                logger.warning(f"Цена {p} имеет слишком много знаков (максимум {OpinionOpenAPI.MAX_PRICE_DECIMALS})")
                return False
            
            return True
        except (ValueError, TypeError):
            logger.warning(f"Неверный формат цены: {price}")
            return False
    
    @staticmethod
    def format_price(price: float) -> str:
        """
        Отформатировать цену согласно требованиям API
        Максимум 4 знака после запятой, удаляем незначащие нули
        
        Args:
            price: Цена для форматирования
            
        Returns:
            Отформатированная цена в виде строки
        """
        # Округляем до 4 знаков
        rounded = round(float(price), OpinionOpenAPI.MAX_PRICE_DECIMALS)
        # Форматируем и удаляем незначащие нули
        formatted = f"{rounded:.{OpinionOpenAPI.MAX_PRICE_DECIMALS}f}".rstrip('0').rstrip('.')
        return formatted
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Выполнить HTTP запрос к API
        
        Args:
            method: HTTP метод (GET, POST, etc)
            endpoint: API endpoint без базового URL
            params: Query параметры
            
        Returns:
            Response словарь с полями code, msg, result
            Стандартный формат ответа:
            {
                'code': 0,           # 0 = успех, non-zero = ошибка
                'msg': 'success',    # Человеко-читаемое сообщение
                'result': {...}      # Данные ответа
            }
        """
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            else:
                response = self.session.request(method, url, json=params, timeout=10)
            
            # Проверить HTTP статус
            if response.status_code == 429:
                logger.error(f"Rate limit превышен ({endpoint}). Максимум {self.RATE_LIMIT} запросов/сек")
                return {'code': 429, 'msg': 'Too Many Requests', 'result': None}
            
            response.raise_for_status()
            data = response.json()
            
            # Проверить стандартный формат ответа
            if 'code' not in data:
                logger.error(f"Неверный формат ответа API ({endpoint}): нет поля 'code'")
                return {'code': -1, 'msg': 'Invalid response format', 'result': None}
            
            if data.get('code') != 0:
                msg = data.get('msg', 'Unknown error')
                logger.warning(f"API ошибка ({endpoint}, код {data.get('code')}): {msg}")
            
            return data
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP ошибка {response.status_code} ({endpoint}): {e}")
            try:
                error_data = response.json()
                return error_data
            except:
                return {'code': response.status_code, 'msg': str(e), 'result': None}
        except requests.exceptions.Timeout:
            logger.error(f"Timeout при запросе ({endpoint})")
            return {'code': -2, 'msg': 'Request timeout', 'result': None}
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error ({endpoint})")
            return {'code': -3, 'msg': 'Connection error', 'result': None}
        except requests.exceptions.RequestException as e:
            logger.error(f"Request ошибка ({endpoint}): {e}")
            return {'code': -1, 'msg': str(e), 'result': None}
        except Exception as e:
            logger.error(f"Ошибка обработки ответа ({endpoint}): {e}")
            return {'code': -1, 'msg': str(e), 'result': None}
    
    # =====================================================================
    # MARKET ENDPOINTS
    # =====================================================================
    
    def get_markets(self, 
                   page: int = 1, 
                   limit: int = 10,
                   status: Optional[str] = None,
                   sort_by: Optional[int] = None) -> Dict:
        """
        Получить список рынков
        
        Args:
            page: Номер страницы (1-based)
            limit: Количество элементов (макс 20)
            status: Фильтр статуса (activated, resolved)
            sort_by: Сортировка:
                1=new, 2=ending soon, 3=volume desc, 4=volume asc,
                5=volume24h desc, 6=volume24h asc, 7=volume7d desc, 8=volume7d asc
                
        Returns:
            Dict с полем result.list - список рынков
        """
        params = {
            'page': page,
            'limit': min(limit, 20),  # макс 20
        }
        if status:
            params['status'] = status
        if sort_by is not None:
            params['sortBy'] = sort_by
            
        return self._make_request('GET', 'market', params)
    
    def get_market(self, market_id: int) -> Dict:
        """
        Получить детали бинарного рынка
        
        Args:
            market_id: ID рынка
            
        Returns:
            Dict с полем result.data - детали рынка
        """
        return self._make_request('GET', f'market/{market_id}')
    
    def get_categorical_market(self, market_id: int) -> Dict:
        """
        Получить детали категориального рынка с дочерними рынками
        
        Args:
            market_id: ID рынка
            
        Returns:
            Dict с полем result.data - детали рынка
        """
        return self._make_request('GET', f'market/categorical/{market_id}')
    
    # =====================================================================
    # TOKEN ENDPOINTS
    # =====================================================================
    
    def get_orderbook(self, token_id: str) -> Tuple[Optional[List], Optional[List]]:
        """
        Получить стакан для токена
        
        Args:
            token_id: ID токена
            
        Returns:
            Кортеж (bids, asks) со списками BID и ASK ордеров
            Каждый элемент имеет структуру: {'price': str, 'size': str}
        """
        response = self._make_request('GET', f'token/orderbook', {'token_id': token_id})
        
        if response.get('code') != 0:
            return None, None
        
        result = response.get('result', {})
        bids = result.get('bids', [])
        asks = result.get('asks', [])
        
        return bids, asks
    
    def get_latest_price(self, token_id: str) -> Optional[Dict]:
        """
        Получить последнюю цену токена
        
        Args:
            token_id: ID токена
            
        Returns:
            Dict с полями: tokenId, price, side, size, timestamp
            None если ошибка
        """
        response = self._make_request('GET', f'token/latest-price', {'token_id': token_id})
        
        if response.get('code') != 0:
            logger.warning(f"Не удалось получить цену для токена {token_id}: {response.get('msg')}")
            return None
        
        result = response.get('result')
        if result and 'price' in result:
            # Валидируем цену
            try:
                price = float(result['price'])
                if not self.validate_price(price):
                    logger.error(f"Получена невалидная цена {price} для токена {token_id}")
                    return None
            except (ValueError, TypeError):
                logger.error(f"Ошибка при обработке цены: {result.get('price')}")
                return None
        
        return result
    
    def get_price_history(self, 
                         token_id: str, 
                         interval: str = '1h',
                         limit: int = 100) -> Optional[List[Dict]]:
        """
        Получить историю цен токена
        
        Args:
            token_id: ID токена
            interval: Интервал (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Количество свечей
            
        Returns:
            List с полями: t (timestamp), p (price), v (volume)
        """
        params = {
            'token_id': token_id,
            'interval': interval,
            'limit': limit
        }
        response = self._make_request('GET', f'token/price-history', params)
        
        if response.get('code') != 0:
            return None
        
        return response.get('result', {}).get('history', [])
    
    # =====================================================================
    # QUOTE TOKEN ENDPOINTS
    # =====================================================================
    
    def get_quote_tokens(self, 
                        page: int = 1,
                        limit: int = 10,
                        quote_token_name: Optional[str] = None) -> Dict:
        """
        Получить список доступных quote tokens (валют)
        
        Args:
            page: Номер страницы
            limit: Количество элементов
            quote_token_name: Фильтр по названию
            
        Returns:
            Dict с полем result.list - список quote tokens
        """
        params = {
            'page': page,
            'limit': limit,
        }
        if quote_token_name:
            params['quoteTokenName'] = quote_token_name
            
        return self._make_request('GET', 'quoteToken', params)


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def format_orderbook(bids: List[Dict], asks: List[Dict]) -> Dict:
    """
    Форматировать стакан для удобства использования
    BEST PRACTICE из документации: всегда проверяйте orderbook перед торговлей
    
    Args:
        bids: Список BID ордеров
        asks: Список ASK ордеров
        
    Returns:
        Dict с:
        - best_bid: Лучший BID (цена покупки)
        - best_ask: Лучший ASK (цена продажи)
        - spread: Спред между лучшими ценами
        - spread_percent: Спред в процентах от середины
        - mid_price: Средняя цена в центре спреда
        - bids: Форматированные BID ордеры (список из 10 лучших)
        - asks: Форматированные ASK ордеры (список из 10 лучших)
        - depth_bid: Суммарный объем BID
        - depth_ask: Суммарный объем ASK
    """
    result = {
        'best_bid': None,
        'best_ask': None,
        'spread': None,
        'spread_percent': None,
        'mid_price': None,
        'bids': [],
        'asks': [],
        'depth_bid': 0,
        'depth_ask': 0
    }
    
    # Форматировать BID (по убыванию цены)
    if bids:
        sorted_bids = sorted(bids, key=lambda x: float(x['price']), reverse=True)[:10]  # Топ 10
        for bid in sorted_bids:
            try:
                price = float(bid['price'])
                size = float(bid['size'])
                # Валидируем цены
                if OpinionOpenAPI.validate_price(price):
                    result['bids'].append({
                        'price': price,
                        'size': size
                    })
                    result['depth_bid'] += size
            except (ValueError, TypeError):
                logger.warning(f"Невалидный BID: price={bid.get('price')}, size={bid.get('size')}")
                continue
        
        if result['bids']:
            result['best_bid'] = result['bids'][0]['price']
    
    # Форматировать ASK (по возрастанию цены)
    if asks:
        sorted_asks = sorted(asks, key=lambda x: float(x['price']))[:10]  # Топ 10
        for ask in sorted_asks:
            try:
                price = float(ask['price'])
                size = float(ask['size'])
                # Валидируем цены
                if OpinionOpenAPI.validate_price(price):
                    result['asks'].append({
                        'price': price,
                        'size': size
                    })
                    result['depth_ask'] += size
            except (ValueError, TypeError):
                logger.warning(f"Невалидный ASK: price={ask.get('price')}, size={ask.get('size')}")
                continue
        
        if result['asks']:
            result['best_ask'] = result['asks'][0]['price']
    
    # Вычислить спред и середину
    if result['best_bid'] is not None and result['best_ask'] is not None:
        result['spread'] = result['best_ask'] - result['best_bid']
        result['mid_price'] = (result['best_bid'] + result['best_ask']) / 2
        # Спред в процентах от середины
        if result['mid_price'] > 0:
            result['spread_percent'] = (result['spread'] / result['mid_price']) * 100
    
    return result
