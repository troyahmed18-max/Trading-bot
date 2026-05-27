import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from analyzer import MarketAnalyzer

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

analyzer = MarketAnalyzer()

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 تحليل زوج", callback_data="analyze")],
        [InlineKeyboardButton("📈 فوركس شائع", callback_data="popular_forex"),
         InlineKeyboardButton("🪙 كريبتو شائع", callback_data="popular_crypto")],
        [InlineKeyboardButton("❓ مساعدة", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *مرحباً في بوت التداول الذكي!*\n\n"
        "أنا بحلل السوق بشكل لحظي وأقولك:\n"
        "• ✅ اشتري (CALL)\n"
        "• ❌ بيع (PUT)\n"
        "• ⏸ انتظر\n\n"
        "اكتب الزوج مباشرةً مثل:\n"
        "`EURUSD` أو `BTCUSDT` أو `AAPL`\n\n"
        "أو اختر من الأزرار 👇",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ─── /analyze ─────────────────────────────────────────────────────────────────
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        symbol = context.args[0].upper()
        await do_analysis(update, context, symbol)
    else:
        await update.message.reply_text(
            "📝 اكتب الزوج الذي تريد تحليله:\n\n"
            "مثال:\n`EURUSD` - فوركس\n`BTCUSDT` - كريبتو\n`AAPL` - أسهم",
            parse_mode='Markdown'
        )

# ─── Callback buttons ──────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "analyze":
        await query.message.reply_text(
            "📝 *أرسل رمز الزوج الذي تريد تحليله:*\n\n"
            "أمثلة:\n"
            "• فوركس: `EURUSD`, `GBPUSD`, `USDJPY`\n"
            "• كريبتو: `BTCUSDT`, `ETHUSDT`, `BNBUSDT`\n"
            "• أسهم: `AAPL`, `TSLA`, `AMZN`",
            parse_mode='Markdown'
        )

    elif query.data == "popular_forex":
        keyboard = [
            [InlineKeyboardButton("EUR/USD", callback_data="sym_EURUSD"),
             InlineKeyboardButton("GBP/USD", callback_data="sym_GBPUSD")],
            [InlineKeyboardButton("USD/JPY", callback_data="sym_USDJPY"),
             InlineKeyboardButton("AUD/USD", callback_data="sym_AUDUSD")],
            [InlineKeyboardButton("USD/CAD", callback_data="sym_USDCAD"),
             InlineKeyboardButton("NZD/USD", callback_data="sym_NZDUSD")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
        ]
        await query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))

    elif query.data == "popular_crypto":
        keyboard = [
            [InlineKeyboardButton("BTC/USDT", callback_data="sym_BTCUSDT"),
             InlineKeyboardButton("ETH/USDT", callback_data="sym_ETHUSDT")],
            [InlineKeyboardButton("BNB/USDT", callback_data="sym_BNBUSDT"),
             InlineKeyboardButton("SOL/USDT", callback_data="sym_SOLUSDT")],
            [InlineKeyboardButton("XRP/USDT", callback_data="sym_XRPUSDT"),
             InlineKeyboardButton("DOGE/USDT", callback_data="sym_DOGEUSDT")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
        ]
        await query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))

    elif query.data == "help":
        await query.message.reply_text(
            "📖 *دليل الاستخدام:*\n\n"
            "1️⃣ أرسل رمز الزوج مثل `EURUSD`\n"
            "2️⃣ البوت يحلل: RSI, MACD, Bollinger Bands, EMA\n"
            "3️⃣ يعطيك توصية بناءً على المؤشرات\n"
            "4️⃣ تنفذ الصفقة يدوياً على Expert Option\n\n"
            "⚠️ *تنبيه:* التداول ينطوي على مخاطر. هذا للأغراض التعليمية فقط.",
            parse_mode='Markdown'
        )

    elif query.data.startswith("sym_"):
        symbol = query.data[4:]
        await do_analysis(query, context, symbol, is_callback=True)

    elif query.data == "back_main":
        keyboard = [
            [InlineKeyboardButton("📊 تحليل زوج", callback_data="analyze")],
            [InlineKeyboardButton("📈 فوركس شائع", callback_data="popular_forex"),
             InlineKeyboardButton("🪙 كريبتو شائع", callback_data="popular_crypto")],
            [InlineKeyboardButton("❓ مساعدة", callback_data="help")],
        ]
        await query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("refresh_"):
        symbol = query.data[8:]
        await do_analysis(query, context, symbol, is_callback=True)

