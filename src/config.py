import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Exchange Settings ---
    # Binance Futures (USDT-M)
    EXCHANGE_ID = 'binance'
    API_KEY = os.getenv('API_KEY', '')
    API_SECRET = os.getenv('API_SECRET', '')

    # --- Telegram Settings ---
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    # --- AI Settings ---
    AI_API_URL = os.getenv('AI_API_URL', None)

    # --- Trading Parameters (Futures) ---
    BASE_CAPITAL = 150.0  # USDT
    MAX_ACTIVE_TRADES = 4 # Allow up to 4 concurrent trades

    # Futures configurations
    LEVERAGE = 5
    MARGIN_MODE = 'isolated' # Use isolated margin to protect account from total liquidation

    # Target symbols for Binance USDT-M Futures (CCXT syntax for linear futures)
    SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'DOGE/USDT:USDT', 'XRP/USDT:USDT']

    # Capital allocation per tier (USDT Margin, NOT position size)
    # Linear DCA: 10 USDT margin per tier. With 5x leverage, position size is 50 USDT per tier.
    TIER_1_MARGIN = 10.0
    TIER_2_MARGIN = 10.0
    TIER_3_MARGIN = 10.0

    # Trigger conditions (price deviation % from average entry price)
    # Since leverage is 5x, a 1.5% move in price = 7.5% move in PnL
    TIER_2_DEV_PCT = 0.015  # 1.5% adverse move
    TIER_3_DEV_PCT = 0.030  # 3.0% adverse move

    # Take Profit & Stop Loss
    # We aim for higher absolute profit per cycle due to leverage
    TP_NET_PROFIT = 1.5      # USDT net profit (Optimized target for 5x leverage)
    # Max loss per position: if tier 3 is hit (30U margin), a total loss of -10U is acceptable before cutting
    SL_MAX_LOSS = -10.0      # USDT per position

    # Technical Indicator Parameters
    RSI_LONG_ENTRY = 25
    RSI_SHORT_ENTRY = 75
    TREND_SMA_LENGTH = 200

    # Binance Futures Fee Rate (Maker 0.02%, Taker 0.05%. We use 0.05% for market orders)
    FEE_RATE = 0.0005

    # Timeframes
    TIMEFRAME = '5m'

config = Config()
