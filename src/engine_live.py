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

        # State Management
        self.active_symbol = None
        self.tier = 0
        self.total_amount = 0.0
        self.total_cost_usdt = 0.0
        self.total_fees_usdt = 0.0
        self.cooldown = False

    def get_avg_price(self):
        if self.total_amount == 0:
            return 0.0
        return self.total_cost_usdt / self.total_amount

    def clear_position(self):
        self.active_symbol = None
        self.tier = 0
        self.total_amount = 0.0
        self.total_cost_usdt = 0.0
        self.total_fees_usdt = 0.0

    def calculate_pnl(self, current_price):
        if self.total_amount == 0:
            return 0.0
        current_value = self.total_amount * current_price
        # Net PnL = Current Value - Total Cost - Total Fees incurred so far - Estimated exit fee
        estimated_exit_fee = current_value * config.FEE_RATE
        net_pnl = current_value - self.total_cost_usdt - self.total_fees_usdt - estimated_exit_fee
        return net_pnl

    def execute_buy(self, symbol, amount_usdt, tier_level):
        order = self.broker.create_market_buy_order(symbol, amount_usdt)
        if order:
            self.tier = tier_level
            self.total_amount += order['amount']
            self.total_cost_usdt += order['cost_usdt']
            self.total_fees_usdt += order['fee_usdt']
            self.active_symbol = symbol

            self.notifier.notify_trade(symbol, tier_level, order['amount'], order['price'])
            logger.info(f"Bought {symbol} Tier {tier_level} at {order['price']}. Amount: {order['amount']}")
            return True
        else:
            self.notifier.notify_error(f"Failed to execute buy for {symbol} Tier {tier_level}")
            return False

    def close_position(self, pnl, is_tp=True):
        order = self.broker.create_market_sell_order(self.active_symbol, self.total_amount)
        if order:
            if is_tp:
                self.notifier.notify_tp(self.active_symbol, pnl)
                logger.info(f"TP closed for {self.active_symbol}. PnL: {pnl}")
            else:
                self.cooldown = True
                self.notifier.notify_sl(self.active_symbol, pnl)
                logger.info(f"SL closed for {self.active_symbol}. PnL: {pnl}. Entering Cooldown.")

            self.clear_position()
        else:
            self.notifier.notify_error(f"Failed to close position for {self.active_symbol}")

    def fetch_data_df(self, symbol):
        ohlcv = self.broker.fetch_ohlcv(symbol, limit=100)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def run_cycle(self):
        if self.cooldown:
            # When in cooldown, we monitor the previous active symbol or the first symbol to see if market stabilized
            symbol_to_check = self.active_symbol if self.active_symbol else config.SYMBOLS[0]
            df = self.fetch_data_df(symbol_to_check)
            df = self.signal_engine.calculate_indicators(df)
            if self.signal_engine.evaluate_cooldown(df):
                logger.info("Cooldown ended. Market stabilized.")
                self.cooldown = False
                self.active_symbol = None
            else:
                logger.info("Market still in cooldown. Waiting...")
            return

        if self.active_symbol is None:
            # Scanning phase
            for symbol in config.SYMBOLS:
                df = self.fetch_data_df(symbol)
                df = self.signal_engine.calculate_indicators(df)

                if self.signal_engine.check_tier_1_signal(df):
                    logger.info(f"Tier 1 signal detected for {symbol}")
                    self.execute_buy(symbol, config.TIER_1_AMOUNT, 1)
                    break # Stop scanning, we have an active trade (MAX_ACTIVE_TRADES = 1)
        else:
            # Management phase
            symbol = self.active_symbol
            current_price = self.broker.get_ticker(symbol)
            if not current_price:
                return

            net_pnl = self.calculate_pnl(current_price)
            avg_price = self.get_avg_price()

            logger.info(f"Managing {symbol} | Tier: {self.tier} | PnL: {net_pnl:.4f} | Price: {current_price}")

            # Check TP/SL
            if net_pnl >= config.TP_NET_PROFIT:
                self.close_position(net_pnl, is_tp=True)
                return
            elif net_pnl <= config.SL_MAX_LOSS:
                self.close_position(net_pnl, is_tp=False)
                return

            # Check for Tier 2 / Tier 3
            df = self.fetch_data_df(symbol)
            df = self.signal_engine.calculate_indicators(df)

            if self.tier == 1:
                if self.signal_engine.check_tier_2_signal(current_price, avg_price, config.TIER_2_DROP_PCT, df):
                    logger.info(f"Tier 2 signal detected for {symbol}")
                    self.execute_buy(symbol, config.TIER_2_AMOUNT, 2)
            elif self.tier == 2:
                if self.signal_engine.check_tier_3_signal(current_price, avg_price, config.TIER_3_DROP_PCT):
                    logger.info(f"Tier 3 signal detected for {symbol}")
                    self.execute_buy(symbol, config.TIER_3_AMOUNT, 3)

    def start(self, poll_interval=60):
        logger.info("Starting Live Engine...")
        self.notifier.send_message("🟢 <b>Bot Started (Live Mode)</b>")
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Error in run cycle: {e}")
                self.notifier.notify_error(str(e))
            time.sleep(poll_interval)