# ─── Core analysis function ────────────────────────────────────────────────────
async def do_analysis(update, context, symbol: str, is_callback=False):
    send = update.message.reply_text if not is_callback else update.message.reply_text

    # Determine the right send method
    if is_callback and hasattr(update, 'message'):
        msg_func = update.message.reply_text
    elif hasattr(update, 'message') and update.message:
        msg_func = update.message.reply_text
    else:
        msg_func = update.reply_text if hasattr(update, 'reply_text') else None

    loading_msg = None
    try:
        if msg_func:
            loading_msg = await msg_func(f"⏳ جاري تحليل *{symbol}*...", parse_mode='Markdown')
    except Exception:
        pass

    try:
        result = await asyncio.to_thread(analyzer.analyze, symbol)

        if result['error']:
            text = f"❌ *خطأ:* {result['error']}\n\nتأكد من صحة رمز الزوج."
        else:
            text = format_analysis(result)

        keyboard = [[
            InlineKeyboardButton("🔄 تحديث", callback_data=f"refresh_{symbol}"),
            InlineKeyboardButton("📊 زوج جديد", callback_data="analyze"),
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if loading_msg:
            await loading_msg.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        elif msg_func:
            await msg_func(text, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        err_text = "❌ حدث خطأ أثناء التحليل. حاول مرة أخرى."
        if loading_msg:
            await loading_msg.edit_text(err_text)
        elif msg_func:
            await msg_func(err_text)

# ─── Format analysis result ────────────────────────────────────────────────────
def format_analysis(r: dict) -> str:
    signal = r['signal']
    confidence = r['confidence']
    price = r['price']
    symbol = r['symbol']

    if signal == 'BUY':
        signal_text = "✅ *اشتري (CALL)*"
        signal_emoji = "🟢"
    elif signal == 'SELL':
        signal_text = "❌ *بيع (PUT)*"
        signal_emoji = "🔴"
    else:
        signal_text = "⏸ *انتظر*"
        signal_emoji = "🟡"

    # Confidence bar
    bars = int(confidence / 10)
    conf_bar = "█" * bars + "░" * (10 - bars)

    rsi = r['indicators'].get('rsi', 0)
    macd_sig = r['indicators'].get('macd_signal', 'N/A')
    bb_pos = r['indicators'].get('bb_position', 'N/A')
    trend = r['indicators'].get('trend', 'N/A')
    ema_cross = r['indicators'].get('ema_cross', 'N/A')

    rsi_comment = "ذروة شراء 🔴" if rsi > 70 else "ذروة بيع 🟢" if rsi < 30 else "محايد 🟡"

    now = datetime.now().strftime("%H:%M:%S")

    return (
        f"📊 *تحليل {symbol}*\n"
        f"🕐 {now}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *السعر الحالي:* `{price:.5f}`\n\n"
        f"{signal_emoji} *التوصية:* {signal_text}\n"
        f"📊 *الثقة:* `{conf_bar}` {confidence}%\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📈 *المؤشرات:*\n\n"
        f"• RSI: `{rsi:.1f}` — {rsi_comment}\n"
        f"• MACD: `{macd_sig}`\n"
        f"• Bollinger: `{bb_pos}`\n"
        f"• الاتجاه (EMA): `{trend}`\n"
        f"• تقاطع EMA: `{ema_cross}`\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _للأغراض التعليمية فقط_"
    )

# ─── Text messages ─────────────────────────────────────────────────────────────
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper().replace("/", "").replace("-", "")
    # Basic symbol validation
    if 3 <= len(text) <= 10 and text.isalpha() or (len(text) <= 12 and text.isalnum()):
        await do_analysis(update, context, text)
    else:
        await update.message.reply_text(
            "❓ أرسل رمز الزوج مباشرةً مثل:\n`EURUSD`, `BTCUSDT`, `AAPL`",
            parse_mode='Markdown'
        )

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود في المتغيرات البيئية!")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🤖 البوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
