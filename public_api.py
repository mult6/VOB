"""
Публичный API клиент для Opinion Trade (без аутентификации)
Использует только публичные endpoints для получения данных
"""
# -*- coding: utf-8 -*-

import requests
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class OpinionPublicAPI:
    """
    Публичный API клиент (БЕЗ API ключа)
    
    Для виртуальной торговли достаточно публичных данных:
    - Список рынков
    - Цены токенов
    - Orderbook (если доступен публично)
    """
    
    # Пробуем разные базовые URL
    BASE_URLS = [
        "https://clob.opinion.trade/api/v1",  # Основной API
        "https://api.opinion.trade/v1",        # Альтернативный
        "https://proxy.opinion.trade:8443/openapi",  # Прокси
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'OpinionVirtualBot/1.0'
        })
        self.base_url = None
        self._find_working_endpoint()
    
    def _find_working_endpoint(self):
        """Найти работающий endpoint"""
        for url in self.BASE_URLS:
            try:
                # Простая проверка доступности
                response = self.session.get(f"{url}/market?page=1&limit=1", timeout=5)
                if response.status_code in [200, 401]:  # 401 = нужен ключ, но endpoint существует
                    logger.info(f"Using base URL: {url}")
                    self.base_url = url
                    return
            except Exception as e:
                logger.debug(f"Endpoint {url} not available: {e}")
                continue
        
        # По умолчанию используем первый
        self.base_url = self.BASE_URLS[0]
        logger.warning(f"No working endpoint found, using default: {self.base_url}")
    
    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Выполнить GET запрос"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Поддержка разных форматов ответа
            if 'errno' in data:
                # Старый формат
                return {
                    'success': data.get('errno', -1) == 0,
                    'data': data.get('result'),
                    'error': data.get('errmsg') if data.get('errno') != 0 else None
                }
            elif 'code' in data:
                # Новый формат
                return {
                    'success': data.get('code', -1) == 0,
                    'data': data.get('result'),
                    'error': data.get('msg') if data.get('code') != 0 else None
                }
            else:
                # Прямой ответ
                return {
                    'success': True,
                    'data': data,
                    'error': None
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error ({endpoint}): {e}")
            
            # Если это запрос рынков и API недоступен, вернуть моки
            if 'market' in endpoint and 'Unauthorized' in str(e):
                logger.warning("API requires authentication - using mock data for virtual trading")
                return self._get_mock_markets()
            
            return {
                'success': False,
                'data': None,
                'error': str(e)
            }
    
    def _get_mock_markets(self) -> Dict:
        """Вернуть моковые рынки для виртуальной торговли"""
        mock_markets = [
            {
                'marketId': 1001,
                'marketTitle': 'Биткоин достигнет $100,000 в 2026?',
                'marketType': 0,
                'volume24h': '50000',
                'yesTokenId': 'YES_BTC_100K',
                'noTokenId': 'NO_BTC_100K'
            },
            {
                'marketId': 1002,
                'marketTitle': 'Ethereum перейдет на PoS полностью в этом году?',
                'marketType': 0,
                'volume24h': '35000',
                'yesTokenId': 'YES_ETH_POS',
                'noTokenId': 'NO_ETH_POS'
            },
            {
                'marketId': 1003,
                'marketTitle': 'OpenAI выпустит GPT-5 в 2026?',
                'marketType': 0,
                'volume24h': '28000',
                'yesTokenId': 'YES_GPT5',
                'noTokenId': 'NO_GPT5'
            },
            {
                'marketId': 1004,
                'marketTitle': 'Россия выиграет Олимпиаду 2026?',
                'marketType': 0,
                'volume24h': '42000',
                'yesTokenId': 'YES_RUS_OLY',
                'noTokenId': 'NO_RUS_OLY'
            },
            {
                'marketId': 1005,
                'marketTitle': 'Apple представит складной iPhone?',
                'marketType': 0,
                'volume24h': '31000',
                'yesTokenId': 'YES_FOLD_IPHONE',
                'noTokenId': 'NO_FOLD_IPHONE'
            },
            {
                'marketId': 1006,
                'marketTitle': 'Tesla выпустит автомобиль дешевле $25,000?',
                'marketType': 0,
                'volume24h': '38000',
                'yesTokenId': 'YES_TESLA_25K',
                'noTokenId': 'NO_TESLA_25K'
            },
            {
                'marketId': 1007,
                'marketTitle': 'SpaceX высадит людей на Марс в 2026?',
                'marketType': 0,
                'volume24h': '45000',
                'yesTokenId': 'YES_MARS_2026',
                'noTokenId': 'NO_MARS_2026'
            },
            {
                'marketId': 1008,
                'marketTitle': 'USD/RUB будет выше 100 в конце года?',
                'marketType': 0,
                'volume24h': '52000',
                'yesTokenId': 'YES_USDRUB_100',
                'noTokenId': 'NO_USDRUB_100'
            },
            {
                'marketId': 1009,
                'marketTitle': 'Золото достигнет $3000 за унцию?',
                'marketType': 0,
                'volume24h': '48000',
                'yesTokenId': 'YES_GOLD_3K',
                'noTokenId': 'NO_GOLD_3K'
            },
            {
                'marketId': 1010,
                'marketTitle': 'Netflix добавит более 50 млн подписчиков?',
                'marketType': 0,
                'volume24h': '29000',
                'yesTokenId': 'YES_NFLX_50M',
                'noTokenId': 'NO_NFLX_50M'
            },
            {
                'marketId': 1011,
                'marketTitle': 'Meta выпустит новые AR-очки Quest 4?',
                'marketType': 0,
                'volume24h': '33000',
                'yesTokenId': 'YES_META_QUEST4',
                'noTokenId': 'NO_META_QUEST4'
            },
            {
                'marketId': 1012,
                'marketTitle': 'Google презентует квантовый компьютер?',
                'marketType': 0,
                'volume24h': '41000',
                'yesTokenId': 'YES_GOOG_QUANTUM',
                'noTokenId': 'NO_GOOG_QUANTUM'
            },
            {
                'marketId': 1013,
                'marketTitle': 'Amazon купит крупную студию контента?',
                'marketType': 0,
                'volume24h': '27000',
                'yesTokenId': 'YES_AMZN_STUDIO',
                'noTokenId': 'NO_AMZN_STUDIO'
            },
            {
                'marketId': 1014,
                'marketTitle': 'Nvidia станет самой дорогой компанией?',
                'marketType': 0,
                'volume24h': '55000',
                'yesTokenId': 'YES_NVDA_TOP',
                'noTokenId': 'NO_NVDA_TOP'
            },
            {
                'marketId': 1015,
                'marketTitle': 'Китай запустит свою космическую станцию?',
                'marketType': 0,
                'volume24h': '36000',
                'yesTokenId': 'YES_CHINA_SPACE',
                'noTokenId': 'NO_CHINA_SPACE'
            },
            {
                'marketId': 1016,
                'marketTitle': 'S&P 500 закроет год выше 6000?',
                'marketType': 0,
                'volume24h': '59000',
                'yesTokenId': 'YES_SPX_6K',
                'noTokenId': 'NO_SPX_6K'
            },
            {
                'marketId': 1017,
                'marketTitle': 'Илон Маск объявит о новом проекте?',
                'marketType': 0,
                'volume24h': '47000',
                'yesTokenId': 'YES_MUSK_PROJECT',
                'noTokenId': 'NO_MUSK_PROJECT'
            },
            {
                'marketId': 1018,
                'marketTitle': 'Искусственный интеллект пройдет тест Тьюринга?',
                'marketType': 0,
                'volume24h': '44000',
                'yesTokenId': 'YES_AI_TURING',
                'noTokenId': 'NO_AI_TURING'
            },
            {
                'marketId': 1019,
                'marketTitle': 'Новая вакцина от рака будет одобрена FDA?',
                'marketType': 0,
                'volume24h': '51000',
                'yesTokenId': 'YES_CANCER_VAX',
                'noTokenId': 'NO_CANCER_VAX'
            },
            {
                'marketId': 1020,
                'marketTitle': 'Глобальная температура превысит рекорд?',
                'marketType': 0,
                'volume24h': '39000',
                'yesTokenId': 'YES_TEMP_RECORD',
                'noTokenId': 'NO_TEMP_RECORD'
            },
        ]
        
        logger.info(f"🎭 Using {len(mock_markets)} mock markets for virtual trading")
        
        return {
            'success': True,
            'data': {
                'total': len(mock_markets),
                'list': mock_markets
            },
            'error': None,
            'mock': True
        }
    
    def get_markets(self, page: int = 1, limit: int = 10, status: str = 'activated') -> Dict:
        """
        Получить список рынков (публичный endpoint)
        
        Args:
            page: Номер страницы
            limit: Рынков на странице (max 20)
            status: Статус рынка ('activated', 'resolved')
        
        Returns:
            {
                'success': bool,
                'data': {'total': int, 'list': [...]},
                'error': str or None
            }
        """
        params = {
            'page': page,
            'limit': min(limit, 20),
            'status': status,
            'sortBy': 5  # По volume 24h
        }
        
        return self._request('market', params)
    
    def get_market(self, market_id: int) -> Dict:
        """Получить детали рынка"""
        return self._request(f'market/{market_id}')
    
    def get_orderbook_public(self, market_id: int) -> Dict:
        """
        Получить orderbook рынка (если доступен публично)
        
        ПРИМЕЧАНИЕ: Если этот endpoint требует API ключ,
        будем симулировать цены на основе последних сделок
        """
        result = self._request(f'market/{market_id}/orderbook')
        
        if not result['success']:
            logger.warning(f"Orderbook недоступен публично для рынка {market_id}")
            # Возвращаем симулированные данные
            return {
                'success': True,
                'data': self._simulate_orderbook(market_id),
                'error': None,
                'simulated': True
            }
        
        return result
    
    def _simulate_orderbook(self, market_id: int) -> Dict:
        """
        Симулировать orderbook на основе случайных цен
        Для виртуальной торговли это приемлемо
        """
        import random
        
        # Генерируем реалистичные цены
        mid_price = random.uniform(0.45, 0.55)
        spread = 0.02
        
        return {
            'bids': [
                {'price': round(mid_price - spread, 3), 'size': '100'},
                {'price': round(mid_price - spread * 2, 3), 'size': '200'},
            ],
            'asks': [
                {'price': round(mid_price + spread, 3), 'size': '100'},
                {'price': round(mid_price + spread * 2, 3), 'size': '200'},
            ]
        }
    
    def get_market_prices_estimate(self, market_id: int, yes_token_id: str, no_token_id: str) -> tuple:
        """
        Оценить цены на рынке
        
        Для виртуальной торговли используем симулированные цены
        На основе вероятности ~50/50 с небольшим спредом
        
        Returns:
            (yes_bid, yes_ask, no_bid, no_ask)
        """
        import random
        
        # Симулируем реалистичные цены
        # YES + NO должно быть примерно = 1.0
        yes_mid = random.uniform(0.45, 0.55)
        no_mid = 1.0 - yes_mid
        
        spread = 0.02  # 2% спред
        
        yes_bid = round(yes_mid - spread, 3)
        yes_ask = round(yes_mid + spread, 3)
        no_bid = round(no_mid - spread, 3)
        no_ask = round(no_mid + spread, 3)
        
        logger.info(f"📊 Симулированные цены для рынка {market_id}:")
        logger.info(f"   YES: BID {yes_bid} | ASK {yes_ask}")
        logger.info(f"   NO:  BID {no_bid} | ASK {no_ask}")
        
        return yes_bid, yes_ask, no_bid, no_ask


# =============================================================================
# АУТЕНТИФИЦИРОВАННЫЙ API КЛИЕНТ
# =============================================================================

class OpinionAuthAPI:
    """
    Аутентифицированный API клиент для Opinion Trade
    
    Требует OPINION_API_KEY для доступа к реальным данным orderbook.
    Используется в гибридном режиме: реальные цены + виртуальные позиции.
    """
    
    BASE_URL = "https://proxy.opinion.trade:8443/openapi"
    
    def __init__(self, api_key: str):
        """
        Args:
            api_key: API ключ от Opinion Trade
        """
        if not api_key:
            raise ValueError("API key is required for OpinionAuthAPI")
        
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': self.api_key,
            'Content-Type': 'application/json',
            'User-Agent': 'OpinionVirtualBot/1.0'
        })
        
        logger.info("🔑 OpinionAuthAPI initialized with API key")
    
    def _request(self, endpoint: str, method: str = 'GET', params: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Dict:
        """Выполнить HTTP запрос с аутентификацией"""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            elif method == 'POST':
                response = self.session.post(url, json=json_data, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            data = response.json()
            
            # Opinion OpenAPI использует формат: {"errno": 0, "errmsg": "success", "result": {...}}
            # Поддержка обоих форматов (errno/code)
            errno = data.get('errno', data.get('code', -1))
            errmsg = data.get('errmsg', data.get('msg', 'Unknown error'))
            
            if errno == 0:
                return {
                    'success': True,
                    'data': data.get('result'),
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'data': None,
                    'error': errmsg
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error ({endpoint}): {e}")
            return {
                'success': False,
                'data': None,
                'error': str(e)
            }
    
    def get_markets(self, page: int = 1, limit: int = 20, status: str = 'activated') -> Dict:
        """Получить список рынков (с аутентификацией)"""
        params = {
            'page': page,
            'limit': min(limit, 20),
            'status': status,
            'sortBy': 5  # 5 = volume24h desc
        }
        return self._request('market', params=params)
    
    def get_market(self, market_id: int) -> Dict:
        """Получить детали рынка"""
        return self._request(f'market/{market_id}')
    
    def get_orderbook(self, token_id: str) -> Dict:
        """
        Получить РЕАЛЬНЫЙ orderbook для токена
        
        Args:
            token_id: ID токена (YES или NO)
        
        Returns:
            {
                'success': bool,
                'data': {
                    'market': str,
                    'tokenId': str,
                    'timestamp': int,
                    'bids': [{'price': str, 'size': str}, ...],
                    'asks': [{'price': str, 'size': str}, ...]
                },
                'error': str or None
            }
        """
        params = {'token_id': token_id}
        result = self._request('token/orderbook', params=params)
        
        if not result['success']:
            logger.error(f"Failed to get orderbook for token {token_id}: {result['error']}")
        else:
            logger.info(f"✅ Got real orderbook for token {token_id}")
        
        return result
    
    def get_market_prices_from_orderbook(self, market_id: int, yes_token_id: str, no_token_id: str) -> tuple:
        """
        Получить реальные цены из orderbook
        
        Извлекает best bid/ask для YES и NO токенов.
        
        Returns:
            (yes_bid, yes_ask, no_bid, no_ask) or (None, None, None, None) при ошибке
        """
        # Получаем orderbook для YES токена
        yes_orderbook = self.get_orderbook(yes_token_id)
        no_orderbook = self.get_orderbook(no_token_id)
        
        if not yes_orderbook['success'] or not no_orderbook['success']:
            logger.error(f"Cannot get orderbook prices for market {market_id}")
            return None, None, None, None
        
        try:
            # Формат из документации: {'bids': [{'price': str, 'size': str}], 'asks': [...]}
            yes_data = yes_orderbook['data']
            no_data = no_orderbook['data']
            
            yes_bids = yes_data.get('bids', [])
            yes_asks = yes_data.get('asks', [])
            no_bids = no_data.get('bids', [])
            no_asks = no_data.get('asks', [])
            
            # Извлекаем best bid/ask (первые элементы - лучшие цены)
            yes_bid = float(yes_bids[0]['price']) if yes_bids else None
            yes_ask = float(yes_asks[0]['price']) if yes_asks else None
            no_bid = float(no_bids[0]['price']) if no_bids else None
            no_ask = float(no_asks[0]['price']) if no_asks else None
            
            logger.info(f"📊 Реальные цены для рынка {market_id}:")
            logger.info(f"   YES: BID {yes_bid} | ASK {yes_ask}")
            logger.info(f"   NO:  BID {no_bid} | ASK {no_ask}")
            
            return yes_bid, yes_ask, no_bid, no_ask
            
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error(f"Error parsing orderbook data: {e}")
            logger.debug(f"YES orderbook: {yes_orderbook.get('data')}")
            logger.debug(f"NO orderbook: {no_orderbook.get('data')}")
            return None, None, None, None
    
    def test_connection(self) -> bool:
        """Проверить подключение к API"""
        result = self.get_markets(limit=1)
        
        if result['success']:
            logger.info("✅ API connection successful")
            return True
        else:
            logger.error(f"❌ API connection failed: {result['error']}")
            return False


# Тестирование
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    api = OpinionPublicAPI()
    
    # Получить рынки
    print("Получаем список рынков...")
    markets = api.get_markets(limit=5)
    
    if markets['success']:
        print(f"✅ Найдено рынков: {len(markets['data'].get('list', []))}")
        for m in markets['data'].get('list', [])[:3]:
            print(f"  - {m.get('marketTitle', 'Unknown')}")
    else:
        print(f"❌ Ошибка: {markets['error']}")
    
    # Симулировать цены
    print("\nСимулируем цены для виртуальной торговли...")
    prices = api.get_market_prices_estimate(123, 'yes_token', 'no_token')
    print(f"Цены: {prices}")
