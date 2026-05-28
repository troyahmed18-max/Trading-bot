import os, asyncio, logging, requests, pandas as pd, numpy as np
from datetime import datetime
from io import StringIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FH_KEY = os.environ.get("FINNHUB_API_KEY", "")

CRYPTO_MAP = {
    "BTCUSDT":"BTC","ETHUSDT":"ETH","BNBUSDT":"BNB","SOLUSDT":"SOL",
    "XRPUSDT":"XRP","DOGEUSDT":"DOGE","ADAUSDT":"ADA","LTCUSDT":"LTC",
    "MATICUSDT":"MATIC","DOTUSDT":"DOT","AVAXUSDT":"AVAX","LINKUSDT":"LINK",
}
FOREX_LIST  = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","NZDUSD","USDCHF","EURGBP","EURJPY","GBPJPY"]
CRYPTO_LIST = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","LTCUSDT"]
STOCKS_LIST = ["AAPL","TSLA","AMZN","MSFT","META","NVDA","NFLX","AMD","BABA","UBER"]
COMMOD_LIST = ["XAUUSD","XAGUSD","USOIL","UKOIL","NATGAS","COPPER","PLATINUM"]
DURATIONS   = ["1 دقيقة","2 دقيقة","3 دقائق","5 دقائق","10 دقائق","15 دقيقة","30 دقيقة","1 ساعة"]

FINNHUB_FOREX = {
    "EURUSD":"OANDA:EUR_USD","GBPUSD":"OANDA:GBP_USD","USDJPY":"OANDA:USD_JPY",
    "AUDUSD":"OANDA:AUD_USD","USDCAD":"OANDA:USD_CAD","NZDUSD":"OANDA:NZD_USD",
    "USDCHF":"OANDA:USD_CHF","EURGBP":"OANDA:EUR_GBP","EURJPY":"OANDA:EUR_JPY",
    "GBPJPY":"OANDA:GBP_JPY",
}
FINNHUB_COMMOD = {
    "XAUUSD":"OANDA:XAU_USD","XAGUSD":"OANDA:XAG_USD",
    "USOIL":"OANDA:BCO_USD","UKOIL":"OANDA:BCO_USD",
}

import time

def get_candles_finnhub(symbol, resolution="5", count=100):
    now = int(time.time())
    since = now - count * 5 * 60
    url = "https://finnhub.io/api/v1/forex/candle"
    params = {"symbol":symbol,"resolution":resolution,"from":since,"to":now,"token":FH_KEY}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("s") != "ok" or not data.get("c"):
        return None
    return pd.Series(data["c"])

def get_stock_candles(symbol, resolution="5", count=100):
    now = int(time.time())
    since = now - count * 5 * 60
    url = "https://finnhub.io/api/v1/stock/candle"
    params = {"symbol":symbol,"resolution":resolution,"from":since,"to":now,"token":FH_KEY}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("s") != "ok" or not data.get("c"):
        return None
    return pd.Series(data["c"])

def get_crypto_candles(symbol, resolution="60", count=100):
    fsym = CRYPTO_MAP.get(symbol, symbol.replace("USDT",""))
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym":fsym,"tsym":"USD","limit":count}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()["Data"]["Data"]
    return pd.Series([d["close"] for d in data])

def get_data(sym):
    s = sym.upper().replace("/","").replace("-","")
    if s in CRYPTO_MAP:
        return get_crypto_candles(s)
    if s in FINNHUB_FOREX:
        return get_candles_finnhub(FINNHUB_FOREX[s])
    if s in FINNHUB_COMMOD:
        return get_candles_finnhub(FINNHUB_COMMOD[s])
    if s in ["NATGAS","COPPER","PLATINUM"]:
        from io import StringIO
        stooq = {"NATGAS":"ng.f","COPPER":"hg.f","PLATINUM":"pl.f"}
        url = "https://stooq.com/q/d/l/?s=" + stooq[s] + "&i=d"
        r = requests.get(url, timeout=15)
        df = pd.read_csv(StringIO(r.text), on_bad_lines="skip")
        if not df.empty and "Close" in df.columns:
            vals = pd.to_numeric(df["Close"], errors="coerce").dropna()
            if len(vals) >= 30:
                return pd.Series(vals.values[-100:])
    return get_stock_candles(s)

