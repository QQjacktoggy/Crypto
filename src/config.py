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
    MAX_ACTIVE_TRADES = 5  # Allow up to 5 concurrent trades

    # Futures configurations
    LEVERAGE = 5
    MARGIN_MODE = 'isolated'

    # Target symbols for Binance USDT-M Futures (CCXT syntax for linear futures)
    SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'DOGE/USDT:USDT', 'XRP/USDT:USDT']

    # --- Compound Interest (Reinvesting Profits) ---
    COMPOUND_MODE = True
    TIER_MARGIN_PCT = 0.055  # ~5.5% per tier; 5 positions * 3 tiers * 5.5% = 82.5% max, ~17.5% buffer

    # Capital allocation per tier (USDT Margin) [Used only if COMPOUND_MODE is False]
    TIER_1_MARGIN = 10.0
    TIER_2_MARGIN = 10.0
    TIER_3_MARGIN = 10.0

    # Trigger conditions (price deviation % from average entry price)
    TIER_2_DEV_PCT = 0.012  # 1.2% adverse move (tighter DCA)
    TIER_3_DEV_PCT = 0.025  # 2.5% adverse move

    # Take Profit & Stop Loss
    TP_MARGIN_ROI = 0.15    # 15% return on margin
    SL_MARGIN_ROI = -0.50   # 50% margin loss

    # --- Trailing Take-Profit ---
    TRAILING_TP_ACTIVATE_ROI = 0.12  # Activate trailing TP after 12% ROI
    TRAILING_TP_CALLBACK_ROI = 0.04  # Trail 4% behind peak

    # --- Absolute Safety Net ---
    SL_GLOBAL_CAP_PCT = -0.08  # 8% of total account

    # Fixed absolute USDT targets [Used only if COMPOUND_MODE is False]
    TP_NET_PROFIT = 1.5
    SL_MAX_LOSS = -10.0

    # Technical Indicator Parameters
    RSI_LONG_ENTRY = 32     # Widened from 25 to capture more opportunities
    RSI_SHORT_ENTRY = 68    # Widened from 75 to capture more opportunities
    TREND_SMA_LENGTH = 200

    # --- MACD Strategy Parameters ---
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9

    # --- EMA Crossover Strategy Parameters ---
    EMA_FAST = 9
    EMA_SLOW = 21

    # --- Funding Rate Simulation ---
    FUNDING_RATE = 0.0001   # 0.01% every 8 hours (realistic average)
    FUNDING_INTERVAL_HOURS = 8

    # Binance Futures Fee Rate (Maker 0.02%, Taker 0.05%. We use 0.05% for market orders)
    FEE_RATE = 0.0005

    # --- Signal Strategy Mode ---
    # 'classic': RSI + Bollinger Bands only (original, high win-rate)
    # 'multi': RSI+BB, MACD, EMA crossover (more trades, potentially more risk)
    SIGNAL_MODE = 'classic'

    # --- Cooldown Settings ---
    COOLDOWN_CANDLES = 12   # Minimum candles (1 hour) before re-entry after SL
    MAX_CONSECUTIVE_LOSSES = 3  # Pause symbol after 3 consecutive losses

    # --- Dynamic ATR-based TP/SL ---
    DYNAMIC_TPSL = False         # Use ATR-based dynamic TP/SL instead of fixed ROI
    ATR_TP_MULT = 2.0            # TP = ATR * multiplier (as price distance)
    ATR_SL_MULT = 1.5            # SL = ATR * multiplier (as price distance)
    ATR_TP_MIN_ROI = 0.08        # Minimum TP ROI floor (8%)
    ATR_TP_MAX_ROI = 0.40        # Maximum TP ROI cap (40%)
    ATR_SL_MIN_ROI = -0.15       # Minimum SL ROI floor (-15%)
    ATR_SL_MAX_ROI = -0.70       # Maximum SL ROI cap (-70%)

    # Timeframes
    TIMEFRAME = '5m'

config = Config()
