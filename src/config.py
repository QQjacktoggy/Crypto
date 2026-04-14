import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Exchange Settings ---
    # We will use cryptocom for live and binance for backtesting data
    EXCHANGE_ID = 'cryptocom'
    API_KEY = os.getenv('API_KEY', '')
    API_SECRET = os.getenv('API_SECRET', '')

    # --- Telegram Settings ---
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    # --- Trading Parameters ---
    BASE_CAPITAL = 150.0  # USDT
    MAX_ACTIVE_TRADES = 1 # Global lock

    # Target symbols for multi-asset scanning (Spot)
    SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'XRP/USDT']

    # Capital allocation per tier (USDT)
    TIER_1_AMOUNT = 20.0
    TIER_2_AMOUNT = 50.0
    TIER_3_AMOUNT = 80.0

    # Trigger conditions (price drop % from average entry price)
    TIER_2_DROP_PCT = -0.03  # -3%
    TIER_3_DROP_PCT = -0.07  # -7%

    # Take Profit & Stop Loss
    TP_NET_PROFIT = 1.0      # USDT (net profit after fees)
    SL_MAX_LOSS = -15.0      # USDT (10% of 150 USDT)

    # Exchange Fee Estimation (Maker/Taker roughly 0.075% for default tier, we use 0.1% to be safe)
    FEE_RATE = 0.001

    # Timeframes
    TIMEFRAME = '15m'

config = Config()
