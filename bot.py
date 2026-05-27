import os
import asyncio
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "BTCUSDT":"bitcoin","ETHUSDT":"ethereum","BNBUSDT":"binancecoin",
    "SOLUSDT":"solana","XRPUSDT":"ripple","DOGEUSDT":"dogecoin",
    "ADAUSDT":"cardano","LTCUSDT":"litecoin","MATICUSDT":"matic-network",
}
FOREX_PAIRS = {"EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","NZDUSD","USDCHF","EURGBP","EURJPY","GBPJPY"}

def fetch_data(symbol):
    upper = symbol.upper().replace("/","").replace("-","")
    if upper in COINGECKO_IDS:
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/{COINGECKO_IDS[upper]}/market_chart",params={"vs_currency":"usd","days":"1","interval":"hourly"},timeout=15)
        r.raise_for_status()
        return pd.Series([p[1] for p in r.json()["prices"]])
    elif upper in FOREX_PAIRS:
        base,quote = upper[:3],upper[3:]
        r = requests.get(f"https://api.frankfurter.app/2024-01-01..?
