import pandas as pd
import pandas_ta as ta
import requests
import logging
from src.config import config

logger = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self, params=None):
        self.params = params or {}
        self.ai_url = config.AI_API_URL

    def get_param(self, name: str):
        return self.params.get(name, getattr(config, name))

    def get_min_signal_candles(self) -> int:
        """
        Minimum 5m candles required before any entry logic should run.
        30 candles covers the 20-period Bollinger / volume windows, 14-period
        RSI / ATR, and gives crossover-based signals extra warm-up margin.
        """
        return 30

    def has_min_donchian_history(self, df: pd.DataFrame) -> bool:
        required = max(self.get_min_signal_candles(), int(self.get_param('DONCHIAN_LENGTH')) + 1)
        return not df.empty and len(df) >= required

    def get_atr_ratio(self, df: pd.DataFrame) -> float:
        if df.empty:
            return None
        atr_cols = [c for c in df.columns if c.startswith('ATRr_')]
        if not atr_cols:
            return None
        atr_col = atr_cols[0]
        atr_series = df[atr_col].dropna()
        if atr_series.empty:
            return None

        lookback = int(self.get_param('ATR_VOL_LOOKBACK'))
        baseline_window = atr_series.tail(lookback)
        if baseline_window.empty:
            return None

        baseline = baseline_window.median()
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or pd.isna(baseline) or baseline <= 0:
            return None
        return current_atr / baseline

    def get_entry_rsi_thresholds(self, df: pd.DataFrame):
        long_threshold = self.get_param('RSI_LONG_ENTRY')
        short_threshold = self.get_param('RSI_SHORT_ENTRY')

        if not self.get_param('VOLATILITY_ADAPTIVE_ENTRY'):
            return long_threshold, short_threshold

        atr_ratio = self.get_atr_ratio(df)
        if atr_ratio is None:
            return long_threshold, short_threshold

        if atr_ratio >= self.get_param('HIGH_VOL_THRESHOLD'):
            return self.get_param('RSI_LONG_ENTRY_HIGH_VOL'), self.get_param('RSI_SHORT_ENTRY_HIGH_VOL')
        if atr_ratio <= self.get_param('LOW_VOL_THRESHOLD'):
            return self.get_param('RSI_LONG_ENTRY_LOW_VOL'), self.get_param('RSI_SHORT_ENTRY_LOW_VOL')
        return long_threshold, short_threshold

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
        Requires at least 30 candles so the 20-period Bollinger / volume windows,
        14-period RSI / ATR, and crossover checks all have enough warm-up history
        before the first entry evaluation.
        """
        if df.empty or len(df) < self.get_min_signal_candles():
            return df

        # Calculate RSI
        df.ta.rsi(length=14, append=True)

        # Calculate Bollinger Bands (20, 2)
        df.ta.bbands(length=20, std=2, append=True)

        # Calculate MACD
        df.ta.macd(
            fast=self.get_param('MACD_FAST'),
            slow=self.get_param('MACD_SLOW'),
            signal=self.get_param('MACD_SIGNAL'),
            append=True,
        )

        # Calculate EMAs for crossover strategy
        df.ta.ema(length=self.get_param('EMA_FAST'), append=True)
        df.ta.ema(length=self.get_param('EMA_SLOW'), append=True)

        # Calculate ATR for volatility-based sizing
        df.ta.atr(length=14, append=True)

        # Calculate volume SMA for volume filter
        df['vol_sma_20'] = df['volume'].rolling(window=20).mean()

        donchian_length = int(self.get_param('DONCHIAN_LENGTH'))
        if len(df) > donchian_length:
            df['donchian_high'] = df['high'].rolling(window=donchian_length).max().shift(1)
            df['donchian_low'] = df['low'].rolling(window=donchian_length).min().shift(1)
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2

        return df

    def calculate_daily_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates long-term indicators on daily data for trend filtering.
        Uses cascading SMAs: 200, 50, 20 - tries longest available first.
        """
        if df.empty or len(df) < 10:
            return df

        # Always compute shorter SMAs as fallbacks
        if len(df) > 20:
            df.ta.sma(length=20, append=True)
        if len(df) > 50:
            df.ta.sma(length=50, append=True)

        sma_len = self.get_param('TREND_SMA_LENGTH')
        if len(df) >= sma_len:
            df.ta.sma(length=sma_len, append=True)

        return df

    def calculate_hourly_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates hourly trend indicators used by multi-timeframe filters.
        """
        if df.empty or len(df) < 5:
            return df

        fast = int(self.get_param('HOURLY_EMA_FAST'))
        slow = int(self.get_param('HOURLY_EMA_SLOW'))
        if len(df) >= fast:
            df.ta.ema(length=fast, append=True)
        if len(df) >= slow:
            df.ta.ema(length=slow, append=True)

        adx_length = int(self.get_param('ADVANCED_TREND_ADX_LENGTH'))
        if len(df) >= adx_length:
            df.ta.adx(length=adx_length, append=True)

        return df

    def get_market_regime(self, df_daily: pd.DataFrame) -> str:
        """
        Determines the current market regime (bull or bear) based on the 1D SMA.
        Uses cascading fallback: SMA_200 → SMA_50 → SMA_20.
        """
        if df_daily.empty or len(df_daily) < 1:
            return 'neutral'

        latest = df_daily.iloc[-1]

        # Try SMAs from longest to shortest
        for sma_prefix in [f"SMA_{self.get_param('TREND_SMA_LENGTH')}", 'SMA_50', 'SMA_20']:
            sma_col = [c for c in df_daily.columns if c.startswith(sma_prefix)]
            if sma_col:
                sma_val = latest[sma_col[0]]
                close_val = latest['close']

                if not pd.isna(sma_val):
                    if close_val > sma_val:
                        return 'bull'
                    elif close_val < sma_val:
                        return 'bear'

        return 'neutral'

    def get_hourly_trend(self, df_hourly: pd.DataFrame) -> str:
        """
        Determines multi-timeframe trend state from hourly EMA structure.
        """
        if df_hourly.empty or len(df_hourly) < 1:
            return 'neutral'

        latest = df_hourly.iloc[-1]
        fast_col = [c for c in df_hourly.columns if c == f"EMA_{self.get_param('HOURLY_EMA_FAST')}"]
        slow_col = [c for c in df_hourly.columns if c == f"EMA_{self.get_param('HOURLY_EMA_SLOW')}"]
        if not fast_col or not slow_col:
            return 'neutral'

        fast_val = latest[fast_col[0]]
        slow_val = latest[slow_col[0]]
        if pd.isna(fast_val) or pd.isna(slow_val):
            return 'neutral'
        if fast_val > slow_val:
            return 'bull'
        if fast_val < slow_val:
            return 'bear'
        return 'neutral'

    def get_hourly_adx(self, df_hourly: pd.DataFrame) -> float:
        if df_hourly.empty:
            return None
        adx_prefix = f"ADX_{int(self.get_param('ADVANCED_TREND_ADX_LENGTH'))}"
        adx_cols = [c for c in df_hourly.columns if c.startswith(adx_prefix)]
        if not adx_cols:
            return None
        adx_val = df_hourly.iloc[-1][adx_cols[0]]
        if pd.isna(adx_val):
            return None
        return adx_val

    def get_hourly_fast_ema(self, df_hourly: pd.DataFrame):
        fast_col = [c for c in df_hourly.columns if c == f"EMA_{self.get_param('HOURLY_EMA_FAST')}"]
        if not fast_col or df_hourly.empty:
            return None
        val = df_hourly.iloc[-1][fast_col[0]]
        if pd.isna(val):
            return None
        return val

    def has_hhhl_structure(self, df_hourly: pd.DataFrame, direction: str) -> bool:
        lookback = int(self.get_param('ADVANCED_TREND_STRUCTURE_BARS'))
        recent = df_hourly[['high', 'low']].dropna().tail(lookback)
        if len(recent) < lookback:
            return False

        highs = recent['high'].tolist()
        lows = recent['low'].tolist()
        if direction == 'long':
            return all(highs[i] > highs[i - 1] for i in range(1, len(highs))) and all(
                lows[i] > lows[i - 1] for i in range(1, len(lows))
            )
        return all(highs[i] < highs[i - 1] for i in range(1, len(highs))) and all(
            lows[i] < lows[i - 1] for i in range(1, len(lows))
        )

    def passes_advanced_trend_filter(self, df_hourly: pd.DataFrame, direction: str) -> bool:
        """
        Stronger trend validation using hourly ADX, EMA slope, and price structure.
        """
        if not self.get_param('ENABLE_ADVANCED_TREND_FILTER'):
            return True
        if df_hourly.empty:
            return False

        hourly_trend = self.get_hourly_trend(df_hourly)
        if direction == 'long' and hourly_trend != 'bull':
            return False
        if direction == 'short' and hourly_trend != 'bear':
            return False

        adx_val = self.get_hourly_adx(df_hourly)
        if adx_val is None or adx_val < self.get_param('ADVANCED_TREND_ADX_THRESHOLD'):
            return False

        lookback = int(self.get_param('ADVANCED_TREND_SLOPE_LOOKBACK'))
        fast_col = [c for c in df_hourly.columns if c == f"EMA_{self.get_param('HOURLY_EMA_FAST')}"]
        if not fast_col or len(df_hourly) <= lookback:
            return False

        fast_series = df_hourly[fast_col[0]].dropna()
        if len(fast_series) <= lookback:
            return False
        latest_fast = fast_series.iloc[-1]
        previous_fast = fast_series.iloc[-(lookback + 1)]
        if pd.isna(latest_fast) or pd.isna(previous_fast) or previous_fast == 0:
            return False

        slope_ratio = (latest_fast - previous_fast) / previous_fast
        slope_min = self.get_param('ADVANCED_TREND_SLOPE_MIN')
        if direction == 'long' and slope_ratio < slope_min:
            return False
        if direction == 'short' and slope_ratio > -slope_min:
            return False

        if not self.has_hhhl_structure(df_hourly, direction):
            return False

        return True

    def check_donchian_long_signal(self, symbol: str, df: pd.DataFrame, df_hourly: pd.DataFrame = None) -> bool:
        """
        Returns True when a long Donchian breakout entry is valid.

        symbol: instrument name used for optional AI confirmation.
        df: current 5m indicator dataframe slice.
        df_hourly: optional shifted 1H indicator dataframe slice for trend filtering.
        """
        if not self.has_min_donchian_history(df):
            return False

        latest = df.iloc[-1]
        close_val = latest['close']
        donchian_high = latest.get('donchian_high')
        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        if pd.isna(close_val) or pd.isna(donchian_high) or not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        if pd.isna(rsi_val):
            return False

        breakout_signal = close_val >= donchian_high * (1 + self.get_param('DONCHIAN_BREAKOUT_BUFFER_PCT'))
        rsi_signal = self.get_param('DONCHIAN_LONG_RSI_MIN') <= rsi_val <= self.get_param('DONCHIAN_LONG_RSI_MAX')

        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * self.get_param('DONCHIAN_VOLUME_MULT')

        hourly_filter = True
        if self.get_param('ENABLE_1H_TREND_FILTER'):
            hourly_filter = self.get_hourly_trend(df_hourly if df_hourly is not None else pd.DataFrame()) == 'bull'
        advanced_filter = self.passes_advanced_trend_filter(
            df_hourly if df_hourly is not None else pd.DataFrame(), 'long'
        )

        if not (breakout_signal and rsi_signal and vol_filter and hourly_filter and advanced_filter):
            return False

        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            return predicted_close > close_val

        return True

    def check_donchian_short_signal(self, symbol: str, df: pd.DataFrame, df_hourly: pd.DataFrame = None) -> bool:
        """
        Returns True when a short Donchian breakdown entry is valid.

        symbol: instrument name used for optional AI confirmation.
        df: current 5m indicator dataframe slice.
        df_hourly: optional shifted 1H indicator dataframe slice for trend filtering.
        """
        if not self.has_min_donchian_history(df):
            return False

        latest = df.iloc[-1]
        close_val = latest['close']
        donchian_low = latest.get('donchian_low')
        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        if pd.isna(close_val) or pd.isna(donchian_low) or not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        if pd.isna(rsi_val):
            return False

        breakout_signal = close_val <= donchian_low * (1 - self.get_param('DONCHIAN_BREAKOUT_BUFFER_PCT'))
        rsi_signal = self.get_param('DONCHIAN_SHORT_RSI_MIN') <= rsi_val <= self.get_param('DONCHIAN_SHORT_RSI_MAX')

        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * self.get_param('DONCHIAN_VOLUME_MULT')

        hourly_filter = True
        if self.get_param('ENABLE_1H_TREND_FILTER'):
            hourly_filter = self.get_hourly_trend(df_hourly if df_hourly is not None else pd.DataFrame()) == 'bear'
        advanced_filter = self.passes_advanced_trend_filter(
            df_hourly if df_hourly is not None else pd.DataFrame(), 'short'
        )

        if not (breakout_signal and rsi_signal and vol_filter and hourly_filter and advanced_filter):
            return False

        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            return predicted_close < close_val

        return True

    def should_exit_trend_position(self, df: pd.DataFrame, df_hourly: pd.DataFrame, direction: str) -> bool:
        """
        Returns True when a trend-following position should be exited.

        df: current 5m indicator dataframe slice.
        df_hourly: shifted 1H indicator dataframe slice for trend-state checks.
        direction: current position direction, either 'long' or 'short'.
        """
        if df.empty:
            return False

        latest = df.iloc[-1]
        hourly_trend = self.get_hourly_trend(df_hourly if df_hourly is not None else pd.DataFrame())

        if self.get_param('ENABLE_TREND_EXIT') and self.get_param('TREND_EXIT_ON_HOURLY_FLIP'):
            if direction == 'long' and hourly_trend == 'bear':
                return True
            if direction == 'short' and hourly_trend == 'bull':
                return True

        if self.get_param('ENABLE_TREND_EXIT') and self.get_param('TREND_EXIT_USE_DONCHIAN_MID'):
            donchian_mid = latest.get('donchian_mid')
            close_val = latest.get('close')
            if not pd.isna(donchian_mid) and not pd.isna(close_val):
                if direction == 'long' and close_val < donchian_mid:
                    return True
                if direction == 'short' and close_val > donchian_mid:
                    return True

        return False

    def check_trend_pyramid_signal(
        self,
        current_price: float,
        last_add_price: float,
        direction: str,
        df: pd.DataFrame,
        df_hourly: pd.DataFrame,
        current_roi: float,
    ) -> bool:
        """
        Phase 7 trend pyramiding: add only after profitable continuation with trend intact.
        """
        if not self.get_param('ENABLE_TREND_PYRAMIDING'):
            return False
        if df.empty or last_add_price is None or last_add_price <= 0:
            return False

        trigger_roi = self.get_param('TREND_PYRAMID_TRIGGER_ROI')
        if current_roi < trigger_roi:
            return False

        latest = df.iloc[-1]
        donchian_mid = latest.get('donchian_mid')
        close_val = latest.get('close')
        if pd.isna(close_val):
            return False

        hourly_trend = self.get_hourly_trend(df_hourly if df_hourly is not None else pd.DataFrame())
        if direction == 'long':
            if hourly_trend != 'bull':
                return False
            if not self.passes_advanced_trend_filter(df_hourly if df_hourly is not None else pd.DataFrame(), 'long'):
                return False
            if current_price < last_add_price * (1 + self.get_param('TREND_PYRAMID_MIN_PULLBACK')):
                return False
            if not pd.isna(donchian_mid) and close_val < donchian_mid:
                return False
            return True

        if hourly_trend != 'bear':
            return False
        if not self.passes_advanced_trend_filter(df_hourly if df_hourly is not None else pd.DataFrame(), 'short'):
            return False
        if current_price > last_add_price * (1 - self.get_param('TREND_PYRAMID_MIN_PULLBACK')):
            return False
        if not pd.isna(donchian_mid) and close_val > donchian_mid:
            return False
        return True

    def check_breakout_long_signal(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        Breakout long for bullish regimes: close above upper Bollinger band with
        trend/momentum alignment and stronger-than-average volume.
        """
        if df.empty or len(df) < self.get_min_signal_candles():
            return False

        latest = df.iloc[-1]
        bbu_col = [c for c in df.columns if c.startswith('BBU_')]
        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        macdh_col = [c for c in df.columns if c.startswith('MACDh_')]
        ema_fast_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_FAST')}"]
        ema_slow_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_SLOW')}"]

        if not bbu_col or not rsi_col:
            return False

        close_val = latest['close']
        bbu_val = latest[bbu_col[0]]
        rsi_val = latest[rsi_col[0]]
        if pd.isna(close_val) or pd.isna(bbu_val) or pd.isna(rsi_val):
            return False

        breakout_signal = close_val >= bbu_val * (1 + self.get_param('BREAKOUT_BUFFER_PCT'))
        rsi_signal = self.get_param('BREAKOUT_LONG_RSI_MIN') <= rsi_val <= self.get_param('BREAKOUT_LONG_RSI_MAX')

        ema_signal = True
        if ema_fast_col and ema_slow_col:
            ema_fast = latest[ema_fast_col[0]]
            ema_slow = latest[ema_slow_col[0]]
            if pd.isna(ema_fast) or pd.isna(ema_slow):
                ema_signal = False
            else:
                ema_signal = ema_fast > ema_slow

        macd_signal = True
        if macdh_col:
            macdh_val = latest[macdh_col[0]]
            if pd.isna(macdh_val):
                macd_signal = False
            else:
                macd_signal = macdh_val > 0

        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * self.get_param('BREAKOUT_VOLUME_MULT')

        if not (breakout_signal and rsi_signal and ema_signal and macd_signal and vol_filter):
            return False

        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            return predicted_close > close_val

        return True

    def check_breakout_short_signal(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        Breakout short for bearish regimes: close below lower Bollinger band with
        trend/momentum alignment and stronger-than-average volume.
        """
        if df.empty or len(df) < self.get_min_signal_candles():
            return False

        latest = df.iloc[-1]
        bbl_col = [c for c in df.columns if c.startswith('BBL_')]
        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        macdh_col = [c for c in df.columns if c.startswith('MACDh_')]
        ema_fast_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_FAST')}"]
        ema_slow_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_SLOW')}"]

        if not bbl_col or not rsi_col:
            return False

        close_val = latest['close']
        bbl_val = latest[bbl_col[0]]
        rsi_val = latest[rsi_col[0]]
        if pd.isna(close_val) or pd.isna(bbl_val) or pd.isna(rsi_val):
            return False

        breakout_signal = close_val <= bbl_val * (1 - self.get_param('BREAKOUT_BUFFER_PCT'))
        rsi_signal = self.get_param('BREAKOUT_SHORT_RSI_MIN') <= rsi_val <= self.get_param('BREAKOUT_SHORT_RSI_MAX')

        ema_signal = True
        if ema_fast_col and ema_slow_col:
            ema_fast = latest[ema_fast_col[0]]
            ema_slow = latest[ema_slow_col[0]]
            if pd.isna(ema_fast) or pd.isna(ema_slow):
                ema_signal = False
            else:
                ema_signal = ema_fast < ema_slow

        macd_signal = True
        if macdh_col:
            macdh_val = latest[macdh_col[0]]
            if pd.isna(macdh_val):
                macd_signal = False
            else:
                macd_signal = macdh_val < 0

        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * self.get_param('BREAKOUT_VOLUME_MULT')

        if not (breakout_signal and rsi_signal and ema_signal and macd_signal and vol_filter):
            return False

        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            return predicted_close < close_val

        return True

    def check_tier_1_long_signal(self, symbol: str, df: pd.DataFrame, signal_mode: str = None) -> bool:
        """
        Checks if conditions for Tier 1 Long entry are met.
        signal_mode: 'classic' (RSI+BB only) or 'multi' (RSI+BB, MACD, EMA crossover)
        """
        if signal_mode is None:
            signal_mode = self.get_param('SIGNAL_MODE')

        if df.empty or len(df) < self.get_min_signal_candles():
            return False

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        bbl_col = [c for c in df.columns if c.startswith('BBL_')]
        macd_col = [c for c in df.columns if c.startswith('MACD_') and not c.startswith('MACDs_') and not c.startswith('MACDh_')]
        macdh_col = [c for c in df.columns if c.startswith('MACDh_')]
        ema_fast_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_FAST')}"]
        ema_slow_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_SLOW')}"]

        if not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        if pd.isna(rsi_val):
            return False

        long_rsi_threshold, _ = self.get_entry_rsi_thresholds(df)

        # Strategy 1: Original RSI + Bollinger Band (always active)
        bb_signal = False
        if bbl_col:
            bbl_val = latest[bbl_col[0]]
            close_val = latest['close']
            if not pd.isna(bbl_val):
                bb_buffer = 1 + self.get_param('BB_ENTRY_BUFFER_PCT')
                bb_signal = (rsi_val < long_rsi_threshold and close_val <= bbl_val * bb_buffer)

        if signal_mode == 'classic':
            traditional_signal = bb_signal
        else:
            # Strategy 2: MACD Bullish Crossover + RSI confirmation
            macd_signal = False
            if macdh_col and prev is not None:
                macdh_val = latest[macdh_col[0]]
                macdh_prev = prev[macdh_col[0]]
                if not pd.isna(macdh_val) and not pd.isna(macdh_prev):
                    macd_signal = (
                        macdh_prev < 0 and macdh_val > 0 and
                        rsi_val < self.get_param('MACD_LONG_RSI_MAX')
                    )

            # Strategy 3: EMA Crossover + RSI confirmation
            ema_signal = False
            if ema_fast_col and ema_slow_col and prev is not None:
                ema_fast = latest[ema_fast_col[0]]
                ema_slow = latest[ema_slow_col[0]]
                ema_fast_prev = prev[ema_fast_col[0]]
                ema_slow_prev = prev[ema_slow_col[0]]
                if not any(pd.isna(v) for v in [ema_fast, ema_slow, ema_fast_prev, ema_slow_prev]):
                    ema_signal = (
                        ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow and
                        rsi_val < self.get_param('EMA_LONG_RSI_MAX')
                    )

            traditional_signal = bb_signal or macd_signal or ema_signal

        # Volume filter: only trade when volume is above average
        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * self.get_param('VOLUME_FILTER_MULT')

        if not (traditional_signal and vol_filter):
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

    def check_tier_1_short_signal(self, symbol: str, df: pd.DataFrame, signal_mode: str = None) -> bool:
        """
        Checks if conditions for Tier 1 Short entry are met.
        signal_mode: 'classic' (RSI+BB only) or 'multi' (RSI+BB, MACD, EMA crossover)
        """
        if signal_mode is None:
            signal_mode = self.get_param('SIGNAL_MODE')

        if df.empty or len(df) < self.get_min_signal_candles():
            return False

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        bbu_col = [c for c in df.columns if c.startswith('BBU_')]
        macdh_col = [c for c in df.columns if c.startswith('MACDh_')]
        ema_fast_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_FAST')}"]
        ema_slow_col = [c for c in df.columns if c == f"EMA_{self.get_param('EMA_SLOW')}"]

        if not rsi_col:
            return False

        rsi_val = latest[rsi_col[0]]
        if pd.isna(rsi_val):
            return False

        _, short_rsi_threshold = self.get_entry_rsi_thresholds(df)

        # Strategy 1: Original RSI + Bollinger Band (always active)
        bb_signal = False
        if bbu_col:
            bbu_val = latest[bbu_col[0]]
            close_val = latest['close']
            if not pd.isna(bbu_val):
                bb_buffer = 1 - self.get_param('BB_ENTRY_BUFFER_PCT')
                bb_signal = (rsi_val > short_rsi_threshold and close_val >= bbu_val * bb_buffer)

        if signal_mode == 'classic':
            traditional_signal = bb_signal
        else:
            # Strategy 2: MACD Bearish Crossover + RSI confirmation
            macd_signal = False
            if macdh_col and prev is not None:
                macdh_val = latest[macdh_col[0]]
                macdh_prev = prev[macdh_col[0]]
                if not pd.isna(macdh_val) and not pd.isna(macdh_prev):
                    macd_signal = (
                        macdh_prev > 0 and macdh_val < 0 and
                        rsi_val > self.get_param('MACD_SHORT_RSI_MIN')
                    )

            # Strategy 3: EMA Crossover + RSI confirmation
            ema_signal = False
            if ema_fast_col and ema_slow_col and prev is not None:
                ema_fast = latest[ema_fast_col[0]]
                ema_slow = latest[ema_slow_col[0]]
                ema_fast_prev = prev[ema_fast_col[0]]
                ema_slow_prev = prev[ema_slow_col[0]]
                if not any(pd.isna(v) for v in [ema_fast, ema_slow, ema_fast_prev, ema_slow_prev]):
                    ema_signal = (
                        ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow and
                        rsi_val > self.get_param('EMA_SHORT_RSI_MIN')
                    )

            traditional_signal = bb_signal or macd_signal or ema_signal

        # Volume filter
        vol_filter = True
        if 'vol_sma_20' in df.columns:
            vol_sma = latest['vol_sma_20']
            if not pd.isna(vol_sma) and vol_sma > 0:
                vol_filter = latest['volume'] >= vol_sma * self.get_param('VOLUME_FILTER_MULT')

        if not (traditional_signal and vol_filter):
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

        if self.get_param('MOMENTUM_GATED_DCA'):
            atr_ratio = self.get_atr_ratio(df)
            if atr_ratio is not None and atr_ratio > self.get_param('TIER_2_MAX_ATR_RATIO'):
                return False

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        if not rsi_col: return False

        latest_rsi = df.iloc[-1][rsi_col[0]]
        prev_rsi = df.iloc[-2][rsi_col[0]]

        if pd.isna(latest_rsi) or pd.isna(prev_rsi):
            return False

        if direction == 'long':
            if current_price > avg_entry_price * (1 - dev_pct):
                return False
            if self.get_param('MOMENTUM_GATED_DCA'):
                return latest_rsi <= self.get_param('TIER_2_LONG_RSI_MAX') and latest_rsi >= prev_rsi
            return (latest_rsi < 35 or latest_rsi > prev_rsi)
        else:
            if current_price < avg_entry_price * (1 + dev_pct):
                return False
            if self.get_param('MOMENTUM_GATED_DCA'):
                return latest_rsi >= self.get_param('TIER_2_SHORT_RSI_MIN') and latest_rsi <= prev_rsi
            return (latest_rsi > 65 or latest_rsi < prev_rsi)

    def check_tier_3_signal(self, current_price: float, avg_entry_price: float, dev_pct: float, direction: str, df: pd.DataFrame = None) -> bool:
        """
        Checks if conditions for Tier 3 entry are met.
        """
        if self.get_param('MOMENTUM_GATED_DCA') and (df is None or df.empty):
            return False

        if self.get_param('MOMENTUM_GATED_DCA') and df is not None and not df.empty:
            atr_ratio = self.get_atr_ratio(df)
            if atr_ratio is not None and atr_ratio > self.get_param('TIER_3_MAX_ATR_RATIO'):
                return False

            rsi_col = [c for c in df.columns if c.startswith('RSI_')]
            if len(df) >= 2 and rsi_col:
                latest_rsi = df.iloc[-1][rsi_col[0]]
                prev_rsi = df.iloc[-2][rsi_col[0]]
                if pd.isna(latest_rsi) or pd.isna(prev_rsi):
                    return False
                if direction == 'long':
                    if latest_rsi > self.get_param('TIER_3_LONG_RSI_RECOVERY') or latest_rsi < prev_rsi:
                        return False
                else:
                    if latest_rsi < self.get_param('TIER_3_SHORT_RSI_RECOVERY') or latest_rsi > prev_rsi:
                        return False

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
