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
    def __init__(self, symbols=None, days=90, param_overrides=None):
        """
        param_overrides: dict of config attribute overrides for optimization runs.
        """
        self.symbols = symbols if symbols else config.SYMBOLS
        self.days = days
        self.exchange = ccxt.okx({'enableRateLimit': True})
        self.signal_engine = SignalEngine()

        # Apply parameter overrides for optimization
        self.params = {}
        param_keys = [
            'RSI_LONG_ENTRY', 'RSI_SHORT_ENTRY', 'TP_MARGIN_ROI', 'SL_MARGIN_ROI',
            'SL_GLOBAL_CAP_PCT', 'TIER_MARGIN_PCT', 'LEVERAGE', 'MAX_ACTIVE_TRADES',
            'TIER_2_DEV_PCT', 'TIER_3_DEV_PCT', 'TRAILING_TP_ACTIVATE_ROI',
            'TRAILING_TP_CALLBACK_ROI', 'FUNDING_RATE', 'COOLDOWN_CANDLES',
            'EMA_FAST', 'EMA_SLOW', 'FEE_RATE', 'COMPOUND_MODE', 'BASE_CAPITAL'
        ]
        for key in param_keys:
            if param_overrides and key in param_overrides:
                self.params[key] = param_overrides[key]
            else:
                self.params[key] = getattr(config, key)

        # State
        self.positions = {}
        self.cooldown_symbols = {}
        self.cooldown_candle_count = {}  # Track candles since SL for each symbol
        self.consecutive_losses = {}     # Track consecutive losses per symbol
        self.trailing_peaks = {}         # Track peak PnL ROI for trailing TP

        # Performance Tracking
        self.initial_balance = self.params['BASE_CAPITAL']
        self.current_balance = self.params['BASE_CAPITAL']
        self.max_balance = self.params['BASE_CAPITAL']
        self.max_drawdown = 0.0
        self.max_margin_usage = 0.0
        self.trades = []

        # Monthly balance snapshots
        self.monthly_balances = {}

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
                time.sleep(0.2)
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
        leverage = self.params['LEVERAGE']
        fee_rate = self.params['FEE_RATE']

        position_value_usdt = margin_usdt * leverage
        amount = position_value_usdt / price
        fee = position_value_usdt * fee_rate

        # Check if we have enough balance
        if self.current_balance < (margin_usdt + fee):
            return  # Skip order if insufficient balance

        if symbol not in self.positions:
            self.positions[symbol] = {
                'tier': 0, 'direction': direction, 'amount': 0.0,
                'margin_usdt': 0.0, 'notional_usdt': 0.0, 'fees_usdt': 0.0,
                'open_time': timestamp
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

    def close_position(self, symbol, price, timestamp, is_tp=True, reason_detail=''):
        pos = self.positions.get(symbol)
        if not pos: return

        fee_rate = self.params['FEE_RATE']
        current_notional = pos['amount'] * price
        fee = current_notional * fee_rate

        if pos['direction'] == 'long':
            gross_pnl = current_notional - pos['notional_usdt']
        else:
            gross_pnl = pos['notional_usdt'] - current_notional

        pnl = gross_pnl - pos['fees_usdt'] - fee

        # Return margin + gross_pnl - exit_fee
        self.current_balance += (pos['margin_usdt'] + gross_pnl - fee)

        if self.current_balance > self.max_balance:
            self.max_balance = self.current_balance
        drawdown = (self.max_balance - self.current_balance) / self.max_balance if self.max_balance > 0 else 0
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        close_reason = 'TP' if is_tp else 'SL'
        if reason_detail:
            close_reason = reason_detail

        self.trades.append({
            'time': timestamp, 'symbol': symbol, 'type': 'close', 'reason': close_reason,
            'price': price, 'amount': pos['amount'], 'fee': fee, 'pnl': pnl
        })

        direction = pos['direction']
        del self.positions[symbol]

        # Clear trailing peak
        if symbol in self.trailing_peaks:
            del self.trailing_peaks[symbol]

        if not is_tp:
            self.cooldown_symbols[symbol] = direction
            self.cooldown_candle_count[symbol] = 0

            # Track consecutive losses
            if symbol not in self.consecutive_losses:
                self.consecutive_losses[symbol] = 0
            self.consecutive_losses[symbol] += 1
        else:
            # Reset consecutive losses on win
            self.consecutive_losses[symbol] = 0

    def calculate_pnl(self, symbol, current_price):
        pos = self.positions.get(symbol)
        if not pos or pos['amount'] == 0:
            return 0.0

        fee_rate = self.params['FEE_RATE']
        current_notional = pos['amount'] * current_price
        estimated_exit_fee = current_notional * fee_rate

        if pos['direction'] == 'long':
            gross_pnl = current_notional - pos['notional_usdt']
        else:
            gross_pnl = pos['notional_usdt'] - current_notional

        net_pnl = gross_pnl - pos['fees_usdt'] - estimated_exit_fee
        return net_pnl

    def apply_funding_rate(self, timestamp):
        """
        Simulate funding rate charges every 8 hours.
        In real markets, longs pay shorts when funding is positive (most common).
        """
        funding_rate = self.params['FUNDING_RATE']
        if funding_rate == 0:
            return

        for symbol, pos in list(self.positions.items()):
            # Funding applies to notional value
            funding_cost = pos['notional_usdt'] * funding_rate
            if pos['direction'] == 'long':
                # Longs typically pay funding
                self.current_balance -= funding_cost
                pos['fees_usdt'] += funding_cost
            else:
                # Shorts typically receive funding
                self.current_balance += funding_cost * 0.5  # Partial benefit (conservative)

    def run(self):
        logger.info("Loading data and calculating indicators for all symbols...")
        indicators = {}
        min_len = float('inf')

        for symbol in self.symbols:
            df = self.fetch_historical_data(symbol)
            if not df.empty:
                df = self.signal_engine.calculate_indicators(df)
                df.set_index('timestamp', inplace=True)
                indicators[symbol] = df
                if len(df) < min_len:
                    min_len = len(df)

        if not indicators:
            logger.error("No data available to backtest.")
            return

        logger.info("Fetching and calculating Daily Trend Filter (BTC SMA)...")
        trend_days = self.days + 200
        df_daily = self.fetch_historical_data('BTC/USDT:USDT', timeframe='1d', limit_fetch_days=trend_days)
        if not df_daily.empty:
            df_daily = self.signal_engine.calculate_daily_indicators(df_daily)
            df_daily.set_index('timestamp', inplace=True)
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

        leverage = self.params['LEVERAGE']
        tp_roi = self.params['TP_MARGIN_ROI']
        sl_roi = self.params['SL_MARGIN_ROI']
        sl_cap = self.params['SL_GLOBAL_CAP_PCT']
        trailing_activate = self.params['TRAILING_TP_ACTIVATE_ROI']
        trailing_callback = self.params['TRAILING_TP_CALLBACK_ROI']
        max_trades = self.params['MAX_ACTIVE_TRADES']
        cooldown_min = self.params['COOLDOWN_CANDLES']

        def get_dynamic_margin():
            if self.params['COMPOUND_MODE']:
                return self.current_balance * self.params['TIER_MARGIN_PCT']
            return config.TIER_1_MARGIN

        # Funding rate tracking
        last_funding_hour = -1
        funding_interval = config.FUNDING_INTERVAL_HOURS

        # Track current month for snapshots
        current_month = None

        # Start from index 30 (need enough data for indicators)
        for i in range(30, len(common_timestamps)):
            timestamp = common_timestamps.iloc[i]

            # Monthly balance snapshot
            ts_month = timestamp.to_period('M')
            if current_month is not None and ts_month != current_month:
                # Record end-of-month balance
                self.monthly_balances[str(current_month)] = self.current_balance
            current_month = ts_month

            # Apply funding rate every 8 hours
            ts_hour = timestamp.hour
            if self.positions and ts_hour % funding_interval == 0 and ts_hour != last_funding_hour:
                self.apply_funding_rate(timestamp)
                last_funding_hour = ts_hour

            # Look up current market regime
            current_regime = 'neutral'
            if not df_daily_shifted.empty:
                daily_slice = df_daily_shifted.loc[:timestamp]
                if not daily_slice.empty:
                    current_regime = self.signal_engine.get_market_regime(daily_slice)

            # 1. Cooldown Check (enhanced with candle count)
            symbols_to_remove_cooldown = []
            for symbol, direction in self.cooldown_symbols.items():
                # Increment cooldown counter
                if symbol in self.cooldown_candle_count:
                    self.cooldown_candle_count[symbol] += 1

                # Must wait minimum candles AND market must stabilize
                candles_waited = self.cooldown_candle_count.get(symbol, 0)
                if candles_waited >= cooldown_min:
                    df_slice = indicators[symbol].loc[:timestamp]
                    if self.signal_engine.evaluate_cooldown(df_slice, direction):
                        symbols_to_remove_cooldown.append(symbol)

            for symbol in symbols_to_remove_cooldown:
                del self.cooldown_symbols[symbol]
                if symbol in self.cooldown_candle_count:
                    del self.cooldown_candle_count[symbol]

            # 2. Position Management
            for symbol in list(self.positions.keys()):
                row = indicators[symbol].loc[timestamp]
                current_price = row['close']
                pos = self.positions[symbol]
                direction = pos['direction']

                if direction == 'long':
                    worst_price = row['low']
                    best_price = row['high']
                else:
                    worst_price = row['high']
                    best_price = row['low']

                if self.params['COMPOUND_MODE']:
                    target_tp = pos['margin_usdt'] * tp_roi
                    margin_sl = pos['margin_usdt'] * sl_roi
                    global_cap_sl = self.current_balance * sl_cap
                    target_sl = max(margin_sl, global_cap_sl)
                else:
                    target_tp = config.TP_NET_PROFIT
                    target_sl = config.SL_MAX_LOSS

                # Check Stop Loss
                sl_pnl = self.calculate_pnl(symbol, worst_price)
                if sl_pnl <= target_sl:
                    exec_price = worst_price * (0.9995 if direction == 'long' else 1.0005)
                    self.close_position(symbol, exec_price, timestamp, is_tp=False)
                    continue

                # Check trailing take-profit
                best_pnl = self.calculate_pnl(symbol, best_price)
                best_roi = best_pnl / pos['margin_usdt'] if pos['margin_usdt'] > 0 else 0

                if best_roi >= trailing_activate:
                    # Update peak
                    if symbol not in self.trailing_peaks or best_roi > self.trailing_peaks[symbol]:
                        self.trailing_peaks[symbol] = best_roi

                    # Check if price has pulled back from peak
                    close_pnl = self.calculate_pnl(symbol, current_price)
                    close_roi = close_pnl / pos['margin_usdt'] if pos['margin_usdt'] > 0 else 0
                    peak_roi = self.trailing_peaks.get(symbol, 0)

                    if peak_roi - close_roi >= trailing_callback and close_roi > 0:
                        exec_price = current_price * (0.9995 if direction == 'long' else 1.0005)
                        self.close_position(symbol, exec_price, timestamp, is_tp=True, reason_detail='TRAILING_TP')
                        continue

                # Check fixed Take Profit
                tp_pnl = self.calculate_pnl(symbol, best_price)
                if tp_pnl >= target_tp:
                    exec_price = best_price * (0.9995 if direction == 'long' else 1.0005)
                    self.close_position(symbol, exec_price, timestamp, is_tp=True)
                    continue

                # Check Tier upgrades using Close
                pos = self.positions.get(symbol)
                if pos:
                    avg_price = self.get_avg_price(symbol)
                    df_slice = indicators[symbol].loc[:timestamp]
                    margin_to_use = get_dynamic_margin()

                    if pos['tier'] == 1:
                        if self.signal_engine.check_tier_2_signal(
                            current_price, avg_price, self.params['TIER_2_DEV_PCT'], direction, df_slice
                        ):
                            exec_price = current_price * (1.0005 if direction == 'long' else 0.9995)
                            self.execute_order(symbol, margin_to_use, exec_price, timestamp, 2, direction)
                    elif pos['tier'] == 2:
                        if self.signal_engine.check_tier_3_signal(
                            current_price, avg_price, self.params['TIER_3_DEV_PCT'], direction
                        ):
                            exec_price = current_price * (1.0005 if direction == 'long' else 0.9995)
                            self.execute_order(symbol, margin_to_use, exec_price, timestamp, 3, direction)

            # 3. Scanning Phase
            if len(self.positions) < max_trades:
                margin_to_use = get_dynamic_margin()
                for symbol in self.symbols:
                    if symbol in self.positions or symbol in self.cooldown_symbols:
                        continue

                    # Skip symbols with too many consecutive losses
                    if self.consecutive_losses.get(symbol, 0) >= config.MAX_CONSECUTIVE_LOSSES:
                        # Reset after extended cooldown
                        if self.cooldown_candle_count.get(symbol, 0) > cooldown_min * 3:
                            self.consecutive_losses[symbol] = 0
                        else:
                            continue

                    df_slice = indicators[symbol].loc[:timestamp]
                    current_price = indicators[symbol].loc[timestamp]['close']

                    can_go_long = current_regime in ['bull', 'neutral']
                    can_go_short = current_regime in ['bear', 'neutral']

                    if can_go_long and self.signal_engine.check_tier_1_long_signal(symbol, df_slice):
                        exec_price = current_price * 1.0005
                        self.execute_order(symbol, margin_to_use, exec_price, timestamp, 1, 'long')
                    elif can_go_short and self.signal_engine.check_tier_1_short_signal(symbol, df_slice):
                        exec_price = current_price * 0.9995
                        self.execute_order(symbol, margin_to_use, exec_price, timestamp, 1, 'short')

                    if len(self.positions) >= max_trades:
                        break

        # Record final month
        if current_month is not None:
            self.monthly_balances[str(current_month)] = self.current_balance

        self.print_report()

    def get_monthly_pnl_report(self):
        """Returns a list of dicts with monthly performance data."""
        closed_trades = [t for t in self.trades if t['type'] == 'close']
        if not closed_trades:
            return []

        df = pd.DataFrame(closed_trades)
        df['time'] = pd.to_datetime(df['time'])
        df['month'] = df['time'].dt.to_period('M')

        monthly_data = []
        cumulative_pnl = 0.0
        prev_balance = self.initial_balance

        for month_period, group in df.groupby('month'):
            month_str = str(month_period)
            trades_count = len(group)
            wins = (group['pnl'] > 0).sum()
            losses = (group['pnl'] <= 0).sum()
            win_rate = wins / trades_count * 100 if trades_count > 0 else 0
            net_pnl = group['pnl'].sum()
            cumulative_pnl += net_pnl
            end_balance = self.monthly_balances.get(month_str, prev_balance + net_pnl)
            prev_balance = end_balance

            monthly_data.append({
                'month': month_str,
                'trades': trades_count,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'net_pnl': net_pnl,
                'cumulative_pnl': cumulative_pnl,
                'end_balance': end_balance,
            })

        return monthly_data

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
        if self.max_drawdown > 0.99:
            print("⚠️ WARNING: Max Drawdown hit ~100%. Account would have been liquidated!")
        elif not self.params['COMPOUND_MODE'] and self.max_margin_usage > self.initial_balance:
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
