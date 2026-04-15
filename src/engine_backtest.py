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
    def __init__(self, symbols=None, days=90):
        self.symbols = symbols if symbols else config.SYMBOLS
        self.days = days
        self.exchange = ccxt.okx({'enableRateLimit': True})
        self.signal_engine = SignalEngine()

        # State
        self.positions = {}
        self.cooldown_symbols = {}

        # Performance Tracking
        self.initial_balance = config.BASE_CAPITAL
        self.current_balance = config.BASE_CAPITAL
        self.max_balance = config.BASE_CAPITAL
        self.max_drawdown = 0.0
        self.max_margin_usage = 0.0
        self.trades = []

        # Data Cache
        self.data_frames = {}

    def fetch_historical_data(self, symbol):
        data_path = f"data/{symbol.replace('/', '_')}_{self.days}d_{config.TIMEFRAME}.csv"

        if os.path.exists(data_path):
            logger.info(f"Loading cached data from {data_path}")
            df = pd.read_csv(data_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df

        logger.info(f"Fetching {self.days} days of data for {symbol}...")
        end_time = self.exchange.milliseconds()
        start_time = end_time - (self.days * 24 * 60 * 60 * 1000)

        all_ohlcv = []
        current_time = start_time

        while current_time < end_time:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, config.TIMEFRAME, since=current_time, limit=100)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                current_time = ohlcv[-1][0] + 1
                time.sleep(0.5) # Rate limit
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                break

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.drop_duplicates(subset=['timestamp'], inplace=True)

        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        df.to_csv(data_path, index=False)
        return df

    def get_avg_price(self, symbol):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0
        return pos['cost_usdt'] / pos['amount']

    def execute_buy(self, symbol, amount_usdt, price, timestamp, tier):
        amount = amount_usdt / price
        fee = amount_usdt * config.FEE_RATE

        if symbol not in self.positions:
            self.positions[symbol] = {'tier': 0, 'amount': 0.0, 'cost_usdt': 0.0, 'fees_usdt': 0.0}

        pos = self.positions[symbol]
        pos['tier'] = tier
        pos['amount'] += amount
        pos['cost_usdt'] += amount_usdt
        pos['fees_usdt'] += fee

        # Calculate current margin usage across all positions
        current_margin = sum(p['cost_usdt'] for p in self.positions.values())
        if current_margin > self.max_margin_usage:
            self.max_margin_usage = current_margin

        self.current_balance -= (amount_usdt + fee)

        self.trades.append({
            'time': timestamp, 'symbol': symbol, 'type': 'buy', 'tier': tier,
            'price': price, 'amount': amount, 'cost': amount_usdt, 'fee': fee
        })

    def close_position(self, symbol, price, timestamp, is_tp=True):
        pos = self.positions.get(symbol)
        if not pos: return

        revenue = pos['amount'] * price
        fee = revenue * config.FEE_RATE
        net_revenue = revenue - fee

        pnl = net_revenue - pos['cost_usdt'] - pos['fees_usdt']
        self.current_balance += net_revenue

        if self.current_balance > self.max_balance:
            self.max_balance = self.current_balance
        drawdown = (self.max_balance - self.current_balance) / self.max_balance
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        self.trades.append({
            'time': timestamp, 'symbol': symbol, 'type': 'sell', 'reason': 'TP' if is_tp else 'SL',
            'price': price, 'amount': pos['amount'], 'revenue': revenue, 'fee': fee, 'pnl': pnl
        })

        del self.positions[symbol]

        if not is_tp:
            self.cooldown_symbols[symbol] = True

    def calculate_pnl(self, symbol, current_price):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0
        current_value = pos['amount'] * current_price
        estimated_exit_fee = current_value * config.FEE_RATE
        net_pnl = current_value - pos['cost_usdt'] - pos['fees_usdt'] - estimated_exit_fee
        return net_pnl

    def run(self):
        logger.info("Loading data and calculating indicators for all symbols...")
        # Dictionary to store indicators pre-calculated for speed
        indicators = {}
        min_len = float('inf')

        for symbol in self.symbols:
            df = self.fetch_historical_data(symbol)
            if not df.empty:
                df = self.signal_engine.calculate_indicators(df)
                # align everything by timestamp index
                df.set_index('timestamp', inplace=True)
                indicators[symbol] = df
                if len(df) < min_len:
                    min_len = len(df)

        if not indicators:
            logger.error("No data available to backtest.")
            return

        # Find common timestamps
        common_timestamps = pd.Series(list(indicators.values())[0].index)
        for df in indicators.values():
            common_timestamps = common_timestamps[common_timestamps.isin(df.index)]

        common_timestamps = common_timestamps.sort_values().reset_index(drop=True)

        logger.info("Starting Multi-Asset Simulation...")
        # Start from index 20
        for i in range(20, len(common_timestamps)):
            timestamp = common_timestamps.iloc[i]

            # 1. Cooldown Check
            symbols_to_remove_cooldown = []
            for symbol in self.cooldown_symbols.keys():
                df_slice = indicators[symbol].loc[:timestamp]
                if self.signal_engine.evaluate_cooldown(df_slice):
                    symbols_to_remove_cooldown.append(symbol)
            for symbol in symbols_to_remove_cooldown:
                del self.cooldown_symbols[symbol]

            # 2. Position Management
            for symbol in list(self.positions.keys()):
                row = indicators[symbol].loc[timestamp]
                current_price = row['close']

                # Check SL using Low
                sl_pnl = self.calculate_pnl(symbol, row['low'])
                if sl_pnl <= config.SL_MAX_LOSS:
                    exec_price = row['low'] * 0.9995 # slippage
                    self.close_position(symbol, exec_price, timestamp, is_tp=False)
                    continue

                # Check TP using High
                tp_pnl = self.calculate_pnl(symbol, row['high'])
                if tp_pnl >= config.TP_NET_PROFIT:
                    exec_price = row['high'] * 0.9995 # slippage
                    self.close_position(symbol, exec_price, timestamp, is_tp=True)
                    continue

                # Check Tiers using Close
                pos = self.positions.get(symbol)
                if pos: # Might have been closed above
                    avg_price = self.get_avg_price(symbol)
                    df_slice = indicators[symbol].loc[:timestamp]

                    if pos['tier'] == 1:
                        if self.signal_engine.check_tier_2_signal(current_price, avg_price, config.TIER_2_DROP_PCT, df_slice):
                            exec_price = current_price * 1.0005
                            self.execute_buy(symbol, config.TIER_2_AMOUNT, exec_price, timestamp, 2)
                    elif pos['tier'] == 2:
                        if self.signal_engine.check_tier_3_signal(current_price, avg_price, config.TIER_3_DROP_PCT):
                            exec_price = current_price * 1.0005
                            self.execute_buy(symbol, config.TIER_3_AMOUNT, exec_price, timestamp, 3)

            # 3. Scanning Phase
            if len(self.positions) < config.MAX_ACTIVE_TRADES:
                for symbol in self.symbols:
                    if symbol in self.positions or symbol in self.cooldown_symbols:
                        continue

                    df_slice = indicators[symbol].loc[:timestamp]
                    current_price = indicators[symbol].loc[timestamp]['close']

                    if self.signal_engine.check_tier_1_signal(symbol, df_slice):
                        exec_price = current_price * 1.0005
                        self.execute_buy(symbol, config.TIER_1_AMOUNT, exec_price, timestamp, 1)

                        if len(self.positions) >= config.MAX_ACTIVE_TRADES:
                            break

        self.print_report()

    def print_report(self):
        sell_trades = [t for t in self.trades if t['type'] == 'sell']
        wins = [t for t in sell_trades if t['pnl'] > 0]
        losses = [t for t in sell_trades if t['pnl'] <= 0]

        win_rate = (len(wins) / len(sell_trades)) * 100 if sell_trades else 0
        total_pnl = sum(t['pnl'] for t in sell_trades)

        print("\n" + "="*40)
        print("📊 BACKTEST PERFORMANCE REPORT (MULTI-ASSET MICRO DCA)")
        print("="*40)
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Timeframe: {config.TIMEFRAME}")
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=90)
    args = parser.parse_args()
    engine = BacktestEngine(days=args.days)
    engine.run()
