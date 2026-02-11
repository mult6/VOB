"""
Telegram Bot для АВТОМАТИЧЕСКОЙ виртуальной торговли на Opinion Trade
Работает как bot_v2.py: автоматически размещает и обновляет ордера
"""
# -*- coding: utf-8 -*-

import os
import logging
from typing import Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

# Наши модули
from public_api import OpinionAuthAPI
from auto_trader import AutoTrader
from localization import get_text, get_button_text, TRANSLATIONS
from database import init_database, create_order, get_orders_by_user, update_order_status

# Загружаем переменные окружения
load_dotenv()

# =============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# WebSocket для realtime данных (опционально)
try:
    from opinion_websocket import OpinionWebSocket, WebSocketPriceProvider
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    logger.warning("WebSocket module not available, using API polling")

# =============================================================================
# КОНСТАНТЫ
# =============================================================================

# Состояния разговора
(
    SELECTING_LANGUAGE,
    WAITING_BALANCE,
    SELECTING_MARKET,
    SELECTING_STRATEGY,
    CONFIRMING_START,
    ADMIN_MENU
) = range(6)

# =============================================================================
# НАСТРОЙКИ АДМИНИСТРАТОРА И ПРОДАЖ
# =============================================================================

# ID администратора (может видеть админ-панель и управлять продажами)
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))

# Настройки продаж
SALES_ENABLED = os.getenv('SALES_ENABLED', 'false').lower() == 'true'
BOT_ARCHIVE_PATH = os.getenv('BOT_ARCHIVE_PATH', './opinion_trade_bot.zip')
BOT_PRICE_USD = float(os.getenv('BOT_PRICE_USD', '49.00'))

# Coinbase Commerce API
COINBASE_API_KEY = os.getenv('COINBASE_API_KEY', '')
COINBASE_WEBHOOK_SECRET = os.getenv('COINBASE_WEBHOOK_SECRET', '')

# Инициализация Coinbase клиента
coinbase_client = None
try:
    if COINBASE_API_KEY:
        from coinbase_commerce.client import Client as CoinbaseClient

        coinbase_client = CoinbaseClient(COINBASE_API_KEY)
        logger.info("✅ Coinbase Commerce client initialized")
except ImportError:
    logger.warning("Coinbase client not available")


# Хранилище ожидающих оплату: user_id -> {'charge_id': ..., 'hosted_url': ..., 'timestamp': ...}
pending_purchases: Dict[int, Dict] = {}

# Успешные покупки: user_id -> timestamp
successful_purchases: Dict[int, datetime] = {}

