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
            # We send the last 400 candles to the AI
            lookback_df = df.tail(400).copy()
            # Ensure 'timestamp' column is correctly formatted as string
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
        Adds RSI and Bollinger Bands to the dataframe.
        """
        if df.empty or len(df) < 20:
            return df

        # Calculate RSI
        df.ta.rsi(length=14, append=True)

        # Calculate Bollinger Bands (20, 2)
        df.ta.bbands(length=20, std=2, append=True)

        return df

    def calculate_daily_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates long-term indicators on daily data for trend filtering.
        Specifically adds a configurable SMA.
        """
        sma_len = config.TREND_SMA_LENGTH
        if df.empty or len(df) < sma_len:
            return df

        df.ta.sma(length=sma_len, append=True)
        return df

    def get_market_regime(self, df_daily: pd.DataFrame) -> str:
        """
        Determines the current market regime (bull or bear) based on the 1D SMA.
        Returns 'bull', 'bear', or 'neutral' (if insufficient data).
        """
        if df_daily.empty or len(df_daily) < 1:
            return 'neutral'

        latest = df_daily.iloc[-1]
        sma_col = [c for c in df_daily.columns if c.startswith(f'SMA_{config.TREND_SMA_LENGTH}')]

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
        Condition: RSI < RSI_LONG_ENTRY AND Price touches/crosses lower Bollinger Band.
        """
        if df.empty or len(df) < 20:
            return False

        latest = df.iloc[-1]

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        bbl_col = [c for c in df.columns if c.startswith('BBL_')]

        if not rsi_col or not bbl_col: return False

        rsi_val = latest[rsi_col[0]]
        bbl_val = latest[bbl_col[0]]
        close_val = latest['close']

        if pd.isna(rsi_val) or pd.isna(bbl_val): return False

        traditional_signal = (rsi_val < config.RSI_LONG_ENTRY and close_val <= bbl_val)

        if not traditional_signal:
            return False

        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            if predicted_close > close_val:
                logger.info(f"Tier 1 LONG AI confirmation passed: Predicted {predicted_close} > Current {close_val}")
                return True
            else:
                logger.info(f"Tier 1 LONG AI confirmation failed. Skipping.")
                return False

        return True

    def check_tier_1_short_signal(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        Checks if conditions for Tier 1 Short entry are met.
        Condition: RSI > RSI_SHORT_ENTRY AND Price touches/crosses upper Bollinger Band.
        """
        if df.empty or len(df) < 20:
            return False

        latest = df.iloc[-1]

        rsi_col = [c for c in df.columns if c.startswith('RSI_')]
        bbu_col = [c for c in df.columns if c.startswith('BBU_')]

        if not rsi_col or not bbu_col: return False

        rsi_val = latest[rsi_col[0]]
        bbu_val = latest[bbu_col[0]]
        close_val = latest['close']

        if pd.isna(rsi_val) or pd.isna(bbu_val): return False

        traditional_signal = (rsi_val > config.RSI_SHORT_ENTRY and close_val >= bbu_val)

        if not traditional_signal:
            return False

        predicted_close = self.get_ai_prediction(symbol, df)
        if predicted_close is not None:
            if predicted_close < close_val:
                logger.info(f"Tier 1 SHORT AI confirmation passed: Predicted {predicted_close} < Current {close_val}")
                return True
            else:
                logger.info(f"Tier 1 SHORT AI confirmation failed. Skipping.")
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
            # Price must drop below entry by dev_pct
            if current_price > avg_entry_price * (1 - dev_pct):
                return False
            # Momentum: oversold or turning up
            return (latest_rsi < 35 or latest_rsi > prev_rsi)
        else:
            # Price must rise above entry by dev_pct
            if current_price < avg_entry_price * (1 + dev_pct):
                return False
            # Momentum: overbought or turning down
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
