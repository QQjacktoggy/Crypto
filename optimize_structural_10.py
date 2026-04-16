"""
optimize_structural_10.py - Round 4 structural optimizer

Focus:
1. Volatility-adaptive entry thresholds
2. Momentum-gated DCA tiers
3. Keep leverage and sizing closer to the current profitable region
"""

import logging
import sys
from datetime import datetime

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config


PARAM_SETS = [
    {  # 1 control: round-3 best
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
        'VOLATILITY_ADAPTIVE_ENTRY': False, 'MOMENTUM_GATED_DCA': False,
    },
    {  # 2
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.20, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 29, 'RSI_LONG_ENTRY_LOW_VOL': 38, 'RSI_SHORT_ENTRY_HIGH_VOL': 71, 'RSI_SHORT_ENTRY_LOW_VOL': 62,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.9, 'TIER_3_MAX_ATR_RATIO': 1.6,
        'TIER_2_LONG_RSI_MAX': 40, 'TIER_2_SHORT_RSI_MIN': 60, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 3
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.1, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.50, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.48,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.007, 'VOLUME_FILTER_MULT': 0.42,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 120, 'HIGH_VOL_THRESHOLD': 1.25, 'LOW_VOL_THRESHOLD': 0.90,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 39, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 61,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.7, 'MIN_TIER_DEV_PCT': 0.0025,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.8, 'TIER_3_MAX_ATR_RATIO': 1.5,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.014, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 4
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 2.9, 'ATR_SL_MULT': 1.3,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.42, 'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.45,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.080, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.40,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.15, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 40, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 60,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.6, 'MIN_TIER_DEV_PCT': 0.0025,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.7, 'TIER_3_MAX_ATR_RATIO': 1.4,
        'TIER_2_LONG_RSI_MAX': 38, 'TIER_2_SHORT_RSI_MIN': 62, 'TIER_3_LONG_RSI_RECOVERY': 33, 'TIER_3_SHORT_RSI_RECOVERY': 67,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.28, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.14, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.013, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
    {  # 5
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 5, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.42,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 120, 'HIGH_VOL_THRESHOLD': 1.25, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 28, 'RSI_LONG_ENTRY_LOW_VOL': 39, 'RSI_SHORT_ENTRY_HIGH_VOL': 72, 'RSI_SHORT_ENTRY_LOW_VOL': 61,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.2, 'TIER_3_ATR_DEV_MULT': 1.9, 'MIN_TIER_DEV_PCT': 0.0030,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 2.0, 'TIER_3_MAX_ATR_RATIO': 1.7,
        'TIER_2_LONG_RSI_MAX': 40, 'TIER_2_SHORT_RSI_MIN': 60, 'TIER_3_LONG_RSI_RECOVERY': 35, 'TIER_3_SHORT_RSI_RECOVERY': 65,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.018, 'SL_GLOBAL_CAP_PCT': -0.08,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
    {  # 6
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'multi',
        'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.007, 'VOLUME_FILTER_MULT': 0.40,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.25, 'LOW_VOL_THRESHOLD': 0.90,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 40, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 60,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.9, 'TIER_3_MAX_ATR_RATIO': 1.6,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 7
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.2, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.14, 'ATR_TP_MAX_ROI': 0.50, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.52,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.095, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.38,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 144, 'HIGH_VOL_THRESHOLD': 1.30, 'LOW_VOL_THRESHOLD': 0.90,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 41, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 59,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.7, 'MIN_TIER_DEV_PCT': 0.0020,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.8, 'TIER_3_MAX_ATR_RATIO': 1.5,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 35, 'TIER_3_SHORT_RSI_RECOVERY': 65,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.16, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.014, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.22, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 8
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 2.8, 'ATR_SL_MULT': 1.3,
        'ATR_TP_MIN_ROI': 0.10, 'ATR_TP_MAX_ROI': 0.40, 'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.45,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.075, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65, 'BB_ENTRY_BUFFER_PCT': 0.010, 'VOLUME_FILTER_MULT': 0.38,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.15, 'LOW_VOL_THRESHOLD': 0.80,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 42, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 58,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.6, 'MIN_TIER_DEV_PCT': 0.0025,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.7, 'TIER_3_MAX_ATR_RATIO': 1.4,
        'TIER_2_LONG_RSI_MAX': 40, 'TIER_2_SHORT_RSI_MIN': 60, 'TIER_3_LONG_RSI_RECOVERY': 35, 'TIER_3_SHORT_RSI_RECOVERY': 65,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.14, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.013, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
    {  # 9
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.1, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.48, 'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.52,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.42,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 120, 'HIGH_VOL_THRESHOLD': 1.35, 'LOW_VOL_THRESHOLD': 0.95,
        'RSI_LONG_ENTRY_HIGH_VOL': 29, 'RSI_LONG_ENTRY_LOW_VOL': 37, 'RSI_SHORT_ENTRY_HIGH_VOL': 71, 'RSI_SHORT_ENTRY_LOW_VOL': 63,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.2, 'TIER_3_ATR_DEV_MULT': 1.9, 'MIN_TIER_DEV_PCT': 0.0025,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 2.0, 'TIER_3_MAX_ATR_RATIO': 1.7,
        'TIER_2_LONG_RSI_MAX': 41, 'TIER_2_SHORT_RSI_MIN': 59, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 6,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.009, 'TIER_3_DEV_PCT': 0.016, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 10
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 72, 'HIGH_VOL_THRESHOLD': 1.10, 'LOW_VOL_THRESHOLD': 0.75,
        'RSI_LONG_ENTRY_HIGH_VOL': 31, 'RSI_LONG_ENTRY_LOW_VOL': 42, 'RSI_SHORT_ENTRY_HIGH_VOL': 69, 'RSI_SHORT_ENTRY_LOW_VOL': 58,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 0.9, 'TIER_3_ATR_DEV_MULT': 1.5, 'MIN_TIER_DEV_PCT': 0.0020,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.6, 'TIER_3_MAX_ATR_RATIO': 1.3,
        'TIER_2_LONG_RSI_MAX': 37, 'TIER_2_SHORT_RSI_MIN': 63, 'TIER_3_LONG_RSI_RECOVERY': 32, 'TIER_3_SHORT_RSI_RECOVERY': 68,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.14, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.013, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
]


def run_single_iteration(iteration_num, params, days=365):
    try:
        full_params = {
            'EMA_FAST': config.EMA_FAST,
            'EMA_SLOW': config.EMA_SLOW,
            'MACD_FAST': config.MACD_FAST,
            'MACD_SLOW': config.MACD_SLOW,
            'MACD_SIGNAL': config.MACD_SIGNAL,
            'TREND_SMA_LENGTH': config.TREND_SMA_LENGTH,
            'FUNDING_RATE': config.FUNDING_RATE,
            'FUNDING_INTERVAL_HOURS': config.FUNDING_INTERVAL_HOURS,
            'FEE_RATE': config.FEE_RATE,
            'COMPOUND_MODE': config.COMPOUND_MODE,
            'BASE_CAPITAL': config.BASE_CAPITAL,
            'MAX_ACTIVE_TRADES': config.MAX_ACTIVE_TRADES,
            'COOLDOWN_CANDLES': config.COOLDOWN_CANDLES,
            'MONTHLY_LOSS_LIMIT_PCT': config.MONTHLY_LOSS_LIMIT_PCT,
        }
        full_params.update(params)

        engine = BacktestEngine(days=days, param_overrides=full_params)
        engine.run()

        monthly_data = engine.get_monthly_pnl_report()
        closed_trades = [t for t in engine.trades if t['type'] == 'close']
        total_pnl = sum(t['pnl'] for t in closed_trades)

        result = {
            'iteration': iteration_num,
            'params': params,
            'initial_balance': engine.initial_balance,
            'final_balance': engine.current_balance,
            'total_pnl': total_pnl,
            'total_trades': len(closed_trades),
            'win_rate': (sum(1 for t in closed_trades if t['pnl'] > 0) / len(closed_trades) * 100) if closed_trades else 0,
            'max_drawdown': engine.max_drawdown * 100,
            'monthly_data': monthly_data,
        }

        if monthly_data:
            monthly_pnls = [m['net_pnl'] for m in monthly_data]
            result['avg_monthly_pnl'] = sum(monthly_pnls) / len(monthly_pnls)
            result['best_month'] = max(monthly_pnls)
            result['months_above_40'] = sum(1 for p in monthly_pnls if p >= 40)
        else:
            result['avg_monthly_pnl'] = 0
            result['best_month'] = 0
            result['months_above_40'] = 0

        return result
    except Exception as e:
        return {
            'iteration': iteration_num,
            'params': params,
            'error': str(e),
            'final_balance': 0,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'max_drawdown': 100,
            'monthly_data': [],
            'avg_monthly_pnl': 0,
            'best_month': 0,
            'months_above_40': 0,
        }


def save_results(results, filename="/home/runner/work/Crypto/Crypto/optimization_round4_structural.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Round 4 Structural Optimization Report\n")
        f.write(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Goal: yearly profit >= 400 USDT on {config.BASE_CAPITAL} USDT capital\n")
        f.write("=" * 72 + "\n\n")
        for result in results:
            f.write(f"Iteration #{result['iteration']}\n")
            if 'error' in result:
                f.write(f"  ERROR: {result['error']}\n\n")
                continue
            params = result['params']
            f.write(
                f"  PnL={result['total_pnl']:+.2f} | Final={result['final_balance']:.2f} | "
                f"WR={result['win_rate']:.1f}% | DD={result['max_drawdown']:.1f}% | "
                f"Trades={result['total_trades']} | AvgM={result['avg_monthly_pnl']:+.2f} | BestM={result['best_month']:+.2f}\n"
            )
            f.write(
                f"  Lev={params['LEVERAGE']}x Margin={params['TIER_MARGIN_PCT']:.3f} Mode={params['SIGNAL_MODE']} "
                f"BBbuf={params['BB_ENTRY_BUFFER_PCT']:.3f} Vol={params['VOLUME_FILTER_MULT']:.2f}\n"
            )
            f.write(
                f"  VolAdapt={params.get('VOLATILITY_ADAPTIVE_ENTRY', False)} "
                f"High/Low={params.get('HIGH_VOL_THRESHOLD', 0):.2f}/{params.get('LOW_VOL_THRESHOLD', 0):.2f} "
                f"DCAgate={params.get('MOMENTUM_GATED_DCA', False)} "
                f"T2/T3 ATR gate={params.get('TIER_2_MAX_ATR_RATIO', 0):.2f}/{params.get('TIER_3_MAX_ATR_RATIO', 0):.2f}\n\n"
            )


def main():
    print("=" * 72)
    print("🚀 ROUND 4 STRUCTURAL OPTIMIZER (10 ITERATIONS)")
    print("=" * 72)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print("Target: yearly profit >= 400 USDT")
    print("Axes: volatility-adaptive entry + momentum-gated DCA")
    print("=" * 72)

    all_results = []
    for i, params in enumerate(PARAM_SETS, start=1):
        sys.stdout.write(f"\r⏳ Running iteration {i}/10...")
        sys.stdout.flush()
        result = run_single_iteration(i, params)
        all_results.append(result)
        if 'error' in result:
            sys.stdout.write(f"\r❌ Iteration {i}/10 | ERROR: {result['error']}\n")
        else:
            sys.stdout.write(
                f"\r✅ Iteration {i}/10 | PnL: {result['total_pnl']:+.2f} | "
                f"WR: {result['win_rate']:.1f}% | DD: {result['max_drawdown']:.1f}% | "
                f"Trades: {result['total_trades']}\n"
            )

    valid = [r for r in all_results if 'error' not in r and r['total_trades'] > 0]
    if not valid:
        print("\n❌ No valid results.")
        save_results(all_results)
        return

    valid.sort(key=lambda r: r['total_pnl'], reverse=True)
    best = valid[0]

    print("\n" + "=" * 72)
    print("🏆 ROUND 4 RANKING BY TOTAL PNL")
    print("=" * 72)
    for rank, result in enumerate(valid, start=1):
        params = result['params']
        marker = " ⭐ BEST" if rank == 1 else ""
        print(
            f"#{rank} Iter {result['iteration']}{marker} | PnL {result['total_pnl']:+.2f} | "
            f"Final {result['final_balance']:.2f} | DD {result['max_drawdown']:.1f}% | "
            f"Trades {result['total_trades']} | Mode {params['SIGNAL_MODE']} | "
            f"VolAdapt {params.get('VOLATILITY_ADAPTIVE_ENTRY', False)} | "
            f"DCAgate {params.get('MOMENTUM_GATED_DCA', False)}"
        )

    print("\n" + "=" * 72)
    print(f"Best yearly PnL: {best['total_pnl']:+.2f} USDT")
    print(f"Target 400 USDT reached: {'YES' if best['total_pnl'] >= 400 else 'NO'}")
    print("=" * 72)

    save_results(all_results)


if __name__ == "__main__":
    main()