def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором"""
    return user_id == ADMIN_USER_ID and ADMIN_USER_ID > 0

def is_sales_enabled() -> bool:
    """Проверить, включены ли продажи"""
    global SALES_ENABLED
    return SALES_ENABLED

def toggle_sales(enabled: bool):
    """Переключить режим продаж"""
    global SALES_ENABLED
    SALES_ENABLED = enabled
    logger.info(f"🛒 Sales {'enabled' if enabled else 'disabled'}")

# Интервал обновления ордеров (секунды)
UPDATE_INTERVAL = 30
# С WebSocket можно уменьшить до 5-10 сек т.к. данные realtime
WEBSOCKET_UPDATE_INTERVAL = 10

# Использовать WebSocket (если доступен)
USE_WEBSOCKET = os.getenv('USE_WEBSOCKET', 'false').lower() == 'true'

# =============================================================================
# ХРАНИЛИЩЕ ТРЕЙДЕРОВ И НАСТРОЕК
# =============================================================================

# Глобальный словарь: user_id -> AutoTrader
traders: Dict[int, AutoTrader] = {}

# WebSocket провайдеры: user_id -> WebSocketPriceProvider
websocket_providers: Dict[int, 'WebSocketPriceProvider'] = {}

# Настройки уведомлений: user_id -> settings
user_settings: Dict[int, Dict] = {}

# Языки пользователей: user_id -> lang ('en' или 'zh')
user_languages: Dict[int, str] = {}

def get_user_lang(user_id: int) -> str:
    """Получить язык пользователя"""
    return user_languages.get(user_id, 'en')

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'price_change_threshold': 0.05,  # 5% - порог уведомления об изменении цены
    'notify_price_changes': False,   # Уведомлять об изменении цен (выкл по умолчанию)
    'notify_repositioned': True,     # Уведомлять о переставлении ордеров
    'notify_trades': True,           # Уведомлять о сделках
}

def get_user_settings(user_id: int) -> Dict:
    """Получить настройки пользователя"""
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]

# API клиент
api: Optional[OpinionAuthAPI] = None

def get_api() -> OpinionAuthAPI:
    """Получить API клиент"""
    global api
    if api is None:
        api_key = os.getenv('OPINION_API_KEY')
        if not api_key:
            raise ValueError("OPINION_API_KEY не установлен")
        api = OpinionAuthAPI(api_key)
    return api

async def _start_websocket(ws_provider, market_id: int, yes_token_id: str, no_token_id: str):
    """Запустить WebSocket и подписаться на рынок"""
    try:
        await ws_provider.start()
        await ws_provider.subscribe_market(market_id, yes_token_id, no_token_id)
        logger.info(f"✅ WebSocket subscribed to market {market_id}")
    except Exception as e:
        logger.error(f"WebSocket start failed: {e}")

async def _stop_websocket(user_id: int):
    """Остановить WebSocket для пользователя"""
    if user_id in websocket_providers:
        try:
            await websocket_providers[user_id].stop()
            del websocket_providers[user_id]
            logger.info(f"🔌 WebSocket stopped for user {user_id}")
        except Exception as e:
            logger.error(f"WebSocket stop error: {e}")

# =============================================================================
# КОМАНДЫ БОТА
# =============================================================================

def get_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Получить главную клавиатуру с кнопками на нужном языке"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'btn_orders')), KeyboardButton(get_text(lang, 'btn_check'))],
        [KeyboardButton(get_text(lang, 'btn_pause_play')), KeyboardButton(get_text(lang, 'btn_settings'))],
        [KeyboardButton(get_text(lang, 'btn_stop'))]
    ]
    
    # Добавляем кнопку покупки если продажи включены
    if is_sales_enabled():
        keyboard.append([KeyboardButton("🛒 Buy Console Bot")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_start_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Получить стартовую клавиатуру"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'btn_start_trading'))],
        [KeyboardButton("/trade")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - выбор языка"""
    user_id = update.effective_user.id
    
    # Если язык уже выбран и есть активная сессия
    if user_id in user_languages and user_id in traders and traders[user_id].is_running:
        lang = get_user_lang(user_id)
        await update.message.reply_text(
            get_text(lang, 'welcome_back_active'),
            reply_markup=get_main_keyboard_with_buy(lang, user_id)
        )
        return
    
    # Показываем выбор языка
    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇨🇳 中文", callback_data="lang_zh")]
    ]
    
    await update.message.reply_text(
        "🌍 **Choose your language / 请选择您的语言：**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора языка"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = query.data.replace('lang_', '')
    
    # Сохраняем язык
    user_languages[user_id] = lang
    
    # Показываем приветствие на выбранном языке
    await query.edit_message_text(
        get_text(lang, 'lang_selected'),
        parse_mode='Markdown'
    )
    
    # Если есть активная сессия
    if user_id in traders and traders[user_id].is_running:
        await context.bot.send_message(
            chat_id=user_id,
            text=get_text(lang, 'welcome_back_active'),
            reply_markup=get_main_keyboard_with_buy(lang, user_id)
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=get_text(lang, 'welcome_title'),
            reply_markup=get_start_keyboard(lang)
        )


async def trade_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать настройку автоторговли"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    # Проверяем активную сессию
    if user_id in traders and traders[user_id].is_running:
        await update.message.reply_text(get_text(lang, 'trade_active_warning'))
        return ConversationHandler.END
    
    await update.message.reply_text(
        get_text(lang, 'step1_balance'),
        parse_mode='Markdown'
    )
    return WAITING_BALANCE

async def receive_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить баланс"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    try:
        balance = float(update.message.text)
        
        if balance < 10:
            await update.message.reply_text(get_text(lang, 'balance_min_error'))
            return WAITING_BALANCE
        
        if balance > 100000:
            await update.message.reply_text(get_text(lang, 'balance_max_error'))
            return WAITING_BALANCE
        
        context.user_data['balance'] = balance
        
        # Получаем рынки
        await update.message.reply_text(get_text(lang, 'loading_markets'))
        
        try:
            api = get_api()
            markets_response = api.get_markets(page=1, limit=20, status='activated')
            
            if not markets_response['success']:
                await update.message.reply_text(f"{get_text(lang, 'api_error')} {markets_response.get('error')}")
                return ConversationHandler.END
            
            markets = markets_response['data'].get('list', [])
            binary_markets = [m for m in markets if m.get('marketType') == 0]
            
            if not binary_markets:
                await update.message.reply_text(get_text(lang, 'no_binary_markets'))
                return ConversationHandler.END
            
            context.user_data['markets'] = binary_markets
            
            # Создаем кнопки выбора рынка
            keyboard = []
            for i, market in enumerate(binary_markets[:10]):  # Первые 10
                title = market.get('marketTitle', 'Unknown')[:40]
                volume = market.get('volume24h', '0')
                try:
                    vol = float(volume)
                    vol_str = f"${vol/1000:.1f}K" if vol >= 1000 else f"${vol:.0f}"
                except:
                    vol_str = volume
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"#{market['marketId']} {title}... ({vol_str})",
                        callback_data=f"market_{i}"
                    )
                ])
            
            await update.message.reply_text(
                get_text(lang, 'step2_market', balance=balance, count=len(binary_markets)),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
            return SELECTING_MARKET
            
        except Exception as e:
            logger.error(f"Ошибка получения рынков: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
            return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(get_text(lang, 'balance_invalid'))
        return WAITING_BALANCE

async def market_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рынок выбран"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    market_index = int(query.data.split('_')[1])
    markets = context.user_data['markets']
    selected_market = markets[market_index]
    
    context.user_data['selected_market'] = selected_market
    
    # Выбор стратегии
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'strategy_hybrid'), callback_data="strategy_hybrid")],
        [InlineKeyboardButton(get_text(lang, 'strategy_dual'), callback_data="strategy_dual_side")],
        [InlineKeyboardButton(get_text(lang, 'strategy_arbitrage'), callback_data="strategy_arbitrage")],
        [InlineKeyboardButton(get_text(lang, 'strategy_yes'), callback_data="strategy_yes_only")],
        [InlineKeyboardButton(get_text(lang, 'strategy_no'), callback_data="strategy_no_only")]
    ]
    
    await query.edit_message_text(
        get_text(lang, 'step3_strategy', 
                 market_id=selected_market['marketId'],
                 title=selected_market.get('marketTitle', 'Unknown')[:50]),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return SELECTING_STRATEGY

async def strategy_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стратегия выбрана - запускаем бота"""
    query = update.callback_query
    await query.answer()
    
    strategy = query.data.replace('strategy_', '')
    context.user_data['strategy'] = strategy
    
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    balance = context.user_data['balance']
    market = context.user_data['selected_market']
    
    market_info = {
        'market_id': market['marketId'],
        'title': market.get('marketTitle', 'Unknown'),
        'yes_token_id': market['yesTokenId'],
        'no_token_id': market['noTokenId'],
        'yes_label': market.get('yesLabel', 'YES'),
        'no_label': market.get('noLabel', 'NO'),
        'volume24h': market.get('volume24h', '0')
    }
    
    # Создаем AutoTrader
    try:
        # Опционально: WebSocket для realtime данных
        ws_provider = None
        update_interval = UPDATE_INTERVAL
        
        if USE_WEBSOCKET and WEBSOCKET_AVAILABLE:
            try:
                api_key = os.getenv('OPINION_API_KEY')
                if api_key:
                    ws_provider = WebSocketPriceProvider(api_key)
                    # WebSocket запускается асинхронно
                    import asyncio
                    asyncio.create_task(_start_websocket(
                        ws_provider, 
                        market_info['market_id'],
                        market_info['yes_token_id'],
                        market_info['no_token_id']
                    ))
                    websocket_providers[user_id] = ws_provider
                    update_interval = WEBSOCKET_UPDATE_INTERVAL
                    logger.info(f"🔌 WebSocket enabled for user {user_id}")
            except Exception as e:
                logger.warning(f"WebSocket init failed: {e}, using API polling")
                ws_provider = None
        
        trader = AutoTrader(
            user_id=user_id,
            balance=balance,
            market_id=market_info['market_id'],
            market_info=market_info,
            api=get_api(),
            strategy=strategy,
            spread_percent=0.10,  # 10% спред
            order_amount=min(balance * 0.25, 50.0),  # 25% баланса или макс $50
            websocket_provider=ws_provider
        )
        
        trader.start()
        traders[user_id] = trader
        
        # Запускаем фоновую задачу
        job_queue = context.application.job_queue
        if job_queue:
            # Удаляем старую задачу если есть
            current_jobs = job_queue.get_jobs_by_name(f"auto_trade_{user_id}")
            for job in current_jobs:
                job.schedule_removal()
            
            # Создаем новую задачу
            job_queue.run_repeating(
                auto_trade_callback,
                interval=update_interval,
                first=5,
                name=f"auto_trade_{user_id}",
                data={'user_id': user_id}
            )
        
        strategy_name = get_text(lang, f'strategy_{strategy}')
        
        await query.edit_message_text(
            get_text(lang, 'trading_started',
                     market_id=market_info['market_id'],
                     title=market_info['title'][:50],
                     balance=balance,
                     strategy=strategy_name,
                     interval=UPDATE_INTERVAL),
            parse_mode='Markdown'
        )
        
        # Первое обновление сразу
        result = trader.update_orders()
        if result.get('placed_orders'):
            orders_text = "\n".join([
                f"   {'🟢' if o.side == 'BID' else '🔴'} {o.token} {o.side}: ${o.amount:.2f} @ {o.price:.3f}"
                for o in result['placed_orders']
            ])
            
            await context.bot.send_message(
                chat_id=user_id,
                text=get_text(lang, 'first_orders_placed', orders=orders_text),
                parse_mode='Markdown',
                reply_markup=get_main_keyboard_with_buy(lang, user_id)
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=get_text(lang, 'keyboard_activated'),
                reply_markup=get_main_keyboard_with_buy(lang, user_id)
            )
        
    except Exception as e:
        logger.error(f"Ошибка создания трейдера: {e}")
        await query.edit_message_text(f"❌ Error: {e}")
    
    return ConversationHandler.END

async def auto_trade_callback(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача автоторговли"""
    job = context.job
    user_id = job.data['user_id']
    lang = get_user_lang(user_id)  # Получаем язык пользователя
    
    if user_id not in traders:
        job.schedule_removal()
        return
    
    trader = traders[user_id]
    
    if not trader.is_running:
        job.schedule_removal()
        return
    
    try:
        result = trader.update_orders()
        settings = get_user_settings(user_id)
        
        # Уведомления об изменении цен (если включено)
        if settings['notify_price_changes'] and result.get('price_changes'):
            threshold = settings['price_change_threshold'] * 100  # В проценты
            for change in result['price_changes']:
                # Фильтруем по порогу
                if abs(change['change_percent']) >= threshold:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=get_text(lang, 'price_change',
                                      direction=change['direction'],
                                      token=change['token'],
                                      prev=change['prev_price'],
                                      curr=change['curr_price'],
                                      pct=change['change_percent']),
                        parse_mode='Markdown'
                    )
        
        # Уведомления о переставленных ордерах (если включено)
        if settings['notify_repositioned'] and result.get('repositioned_orders'):
            for repo in result['repositioned_orders']:
                # Формируем локализованный reason
                if repo['reason_direction'] == 'up':
                    reason_text = get_text(lang, 'reason_price_up', 
                                          prev=repo['reason_prev'], 
                                          curr=repo['reason_curr'])
                else:
                    reason_text = get_text(lang, 'reason_price_down', 
                                          prev=repo['reason_prev'], 
                                          curr=repo['reason_curr'])
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=get_text(lang, 'order_repositioned',
                                  token=repo['token'],
                                  side=repo['side'],
                                  old=repo['old_price'],
                                  new=repo['new_price'],
                                  reason=reason_text),
                    parse_mode='Markdown'
                )
        
        # Уведомления об арбитраже
        if result.get('arbitrage') and result['arbitrage'].get('executed'):
            arb = result['arbitrage']
            details = arb.get('details', {})
            await context.bot.send_message(
                chat_id=user_id,
                text=get_text(lang, 'arbitrage_executed',
                              arb_type=details.get('type', 'UNKNOWN'),
                              pairs=details.get('pairs', 0),
                              profit=arb.get('profit', 0),
                              profit_pct=details.get('profit_percent', 0)),
                parse_mode='Markdown'
            )
        
        # Уведомления о сделках (если включено)
        if settings['notify_trades'] and result.get('executed_trades'):
            for trade in result['executed_trades']:
                pnl_str = f" (PnL: ${trade.pnl:+.2f})" if trade.pnl != 0 else ""
                emoji = "🟢" if trade.side == 'BUY' else "🔴"
                
                # Получаем актуальный PnL (unrealized) как при /check
                current_total_pnl = trader.get_total_pnl()
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=get_text(lang, 'trade_executed',
                                  emoji=emoji,
                                  side=trade.side,
                                  token=trade.token,
                                  price=trade.price,
                                  amount=trade.amount,
                                  tokens=trade.tokens,
                                  pnl=pnl_str,
                                  total_pnl=current_total_pnl),
                    parse_mode='Markdown'
                )
        
    except Exception as e:
        logger.error(f"Ошибка auto_trade для {user_id}: {e}")

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in traders:
        await update.message.reply_text(get_text(lang, 'no_session_command'))
        return
    
    trader = traders[user_id]
    status_message = trader.get_status_message()
    
    keyboard = [
        [
            InlineKeyboardButton(get_text(lang, 'btn_refresh'), callback_data="refresh_status"),
            InlineKeyboardButton(get_text(lang, 'btn_stop'), callback_data="stop_trading")
        ]
    ]
    
    await update.message.reply_text(
        status_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок статуса"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    if query.data == "refresh_status":
        if user_id not in traders:
            await query.edit_message_text(get_text(lang, 'no_active_session'))
            return
        
        trader = traders[user_id]
        status_message = trader.get_status_message()
        
        keyboard = [
            [
                InlineKeyboardButton(get_text(lang, 'btn_refresh'), callback_data="refresh_status"),
                InlineKeyboardButton(get_text(lang, 'btn_stop'), callback_data="stop_trading")
            ]
        ]
        
        await query.edit_message_text(
            status_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == "stop_trading":
        await stop_trading_internal(query, context, user_id)

async def stop_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановить торговлю"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in traders:
        await update.message.reply_text(get_text(lang, 'no_active_session'))
        return
    
    trader = traders[user_id]
    stats = trader.stop()
    
    # Удаляем фоновую задачу
    job_queue = context.application.job_queue
    if job_queue:
        current_jobs = job_queue.get_jobs_by_name(f"auto_trade_{user_id}")
        for job in current_jobs:
            job.schedule_removal()
    
    # Останавливаем WebSocket если есть
    await _stop_websocket(user_id)
    
    # Удаляем трейдера
    del traders[user_id]
    
    pnl = stats['final_balance'] - stats['initial_balance']
    pnl_percent = (pnl / stats['initial_balance']) * 100
    pnl_emoji = "📈" if pnl >= 0 else "📉"
    
    await update.message.reply_text(
        get_text(lang, 'trading_stopped',
                 initial=stats['initial_balance'],
                 final=stats['final_balance'],
                 emoji=pnl_emoji,
                 pnl=pnl,
                 pct=pnl_percent,
                 trades=stats['trades_count'],
                 cycles=stats['cycles_count'],
                 yes=stats['yes_tokens'],
                 no=stats['no_tokens']),
        parse_mode='Markdown',
        reply_markup=get_start_keyboard(lang)
    )

async def stop_trading_internal(query, context, user_id):
    """Внутренняя функция остановки"""
    lang = get_user_lang(user_id)
    
    if user_id not in traders:
        await query.edit_message_text(get_text(lang, 'no_active_session'))
        return
    
    trader = traders[user_id]
    stats = trader.stop()
    
    # Удаляем фоновую задачу
    job_queue = context.application.job_queue
    if job_queue:
        current_jobs = job_queue.get_jobs_by_name(f"auto_trade_{user_id}")
        for job in current_jobs:
            job.schedule_removal()
    
    # Останавливаем WebSocket если есть
    await _stop_websocket(user_id)
    
    del traders[user_id]
    
    pnl = stats['final_balance'] - stats['initial_balance']
    pnl_percent = (pnl / stats['initial_balance']) * 100
    pnl_emoji = "📈" if pnl >= 0 else "📉"
    
    await query.edit_message_text(
        get_text(lang, 'trading_stopped',
                 initial=stats['initial_balance'],
                 final=stats['final_balance'],
                 emoji=pnl_emoji,
                 pnl=pnl,
                 pct=pnl_percent,
                 trades=stats['trades_count'],
                 cycles=stats['cycles_count'],
                 yes=stats['yes_tokens'],
                 no=stats['no_tokens']),
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок клавиатуры"""
    text = update.message.text
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    # Проверяем кнопки на разных языках
    btn_start_en = get_text('en', 'btn_start_trading')
    btn_start_zh = get_text('zh', 'btn_start_trading')
    btn_orders_en = get_text('en', 'btn_orders')
    btn_orders_zh = get_text('zh', 'btn_orders')
    btn_check_en = get_text('en', 'btn_check')
    btn_check_zh = get_text('zh', 'btn_check')
    btn_pause_en = get_text('en', 'btn_pause_play')
    btn_pause_zh = get_text('zh', 'btn_pause_play')
    btn_stop_en = get_text('en', 'btn_stop')
    btn_stop_zh = get_text('zh', 'btn_stop')
    btn_settings_en = get_text('en', 'btn_settings')
    btn_settings_zh = get_text('zh', 'btn_settings')
    
    if text in [btn_start_en, btn_start_zh, "🚀 Начать торговлю", "🚀 Начать автоторговлю"]:
        return await trade_start(update, context)
    elif text in [btn_stop_en, btn_stop_zh, "🛑 Остановить", "⏹️ Остановить"]:
        return await stop_trading(update, context)
    elif text in [btn_pause_en, btn_pause_zh, "⏸️ Пауза", "⏸️ Pause/Play"]:
        if user_id in traders:
            trader = traders[user_id]
            if trader.is_running:
                trader.is_running = False
                await update.message.reply_text(get_text(lang, 'paused'))
            else:
                trader.is_running = True
                await update.message.reply_text(get_text(lang, 'resumed'))
        else:
            await send_no_session_message(update, lang)
    elif text in [btn_orders_en, btn_orders_zh, "📝 Ордера", "💰 Ордера"]:
        # Показать текущие ордера
        if user_id in traders:
            trader = traders[user_id]
            open_orders = [o for o in trader.orders.values() if o.status == 'open']
            
            if open_orders:
                orders_text = "\n".join([
                    f"{'🟢' if o.side == 'BID' else '🔴'} {o.token} {o.side}: ${o.amount:.2f} @ {o.price:.3f}"
                    for o in open_orders
                ])
                await update.message.reply_text(
                    get_text(lang, 'active_orders', count=len(open_orders), orders=orders_text),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(get_text(lang, 'no_active_orders'))
        else:
            await send_no_session_message(update, lang)
    elif text in [btn_check_en, btn_check_zh] or "Проверить" in text or "检查" in text:
        # Принудительно обновить ордера
        if user_id in traders:
            trader = traders[user_id]
            await update.message.reply_text(get_text(lang, 'checking_orders'))
            result = trader.update_orders()
            
            msg = get_text(lang, 'check_result')
            
            if result.get('executed_trades'):
                msg += get_text(lang, 'trades_executed', count=len(result['executed_trades']))
                for t in result['executed_trades']:
                    msg += f"   • {t.side} {t.token} @ {t.price:.3f}\n"
            
            if result.get('placed_orders'):
                msg += get_text(lang, 'orders_placed', count=len(result['placed_orders']))
                for o in result['placed_orders']:
                    msg += f"   • {o.side} {o.token} @ {o.price:.3f}\n"
            
            if result.get('cancelled_orders'):
                msg += get_text(lang, 'orders_cancelled', count=len(result['cancelled_orders']))
            
            if not any([result.get('executed_trades'), result.get('placed_orders'), result.get('cancelled_orders')]):
                msg += get_text(lang, 'nothing_new')
            
            # Получаем статус с расчётом портфеля
            status = trader.get_status()
            pnl = status['total_pnl']
            pnl_pct = (pnl / status['initial_balance'] * 100) if status['initial_balance'] > 0 else 0
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            
            msg += get_text(lang, 'balance_label', balance=trader.balance)
            msg += get_text(lang, 'portfolio_label', portfolio=status['portfolio_value'])
            msg += get_text(lang, 'pnl_label', emoji=pnl_emoji, pnl=pnl, pct=pnl_pct)
            
            await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await send_no_session_message(update, lang)
    elif text in [btn_settings_en, btn_settings_zh, "⚙️ Настройки"]:
        await show_settings(update, context)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню настроек"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    settings = get_user_settings(user_id)
    
    # Формируем текст состояния
    threshold_pct = int(settings['price_change_threshold'] * 100)
    
    on_text = get_text(lang, 'on')
    off_text = get_text(lang, 'off')
    
    price_status = f"{on_text} ({threshold_pct}%)" if settings['notify_price_changes'] else off_text
    repo_status = on_text if settings['notify_repositioned'] else off_text
    trades_status = on_text if settings['notify_trades'] else off_text
    
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'settings_prices', status=price_status), callback_data="settings_price_toggle")],
        [
            InlineKeyboardButton("1%", callback_data="settings_threshold_1"),
            InlineKeyboardButton("5%", callback_data="settings_threshold_5"),
            InlineKeyboardButton("10%", callback_data="settings_threshold_10"),
            InlineKeyboardButton("20%", callback_data="settings_threshold_20")
        ],
        [InlineKeyboardButton(get_text(lang, 'settings_repo', status=repo_status), callback_data="settings_repo_toggle")],
        [InlineKeyboardButton(get_text(lang, 'settings_trades', status=trades_status), callback_data="settings_trades_toggle")],
        [InlineKeyboardButton(get_text(lang, 'btn_close'), callback_data="settings_close")]
    ]
    
    await update.message.reply_text(
        get_text(lang, 'settings_title', 
                 price_status=price_status,
                 threshold=threshold_pct,
                 repo_status=repo_status,
                 trades_status=trades_status),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок настроек"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    settings = get_user_settings(user_id)
    
    action = query.data
    
    if action == "settings_price_toggle":
        settings['notify_price_changes'] = not settings['notify_price_changes']
    elif action == "settings_repo_toggle":
        settings['notify_repositioned'] = not settings['notify_repositioned']
    elif action == "settings_trades_toggle":
        settings['notify_trades'] = not settings['notify_trades']
    elif action == "settings_threshold_1":
        settings['price_change_threshold'] = 0.01
        settings['notify_price_changes'] = True
    elif action == "settings_threshold_5":
        settings['price_change_threshold'] = 0.05
        settings['notify_price_changes'] = True
    elif action == "settings_threshold_10":
        settings['price_change_threshold'] = 0.10
        settings['notify_price_changes'] = True
    elif action == "settings_threshold_20":
        settings['price_change_threshold'] = 0.20
        settings['notify_price_changes'] = True
    elif action == "settings_close":
        await query.delete_message()
        return
    
    # Обновляем сообщение
    threshold_pct = int(settings['price_change_threshold'] * 100)
    
    on_text = get_text(lang, 'on')
    off_text = get_text(lang, 'off')
    
    price_status = f"{on_text} ({threshold_pct}%)" if settings['notify_price_changes'] else off_text
    repo_status = on_text if settings['notify_repositioned'] else off_text
    trades_status = on_text if settings['notify_trades'] else off_text
    
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'settings_prices', status=price_status), callback_data="settings_price_toggle")],
        [
            InlineKeyboardButton("1%", callback_data="settings_threshold_1"),
            InlineKeyboardButton("5%", callback_data="settings_threshold_5"),
            InlineKeyboardButton("10%", callback_data="settings_threshold_10"),
            InlineKeyboardButton("20%", callback_data="settings_threshold_20")
        ],
        [InlineKeyboardButton(get_text(lang, 'settings_repo', status=repo_status), callback_data="settings_repo_toggle")],
        [InlineKeyboardButton(get_text(lang, 'settings_trades', status=trades_status), callback_data="settings_trades_toggle")],
        [InlineKeyboardButton(get_text(lang, 'btn_close'), callback_data="settings_close")]
    ]
    
    await query.edit_message_text(
        get_text(lang, 'settings_title', 
                 price_status=price_status,
                 threshold=threshold_pct,
                 repo_status=repo_status,
                 trades_status=trades_status),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def send_no_session_message(update: Update, lang: str = 'en'):
    """Отправить сообщение 'нет сессии' с клавиатурой для начала торговли"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'btn_start_trading'))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        get_text(lang, 'no_active_session'),
        reply_markup=reply_markup
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    await update.message.reply_text(get_text(lang, 'cancelled'))
    return ConversationHandler.END


# =============================================================================
# ФУНКЦИИ АДМИНИСТРАТОРА
# =============================================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin - панель администратора"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Access denied. You are not an admin.")
        return
    
    # Статистика
    total_users = len(user_languages)
    active_traders = len([t for t in traders.values() if t.is_running])
    pending_count = len(pending_purchases)
    purchases_count = len(successful_purchases)
    
    sales_status = "🟢 ON" if is_sales_enabled() else "🔴 OFF"
    
    message = f"""
🔐 **ADMIN PANEL**

📊 **Statistics:**
• Total users: {total_users}
• Active traders: {active_traders}
• Pending purchases: {pending_count}
• Successful purchases: {purchases_count}

🛒 **Sales Status:** {sales_status}
💰 **Bot Price:** ${BOT_PRICE_USD:.2f}

⚙️ **Actions:**
"""
    
    keyboard = [
        [
            InlineKeyboardButton(
                "🟢 Enable Sales" if not is_sales_enabled() else "🔴 Disable Sales",
                callback_data="admin_toggle_sales"
            )
        ],
        [InlineKeyboardButton("📦 Generate Bot Archive", callback_data="admin_generate_archive")],
        [InlineKeyboardButton("📋 View Purchases", callback_data="admin_view_purchases")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback от админ-панели"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await query.answer("⛔ Access denied", show_alert=True)
        return
    
    await query.answer()
    action = query.data
    
    if action == "admin_toggle_sales":
        # Переключить продажи
        toggle_sales(not is_sales_enabled())
        
        status = "🟢 Sales ENABLED" if is_sales_enabled() else "🔴 Sales DISABLED"
        await query.edit_message_text(
            f"✅ {status}\n\nUsers will {'now see' if is_sales_enabled() else 'no longer see'} the Buy button.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_back")]
            ])
        )
        
    elif action == "admin_generate_archive":
        await query.edit_message_text("⏳ Generating bot archive...")
        
        try:
            # Запускаем package_bot.py
            import subprocess
            result = subprocess.run(
                ['python', 'package_bot.py', '--version', '3.0'],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            if result.returncode == 0:
                # Находим созданный архив
                import glob
                parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                archives = glob.glob(os.path.join(parent_dir, 'opinion_trade_bot_*.zip'))
                
                if archives:
                    latest_archive = max(archives, key=os.path.getctime)
                    archive_size = os.path.getsize(latest_archive) / 1024
                    
                    await query.edit_message_text(
                        f"✅ **Archive created!**\n\n"
                        f"📁 `{os.path.basename(latest_archive)}`\n"
                        f"📊 Size: {archive_size:.1f} KB\n\n"
                        f"Archive is ready for distribution.",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]
                        ])
                    )
                else:
                    await query.edit_message_text(
                        "⚠️ Archive created but file not found",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]
                        ])
                    )
            else:
                await query.edit_message_text(
                    f"❌ Error creating archive:\n```\n{result.stderr[:500]}\n```",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]
                    ])
                )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Error: {str(e)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]
                ])
            )
    
    elif action == "admin_view_purchases":
        if not successful_purchases:
            message = "📋 **Purchases:** No purchases yet."
        else:
            message = "📋 **Successful Purchases:**\n\n"
            for uid, timestamp in successful_purchases.items():
                message += f"• User `{uid}` - {timestamp.strftime('%Y-%m-%d %H:%M')}\n"
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]
            ])
        )
    
    elif action == "admin_broadcast":
        await query.edit_message_text(
            "📢 **Broadcast Message**\n\n"
            "Send your message now. It will be delivered to all users.\n"
            "Use /cancel to cancel.",
            parse_mode='Markdown'
        )
        context.user_data['admin_broadcast'] = True
        
    elif action == "admin_back":
        # Вернуться к админ-панели
        total_users = len(user_languages)
        active_traders = len([t for t in traders.values() if t.is_running])
        pending_count = len(pending_purchases)
        purchases_count = len(successful_purchases)
        sales_status = "🟢 ON" if is_sales_enabled() else "🔴 OFF"
        
        message = f"""
🔐 **ADMIN PANEL**

📊 **Statistics:**
• Total users: {total_users}
• Active traders: {active_traders}
• Pending purchases: {pending_count}
• Successful purchases: {purchases_count}

🛒 **Sales Status:** {sales_status}
💰 **Bot Price:** ${BOT_PRICE_USD:.2f}
"""
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "🟢 Enable Sales" if not is_sales_enabled() else "🔴 Disable Sales",
                    callback_data="admin_toggle_sales"
                )
            ],
            [InlineKeyboardButton("📦 Generate Bot Archive", callback_data="admin_generate_archive")],
            [InlineKeyboardButton("📋 View Purchases", callback_data="admin_view_purchases")],
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif action == "admin_close":
        await query.delete_message()