def run_analysis(sym, duration="5 دقائق"):
    res = {"symbol":sym,"price":0.0,"signal":"WAIT","confidence":0,"ind":{},"error":None,"duration":duration}
    try:
        close = get_data(sym)
        if close is None or len(close) < 30:
            res["error"] = "لا توجد بيانات للرمز: " + sym
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
        mv = float(macd.iloc[-1]); sv = float(msig.iloc[-1])
        if mv > sv: ind["macd"]="صاعد 🟢"; ind["ms"]=1
        elif mv < sv: ind["macd"]="هابط 🔴"; ind["ms"]=-1
        else: ind["macd"]="محايد 🟡"; ind["ms"]=0
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        p = float(close.iloc[-1])
        u = float((sma+2*std).iloc[-1])
        l = float((sma-2*std).iloc[-1])
        m = float(sma.iloc[-1])
        if p >= u: ind["bb"]="فوق الحد العلوي 🔴"; ind["bs"]=-1
        elif p <= l: ind["bb"]="تحت الحد السفلي 🟢"; ind["bs"]=1
        elif p > m: ind["bb"]="اعلى المتوسط 🟡"; ind["bs"]=0.5
        else: ind["bb"]="اسفل المتوسط 🟡"; ind["bs"]=-0.5
        e9  = float(close.ewm(span=9 ,adjust=False).mean().iloc[-1])
        e21 = float(close.ewm(span=21,adjust=False).mean().iloc[-1])
        e50 = float(close.ewm(span=50,adjust=False).mean().iloc[-1])
        if e9>e21>e50: ind["trend"]="صاعد قوي 🟢"; ind["ts"]=2
        elif e9>e21: ind["trend"]="صاعد 🟢"; ind["ts"]=1
        elif e9<e21<e50: ind["trend"]="هابط قوي 🔴"; ind["ts"]=-2
        elif e9<e21: ind["trend"]="هابط 🔴"; ind["ts"]=-1
        else: ind["trend"]="محايد 🟡"; ind["ts"]=0
        res["ind"] = ind
        score = 0
        rsi = ind["rsi"]
        if rsi < 30: score += 2
        elif rsi > 70: score -= 2
        elif rsi < 45: score += 0.5
        elif rsi > 55: score -= 0.5
        score += ind["ms"] + ind["bs"] + ind["ts"]
        conf = min(int(abs(score)/7*100), 98)
        if score >= 2: res["signal"]="BUY"; res["confidence"]=max(conf,55)
        elif score <= -2: res["signal"]="SELL"; res["confidence"]=max(conf,55)
        else: res["signal"]="WAIT"; res["confidence"]=conf
    except Exception as e:
        res["error"] = str(e)
    return res

def fmt(r):
    sig = r["signal"]
    if sig == "BUY": st="✅ *اشتري (CALL)*"; se="🟢"
    elif sig == "SELL": st="❌ *بيع (PUT)*"; se="🔴"
    else: st="⏸ *انتظر*"; se="🟡"
    ind = r["ind"]; rsi = ind.get("rsi",0)
    rc = "ذروة شراء 🔴" if rsi>70 else "ذروة بيع 🟢" if rsi<30 else "محايد 🟡"
    conf = r["confidence"]
    bars = "█"*int(conf/10) + "░"*(10-int(conf/10))
    now = datetime.now().strftime("%H:%M:%S")
    dur = r.get("duration","5 دقائق")
    return ("📊 *" + r["symbol"] + "*\n🕐 " + now + "\n━━━━━━━━━━━━━━━\n\n"
            + "💰 *السعر:* `" + str(round(r["price"],5)) + "`\n"
            + "⏱ *مدة الصفقة:* `" + dur + "`\n\n"
            + se + " " + st + "\n"
            + "📊 *الثقة:* `" + bars + "` " + str(conf) + "%\n\n"
            + "━━━━━━━━━━━━━━━\n📈 *المؤشرات:*\n\n"
            + "• RSI: `" + str(round(rsi,1)) + "` — " + rc + "\n"
            + "• MACD: `" + str(ind.get("macd","")) + "`\n"
            + "• Bollinger: `" + str(ind.get("bb","")) + "`\n"
            + "• الاتجاه: `" + str(ind.get("trend","")) + "`\n\n"
            + "━━━━━━━━━━━━━━━\n⚠️ _للتعليم فقط_")

user_sym = {}
user_dur = {}

