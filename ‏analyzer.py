import pandas as pd
import numpy as np
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

# CoinGecko IDs for crypto
COINGECKO_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
    "ADAUSDT": "cardano", "AVAXUSDT": "avalanche-2", "DOTUSDT": "polkadot",
    "LINKUSDT": "chainlink", "LTCUSDT": "litecoin", "UNIUSDT": "uniswap",
    "MATICUSDT": "matic-network", "ATOMUSDT": "cosmos", "TRXUSDT": "tron",
}

# Forex pairs via exchangerate.host (free, no key)
FOREX_PAIRS = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "NZDUSD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
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

            if upper in COINGECKO_IDS:
                close = self._fetch_coingecko(upper)
            elif upper in FOREX_PAIRS or (len(upper) == 6 and upper.isalpha()):
                close = self._fetch_forex(upper)
            else:
                # Try as stock via stooq
                close = self._fetch_stooq(upper)

            if close is None or len(close) < 30:
                result["error"] = (
                    f"لا توجد بيانات كافية للرمز '{symbol}'.\n"
                    "جرب:\n• كريبتو: BTCUSDT, ETHUSDT\n"
                    "• فوركس: EURUSD, GBPUSD\n• أسهم: AAPL, TSLA"
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
            result["error"] = f"خطأ عند تحليل '{symbol}'. حاول مجدداً."
        return result

    def _fetch_coingecko(self, symbol: str) -> pd.Series | None:
        coin_id = COINGECKO_IDS.get(symbol)
        if not coin_id:
            return None
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            params = {"vs_currency": "usd", "days": "1", "interval": "hourly"}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            prices = [p[1] for p in r.json()["prices"]]
            return pd.Series(prices)
        except Exception as e:
            logger.error(f"CoinGecko error {symbol}: {e}")
            return None

    def _fetch_forex(self, symbol: str) -> pd.Series | None:
        base = symbol[:3]
        quote = symbol[3:]
        try:
            # Use frankfurter.app - free forex API
            url = f"https://api.frankfurter.app/latest?from={base}&to={quote}"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            rate = r.json()["rates"][quote]
            # Generate synthetic series around current rate for indicators
            # Use timeseries endpoint for history
            url2 = f"https://api.frankfurter.app/2024-01-01..?from={base}&to={quote}"
            r2 = requests.get(url2, timeout=15)
            r2.raise_for_status()
            rates_dict = r2.json()["rates"]
            prices = [v[quote] for v in rates_dict.values()]
            if len(prices) < 30:
                return None
            return pd.Series(prices)
        except Exception as e:
            logger.error(f"Forex error {symbol}: {e}")
            return None

    def _fetch_stooq(self, symbol: str) -> pd.Series | None:
        try:
            url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            if df.empty or "Close" not in df.columns:
                return None
            return pd.Series(df["Close"].values[-100:])
        except Exception as e:
            logger.error(f"Stooq error {symbol}: {e}")
            return None

    def _compute_indicators(self, close: pd.Series) -> Dict[str, Any]:
        ind = {}
        ind["rsi"] = self._rsi(close, 14)

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        m, s = float(macd_line.iloc[-1]), float(signal_line.iloc[-1])
        if m > s:
            ind["macd_signal"] = "صاعد 🟢"; ind["macd_score"] = 1
        elif m < s:
            ind["macd_signal"] = "هابط 🔴"; ind["macd_score"] = -1
        else:
            ind["macd_signal"] = "محايد 🟡"; ind["macd_score"] = 0

        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_b = sma20 + 2 * std20
        lower_b = sma20 - 2 * std20
        price = float(close.iloc[-1])
        u, l, mid = float(upper_b.iloc[-1]), float(lower_b.iloc[-1]), float(sma20.iloc[-1])
        if price >= u:
            ind["bb_position"] = "فوق الحد العلوي 🔴"; ind["bb_score"] = -1
        elif price <= l:
            ind["bb_position"] = "تحت الحد السفلي 🟢"; ind["bb_score"] = 1
        elif price > mid:
            ind["bb_position"] = "أعلى المتوسط 🟡"; ind["bb_score"] = 0.5
        else:
            ind["bb_position"] = "أسفل المتوسط 🟡"; ind["bb_score"] = -0.5

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

        prev_e9, prev_e21 = float(ema9.iloc[-2]), float(ema21.iloc[-2])
        if prev_e9 <= prev_e21 and e9 > e21:
            ind["ema_cross"] = "تقاطع صاعد 🟢"; ind["cross_score"] = 2
        elif prev_e9 >= prev_e21 and e9 < e21:
            ind["ema_cross"] = "تقاطع هابط 🔴"; ind["cross_score"] = -2
        else:
            ind["ema_cross"] = "لا يوجد تقاطع 🟡"; ind["cross_score"] = 0

        return ind

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return float((100 - (100 / (1 + rs))).iloc[-1])

    def _generate_signal(self, ind: Dict) -> tuple:
        score = 0.0
        rsi = ind.get("rsi", 50)
        if rsi < 30:   score += 2
        elif rsi > 70: score -= 2
        elif rsi < 45: score += 0.5
        elif rsi > 55: score -= 0.5
        score += ind.get("macd_score", 0)
        score += ind.get("bb_score", 0)
        score += ind.get("trend_score", 0)
        score += ind.get("cross_score", 0)
        confidence = min(int(abs(score) / 7.0 * 100), 98)
        if score >= 2:    return "BUY",  max(confidence, 55)
        elif score <= -2: return "SELL", max(confidence, 55)
        else:             return "WAIT", confidence
