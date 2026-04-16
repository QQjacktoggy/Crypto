"""
Minimal pandas-ta shim
======================
Implements only the indicators used by signal_logic.py:
  - RSI (Wilder EMA method)
  - Bollinger Bands
  - SMA

Attaches a `.ta` accessor to pandas DataFrames with the same API
(`rsi`, `bbands`, `sma` with `append=True`).
"""

import numpy as np
import pandas as pd

__version__ = "shim-0.1.0"


# ── Pure-function implementations ────────────────────────────────────────────

def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """RSI via Wilder smoothing (EMA with alpha = 1/length)."""
    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    avg_g  = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_l  = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs     = avg_g / avg_l.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result.name = f"RSI_{length}"
    return result


def bbands(close: pd.Series, length: int = 20, std: float = 2.0):
    """Bollinger Bands — returns (BBL, BBM, BBU, BBB, BBP)."""
    mid = close.rolling(length).mean()
    sd  = close.rolling(length).std(ddof=0)
    lo  = mid - std * sd
    hi  = mid + std * sd
    bw  = (hi - lo) / mid.replace(0, np.nan)        # bandwidth
    pct = (close - lo) / (hi - lo).replace(0, np.nan)  # %B

    tag = f"_{length}_{float(std)}"
    lo.name, mid.name, hi.name  = f"BBL{tag}", f"BBM{tag}", f"BBU{tag}"
    bw.name, pct.name           = f"BBB{tag}", f"BBP{tag}"
    return lo, mid, hi, bw, pct


def sma(close: pd.Series, length: int) -> pd.Series:
    result = close.rolling(length).mean()
    result.name = f"SMA_{length}"
    return result


# ── DataFrame accessor ───────────────────────────────────────────────────────

@pd.api.extensions.register_dataframe_accessor("ta")
class _TaAccessor:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def rsi(self, length: int = 14, append: bool = False) -> pd.Series:
        result = rsi(self._df["close"], length)
        if append:
            self._df[result.name] = result
        return result

    def bbands(self, length: int = 20, std: float = 2.0, append: bool = False):
        lo, mid, hi, bw, pct = bbands(self._df["close"], length, std)
        if append:
            for s in (lo, mid, hi, bw, pct):
                self._df[s.name] = s
        return pd.DataFrame({lo.name: lo, mid.name: mid, hi.name: hi,
                              bw.name: bw, pct.name: pct})

    def sma(self, length: int, append: bool = False) -> pd.Series:
        result = sma(self._df["close"], length)
        if append:
            self._df[result.name] = result
        return result
