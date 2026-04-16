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

    def fetch_historical_data(self, symbol, timeframe=config.TIMEFRAME, limit_fetch_days=None):
        days_to_fetch = limit_fetch_days if limit_fetch_days else self.days
        data_path = f"data/{symbol.replace('/', '_')}_{days_to_fetch}d_{timeframe}.csv"

        if os.path.exists(data_path):
            logger.info(f"Loading cached data from {data_path}")
            df = pd.read_csv(data_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df

        logger.info(f"Fetching {days_to_fetch} days of data for {symbol} ({timeframe})...")
        end_time = self.exchange.milliseconds()
        start_time = end_time - (days_to_fetch * 24 * 60 * 60 * 1000)

        all_ohlcv = []
        current_time = start_time

        while current_time < end_time:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=current_time, limit=500)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                current_time = ohlcv[-1][0] + 1
                time.sleep(0.2) # Rate limit
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
        return pos['notional_usdt'] / pos['amount']

    def execute_order(self, symbol, margin_usdt, price, timestamp, tier, direction):
        position_value_usdt = margin_usdt * config.LEVERAGE
        amount = position_value_usdt / price
        fee = position_value_usdt * config.FEE_RATE

        if symbol not in self.positions:
            self.positions[symbol] = {
                'tier': 0, 'direction': direction, 'amount': 0.0,
                'margin_usdt': 0.0, 'notional_usdt': 0.0, 'fees_usdt': 0.0
            }

        pos = self.positions[symbol]
        pos['tier'] = tier
        pos['amount'] += amount
        pos['margin_usdt'] += margin_usdt
        pos['notional_usdt'] += position_value_usdt
        pos['fees_usdt'] += fee

        current_margin = sum(p['margin_usdt'] for p in self.positions.values())
        if current_margin > self.max_margin_usage:
            self.max_margin_usage = current_margin

        # Deduct margin and fee from balance
        self.current_balance -= (margin_usdt + fee)

        self.trades.append({
            'time': timestamp, 'symbol': symbol, 'type': 'open', 'tier': tier, 'direction': direction,
            'price': price, 'amount': amount, 'margin': margin_usdt, 'notional': position_value_usdt, 'fee': fee
        })

    def close_position(self, symbol, price, timestamp, is_tp=True):
        pos = self.positions.get(symbol)
        if not pos: return

        current_notional = pos['amount'] * price
        fee = current_notional * config.FEE_RATE

        if pos['direction'] == 'long':
            gross_pnl = current_notional - pos['notional_usdt']
        else:
            gross_pnl = pos['notional_usdt'] - current_notional

        pnl = gross_pnl - pos['fees_usdt'] - fee

        # Return margin + gross_pnl - exit_fee
        self.current_balance += (pos['margin_usdt'] + gross_pnl - fee)

        if self.current_balance > self.max_balance:
            self.max_balance = self.current_balance
        drawdown = (self.max_balance - self.current_balance) / self.max_balance
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        self.trades.append({
            'time': timestamp, 'symbol': symbol, 'type': 'close', 'reason': 'TP' if is_tp else 'SL',
            'price': price, 'amount': pos['amount'], 'fee': fee, 'pnl': pnl
        })

        del self.positions[symbol]

        if not is_tp:
            self.cooldown_symbols[symbol] = pos['direction']

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

        logger.info("Fetching and calculating Daily Trend Filter (BTC 200 SMA)...")
        # Fetch 200 extra days so we have enough data to calculate the 200 SMA right from the start of our backtest period
        trend_days = self.days + 200
        df_daily = self.fetch_historical_data('BTC/USDT:USDT', timeframe='1d', limit_fetch_days=trend_days)
        if not df_daily.empty:
            df_daily = self.signal_engine.calculate_daily_indicators(df_daily)
            df_daily.set_index('timestamp', inplace=True)
            # Forward fill the daily regime so we can look it up at any 5m timestamp easily
            # We shift the daily data by 1 so we only use yesterday's close to determine today's regime (avoid lookahead bias)
            df_daily_shifted = df_daily.shift(1)
        else:
            logger.warning("Failed to fetch daily data for trend filtering.")
            df_daily_shifted = pd.DataFrame()

        # Find common timestamps
        common_timestamps = pd.Series(list(indicators.values())[0].index)
        for df in indicators.values():
            common_timestamps = common_timestamps[common_timestamps.isin(df.index)]

        common_timestamps = common_timestamps.sort_values().reset_index(drop=True)

        logger.info("Starting Multi-Asset Simulation...")

        def get_dynamic_margin():
            if config.COMPOUND_MODE:
                return self.current_balance * config.TIER_MARGIN_PCT
            return config.TIER_1_MARGIN

        # Start from index 20
        for i in range(20, len(common_timestamps)):
            timestamp = common_timestamps.iloc[i]

            # Look up current market regime
            current_regime = 'neutral'
            if not df_daily_shifted.empty:
                # Find the latest daily bar that occurred before or exactly at our current 5m timestamp
                daily_slice = df_daily_shifted.loc[:timestamp]
                if not daily_slice.empty:
                    current_regime = self.signal_engine.get_market_regime(daily_slice)

            # 1. Cooldown Check
            symbols_to_remove_cooldown = []
            for symbol, direction in self.cooldown_symbols.items():
                df_slice = indicators[symbol].loc[:timestamp]
                if self.signal_engine.evaluate_cooldown(df_slice, direction):
                    symbols_to_remove_cooldown.append(symbol)
            for symbol in symbols_to_remove_cooldown:
                del self.cooldown_symbols[symbol]

            # 2. Position Management
            for symbol in list(self.positions.keys()):
                row = indicators[symbol].loc[timestamp]
                current_price = row['close']
                pos = self.positions[symbol]
                direction = pos['direction']

                # Check SL and TP (using appropriate high/low based on direction)
                if direction == 'long':
                    # Longs suffer on Lows, profit on Highs
                    worst_price = row['low']
                    best_price = row['high']
                else:
                    # Shorts suffer on Highs, profit on Lows
                    worst_price = row['high']
                    best_price = row['low']

                if config.COMPOUND_MODE:
                    target_tp = pos['margin_usdt'] * config.TP_MARGIN_ROI
                    margin_sl = pos['margin_usdt'] * config.SL_MARGIN_ROI
                    global_cap_sl = self.current_balance * config.SL_GLOBAL_CAP_PCT
                    target_sl = max(margin_sl, global_cap_sl)
                else:
                    target_tp = config.TP_NET_PROFIT
                    target_sl = config.SL_MAX_LOSS

                sl_pnl = self.calculate_pnl(symbol, worst_price)
                if sl_pnl <= target_sl:
                    exec_price = worst_price * (0.9995 if direction == 'long' else 1.0005) # slippage
                    self.close_position(symbol, exec_price, timestamp, is_tp=False)
                    continue

                tp_pnl = self.calculate_pnl(symbol, best_price)
                if tp_pnl >= target_tp:
                    exec_price = best_price * (0.9995 if direction == 'long' else 1.0005) # slippage
                    self.close_position(symbol, exec_price, timestamp, is_tp=True)
                    continue

                # Check Tiers using Close
                pos = self.positions.get(symbol)
                if pos: # Might have been closed above
                    avg_price = self.get_avg_price(symbol)
                    df_slice = indicators[symbol].loc[:timestamp]
                    margin_to_use = get_dynamic_margin()

                    if pos['tier'] == 1:
                        if self.signal_engine.check_tier_2_signal(current_price, avg_price, config.TIER_2_DEV_PCT, direction, df_slice):
                            exec_price = current_price * (1.0005 if direction == 'long' else 0.9995)
                            self.execute_order(symbol, margin_to_use, exec_price, timestamp, 2, direction)
                    elif pos['tier'] == 2:
                        if self.signal_engine.check_tier_3_signal(current_price, avg_price, config.TIER_3_DEV_PCT, direction):
                            exec_price = current_price * (1.0005 if direction == 'long' else 0.9995)
                            self.execute_order(symbol, margin_to_use, exec_price, timestamp, 3, direction)

            # 3. Scanning Phase
            if len(self.positions) < config.MAX_ACTIVE_TRADES:
                margin_to_use = get_dynamic_margin()
                for symbol in self.symbols:
                    if symbol in self.positions or symbol in self.cooldown_symbols:
                        continue

                    df_slice = indicators[symbol].loc[:timestamp]
                    current_price = indicators[symbol].loc[timestamp]['close']

                    # Apply Trend Filter: Only go long if bull or neutral, only go short if bear or neutral
                    can_go_long = current_regime in ['bull', 'neutral']
                    can_go_short = current_regime in ['bear', 'neutral']

                    if can_go_long and self.signal_engine.check_tier_1_long_signal(symbol, df_slice):
                        exec_price = current_price * 1.0005
                        self.execute_order(symbol, margin_to_use, exec_price, timestamp, 1, 'long')
                    elif can_go_short and self.signal_engine.check_tier_1_short_signal(symbol, df_slice):
                        exec_price = current_price * 0.9995
                        self.execute_order(symbol, margin_to_use, exec_price, timestamp, 1, 'short')

                    if len(self.positions) >= config.MAX_ACTIVE_TRADES:
                        break

        # Force-close any remaining open positions at last known price
        last_ts = common_timestamps.iloc[-1]
        for symbol in list(self.positions.keys()):
            last_price = indicators[symbol].loc[last_ts]['close']
            self.close_position(symbol, last_price, last_ts, is_tp=True)

        self.print_report()

    def print_report(self):
        closed_trades = [t for t in self.trades if t['type'] == 'close']
        wins = [t for t in closed_trades if t['pnl'] > 0]
        losses = [t for t in closed_trades if t['pnl'] <= 0]

        win_rate = (len(wins) / len(closed_trades)) * 100 if closed_trades else 0
        total_pnl = sum(t['pnl'] for t in closed_trades)

        print("\n" + "="*40)
        print("📊 BACKTEST PERFORMANCE REPORT (BINANCE FUTURES DCA)")
        print("="*40)
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Timeframe: {config.TIMEFRAME}")
        print(f"Initial Balance: {self.initial_balance} USDT")
        print(f"Final Balance: {self.current_balance:.2f} USDT")
        print(f"Total Net PnL: {total_pnl:.2f} USDT")
        print(f"Total Trades (Cycles): {len(closed_trades)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Max Drawdown (MDD): {self.max_drawdown*100:.2f}%")
        print(f"Max Margin Usage: {self.max_margin_usage:.2f} USDT")
        print("="*40)
        # Margin safety warning: For compound mode, margin_usage naturally exceeds initial_balance.
        # What matters is that Max Drawdown hasn't blown up the account.
        if self.max_drawdown > 0.99:
            print("⚠️ WARNING: Max Drawdown hit ~100%. Account would have been liquidated!")
        elif not config.COMPOUND_MODE and self.max_margin_usage > self.initial_balance:
            print("⚠️ WARNING: Fixed margin exceeded initial balance. Account would have been liquidated!")
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
