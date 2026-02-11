"""
Coinbase Commerce Webhook Server
================================

Принимает webhook от Coinbase Commerce после успешной оплаты
и автоматически отправляет архив бота покупателю через Telegram.

Использует официальный SDK: pip install coinbase-commerce

Запуск:
    python coinbase_webhook.py

Настройка в Coinbase Commerce:
1. Dashboard -> Settings -> Webhooks
2. Add Webhook Endpoint: https://your-server.com/webhook/coinbase
3. Скопируйте Shared Secret в .env как COINBASE_WEBHOOK_SECRET

Важно: Этот сервер должен быть доступен из интернета!
Используйте ngrok для тестирования: ngrok http 5000
"""

import os
import json
import logging
import asyncio
import glob
from datetime import datetime
from typing import Optional, Dict
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# COINBASE COMMERCE SDK
# =============================================================================

try:
    from coinbase_commerce.webhook import Webhook
    from coinbase_commerce.error import SignatureVerificationError, WebhookInvalidPayload
    SDK_AVAILABLE = True
    logger.info("✅ coinbase-commerce SDK loaded")
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("⚠️ SDK not installed. Run: pip install coinbase-commerce")

# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================

COINBASE_WEBHOOK_SECRET = os.getenv('COINBASE_WEBHOOK_SECRET', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
BOT_ARCHIVE_PATH = os.getenv('BOT_ARCHIVE_PATH', './opinion_trade_bot.zip')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '5000'))

# Хранилище: checkout_id -> user_id
pending_checkouts: Dict[str, int] = {}

# Flask приложение
app = Flask(__name__)


# =============================================================================
# ФУНКЦИИ
# =============================================================================

async def send_bot_to_telegram(user_id: int, archive_path: str) -> bool:
    """
    Отправить архив бота пользователю через Telegram
    
    Args:
        user_id: Telegram user ID
        archive_path: Путь к архиву
        
    Returns:
        True если успешно
    """
    try:
        import telegram
        
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Отправляем сообщение
        await bot.send_message(
            chat_id=user_id,
            text="🎉 **Payment Confirmed!**\n\n"
                 "Thank you for your purchase!\n"
                 "Your bot archive is being sent...",
            parse_mode='Markdown'
        )
        
        # Отправляем файл
        with open(archive_path, 'rb') as f:
            await bot.send_document(
                chat_id=user_id,
                document=f,
                filename=os.path.basename(archive_path),
                caption="📦 **Opinion Trade Bot**\n\n"
                        "Extract the archive and follow README.md to get started.\n\n"
                        "Need help? Contact @your_support_username"
            )
        
        logger.info(f"✅ Bot sent to user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send bot to {user_id}: {e}")
        return False