async def do(msg_func, sym, duration="5 دقائق"):
    loading = await msg_func("⏳ جاري تحليل *" + sym + "*...", parse_mode="Markdown")
    r = await asyncio.to_thread(run_analysis, sym, duration)
    text = fmt(r) if not r["error"] else "❌ " + r["error"]
    kb = [
        [InlineKeyboardButton("🔄 تحديث", callback_data="ref_"+sym),
         InlineKeyboardButton("⏱ غير المدة", callback_data="dur_"+sym)],
        [InlineKeyboardButton("🏠 القائمة", callback_data="back_main")],
    ]
    await loading.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def start(update, context):
    kb = [
        [InlineKeyboardButton("💱 فوركس", callback_data="menu_forex"),
         InlineKeyboardButton("🪙 كريبتو", callback_data="menu_crypto")],
        [InlineKeyboardButton("📈 أسهم", callback_data="menu_stocks"),
         InlineKeyboardButton("🏅 خامات", callback_data="menu_commod")],
        [InlineKeyboardButton("✏️ اكتب رمز", callback_data="newpair")],
    ]
    await update.message.reply_text(
        "🤖 *بوت التداول الذكي*\n\nاختار نوع الأصل 👇",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

def make_grid(items, prefix):
    rows = []
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i], callback_data=prefix+items[i])]
        if i+1 < len(items):
            row.append(InlineKeyboardButton(items[i+1], callback_data=prefix+items[i+1]))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)

async def btn(update, context):
    q = update.callback_query
    await q.answer()
    cid = q.message.chat_id
    if q.data == "newpair":
        await q.message.reply_text("📝 ارسل رمز الزوج:\n`EURUSD` `BTCUSDT` `AAPL` `XAUUSD`", parse_mode="Markdown")
    elif q.data == "menu_forex":
        await q.message.edit_reply_markup(make_grid(FOREX_LIST, "sym_"))
    elif q.data == "menu_crypto":
        await q.message.edit_reply_markup(make_grid(CRYPTO_LIST, "sym_"))
    elif q.data == "menu_stocks":
        await q.message.edit_reply_markup(make_grid(STOCKS_LIST, "sym_"))
    elif q.data == "menu_commod":
        await q.message.edit_reply_markup(make_grid(COMMOD_LIST, "sym_"))
    elif q.data == "back_main":
        kb = [
            [InlineKeyboardButton("💱 فوركس", callback_data="menu_forex"),
             InlineKeyboardButton("🪙 كريبتو", callback_data="menu_crypto")],
            [InlineKeyboardButton("📈 أسهم", callback_data="menu_stocks"),
             InlineKeyboardButton("🏅 خامات", callback_data="menu_commod")],
            [InlineKeyboardButton("✏️ اكتب رمز", callback_data="newpair")],
        ]
        await q.message.edit_reply_markup(InlineKeyboardMarkup(kb))
    elif q.data.startswith("sym_"):
        sym = q.data[4:]
        user_sym[cid] = sym
        await do(q.message.reply_text, sym, user_dur.get(cid,"5 دقائق"))
    elif q.data.startswith("ref_"):
        sym = q.data[4:]
        await do(q.message.reply_text, sym, user_dur.get(cid,"5 دقائق"))
    elif q.data.startswith("dur_"):
        sym = q.data[4:]
        user_sym[cid] = sym
        rows = []
        for i in range(0, len(DURATIONS), 2):
            row = [InlineKeyboardButton(DURATIONS[i], callback_data="sd_"+DURATIONS[i]+"__"+sym)]
            if i+1 < len(DURATIONS):
                row.append(InlineKeyboardButton(DURATIONS[i+1], callback_data="sd_"+DURATIONS[i+1]+"__"+sym))
            rows.append(row)
        await q.message.reply_text("⏱ اختار مدة الصفقة:", reply_markup=InlineKeyboardMarkup(rows))
    elif q.data.startswith("sd_"):
        parts = q.data[3:].split("__")
        dur = parts[0]
        sym = parts[1] if len(parts) > 1 else user_sym.get(cid,"BTCUSDT")
        user_dur[cid] = dur
        await do(q.message.reply_text, sym, dur)

async def txt(update, context):
    cid = update.message.chat_id
    t = update.message.text.strip().upper().replace("/","").replace("-","").replace(" ","")
    if 2 <= len(t) <= 12:
        user_sym[cid] = t
        await do(update.message.reply_text, t, user_dur.get(cid,"5 دقائق"))
    else:
        await update.message.reply_text("❓ ارسل رمز مثل BTCUSDT")

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN مش موجود!")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt))
    logger.info("البوت شغال!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
