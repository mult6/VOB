"""
Локализация для Telegram бота
Поддерживаемые языки: English, 中文 (Китайский)
"""

TRANSLATIONS = {
    'en': {
        # Общие
        'lang_name': 'English',
        'lang_selected': '🇬🇧 Language set to English',
        
        # Приветствие и старт
        'welcome_choose_lang': '🌍 Choose your language:',
        'welcome_back_active': '👋 Welcome back! You have an active session.\n\nUse buttons to control:',
        'welcome_title': '👋 Automatic Opinion Trade Bot\n\n'
                        '🤖 Bot trades automatically:\n'
                        '• Places BID/ASK orders with spread\n'
                        '• Checks execution every 30 sec\n'
                        '• Updates prices on market changes\n'
                        '• Tracks PnL\n\n'
                        '💡 Positions are VIRTUAL - completely safe!\n\n'
                        '🚀 Press the button to start',
        
        # Кнопки
        'btn_start_trading': '🚀 Start Trading',
        'btn_orders': '📝 Orders',
        'btn_check': '🔍 Check',
        'btn_pause_play': '⏸️ Pause/Play',
        'btn_settings': '⚙️ Settings',
        'btn_stop': '🛑 Stop',
        'btn_close': '◀️ Close',
        'btn_refresh': '🔄 Refresh',
        
        # Торговля - шаги
        'trade_active_warning': '⚠️ You already have an active trading session!\n\n'
                               'Use:\n📊 /status - view status\n⏹️ /stop - stop trading',
        'step1_balance': '💰 **Step 1/3: Virtual Balance**\n\n'
                        'Enter amount in USDT for trading:\n'
                        '(minimum $10, recommended $50-100)',
        'balance_min_error': '❌ Minimum $10. Enter amount:',
        'balance_max_error': '❌ Maximum $100,000. Enter amount:',
        'balance_invalid': '❌ Enter a number (e.g.: 50):',
        'loading_markets': '🔍 Loading markets from Opinion Trade...',
        'api_error': '❌ API Error:',
        'no_binary_markets': '❌ No available binary markets',
        'step2_market': '📊 **Step 2/3: Select Market**\n\n💰 Balance: ${balance:.2f} USDT\n\nChoose a market ({count} available):',
        'step3_strategy': '🎯 **Step 3/3: Select Strategy**\n\n'
                         '📍 Market: #{market_id}\n'
                         '📰 {title}...\n\n'
                         'Choose trading strategy:',
        'strategy_dual': '📊 Dual-Side (market making)',
        'strategy_yes': '✅ YES only',
        'strategy_no': '❌ NO only',
        'strategy_arbitrage': '🎯 Arbitrage only',
        'strategy_hybrid': '🔀 Hybrid (recommended)',
        'strategy_hybrid_desc': '70% spread earning + 30% arbitrage reserve',
        
        # Запуск торговли
        'trading_started': '🚀 **Auto-trading started!**\n\n'
                          '📍 Market: #{market_id}\n'
                          '📰 {title}...\n\n'
                          '💰 Balance: ${balance:.2f} USDT\n'
                          '🎯 Strategy: {strategy}\n'
                          '📊 Spread: 10%\n'
                          '⏱️ Update: every {interval} sec\n\n'
                          '✅ Bot automatically:\n'
                          '• Places BID/ASK orders\n'
                          '• Checks execution\n'
                          '• Updates prices\n'
                          '• Sends trade notifications\n\n'
                          '📊 Use /status to view',
        'first_orders_placed': '📝 **First orders placed:**\n{orders}\n\n⌨️ Use buttons to control:',
        'keyboard_activated': '⌨️ Control keyboard activated!',
        
        # Статус
        'no_active_session': '❌ No active trading session.\n\n🚀 Press button to start!',
        'no_session_command': '❌ No active trading session.\n\nUse /trade to start',
        
        # Уведомления
        'price_change': '{direction} **Price change {token}**\n\nWas: {prev:.3f}\nNow: {curr:.3f}\nChange: {pct:+.1f}%',
        'order_repositioned': '🔄 **Order repositioned**\n\n📍 {token} {side}\n❌ Old price: {old:.3f}\n✅ New price: {new:.3f}\n\n💡 Reason: {reason}',
        'reason_price_up': 'Price jumped up: {prev:.3f} → {curr:.3f}',
        'reason_price_down': 'Price jumped down: {prev:.3f} → {curr:.3f}',
        'trade_executed': '✅ **Trade executed!**\n\n{emoji} {side} {token}\n💵 Price: {price:.3f}\n📊 Amount: ${amount:.2f}\n🎯 Tokens: {tokens:.4f}{pnl}\n\n📈 Total PnL: ${total_pnl:+.2f}',
        'arbitrage_executed': '🎯 **ARBITRAGE EXECUTED!**\n\n💰 Type: {arb_type}\n📦 Pairs: {pairs:.2f}\n💵 Profit: ${profit:.2f}\n📈 ROI: {profit_pct:.2f}%\n\n✨ Risk-free profit!',
        
        # Пауза
        'paused': '⏸️ Trading paused\n\nPress ⏸️ again to resume',
        'resumed': '▶️ Trading resumed',
        
        # Ордера
        'active_orders': '📝 **Active orders ({count}):**\n\n{orders}',
        'no_active_orders': '📝 No active orders',
        
        # Проверка
        'checking_orders': '🔍 Checking orders...',
        'check_result': '📊 **Check result:**\n\n',
        'trades_executed': '✅ Trades executed: {count}\n',
        'orders_placed': '\n📝 Orders placed: {count}\n',
        'orders_cancelled': '\n🚫 Stale orders cancelled: {count}\n',
        'nothing_new': 'Nothing new. Orders awaiting execution.',
        'balance_label': '\n\n💰 USDT: ${balance:.2f}',
        'portfolio_label': '\n💼 Portfolio: ${portfolio:.2f}',
        'pnl_label': '\n{emoji} PnL: ${pnl:+.2f} ({pct:+.1f}%)',
        
        # Остановка
        'trading_stopped': '🏁 **Trading stopped**\n\n'
                          '💰 Initial balance: ${initial:.2f}\n'
                          '💼 Final balance: ${final:.2f}\n\n'
                          '{emoji} **Result: ${pnl:+.2f} ({pct:+.1f}%)**\n\n'
                          '📊 Statistics:\n'
                          '   • Trades: {trades}\n'
                          '   • Cycles: {cycles}\n'
                          '   • YES tokens: {yes:.4f}\n'
                          '   • NO tokens: {no:.4f}\n\n'
                          '🚀 /trade - start new session',
        
        # Настройки
        'settings_title': '⚙️ **Notification Settings**\n\n'
                         '📊 **Price changes:** {price_status}\n'
                         '   Threshold: {threshold}%\n\n'
                         '🔄 **Order repositioning:** {repo_status}\n\n'
                         '✅ **Trade execution:** {trades_status}\n\n'
                         '💡 Click button to change',
        'settings_prices': '📊 Prices: {status}',
        'settings_repo': '🔄 Repositioning: {status}',
        'settings_trades': '✅ Trades: {status}',
        'on': '✅ On',
        'off': '❌ Off',
        
        # Стратегии
        'strategy_dual_side': 'Dual-Side (YES + NO)',
        'strategy_yes_only': 'YES only',
        'strategy_no_only': 'NO only',
        
        # Отмена
        'cancelled': '❌ Operation cancelled',
    },
    
    'zh': {
        # Общие
        'lang_name': '中文',
        'lang_selected': '🇨🇳 语言已设置为中文',
        
        # Приветствие и старт
        'welcome_choose_lang': '🌍 请选择您的语言：',
        'welcome_back_active': '👋 欢迎回来！您有一个活跃的交易会话。\n\n使用按钮控制：',
        'welcome_title': '👋 Opinion Trade 自动交易机器人\n\n'
                        '🤖 机器人自动交易：\n'
                        '• 按价差下买入/卖出订单\n'
                        '• 每30秒检查执行情况\n'
                        '• 市场变化时更新价格\n'
                        '• 追踪盈亏\n\n'
                        '💡 仓位是虚拟的 - 完全安全！\n\n'
                        '🚀 点击按钮开始',
        
        # Кнопки
        'btn_start_trading': '🚀 开始交易',
        'btn_orders': '📝 订单',
        'btn_check': '🔍 检查',
        'btn_pause_play': '⏸️ 暂停/继续',
        'btn_settings': '⚙️ 设置',
        'btn_stop': '🛑 停止',
        'btn_close': '◀️ 关闭',
        'btn_refresh': '🔄 刷新',
        
        # Торговля - шаги
        'trade_active_warning': '⚠️ 您已有活跃的交易会话！\n\n'
                               '使用：\n📊 /status - 查看状态\n⏹️ /stop - 停止交易',
        'step1_balance': '💰 **第1步/共3步：虚拟余额**\n\n'
                        '输入USDT交易金额：\n'
                        '（最低$10，建议$50-100）',
        'balance_min_error': '❌ 最低$10。请输入金额：',
        'balance_max_error': '❌ 最高$100,000。请输入金额：',
        'balance_invalid': '❌ 请输入数字（例如：50）：',
        'loading_markets': '🔍 正在从 Opinion Trade 加载市场...',
        'api_error': '❌ API错误：',
        'no_binary_markets': '❌ 没有可用的二元市场',
        'step2_market': '📊 **第2步/共3步：选择市场**\n\n💰 余额：${balance:.2f} USDT\n\n选择市场（{count}个可用）：',
        'step3_strategy': '🎯 **第3步/共3步：选择策略**\n\n'
                         '📍 市场：#{market_id}\n'
                         '📰 {title}...\n\n'
                         '选择交易策略：',
        'strategy_dual': '📊 双边策略（做市）',
        'strategy_arbitrage': '🎯 仅套利',
        'strategy_yes': '✅ 仅买YES',
        'strategy_no': '❌ 仅买NO',
        'strategy_hybrid': '🔀 混合策略（推荐）',
        'strategy_hybrid_desc': '70%价差收益 + 30%套利储备',
        
        # Запуск торговли
        'trading_started': '🚀 **自动交易已启动！**\n\n'
                          '📍 市场：#{market_id}\n'
                          '📰 {title}...\n\n'
                          '💰 余额：${balance:.2f} USDT\n'
                          '🎯 策略：{strategy}\n'
                          '📊 价差：10%\n'
                          '⏱️ 更新：每{interval}秒\n\n'
                          '✅ 机器人自动：\n'
                          '• 下买入/卖出订单\n'
                          '• 检查执行情况\n'
                          '• 更新价格\n'
                          '• 发送交易通知\n\n'
                          '📊 使用 /status 查看',
        'first_orders_placed': '📝 **首批订单已下：**\n{orders}\n\n⌨️ 使用按钮控制：',
        'keyboard_activated': '⌨️ 控制键盘已激活！',
        
        # Статус
        'no_active_session': '❌ 没有活跃的交易会话。\n\n🚀 点击按钮开始！',
        'no_session_command': '❌ 没有活跃的交易会话。\n\n使用 /trade 开始',
        
        # Уведомления
        'price_change': '{direction} **{token}价格变动**\n\n之前：{prev:.3f}\n现在：{curr:.3f}\n变化：{pct:+.1f}%',
        'order_repositioned': '🔄 **订单已重新定位**\n\n📍 {token} {side}\n❌ 旧价格：{old:.3f}\n✅ 新价格：{new:.3f}\n\n💡 原因：{reason}',
        'reason_price_up': '价格上涨：{prev:.3f} → {curr:.3f}',
        'reason_price_down': '价格下跌：{prev:.3f} → {curr:.3f}',
        'trade_executed': '✅ **交易已执行！**\n\n{emoji} {side} {token}\n💵 价格：{price:.3f}\n📊 金额：${amount:.2f}\n🎯 代币：{tokens:.4f}{pnl}\n\n📈 总盈亏：${total_pnl:+.2f}',
        'arbitrage_executed': '🎯 **套利已执行！**\n\n💰 类型：{arb_type}\n📦 对数：{pairs:.2f}\n💵 利润：${profit:.2f}\n📈 收益率：{profit_pct:.2f}%\n\n✨ 无风险利润！',
        
        # Пауза
        'paused': '⏸️ 交易已暂停\n\n再次点击 ⏸️ 继续',
        'resumed': '▶️ 交易已恢复',
        
        # Ордера
        'active_orders': '📝 **活跃订单（{count}个）：**\n\n{orders}',
        'no_active_orders': '📝 没有活跃订单',
        
        # Проверка
        'checking_orders': '🔍 检查订单中...',
        'check_result': '📊 **检查结果：**\n\n',
        'trades_executed': '✅ 已执行交易：{count}\n',
        'orders_placed': '\n📝 已下订单：{count}\n',
        'orders_cancelled': '\n🚫 已取消过期订单：{count}\n',
        'nothing_new': '没有新动态。订单等待执行中。',
        'balance_label': '\n\n💰 USDT：${balance:.2f}',
        'portfolio_label': '\n💼 投资组合：${portfolio:.2f}',
        'pnl_label': '\n{emoji} 盈亏：${pnl:+.2f}（{pct:+.1f}%）',
        
        # Остановка
        'trading_stopped': '🏁 **交易已停止**\n\n'
                          '💰 初始余额：${initial:.2f}\n'
                          '💼 最终余额：${final:.2f}\n\n'
                          '{emoji} **结果：${pnl:+.2f}（{pct:+.1f}%）**\n\n'
                          '📊 统计：\n'
                          '   • 交易：{trades}\n'
                          '   • 周期：{cycles}\n'
                          '   • YES代币：{yes:.4f}\n'
                          '   • NO代币：{no:.4f}\n\n'
                          '🚀 /trade - 开始新会话',
        
        # Настройки
        'settings_title': '⚙️ **通知设置**\n\n'
                         '📊 **价格变动：** {price_status}\n'
                         '   阈值：{threshold}%\n\n'
                         '🔄 **订单重新定位：** {repo_status}\n\n'
                         '✅ **交易执行：** {trades_status}\n\n'
                         '💡 点击按钮更改',
        'settings_prices': '📊 价格：{status}',
        'settings_repo': '🔄 重新定位：{status}',
        'settings_trades': '✅ 交易：{status}',
        'on': '✅ 开',
        'off': '❌ 关',
        
        # Стратегии
        'strategy_dual_side': '双边策略（YES + NO）',
        'strategy_yes_only': '仅YES',
        'strategy_no_only': '仅NO',
        
        # Отмена
        'cancelled': '❌ 操作已取消',
    }
}


def get_text(lang: str, key: str, **kwargs) -> str:
    """Получить локализованный текст"""
    if lang not in TRANSLATIONS:
        lang = 'en'
    
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['en'].get(key, key))
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def get_button_text(lang: str, key: str) -> str:
    """Получить текст кнопки на нужном языке"""
    return get_text(lang, key)
