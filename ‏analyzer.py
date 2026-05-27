import pandas as pd
import numpy as np
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
}

FOREX_PAIRS = {"EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","NZDUSD","USDCHF","EURGBP","EURJPY","GBPJPY"}

class MarketAnalyzer:
    def analyze(self, symbol):
        result = {"symbol":symbol,"price":0.0,"signal":"WAIT","confidence":0,"indicators":{},"error":None}
        try:
            upper = symbol.upper().replace("/","").replace("-","")
            if upper in COINGECKO_IDS:
                close = self._fetch_coingecko(upper)
            elif upper in FOREX_PAIRS:
                close = self._fetch_forex(upper)
            else:
                close = self._fetch_stooq(upper)
            if close is None or len(close) < 30:
                result["error"] = f"لا توجد بيانات للرمز '{symbol}'. جرب: BTCUSDT او EURUSD او AAPL"
                return result
            result["price"] = float(close.iloc[-1])
            ind = self._compute_indicators(close)
            result["indicators"] = ind
            result["signal"], result["confidence"] = self._generate_signal(ind)
        except Exception as e:
            result["error"] = f"خطأ: {str(e)}"
        return result

    def _fetch_coingecko(self, symbol):
        coin_id = COINGECKO_IDS[symbol]
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart", params={"vs_currency":"usd","days":"1","interval":"hourly"}, timeout=15)
        r.raise_for_status()
        return pd.Series
