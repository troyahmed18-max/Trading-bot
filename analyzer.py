import yfinance as yf
import pandas as pd
import numpy as np
import logging
import requests
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

FOREX_MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "NZDUSD": "NZDUSD=X",
    "USDCHF": "USDCHF=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "XAUUSD": "GC=F", "XAGUSD": "SI=F",
    "GOLD": "GC=F", "OIL": "CL=F", "USOIL": "CL=F",
}

CRYPTO_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT", "LTCUSDT",
    "UNIUSDT", "ATOMUSDT", "TRXUSDT", "SHIBUSDT",
}


class MarketAnalyzer:
    def analyze(self, symbol: str) -> Dict[str, Any]:
        result = {
            "symbol": symbol,
            "price": 0.0,
            "signal": "WAIT",
            "confidence": 0,
            "indicators": {},
            "error": None,
        }
        try:
            upper = symbol.upper().replace("/", "").replace("-", "")

            # Route to correct data source
            if upper in CRYPTO_SYMBOLS or (upper.endswith("USDT") and len(upper) <= 12):
                close = self._fetch_binance(upper)
                result["symbol"] = upper
            else:
                yf_sym = FOREX_MAP.get(upper, upper)
                close = self._fetch_yfinance(yf_sym)
                result["symbol"] = upper

            if close is None or len(close) < 30:
                result["error"] = (
                    f"لا توجد بيانات كافية للرمز '{symbol}'.\n"
                    "تأكد من صحة الرمز، مثل:\n"
                    "• فوركس: EURUSD, GBPUSD\n"
                    "• كريبتو: BTCUSDT, ETHUSDT\n"
                    "• أسهم: AAPL, TSLA"
                )
                return result

            result["price"] = float(close.iloc[-1])
            indicators = self._compute_indicators(close)
            result["indicators"] = indicators
            signal, confidence = self._generate_signal(indicators)
            result["signal"] = signal
            result["confidence"] = confidence

        except Exception as e:
            logger.error(f"Analyzer error for {symbol}: {e}", exc_info=True)
            result["error"] = f"خطأ غير متوقع عند تحليل '{symbol}'. حاول مجدداً."
        return result

    # ── Binance (crypto) ───────────────────────────────────────────────────────
    def _fetch_binance(self, symbol: str) -> pd.Series | None:
        url = "https://api.binance.com/api/v3/klines"
        try:
            params = {"symbol": symbol, "interval": "5m", "limit": 100}
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            closes = [float(k[4]) for k in data]
            return pd.Series(closes)
        except Exception as e:
            logger.warning(f"Binance fetch failed for {symbol}: {e}")
            # Fallback to yfinance
            base = symbol.replace("USDT", "")
            return self._fetch_yfinance(f"{base}-USD")

    # ── yfinance (forex / stocks) ──────────────────────────────────────────────
    def _fetch_yfinance(self, yf_symbol: str) -> pd.Series | None:
        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period="5d", interval="5m")
            if df.empty:
                df = ticker.history(period="1mo", interval="1h")
            if df.empty:
                return None
            close = df["Close"].squeeze()
            return close.reset_index(drop=True)
        except Exception as e:
            logger.error(f"yfinance fetch error {yf_symbol}: {e}")
            return None

    # ── indicators ─────────────────────────────────────────────────────────────
    def _compute_indicators(self, close: pd.Series) -> Dict[str, Any]:
        ind = {}

        # RSI
        ind["rsi"] = self._rsi(close, 14)

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        m = float(macd_line.iloc[-1])
        s = float(signal_line.iloc[-1])
        if m > s:
            ind["macd_signal"] = "صاعد 🟢"; ind["macd_score"] = 1
        elif m < s:
            ind["macd_signal"] = "هابط 🔴"; ind["macd_score"] = -1
        else:
            ind["macd_signal"] = "محايد 🟡"; ind["macd_score"] = 0

        # Bollinger Bands
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_b = sma20 + 2 * std20
        lower_b = sma20 - 2 * std20
        price = float(close.iloc[-1])
        u = float(upper_b.iloc[-1])
        l = float(lower_b.iloc[-1])
        mid = float(sma20.iloc[-1])
        if price >= u:
            ind["bb_position"] = "فوق الحد العلوي 🔴"; ind["bb_score"] = -1
        elif price <= l:
            ind["bb_position"] = "تحت الحد السفلي 🟢"; ind["bb_score"] = 1
        elif price > mid:
            ind["bb_position"] = "أعلى المتوسط 🟡"; ind["bb_score"] = 0.5
        else:
            ind["bb_position"] = "أسفل المتوسط 🟡"; ind["bb_score"] = -0.5

        # EMA trend
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        e9, e21, e50 = float(ema9.iloc[-1]), float(ema21.iloc[-1]), float(ema50.iloc[-1])
        if e9 > e21 > e50:
            ind["trend"] = "صاعد قوي 🟢"; ind["trend_score"] = 2
        elif e9 > e21:
            ind["trend"] = "صاعد 🟢"; ind["trend_score"] = 1
        elif e9 < e21 < e50:
            ind["trend"] = "هابط قوي 🔴"; ind["trend_score"] = -2
        elif e9 < e21:
            ind["trend"] = "هابط 🔴"; ind["trend_score"] = -1
        else:
            ind["trend"] = "محايد 🟡"; ind["trend_score"] = 0

        # EMA cross
        prev_e9  = float(ema9.iloc[-2])
        prev_e21 = float(ema21.iloc[-2])
        if prev_e9 <= prev_e21 and e9 > e21:
            ind["ema_cross"] = "تقاطع صاعد (Golden Cross) 🟢"; ind["cross_score"] = 2
        elif prev_e9 >= prev_e21 and e9 < e21:
            ind["ema_cross"] = "تقاطع هابط (Death Cross) 🔴"; ind["cross_score"] = -2
        else:
            ind["ema_cross"] = "لا يوجد تقاطع 🟡"; ind["cross_score"] = 0

        return ind

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    def _generate_signal(self, ind: Dict) -> tuple:
        score = 0.0
        max_score = 7.0

        rsi = ind.get("rsi", 50)
        if rsi < 30:   score += 2
        elif rsi > 70: score -= 2
        elif rsi < 45: score += 0.5
        elif rsi > 55: score -= 0.5

        score += ind.get("macd_score", 0)
        score += ind.get("bb_score", 0)
        score += ind.get("trend_score", 0)
        score += ind.get("cross_score", 0)

        confidence = min(int(abs(score) / max_score * 100), 98)

        if score >= 2:   return "BUY",  max(confidence, 55)
        elif score <= -2: return "SELL", max(confidence, 55)
        else:             return "WAIT", confidence
