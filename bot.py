import os, asyncio, logging, requests, pandas as pd, numpy as np
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CRYPTO = {"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","BNBUSDT":"binancecoin","SOLUSDT":"solana","XRPUSDT":"ripple","DOGEUSDT":"dogecoin"}
FOREX = {"EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","NZDUSD","USDCHF","EURGBP","EURJPY","GBPJPY"}

def get_data(sym):
    s = sym.upper().replace("/","").replace("-","")
    if s in CRYPTO:
        url = "https://api.coingecko.com/api/v3/coins/" + CRYPTO[s] + "/market_chart"
        r = requests.get(url, params={"vs_currency":"usd","days":"1","interval":"hourly"}, timeout=15)
        r.raise_for_status()
        return pd.Series([p[1] for p in r.json()["prices"]])
    elif s in FOREX:
        base = s[:3]
        quote = s[3:]
        url = "https://api.frankfurter.app/2024-01-01..?from=" + base + "&to=" + quote
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        prices = [v[quote] for v in r.json()["rates"].values()]
        return pd.Series(prices) if len(prices) >= 30 else None
    else:
        from io import StringIO
        url = "https://stooq.com/q/d/l/?s=" + s.lower() + ".us&i=d"
        r = requests.get(url, timeout=15)
        df = pd.read_csv(StringIO(r.text))
        if df.empty or "Close" not in df.columns:
            return None
        return pd.Series(df["Close"].values[-100:])

def run_analysis(sym):
    res = {"symbol":sym,"price":0.0,"signal":"WAIT","confidence":0,"ind":{},"error":None}
    try:
        close = get_data(sym)
        if close is None or len(close) < 30:
            res["error"] = "لا توجد بيانات. جرب BTCUSDT او EURUSD او AAPL"
            return res
        res["price"] = float(close.iloc[-1])
        ind = {}
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        ind["rsi"] = float((100-(100/(1+gain/loss.replace(0,np.nan)))).iloc[-1])
        e12 = close.ewm(span=12,adjust=False).mean()
        e26 = close.ewm(span=26,adjust=False).mean()
        macd = e12 - e26
        msig = macd.ewm(span=9,adjust=False).mean()
        if float(macd.iloc[-1]) > float(msig.iloc[-1]):
            ind["macd"] = "صاعد 🟢"; ind["ms"] = 1
        elif float(macd.iloc[-1]) < float(msig.iloc[-1]):
            ind["macd"] = "هابط 🔴"; ind["ms"] = -1
        else:
            ind["macd"] = "محايد 🟡"; ind["ms"] = 0
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        p = float(close.iloc[-1])
        u = float((sma+2*std).iloc[-1])
        l = float((sma-2*std).iloc[-1])
        m = float(sma.iloc[-1])
        if p >= u:
            ind["bb"] = "فوق الحد العلوي 🔴"; ind["bs"] = -1
        elif p <= l:
            ind["bb"] = "تحت الحد السفلي 🟢"; ind["bs"] = 1
        elif p > m:
            ind["bb"] = "اعلى المتوسط 🟡"; ind["bs"] = 0.5
        else:
            ind["bb"] = "اسفل المتوسط 🟡"; ind["bs"] = -0.5
        e9 = float(close.ewm(span=9,adjust=False).mean().iloc[-1])
        e21 = float(close.ewm(span=21,adjust=False).mean().iloc[-1])
        e50 = float(close.ewm(span=50,adjust=False).mean().iloc[-1])
        if e9 > e21 > e50:
            ind["trend"] = "صاعد قوي 🟢"; ind["ts"] = 2
        elif e9 > e21:
            ind["trend"] = "صاعد 🟢"; ind["ts"] = 1
        elif e9 < e21 < e50:
            ind["trend"] = "هابط قوي 🔴"; ind["ts"] = -2
        elif e9 < e21:
            ind["trend"] = "هابط 🔴"; ind["ts"] = -1
        else:
            ind["trend"] = "محايد 🟡"; ind["ts"] = 0
        res["ind"] = ind
        score = 0
        rsi = ind["rsi"]
        if rsi < 30: score += 2
        elif rsi > 70: score -= 2
        score += ind["ms"] + ind["bs"] + ind["ts"]
        conf = min(int(abs(score)/6*100), 98)
        if score >= 2:
            res["signal"] = "BUY"; res["confidence"] = max(conf,55)
        elif score <= -2:
            res["signal"] = "SELL"; res["confidence"] = max(conf,55)
        else:
            res["signal"] = "WAIT"; res["confidence"] = conf
    except Exception as e:
        res["error"] = str(e)
    return res

def fmt(r):
    if r["signal"] == "BUY": st = "✅ اشتري CALL"; se = "🟢"
    elif r["signal"] == "SELL": st = "❌ بيع PUT"; se = "🔴"
    else: st = "⏸ انتظر"; se = "🟡"
    ind = r["ind"]
    rsi = ind.get("rsi", 0)
    rc = "ذروة شراء 🔴" if rsi > 70 else "ذروة بيع 🟢" if rsi < 30 else "محايد 🟡"
    conf = r["confidence"]
    bars = "█"*int(conf/10) + "░"*(10-int(conf/10))
    now = datetime.now().strftime("%H:%M:%S")
    return ("📊 *" + r["symbol"] + "*\n🕐 " + now + "\n━━━━━━━━━━━━━\n\n"
            + "💰 السعر: `" + str(round(r["price"],5)) + "`\n\n"
            + se + " *" + st + "*\n"
            + "📊 الثقة: `" + bars + "` " + str(conf) + "%\n\n"
            + "━━━━━━━━━━━━━\n"
            + "• RSI: `" + str(round(rsi,1)) + "` " + rc + "\n"
            + "• MACD: `" + str(ind.get("macd","")) + "`\n"
            + "• Bollinger: `" + str(ind.get("bb","")) + "`\n"
            + "• الاتجاه: `" + str(ind.get("trend","")) + "`\n\n"
            + "⚠️ _للتعليم فقط_")

async def do(msg_func, sym):
    loading = await msg_func("⏳ جاري تحليل *" + sym + "*...", parse_mode="Markdown")
    r = await asyncio.to_thread(run_analysis, sym)
    text = fmt(r) if not r["error"] else "❌ " + r["error"]
    kb = [[InlineKeyboardButton("🔄 تحديث", callback_data="r_"+sym), InlineKeyboardButton("📊 جديد", callback_data="analyze")]]
    await loading.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def start(update, context):
    await update.message.reply_text("🤖 *بوت التداول*\n\nارسل رمز الزوج:\n`BTCUSDT` `EURUSD` `AAPL`", parse_mode="Markdown")

async def btn(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "analyze":
        await q.message.reply_text("📝 ارسل رمز الزوج:", parse_mode="Markdown")
    elif q.data.startswith("r_"):
        await do(q.message.reply_text, q.data[2:])

async def txt(update, context):
    t = update.message.text.strip().upper().replace("/","").replace("-","")
    if 3 <= len(t) <= 12:
        await do(update.message.reply_text, t)
    else:
        await update.message.reply_text("❓ ارسل رمز مثل BTCUSDT")

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Token مش موجود!")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