async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка broadcast сообщения от админа"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    if not context.user_data.get('admin_broadcast'):
        return
    
    # Сброс флага
    context.user_data['admin_broadcast'] = False
    
    message = update.message.text
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text("📢 Broadcasting message...")
    
    for uid in user_languages.keys():
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 **Announcement**\n\n{message}",
                parse_mode='Markdown'
            )
            sent_count += 1
        except Exception:
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ Broadcast complete!\n"
        f"• Sent: {sent_count}\n"
        f"• Failed: {failed_count}"
    )


# =============================================================================
# ФУНКЦИИ ПРОДАЖ
# =============================================================================

async def buy_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда покупки бота"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    username = update.effective_user.username
    
    if not is_sales_enabled():
        await update.message.reply_text(
            "🔒 Bot sales are currently disabled. Check back later!"
        )
        return

    if not coinbase_client:
        await update.message.reply_text(
            "🔒 Payment gateway not available! Check back later!"
        )
        return        
    
    # Проверяем, не купил ли уже
    # if user_id in successful_purchases:
    #    await update.message.reply_text(
    #        "✅ You have already purchased the bot!\n"
    #        "Use /download to get your copy."
    #    )
    #    return
    order = create_order(user_id)
    
    charge_info = {
        "name": "Opinion Bot",
        "description": "Opinion telegram bot distributibe",
        "local_price": {
            "amount": BOT_PRICE_USD,
            "currency": "USD"
        },
        "pricing_type": "fixed_price",
        "metadata": {
            "order_id": str(order.id),
            "user_id": str(user_id)
        }
    }

    charge = coinbase_client.charge.create(**charge_info)
    
    print(f"User ID: {user_id}")
    print(f"Payment ID: {charge.id}")
    print(f"Order Code: {charge.code}")
    print(f"Payment Link: {charge.hosted_url}")
    
    message = f"""
🤖 **Opinion Trade Bot - Console Edition**

💰 **Price:** ${BOT_PRICE_USD:.2f}

📦 **What you get:**
• Full source code of the trading bot
• 3 trading strategies (Market Making, Arbitrage, Hybrid)
• Automatic order placement
• Real-time price monitoring
• Lifetime updates

🚀 **Features:**
• Works 24/7 on your server
• Your own private keys
• No monthly fees
• Full customization

⚡ **How to buy:**
1. Click "Pay with Crypto" below
2. Complete payment via Coinbase
3. Bot archive will be sent automatically!

"""
    
    keyboard = [
        [InlineKeyboardButton(f"💳 Pay ${BOT_PRICE_USD:.2f} with Crypto", url=charge.hosted_url)]
        #[InlineKeyboardButton("✅ I've Paid - Check Status", callback_data="check_payment")],
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def sales_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback от продаж"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    action = query.data
    
    if action == "check_payment":
        # Проверяем статус через Coinbase API
        purchase_info = pending_purchases.get(user_id)
        
        if purchase_info and purchase_info.get('charge_id') and coinbase_client:
            charge_data = coinbase_client.get_charge(purchase_info['charge_id'])
            
            if charge_data:
                timeline = charge_data.get('timeline', [])
                last_status = timeline[-1].get('status') if timeline else 'UNKNOWN'
                
                if last_status in ['COMPLETED', 'CONFIRMED']:
                    # Платёж подтверждён - отправляем бота!
                    await query.edit_message_text("✅ Payment confirmed! Sending bot...")
                    
                    # Отправляем бота
                    await send_bot_to_user(context, user_id)
                    return
                    
                elif last_status == 'PENDING':
                    await query.edit_message_text(
                        "⏳ **Payment Pending**\n\n"
                        "We've received your payment and it's being confirmed on the blockchain.\n"
                        "This usually takes 1-5 minutes.\n\n"
                        "The bot will be sent automatically once confirmed!",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Check Again", callback_data="check_payment")]
                        ])
                    )
                    return
        
        # Fallback: ручная проверка
        await query.edit_message_text(
            "⏳ **Payment Verification**\n\n"
            "Your payment is being verified.\n"
            "This usually takes 1-5 minutes after blockchain confirmation.\n\n"
            "If you've completed the payment, please wait.\n"
            "The bot will be sent automatically once confirmed!\n\n"
            "💬 Having issues? Contact @unik0l",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Again", callback_data="check_payment")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_purchase")]
            ])
        )
        
        # Уведомляем админа
        if ADMIN_USER_ID > 0:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"💰 **Payment Check Request**\n\n"
                         f"User ID: `{user_id}`\n"
                         f"Username: @{update.effective_user.username or 'N/A'}\n"
                         f"Name: {update.effective_user.full_name}\n\n"
                         f"Please verify payment in Coinbase Commerce dashboard.\n\n"
                         f"Use `/confirm {user_id}` to send them the bot.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    
    elif action == "cancel_purchase":
        if user_id in pending_purchases:
            del pending_purchases[user_id]
        
        await query.edit_message_text(
            "❌ Purchase cancelled.\n\n"
            "Feel free to come back anytime!"
        )


