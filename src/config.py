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

    # --- Compound Interest (Reinvesting Profits) ---
    COMPOUND_MODE = True
    # If True, TIER_MARGIN will be calculated as: current_balance * TIER_MARGIN_PCT
    # Optimized for higher return (450U target): 15% of account per tier.
    # High risk, high reward profile.
    TIER_MARGIN_PCT = 0.15

    # Capital allocation per tier (USDT Margin) [Used only if COMPOUND_MODE is False]
    TIER_1_MARGIN = 10.0
    TIER_2_MARGIN = 10.0
    TIER_3_MARGIN = 10.0

    # Trigger conditions (price deviation % from average entry price)
    TIER_2_DEV_PCT = 0.015  # 1.5% adverse move
    TIER_3_DEV_PCT = 0.030  # 3.0% adverse move

    # Take Profit & Stop Loss
    # If COMPOUND_MODE is True, we target a percentage ROI on the invested margin
    # TP = 30% return on margin to hit higher profit targets. SL = 100% loss of margin
    TP_MARGIN_ROI = 0.30
    SL_MARGIN_ROI = -1.0

    # --- Absolute Safety Net ---
    # In COMPOUND_MODE, a 100% margin loss can be devastating when balance is huge.
    # This caps the maximum loss of a single position to X% of the TOTAL current account balance.
    # Relaxed to 20% to prevent premature stop outs during the wider swings, aiding the 450U target.
    SL_GLOBAL_CAP_PCT = -0.20

    # Fixed absolute USDT targets [Used only if COMPOUND_MODE is False]
    TP_NET_PROFIT = 1.5
    SL_MAX_LOSS = -10.0

    # Technical Indicator Parameters
    RSI_LONG_ENTRY = 30
    RSI_SHORT_ENTRY = 70
    TREND_SMA_LENGTH = 200

    # Binance Futures Fee Rate (Maker 0.02%, Taker 0.05%. We use 0.05% for market orders)
    FEE_RATE = 0.0005

    # Timeframes
    TIMEFRAME = '5m'

config = Config()
