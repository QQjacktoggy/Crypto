import ccxt
import pandas as pd
import time
import logging
import os
from src.config import config
from src.signal_logic import SignalEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, symbol='BTC/USDT', days=365):
        self.symbol = symbol
        self.days = days
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.signal_engine = SignalEngine()
        self.data_path = f"data/{symbol.replace('/', '_')}_{days}d_15m.csv"

        # State
        self.active_position = False
        self.tier = 0
        self.total_amount = 0.0
        self.total_cost_usdt = 0.0
        self.total_fees_usdt = 0.0
        self.cooldown = False

        # Performance Tracking
        self.initial_balance = config.BASE_CAPITAL
        self.current_balance = config.BASE_CAPITAL
        self.max_balance = config.BASE_CAPITAL
        self.max_drawdown = 0.0
        self.max_margin_usage = 0.0
        self.trades = []

    def fetch_historical_data(self):
        if os.path.exists(self.data_path):
            logger.info(f"Loading cached data from {self.data_path}")
            df = pd.read_csv(self.data_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df

        logger.info(f"Fetching {self.days} days of data for {self.symbol}...")
        end_time = self.exchange.milliseconds()
        start_time = end_time - (self.days * 24 * 60 * 60 * 1000)

        all_ohlcv = []
        current_time = start_time

        while current_time < end_time:
            try:
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, config.TIMEFRAME, since=current_time, limit=1000)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                current_time = ohlcv[-1][0] + 1
                time.sleep(0.5) # Rate limit
            except Exception as e:
                logger.error(f"Error fetching data: {e}")
                break

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.drop_duplicates(subset=['timestamp'], inplace=True)

        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        df.to_csv(self.data_path, index=False)
        return df

    def get_avg_price(self):
        if self.total_amount == 0:
            return 0.0
        return self.total_cost_usdt / self.total_amount

    def execute_buy(self, amount_usdt, price, timestamp, tier):
        amount = amount_usdt / price
        fee = amount_usdt * config.FEE_RATE

        self.tier = tier
        self.total_amount += amount
        self.total_cost_usdt += amount_usdt
        self.total_fees_usdt += fee
        self.active_position = True

        if self.total_cost_usdt > self.max_margin_usage:
            self.max_margin_usage = self.total_cost_usdt

        self.current_balance -= (amount_usdt + fee)

        self.trades.append({
            'time': timestamp, 'type': 'buy', 'tier': tier,
            'price': price, 'amount': amount, 'cost': amount_usdt, 'fee': fee
        })

    def close_position(self, price, timestamp, is_tp=True):
        revenue = self.total_amount * price
        fee = revenue * config.FEE_RATE
        net_revenue = revenue - fee

        # Calculate PnL for the trade
        pnl = net_revenue - self.total_cost_usdt - self.total_fees_usdt

        self.current_balance += net_revenue

        # Update Drawdown
        if self.current_balance > self.max_balance:
            self.max_balance = self.current_balance
        drawdown = (self.max_balance - self.current_balance) / self.max_balance
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        self.trades.append({
            'time': timestamp, 'type': 'sell', 'reason': 'TP' if is_tp else 'SL',
            'price': price, 'amount': self.total_amount, 'revenue': revenue, 'fee': fee, 'pnl': pnl
        })

        self.active_position = False
        self.tier = 0
        self.total_amount = 0.0
        self.total_cost_usdt = 0.0
        self.total_fees_usdt = 0.0

        if not is_tp:
            self.cooldown = True

    def calculate_pnl(self, current_price):
        if self.total_amount == 0:
            return 0.0
        current_value = self.total_amount * current_price
        estimated_exit_fee = current_value * config.FEE_RATE
        net_pnl = current_value - self.total_cost_usdt - self.total_fees_usdt - estimated_exit_fee
        return net_pnl

    def run(self):
        df = self.fetch_historical_data()
        if df.empty:
            logger.error("No data fetched.")
            return

        logger.info("Calculating indicators...")
        df = self.signal_engine.calculate_indicators(df)

        logger.info("Starting simulation...")
        # Start from index 20 to have enough data for indicators
        for i in range(20, len(df)):
            row = df.iloc[i]
            timestamp = row['timestamp']
            current_price = row['close']

            # Slice dataframe up to current point to simulate real-time state for indicators
            current_df = df.iloc[:i+1]

            if self.cooldown:
                if self.signal_engine.evaluate_cooldown(current_df):
                    self.cooldown = False
                continue

            if not self.active_position:
                if self.signal_engine.check_tier_1_signal(current_df):
                    # Simulate slippage on market order (+0.05%)
                    exec_price = current_price * 1.0005
                    self.execute_buy(config.TIER_1_AMOUNT, exec_price, timestamp, 1)
            else:
                # Intrabar Simulation Logic (using High/Low for TP/SL is more accurate, but here we use Close/Low for simplicity)
                # To be conservative, we check if the Low hits our SL or if High hits our TP
                avg_price = self.get_avg_price()

                # Check SL using Low
                sl_pnl = self.calculate_pnl(row['low'])
                if sl_pnl <= config.SL_MAX_LOSS:
                    exec_price = row['low'] * 0.9995 # slippage
                    self.close_position(exec_price, timestamp, is_tp=False)
                    continue

                # Check TP using High
                tp_pnl = self.calculate_pnl(row['high'])
                if tp_pnl >= config.TP_NET_PROFIT:
                    exec_price = row['high'] * 0.9995 # slippage
                    self.close_position(exec_price, timestamp, is_tp=True)
                    continue

                # Check for Tiers using Close
                if self.tier == 1:
                    if self.signal_engine.check_tier_2_signal(current_price, avg_price, config.TIER_2_DROP_PCT, current_df):
                        exec_price = current_price * 1.0005
                        self.execute_buy(config.TIER_2_AMOUNT, exec_price, timestamp, 2)
                elif self.tier == 2:
                    if self.signal_engine.check_tier_3_signal(current_price, avg_price, config.TIER_3_DROP_PCT):
                        exec_price = current_price * 1.0005
                        self.execute_buy(config.TIER_3_AMOUNT, exec_price, timestamp, 3)

        self.print_report()

    def print_report(self):
        sell_trades = [t for t in self.trades if t['type'] == 'sell']
        wins = [t for t in sell_trades if t['pnl'] > 0]
        losses = [t for t in sell_trades if t['pnl'] <= 0]

        win_rate = (len(wins) / len(sell_trades)) * 100 if sell_trades else 0
        total_pnl = sum(t['pnl'] for t in sell_trades)

        print("\n" + "="*40)
        print("📊 BACKTEST PERFORMANCE REPORT")
        print("="*40)
        print(f"Symbol: {self.symbol}")
        print(f"Initial Balance: {self.initial_balance} USDT")
        print(f"Final Balance: {self.current_balance:.2f} USDT")
        print(f"Total Net PnL: {total_pnl:.2f} USDT")
        print(f"Total Trades (Cycles): {len(sell_trades)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Max Drawdown (MDD): {self.max_drawdown*100:.2f}%")
        print(f"Max Margin Usage: {self.max_margin_usage:.2f} USDT")
        print("="*40)
        if self.max_margin_usage > self.initial_balance:
            print("⚠️ WARNING: Max margin usage exceeded initial balance. Account would have been liquidated!")
        else:
            print("✅ Margin safety passed.")
        print("="*40 + "\n")

if __name__ == "__main__":
    engine = BacktestEngine()
    engine.run()
