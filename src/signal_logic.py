import pandas as pd
import pandas_ta as ta
import requests
import logging
from src.config import config

logger = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self):
        self.ai_url = config.AI_API_URL

    def get_ai_prediction(self, symbol: str, df: pd.DataFrame) -> float:
        """
        Sends historical data to the Colab AI API to get the predicted next close price.
        Returns the predicted close price. If it fails, returns None.
        """
        if not self.ai_url:
            return None

        try:
            lookback_df = df.tail(400).copy()
            lookback_df['timestamp'] = lookback_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

            payload = {
                "symbol": symbol,
                "lookback_data": lookback_df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_dict('records'),
                "pred_len": 1
            }

            url = f"{self.ai_url}/predict"
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            data = response.json()
            predicted_close = data.get("predicted_close")
            logger.info(f"AI Prediction for {symbol}: {predicted_close}")
            return predicted_close
        except Exception as e:
            logger.error(f"Failed to fetch AI prediction (fallback to traditional): {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates required technical indicators using pandas-ta.
        Adds RSI, Bollinger Bands, MACD, EMA crossover, and ATR.
        """
        if df.empty or len(df) < 30:
            return df

        # Calculate RSI
        df.ta.rsi(length=14, append=True)

        # Calculate Bollinger Bands (20, 2)
        df.ta.bbands(length=20, std=2, append=True)

        # Calculate MACD
        df.ta.macd(fast=config.MACD_FAST, slow=config.MACD_SLOW, signal=config.MACD_SIGNAL, append=True)

        # Calculate EMAs for crossover strategy
        df.ta.ema(length=config.EMA_FAST, append=True)
        df.ta.ema(length=config.EMA_SLOW, append=True)

        # Calculate ATR for volatility-based sizing
        df.ta.atr(length=14, append=True)

        # Calculate volume SMA for volume filter
        df['vol_sma_20'] = df['volume'].rolling(window=20).mean()

        return df

    def calculate_daily_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates long-term indicators on daily data for trend filtering.
        """
        sma_len = config.TREND_SMA_LENGTH
        if df.empty or len(df) < sma_len:
            # If not enough data for 200 SMA, use a shorter SMA (50) as fallback
            fallback_len = min(50, len(df) - 1)
            if fallback_len > 10:
                df.ta.sma(length=fallback_len, append=True)
            return df

        df.ta.sma(length=sma_len, append=True)
        return df

    def get_market_regime(self, df_daily: pd.DataFrame) -> str:
        """
        Determines the current market regime (bull or bear) based on the 1D SMA.
        Falls back to shorter SMA if 200 SMA is not available.
        """
        if df_daily.empty or len(df_daily) < 1:
            return 'neutral'

        latest = df_daily.iloc[-1]

        # Try 200 SMA first, then fall back to shorter SMAs
        sma_col = [c for c in df_daily.columns if c.startswith(f'SMA_{config.TREND_SMA_LENGTH}')]
        if not sma_col:
            sma_col = [c for c in df_daily.columns if c.startswith('SMA_')]

        if not sma_col:
            return 'neutral'

        sma_val = latest[sma_col[0]]
        close_val = latest['close']

        if pd.isna(sma_val):
            return 'neutral'

        if close_val > sma_val:
            return 'bull'
        elif close_val < sma_val:
            return 'bear'

        return 'neutral'

    def check_tier_1_long_signal(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        Checks if conditions for Tier 1 Long entry are met.
        Uses multi-strategy approach: RSI+BB, MACD crossover, or EMA crossover.
        """
        if df.empty or len(df) < 30:
            return False

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        bbl_col = [c for c in df.columns if c.startswith('BBL_')]
        macd_col = [c for c in df.columns if c.startswith('MACD_') and not c.startswith('MACDs_') and not c.startswith('MACDh_')]
        macdh_col = [c for c in df.columns if c.startswith('MACDh_')]
        ema_fast_col = [c for c in df.columns if c == f'EMA_{config.EMA_FAST}']
        ema_slow_col = [c for c in df.columns if c == f'EMA_{config.EMA_SLOW}']

        if not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        if pd.isna(rsi_val):
            return False

        # Strategy 1: Original RSI + Bollinger Band
        bb_signal = False
        if bbl_col:
            bbl_val = latest[bbl_col[0]]
            close_val = latest['close']
            if not pd.isna(bbl_val):
                bb_signal = (rsi_val < config.RSI_LONG_ENTRY and close_val <= bbl_val)

        # Strategy 2: MACD Bullish Crossover + RSI confirmation
        macd_signal = False
        if macdh_col and prev is not None:
            macdh_val = latest[macdh_col[0]]
            macdh_prev = prev[macdh_col[0]]
            if not pd.isna(macdh_val) and not pd.isna(macdh_prev):
                # MACD histogram crosses from negative to positive (bullish crossover)
                macd_signal = (macdh_prev < 0 and macdh_val > 0 and rsi_val < 45)

        # Strategy 3: EMA Crossover + RSI confirmation
        ema_signal = False
        if ema_fast_col and ema_slow_col and prev is not None:
            ema_fast = latest[ema_fast_col[0]]
            ema_slow = latest[ema_slow_col[0]]
            ema_fast_prev = prev[ema_fast_col[0]]
            ema_slow_prev = prev[ema_slow_col[0]]
            if not any(pd.isna(v) for v in [ema_fast, ema_slow, ema_fast_prev, ema_slow_prev]):
                # EMA fast crosses above slow (golden cross)
                ema_signal = (ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow and rsi_val < 50)

        # Volume filter: only trade when volume is above average
        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * 0.7  # At least 70% of avg volume

        traditional_signal = (bb_signal or macd_signal or ema_signal) and vol_filter

        if not traditional_signal:
            return False

        # AI confirmation (optional)
        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            close_val = latest['close']
            if predicted_close > close_val:
                return True
            else:
                return False

        return True

    def check_tier_1_short_signal(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        Checks if conditions for Tier 1 Short entry are met.
        Uses multi-strategy approach: RSI+BB, MACD crossover, or EMA crossover.
        """
        if df.empty or len(df) < 30:
            return False

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        bbu_col = [c for c in df.columns if c.startswith('BBU_')]
        macdh_col = [c for c in df.columns if c.startswith('MACDh_')]
        ema_fast_col = [c for c in df.columns if c == f'EMA_{config.EMA_FAST}']
        ema_slow_col = [c for c in df.columns if c == f'EMA_{config.EMA_SLOW}']

        if not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        if pd.isna(rsi_val):
            return False

        # Strategy 1: Original RSI + Bollinger Band
        bb_signal = False
        if bbu_col:
            bbu_val = latest[bbu_col[0]]
            close_val = latest['close']
            if not pd.isna(bbu_val):
                bb_signal = (rsi_val > config.RSI_SHORT_ENTRY and close_val >= bbu_val)

        # Strategy 2: MACD Bearish Crossover + RSI confirmation
        macd_signal = False
        if macdh_col and prev is not None:
            macdh_val = latest[macdh_col[0]]
            macdh_prev = prev[macdh_col[0]]
            if not pd.isna(macdh_val) and not pd.isna(macdh_prev):
                # MACD histogram crosses from positive to negative (bearish crossover)
                macd_signal = (macdh_prev > 0 and macdh_val < 0 and rsi_val > 55)

        # Strategy 3: EMA Crossover + RSI confirmation
        ema_signal = False
        if ema_fast_col and ema_slow_col and prev is not None:
            ema_fast = latest[ema_fast_col[0]]
            ema_slow = latest[ema_slow_col[0]]
            ema_fast_prev = prev[ema_fast_col[0]]
            ema_slow_prev = prev[ema_slow_col[0]]
            if not any(pd.isna(v) for v in [ema_fast, ema_slow, ema_fast_prev, ema_slow_prev]):
                # EMA fast crosses below slow (death cross)
                ema_signal = (ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow and rsi_val > 50)

        # Volume filter
        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * 0.7

        traditional_signal = (bb_signal or macd_signal or ema_signal) and vol_filter

        if not traditional_signal:
            return False

        # AI confirmation (optional)
        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            close_val = latest['close']
            if predicted_close < close_val:
                return True
            else:
                return False

        return True

    def check_tier_2_signal(self, current_price: float, avg_entry_price: float, dev_pct: float, direction: str, df: pd.DataFrame) -> bool:
        """
        Checks if conditions for Tier 2 entry are met for either long or short.
        """
        if df.empty or len(df) < 2: return False

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        if not rsi_col: return False

        latest_rsi = df.iloc[-1][rsi_col[0]]
        prev_rsi = df.iloc[-2][rsi_col[0]]

        if direction == 'long':
            if current_price > avg_entry_price * (1 - dev_pct):
                return False
            return (latest_rsi < 35 or latest_rsi > prev_rsi)
        else:
            if current_price < avg_entry_price * (1 + dev_pct):
                return False
            return (latest_rsi > 65 or latest_rsi < prev_rsi)

    def check_tier_3_signal(self, current_price: float, avg_entry_price: float, dev_pct: float, direction: str) -> bool:
        """
        Checks if conditions for Tier 3 entry are met.
        """
        if direction == 'long':
            return current_price <= avg_entry_price * (1 - dev_pct)
        else:
            return current_price >= avg_entry_price * (1 + dev_pct)

    def evaluate_cooldown(self, df: pd.DataFrame, direction: str = 'long') -> bool:
        """
        Evaluates if the market has stabilized after a Stop Loss.
        """
        if df.empty or len(df) < 20:
            return False

        latest = df.iloc[-1]

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        if not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        close_val = latest['close']

        sma_20 = df['close'].rolling(window=20).mean().iloc[-1]

        if pd.isna(rsi_val) or pd.isna(sma_20):
            return False

        if direction == 'long':
            return rsi_val > 40 and close_val > sma_20
        else:
            return rsi_val < 60 and close_val < sma_20
