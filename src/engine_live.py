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
        # format: { 'BTC/USDT': {'tier': 1, 'amount': 0.1, 'cost_usdt': 20.0, 'fees_usdt': 0.05, 'cooldown': False} }
        self.positions = {}
        # Cooldown state per symbol
        self.cooldown_symbols = {}

    def get_avg_price(self, symbol):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0
        return pos['cost_usdt'] / pos['amount']

    def clear_position(self, symbol):
        if symbol in self.positions:
            del self.positions[symbol]

    def calculate_pnl(self, symbol, current_price):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0
        current_value = pos['amount'] * current_price
        estimated_exit_fee = current_value * config.FEE_RATE
        net_pnl = current_value - pos['cost_usdt'] - pos['fees_usdt'] - estimated_exit_fee
        return net_pnl

    def execute_buy(self, symbol, amount_usdt, tier_level):
        order = self.broker.create_market_buy_order(symbol, amount_usdt)
        if order:
            if symbol not in self.positions:
                self.positions[symbol] = {'tier': 0, 'amount': 0.0, 'cost_usdt': 0.0, 'fees_usdt': 0.0}

            pos = self.positions[symbol]
            pos['tier'] = tier_level
            pos['amount'] += order['amount']
            pos['cost_usdt'] += order['cost_usdt']
            pos['fees_usdt'] += order['fee_usdt']

            self.notifier.notify_trade(symbol, tier_level, order['amount'], order['price'])
            logger.info(f"Bought {symbol} Tier {tier_level} at {order['price']}. Amount: {order['amount']}")
            return True
        else:
            self.notifier.notify_error(f"Failed to execute buy for {symbol} Tier {tier_level}")
            return False

    def close_position(self, symbol, pnl, is_tp=True):
        pos = self.positions.get(symbol)
        if not pos:
            return

        order = self.broker.create_market_sell_order(symbol, pos['amount'])
        if order:
            if is_tp:
                self.notifier.notify_tp(symbol, pnl)
                logger.info(f"TP closed for {symbol}. PnL: {pnl}")
            else:
                self.cooldown_symbols[symbol] = True
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
        for symbol in self.cooldown_symbols.keys():
            df = self.fetch_data_df(symbol)
            df = self.signal_engine.calculate_indicators(df)
            if self.signal_engine.evaluate_cooldown(df):
                logger.info(f"Cooldown ended for {symbol}. Market stabilized.")
                symbols_to_remove_cooldown.append(symbol)
            else:
                logger.info(f"Market still in cooldown for {symbol}. Waiting...")

        for symbol in symbols_to_remove_cooldown:
            del self.cooldown_symbols[symbol]

        # 2. Manage Active Positions
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            current_price = self.broker.get_ticker(symbol)
            if not current_price:
                continue

            net_pnl = self.calculate_pnl(symbol, current_price)
            avg_price = self.get_avg_price(symbol)

            logger.info(f"Managing {symbol} | Tier: {pos['tier']} | PnL: {net_pnl:.4f} | Price: {current_price}")

            # Check TP/SL
            if net_pnl >= config.TP_NET_PROFIT:
                self.close_position(symbol, net_pnl, is_tp=True)
                continue
            elif net_pnl <= config.SL_MAX_LOSS:
                self.close_position(symbol, net_pnl, is_tp=False)
                continue

            # Check for Tier 2 / Tier 3
            df = self.fetch_data_df(symbol)
            df = self.signal_engine.calculate_indicators(df)

            if pos['tier'] == 1:
                if self.signal_engine.check_tier_2_signal(current_price, avg_price, config.TIER_2_DROP_PCT, df):
                    logger.info(f"Tier 2 signal detected for {symbol}")
                    self.execute_buy(symbol, config.TIER_2_AMOUNT, 2)
            elif pos['tier'] == 2:
                if self.signal_engine.check_tier_3_signal(current_price, avg_price, config.TIER_3_DROP_PCT):
                    logger.info(f"Tier 3 signal detected for {symbol}")
                    self.execute_buy(symbol, config.TIER_3_AMOUNT, 3)

        # 3. Scanning for New Positions
        if len(self.positions) < config.MAX_ACTIVE_TRADES:
            for symbol in config.SYMBOLS:
                if symbol in self.positions or symbol in self.cooldown_symbols:
                    continue # Skip already active or cooldown symbols

                df = self.fetch_data_df(symbol)
                df = self.signal_engine.calculate_indicators(df)

                if self.signal_engine.check_tier_1_signal(symbol, df):
                    logger.info(f"Tier 1 signal detected for {symbol}")
                    self.execute_buy(symbol, config.TIER_1_AMOUNT, 1)

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