def find_latest_archive() -> Optional[str]:
    """Найти последний созданный архив бота"""
    # Пробуем путь из конфига
    if os.path.exists(BOT_ARCHIVE_PATH):
        return BOT_ARCHIVE_PATH
    
    # Ищем по паттерну
    archives = glob.glob('opinion_trade_bot_*.zip')
    if archives:
        return max(archives, key=os.path.getctime)
    
    # Ищем в родительской папке
    parent_archives = glob.glob('../opinion_trade_bot_*.zip')
    if parent_archives:
        return max(parent_archives, key=os.path.getctime)
    
    return None


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/coinbase', methods=['POST'])
def coinbase_webhook():
    """
    Обработка webhook от Coinbase Commerce
    
    Events:
    - charge:created - Платёж создан
    - charge:confirmed - Платёж подтверждён (отправляем бота!)
    - charge:failed - Платёж не прошёл
    - charge:pending - Ожидает подтверждения блокчейном
    """
    # Получаем данные
    payload = request.get_data(as_text=True)
    signature = request.headers.get('X-CC-Webhook-Signature', '')
    
    # Используем SDK для проверки подписи
    if SDK_AVAILABLE and COINBASE_WEBHOOK_SECRET:
        try:
            event = Webhook.construct_event(payload, signature, COINBASE_WEBHOOK_SECRET)
            event_type = event.type
            event_data = event.data
            logger.info(f"📥 Verified webhook: {event_type}")
        except (SignatureVerificationError, WebhookInvalidPayload) as e:
            logger.warning(f"Invalid webhook signature: {e}")
            return jsonify({'error': 'Invalid signature'}), 401
    else:
        # Fallback: без проверки подписи
        try:
            data = json.loads(payload)
            event_type = data.get('event', {}).get('type', '')
            event_data = data.get('event', {}).get('data', {})
            logger.warning(f"📥 Unverified webhook: {event_type}")
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON'}), 400
    
    # Извлекаем данные о платеже
    checkout_id = event_data.get('id', '') if isinstance(event_data, dict) else getattr(event_data, 'id', '')
    code = event_data.get('code', '') if isinstance(event_data, dict) else getattr(event_data, 'code', '')
    metadata = event_data.get('metadata', {}) if isinstance(event_data, dict) else getattr(event_data, 'metadata', {})
    
    logger.info(f"   Code: {code}, Checkout ID: {checkout_id}")
    
    # Пытаемся найти user_id в metadata
    # Когда пользователь оплачивает, мы можем передать его user_id в metadata
    user_id = metadata.get('telegram_user_id')
    if user_id:
        user_id = int(user_id)
    
    if event_type == 'charge:created':
        logger.info(f"💳 Charge created: {code}")
        
        # Сохраняем связь checkout -> user (если есть)
        if user_id:
            pending_checkouts[checkout_id] = user_id
            logger.info(f"   User ID: {user_id}")
    
    elif event_type == 'charge:confirmed':
        logger.info(f"✅ Payment CONFIRMED: {code}")
        
        # Находим user_id
        if not user_id and checkout_id in pending_checkouts:
            user_id = pending_checkouts[checkout_id]
        
        if user_id:
            # Находим архив
            archive_path = find_latest_archive()
            
            if archive_path:
                # Отправляем бота асинхронно
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(send_bot_to_telegram(user_id, archive_path))
                loop.close()
                
                if success:
                    # Убираем из pending
                    if checkout_id in pending_checkouts:
                        del pending_checkouts[checkout_id]
                    
                    return jsonify({
                        'status': 'ok',
                        'message': 'Bot sent to user'
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to send bot'
                    }), 500
            else:
                logger.error("❌ No bot archive found!")
                return jsonify({
                    'status': 'error',
                    'message': 'Bot archive not found'
                }), 500
        else:
            logger.warning(f"⚠️ Payment confirmed but no user_id for checkout {checkout_id}")
            # Всё равно возвращаем OK чтобы Coinbase не ретраил
            return jsonify({
                'status': 'ok',
                'message': 'Payment confirmed but user unknown'
            })
    
    elif event_type == 'charge:failed':
        logger.info(f"❌ Payment FAILED: {code}")
        
        if checkout_id in pending_checkouts:
            del pending_checkouts[checkout_id]
    
    elif event_type == 'charge:pending':
        logger.info(f"⏳ Payment pending: {code}")
    
    return jsonify({'status': 'ok'})


@app.route('/register_purchase', methods=['POST'])
def register_purchase():
    """
    API для регистрации pending purchase из Telegram бота
    
    POST /register_purchase
    {
        "user_id": 123456789,
        "checkout_id": "abc123"
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    user_id = data.get('user_id')
    checkout_id = data.get('checkout_id')
    
    if not user_id or not checkout_id:
        return jsonify({'error': 'Missing user_id or checkout_id'}), 400
    
    pending_checkouts[checkout_id] = int(user_id)
    
    logger.info(f"📝 Registered pending purchase: user {user_id} -> checkout {checkout_id}")
    
    return jsonify({
        'status': 'ok',
        'message': 'Purchase registered'
    })


@app.route('/manual_send/<int:user_id>', methods=['POST'])
def manual_send(user_id: int):
    """
    Ручная отправка бота (для админа)
    
    POST /manual_send/123456789
    """
    # Здесь можно добавить авторизацию
    
    archive_path = find_latest_archive()
    
    if not archive_path:
        return jsonify({'error': 'No bot archive found'}), 404
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(send_bot_to_telegram(user_id, archive_path))
    loop.close()
    
    if success:
        return jsonify({
            'status': 'ok',
            'message': f'Bot sent to user {user_id}'
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Failed to send bot'
        }), 500


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║     Coinbase Commerce Webhook Server                       ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # Проверяем конфигурацию
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        return
    
    if not COINBASE_WEBHOOK_SECRET:
        logger.warning("⚠️ COINBASE_WEBHOOK_SECRET not set - signature verification disabled")
    
    # Проверяем наличие архива
    archive = find_latest_archive()
    if archive:
        logger.info(f"📦 Bot archive found: {archive}")
    else:
        logger.warning("⚠️ No bot archive found - generate one with package_bot.py")
    
    logger.info(f"🚀 Starting webhook server on port {WEBHOOK_PORT}")
    logger.info(f"📍 Webhook endpoint: http://0.0.0.0:{WEBHOOK_PORT}/webhook/coinbase")
    
    # Запускаем сервер
    app.run(
        host='0.0.0.0',
        port=WEBHOOK_PORT,
        debug=False
    )


if __name__ == '__main__':
    main()