async def confirm_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /confirm <user_id> - подтвердить покупку и отправить бота"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /confirm <user_id>\n"
            "Example: /confirm 123456789"
        )
        return
    
    try:
        buyer_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
        return
    
    # Находим архив
    import glob
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    archives = glob.glob(os.path.join(parent_dir, 'opinion_trade_bot_*.zip'))
    
    if not archives:
        # Пробуем использовать путь из конфига
        archive_path = os.path.join(parent_dir, BOT_ARCHIVE_PATH)
        if not os.path.exists(archive_path):
            await update.message.reply_text(
                "❌ No bot archive found!\n"
                "Please generate one first using /admin -> Generate Archive"
            )
            return
    else:
        archive_path = max(archives, key=os.path.getctime)
    
    try:
        # Отправляем архив покупателю
        await context.bot.send_message(
            chat_id=buyer_id,
            text="🎉 **Payment Confirmed!**\n\n"
                 "Thank you for your purchase!\n"
                 "Your bot archive is being sent...",
            parse_mode='Markdown'
        )
        
        with open(archive_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=buyer_id,
                document=f,
                filename=os.path.basename(archive_path),
                caption="📦 **Opinion Trade Bot**\n\n"
                        "Extract the archive and follow README.md to get started.\n\n"
                        "Need help? Contact @your_support_username"
            )
        
        # Записываем успешную покупку
        successful_purchases[buyer_id] = datetime.now()
        if buyer_id in pending_purchases:
            del pending_purchases[buyer_id]
        
        await update.message.reply_text(
            f"✅ Bot sent to user {buyer_id}!\n"
            f"Archive: {os.path.basename(archive_path)}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending bot: {e}")


