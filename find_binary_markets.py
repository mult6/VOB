"""
Поиск бинарных рынков (только YES и NO) на Opinion Trade
Выводит список активных рынков с их параметрами
"""
# -*- coding: utf-8 -*-

import requests
import logging
from typing import List, Dict
from config import APIKEY, HOST

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BinaryMarketFinder:
    """Поиск бинарных рынков"""
    
    BASE_URL = "https://proxy.opinion.trade:8443/openapi"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': self.api_key,
            'Content-Type': 'application/json'
        })
    
    def get_markets(self, page: int = 1, limit: int = 20, status: str = 'activated') -> List[Dict]:
        """
        Получить список рынков с фильтром по статусу
        
        Args:
            page: Номер страницы
            limit: Количество рынков на странице (макс 20)
            status: Статус рынка (activated, resolved)
            
        Returns:
            Список рынков
        """
        try:
            params = {
                'page': page,
                'limit': min(limit, 20),
                'status': status,
                'sortBy': 5  # Сортировка по volume 24h descending
            }
            
            logger.debug(f"Запрос с параметрами: {params}")
            response = self.session.get(
                f"{self.BASE_URL}/market",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"Raw response text: {response.text[:300] if response.text else 'empty'}")
            logger.debug(f"JSON type: {type(data)}, JSON keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            
            # Opinion API использует errno вместо code
            errno = data.get('errno', data.get('code', -1))
            errmsg = data.get('errmsg', data.get('msg', 'Unknown error'))
            
            logger.debug(f"Ответ API: errno={errno}, errmsg={errmsg}")
            
            if errno != 0:
                logger.error(f"API ошибка: {errmsg} (errno: {errno})")
                return []
            
            result = data.get('result', {})
            markets = result.get('list', []) if isinstance(result, dict) else []
            logger.debug(f"Получено {len(markets)} рынков")
            return markets
            
        except Exception as e:
            logger.error(f"Ошибка получения рынков: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def filter_binary_markets(self, markets: List[Dict]) -> List[Dict]:
        """
        Отфильтровать только бинарные рынки (YES/NO)
        
        Args:
            markets: Список всех рынков
            
        Returns:
            Список только бинарных рынков
        """
        binary_markets = []
        
        for market in markets:
            # Проверяем тип рынка (0 = Binary, 1 = Categorical)
            market_type = market.get('marketType', -1)
            
            if market_type == 0:  # Binary market
                binary_markets.append(market)
        
        return binary_markets
    
    def find_all_binary_markets(self, max_pages: int = 5) -> List[Dict]:
        """
        Найти все бинарные рынки со страниц
        
        Args:
            max_pages: Максимальное количество страниц для поиска
            
        Returns:
            Список всех найденных бинарных рынков
        """
        all_binary_markets = []
        
        for page in range(1, max_pages + 1):
            logger.info(f"📄 Получение страницы {page}...")
            markets = self.get_markets(page=page, limit=20, status='activated')
            
            if not markets:
                logger.info(f"⚠️  Нет больше рынков")
                break
            
            binary_markets = self.filter_binary_markets(markets)
            all_binary_markets.extend(binary_markets)
            
            logger.info(f"✅ Найдено {len(binary_markets)} бинарных рынков на странице {page}")
        
        return all_binary_markets
    
    def display_markets(self, markets: List[Dict]):
        """
        Красиво вывести информацию о рынках
        
        Args:
            markets: Список рынков
        """
        if not markets:
            logger.warning("❌ Бинарные рынки не найдены")
            return
        
        logger.info(f"\n{'='*100}")
        logger.info(f"{'БИНАРНЫЕ РЫНКИ (YES/NO)':<100}")
        logger.info(f"{'='*100}\n")
        
        for i, market in enumerate(markets, 1):
            market_id = market.get('marketId')
            title = market.get('marketTitle', 'Unknown')
            status = market.get('statusEnum', 'Unknown')
            volume_24h = market.get('volume24h', '0')
            
            yes_label = market.get('yesLabel', 'YES')
            no_label = market.get('noLabel', 'NO')
            
            yes_token = market.get('yesTokenId', 'N/A')
            no_token = market.get('noTokenId', 'N/A')
            
            quote_token = market.get('quoteToken', 'USDT')
            
            cutoff_time = market.get('cutoffAt', 0)
            
            # Вывод информации
            logger.info(f"#{i}")
            logger.info(f"  📍 ID: {market_id}")
            logger.info(f"  📰 Вопрос: {title}")
            logger.info(f"  🏷️  Статус: {status}")
            logger.info(f"  💰 Volume 24h: {volume_24h} {quote_token}")
            logger.info(f"  ✅ {yes_label} Token: {yes_token}")
            logger.info(f"  ❌ {no_label} Token: {no_token}")
            logger.info(f"  ⏰ Завершение: {cutoff_time}")
            logger.info("")  # Пустая строка
        
        logger.info(f"{'='*100}")
        logger.info(f"Всего найдено: {len(markets)} бинарных рынков")
        logger.info(f"{'='*100}\n")


def main():
    """Главная функция"""
    
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║     ПОИСК БИНАРНЫХ РЫНКОВ (YES/NO) НА OPINION TRADE       ║
    ║                                                            ║
    ║  Поиск активных рынков только с бинарными опциями         ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    if not APIKEY:
        print("❌ ОШИБКА: API KEY не установлен в .env файле")
        print("   Добавьте APIKEY=your_api_key в .env файл")
        return
    
    finder = BinaryMarketFinder(APIKEY)
    
    # Получить все бинарные рынки
    logger.info("🔍 Поиск бинарных рынков...")
    binary_markets = finder.find_all_binary_markets(max_pages=5)
    
    # Вывести результаты
    finder.display_markets(binary_markets)
    
    # Дополнительная статистика
    if binary_markets:
        total_volume = sum(
            float(market.get('volume24h', 0)) 
            for market in binary_markets
        )
        avg_volume = total_volume / len(binary_markets) if binary_markets else 0
        
        logger.info("📊 СТАТИСТИКА:")
        logger.info(f"   Всего бинарных рынков: {len(binary_markets)}")
        logger.info(f"   Общий volume 24h: {total_volume:,.2f}")
        logger.info(f"   Средний volume: {avg_volume:,.2f}\n")
        
        # Найти топ 5 по активности
        top_markets = sorted(
            binary_markets,
            key=lambda m: float(m.get('volume24h', 0)),
            reverse=True
        )[:5]
        
        logger.info("🔥 ТОП 5 ПО АКТИВНОСТИ (Volume 24h):")
        for i, market in enumerate(top_markets, 1):
            logger.info(f"   {i}. ID {market.get('marketId')}: {market.get('volume24h')} (Volume 24h)")


if __name__ == "__main__":
    main()
