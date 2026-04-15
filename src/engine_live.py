import time
import logging
import pandas as pd
from src.config import config
from src.broker_ccxt import Broker
from src.signal_logic import SignalEngine
from src.notifier import TelegramNotifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LiveEngine:
    def __init__(self, use_testnet=False):
        self.broker = Broker(use_testnet=use_testnet)
        self.signal_engine = SignalEngine()
        self.notifier = TelegramNotifier()

        # State Management: Multiple active positions
        # format: { 'BTC/USDT': {'tier': 1, 'direction': 'long', 'amount': 0.1, 'margin_usdt': 10.0, 'notional_usdt': 50.0, 'fees_usdt': 0.05} }
        self.positions = {}
        # Cooldown state: format: {'BTC/USDT': 'long'}
        self.cooldown_symbols = {}

    def get_avg_price(self, symbol):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0
        return pos['notional_usdt'] / pos['amount']

    def clear_position(self, symbol):
        if symbol in self.positions:
            del self.positions[symbol]

    def calculate_pnl(self, symbol, current_price):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0

        current_notional = pos['amount'] * current_price
        estimated_exit_fee = current_notional * config.FEE_RATE

        if pos['direction'] == 'long':
            gross_pnl = current_notional - pos['notional_usdt']
        else:
            gross_pnl = pos['notional_usdt'] - current_notional

        net_pnl = gross_pnl - pos['fees_usdt'] - estimated_exit_fee
        return net_pnl

    def execute_order(self, symbol, margin_usdt, tier_level, direction):
        side = 'buy' if direction == 'long' else 'sell'

        order = self.broker.execute_futures_order(symbol, margin_usdt, side, side.upper())
        if order:
            if symbol not in self.positions:
                self.positions[symbol] = {
                    'tier': 0, 'direction': direction, 'amount': 0.0,
                    'margin_usdt': 0.0, 'notional_usdt': 0.0, 'fees_usdt': 0.0
                }

            pos = self.positions[symbol]
            pos['tier'] = tier_level
            pos['amount'] += order['amount']
            pos['margin_usdt'] += order['margin_used']
            pos['notional_usdt'] += order['notional_value']
            pos['fees_usdt'] += order['fee_usdt']

            dir_str = "LONG" if direction == "long" else "SHORT"
            self.notifier.notify_trade(symbol, tier_level, order['amount'], order['price'])
            logger.info(f"Opened {dir_str} on {symbol} Tier {tier_level} at {order['price']}. Amount: {order['amount']}")
            return True
        else:
            self.notifier.notify_error(f"Failed to execute {direction} order for {symbol} Tier {tier_level}")
            return False

    def close_position(self, symbol, pnl, is_tp=True):
        pos = self.positions.get(symbol)
        if not pos:
            return

        close_side = 'sell' if pos['direction'] == 'long' else 'buy'
        order = self.broker.execute_close_futures_position(symbol, pos['amount'], close_side)

        if order:
            if is_tp:
                self.notifier.notify_tp(symbol, pnl)
                logger.info(f"TP closed for {symbol}. PnL: {pnl}")
            else:
                self.cooldown_symbols[symbol] = pos['direction'] # Cooldown same direction
                self.notifier.notify_sl(symbol, pnl)
                logger.info(f"SL closed for {symbol}. PnL: {pnl}. Entering Cooldown.")

            self.clear_position(symbol)
        else:
            self.notifier.notify_error(f"Failed to close position for {symbol}")

    def fetch_data_df(self, symbol):
        ohlcv = self.broker.fetch_ohlcv(symbol, timeframe=config.TIMEFRAME, limit=100)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def run_cycle(self):
        # 1. Manage Cooldowns
        symbols_to_remove_cooldown = []
        for symbol, direction in self.cooldown_symbols.items():
            df = self.fetch_data_df(symbol)
            df = self.signal_engine.calculate_indicators(df)
            if self.signal_engine.evaluate_cooldown(df, direction):
                logger.info(f"Cooldown ended for {symbol} ({direction}). Market stabilized.")
                symbols_to_remove_cooldown.append(symbol)
            else:
                logger.info(f"Market still in cooldown for {symbol} ({direction}). Waiting...")

        for symbol in symbols_to_remove_cooldown:
            del self.cooldown_symbols[symbol]

        current_balance = self.broker.get_balance()
        if current_balance <= 0:
            current_balance = config.BASE_CAPITAL # fallback

        def get_dynamic_margin():
            if config.COMPOUND_MODE:
                return current_balance * config.TIER_MARGIN_PCT
            return config.TIER_1_MARGIN

        # 2. Manage Active Positions
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            current_price = self.broker.get_ticker(symbol)
            if not current_price:
                continue

            net_pnl = self.calculate_pnl(symbol, current_price)
            avg_price = self.get_avg_price(symbol)

            logger.info(f"Managing {symbol} ({pos['direction']}) | Tier: {pos['tier']} | PnL: {net_pnl:.4f} | Price: {current_price}")

            # Check TP/SL
            if config.COMPOUND_MODE:
                target_tp = pos['margin_usdt'] * config.TP_MARGIN_ROI
                # Max loss is either 100% of margin, or the global cap percentage of the total balance, whichever is less damaging (closer to zero).
                margin_sl = pos['margin_usdt'] * config.SL_MARGIN_ROI
                global_cap_sl = current_balance * config.SL_GLOBAL_CAP_PCT
                target_sl = max(margin_sl, global_cap_sl)
            else:
                target_tp = config.TP_NET_PROFIT
                target_sl = config.SL_MAX_LOSS

            if net_pnl >= target_tp:
                self.close_position(symbol, net_pnl, is_tp=True)
                continue
            elif net_pnl <= target_sl:
                self.close_position(symbol, net_pnl, is_tp=False)
                continue

            # Check for Tier 2 / Tier 3
            df = self.fetch_data_df(symbol)
            df = self.signal_engine.calculate_indicators(df)

            margin_to_use = get_dynamic_margin()

            if pos['tier'] == 1:
                if self.signal_engine.check_tier_2_signal(current_price, avg_price, config.TIER_2_DEV_PCT, pos['direction'], df):
                    logger.info(f"Tier 2 {pos['direction']} signal detected for {symbol}")
                    self.execute_order(symbol, margin_to_use, 2, pos['direction'])
            elif pos['tier'] == 2:
                if self.signal_engine.check_tier_3_signal(current_price, avg_price, config.TIER_3_DEV_PCT, pos['direction']):
                    logger.info(f"Tier 3 {pos['direction']} signal detected for {symbol}")
                    self.execute_order(symbol, margin_to_use, 3, pos['direction'])

        # 3. Scanning for New Positions
        if len(self.positions) < config.MAX_ACTIVE_TRADES:
            margin_to_use = get_dynamic_margin()
            for symbol in config.SYMBOLS:
                if symbol in self.positions or symbol in self.cooldown_symbols:
                    continue # Skip already active or cooldown symbols

                df = self.fetch_data_df(symbol)
                df = self.signal_engine.calculate_indicators(df)

                if self.signal_engine.check_tier_1_long_signal(symbol, df):
                    logger.info(f"Tier 1 LONG signal detected for {symbol}")
                    self.execute_order(symbol, margin_to_use, 1, 'long')
                elif self.signal_engine.check_tier_1_short_signal(symbol, df):
                    logger.info(f"Tier 1 SHORT signal detected for {symbol}")
                    self.execute_order(symbol, margin_to_use, 1, 'short')

                if len(self.positions) >= config.MAX_ACTIVE_TRADES:
                    break # Reached max concurrent trades

    def start(self, poll_interval=60):
        logger.info("Starting Live Engine (Multi-Asset)...")
        self.notifier.send_message(f"🟢 <b>Bot Started (Live Mode)</b>\nMax Concurrent Trades: {config.MAX_ACTIVE_TRADES}")
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Error in run cycle: {e}")
                self.notifier.notify_error(str(e))
            time.sleep(poll_interval)