async def send_bot_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """
    Отправить архив бота пользователю
    
    Используется для автоматической доставки после подтверждения платежа
    """
    import glob
    
    # Ищем архив бота
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    archives = glob.glob(os.path.join(parent_dir, 'opinion_trade_bot_*.zip'))
    
    if not archives:
        logger.error(f"No bot archive found for user {user_id}")
        return False
    
    archive_path = max(archives, key=os.path.getctime)
    
    try:
        # Отправляем уведомление
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 **Payment Confirmed!**\n\n"
                 "Thank you for your purchase!\n"
                 "Your bot archive is being sent...",
            parse_mode='Markdown'
        )
        
        # Отправляем архив
        with open(archive_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=os.path.basename(archive_path),
                caption="📦 **Opinion Trade Bot**\n\n"
                        "Extract the archive and follow README.md to get started.\n\n"
                        "Need help? Contact @your_support_username"
            )
        
        # Сохраняем успешную покупку
        successful_purchases[user_id] = datetime.now()
        if user_id in pending_purchases:
            del pending_purchases[user_id]
        
        logger.info(f"✅ Bot sent to user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send bot to user {user_id}: {e}")
        return False


async def download_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /download - скачать бота повторно (для тех кто уже купил)"""
    user_id = update.effective_user.id
    
    if user_id not in successful_purchases:
        await update.message.reply_text(
            "❌ You haven't purchased the bot yet.\n"
            "Use /buy to purchase."
        )
        return
    
    # Находим архив
    import glob
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    archives = glob.glob(os.path.join(parent_dir, 'opinion_trade_bot_*.zip'))
    
    if not archives:
        await update.message.reply_text(
            "❌ Bot archive not available. Please contact support."
        )
        return
    
    archive_path = max(archives, key=os.path.getctime)
    
    try:
        with open(archive_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(archive_path),
                caption="📦 **Opinion Trade Bot**\n\nHere's your bot archive!"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")



def get_main_keyboard_with_buy(lang: str, user_id: int) -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой покупки:
    - всегда для админа
    - для остальных только если продажи включены"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'btn_orders')), KeyboardButton(get_text(lang, 'btn_check'))],
        [KeyboardButton(get_text(lang, 'btn_pause_play')), KeyboardButton(get_text(lang, 'btn_settings'))],
        [KeyboardButton(get_text(lang, 'btn_stop'))]
    ]
    if is_admin(user_id) or is_sales_enabled():
        keyboard.append([KeyboardButton("🛒 Buy Console Bot")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =============================================================================

def main():
    """Запуск бота"""
    load_dotenv()
    
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен")
        return
    
    api_key = os.getenv('OPINION_API_KEY')
    if not api_key:
        logger.error("❌ OPINION_API_KEY не установлен")
        return
    
    logger.info("=" * 60)
    logger.info("🤖 Telegram Auto-Trading Bot")
    logger.info("=" * 60)

    # Initialize database
    logger.info("Initializing database...")
    init_database()

    # Проверяем API
    try:
        test_api = OpinionAuthAPI(api_key)
        if test_api.test_connection():
            logger.info("✅ API подключен")
        else:
            logger.error("❌ API не отвечает")
            return
    except Exception as e:
        logger.error(f"❌ Ошибка API: {e}")
        return
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # ConversationHandler для настройки торговли
    trade_conv = ConversationHandler(
        entry_points=[
            CommandHandler('trade', trade_start),
            MessageHandler(filters.Regex('^🚀'), trade_start)  # Ловим все кнопки с ракетой
        ],
        states={
            WAITING_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_balance)],
            SELECTING_MARKET: [CallbackQueryHandler(market_selected, pattern='^market_')],
            SELECTING_STRATEGY: [CallbackQueryHandler(strategy_selected, pattern='^strategy_')],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Обработчики
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(language_selected, pattern='^lang_'))  # Выбор языка
    application.add_handler(trade_conv)
    application.add_handler(CommandHandler('status', show_status))
    application.add_handler(CommandHandler('stop', stop_trading))
    application.add_handler(CommandHandler('settings', show_settings))
    
    # Админ команды
    application.add_handler(CommandHandler('admin', admin_command))
    application.add_handler(CommandHandler('confirm', confirm_purchase))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    
    # Команды продаж
    application.add_handler(CommandHandler('buy', buy_bot_command))
    application.add_handler(CommandHandler('download', download_bot))
    application.add_handler(CallbackQueryHandler(sales_callback, pattern='^(check_payment|cancel_purchase)$'))
    
    # Обработчик кнопки покупки
    application.add_handler(MessageHandler(filters.Regex('^🛒'), buy_bot_command))
    
    application.add_handler(CallbackQueryHandler(status_callback, pattern='^(refresh_status|stop_trading)$'))
    application.add_handler(CallbackQueryHandler(settings_callback, pattern='^settings_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button))
    
    # Логирование настроек
    logger.info("🤖 Bot started / 机器人已启动")
    logger.info(f"⏱️ Update interval: {UPDATE_INTERVAL} sec")
    if ADMIN_USER_ID > 0:
        logger.info(f"👤 Admin ID: {ADMIN_USER_ID}")
    logger.info(f"🛒 Sales enabled: {is_sales_enabled()}")
    
    application.run_polling()

if __name__ == "__main__":
    main()
