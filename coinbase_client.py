"""
Coinbase Commerce Client
========================

Клиент для работы с Coinbase Commerce.
Использует официальный SDK: pip install coinbase-commerce

Документация: https://github.com/coinbase/coinbase-commerce-python
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# =============================================================================
# ПОПЫТКА ИСПОЛЬЗОВАТЬ ОФИЦИАЛЬНЫЙ SDK
# =============================================================================

try:
    from coinbase_commerce.client import Client
    from coinbase_commerce.webhook import Webhook
    from coinbase_commerce.error import SignatureVerificationError, WebhookInvalidPayload
    SDK_AVAILABLE = True
    logger.info("✅ coinbase-commerce SDK loaded")
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("⚠️ coinbase-commerce SDK not installed. Run: pip install coinbase-commerce")


@dataclass
class ChargeResult:
    """Результат создания charge"""
    success: bool
    charge_id: Optional[str] = None
    code: Optional[str] = None
    hosted_url: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


class CoinbaseCommerceClient:
    """
    Простой клиент Coinbase Commerce на основе официального SDK
    
    Установка: pip install coinbase-commerce
    
    Пример использования:
        client = CoinbaseCommerceClient(api_key)
        result = client.create_charge(
            name="Product",
            description="Description",
            amount=49.00,
            metadata={"user_id": "123"}
        )
        print(result.hosted_url)  # Ссылка на оплату
    """
    
    def __init__(self, api_key: str, webhook_secret: Optional[str] = None):
        """
        Args:
            api_key: API ключ Coinbase Commerce
            webhook_secret: Секрет для проверки подписи webhook
        """
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self._client = None
        
        if SDK_AVAILABLE and api_key:
            self._client = Client(api_key=api_key)
            logger.info("✅ Coinbase Commerce client initialized")
    
    @property
    def is_available(self) -> bool:
        """SDK доступен и клиент инициализирован"""
        return self._client is not None
    
    def create_charge(
        self,
        name: str,
        description: str,
        amount: float,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
        redirect_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> ChargeResult:
        """
        Создать новый charge (запрос на оплату)
        
        Args:
            name: Название товара/услуги
            description: Описание
            amount: Сумма
            currency: Валюта (USD, EUR, etc.)
            metadata: Кастомные поля (например telegram_user_id)
            redirect_url: URL после успешной оплаты
            cancel_url: URL при отмене
            
        Returns:
            ChargeResult с информацией о charge
        """
        if not self._client:
            return ChargeResult(success=False, error="SDK not available or API key not set")
        
        try:
            charge_info = {
                "name": name,
                "description": description,
                "pricing_type": "fixed_price",
                "local_price": {
                    "amount": str(amount),
                    "currency": currency
                }
            }
            
            if metadata:
                charge_info["metadata"] = metadata
            
            if redirect_url:
                charge_info["redirect_url"] = redirect_url
            
            if cancel_url:
                charge_info["cancel_url"] = cancel_url
            
            # Создаём charge через SDK
            charge = self._client.charge.create(**charge_info)
            
            return ChargeResult(
                success=True,
                charge_id=charge.id,
                code=charge.code,
                hosted_url=charge.hosted_url,
                expires_at=getattr(charge, 'expires_at', None)
            )
            
        except Exception as e:
            logger.error(f"Failed to create charge: {e}")
            return ChargeResult(success=False, error=str(e))
    
    def get_charge(self, charge_id: str) -> Optional[Dict]:
        """
        Получить информацию о charge
        
        Args:
            charge_id: UUID или код charge
            
        Returns:
            Dict с данными charge или None
        """
        if not self._client:
            return None
        
        try:
            charge = self._client.charge.retrieve(charge_id)
            return dict(charge)
        except Exception as e:
            logger.error(f"Failed to get charge: {e}")
            return None
    
    def list_charges(self, limit: int = 25) -> list:
        """
        Получить список charges
        
        Returns:
            Список charges
        """
        if not self._client:
            return []
        
        try:
            charges = self._client.charge.list()
            return list(charges)[:limit]
        except Exception as e:
            logger.error(f"Failed to list charges: {e}")
            return []
    
    def verify_webhook(self, payload: str, signature: str) -> Optional[Dict]:
        """
        Проверить подпись webhook и получить event
        
        Args:
            payload: Тело запроса (строка)
            signature: Заголовок X-CC-Webhook-Signature
            
        Returns:
            Event объект или None если подпись невалидна
        """
        if not SDK_AVAILABLE:
            logger.warning("SDK not available, cannot verify webhook")
            return None
        
        if not self.webhook_secret:
            logger.warning("Webhook secret not set")
            return None
        
        try:
            event = Webhook.construct_event(payload, signature, self.webhook_secret)
            return dict(event)
        except (SignatureVerificationError, WebhookInvalidPayload) as e:
            logger.error(f"Webhook verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return None
    
    @staticmethod
    def parse_event_metadata(event: Dict) -> Dict:
        """
        Извлечь metadata из webhook события
        
        Args:
            event: Событие от webhook
            
        Returns:
            Dict с metadata (включая telegram_user_id если передавали)
        """
        try:
            # Структура события: event.data.metadata
            data = event.get('data', {})
            return data.get('metadata', {})
        except Exception:
            return {}


# =============================================================================
# HELPER ФУНКЦИИ
# =============================================================================

def create_bot_purchase_charge(
    client: CoinbaseCommerceClient,
    telegram_user_id: int,
    telegram_username: Optional[str] = None,
    price: float = 49.00
) -> ChargeResult:
    """
    Создать charge для покупки бота с привязкой к Telegram пользователю
    
    Args:
        client: Инициализированный CoinbaseCommerceClient
        telegram_user_id: ID пользователя Telegram
        telegram_username: Username пользователя (опционально)
        price: Цена в USD
        
    Returns:
        ChargeResult с hosted_url для оплаты
    """
    metadata = {
        "telegram_user_id": str(telegram_user_id),
        "product": "opinion_trade_bot"
    }
    
    if telegram_username:
        metadata["telegram_username"] = telegram_username
    
    return client.create_charge(
        name="Opinion Trade Bot - Console Edition",
        description="Automated trading bot for Opinion Trade platform. "
                    "Includes 3 strategies, real-time monitoring, and lifetime updates.",
        amount=price,
        currency="USD",
        metadata=metadata
    )


# =============================================================================
# ТЕСТИРОВАНИЕ
# =============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('COINBASE_API_KEY', '')
    
    if not api_key:
        print("❌ COINBASE_API_KEY not set in .env")
        exit(1)
    
    print("=" * 50)
    print("Coinbase Commerce Client Test")
    print("=" * 50)
    
    client = CoinbaseCommerceClient(api_key)
    
    if not client.is_available:
        print("❌ Client not available")
        print("   Run: pip install coinbase-commerce")
        exit(1)
    
    print("✅ Client initialized")
    
    # Тест создания charge
    print("\n📝 Creating test charge...")
    result = create_bot_purchase_charge(
        client=client,
        telegram_user_id=123456789,
        telegram_username="test_user",
        price=1.00  # $1 для теста
    )
    
    if result.success:
        print(f"✅ Charge created!")
        print(f"   Code: {result.code}")
        print(f"   URL: {result.hosted_url}")
        print(f"   Expires: {result.expires_at}")
    else:
        print(f"❌ Failed: {result.error}")
    
    # Тест получения списка charges
    print("\n📋 Recent charges:")
    charges = client.list_charges(limit=5)
    for c in charges:
        print(f"   - {c.get('code', 'N/A')}: {c.get('timeline', [{}])[-1].get('status', 'unknown')}")
